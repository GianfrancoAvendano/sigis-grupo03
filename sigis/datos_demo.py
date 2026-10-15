"""Carga un conjunto de datos ficticios para explorar SIGIS."""

from datetime import datetime, timedelta

from .enums import OrigenAlerta
from .enums import EstadoIncidente


def cargar(auth, equipos, incidentes):
    """Crea cuentas, equipos e incidentes de muestra en los últimos tres meses."""
    jefe = auth.registrar_usuario("jefe_ti", "Jefe de TI", "jefe123", es_jefe=True)
    auth.registrar_usuario("analista1", "Analista Uno", "clave123")
    auth.registrar_usuario("analista2", "Analista Dos", "clave456")
    auth.registrar_usuario("analista3", "Analista Tres", "clave789")
    auth.registrar_usuario("auditor", "Auditor de Seguridad", "auditor123")

    equipos_iniciales = [
        ("SRV-01", "Centro de datos", "Infraestructura"),
        ("SRV-02", "Centro de datos", "Infraestructura"),
        ("PC-101", "Finanzas", "Finanzas"),
        ("PC-102", "Recursos Humanos", "Recursos Humanos"),
        ("NET-01", "Redes", "Infraestructura"),
        ("DB-01", "Bases de datos", "Aplicaciones"),
    ]
    for codigo, area, responsable in equipos_iniciales:
        equipos.registrar(codigo, area, responsable, jefe)

    ahora = datetime.now().replace(second=0, microsecond=0)
    equipos_codigos = [item[0] for item in equipos_iniciales]
    origenes = list(OrigenAlerta)
    amenazas = [
        "Ransomware", "Phishing", "Malware", "Acceso no autorizado",
        "Escaneo de puertos", "Exfiltración", "Troyano", "Fuerza bruta",
        "Malware", "Phishing", "Ransomware", "Acceso no autorizado",
    ]
    for indice in range(12):
        detectada = ahora - timedelta(days=(indice % 3) * 31 + indice + 2)
        ocurrida = detectada - timedelta(hours=indice % 10 + 1)
        incidente = incidentes.registrar(
            origenes[indice % len(origenes)],
            equipos_codigos[indice % len(equipos_codigos)],
            amenazas[indice],
            f"Evento de demostración número {indice + 1}. Datos ficticios.",
            ocurrida,
            detectada,
            involucra_datos_personales=(indice in (2, 8)),
            usuario=jefe,
        )
        incidentes.clasificar(incidente.codigo, (indice % 3) + 1, ((indice + 1) % 3) + 1, jefe)
        if indice % 4 == 0:
            incidente.analista_asignado = "analista1"
        elif indice % 4 == 1:
            incidente.analista_asignado = "analista2"
        if indice % 5 == 0:
            incidentes.marcar_falso_positivo(
                incidente.codigo, "Alerta de demostración no confirmada", jefe
            )
        elif indice % 3 == 0:
            incidente.fecha_cierre = ahora - timedelta(days=indice % 4, hours=1)
            incidente.causa_raiz = "Análisis de causa completado para la demostración"
            incidente.estado = EstadoIncidente.CERRADO

    return {
        "usuarios": len(auth.repo.usuarios),
        "equipos": len(equipos.repo.equipos),
        "incidentes": len(incidentes.repo.incidentes),
    }
