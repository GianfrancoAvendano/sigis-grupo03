"""Servicios de aplicación y reglas de negocio de SIGIS."""

from datetime import datetime

from .enums import EstadoEquipo, EstadoIncidente, OrigenAlerta
from .excepciones import (
    AutenticacionError,
    DatoInvalidoError,
    EstadoInvalidoError,
    NoEncontradoError,
    PermisoDenegadoError,
)
from .indicadores import CalculadoraIndicadores, GeneradorReporteMensual
from .modelo import Analista, Equipo, JefeTI
from .patrones import (
    AlertaPlazoLegal,
    BitacoraAuditoria,
    ClasificadorIncidentes,
    FabricaIncidentes,
    Notificador,
    Repositorio,
)


class ServicioBase:
    def __init__(self, repositorio, notificador=None):
        self.repo = repositorio
        self.notificador = notificador or Notificador()

    def _evento(self, evento, usuario="sistema", descripcion=None, **datos):
        detalle = {
            "usuario": getattr(usuario, "nombre_usuario", usuario),
            "descripcion": descripcion or evento.replace("_", " "),
        }
        detalle.update(datos)
        self.notificador.notificar(evento, detalle)

    @staticmethod
    def _exigir_permiso(usuario, accion):
        if usuario is None or not usuario.puede(accion):
            raise PermisoDenegadoError(f"No tiene permiso para realizar: {accion}.")


class ServicioAutenticacion(ServicioBase):
    def registrar_usuario(self, nombre_usuario, nombre_completo, clave, es_jefe=False):
        usuario_key = str(nombre_usuario).strip()
        if usuario_key in self.repo.usuarios:
            raise DatoInvalidoError(f"El usuario {usuario_key} ya existe.")
        clase = JefeTI if es_jefe else Analista
        usuario = clase(usuario_key, nombre_completo, clave)
        self.repo.usuarios[usuario.nombre_usuario] = usuario
        self._evento("usuario_registrado", usuario, f"Alta de usuario {usuario.nombre_usuario}")
        return usuario

    def iniciar_sesion(self, nombre_usuario, clave):
        usuario = self.repo.usuarios.get(str(nombre_usuario).strip())
        if usuario is None:
            raise AutenticacionError("Usuario o contraseña incorrectos.")
        if usuario.bloqueado:
            raise AutenticacionError("La cuenta está bloqueada.")
        if not usuario.verificar_clave(clave):
            usuario.intentos_fallidos += 1
            if usuario.intentos_fallidos >= 3:
                usuario.bloqueado = True
                self._evento(
                    "usuario_bloqueado", usuario,
                    f"Cuenta {usuario.nombre_usuario} bloqueada tras tres intentos fallidos",
                )
            raise AutenticacionError("Usuario o contraseña incorrectos.")
        usuario.intentos_fallidos = 0
        self._evento("inicio_sesion", usuario, f"Inició sesión {usuario.nombre_usuario}")
        return usuario

    def autenticar(self, nombre_usuario, clave):
        return self.iniciar_sesion(nombre_usuario, clave)


class ServicioEquipos(ServicioBase):
    def registrar(self, codigo, area, responsable, usuario=None):
        self._exigir_permiso(usuario, "equipos_admin")
        key = str(codigo).strip()
        if key in self.repo.equipos:
            raise DatoInvalidoError(f"El equipo {key} ya existe.")
        equipo = Equipo(key, area, responsable)
        self.repo.equipos[key] = equipo
        self._evento("equipo_registrado", usuario, f"Registró equipo {key}")
        return equipo

    def agregar(self, codigo, area, responsable, usuario=None):
        return self.registrar(codigo, area, responsable, usuario)

    def listar(self):
        return list(self.repo.equipos.values())

    def buscar(self, codigo):
        try:
            return self.repo.equipos[codigo]
        except KeyError as error:
            raise NoEncontradoError(f"No existe el equipo {codigo}.") from error

    def cambiar_estado(self, codigo, estado, usuario=None):
        self._exigir_permiso(usuario, "equipos_admin")
        equipo = self.buscar(codigo)
        estado = EstadoEquipo(estado)
        if estado == EstadoEquipo.INHABILITADO:
            equipo.inhabilitar()
        elif equipo.estado == EstadoEquipo.INHABILITADO:
            equipo.devolver()
            equipo.estado = estado
        else:
            equipo.estado = estado
        self._evento("equipo_actualizado", usuario, f"Cambió estado de {codigo} a {estado}")
        return equipo

    def inhabilitar(self, codigo, usuario=None):
        self._exigir_permiso(usuario, "equipos_admin")
        equipo = self.buscar(codigo)
        equipo.inhabilitar()
        self._evento("equipo_inhabilitado", usuario, f"Inhabilitó equipo {codigo}")
        return equipo

    def devolver(self, codigo, usuario=None):
        self._exigir_permiso(usuario, "equipos_admin")
        equipo = self.buscar(codigo)
        horas = equipo.devolver()
        self._evento("equipo_devuelto", usuario, f"Devolvió equipo {codigo}")
        return horas

    def resumen_parque(self):
        conteo = {estado: 0 for estado in EstadoEquipo}
        for equipo in self.repo.equipos.values():
            conteo[equipo.estado] += 1
        conteo["total"] = len(self.repo.equipos)
        return conteo


