"""Enumeraciones y parámetros de las reglas de negocio de SIGIS."""

from enum import Enum


class ValorEnum(str, Enum):
    """Enum cuyos valores se imprimen naturalmente en la interfaz."""

    def __str__(self):
        return self.value


class Criticidad(ValorEnum):
    BAJO = "BAJO"
    MEDIO = "MEDIO"
    ALTO = "ALTO"
    CRITICO = "CRITICO"


class EstadoEquipo(ValorEnum):
    OPERATIVO = "Operativo"
    EN_CUARENTENA = "En cuarentena"
    INHABILITADO = "Inhabilitado"
    EN_MANTENIMIENTO = "En mantenimiento"


class EstadoIncidente(ValorEnum):
    REGISTRADO = "Registrado"
    EN_ATENCION = "En atención"
    CONTENIDO = "Contenido"
    ESCALADO = "Escalado"
    FALSO_POSITIVO = "Falso positivo"
    CERRADO = "Cerrado"


class OrigenAlerta(ValorEnum):
    WAZUH = "Wazuh"
    SOPHOS = "Sophos"
    USUARIO = "Usuario"


# La clave de la matriz es impacto * urgencia (ambas escalas van de 1 a 3).
MATRIZ_CRITICIDAD = {
    1: Criticidad.BAJO,
    2: Criticidad.BAJO,
    3: Criticidad.MEDIO,
    4: Criticidad.MEDIO,
    6: Criticidad.ALTO,
    9: Criticidad.CRITICO,
}

ESCALA_IMPACTO = {
    1: "Bajo",
    2: "Medio",
    3: "Alto",
}

ESCALA_URGENCIA = {
    1: "Baja",
    2: "Media",
    3: "Alta",
}

TIEMPOS_OBJETIVO = {
    Criticidad.BAJO: 72,
    Criticidad.MEDIO: 48,
    Criticidad.ALTO: 24,
    Criticidad.CRITICO: 8,
}

COSTO_HORA_INDISPONIBILIDAD = 250.0
PLAZO_NOTIFICACION_HORAS = 48
INTENTOS_MAXIMOS = 3
