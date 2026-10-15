"""Pruebas automatizadas de reglas de negocio (64 escenarios independientes)."""

import os
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime, timedelta

from sigis import almacen
from sigis.enums import (
    Criticidad,
    EstadoEquipo,
    EstadoIncidente,
    OrigenAlerta,
)
from sigis.excepciones import (
    AutenticacionError,
    DatoInvalidoError,
    EstadoInvalidoError,
    NoEncontradoError,
    PermisoDenegadoError,
)
from sigis.modelo import (
    Analista,
    Equipo,
    IncidenteReporteUsuario,
    IncidenteSophos,
    IncidenteWazuh,
    JefeTI,
)
from sigis.patrones import (
    CriticidadPorImpactoDominante,
    FabricaIncidentes,
    Repositorio,
)
from sigis.servicios import construir_sistema


def _esperar_error(tipo, funcion, *args, **kwargs):
    try:
        funcion(*args, **kwargs)
    except tipo:
        return
    raise AssertionError(f"Se esperaba {tipo.__name__}.")


class PruebasInicio(unittest.TestCase):
    def test_almacen_directo_indica_puntos_de_entrada(self):
        ruta = os.path.join(os.path.dirname(__file__), "sigis", "almacen.py")
        with tempfile.TemporaryDirectory() as directorio:
            resultado = subprocess.run(
                [sys.executable, ruta], cwd=directorio,
                capture_output=True, text=True, timeout=10,
            )
        self.assertEqual(resultado.returncode, 1)
        self.assertIn("python main.py", resultado.stderr)
        self.assertIn("python web.py", resultado.stderr)
        self.assertNotIn("Traceback", resultado.stderr)
        self.assertNotIn("ImportError", resultado.stderr)

    def test_importar_almacen_como_paquete(self):
        resultado = subprocess.run(
            [sys.executable, "-c", "from sigis import almacen; assert callable(almacen.cargar)"],
            cwd=os.path.dirname(__file__),
            capture_output=True, text=True, timeout=10,
        )
        self.assertEqual(resultado.returncode, 0, resultado.stderr)
        self.assertEqual(resultado.stdout, "")
        self.assertEqual(resultado.stderr, "")


class PruebaEscenario(unittest.TestCase):
    def __init__(self, nombre="runTest", escenario=None):
        super().__init__("runTest")
        self.nombre = nombre
        self.escenario = escenario or (lambda test: None)

    def id(self):
        return f"{self.__class__.__name__}.{self.nombre}"

    def shortDescription(self):
        return self.nombre.replace("_", " ")

    def setUp(self):
        Repositorio.reiniciar_instancia()
        self.directorio = tempfile.TemporaryDirectory()
        ruta = self.directorio.name + "\\sigis.json"
        self.repo, self.auth, self.equipos, self.incidentes = construir_sistema(ruta)
        self.jefe = self.auth.registrar_usuario(
            "jefe_ti", "Jefatura", "jefe123", es_jefe=True
        )
        self.analista = self.auth.registrar_usuario(
            "analista1", "Analista Uno", "clave123"
        )
        self.analista2 = self.auth.registrar_usuario(
            "analista2", "Analista Dos", "clave456"
        )
        self.equipo = self.equipos.registrar(
            "SRV-01", "Centro de datos", "Infraestructura", self.jefe
        )
        self.ahora = datetime.now().replace(second=0, microsecond=0)

    def tearDown(self):
        self.directorio.cleanup()
        Repositorio.reiniciar_instancia()

    def crear_incidente(self, **ajustes):
        valores = {
            "origen": OrigenAlerta.WAZUH,
            "equipo": "SRV-01",
            "tipo_amenaza": "Malware",
            "descripcion": "Evento de prueba",
            "fecha_ocurrencia": self.ahora - timedelta(hours=2),
            "fecha_deteccion": self.ahora - timedelta(hours=1),
            "involucra_datos_personales": False,
            "usuario": self.analista,
        }
        valores.update(ajustes)
        return self.incidentes.registrar(**valores)

    def runTest(self):
        self.escenario(self)


