"""
Servicios de negocio de SIGIS.

Esta capa concentra las reglas RN-01 a RN-09. Las pantallas (menus.py)
solo piden datos y llaman a estos metodos; no contienen logica de negocio.
Esa separacion es la que permite probar el negocio sin abrir el programa
(ver pruebas_negocio.py) y la que hace posible cambiar la interfaz mas
adelante sin reescribir las reglas.
"""

import hashlib
from datetime import datetime

from .enums import (
    ACCIONES_CONTENCION,
    EstadoEquipo,
    EstadoIncidente,
    MOTIVOS_FALSO_POSITIVO,
    OrigenAlerta,
)
from .excepciones import (
    DatoInvalidoError,
    EquipoNoEncontradoError,
    IncidenteNoEncontradoError,
    OperacionNoPermitidaError,
    ReglaNegocioError,
    UsuarioNoEncontradoError,
)
from .modelo import Analista, Equipo, JefeTI
from .patrones import (
    AlertaPlazoLegal,
    BitacoraAuditoria,
    ClasificadorIncidentes,
    FabricaIncidentes,
    GuardadoAutomatico,
    Notificador,
    Repositorio,
)

MAX_INTENTOS = 3


def cifrar(clave):
    """
    Las contrasenas nunca se guardan en texto plano (seccion D.2.6 del
    informe, alineado a ISO/IEC 27002:2022).
    """
    return hashlib.sha256(clave.encode("utf-8")).hexdigest()


# ===========================================================================
#  AUTENTICACION  (pantalla P-01)
# ===========================================================================
class ServicioAutenticacion:

    def __init__(self, repositorio):
        self._repo = repositorio

    def registrar_usuario(self, nombre_usuario, nombre_completo, clave, es_jefe=False):
        if nombre_usuario in self._repo.usuarios:
            raise DatoInvalidoError(f"El usuario {nombre_usuario} ya existe.")
        clase = JefeTI if es_jefe else Analista
        usuario = clase(nombre_usuario, nombre_completo, cifrar(clave))
        self._repo.usuarios[nombre_usuario] = usuario
        return usuario

    def autenticar(self, nombre_usuario, clave):
        usuario = self._repo.usuarios.get(nombre_usuario)
        if usuario is None:
            raise UsuarioNoEncontradoError("Credenciales incorrectas.")
        if usuario.bloqueado:
            raise OperacionNoPermitidaError(
                "El usuario esta bloqueado por exceso de intentos fallidos.")
        if not usuario.verificar_clave(cifrar(clave)):
            usuario.intentos_fallidos += 1
            if usuario.intentos_fallidos >= MAX_INTENTOS:
                usuario.bloqueado = True
                raise OperacionNoPermitidaError(
                    "Usuario bloqueado tras 3 intentos fallidos.")
            restantes = MAX_INTENTOS - usuario.intentos_fallidos
            raise UsuarioNoEncontradoError(
                f"Credenciales incorrectas. Le quedan {restantes} intentos.")
        usuario.intentos_fallidos = 0
        return usuario


# ===========================================================================
#  EQUIPOS  (pantalla P-13)
# ===========================================================================
class ServicioEquipos:

    def __init__(self, repositorio):
        self._repo = repositorio

    def registrar(self, codigo, area, responsable):
        codigo = codigo.strip().upper()
        if not codigo:
            raise DatoInvalidoError("El codigo del equipo no puede estar vacio.")
        if codigo in self._repo.equipos:
            raise DatoInvalidoError(f"El equipo {codigo} ya esta registrado.")
        if not (codigo.startswith("EQ-") or codigo.startswith("SRV-")):
            raise DatoInvalidoError(
                "El codigo debe tener el formato EQ-NNNN o SRV-NNN.")
        equipo = Equipo(codigo, area, responsable)
        self._repo.equipos[codigo] = equipo
        return equipo

    def obtener(self, codigo):
        equipo = self._repo.equipos.get(codigo.strip().upper())
        if equipo is None:
            raise EquipoNoEncontradoError(
                f"El equipo {codigo} no existe en el inventario.")
        return equipo

    def listar(self, estado=None):
        equipos = list(self._repo.equipos.values())
        if estado is not None:
            equipos = [e for e in equipos if e.estado == estado]
        return sorted(equipos, key=lambda e: e.codigo)

    def buscar(self, texto):
        texto = texto.strip().lower()
        return [e for e in self._repo.equipos.values()
                if texto in e.codigo.lower()
                or texto in e.area.lower()
                or texto in e.responsable.lower()]

    def dar_de_baja(self, codigo):
        equipo = self.obtener(codigo)
        if equipo.esta_fuera_de_servicio():
            raise ReglaNegocioError(
                "No se puede dar de baja un equipo que esta fuera de servicio.")
        equipo.estado = EstadoEquipo.DADO_DE_BAJA
        return equipo

    def resumen_parque(self):
        resumen = {estado: 0 for estado in EstadoEquipo}
        for equipo in self._repo.equipos.values():
            resumen[equipo.estado] += 1
        resumen["total"] = len(self._repo.equipos)
        return resumen


