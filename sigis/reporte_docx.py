"""
Generacion del reporte mensual en formato Word (.docx).

Un archivo .docx es, por dentro, un ZIP con varios documentos XML. Como
Python trae `zipfile` en su libreria estandar, el reporte se construye
aqui sin instalar ninguna dependencia: se arma el XML del documento y se
empaqueta.

Cumple la historia de usuario HU-21 (exportar el reporte mensual para
adjuntarlo al informe a la gerencia). La informacion que se imprime es
exactamente la misma que calcula `indicadores.CalculadoraIndicadores`:
este modulo solo le da forma, no calcula nada.
"""

import io
import zipfile
from datetime import datetime
from xml.sax.saxutils import escape

from .enums import COSTO_HORA_INDISPONIBILIDAD

AZUL = "14233D"
NARANJA = "C2611F"
GRIS = "F2F3F0"
ANCHO_UTIL = 9638          # A4 menos margenes, en twips

MESES = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio",
         "agosto", "setiembre", "octubre", "noviembre", "diciembre"]

NS = ('xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main" '
      'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"')


# ===========================================================================
#  Piezas del documento
# ===========================================================================
def _visible(valor):
    """Valor de una enumeracion como debe leerse en el documento."""
    texto = getattr(valor, "value", valor)
    return {"CRITICO": "CRÍTICO", "En atencion": "En atención"}.get(texto, texto)


def _texto(valor):
    return escape("" if valor is None else str(valor))


def _corrida(texto, negrita=False, tam=20, color="000000", fuente="Arial"):
    """Una 'corrida' (w:r) es un fragmento de texto con un formato."""
    props = [f'<w:rFonts w:ascii="{fuente}" w:hAnsi="{fuente}"/>']
    if negrita:
        props.append("<w:b/>")
    props.append(f'<w:color w:val="{color}"/>')
    props.append(f'<w:sz w:val="{tam}"/><w:szCs w:val="{tam}"/>')
    return (f'<w:r><w:rPr>{"".join(props)}</w:rPr>'
            f'<w:t xml:space="preserve">{_texto(texto)}</w:t></w:r>')


def _parrafo(texto="", negrita=False, tam=20, color="000000", alineacion=None,
             espacio_antes=0, espacio_despues=120, estilo=None):
    props = []
    if estilo:
        props.append(f'<w:pStyle w:val="{estilo}"/>')
    if alineacion:
        props.append(f'<w:jc w:val="{alineacion}"/>')
    props.append(f'<w:spacing w:before="{espacio_antes}" w:after="{espacio_despues}"/>')
    corrida = _corrida(texto, negrita, tam, color) if texto != "" else ""
    return f"<w:p><w:pPr>{''.join(props)}</w:pPr>{corrida}</w:p>"


def _titulo_seccion(numero, texto):
    return (f'<w:p><w:pPr><w:pStyle w:val="Titulo2"/>'
            f'<w:spacing w:before="280" w:after="120"/></w:pPr>'
            f'{_corrida(f"{numero}. {texto}", True, 24, AZUL)}</w:p>')


def _celda(texto, ancho, negrita=False, fondo=None, color="000000",
           alineacion=None, tam=19):
    sombra = f'<w:shd w:val="clear" w:color="auto" w:fill="{fondo}"/>' if fondo else ""
    props = (f'<w:tcPr><w:tcW w:w="{ancho}" w:type="dxa"/>{sombra}'
             f'<w:vAlign w:val="center"/>'
             f'<w:tcMar><w:top w:w="60" w:type="dxa"/><w:bottom w:w="60" w:type="dxa"/>'
             f'<w:left w:w="110" w:type="dxa"/><w:right w:w="110" w:type="dxa"/></w:tcMar>'
             f'</w:tcPr>')
    jc = f'<w:jc w:val="{alineacion}"/>' if alineacion else ""
    parrafo = (f'<w:p><w:pPr>{jc}<w:spacing w:before="0" w:after="0"/></w:pPr>'
               f'{_corrida(texto, negrita, tam, color)}</w:p>')
    return f"<w:tc>{props}{parrafo}</w:tc>"


