"""
Persistencia de SIGIS en archivos JSON.

Resuelve lo que la seccion D.2.6 del informe compromete: la informacion
se guarda en archivos estructurados y se mantiene una copia de respaldo
diaria, requisito que el Reglamento de la Ley 29733 exige al responsable
del tratamiento.

El guardado no se invoca a mano desde las pantallas: lo dispara el
observador GuardadoAutomatico cada vez que ocurre un evento del sistema
(ver patrones.py). Asi, si manana se agrega una operacion nueva, queda
persistida sin tocar esta capa.
"""

import json
import os
from datetime import date, datetime

from .enums import EstadoEquipo, EstadoIncidente, Criticidad, OrigenAlerta
from .modelo import AccionAuditoria, Analista, Equipo, JefeTI

CARPETA = "datos"
ARCHIVO = os.path.join(CARPETA, "sigis.json")


# --- utilidades -----------------------------------------------------------
def _f(momento):
    """datetime -> texto ISO (o None)."""
    return momento.isoformat() if momento else None


def _d(texto):
    """texto ISO -> datetime (o None)."""
    return datetime.fromisoformat(texto) if texto else None


# --- serializacion --------------------------------------------------------
def _usuario_a_dic(u):
    return {
        "nombre_usuario": u.nombre_usuario,
        "nombre_completo": u.nombre_completo,
        "hash": u.obtener_hash(),
        "es_jefe": isinstance(u, JefeTI),
        "bloqueado": u.bloqueado,
        "intentos_fallidos": u.intentos_fallidos,
    }


def _equipo_a_dic(e):
    return {
        "codigo": e.codigo,
        "area": e.area,
        "responsable": e.responsable,
        "estado": e.estado.value,
        "inhabilitado_desde": _f(e.inhabilitado_desde),
        "horas_indisponible": e.horas_indisponible,
        "periodos_indisponible": [[_f(a), _f(b)] for a, b in e.periodos_indisponible],
    }


def _incidente_a_dic(i):
    return {
        "codigo": i.codigo,
        "origen": i.origen.value,
        "equipo": i.equipo,
        "tipo_amenaza": i.tipo_amenaza,
        "descripcion": i.descripcion,
        "fecha_ocurrencia": _f(i.fecha_ocurrencia),
        "fecha_deteccion": _f(i.fecha_deteccion),
        "involucra_datos_personales": i.involucra_datos_personales,
        "estado": i.estado.value,
        "analista_asignado": i.analista_asignado,
        "impacto": i.impacto,
        "urgencia": i.urgencia,
        "criticidad": i.criticidad.value if i.criticidad else None,
        "fecha_contencion": _f(i.fecha_contencion),
        "fecha_cierre": _f(i.fecha_cierre),
        "causa_raiz": i.causa_raiz,
        "leccion_aprendida": i.leccion_aprendida,
        "motivo_falso_positivo": i.motivo_falso_positivo,
        "notificado_anpd": i.notificado_anpd,
        "acciones": [
            {"usuario": a.usuario, "descripcion": a.descripcion,
             "momento": _f(a.momento)}
            for a in i.acciones
        ],
    }


def _accion_a_dic(a):
    return {
        "usuario": a.usuario,
        "descripcion": a.descripcion,
        "codigo_incidente": a.codigo_incidente,
        "momento": _f(a.momento),
    }


# --- reconstruccion -------------------------------------------------------
def _dic_a_usuario(d):
    clase = JefeTI if d["es_jefe"] else Analista
    u = clase(d["nombre_usuario"], d["nombre_completo"], d["hash"])
    u.bloqueado = d.get("bloqueado", False)
    u.intentos_fallidos = d.get("intentos_fallidos", 0)
    return u


def _dic_a_equipo(d):
    e = Equipo(d["codigo"], d["area"], d["responsable"],
               EstadoEquipo(d["estado"]))
    e.inhabilitado_desde = _d(d.get("inhabilitado_desde"))
    e.horas_indisponible = d.get("horas_indisponible", 0.0)
    # Archivos guardados por versiones anteriores no traen el historial.
    e.periodos_indisponible = [(_d(a), _d(b))
                               for a, b in d.get("periodos_indisponible", [])]
    return e


