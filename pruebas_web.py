"""Pruebas HTTP de pantallas web con persistencia temporal aislada."""

import csv
import io
import json
import os
import tempfile
import threading
import unittest
from datetime import datetime, timedelta
from html.parser import HTMLParser
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer
from urllib.parse import urlencode

from sigis.patrones import Repositorio
from sigis.web.servidor import crear_aplicacion, crear_manejador


class Formularios(HTMLParser):
    def __init__(self, contenido):
        super().__init__()
        self.formularios = []
        self.actual = None
        self.feed(contenido)

    def handle_starttag(self, tag, attrs):
        atributos = dict(attrs)
        if tag == "form":
            self.actual = {"action": atributos.get("action"), "campos": {}}
            self.formularios.append(self.actual)
        elif tag == "input" and self.actual is not None:
            self.actual["campos"][atributos.get("name")] = atributos.get("value", "")

    def handle_endtag(self, tag):
        if tag == "form":
            self.actual = None


class PruebasWeb(unittest.TestCase):
    def setUp(self):
        Repositorio.reiniciar_instancia()
        self.temporal = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporal.cleanup)
        self.addCleanup(Repositorio.reiniciar_instancia)
        self.ruta = os.path.join(self.temporal.name, "sigis.json")
        self.estado = crear_aplicacion(self.ruta)
        manejador = crear_manejador(self.estado)
        manejador.log_message = lambda *args: None
        self.servidor = ThreadingHTTPServer(("127.0.0.1", 0), manejador)
        self.hilo = threading.Thread(target=self.servidor.serve_forever, daemon=True)
        self.hilo.start()
        self.addCleanup(self._cerrar_servidor)
        self.cookie = ""

    def _cerrar_servidor(self):
        self.servidor.shutdown()
        self.servidor.server_close()
        self.hilo.join(timeout=5)

    def solicitud(self, metodo, ruta, datos=None):
        conexion = HTTPConnection("127.0.0.1", self.servidor.server_port, timeout=10)
        try:
            cabeceras = {"Cookie": self.cookie}
            cuerpo = urlencode(datos) if datos is not None else None
            if cuerpo is not None:
                cabeceras["Content-Type"] = "application/x-www-form-urlencoded"
            conexion.request(metodo, ruta, cuerpo, cabeceras)
            respuesta = conexion.getresponse()
            contenido = respuesta.read()
            return respuesta.status, dict(respuesta.getheaders()), contenido
        finally:
            conexion.close()

    def entrar(self, usuario="jefe_ti", clave="jefe123"):
        self.cookie = ""
        codigo, cabeceras, _ = self.solicitud(
            "POST", "/entrar", {"usuario": usuario, "clave": clave}
        )
        self.assertEqual(codigo, 303)
        self.cookie = cabeceras["Set-Cookie"].split(";", 1)[0]

    def csrf(self, ruta="/panel", accion="/salir"):
        codigo, _, contenido = self.solicitud("GET", ruta)
        self.assertEqual(codigo, 200)
        for formulario in Formularios(contenido.decode("utf-8")).formularios:
            if formulario["action"] == accion:
                return formulario["campos"]["csrf"]
        self.fail(f"No se encontro el formulario {accion}.")

    def test_salir_desde_formulario_invalida_sesion(self):
        self.entrar()
        token = self.csrf()
        self.assertTrue(token)
        codigo, cabeceras, _ = self.solicitud("POST", "/salir", {"csrf": token})
        self.assertEqual(codigo, 303)
        self.assertEqual(cabeceras["Location"], "/login")
        self.assertEqual(self.solicitud("GET", "/panel")[1]["Location"], "/login")

    def test_salir_sin_csrf_conserva_sesion(self):
        self.entrar()
        self.assertEqual(self.solicitud("POST", "/salir", {})[0], 403)
        self.assertEqual(self.solicitud("GET", "/panel")[0], 200)

    def test_carga_exclusivamente_ruta_configurada(self):
        ruta = os.path.join(self.temporal.name, "vacio.json")
        with open(ruta, "w", encoding="utf-8") as archivo:
            json.dump({"usuarios": [], "equipos": [], "incidentes": []}, archivo)
        Repositorio.reiniciar_instancia()
        aplicacion = crear_aplicacion(ruta)
        self.assertEqual(aplicacion["repo"].usuarios, {})
        self.assertEqual(aplicacion["repo"].incidentes, {})
        self.assertTrue(os.path.isfile(self.ruta))

    def test_jefatura_registra_y_cambia_estado_equipo(self):
        self.entrar()
        token = self.csrf("/equipos/nuevo", "/equipos/nuevo")
        codigo, _, _ = self.solicitud("POST", "/equipos/nuevo", {
            "csrf": token, "codigo": "WEB-01", "area": "Soporte", "responsable": "Ana",
        })
        self.assertEqual(codigo, 303)
        for nuevo_estado in ("Inhabilitado", "Operativo"):
            codigo, _, _ = self.solicitud("POST", "/equipos/WEB-01/estado", {
                "csrf": token, "estado": nuevo_estado,
            })
            self.assertEqual(codigo, 303)
            self.assertEqual(self.estado["repo"].equipos["WEB-01"].estado.value, nuevo_estado)
        with open(self.ruta, encoding="utf-8") as archivo:
            self.assertIn("WEB-01", {equipo["codigo"] for equipo in json.load(archivo)["equipos"]})

    def test_analista_no_administra_equipos(self):
        self.entrar("analista1", "clave123")
        token = self.csrf()
        self.assertEqual(self.solicitud("GET", "/equipos/nuevo")[0], 403)
        self.assertEqual(self.solicitud("POST", "/equipos/nuevo", {
            "csrf": token, "codigo": "NO", "area": "TI", "responsable": "Ana",
        })[0], 403)
        codigo_equipo = next(iter(self.estado["repo"].equipos))
        self.assertEqual(self.solicitud("POST", f"/equipos/{codigo_equipo}/estado", {
            "csrf": token, "estado": "Inhabilitado",
        })[0], 403)
        self.assertNotIn("NO", self.estado["repo"].equipos)

    def test_acciones_incidente_tienen_formularios_independientes(self):
        self.entrar()
        incidente = next(item for item in self.estado["repo"].incidentes.values() if item.esta_abierto())
        ruta = f"/incidentes/{incidente.codigo}"
        codigo, _, contenido = self.solicitud("GET", ruta)
        self.assertEqual(codigo, 200)
        formularios = Formularios(contenido.decode("utf-8")).formularios
        acciones = {form["campos"].get("accion"): form for form in formularios}
        self.assertIn("motivo", acciones["escalar"]["campos"])
        self.assertIn("motivo", acciones["falso"]["campos"])
        self.assertNotIn("motivo", acciones["clasificar"]["campos"])
        codigo, _, _ = self.solicitud("POST", ruta + "/acciones", {
            "csrf": acciones["escalar"]["campos"]["csrf"],
            "accion": "escalar", "motivo": "Requiere jefatura",
        })
        self.assertEqual(codigo, 303)
        self.assertEqual(incidente.estado.value, "Escalado")

    def test_pantallas_y_permisos_bitacora(self):
        self.entrar()
        for ruta in ("/panel", "/incidentes", "/incidentes/nuevo", "/equipos", "/indicadores", "/reporte", "/bitacora"):
            with self.subTest(ruta=ruta):
                self.assertEqual(self.solicitud("GET", ruta)[0], 200)
        self.entrar("analista1", "clave123")
        self.assertEqual(self.solicitud("GET", "/bitacora")[0], 403)

    def test_filtros_combinados_y_csv_coinciden(self):
        self.entrar()
        incidente = next(item for item in self.estado["repo"].incidentes.values() if item.criticidad)
        query = urlencode({
            "q": incidente.codigo, "estado": incidente.estado.value,
            "origen": incidente.origen.value, "criticidad": incidente.criticidad.value,
            "desde": incidente.fecha_deteccion.date().isoformat(),
            "hasta": incidente.fecha_deteccion.date().isoformat(),
        })
        codigo, _, contenido = self.solicitud("GET", "/incidentes?" + query)
        self.assertEqual(codigo, 200)
        self.assertIn("1 incidentes", contenido.decode("utf-8"))
        codigo, _, contenido = self.solicitud("GET", "/incidentes.csv?" + query)
        self.assertEqual(codigo, 200)
        filas = list(csv.reader(io.StringIO(contenido.decode("utf-8-sig"))))
        self.assertEqual(len(filas), 2)
        self.assertEqual(filas[1][0], incidente.codigo)

    def test_filtros_invalidos_y_sin_resultados(self):
        self.entrar()
        for query in ("estado=INVENTADO", "desde=2026-12-01&hasta=2026-01-01", "desde=fecha"):
            with self.subTest(query=query):
                self.assertEqual(self.solicitud("GET", "/incidentes?" + query)[0], 400)
                self.assertEqual(self.solicitud("GET", "/incidentes.csv?" + query)[0], 400)
        codigo, _, contenido = self.solicitud("GET", "/incidentes?q=NO-EXISTE-987654")
        self.assertEqual(codigo, 200)
        self.assertIn("No hay incidentes con estos filtros", contenido.decode("utf-8"))

    def test_busqueda_escapa_html_y_no_busca_etiquetas(self):
        self.entrar()
        codigo, _, contenido = self.solicitud("GET", "/incidentes?" + urlencode({"q": '<script>alert("x")</script>'}))
        self.assertEqual(codigo, 200)
        self.assertNotIn("<script>", contenido.decode("utf-8"))
        codigo, _, contenido = self.solicitud("GET", "/incidentes?q=%3Ctr%3E")
        self.assertEqual(codigo, 200)
        self.assertIn("0 incidentes", contenido.decode("utf-8"))

    def crear_incidente_web(self):
        token = self.csrf("/incidentes/nuevo", "/incidentes/nuevo")
        equipo = next(item for item in self.estado["repo"].equipos.values() if item.estado.value != "Inhabilitado")
        ahora = datetime.now().replace(second=0, microsecond=0)
        datos = {
            "csrf": token, "origen": "Wazuh", "equipo": equipo.codigo,
            "amenaza": "Caso HTTP", "descripcion": "Incidente de validación web",
            "ocurrencia": (ahora - timedelta(hours=2)).isoformat(),
            "deteccion": (ahora - timedelta(hours=1)).isoformat(), "datos_personales": "si",
        }
        codigo, _, _ = self.solicitud("POST", "/incidentes/nuevo", {
            **datos, "ocurrencia": ahora.isoformat(),
        })
        self.assertEqual(codigo, 400)
        codigo, cabeceras, _ = self.solicitud("POST", "/incidentes/nuevo", datos)
        self.assertEqual(codigo, 303)
        return cabeceras["Location"], token

    def test_ciclo_completo_incidente_desde_web(self):
        self.entrar()
        ruta, token = self.crear_incidente_web()
        codigo_incidente = ruta.rsplit("/", 1)[-1]
        acciones = (
            {"accion": "clasificar", "impacto": "3", "urgencia": "3"},
            {"accion": "asignar", "analista": "analista1"},
            {"accion": "contener"},
            {"accion": "notificar"},
        )
        for datos in acciones:
            with self.subTest(accion=datos["accion"]):
                self.assertEqual(self.solicitud("POST", ruta + "/acciones", {"csrf": token, **datos})[0], 303)
        self.assertEqual(self.solicitud("POST", ruta + "/acciones", {
            "csrf": token, "accion": "cerrar", "causa": "",
        })[0], 400)
        self.assertEqual(self.solicitud("POST", ruta + "/acciones", {
            "csrf": token, "accion": "cerrar", "causa": "Parche pendiente", "leccion": "Actualizar equipos",
        })[0], 303)
        incidente = self.estado["repo"].incidentes[codigo_incidente]
        self.assertEqual(incidente.estado.value, "Cerrado")
        self.assertEqual(incidente.analista_asignado, "analista1")
        self.assertTrue(incidente.notificado_anpd)
        codigo, _, contenido = self.solicitud("GET", ruta)
        self.assertEqual(codigo, 200)
        self.assertIn("Actualizar equipos", contenido.decode("utf-8"))
        self.assertIn("Historial del incidente", contenido.decode("utf-8"))

    def test_falso_positivo_con_motivo_desde_web(self):
        self.entrar()
        ruta, token = self.crear_incidente_web()
        self.assertEqual(self.solicitud("POST", ruta + "/acciones", {
            "csrf": token, "accion": "falso", "motivo": "Actividad autorizada",
        })[0], 303)
        incidente = self.estado["repo"].incidentes[ruta.rsplit("/", 1)[-1]]
        self.assertEqual(incidente.motivo_falso_positivo, "Actividad autorizada")
        self.assertTrue(incidente.es_falso_positivo())

    def test_descargas_y_periodo_reporte(self):
        self.entrar()
        codigo, cabeceras, contenido = self.solicitud("GET", "/reporte.docx?anio=2026&mes=10")
        self.assertEqual(codigo, 200)
        self.assertIn("wordprocessingml.document", cabeceras["Content-Type"])
        self.assertTrue(contenido.startswith(b"PK"))
        self.assertEqual(self.solicitud("GET", "/reporte?anio=2026&mes=13")[0], 400)
        self.assertEqual(self.solicitud("GET", "/reporte.docx?anio=2026&mes=13")[0], 400)


if __name__ == "__main__":
    unittest.main(verbosity=2)