def _tabla(cabeceras, filas, proporciones=None):
    """Construye una tabla con cabecera azul y filas alternadas."""
    columnas = len(cabeceras)
    proporciones = proporciones or [1] * columnas
    total = sum(proporciones)
    anchos = [int(ANCHO_UTIL * prop / total) for prop in proporciones]
    anchos[-1] += ANCHO_UTIL - sum(anchos)

    borde = ('<w:top w:val="single" w:sz="4" w:color="D0D4CC"/>'
             '<w:left w:val="single" w:sz="4" w:color="D0D4CC"/>'
             '<w:bottom w:val="single" w:sz="4" w:color="D0D4CC"/>'
             '<w:right w:val="single" w:sz="4" w:color="D0D4CC"/>'
             '<w:insideH w:val="single" w:sz="4" w:color="D0D4CC"/>'
             '<w:insideV w:val="single" w:sz="4" w:color="D0D4CC"/>')
    props = (f'<w:tblPr><w:tblW w:w="{ANCHO_UTIL}" w:type="dxa"/>'
             f'<w:tblBorders>{borde}</w:tblBorders>'
             f'<w:tblLayout w:type="fixed"/></w:tblPr>')
    rejilla = ("<w:tblGrid>"
               + "".join(f'<w:gridCol w:w="{a}"/>' for a in anchos)
               + "</w:tblGrid>")

    partes = [f"<w:tbl>{props}{rejilla}"]
    celdas = "".join(
        _celda(t, anchos[i], True, AZUL, "FFFFFF",
               "center" if i else None)
        for i, t in enumerate(cabeceras))
    partes.append(f'<w:tr><w:trPr><w:tblHeader/></w:trPr>{celdas}</w:tr>')

    for n, fila in enumerate(filas):
        fondo = GRIS if n % 2 == 0 else None
        celdas = "".join(
            _celda(valor, anchos[i], i == 0, fondo,
                   alineacion="center" if i else None)
            for i, valor in enumerate(fila))
        partes.append(f"<w:tr>{celdas}</w:tr>")

    partes.append("</w:tbl>")
    # Word exige un parrafo despues de cada tabla.
    partes.append('<w:p><w:pPr><w:spacing w:after="80"/></w:pPr></w:p>')
    return "".join(partes)