class ServicioIncidentes(ServicioBase):
    def __init__(self, repositorio, notificador=None, clasificador=None):
        super().__init__(repositorio, notificador)
        self.clasificador = clasificador or ClasificadorIncidentes()
        self.alerta_plazo = AlertaPlazoLegal(repositorio)
        self.notificador.suscribir(BitacoraAuditoria(repositorio))
        self.notificador.suscribir(self.alerta_plazo)

    def registrar(
        self, origen, equipo, tipo_amenaza, descripcion, fecha_ocurrencia,
        fecha_deteccion, involucra_datos_personales=False, usuario=None,
    ):
        self._exigir_permiso(usuario, "registrar")
        origen = OrigenAlerta(origen)
        activo = self.repo.equipos.get(str(equipo))
        if activo is None:
            raise NoEncontradoError(f"No existe el equipo {equipo}.")
        if activo.estado == EstadoEquipo.INHABILITADO:
            raise EstadoInvalidoError(
                f"No se puede registrar un incidente: el equipo {equipo} está inhabilitado."
            )
        if not isinstance(fecha_ocurrencia, datetime) or not isinstance(fecha_deteccion, datetime):
            raise DatoInvalidoError("Ingrese fechas de ocurrencia y detección válidas.")
        if fecha_deteccion < fecha_ocurrencia:
            raise DatoInvalidoError(
                "La detección no puede ser anterior a la ocurrencia del incidente."
            )
        codigo = self.repo.siguiente_codigo_incidente()
        incidente = FabricaIncidentes.crear(
            origen,
            codigo=codigo,
            equipo=str(equipo),
            tipo_amenaza=tipo_amenaza,
            descripcion=descripcion,
            fecha_ocurrencia=fecha_ocurrencia,
            fecha_deteccion=fecha_deteccion,
            involucra_datos_personales=involucra_datos_personales,
        )
        self.repo.incidentes[codigo] = incidente
        incidente.acciones.append(
            self._accion(usuario, f"Incidente registrado: {codigo}", codigo)
        )
        self._evento(
            "incidente_registrado", usuario, f"Registró incidente {codigo}",
            codigo=codigo, incidente=incidente,
        )
        return incidente

    def listar(self, estado=None, criticidad=None, equipo=None, origen=None):
        resultado = list(self.repo.incidentes.values())
        if estado is not None:
            estado = EstadoIncidente(estado)
            resultado = [i for i in resultado if i.estado == estado]
        if criticidad is not None:
            resultado = [i for i in resultado if i.criticidad == criticidad]
        if equipo is not None:
            resultado = [i for i in resultado if i.equipo == equipo]
        if origen is not None:
            origen = OrigenAlerta(origen)
            resultado = [i for i in resultado if i.origen == origen]
        return sorted(resultado, key=lambda i: i.fecha_deteccion, reverse=True)

    def buscar(self, codigo):
        try:
            return self.repo.incidentes[codigo]
        except KeyError as error:
            raise NoEncontradoError(f"No existe el incidente {codigo}.") from error

    def asignar(self, codigo, analista, usuario=None):
        self._exigir_permiso(usuario, "asignar")
        incidente = self.buscar(codigo)
        if analista not in self.repo.usuarios or not isinstance(
            self.repo.usuarios[analista], Analista
        ):
            raise DatoInvalidoError(f"{analista} no es un analista registrado.")
        incidente.analista_asignado = analista
        self._evento("incidente_asignado", usuario, f"Asignó {codigo} a {analista}", codigo=codigo)
        return incidente

    def clasificar(self, codigo, impacto, urgencia, usuario=None):
        self._exigir_permiso(usuario, "atender")
        incidente = self.buscar(codigo)
        self.clasificador.clasificar(incidente, impacto, urgencia)
        if incidente.estado == EstadoIncidente.REGISTRADO:
            incidente.estado = EstadoIncidente.EN_ATENCION
        self._evento("incidente_clasificado", usuario, f"Clasificó incidente {codigo}", codigo=codigo)
        return incidente

    def contener(self, codigo, descripcion="", usuario=None):
        self._exigir_permiso(usuario, "contener")
        incidente = self.buscar(codigo)
        if not incidente.esta_abierto():
            raise EstadoInvalidoError("Solo se pueden contener incidentes abiertos.")
        incidente.fecha_contencion = datetime.now()
        incidente.estado = EstadoIncidente.CONTENIDO
        self._accion_en_incidente(incidente, usuario, descripcion or "Incidente contenido")
        self._evento("incidente_contenido", usuario, f"Contuvo incidente {codigo}", codigo=codigo)
        return incidente

    def escalar(self, codigo, motivo, usuario=None):
        self._exigir_permiso(usuario, "escalar")
        if not str(motivo).strip():
            raise DatoInvalidoError("Indique el motivo del escalamiento.")
        incidente = self.buscar(codigo)
        if not incidente.esta_abierto():
            raise EstadoInvalidoError("No se puede escalar un incidente cerrado.")
        incidente.estado = EstadoIncidente.ESCALADO
        self._accion_en_incidente(incidente, usuario, f"Escalado: {motivo}")
        self._evento("incidente_escalado", usuario, f"Escaló incidente {codigo}", codigo=codigo)
        return incidente

    def marcar_falso_positivo(self, codigo, motivo, usuario=None):
        self._exigir_permiso(usuario, "falso_positivo")
        if not str(motivo).strip():
            raise DatoInvalidoError("Indique el motivo para descartar la alerta.")
        incidente = self.buscar(codigo)
        if not incidente.esta_abierto():
            raise EstadoInvalidoError("El incidente ya está cerrado.")
        incidente.motivo_falso_positivo = str(motivo).strip()
        incidente.estado = EstadoIncidente.FALSO_POSITIVO
        incidente.fecha_cierre = datetime.now()
        self._accion_en_incidente(incidente, usuario, "Marcado como falso positivo")
        self._evento("falso_positivo", usuario, f"Descartó incidente {codigo}", codigo=codigo)
        return incidente

    def cerrar(self, codigo, causa_raiz, leccion_aprendida=None, usuario=None):
        self._exigir_permiso(usuario, "cerrar")
        if not str(causa_raiz or "").strip():
            raise DatoInvalidoError("No se puede cerrar un incidente sin causa raíz.")
        incidente = self.buscar(codigo)
        if not incidente.esta_abierto():
            raise EstadoInvalidoError("El incidente ya está cerrado.")
        incidente.causa_raiz = str(causa_raiz).strip()
        incidente.leccion_aprendida = (
            str(leccion_aprendida).strip() if leccion_aprendida else None
        )
        incidente.fecha_cierre = datetime.now()
        incidente.estado = EstadoIncidente.CERRADO
        self._accion_en_incidente(incidente, usuario, "Incidente cerrado")
        self._evento("incidente_cerrado", usuario, f"Cerró incidente {codigo}", codigo=codigo)
        return incidente

    def notificar_anpd(self, codigo, usuario=None):
        self._exigir_permiso(usuario, "atender")
        incidente = self.buscar(codigo)
        if not incidente.involucra_datos_personales:
            raise EstadoInvalidoError("El incidente no involucra datos personales.")
        incidente.notificado_anpd = True
        self._evento("anpd_notificada", usuario, f"Registró notificación ANPD para {codigo}", codigo=codigo)
        return incidente

    def _accion(self, usuario, descripcion, codigo):
        from .modelo import AccionAuditoria
        return AccionAuditoria(
            getattr(usuario, "nombre_usuario", usuario or "sistema"),
            descripcion,
            codigo,
        )

    def _accion_en_incidente(self, incidente, usuario, descripcion):
        incidente.acciones.append(self._accion(usuario, descripcion, incidente.codigo))


def construir_sistema(ruta_guardado=None):
    """Construye el repositorio y servicios compartidos por ambas interfaces."""
    repo = Repositorio()
    notificador = Notificador()
    from .patrones import GuardadoAutomatico
    notificador.suscribir(GuardadoAutomatico(repo, ruta_guardado))
    auth = ServicioAutenticacion(repo, notificador)
    equipos = ServicioEquipos(repo, notificador)
    incidentes = ServicioIncidentes(repo, notificador)
    incidentes.calculadora = CalculadoraIndicadores(repo)
    incidentes.reporte = GeneradorReporteMensual(repo, incidentes.calculadora, equipos)
    from .reporte_docx import GeneradorReporteWord
    incidentes.reporte_word = GeneradorReporteWord(repo, incidentes.calculadora, equipos)
    return repo, auth, equipos, incidentes
