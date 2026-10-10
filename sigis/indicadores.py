"""
Calculo de los indicadores del proceso y generacion del reporte mensual.

Implementa las formulas de la regla RN-05 del informe (Tabla 12):
MTTD, MTTR, cumplimiento del tiempo objetivo, tasa de falsos positivos,
carga por analista, horas de indisponibilidad, costo estimado e indice
de reincidencia.
"""

from collections import Counter
from datetime import datetime, timedelta

from .enums import (
    COSTO_HORA_INDISPONIBILIDAD,
    Criticidad,
    EstadoEquipo,
    EstadoIncidente,
    OrigenAlerta,
)


class CalculadoraIndicadores:

    def __init__(self, repositorio):
        self._repo = repositorio

    # --- seleccion del periodo --------------------------------------------
    def incidentes_del_periodo(self, desde, hasta):
        return [i for i in self._repo.incidentes.values()
                if desde <= i.fecha_deteccion <= hasta]

    # --- RN-05: MTTD -------------------------------------------------------
    def mttd(self, incidentes):
        """Tiempo medio de deteccion, en horas."""
        if not incidentes:
            return 0.0
        total = sum(i.tiempo_deteccion_horas() for i in incidentes)
        return round(total / len(incidentes), 2)

    # --- RN-05: MTTR -------------------------------------------------------
    def mttr(self, incidentes):
        """
        Tiempo medio de resolucion, en horas. Solo considera incidentes
        cerrados y confirmados: los falsos positivos se excluyen del MTTR
        pero si cuentan para la tasa de falsos positivos.
        """
        cerrados = [i for i in incidentes
                    if i.fecha_cierre is not None and not i.es_falso_positivo()]
        if not cerrados:
            return 0.0
        total = sum(i.tiempo_resolucion_horas() for i in cerrados)
        return round(total / len(cerrados), 2)

    # --- RN-05: cumplimiento del tiempo objetivo ---------------------------
    def cumplimiento_objetivo(self, incidentes):
        """
        Porcentaje de incidentes resueltos dentro de su plazo (Tabla 12).

        Igual que en el MTTR, los falsos positivos se excluyen: no son
        incidentes, y un falso positivo descartado en minutos inflaria el
        porcentaje sin que el area haya atendido nada a tiempo.
        """
        evaluables = [i for i in incidentes
                      if not i.es_falso_positivo()
                      and i.cumple_tiempo_objetivo() is not None]
        if not evaluables:
            return 0.0
        cumplen = sum(1 for i in evaluables if i.cumple_tiempo_objetivo())
        return round(cumplen / len(evaluables) * 100, 1)

    # --- RN-05: tasa de falsos positivos -----------------------------------
    def tasa_falsos_positivos(self, incidentes):
        if not incidentes:
            return 0.0
        falsos = sum(1 for i in incidentes if i.es_falso_positivo())
        return round(falsos / len(incidentes) * 100, 1)

    def falsos_positivos_por_origen(self, incidentes):
        """Permite decidir sobre que herramienta ajustar las reglas."""
        detalle = {}
        for origen in OrigenAlerta:
            del_origen = [i for i in incidentes if i.origen == origen]
            falsos = sum(1 for i in del_origen if i.es_falso_positivo())
            porcentaje = round(falsos / len(del_origen) * 100, 1) if del_origen else 0.0
            detalle[origen] = {
                "total": len(del_origen),
                "falsos": falsos,
                "porcentaje": porcentaje,
            }
        return detalle

    # --- RN-05: carga por analista -----------------------------------------
    def carga_por_analista(self, incidentes):
        abiertos = [i for i in incidentes if i.esta_abierto() and i.analista_asignado]
        conteo = Counter(i.analista_asignado for i in abiertos)
        total = sum(conteo.values())
        return {
            analista: {
                "casos": casos,
                "porcentaje": round(casos / total * 100, 1) if total else 0.0,
            }
            for analista, casos in conteo.most_common()
        }

    # --- RN-05: indisponibilidad -------------------------------------------
    def horas_indisponibilidad(self, desde=None, hasta=None):
        """
        Sin periodo: total historico acumulado.
        Con periodo: solo las horas que caen dentro de [desde, hasta].
        """
        equipos = self._repo.equipos.values()
        if desde is None or hasta is None:
            return round(sum(e.horas_indisponible for e in equipos), 2)
        return round(sum(e.horas_indisponible_entre(desde, hasta) for e in equipos), 2)

    def costo_indisponibilidad(self, costo_hora=COSTO_HORA_INDISPONIBILIDAD,
                               desde=None, hasta=None):
        return round(self.horas_indisponibilidad(desde, hasta) * costo_hora, 2)

    # --- RN-05: reincidencia -----------------------------------------------
    def indice_reincidencia(self, incidentes, dias=30):
        """Equipos con dos o mas incidentes en la ventana indicada."""
        if not incidentes:
            return 0.0
        limite = max(i.fecha_deteccion for i in incidentes) - timedelta(days=dias)
        recientes = [i for i in incidentes if i.fecha_deteccion >= limite]
        conteo = Counter(i.equipo for i in recientes)
        if not conteo:
            return 0.0
        reincidentes = sum(1 for cantidad in conteo.values() if cantidad >= 2)
        return round(reincidentes / len(conteo) * 100, 1)

    # --- distribuciones para el reporte ------------------------------------
    def distribucion_por_criticidad(self, incidentes):
        conteo = {c: 0 for c in Criticidad}
        for i in incidentes:
            if i.criticidad is not None:
                conteo[i.criticidad] += 1
        return conteo

    def distribucion_por_estado(self, incidentes):
        conteo = {e: 0 for e in EstadoIncidente}
        for i in incidentes:
            conteo[i.estado] += 1
        return conteo

    def tipos_de_malware(self, incidentes):
        """Lo que la jefatura pide expresamente en el reporte mensual."""
        confirmados = [i for i in incidentes if not i.es_falso_positivo()]
        return Counter(i.tipo_amenaza for i in confirmados).most_common()

    # --- resumen integral (pantalla P-14) ----------------------------------
    def resumen(self, desde, hasta):
        incidentes = self.incidentes_del_periodo(desde, hasta)
        return {
            "desde": desde,
            "hasta": hasta,
            "total_alertas": len(incidentes),
            "confirmados": sum(1 for i in incidentes if not i.es_falso_positivo()),
            "falsos_positivos": sum(1 for i in incidentes if i.es_falso_positivo()),
            "mttd": self.mttd(incidentes),
            "mttr": self.mttr(incidentes),
            "cumplimiento": self.cumplimiento_objetivo(incidentes),
            "tasa_fp": self.tasa_falsos_positivos(incidentes),
            "fp_por_origen": self.falsos_positivos_por_origen(incidentes),
            "carga": self.carga_por_analista(incidentes),
            "horas_indisponibilidad": self.horas_indisponibilidad(desde, hasta),
            "costo_indisponibilidad": self.costo_indisponibilidad(desde=desde, hasta=hasta),
            "reincidencia": self.indice_reincidencia(incidentes),
            "por_criticidad": self.distribucion_por_criticidad(incidentes),
            "por_estado": self.distribucion_por_estado(incidentes),
            "malware": self.tipos_de_malware(incidentes),
            "con_datos_personales": [i for i in incidentes
                                     if i.involucra_datos_personales],
        }