# ===========================================================================
#  Armado del cuerpo del reporte
# ===========================================================================
def _cuerpo(datos, parque, anio, mes, total_equipos):
    def n(valor, sufijo=""):
        return "no calculable" if valor is None else f"{valor}{sufijo}"

    partes = []

    # --- Portada del reporte ---
    partes.append(_parrafo("MADISON LATAM  ·  ÁREA DE TECNOLOGÍAS DE LA INFORMACIÓN",
                           True, 16, NARANJA, "center", 0, 60))
    partes.append(_parrafo("Reporte mensual de incidentes de seguridad",
                           True, 40, AZUL, "center", 0, 60))
    partes.append(_parrafo(f"{MESES[mes - 1].capitalize()} de {anio}",
                           False, 24, "4A5568", "center", 0, 360))

    if datos["total_alertas"] == 0:
        partes.append(_parrafo(
            "En el período seleccionado no se registraron incidentes.",
            False, 22, "000000", "center"))
        return "".join(partes)

    # --- 1. Resumen ---
    partes.append(_titulo_seccion(1, "Resumen del período"))
    partes.append(_tabla(
        ["Concepto", "Cantidad"],
        [["Alertas registradas", datos["total_alertas"]],
         ["Incidentes confirmados", datos["confirmados"]],
         ["Falsos positivos", datos["falsos_positivos"]]],
        [4, 1]))

    # --- 2. Criticidad ---
    partes.append(_titulo_seccion(2, "Distribución por criticidad"))
    partes.append(_tabla(
        ["Nivel de criticidad", "Incidentes"],
        [[_visible(k), v] for k, v in datos["por_criticidad"].items() if v]
        or [["Sin datos", 0]],
        [4, 1]))

    # --- 3. Amenazas ---
    partes.append(_titulo_seccion(3, "Tipos de amenaza detectados"))
    partes.append(_tabla(
        ["Tipo de amenaza", "Casos"],
        [[k, v] for k, v in datos["malware"]] or [["Sin amenazas confirmadas", 0]],
        [4, 1]))

    # --- 4. Equipos ---
    partes.append(_titulo_seccion(4, f"Estado de los equipos ({total_equipos} en el parque)"))
    partes.append(_parrafo("Situación al momento de generar el reporte.",
                           False, 18, "7A8494", espacio_despues=80))
    partes.append(_tabla(
        ["Estado", "Equipos"],
        [[k.value, v] for k, v in parque.items()
         if k != "total" and v] or [["Sin datos", 0]],
        [4, 1]))
    partes.append(_parrafo(
        f"Horas de indisponibilidad en el mes: {datos['horas_indisponibilidad']:.1f} h  "
        f"·  costo estimado S/ {datos['costo_indisponibilidad']:.2f} "
        f"(a S/ {COSTO_HORA_INDISPONIBILIDAD:.2f} la hora).",
        False, 19, "4A5568"))

    # --- 5. Monitoreo ---
    partes.append(_titulo_seccion(5, "Estado del monitoreo"))
    filas = []
    for origen, valores in datos["fp_por_origen"].items():
        filas.append([origen.value, valores["total"], valores["falsos"],
                      f"{valores['porcentaje']} %"])
    partes.append(_tabla(
        ["Origen de la alerta", "Alertas", "Falsos positivos", "Tasa"],
        filas or [["Sin datos", 0, 0, "0 %"]],
        [4, 1.4, 1.8, 1.2]))

    # --- 6. Indicadores ---
    partes.append(_titulo_seccion(6, "Indicadores del período"))
    partes.append(_tabla(
        ["Indicador", "Valor", "Qué mide"],
        [["MTTD", n(datos["mttd"], " h"), "Tiempo medio entre la ocurrencia y la detección"],
         ["MTTR", n(datos["mttr"], " h"),
          "Tiempo medio de resolución de los casos confirmados"],
         ["Cumplimiento", n(datos["cumplimiento"], " %"),
          "Casos resueltos dentro del tiempo objetivo (RN-04)"],
         ["Falsos positivos", n(datos["tasa_fp"], " %"),
          "Alertas que no resultaron incidentes reales"],
         ["Reincidencia", n(datos["reincidencia"], " %"),
          "Equipos con más de un incidente en 30 días"]],
        [1.8, 1.4, 5]))

    # --- 7. Carga por analista ---
    if datos["carga"]:
        partes.append(_titulo_seccion(7, "Carga de trabajo por analista"))
        partes.append(_tabla(
            ["Analista", "Casos atendidos"],
            [[k, f"{v['casos']}  ({v['porcentaje']} %)"]
             for k, v in sorted(datos["carga"].items())],
            [4, 1]))
        siguiente = 8
    else:
        siguiente = 7

    # --- 8. Datos personales ---
    partes.append(_titulo_seccion(siguiente, "Incidentes con datos personales (Ley 29733)"))
    con_datos = datos["con_datos_personales"]
    if not con_datos:
        partes.append(_parrafo(
            "Ningún incidente del período involucró datos personales.", False, 20))
    else:
        filas = []
        for inc in con_datos:
            limite = inc.fecha_limite_notificacion()
            filas.append([
                inc.codigo,
                inc.tipo_amenaza,
                inc.fecha_deteccion.strftime("%d/%m/%Y %H:%M"),
                limite.strftime("%d/%m/%Y %H:%M") if limite else "—",
                "Notificado" if inc.notificado_anpd else "PENDIENTE",
            ])
        partes.append(_tabla(
            ["Código", "Amenaza", "Detección", "Plazo límite (48 h)", "Estado"],
            filas, [1.6, 3, 2, 2, 1.7]))
        pendientes = sum(1 for i in con_datos if not i.notificado_anpd)
        if pendientes:
            partes.append(_parrafo(
                f"ATENCIÓN: {pendientes} incidente(s) con datos personales siguen "
                f"pendientes de notificación a la Autoridad Nacional de Protección "
                f"de Datos Personales.", True, 20, "B3261E"))

    # --- Pie ---
    partes.append(_parrafo("", espacio_despues=200))
    partes.append(_parrafo(
        f"Generado automáticamente por SIGIS el "
        f"{datetime.now().strftime('%d/%m/%Y a las %H:%M')}. "
        f"Los indicadores se calculan conforme a la regla de negocio RN-05 "
        f"del informe del proyecto.",
        False, 16, "7A8494", "center"))
    return "".join(partes)


# ===========================================================================
#  Empaquetado del .docx
# ===========================================================================
_CT = "application/vnd.openxmlformats-officedocument.wordprocessingml"
_REL = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"

_CONTENT_TYPES = f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
<Default Extension="rels"
 ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
<Default Extension="xml" ContentType="application/xml"/>
<Override PartName="/word/document.xml" ContentType="{_CT}.document.main+xml"/>
<Override PartName="/word/styles.xml" ContentType="{_CT}.styles+xml"/>
<Override PartName="/docProps/core.xml"
 ContentType="application/vnd.openxmlformats-package.core-properties+xml"/>