def _dic_a_incidente(d):
    # Se importa aqui para evitar una dependencia circular con patrones.py
    from .patrones import FabricaIncidentes

    i = FabricaIncidentes.crear(
        OrigenAlerta(d["origen"]),
        codigo=d["codigo"],
        equipo=d["equipo"],
        tipo_amenaza=d["tipo_amenaza"],
        descripcion=d["descripcion"],
        fecha_ocurrencia=_d(d["fecha_ocurrencia"]),
        fecha_deteccion=_d(d["fecha_deteccion"]),
        involucra_datos_personales=d["involucra_datos_personales"],
    )
    i.estado = EstadoIncidente(d["estado"])
    i.analista_asignado = d.get("analista_asignado")
    i.impacto = d.get("impacto")
    i.urgencia = d.get("urgencia")
    i.criticidad = Criticidad(d["criticidad"]) if d.get("criticidad") else None
    i.fecha_contencion = _d(d.get("fecha_contencion"))
    i.fecha_cierre = _d(d.get("fecha_cierre"))
    i.causa_raiz = d.get("causa_raiz")
    i.leccion_aprendida = d.get("leccion_aprendida")
    i.motivo_falso_positivo = d.get("motivo_falso_positivo")
    i.notificado_anpd = d.get("notificado_anpd", False)
    i.acciones = [
        AccionAuditoria(a["usuario"], a["descripcion"], d["codigo"],
                        _d(a["momento"]))
        for a in d.get("acciones", [])
    ]
    return i


# --- interfaz publica -----------------------------------------------------
def guardar(repositorio, ruta=ARCHIVO):
    """
    Escribe todo el repositorio en un archivo JSON y deja una copia de
    respaldo por dia. Devuelve True si se guardo, False si no se pudo:
    un fallo de disco nunca debe interrumpir la operacion del sistema.
    """
    datos = {
        "version": 1,
        "guardado": _f(datetime.now()),
        "correlativo": repositorio.correlativo,
        "usuarios": [_usuario_a_dic(u) for u in repositorio.usuarios.values()],
        "equipos": [_equipo_a_dic(e) for e in repositorio.equipos.values()],
        "incidentes": [_incidente_a_dic(i) for i in repositorio.incidentes.values()],
        "bitacora": [_accion_a_dic(a) for a in repositorio.bitacora],
    }
    try:
        carpeta = os.path.dirname(ruta)
        if carpeta:
            os.makedirs(carpeta, exist_ok=True)
        with open(ruta, "w", encoding="utf-8") as archivo:
            json.dump(datos, archivo, ensure_ascii=False, indent=1)

        # copia de respaldo diaria (Reglamento de la Ley 29733)
        if carpeta:
            respaldo = os.path.join(carpeta, f"respaldo_{date.today().isoformat()}.json")
            if not os.path.exists(respaldo):
                with open(respaldo, "w", encoding="utf-8") as archivo:
                    json.dump(datos, archivo, ensure_ascii=False, indent=1)
        return True
    except OSError:
        return False


def cargar(repositorio, ruta=ARCHIVO):
    """
    Reconstruye el repositorio desde el archivo. Devuelve True si cargo
    datos, False si el archivo no existe o esta danado.
    """
    if not os.path.exists(ruta):
        return False
    try:
        with open(ruta, encoding="utf-8") as archivo:
            datos = json.load(archivo)
    except (OSError, json.JSONDecodeError):
        return False

    repositorio.limpiar()
    for d in datos.get("usuarios", []):
        u = _dic_a_usuario(d)
        repositorio.usuarios[u.nombre_usuario] = u
    for d in datos.get("equipos", []):
        e = _dic_a_equipo(d)
        repositorio.equipos[e.codigo] = e
    for d in datos.get("incidentes", []):
        i = _dic_a_incidente(d)
        repositorio.incidentes[i.codigo] = i
    repositorio.bitacora = [
        AccionAuditoria(a["usuario"], a["descripcion"],
                        a.get("codigo_incidente"), _d(a["momento"]))
        for a in datos.get("bitacora", [])
    ]
    repositorio.correlativo = datos.get("correlativo", 0)
    return True


def hay_datos(ruta=ARCHIVO):
    return os.path.exists(ruta)