# ===========================================================================
#  INCIDENTES  (pantallas P-03 a P-12)
# ===========================================================================
class ServicioIncidentes:

    def __init__(self, repositorio, servicio_equipos, clasificador=None,
                 notificador=None, alerta_plazo=None):
        self._repo = repositorio
        self._equipos = servicio_equipos
        self._clasificador = clasificador or ClasificadorIncidentes()
        self._notificador = notificador or Notificador()
        self._alerta = alerta_plazo or AlertaPlazoLegal(repositorio)

    @property
    def notificador(self):
        return self._notificador

    @property
    def clasificador(self):
        return self._clasificador

    @property
    def alerta_plazo(self):
        return self._alerta

    # --- registro (P-04) ---------------------------------------------------
    def registrar(self, origen, codigo_equipo, tipo_amenaza, descripcion,
                  fecha_ocurrencia, fecha_deteccion, datos_personales,
                  usuario="sistema"):
        """
        Crea el incidente con la fabrica (Factory Method) y avisa a los
        observadores (bitacora y alerta de plazo legal).
        """
        equipo = self._equipos.obtener(codigo_equipo)

        # RN-09: un equipo fuera de servicio no admite un nuevo caso activo.
        if equipo.esta_fuera_de_servicio():
            raise ReglaNegocioError(
                f"El equipo {equipo.codigo} esta {equipo.estado.value.lower()}. "
                "Registre primero su devolucion.")

        if not tipo_amenaza.strip():
            raise DatoInvalidoError("El tipo de amenaza es obligatorio.")
        if fecha_deteccion > datetime.now():
            raise DatoInvalidoError("La deteccion no puede ser una fecha futura.")

        incidente = FabricaIncidentes.crear(
            origen,
            codigo=self._repo.siguiente_codigo_incidente(),
            equipo=equipo.codigo,
            tipo_amenaza=tipo_amenaza.strip(),
            descripcion=descripcion.strip(),
            fecha_ocurrencia=fecha_ocurrencia,
            fecha_deteccion=fecha_deteccion,
            involucra_datos_personales=datos_personales,
        )
        self._repo.incidentes[incidente.codigo] = incidente
        incidente.registrar_accion(usuario, "Registro del incidente")
        self._notificador.notificar("incidente_registrado", {
            "usuario": usuario,
            "codigo": incidente.codigo,
            "descripcion": f"Registro de {incidente.codigo}",
            "incidente": incidente,
        })
        return incidente

    # --- clasificacion (P-05) ---------------------------------------------
    def clasificar(self, codigo, impacto, urgencia, usuario="sistema"):
        incidente = self.obtener(codigo)
        criticidad = self._clasificador.clasificar(incidente, impacto, urgencia)
        incidente.registrar_accion(
            usuario, f"Clasificacion: {impacto} x {urgencia} = {criticidad.value}")
        self._notificador.notificar("incidente_clasificado", {
            "usuario": usuario,
            "codigo": codigo,
            "descripcion": f"Clasificacion de {codigo} como {criticidad.value}",
        })
        return criticidad

    # --- consulta ----------------------------------------------------------
    def obtener(self, codigo):
        incidente = self._repo.incidentes.get(codigo.strip().upper())
        if incidente is None:
            raise IncidenteNoEncontradoError(f"El incidente {codigo} no existe.")
        return incidente

    def listar(self, estado=None, criticidad=None, analista=None,
               solo_abiertos=False, desde=None, hasta=None):
        """HU-13: filtra por estado, criticidad, analista y rango de deteccion."""
        incidentes = list(self._repo.incidentes.values())
        if desde is not None:
            incidentes = [i for i in incidentes if i.fecha_deteccion >= desde]
        if hasta is not None:
            incidentes = [i for i in incidentes if i.fecha_deteccion <= hasta]
        if estado is not None:
            incidentes = [i for i in incidentes if i.estado == estado]
        if criticidad is not None:
            incidentes = [i for i in incidentes if i.criticidad == criticidad]
        if analista is not None:
            incidentes = [i for i in incidentes if i.analista_asignado == analista]
        if solo_abiertos:
            incidentes = [i for i in incidentes if i.esta_abierto()]
        return sorted(incidentes, key=lambda i: i.codigo, reverse=True)

    # --- asignacion (P-08) -------------------------------------------------
    def asignar(self, codigo, nombre_analista, usuario="sistema"):
        if nombre_analista not in self._repo.usuarios:
            raise UsuarioNoEncontradoError(
                f"El analista {nombre_analista} no existe.")
        incidente = self.obtener(codigo)
        if incidente.estado == EstadoIncidente.CERRADO:
            raise ReglaNegocioError("No se puede reasignar un incidente cerrado.")
        anterior = incidente.analista_asignado or "sin asignar"
        incidente.analista_asignado = nombre_analista
        if incidente.estado == EstadoIncidente.REGISTRADO:
            incidente.estado = EstadoIncidente.EN_ATENCION
        incidente.registrar_accion(
            usuario, f"Asignado de {anterior} a {nombre_analista}")
        self._notificador.notificar("incidente_asignado", {
            "usuario": usuario,
            "codigo": codigo,
            "descripcion": f"Asignacion de {codigo} a {nombre_analista}",
        })
        return incidente

    def carga_por_analista(self):
        """RN-05: cuantos incidentes abiertos tiene cada analista."""
        carga = {nombre: 0 for nombre in self._repo.usuarios}
        for incidente in self._repo.incidentes.values():
            if incidente.esta_abierto() and incidente.analista_asignado:
                carga[incidente.analista_asignado] = \
                    carga.get(incidente.analista_asignado, 0) + 1
        return carga

    # --- falso positivo (P-09) --------------------------------------------
    def marcar_falso_positivo(self, codigo, motivo, observacion="",
                              usuario="sistema"):
        incidente = self.obtener(codigo)
        if incidente.estado == EstadoIncidente.CERRADO:
            raise ReglaNegocioError("El incidente ya esta cerrado.")
        if motivo not in MOTIVOS_FALSO_POSITIVO:
            raise DatoInvalidoError("Debe indicar un motivo valido (1 a 4).")
        incidente.motivo_falso_positivo = MOTIVOS_FALSO_POSITIVO[motivo]
        incidente.estado = EstadoIncidente.FALSO_POSITIVO
        detalle = incidente.motivo_falso_positivo
        if observacion:
            detalle += f" - {observacion}"
        incidente.registrar_accion(usuario, f"Falso positivo: {detalle}")
        self._notificador.notificar("falso_positivo", {
            "usuario": usuario,
            "codigo": codigo,
            "descripcion": f"{codigo} marcado como falso positivo",
        })
        return incidente

    # --- escalamiento ------------------------------------------------------
    def escalar(self, codigo, motivo, usuario="sistema"):
        incidente = self.obtener(codigo)
        if incidente.estado in (EstadoIncidente.CERRADO,
                                EstadoIncidente.FALSO_POSITIVO):
            raise ReglaNegocioError("No se puede escalar un incidente cerrado.")
        incidente.estado = EstadoIncidente.ESCALADO
        incidente.registrar_accion(usuario, f"Escalado a jefatura: {motivo}")
        # RN-08: el escalamiento tambien debe llegar a la bitacora general.
        self._notificador.notificar("incidente_escalado", {
            "usuario": usuario,
            "codigo": codigo,
            "descripcion": f"Escalamiento de {codigo} a la jefatura: {motivo}",
        })
        return incidente

    # --- contencion (P-10) -------------------------------------------------
    def registrar_contencion(self, codigo, opcion_accion, usuario="sistema",
                             momento=None):
        if opcion_accion not in ACCIONES_CONTENCION:
            raise DatoInvalidoError("Debe elegir una accion de contencion valida.")
        incidente = self.obtener(codigo)
        equipo = self._equipos.obtener(incidente.equipo)
        momento = momento or datetime.now()
        nombre_accion, nuevo_estado = ACCIONES_CONTENCION[opcion_accion]
        equipo.inhabilitar(momento, nuevo_estado)
        incidente.estado = EstadoIncidente.CONTENIDO
        incidente.fecha_contencion = momento
        incidente.registrar_accion(
            usuario, f"{nombre_accion} sobre el equipo {equipo.codigo}")
        self._notificador.notificar("contencion", {
            "usuario": usuario,
            "codigo": codigo,
            "descripcion": f"{nombre_accion} - equipo {equipo.codigo}",
        })
        return equipo

    # --- devolucion del equipo (P-11) --------------------------------------
    def registrar_devolucion(self, codigo_equipo, accion_realizada,
                             usuario="sistema", momento=None):
        equipo = self._equipos.obtener(codigo_equipo)
        momento = momento or datetime.now()
        horas = equipo.devolver(momento)
        self._notificador.notificar("devolucion", {
            "usuario": usuario,
            "codigo": None,
            "descripcion": (f"Devolucion del equipo {equipo.codigo} "
                            f"({horas} h fuera de servicio): {accion_realizada}"),
        })
        return horas

    # --- cierre (P-12) -----------------------------------------------------
    def cerrar(self, codigo, clasificacion_final, causa_raiz, leccion_aprendida,
               notificado_anpd=False, usuario="sistema", momento=None):
        """
        RN-07: no se puede cerrar sin causa raiz ni clasificacion final.
        """
        incidente = self.obtener(codigo)
        if incidente.estado == EstadoIncidente.CERRADO:
            raise ReglaNegocioError(f"El incidente {codigo} ya estaba cerrado.")
        if clasificacion_final not in ("confirmado", "falso_positivo"):
            raise DatoInvalidoError(
                "La clasificacion final debe ser 'confirmado' o 'falso_positivo'.")
        if not causa_raiz or not causa_raiz.strip():
            raise ReglaNegocioError(
                "No se puede cerrar el incidente sin registrar la causa raiz (RN-07).")
        if not leccion_aprendida or not leccion_aprendida.strip():
            raise ReglaNegocioError(
                "No se puede cerrar el incidente sin registrar la leccion aprendida.")

        equipo = self._equipos.obtener(incidente.equipo)
        if equipo.esta_fuera_de_servicio():
            raise ReglaNegocioError(
                f"Registre primero la devolución del equipo {equipo.codigo}.")

        incidente.causa_raiz = causa_raiz.strip()
        incidente.leccion_aprendida = leccion_aprendida.strip()
        incidente.notificado_anpd = notificado_anpd
        incidente.fecha_cierre = momento or datetime.now()
        incidente.estado = EstadoIncidente.CERRADO
        if clasificacion_final == "falso_positivo" and not incidente.es_falso_positivo():
            incidente.motivo_falso_positivo = MOTIVOS_FALSO_POSITIVO[4]
        incidente.registrar_accion(usuario, f"Cierre del incidente ({clasificacion_final})")
        self._notificador.notificar("incidente_cerrado", {
            "usuario": usuario,
            "codigo": codigo,
            "descripcion": f"Cierre de {codigo}",
        })
        return incidente

    # --- alertas del plazo legal (RN-06) -----------------------------------
    def incidentes_con_plazo_por_vencer(self, umbral_horas=12, ahora=None):
        """Delega en el observador AlertaPlazoLegal, que es el responsable
        unico del plazo legal (RN-06)."""
        return self._alerta.pendientes(umbral_horas, ahora)


def construir_sistema(persistencia=True, ruta=None):
    """
    Arma el sistema completo y conecta los tres observadores:
      - BitacoraAuditoria   (RN-08)
      - AlertaPlazoLegal    (RN-06)
      - GuardadoAutomatico  (persistencia, seccion D.2.6)

    Punto unico de inicializacion usado por main.py y por las pruebas.
    Las pruebas lo llaman con persistencia=False para no escribir en disco.
    """
    repo = Repositorio()
    equipos = ServicioEquipos(repo)
    notificador = Notificador()
    notificador.suscribir(BitacoraAuditoria(repo))
    alerta = AlertaPlazoLegal(repo)
    notificador.suscribir(alerta)
    if persistencia:
        notificador.suscribir(GuardadoAutomatico(repo, ruta))
    incidentes = ServicioIncidentes(repo, equipos, notificador=notificador,
                                    alerta_plazo=alerta)
    autenticacion = ServicioAutenticacion(repo)
    return repo, autenticacion, equipos, incidentes
