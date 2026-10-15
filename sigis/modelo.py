"""Entidades del dominio de SIGIS."""

import hashlib
import hmac
from datetime import datetime

from .enums import (
    EstadoEquipo,
    EstadoIncidente,
    OrigenAlerta,
    PLAZO_NOTIFICACION_HORAS,
    TIEMPOS_OBJETIVO,
)
from .excepciones import DatoInvalidoError, EstadoInvalidoError


class Usuario:
    """Usuario del sistema con clave almacenada como resumen SHA-256."""

    _OPCIONES_COMUNES = ("panel", "incidentes", "equipos", "indicadores", "reportes")

    def __init__(self, nombre_usuario, nombre_completo, clave, hash_guardado=False):
        self.nombre_usuario = str(nombre_usuario).strip()
        self.nombre_completo = str(nombre_completo).strip()
        if not self.nombre_usuario or not self.nombre_completo or not clave:
            raise DatoInvalidoError("El usuario, nombre y contraseña son obligatorios.")
        self.__hash_clave = clave if hash_guardado else self._hash(clave)
        self.bloqueado = False
        self.intentos_fallidos = 0

    @staticmethod
    def _hash(clave):
        return hashlib.sha256(str(clave).encode("utf-8")).hexdigest()

    def verificar_clave(self, clave):
        return hmac.compare_digest(self.__hash_clave, self._hash(clave))

    def obtener_hash(self):
        return self.__hash_clave

    def opciones_menu(self):
        return list(self._OPCIONES_COMUNES)

    def puede(self, accion):
        return accion in self.opciones_menu()


class Analista(Usuario):
    def opciones_menu(self):
        return super().opciones_menu() + ["registrar", "atender", "contener", "cerrar"]


class JefeTI(Usuario):
    def opciones_menu(self):
        return super().opciones_menu() + [
            "registrar", "atender", "contener", "cerrar", "asignar", "bitacora",
            "configuracion", "escalar", "falso_positivo", "equipos_admin",
        ]

    def puede(self, accion):
        return accion in self.opciones_menu()


class Equipo:
    """Activo tecnológico e historial de sus periodos de indisponibilidad."""

    def __init__(self, codigo, area, responsable, estado=EstadoEquipo.OPERATIVO):
        self.codigo = str(codigo).strip()
        self.area = str(area).strip()
        self.responsable = str(responsable).strip()
        if not self.codigo or not self.area or not self.responsable:
            raise DatoInvalidoError("Código, área y responsable del equipo son obligatorios.")
        self.estado = EstadoEquipo(estado)
        self.inhabilitado_desde = None
        self.horas_indisponible = 0.0
        self.periodos_indisponible = []

    def inhabilitar(self, momento=None):
        if self.estado == EstadoEquipo.INHABILITADO:
            raise EstadoInvalidoError(f"El equipo {self.codigo} ya está inhabilitado.")
        self.estado = EstadoEquipo.INHABILITADO
        self.inhabilitado_desde = momento or datetime.now()

    def devolver(self, momento=None):
        if self.estado != EstadoEquipo.INHABILITADO or self.inhabilitado_desde is None:
            raise EstadoInvalidoError(f"El equipo {self.codigo} no está inhabilitado.")
        fin = momento or datetime.now()
        if fin < self.inhabilitado_desde:
            raise DatoInvalidoError("La fecha de devolución no puede ser anterior al inicio.")
        horas = (fin - self.inhabilitado_desde).total_seconds() / 3600
        self.horas_indisponible += horas
        self.periodos_indisponible.append((self.inhabilitado_desde, fin))
        self.inhabilitado_desde = None
        self.estado = EstadoEquipo.OPERATIVO
        return round(horas, 2)

    def horas_indisponible_entre(self, desde, hasta):
        periodos = list(self.periodos_indisponible)
        if self.inhabilitado_desde is not None:
            periodos.append((self.inhabilitado_desde, datetime.now()))
        total = 0.0
        for inicio, fin in periodos:
            inicio_solapado = max(inicio, desde)
            fin_solapado = min(fin, hasta)
            if fin_solapado > inicio_solapado:
                total += (fin_solapado - inicio_solapado).total_seconds() / 3600
        return total


