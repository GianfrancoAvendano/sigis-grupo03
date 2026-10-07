"""
Patrones de diseno aplicados en SIGIS.

  1. SINGLETON       -> Repositorio: una sola instancia de datos en memoria.
  2. FACTORY METHOD  -> FabricaIncidentes: crea la subclase que corresponde
                        al origen de la alerta sin que el resto del programa
                        conozca las subclases.
  3. STRATEGY        -> EstrategiaCriticidad: permite cambiar la forma de
                        calcular la criticidad sin tocar la clase Incidente.
  4. OBSERVER        -> Notificador: al ocurrir un evento avisa a todos los
                        observadores suscritos (bitacora y alerta legal).
"""

from abc import ABC, abstractmethod
from datetime import datetime

from .enums import (
    Criticidad,
    MATRIZ_CRITICIDAD,
    OrigenAlerta,
)
from .excepciones import DatoInvalidoError
from .modelo import (
    AccionAuditoria,
    IncidenteReporteUsuario,
    IncidenteSophos,
    IncidenteWazuh,
)


# ===========================================================================
#  1. SINGLETON
# ===========================================================================
class Repositorio:
    """
    Almacen unico en memoria de usuarios, equipos, incidentes y bitacora.

    Se implementa con __new__: por mas veces que se escriba Repositorio(),
    siempre se obtiene el mismo objeto.
    """

    _instancia = None

    def __new__(cls):
        if cls._instancia is None:
            cls._instancia = super().__new__(cls)
            cls._instancia._inicializar()
        return cls._instancia

    def _inicializar(self):
        self.usuarios = {}          # nombre_usuario -> Usuario
        self.equipos = {}           # codigo -> Equipo
        self.incidentes = {}        # codigo -> Incidente
        self.bitacora = []          # lista de AccionAuditoria
        self.correlativo = 0
        self.parametros = {}

    # --- generacion de codigos --------------------------------------------
    def siguiente_codigo_incidente(self):
        """Formato INC-AAAA-NNNN, correlativo y unico."""
        self.correlativo += 1
        return f"INC-{datetime.now().year}-{self.correlativo:04d}"

    # --- utilidades --------------------------------------------------------
    def limpiar(self):
        """Solo se usa en las pruebas automatizadas."""
        self._inicializar()

    @classmethod
    def reiniciar_instancia(cls):
        cls._instancia = None


# ===========================================================================
#  2. FACTORY METHOD
# ===========================================================================
class FabricaIncidentes:
    """
    Crea el objeto Incidente de la subclase correcta segun el origen.

    El resto del sistema pide "un incidente de origen X" y no necesita
    conocer IncidenteWazuh, IncidenteSophos ni IncidenteReporteUsuario.
    """

    _CATALOGO = {
        OrigenAlerta.WAZUH: IncidenteWazuh,
        OrigenAlerta.SOPHOS: IncidenteSophos,
        OrigenAlerta.USUARIO: IncidenteReporteUsuario,
    }

    @classmethod
    def crear(cls, origen, **datos):
        clase = cls._CATALOGO.get(origen)
        if clase is None:
            raise DatoInvalidoError(f"Origen de alerta no reconocido: {origen}")
        return clase(**datos)

    @classmethod
    def origenes_disponibles(cls):
        return list(cls._CATALOGO.keys())


# ===========================================================================
#  3. STRATEGY
# ===========================================================================
class EstrategiaCriticidad(ABC):
    """Interfaz comun de todas las formas de calcular la criticidad."""

    @abstractmethod
    def calcular(self, impacto, urgencia):
        """Devuelve un valor de Criticidad."""

    @abstractmethod
    def nombre(self):
        """Nombre legible de la estrategia, para mostrarlo en pantalla."""


class CriticidadPorMatriz(EstrategiaCriticidad):
    """Estrategia vigente (RN-01): criticidad = impacto x urgencia."""

    def calcular(self, impacto, urgencia):
        return MATRIZ_CRITICIDAD[impacto * urgencia]

    def nombre(self):
        return "Matriz impacto x urgencia (RN-01)"


class CriticidadPorImpactoDominante(EstrategiaCriticidad):
    """
    Estrategia alternativa, propuesta para una version posterior: el impacto
    manda y la urgencia solo puede subir un nivel. Existe para demostrar que
    la regla se puede cambiar sin tocar la clase Incidente.
    """

    _ESCALA = [Criticidad.BAJO, Criticidad.MEDIO, Criticidad.ALTO, Criticidad.CRITICO]

    def calcular(self, impacto, urgencia):
        posicion = impacto - 1
        if urgencia == 3:
            posicion = min(posicion + 1, len(self._ESCALA) - 1)
        return self._ESCALA[posicion]

    def nombre(self):
        return "Impacto dominante (propuesta de mejora)"