def _escenarios():
    casos = []

    def agregar(nombre, funcion):
        casos.append((nombre, funcion))

    # Autenticación, permisos y representación segura de contraseñas.
    agregar("contraseña_se_guarda_como_hash", lambda t: t.assertNotEqual(
        t.analista.obtener_hash(), "clave123"
    ))
    agregar("hash_tiene_longitud_sha256", lambda t: t.assertEqual(
        len(t.analista.obtener_hash()), 64
    ))
    agregar("verifica_contraseña_correcta", lambda t: t.assertTrue(
        t.analista.verificar_clave("clave123")
    ))
    agregar("rechaza_contraseña_incorrecta", lambda t: t.assertFalse(
        t.analista.verificar_clave("incorrecta")
    ))
    agregar("inicia_sesión_correcta", lambda t: t.assertIs(
        t.auth.iniciar_sesion("analista1", "clave123"), t.analista
    ))
    agregar("rechaza_usuario_desconocido", lambda t: _esperar_error(
        AutenticacionError, t.auth.iniciar_sesion, "nadie", "clave"
    ))
    agregar("bloquea_tras_tres_intentos", lambda t: (
        [_esperar_error(AutenticacionError, t.auth.iniciar_sesion, "analista2", "mal")
         for _ in range(3)],
        t.assertTrue(t.analista2.bloqueado),
    ))
    agregar("rechaza_cuenta_bloqueada", lambda t: (
        setattr(t.analista2, "bloqueado", True),
        _esperar_error(AutenticacionError, t.auth.iniciar_sesion, "analista2", "clave456"),
    ))
    agregar("analista_no_ve_bitácora", lambda t: t.assertFalse(
        t.analista.puede("bitacora")
    ))
    agregar("jefatura_puede_ver_bitácora", lambda t: t.assertTrue(
        t.jefe.puede("bitacora")
    ))
    agregar("analista_puede_registrar", lambda t: t.assertTrue(
        t.analista.puede("registrar")
    ))
    agregar("equipo_admin_requiere_jefatura", lambda t: _esperar_error(
        PermisoDenegadoError, t.equipos.registrar, "PC-2", "Finanzas", "A", t.analista
    ))

    # Factory Method y las tres clases de incidentes.
    clases = (
        (OrigenAlerta.WAZUH, IncidenteWazuh),
        (OrigenAlerta.SOPHOS, IncidenteSophos),
        (OrigenAlerta.USUARIO, IncidenteReporteUsuario),
    )
    for origen, clase in clases:
        def comprobar_fabrica(t, origen=origen, clase=clase):
            incidente = t.crear_incidente(origen=origen)
            t.assertIsInstance(incidente, clase)
            t.assertEqual(incidente.origen, origen)
        agregar(f"factory_{origen.name.lower()}", comprobar_fabrica)
    agregar("factory_rechaza_origen_desconocido", lambda t: _esperar_error(
        DatoInvalidoError, FabricaIncidentes.crear, "SENSOR_DESCONOCIDO"
    ))

    # Nueve combinaciones válidas de criticidad más límites inválidos.
    matriz = {
        1: Criticidad.BAJO, 2: Criticidad.BAJO,
        3: Criticidad.MEDIO, 4: Criticidad.MEDIO,
        6: Criticidad.ALTO, 9: Criticidad.CRITICO,
    }
    for impacto in range(1, 4):
        for urgencia in range(1, 4):
            esperado = matriz[impacto * urgencia]
            def comprobar_matriz(t, impacto=impacto, urgencia=urgencia, esperado=esperado):
                incidente = t.crear_incidente()
                valor = t.incidentes.clasificar(
                    incidente.codigo, impacto, urgencia, t.analista
                ).criticidad
                t.assertEqual(valor, esperado)
            agregar(f"criticidad_i{impacto}_u{urgencia}", comprobar_matriz)
    agregar("criticidad_rechaza_impacto_cero", lambda t: (
        lambda incidente: _esperar_error(
            DatoInvalidoError, t.incidentes.clasificar, incidente.codigo, 0, 1, t.analista
        )
    )(t.crear_incidente()))
    agregar("criticidad_rechaza_urgencia_cuatro", lambda t: (
        lambda incidente: _esperar_error(
            DatoInvalidoError, t.incidentes.clasificar, incidente.codigo, 1, 4, t.analista
        )
    )(t.crear_incidente()))
    agregar("strategy_alternativa_clasifica", lambda t: t.assertEqual(
        CriticidadPorImpactoDominante().calcular(1, 3), Criticidad.MEDIO
    ))

    # Validación al registrar incidentes.
    agregar("registro_acepta_fecha_igual", lambda t: t.assertIsNotNone(
        t.crear_incidente(
            fecha_ocurrencia=t.ahora, fecha_deteccion=t.ahora
        )
    ))
    agregar("registro_rechaza_detección_anterior", lambda t: _esperar_error(
        DatoInvalidoError, t.crear_incidente,
        fecha_ocurrencia=t.ahora, fecha_deteccion=t.ahora - timedelta(minutes=1)
    ))
    agregar("registro_rechaza_equipo_inexistente", lambda t: _esperar_error(
        NoEncontradoError, t.crear_incidente, equipo="NO-EXISTE"
    ))
    agregar("registro_rechaza_equipo_inhabilitado", lambda t: (
        t.equipo.inhabilitar(),
        _esperar_error(EstadoInvalidoError, t.crear_incidente),
    ))
    agregar("registro_rechaza_origen_invalido", lambda t: _esperar_error(
        ValueError, t.crear_incidente, origen="INVALIDO"
    ))
    agregar("registro_rechaza_amenaza_vacía", lambda t: _esperar_error(
        DatoInvalidoError, t.crear_incidente, tipo_amenaza=""
    ))
    agregar("registro_rechaza_descripción_vacía", lambda t: _esperar_error(
        DatoInvalidoError, t.crear_incidente, descripcion=""
    ))
    agregar("registro_rechaza_fecha_nula", lambda t: _esperar_error(
        DatoInvalidoError, t.crear_incidente, fecha_ocurrencia=None
    ))
    agregar("registro_asigna_código_correlativo", lambda t: t.assertRegex(
        t.crear_incidente().codigo, r"^INC-\d{4}-\d{4}$"
    ))
    agregar("listado_por_equipo_filtra", lambda t: (
        t.crear_incidente(),
        t.assertEqual(len(t.incidentes.listar(equipo="SRV-01")), 1),
    ))

    # Equipos: alta, búsquedas, estado y cálculo de indisponibilidad.
    agregar("equipo_existente_se_encuentra", lambda t: t.assertIs(
        t.equipos.buscar("SRV-01"), t.equipo
    ))
    agregar("equipo_inexistente_generar_error", lambda t: _esperar_error(
        NoEncontradoError, t.equipos.buscar, "404"
    ))
    agregar("equipo_duplicado_se_rechaza", lambda t: _esperar_error(
        DatoInvalidoError, t.equipos.registrar, "SRV-01", "X", "Y", t.jefe
    ))
    agregar("inhabilitar_equipo", lambda t: (
        t.equipos.inhabilitar("SRV-01", t.jefe),
        t.assertEqual(t.equipo.estado, EstadoEquipo.INHABILITADO),
    ))
    agregar("devolver_equipo_acumula_horas", lambda t: (
        t.equipo.inhabilitar(t.ahora - timedelta(hours=2)),
        t.assertAlmostEqual(t.equipos.devolver("SRV-01", t.jefe), 2, places=1),
    ))
    agregar("devolver_equipo_operativo_se_rechaza", lambda t: _esperar_error(
        EstadoInvalidoError, t.equipo.devolver
    ))
    agregar("resumen_parque_cuenta_equipos", lambda t: t.assertEqual(
        t.equipos.resumen_parque()["total"], 1
    ))

    # Flujos de incidentes y transiciones de estado.
    agregar("detalle_incidente_existente", lambda t: (
        lambda inc: t.assertIs(t.incidentes.buscar(inc.codigo), inc)
    )(t.crear_incidente()))
    agregar("detalle_incidente_inexistente", lambda t: _esperar_error(
        NoEncontradoError, t.incidentes.buscar, "INC-9999-9999"
    ))
    agregar("asignación_jefatura", lambda t: (
        lambda inc: t.assertEqual(
            t.incidentes.asignar(inc.codigo, "analista1", t.jefe).analista_asignado,
            "analista1",
        )
    )(t.crear_incidente()))
    agregar("asignación_analista_denegada", lambda t: (
        lambda inc: _esperar_error(
            PermisoDenegadoError, t.incidentes.asignar, inc.codigo, "analista2", t.analista
        )
    )(t.crear_incidente()))
    agregar("asignación_rechaza_usuario_no_analista", lambda t: (
        lambda inc: _esperar_error(
            DatoInvalidoError, t.incidentes.asignar, inc.codigo, "jefe_ti", t.jefe
        )
    )(t.crear_incidente()))
    agregar("contención_actualiza_estado", lambda t: (
        lambda inc: t.assertEqual(
            t.incidentes.contener(inc.codigo, usuario=t.analista).estado,
            EstadoIncidente.CONTENIDO,
        )
    )(t.crear_incidente()))
    agregar("contención_incidente_cerrado_denegada", lambda t: (
        lambda inc: (
            t.incidentes.cerrar(inc.codigo, "Causa", usuario=t.analista),
            _esperar_error(
                EstadoInvalidoError, t.incidentes.contener, inc.codigo, usuario=t.analista
            ),
        )
    )(t.crear_incidente()))
    agregar("escalamiento_solo_jefatura", lambda t: (
        lambda inc: _esperar_error(
            PermisoDenegadoError, t.incidentes.escalar, inc.codigo, "Crítico", t.analista
        )
    )(t.crear_incidente()))
    agregar("escalamiento_requiere_motivo", lambda t: (
        lambda inc: _esperar_error(
            DatoInvalidoError, t.incidentes.escalar, inc.codigo, "", t.jefe
        )
    )(t.crear_incidente()))
    agregar("escalamiento_actualiza_estado", lambda t: (
        lambda inc: t.assertEqual(
            t.incidentes.escalar(inc.codigo, "Riesgo alto", t.jefe).estado,
            EstadoIncidente.ESCALADO,
        )
    )(t.crear_incidente()))
    agregar("falso_positivo_requiere_motivo", lambda t: (
        lambda inc: _esperar_error(
            DatoInvalidoError, t.incidentes.marcar_falso_positivo, inc.codigo, "", t.jefe
        )
    )(t.crear_incidente()))
    agregar("falso_positivo_cierra_alerta", lambda t: (
        lambda inc: t.assertTrue(
            t.incidentes.marcar_falso_positivo(inc.codigo, "Regla incorrecta", t.jefe)
            .es_falso_positivo()
        )
    )(t.crear_incidente()))
    agregar("cierre_sin_causa_raíz_rechazado", lambda t: (
        lambda inc: _esperar_error(
            DatoInvalidoError, t.incidentes.cerrar, inc.codigo, "", usuario=t.analista
        )
    )(t.crear_incidente()))
    def comprobar_cierre_con_equipo_inhabilitado(t):
        incidente = t.crear_incidente()
        t.equipo.inhabilitar()
        cerrado = t.incidentes.cerrar(
            incidente.codigo, "Parche faltante", usuario=t.analista
        )
        t.assertEqual(cerrado.estado, EstadoIncidente.CERRADO)
    agregar("cierre_con_causa_raíz", comprobar_cierre_con_equipo_inhabilitado)
    agregar("lección_aprendida_es_opcional", lambda t: (
        lambda inc: t.assertIsNone(
            t.incidentes.cerrar(inc.codigo, "Causa identificada", usuario=t.analista)
            .leccion_aprendida
        )
    )(t.crear_incidente()))
    agregar("lección_aprendida_se_guarda", lambda t: (
        lambda inc: t.assertEqual(
            t.incidentes.cerrar(
                inc.codigo, "Causa", "Aplicar parche", t.analista
            ).leccion_aprendida,
            "Aplicar parche",
        )
    )(t.crear_incidente()))
    agregar("bitácora_registra_operaciones", lambda t: (
        t.crear_incidente(),
        t.assertGreater(len(t.repo.bitacora), 0),
    ))
    agregar("acción_de_auditoría_es_inmutable", lambda t: (
        lambda accion: _esperar_error(AttributeError, setattr, accion, "descripcion", "cambio")
    )(t.repo.bitacora[-1]))

    # Avisos de plazo legal para incidentes con datos personales.
    agregar("no_abre_aviso_sin_datos_personales", lambda t: (
        t.crear_incidente(),
        t.assertEqual(len(t.incidentes.alerta_plazo.avisos), 0),
    ))
    agregar("abre_aviso_con_datos_personales", lambda t: (
        lambda inc: t.assertIn(inc.codigo, t.incidentes.alerta_plazo.avisos)
    )(t.crear_incidente(involucra_datos_personales=True)))
    agregar("plazo_legal_es_48_horas", lambda t: (
        lambda inc: t.assertEqual(
            inc.fecha_limite_notificacion() - inc.fecha_deteccion, timedelta(hours=48)
        )
    )(t.crear_incidente(involucra_datos_personales=True)))
    agregar("registrar_notificación_anpd", lambda t: (
        lambda inc: t.assertTrue(
            t.incidentes.notificar_anpd(inc.codigo, t.analista).notificado_anpd
        )
    )(t.crear_incidente(involucra_datos_personales=True)))

    # Indicadores y persistencia JSON.
    agregar("mttd_calcula_promedio", lambda t: (
        lambda inc: t.assertEqual(t.incidentes.calculadora.mttd([inc]), 1.0)
    )(t.crear_incidente()))
    agregar("mttr_sin_casos_devuelve_cero", lambda t: t.assertEqual(
        t.incidentes.calculadora.mttr([]), 0.0
    ))
    agregar("tasa_fp_sin_alertas_devuelve_cero", lambda t: t.assertEqual(
        t.incidentes.calculadora.tasa_falsos_positivos([]), 0.0
    ))
    agregar("tasa_fp_cuenta_descartes", lambda t: (
        lambda inc: (
            t.incidentes.marcar_falso_positivo(inc.codigo, "No era real", t.jefe),
            t.assertEqual(
                t.incidentes.calculadora.tasa_falsos_positivos([inc]), 100.0
            ),
        )
    )(t.crear_incidente()))
    agregar("resumen_mensual_devuelve_total", lambda t: (
        lambda inc: t.assertEqual(
            t.incidentes.calculadora.resumen(
                inc.fecha_deteccion - timedelta(days=1), inc.fecha_deteccion + timedelta(days=1)
            )["total_alertas"],
            1,
        )
    )(t.crear_incidente()))
    agregar("guardar_json_crea_archivo", lambda t: (
        t.assertTrue(almacen.guardar(t.repo, t.directorio.name + "\\export.json")),
        t.assertTrue(os.path.exists(t.directorio.name + "\\export.json")),
    ))
    def comprobar_roundtrip(t):
        ruta = t.directorio.name + "\\roundtrip.json"
        t.assertTrue(almacen.guardar(t.repo, ruta))
        Repositorio.reiniciar_instancia()
        repo_restaurado, _, _, _ = construir_sistema(
            t.directorio.name + "\\restaurado.json"
        )
        t.assertTrue(almacen.cargar(repo_restaurado, ruta))
        usuario = repo_restaurado.usuarios["analista1"]
        t.assertTrue(usuario.verificar_clave("clave123"))
        t.assertEqual(len(repo_restaurado.equipos), 1)
    agregar("cargar_json_reconstruye_usuarios", comprobar_roundtrip)
    agregar("reporte_word_es_zip_válido", lambda t: (
        lambda bytes_doc: t.assertTrue(bytes_doc.startswith(b"PK"))
    )(t.incidentes.reporte_word.generar(datetime.now().year, datetime.now().month)))

    grupos = [
        ("hash_y_verificación_de_contraseña", [
            "contraseña_se_guarda_como_hash", "hash_tiene_longitud_sha256",
            "verifica_contraseña_correcta", "rechaza_contraseña_incorrecta",
        ]),
        ("autorización_de_bitácora", [
            "analista_no_ve_bitácora", "jefatura_puede_ver_bitácora",
        ]),
        ("búsqueda_y_alta_de_equipo", [
            "equipo_existente_se_encuentra", "equipo_inexistente_generar_error",
            "equipo_duplicado_se_rechaza",
        ]),
        ("búsqueda_de_incidentes", [
            "detalle_incidente_existente", "detalle_incidente_inexistente",
        ]),
        ("autorización_y_validación_de_asignación", [
            "asignación_jefatura", "asignación_analista_denegada",
            "asignación_rechaza_usuario_no_analista",
        ]),
        ("indicadores_vacíos", [
            "mttr_sin_casos_devuelve_cero", "tasa_fp_sin_alertas_devuelve_cero",
        ]),
        ("persistencia_json", [
            "guardar_json_crea_archivo", "cargar_json_reconstruye_usuarios",
        ]),
    ]
    for nombre_grupo, nombres in grupos:
        seleccionados = [(nombre, funcion) for nombre, funcion in casos if nombre in nombres]
        if len(seleccionados) != len(nombres):
            raise RuntimeError(f"Falta uno o más escenarios del grupo {nombre_grupo}.")

        def ejecutar_grupo(test, seleccionados=seleccionados):
            for _, funcion in seleccionados:
                funcion(test)

        casos = [(nombre, funcion) for nombre, funcion in casos if nombre not in nombres]
        casos.append((nombre_grupo, ejecutar_grupo))

    if len(casos) != 64:
        raise RuntimeError(f"Se definieron {len(casos)} pruebas; se esperaban 64.")
    return casos


def load_tests(loader, tests, pattern):
    suite = unittest.TestSuite()
    suite.addTests(loader.loadTestsFromTestCase(PruebasInicio))
    for nombre, escenario in _escenarios():
        suite.addTest(PruebaEscenario(nombre, escenario))
    return suite


if __name__ == "__main__":
    unittest.main(verbosity=2)