class AccionAuditoria:
    """Registro de auditoría de solo lectura."""

    __slots__ = ("_usuario", "_descripcion", "_codigo_incidente", "_momento")

    def __init__(self, usuario, descripcion, codigo_incidente=None, momento=None):
        object.__setattr__(self, "_usuario", usuario)
        object.__setattr__(self, "_descripcion", descripcion)
        object.__setattr__(self, "_codigo_incidente", codigo_incidente)
        object.__setattr__(self, "_momento", momento or datetime.now())

    def __setattr__(self, name, value):
        raise AttributeError("Las acciones de auditoría son inmutables.")

    @property
    def usuario(self):
        return self._usuario

    @property
    def descripcion(self):
        return self._descripcion

    @property
    def codigo_incidente(self):
        return self._codigo_incidente

    @property
    def momento(self):
        return self._momento


class Incidente:
    """Caso de seguridad registrado y atendido en el sistema."""

    ORIGEN = None
    CONFIABILIDAD = 1.0

    def __init__(
        self,
        codigo,
        equipo,
        tipo_amenaza,
        descripcion,
        fecha_ocurrencia,
        fecha_deteccion,
        involucra_datos_personales=False,
    ):
        if not codigo or not equipo or not tipo_amenaza or not descripcion:
            raise DatoInvalidoError("Complete código, equipo, amenaza y descripción.")
        self.codigo = str(codigo)
        self.equipo = str(equipo)
        self.tipo_amenaza = str(tipo_amenaza).strip()
        self.descripcion = str(descripcion).strip()
        self.fecha_ocurrencia = fecha_ocurrencia
        self.fecha_deteccion = fecha_deteccion
        if not isinstance(fecha_ocurrencia, datetime) or not isinstance(fecha_deteccion, datetime):
            raise DatoInvalidoError("Las fechas de ocurrencia y detección deben ser válidas.")
        if fecha_deteccion < fecha_ocurrencia:
            raise DatoInvalidoError(
                "La fecha/hora de detección no puede ser anterior a la de ocurrencia."
            )
        self.involucra_datos_personales = bool(involucra_datos_personales)
        self.estado = EstadoIncidente.REGISTRADO
        self.analista_asignado = None
        self.impacto = None
        self.urgencia = None
        self.criticidad = None
        self.fecha_contencion = None
        self.fecha_cierre = None
        self.causa_raiz = None
        self.leccion_aprendida = None
        self.motivo_falso_positivo = None
        self.notificado_anpd = False
        self.acciones = []
        self.origen = self.ORIGEN

    @classmethod
    def descripcion_origen(cls):
        return cls.ORIGEN.value if cls.ORIGEN else "Desconocido"

    @classmethod
    def peso_confiabilidad(cls):
        return cls.CONFIABILIDAD

    def tiempo_deteccion_horas(self):
        return round((self.fecha_deteccion - self.fecha_ocurrencia).total_seconds() / 3600, 2)

    def tiempo_resolucion_horas(self):
        if self.fecha_cierre is None:
            return None
        return round((self.fecha_cierre - self.fecha_deteccion).total_seconds() / 3600, 2)

    def es_falso_positivo(self):
        return self.estado == EstadoIncidente.FALSO_POSITIVO

    def esta_abierto(self):
        return self.estado not in (EstadoIncidente.CERRADO, EstadoIncidente.FALSO_POSITIVO)

    def cumple_tiempo_objetivo(self):
        if self.fecha_cierre is None or self.criticidad is None:
            return None
        objetivo = TIEMPOS_OBJETIVO[self.criticidad]
        return self.tiempo_resolucion_horas() <= objetivo

    def fecha_limite_notificacion(self):
        if not self.involucra_datos_personales:
            return None
        from datetime import timedelta
        return self.fecha_deteccion + timedelta(hours=PLAZO_NOTIFICACION_HORAS)

    def horas_restantes_notificacion(self, ahora=None):
        limite = self.fecha_limite_notificacion()
        if limite is None:
            return None
        return round((limite - (ahora or datetime.now())).total_seconds() / 3600, 2)


class IncidenteWazuh(Incidente):
    ORIGEN = OrigenAlerta.WAZUH
    CONFIABILIDAD = 0.9


class IncidenteSophos(Incidente):
    ORIGEN = OrigenAlerta.SOPHOS
    CONFIABILIDAD = 0.85


class IncidenteReporteUsuario(Incidente):
    ORIGEN = OrigenAlerta.USUARIO
    CONFIABILIDAD = 0.7