class GeneradorReporteMensual:
    """
    Reemplaza el reporte que hoy se arma a mano (problema P-05 del informe).
    Responde exactamente a lo que la jefatura solicita: tipo de malware,
    estado de los equipos y estado del monitoreo.
    """

    def __init__(self, repositorio, calculadora, servicio_equipos):
        self._repo = repositorio
        self._calc = calculadora
        self._equipos = servicio_equipos

    def generar(self, anio, mes):
        desde = datetime(anio, mes, 1)
        hasta = (datetime(anio + 1, 1, 1) if mes == 12
                 else datetime(anio, mes + 1, 1)) - timedelta(seconds=1)
        datos = self._calc.resumen(desde, hasta)
        parque = self._equipos.resumen_parque()

        meses = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio",
                 "agosto", "setiembre", "octubre", "noviembre", "diciembre"]

        lineas = []
        ancho = 66
        lineas.append("=" * ancho)
        lineas.append(f"REPORTE MENSUAL DE INCIDENTES - {meses[mes - 1]} de {anio}".center(ancho))
        lineas.append("Area de Tecnologias de la Informacion".center(ancho))
        lineas.append("=" * ancho)

        if datos["total_alertas"] == 0:
            lineas.append("")
            lineas.append("  En el periodo seleccionado no se registraron incidentes.")
            lineas.append("=" * ancho)
            return "\n".join(lineas)

        lineas.append("")
        lineas.append("1. RESUMEN DEL PERIODO")
        lineas.append(f"   Alertas registradas .....: {datos['total_alertas']}")
        lineas.append(f"   Incidentes confirmados ..: {datos['confirmados']}")
        lineas.append(f"   Falsos positivos ........: {datos['falsos_positivos']}")

        lineas.append("")
        lineas.append("2. DISTRIBUCION POR CRITICIDAD")
        partes = [f"{c.value} {n}" for c, n in datos["por_criticidad"].items() if n]
        lineas.append("   " + (" | ".join(partes) if partes else "sin clasificar"))

        lineas.append("")
        lineas.append("3. TIPOS DE MALWARE DETECTADOS")
        if datos["malware"]:
            for tipo, cantidad in datos["malware"]:
                lineas.append(f"   {tipo:.<40} {cantidad}")
        else:
            lineas.append("   No se confirmaron amenazas en el periodo.")

        lineas.append("")
        lineas.append(f"4. ESTADO DE LOS EQUIPOS ({parque['total']} en el parque)")
        lineas.append("   (situacion al momento de generar el reporte)")
        lineas.append(f"   Operativos {parque[EstadoEquipo.OPERATIVO]} | "
                      f"Cuarentena {parque[EstadoEquipo.EN_CUARENTENA]} | "
                      f"Inhabilitados {parque[EstadoEquipo.INHABILITADO]} | "
                      f"Mantenimiento {parque[EstadoEquipo.EN_MANTENIMIENTO]}")

        lineas.append("")
        lineas.append("5. ESTADO DEL MONITOREO")
        for origen, det in datos["fp_por_origen"].items():
            lineas.append(f"   {origen.value:.<20} {det['total']} alertas, "
                          f"{det['falsos']} falsos positivos ({det['porcentaje']} %)")

        lineas.append("")
        lineas.append("6. INDICADORES DEL PERIODO")
        lineas.append(f"   MTTD ....................: {datos['mttd']} h")
        lineas.append(f"   MTTR ....................: {datos['mttr']} h")
        lineas.append(f"   Cumplimiento del plazo ..: {datos['cumplimiento']} %")
        lineas.append(f"   Tasa de falsos positivos : {datos['tasa_fp']} %")
        horas = datos['horas_indisponibilidad']
        lineas.append(f"   Horas de indisponibilidad: {horas} h (en el mes)")
        lineas.append(f"   Costo estimado ..........: S/ {datos['costo_indisponibilidad']}")
        lineas.append(f"   Indice de reincidencia ..: {datos['reincidencia']} %")

        lineas.append("")
        pendientes = [i for i in datos["con_datos_personales"] if not i.notificado_anpd]
        lineas.append("7. INCIDENTES CON DATOS PERSONALES")
        lineas.append(f"   Total: {len(datos['con_datos_personales'])} | "
                      f"Notificados a la ANPD: "
                      f"{len(datos['con_datos_personales']) - len(pendientes)} | "
                      f"Pendientes: {len(pendientes)}")
        for incidente in pendientes:
            lineas.append(f"   PENDIENTE {incidente.codigo} - plazo hasta "
                          f"{incidente.fecha_limite_notificacion().strftime('%d/%m/%Y %H:%M')}")

        lineas.append("")
        lineas.append("=" * ancho)
        lineas.append("Generado automaticamente por SIGIS - "
                      f"{datetime.now().strftime('%d/%m/%Y %H:%M')}")
        lineas.append("=" * ancho)
        return "\n".join(lineas)