</Types>"""

_RELS = f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
<Relationship Id="rId1" Type="{_REL}/officeDocument" Target="word/document.xml"/>
<Relationship Id="rId2"
 Type="http://schemas.openxmlformats.org/package/2006/relationships/metadata/core-properties"
 Target="docProps/core.xml"/>
</Relationships>"""

_DOC_RELS = f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
<Relationship Id="rId1" Type="{_REL}/styles" Target="styles.xml"/>
</Relationships>"""

_ESTILOS = f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:styles {NS}>
<w:docDefaults><w:rPrDefault><w:rPr>
<w:rFonts w:ascii="Arial" w:hAnsi="Arial" w:cs="Arial"/>
<w:sz w:val="20"/><w:szCs w:val="20"/><w:lang w:val="es-PE"/>
</w:rPr></w:rPrDefault>
<w:pPrDefault><w:pPr>
<w:spacing w:after="120" w:line="252" w:lineRule="auto"/>
</w:pPr></w:pPrDefault>
</w:docDefaults>
<w:style w:type="paragraph" w:default="1" w:styleId="Normal">
<w:name w:val="Normal"/><w:qFormat/></w:style>
<w:style w:type="paragraph" w:styleId="Titulo2">
<w:name w:val="heading 2"/><w:basedOn w:val="Normal"/><w:next w:val="Normal"/>
<w:qFormat/><w:pPr><w:outlineLvl w:val="1"/><w:keepNext/></w:pPr>
<w:rPr><w:b/><w:color w:val="{AZUL}"/><w:sz w:val="24"/></w:rPr></w:style>
</w:styles>"""


def _propiedades(anio, mes):
    creado = datetime.now().strftime('%Y-%m-%dT%H:%M:%SZ')
    return f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<cp:coreProperties
 xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/core-properties"
 xmlns:dc="http://purl.org/dc/elements/1.1/" xmlns:dcterms="http://purl.org/dc/terms/"
 xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
<dc:title>Reporte mensual de incidentes - {MESES[mes - 1]} de {anio}</dc:title>
<dc:creator>SIGIS</dc:creator>
<cp:lastModifiedBy>SIGIS</cp:lastModifiedBy>
<dcterms:created xsi:type="dcterms:W3CDTF">{creado}</dcterms:created>
</cp:coreProperties>"""


def _documento(cuerpo):
    seccion = ('<w:sectPr><w:pgSz w:w="11906" w:h="16838"/>'
               '<w:pgMar w:top="1134" w:right="1134" w:bottom="1134" w:left="1134" '
               'w:header="708" w:footer="708" w:gutter="0"/></w:sectPr>')
    return (f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            f'<w:document {NS}><w:body>{cuerpo}{seccion}</w:body></w:document>')


class GeneradorReporteWord:
    """
    Produce el reporte mensual como documento de Word.

    Usa la misma calculadora de indicadores que el reporte de texto: no
    duplica ningun calculo, solo cambia el formato de salida (HU-21).
    """

    def __init__(self, repositorio, calculadora, servicio_equipos):
        self._repo = repositorio
        self._calc = calculadora
        self._equipos = servicio_equipos

    def generar(self, anio, mes):
        """Devuelve los bytes del archivo .docx."""
        from datetime import timedelta
        desde = datetime(anio, mes, 1)
        hasta = (datetime(anio + 1, 1, 1) if mes == 12
                 else datetime(anio, mes + 1, 1)) - timedelta(seconds=1)
        datos = self._calc.resumen(desde, hasta)
        parque = self._equipos.resumen_parque()

        cuerpo = _cuerpo(datos, parque, anio, mes, len(self._repo.equipos))

        memoria = io.BytesIO()
        with zipfile.ZipFile(memoria, "w", zipfile.ZIP_DEFLATED) as paquete:
            paquete.writestr("[Content_Types].xml", _CONTENT_TYPES)
            paquete.writestr("_rels/.rels", _RELS)
            paquete.writestr("docProps/core.xml", _propiedades(anio, mes))
            paquete.writestr("word/_rels/document.xml.rels", _DOC_RELS)
            paquete.writestr("word/styles.xml", _ESTILOS)
            paquete.writestr("word/document.xml", _documento(cuerpo))
        return memoria.getvalue()

    def nombre_archivo(self, anio, mes):
        return f"reporte_{anio}_{mes:02d}.docx"