class ClasificadorIncidentes:
    """Contexto del patron Strategy: usa la estrategia que se le inyecte."""

    def __init__(self, estrategia=None):
        self._estrategia = estrategia or CriticidadPorMatriz()

    def cambiar_estrategia(self, estrategia):
        self._estrategia = estrategia

    @property
    def estrategia(self):
        return self._estrategia

    def clasificar(self, incidente, impacto, urgencia):
        if impacto not in (1, 2, 3) or urgencia not in (1, 2, 3):
            raise DatoInvalidoError("El impacto y la urgencia deben estar entre 1 y 3.")
        incidente.impacto = impacto
        incidente.urgencia = urgencia
        incidente.criticidad = self._estrategia.calcular(impacto, urgencia)
        return incidente.criticidad


# ===========================================================================
#  4. OBSERVER
# ===========================================================================
class Observador(ABC):
    """Interfaz de los objetos que reaccionan a los eventos del sistema."""

    @abstractmethod
    def actualizar(self, evento, datos):
        """Recibe el nombre del evento y un diccionario con su informacion."""


class BitacoraAuditoria(Observador):
    """
    RN-08: registra toda accion en el repositorio.
    La lista solo se agrega; ningun metodo del sistema la edita ni la borra.
    """

    def __init__(self, repositorio):
        self._repositorio = repositorio

    def actualizar(self, evento, datos):
        accion = AccionAuditoria(
            usuario=datos.get("usuario", "sistema"),
            descripcion=datos.get("descripcion", evento),
            codigo_incidente=datos.get("codigo"),
        )
        self._repositorio.bitacora.append(accion)


class AlertaPlazoLegal(Observador):
    """
    RN-06: lleva el control del plazo de 48 horas para notificar a la ANPD.

    Es el unico responsable de ese plazo en todo el sistema: anota los
    incidentes que lo abren y responde que tan cerca estan de vencer. Los
    servicios y las pantallas le preguntan a el, no recorren el repositorio
    por su cuenta.
    """

    def __init__(self, repositorio):
        self._repo = repositorio
        self.avisos = {}          # codigo -> fecha limite

    def actualizar(self, evento, datos):
        if evento != "incidente_registrado":
            return
        incidente = datos.get("incidente")
        if incidente is not None and incidente.involucra_datos_personales:
            self.avisos[incidente.codigo] = incidente.fecha_limite_notificacion()

    def reconstruir(self):
        """Rearma los avisos al cargar datos guardados de una sesion anterior."""
        self.avisos = {
            i.codigo: i.fecha_limite_notificacion()
            for i in self._repo.incidentes.values()
            if i.involucra_datos_personales
        }

    def pendientes(self, umbral_horas=12, ahora=None):
        """
        Incidentes con datos personales aun no notificados cuyo plazo vence
        dentro del umbral indicado. Devuelve [(incidente, horas_restantes)].
        """
        resultado = []
        for codigo in self.avisos:
            incidente = self._repo.incidentes.get(codigo)
            if incidente is None or incidente.notificado_anpd:
                continue
            restantes = incidente.horas_restantes_notificacion(ahora)
            if restantes is not None and restantes <= umbral_horas:
                resultado.append((incidente, restantes))
        return sorted(resultado, key=lambda par: par[1])


class GuardadoAutomatico(Observador):
    """
    Persistencia (seccion D.2.6 del informe): guarda el repositorio completo
    cada vez que ocurre un evento, de modo que la informacion sobreviva al
    cierre del programa.

    Se implementa como observador y no como llamada dentro de cada servicio
    para que toda operacion nueva quede persistida sin tocar la capa de
    negocio. Un fallo de disco nunca interrumpe la operacion.
    """

    def __init__(self, repositorio, ruta=None):
        self._repo = repositorio
        self._ruta = ruta
        self.activo = True
        self.ultimo_resultado = None

    def actualizar(self, evento, datos):
        if not self.activo:
            return
        from . import almacen
        ruta = self._ruta or almacen.ARCHIVO
        self.ultimo_resultado = almacen.guardar(self._repo, ruta)


class Notificador:
    """Sujeto observable: mantiene la lista de observadores y los avisa."""

    def __init__(self):
        self._observadores = []

    def suscribir(self, observador):
        if observador not in self._observadores:
            self._observadores.append(observador)

    def quitar(self, observador):
        if observador in self._observadores:
            self._observadores.remove(observador)

    def notificar(self, evento, datos):
        for observador in self._observadores:
            observador.actualizar(evento, datos)
