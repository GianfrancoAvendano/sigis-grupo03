"""Interfaz de consola para las operaciones habituales de SIGIS."""

from datetime import datetime

from .consola import leer_fecha, leer_texto
from .enums import OrigenAlerta
from .excepciones import SIGISError


class Aplicacion:
    def __init__(self, repositorio, autenticacion, equipos, incidentes):
        self.repo = repositorio
        self.auth = autenticacion
        self.equipos = equipos
        self.incidentes = incidentes

    def ejecutar(self):
        print("\nSIGIS — Sistema de Gestión de Incidentes de Seguridad")
        usuario = self._iniciar_sesion()
        while usuario is not None:
            try:
                print("\n1. Panel   2. Incidentes   3. Registrar incidente")
                print("4. Equipos   5. Indicadores   6. Reporte mensual")
                if usuario.puede("bitacora"):
                    print("7. Bitácora")
                print("0. Salir")
                opcion = leer_texto("Opción: ")
                if opcion == "0":
                    break
                if opcion == "1":
                    self._panel()
                elif opcion == "2":
                    self._listar_incidentes()
                elif opcion == "3":
                    self._registrar(usuario)
                elif opcion == "4":
                    self._listar_equipos()
                elif opcion == "5":
                    self._indicadores()
                elif opcion == "6":
                    self._reporte()
                elif opcion == "7" and usuario.puede("bitacora"):
                    self._bitacora()
                else:
                    print("Opción no disponible.")
            except (SIGISError, ValueError) as error:
                print(f"Error: {error}")

    def _iniciar_sesion(self):
        for _ in range(3):
            try:
                nombre = leer_texto("Usuario: ")
                clave = leer_texto("Contraseña: ")
                usuario = self.auth.iniciar_sesion(nombre, clave)
                print(f"Bienvenido/a, {usuario.nombre_completo}.")
                return usuario
            except SIGISError as error:
                print(f"Error de autenticación: {error}")
        return None

    def _panel(self):
        abiertos = sum(1 for i in self.repo.incidentes.values() if i.esta_abierto())
        print(f"Incidentes registrados: {len(self.repo.incidentes)} | Abiertos: {abiertos}")

    def _listar_incidentes(self):
        for incidente in self.incidentes.listar():
            print(
                f"{incidente.codigo} | {incidente.fecha_deteccion:%Y-%m-%d} | "
                f"{incidente.equipo} | {incidente.tipo_amenaza} | {incidente.estado}"
            )

    def _registrar(self, usuario):
        print("Orígenes:", ", ".join(origen.value for origen in OrigenAlerta))
        origen = leer_texto("Origen: ").casefold()
        mapa = {item.value.casefold(): item for item in OrigenAlerta}
        if origen not in mapa:
            raise ValueError("Origen no válido.")
        incidente = self.incidentes.registrar(
            mapa[origen],
            leer_texto("Equipo: "),
            leer_texto("Tipo de amenaza: "),
            leer_texto("Descripción: "),
            leer_fecha("Ocurrencia (AAAA-MM-DD HH:MM): "),
            leer_fecha("Detección (AAAA-MM-DD HH:MM): "),
            leer_texto("¿Involucra datos personales? (s/n): ").casefold() == "s",
            usuario,
        )
        print(f"Incidente registrado: {incidente.codigo}")

    def _listar_equipos(self):
        for equipo in self.equipos.listar():
            print(f"{equipo.codigo} | {equipo.area} | {equipo.estado}")

    def _indicadores(self):
        ahora = datetime.now()
        datos = self.incidentes.calculadora.resumen(
            datetime(ahora.year, ahora.month, 1), ahora
        )
        print(f"Alertas del mes: {datos['total_alertas']}")
        print(f"MTTD: {datos['mttd']} h | Falsos positivos: {datos['tasa_fp']} %")
        print(f"Cumplimiento objetivo: {datos['cumplimiento']} %")

    def _reporte(self):
        ahora = datetime.now()
        print(self.incidentes.reporte.generar(ahora.year, ahora.month))

    def _bitacora(self):
        for accion in self.repo.bitacora:
            print(f"{accion.momento:%Y-%m-%d %H:%M} | {accion.usuario} | {accion.descripcion}")
