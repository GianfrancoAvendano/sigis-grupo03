"""Servidor web local de SIGIS: rutas, formularios y sesiones."""

import csv
import io
import secrets
import threading
import webbrowser
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from html import escape
from urllib.parse import parse_qs, quote, unquote, urlencode, urlsplit

from .. import almacen
from ..datos_demo import cargar
from ..enums import Criticidad, EstadoEquipo, EstadoIncidente, OrigenAlerta
from ..excepciones import PermisoDenegadoError, SIGISError
from ..modelo import Analista
from ..servicios import construir_sistema
from .plantillas import login as login_html
from .plantillas import pagina


MAX_BODY_BYTES = 65536


def crear_aplicacion(ruta_guardado=None):
    ruta_guardado = ruta_guardado if ruta_guardado is not None else almacen.ARCHIVO
    repo, auth, equipos, incidentes = construir_sistema(ruta_guardado)
    if almacen.cargar(repo, ruta_guardado):
        incidentes.alerta_plazo.reconstruir()
    else:
        cargar(auth, equipos, incidentes)
        almacen.guardar(repo, ruta_guardado)
    return {
        "repo": repo,
        "auth": auth,
        "equipos": equipos,
        "incidentes": incidentes,
        "sesiones": {},
        "lock": threading.Lock(),
    }


def crear_manejador(estado):
    class ManejadorSIGIS(BaseHTTPRequestHandler):
        server_version = "SIGIS/1.0"

        def log_message(self, formato, *args):
            print("%s - %s" % (self.address_string(), formato % args))

        def do_GET(self):
            ruta = urlsplit(self.path)
            path = unquote(ruta.path)
            usuario = self._usuario()
            if path in ("/", "/login"):
                if usuario is not None:
                    return self._redirect("/panel")
                return self._html(login_html())
            if usuario is None:
                return self._redirect("/login")
            try:
                if path == "/panel":
                    return self._panel(usuario)
                if path == "/incidentes":
                    return self._incidentes(usuario)
                if path == "/incidentes/nuevo":
                    return self._formulario_incidente(usuario)
                if path == "/incidentes.csv":
                    return self._csv(usuario)
                if path.startswith("/incidentes/"):
                    return self._detalle(usuario, path[len("/incidentes/"):])
                if path == "/equipos":
                    return self._equipos(usuario)
                if path == "/equipos/nuevo":
                    return self._formulario_equipo(usuario)
                if path == "/indicadores":
                    return self._indicadores(usuario)
                if path == "/reporte":
                    return self._reporte(usuario, ruta.query)
                if path == "/reporte.docx":
                    return self._reporte_word(usuario, ruta.query)
                if path == "/bitacora":
                    return self._bitacora(usuario)
                return self._html(
                    self._pagina("No encontrada", "<p>La página solicitada no existe.</p>", usuario),
                    404,
                )
            except PermisoDenegadoError as error:
                return self._error(usuario, str(error), 403)
            except SIGISError as error:
                return self._error(usuario, str(error), 400)
            except (ValueError, KeyError) as error:
                return self._error(usuario, str(error), 400)

        def do_POST(self):
            usuario = self._usuario()
            try:
                datos = self._datos_formulario()
                if self.path == "/entrar":
                    if usuario is not None:
                        return self._redirect("/panel")
                    try:
                        cuenta = estado["auth"].iniciar_sesion(
                            datos.get("usuario", ""), datos.get("clave", "")
                        )
                    except SIGISError as error:
                        return self._html(login_html(str(error)), 401)
                    token = secrets.token_urlsafe(32)
                    csrf = secrets.token_urlsafe(24)
                    with estado["lock"]:
                        estado["sesiones"][token] = (cuenta.nombre_usuario, csrf)
                    self.send_response(303)
                    self.send_header("Set-Cookie", f"sigis_session={token}; HttpOnly; SameSite=Lax; Path=/")
                    self.send_header("Location", "/panel")
                    self.end_headers()
                    return
                if usuario is None:
                    return self._redirect("/login")
                if not self._csrf_valido(datos):
                    return self._error(usuario, "Formulario expirado. Recargue e intente otra vez.", 403)
                if self.path == "/salir":
                    token = self._token()
                    with estado["lock"]:
                        estado["sesiones"].pop(token, None)
                    self.send_response(303)
                    self.send_header("Set-Cookie", "sigis_session=; Max-Age=0; HttpOnly; Path=/")
                    self.send_header("Location", "/login")
                    self.end_headers()
                    return
                if self.path == "/incidentes/nuevo":
                    return self._crear_incidente(usuario, datos)
                if self.path == "/equipos/nuevo":
                    estado["equipos"].registrar(
                        datos.get("codigo", ""), datos.get("area", ""),
                        datos.get("responsable", ""), usuario,
                    )
                    return self._redirect("/equipos")
                if self.path.startswith("/equipos/") and self.path.endswith("/estado"):
                    codigo = unquote(self.path.split("/")[2])
                    estado["equipos"].cambiar_estado(codigo, datos.get("estado", ""), usuario)
                    return self._redirect("/equipos")
                if self.path.startswith("/incidentes/") and self.path.endswith("/acciones"):
                    codigo = unquote(self.path.split("/")[2])
                    return self._accion_incidente(usuario, codigo, datos)
                return self._error(usuario, "Operación no encontrada.", 404)
            except PermisoDenegadoError as error:
                return self._error(usuario, str(error), 403)
            except SIGISError as error:
                return self._error(usuario, str(error), 400)
            except (ValueError, KeyError) as error:
                return self._error(usuario, str(error), 400)
            except (UnicodeDecodeError, OSError) as error:
                return self._error(usuario, f"No se pudo procesar la solicitud: {error}", 400)

        def _usuario(self):
            token = self._token()
            with estado["lock"]:
                sesion = estado["sesiones"].get(token)
            if sesion is None:
                return None
            return estado["repo"].usuarios.get(sesion[0])

        def _token(self):
            for parte in self.headers.get("Cookie", "").split(";"):
                clave, _, valor = parte.strip().partition("=")
                if clave == "sigis_session":
                    return valor
            return ""

        def _csrf_valido(self, datos):
            with estado["lock"]:
                sesion = estado["sesiones"].get(self._token())
            return sesion is not None and secrets.compare_digest(
                sesion[1], datos.get("csrf", "")
            )

        def _datos_formulario(self):
            try:
                longitud = int(self.headers.get("Content-Length", "0"))
            except ValueError as error:
                raise ValueError("Longitud de formulario inválida.") from error
            if longitud < 0 or longitud > MAX_BODY_BYTES:
                raise ValueError("El formulario supera el tamaño permitido.")
            contenido = self.rfile.read(longitud)
            decodificado = contenido.decode("utf-8")
            return {k: v[-1] for k, v in parse_qs(decodificado).items()}

        def _csrf(self):
            with estado["lock"]:
                sesion = estado["sesiones"].get(self._token())
            token = sesion[1] if sesion else ""
            return f'<input type="hidden" name="csrf" value="{escape(token, quote=True)}">'

        def _html(self, contenido, status=200):
            datos = contenido.encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(datos)))
            self.end_headers()
            self.wfile.write(datos)

        def _pagina(self, titulo, contenido, usuario):
            return pagina(titulo, contenido, usuario, csrf=self._csrf_value())

        def _texto(self, texto, tipo="text/plain; charset=utf-8", nombre=None):
            datos = texto if isinstance(texto, bytes) else texto.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", tipo)
            if nombre:
                self.send_header("Content-Disposition", f'attachment; filename="{nombre}"')
            self.send_header("Content-Length", str(len(datos)))
            self.end_headers()
            self.wfile.write(datos)

        def _redirect(self, destino):
            self.send_response(303)
            self.send_header("Location", destino)
            self.end_headers()

        def _error(self, usuario, mensaje, estado_http):
            return self._html(
                self._pagina("No se pudo completar la acción",
                       f'<p class="error">{escape(mensaje)}</p><a href="/incidentes">Volver</a>',
                       usuario),
                estado_http,
            )

        def _panel(self, usuario):
            total = len(estado["repo"].incidentes)
            abiertos = sum(1 for item in estado["repo"].incidentes.values() if item.esta_abierto())
            ultimo = max(
                estado["repo"].incidentes.values(),
                key=lambda item: item.fecha_deteccion,
                default=None,
            )
            ultimo_html = (
                f'<p>Último caso: <a href="/incidentes/{quote(ultimo.codigo)}">'
                f'{escape(ultimo.codigo)} — {escape(ultimo.tipo_amenaza)}</a></p>'
                if ultimo else "<p>No hay incidentes registrados.</p>"
            )
            contenido = (
                f'<div class="cards"><section><h2>{total}</h2><p>Alertas registradas</p></section>'
                f'<section><h2>{abiertos}</h2><p>Casos abiertos</p></section></div>{ultimo_html}'
            )
            pendientes = estado["incidentes"].alerta_plazo.pendientes()
            if pendientes:
                avisos = "".join(
                    f'<li><a href="/incidentes/{quote(item.codigo)}">{escape(item.codigo)}</a>: '
                    + (f'plazo vencido hace {abs(horas):.1f} h' if horas < 0 else f'vence en {horas:.1f} h')
                    + '</li>'
                    for item, horas in pendientes
                )
                contenido += f'<section class="aviso"><h2>Notificaciones ANPD pendientes</h2><ul>{avisos}</ul></section>'
            return self._html(self._pagina("Panel", contenido, usuario))

        def _incidentes_filtrados(self):
            query = parse_qs(urlsplit(self.path).query)
            valores = {clave: query.get(clave, [""])[-1] for clave in (
                "q", "estado", "origen", "criticidad", "desde", "hasta",
            )}
            desde = datetime.strptime(valores["desde"], "%Y-%m-%d").date() if valores["desde"] else None
            hasta = datetime.strptime(valores["hasta"], "%Y-%m-%d").date() if valores["hasta"] else None
            if desde and hasta and desde > hasta:
                raise ValueError("La fecha inicial no puede ser posterior a la fecha final.")
            items = estado["incidentes"].listar(
                estado=EstadoIncidente(valores["estado"]) if valores["estado"] else None,
                origen=OrigenAlerta(valores["origen"]) if valores["origen"] else None,
                criticidad=Criticidad(valores["criticidad"]) if valores["criticidad"] else None,
            )
            texto = valores["q"].strip().casefold()
            items = [item for item in items if (
                (not texto or texto in " ".join((item.codigo, item.equipo, item.tipo_amenaza, item.descripcion)).casefold())
                and (desde is None or item.fecha_deteccion.date() >= desde)
                and (hasta is None or item.fecha_deteccion.date() <= hasta)
            )]
            return items, valores

        def _incidentes(self, usuario):
            items, valores = self._incidentes_filtrados()
            rows = []
            for item in items:
                rows.append(
                    f'<tr><td><a href="/incidentes/{quote(item.codigo)}">'
                    f'{escape(item.codigo)}</a></td><td>{item.fecha_deteccion:%Y-%m-%d %H:%M}</td>'
                    f'<td>{escape(item.equipo)}</td><td>{escape(item.tipo_amenaza)}</td>'
                    f'<td>{escape(item.estado.value)}</td><td>'
                    f'{escape(item.criticidad.value if item.criticidad else "Sin clasificar")}</td></tr>'
                )
            def selector(nombre, titulo, opciones):
                contenido = '<option value="">Todos</option>' + "".join(
                    f'<option value="{escape(valor.value, quote=True)}"'
                    f'{" selected" if valores[nombre] == valor.value else ""}>{escape(valor.value)}</option>'
                    for valor in opciones
                )
                return f'<label>{titulo}<select name="{nombre}">{contenido}</select></label>'

            parametros = urlencode({clave: valor for clave, valor in valores.items() if valor})
            filtros = (
                '<form class="filtros" method="get" action="/incidentes">'
                f'<label>Buscar<input name="q" value="{escape(valores["q"], quote=True)}"></label>'
                + selector("estado", "Estado", EstadoIncidente)
                + selector("origen", "Origen", OrigenAlerta)
                + selector("criticidad", "Criticidad", Criticidad)
                + f'<label>Detección desde<input type="date" name="desde" value="{escape(valores["desde"], quote=True)}"></label>'
                + f'<label>Detección hasta<input type="date" name="hasta" value="{escape(valores["hasta"], quote=True)}"></label>'
                + '<div class="comandos"><button>Filtrar</button><a href="/incidentes">Limpiar</a></div></form>'
                + f'<p class="comandos"><a class="button" href="/incidentes.csv?{escape(parametros, quote=True)}">Descargar CSV</a>'
                + '<a class="button" href="/incidentes/nuevo">Registrar incidente</a></p>'
                + f'<p>{len(items)} incidentes</p>'
            )
            tabla = (
                '<div class="tabla-scroll" tabindex="0" role="region" aria-label="Incidentes"><table><thead><tr><th>Código</th><th>Detección</th><th>Equipo</th>'
                "<th>Amenaza</th><th>Estado</th><th>Criticidad</th></tr></thead><tbody>"
                + ("".join(rows) or '<tr><td colspan="6">No hay incidentes con estos filtros.</td></tr>')
                + "</tbody></table></div>"
            )
            return self._html(self._pagina("Incidentes", filtros + tabla, usuario))

        def _formulario_incidente(self, usuario, error=""):
            if not usuario.puede("registrar"):
                raise SIGISError("No tiene autorización para registrar incidentes.")
            opciones = "".join(
                f'<option value="{escape(origen.value, quote=True)}">{escape(origen.value)}</option>'
                for origen in OrigenAlerta
            )
            equipos_html = "".join(
                f'<option value="{escape(e.codigo, quote=True)}">{escape(e.codigo)} — '
                f'{escape(e.area)}</option>'
                for e in estado["equipos"].listar()
                if e.estado != EstadoEquipo.INHABILITADO
            )
            contenido = f"""{f'<p class="error">{escape(error)}</p>' if error else ''}
<form class="card" method="post" action="/incidentes/nuevo">{self._csrf()}
<label>Origen</label><select name="origen" required>{opciones}</select>
<label>Equipo</label><select name="equipo" required>{equipos_html}</select>
<label>Tipo de amenaza</label><input name="amenaza" required>
<label>Descripción</label><textarea name="descripcion" required></textarea>
<label>Fecha/hora de ocurrencia</label><input type="datetime-local" name="ocurrencia" required>
<label>Fecha/hora de detección</label><input type="datetime-local" name="deteccion" required>
<label><input style="width:auto" type="checkbox" name="datos_personales" value="si">
Involucra datos personales</label><button>Registrar</button>
<a href="/incidentes">Cancelar</a></form>"""
            return self._html(self._pagina("Registrar incidente", contenido, usuario))

        def _crear_incidente(self, usuario, datos):
            ocurrencia = datetime.fromisoformat(datos.get("ocurrencia", ""))
            deteccion = datetime.fromisoformat(datos.get("deteccion", ""))
            item = estado["incidentes"].registrar(
                datos.get("origen", ""),
                datos.get("equipo", ""),
                datos.get("amenaza", ""),
                datos.get("descripcion", ""),
                ocurrencia,
                deteccion,
                datos.get("datos_personales") == "si",
                usuario,
            )
            return self._redirect(f"/incidentes/{quote(item.codigo)}")

        def _detalle(self, usuario, codigo):
            item = estado["incidentes"].buscar(codigo)
            criticidad = item.criticidad.value if item.criticidad else "Sin clasificar"
            contenido = f"""<section><p><b>Estado:</b> {escape(item.estado.value)} ·
<b>Criticidad:</b> {escape(criticidad)}</p><p><b>Equipo:</b> {escape(item.equipo)} ·
<b>Origen:</b> {escape(item.origen.value)}</p><p><b>Ocurrencia:</b> {item.fecha_ocurrencia:%Y-%m-%d %H:%M} ·
<b>Detección:</b> {item.fecha_deteccion:%Y-%m-%d %H:%M}</p>
<p>{escape(item.descripcion)}</p>
<p><b>Asignado a:</b> {escape(item.analista_asignado or "Sin asignar")}</p>
<p><b>Causa raíz:</b> {escape(item.causa_raiz or "Pendiente")}</p>
<p><b>Lección aprendida:</b> {escape(item.leccion_aprendida or "Sin registrar")}</p>
<p><b>Motivo de falso positivo:</b> {escape(item.motivo_falso_positivo or "No aplica")}</p></section>"""

            def formulario(accion, titulo, campos=""):
                return (
                    f'<form class="card" method="post" action="/incidentes/{quote(codigo, safe="")}/acciones">'
                    f'{self._csrf()}<input type="hidden" name="accion" value="{accion}">'
                    f'<h3>{titulo}</h3>{campos}<button>{titulo}</button></form>'
                )

            if item.involucra_datos_personales:
                limite = item.fecha_limite_notificacion()
                notificacion = "Notificada" if item.notificado_anpd else "Pendiente"
                contenido += (
                    f'<section><h2>Notificación ANPD</h2><p>{notificacion} · '
                    f'Fecha límite: {limite:%Y-%m-%d %H:%M}</p></section>'
                )
                if not item.notificado_anpd and usuario.puede("atender"):
                    contenido += formulario("notificar", "Registrar notificación ANPD")
            if item.esta_abierto():
                acciones = []
                if usuario.puede("atender"):
                    acciones.append(formulario(
                        "clasificar", "Clasificar",
                        '<label>Impacto (1–3)<input type="number" name="impacto" min="1" max="3" required></label>'
                        '<label>Urgencia (1–3)<input type="number" name="urgencia" min="1" max="3" required></label>',
                    ))
                if usuario.puede("contener"):
                    acciones.append(formulario("contener", "Contener"))
                if usuario.puede("escalar"):
                    acciones.append(formulario(
                        "escalar", "Escalar",
                        '<label>Motivo de escalamiento<input name="motivo" required></label>',
                    ))
                if usuario.puede("falso_positivo"):
                    acciones.append(formulario(
                        "falso", "Marcar falso positivo",
                        '<label>Motivo de falso positivo<input name="motivo" required></label>',
                    ))
                if usuario.puede("cerrar"):
                    acciones.append(formulario(
                        "cerrar", "Cerrar incidente",
                        '<label>Causa raíz<textarea name="causa" required></textarea></label>'
                        '<label>Lección aprendida (opcional)<textarea name="leccion"></textarea></label>',
                    ))
                if usuario.puede("asignar"):
                    options = "".join(
                        f'<option value="{escape(u.nombre_usuario, quote=True)}">'
                        f'{escape(u.nombre_completo)}</option>'
                        for u in estado["repo"].usuarios.values()
                        if isinstance(u, Analista)
                    )
                    acciones.append(formulario(
                        "asignar", "Asignar",
                        f'<label>Analista<select name="analista" required>{options}</select></label>',
                    ))
                contenido += '<div class="acciones">' + "".join(acciones) + '</div>'
            historial = "".join(
                f'<tr><td>{accion.momento:%Y-%m-%d %H:%M}</td>'
                f'<td>{escape(accion.usuario)}</td><td>{escape(accion.descripcion)}</td></tr>'
                for accion in reversed(estado["repo"].bitacora)
                if accion.codigo_incidente == codigo
            )
            contenido += (
                '<h2>Historial del incidente</h2><div class="tabla-scroll" tabindex="0" role="region" aria-label="Historial"><table><thead><tr><th>Fecha</th>'
                '<th>Usuario</th><th>Acción</th></tr></thead><tbody>'
                + (historial or '<tr><td colspan="3">Sin acciones registradas.</td></tr>')
                + '</tbody></table></div><p><a href="/incidentes">Volver a incidentes</a></p>'
            )
            return self._html(self._pagina(f"Incidente {codigo}", contenido, usuario))

        def _csrf_value(self):
            with estado["lock"]:
                sesion = estado["sesiones"].get(self._token())
            return sesion[1] if sesion else ""

        def _accion_incidente(self, usuario, codigo, datos):
            servicio = estado["incidentes"]
            accion = datos.get("accion", "")
            if accion == "clasificar":
                servicio.clasificar(codigo, int(datos.get("impacto", "")),
                                    int(datos.get("urgencia", "")), usuario)
            elif accion == "contener":
                servicio.contener(codigo, usuario=usuario)
            elif accion == "escalar":
                servicio.escalar(codigo, datos.get("motivo", ""), usuario)
            elif accion == "falso":
                servicio.marcar_falso_positivo(codigo, datos.get("motivo", ""), usuario)
            elif accion == "cerrar":
                servicio.cerrar(codigo, datos.get("causa", ""),
                                datos.get("leccion") or None, usuario)
            elif accion == "asignar":
                servicio.asignar(codigo, datos.get("analista", ""), usuario)
            elif accion == "notificar":
                servicio.notificar_anpd(codigo, usuario)
            else:
                return self._error(usuario, "Acción desconocida.", 400)
            return self._redirect(f"/incidentes/{quote(codigo)}")

        def _equipos(self, usuario):
            administrar = usuario.puede("equipos_admin")
            rows = []
            for equipo in estado["equipos"].listar():
                accion = ""
                if administrar:
                    opciones = "".join(
                        f'<option value="{escape(valor.value, quote=True)}"'
                        f'{" selected" if valor == equipo.estado else ""}>{escape(valor.value)}</option>'
                        for valor in EstadoEquipo
                    )
                    accion = (
                        f'<td><form class="inline" method="post" action="/equipos/{quote(equipo.codigo, safe="")}/estado">'
                        f'{self._csrf()}<select name="estado" aria-label="Estado de {escape(equipo.codigo, quote=True)}">'
                        f'{opciones}</select><button>Actualizar estado</button></form></td>'
                    )
                rows.append(
                    f'<tr><td>{escape(equipo.codigo)}</td><td>{escape(equipo.area)}</td>'
                    f'<td>{escape(equipo.responsable)}</td><td>{escape(equipo.estado.value)}</td>{accion}</tr>'
                )
            enlace = '<p><a class="button" href="/equipos/nuevo">Registrar equipo</a></p>' if administrar else ""
            columna = '<th>Administración</th>' if administrar else ""
            return self._html(self._pagina(
                "Equipos",
                enlace + '<div class="tabla-scroll" tabindex="0" role="region" aria-label="Equipos"><table><thead><tr><th>Código</th><th>Área</th><th>Responsable</th>'
                f"<th>Estado</th>{columna}</tr></thead><tbody>{''.join(rows)}</tbody></table></div>",
                usuario,
            ))

        def _formulario_equipo(self, usuario):
            if not usuario.puede("equipos_admin"):
                raise PermisoDenegadoError("Solo jefatura puede administrar equipos.")
            contenido = f'''<form class="card" method="post" action="/equipos/nuevo">{self._csrf()}
<label>Código<input name="codigo" required></label>
<label>Área<input name="area" required></label>
<label>Responsable<input name="responsable" required></label>
<button>Registrar equipo</button><a href="/equipos">Cancelar</a></form>'''
            return self._html(self._pagina("Registrar equipo", contenido, usuario))

        def _indicadores(self, usuario):
            ahora = datetime.now()
            desde = datetime(ahora.year, ahora.month, 1)
            datos = estado["incidentes"].calculadora.resumen(desde, ahora)
            contenido = f"""<section><p>Período: {desde:%d/%m/%Y} — {ahora:%d/%m/%Y}</p>
<p>Alertas: {datos['total_alertas']} · Confirmados: {datos['confirmados']} ·
Falsos positivos: {datos['falsos_positivos']}</p><p>MTTD: {datos['mttd']} h ·
MTTR: {datos['mttr']} h · Cumplimiento objetivo: {datos['cumplimiento']} % ·
Tasa de falsos positivos: {datos['tasa_fp']} % · Reincidencia: {datos['reincidencia']} %</p>
<p>Indisponibilidad: {datos['horas_indisponibilidad']} h ·
Costo estimado: S/ {datos['costo_indisponibilidad']:.2f}</p></section>"""
            return self._html(self._pagina("Indicadores", contenido, usuario))

        def _reporte(self, usuario, query):
            anio, mes = self._periodo(query)
            texto = estado["incidentes"].reporte.generar(anio, mes)
            form = f"""<form method="get" action="/reporte">
<label>Año</label><input type="number" name="anio" value="{anio}" required>
<label>Mes</label><input type="number" name="mes" min="1" max="12" value="{mes}" required>
<button>Generar</button><a class="button" href="/reporte.docx?anio={anio}&mes={mes}">Descargar Word</a>
</form><pre>{escape(texto)}</pre>"""
            return self._html(self._pagina("Reporte mensual", form, usuario))

        def _reporte_word(self, usuario, query):
            anio, mes = self._periodo(query)
            contenido = estado["incidentes"].reporte_word.generar(anio, mes)
            self._texto(
                contenido,
                "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                f"reporte_{anio}_{mes:02d}.docx",
            )

        @staticmethod
        def _periodo(query):
            valores = parse_qs(query)
            ahora = datetime.now()
            anio = int(valores.get("anio", [ahora.year])[-1])
            mes = int(valores.get("mes", [ahora.month])[-1])
            if anio < 1 or anio > 9998 or mes < 1 or mes > 12:
                raise ValueError("El período debe incluir un año válido y un mes entre 1 y 12.")
            return anio, mes

        def _csv(self, usuario):
            salida = io.StringIO(newline="")
            escritor = csv.writer(salida)
            escritor.writerow([
                "Código", "Origen", "Equipo", "Amenaza", "Detección", "Estado", "Criticidad",
            ])
            items, _ = self._incidentes_filtrados()
            for item in items:
                escritor.writerow([
                    item.codigo, item.origen.value, item.equipo, item.tipo_amenaza,
                    item.fecha_deteccion.isoformat(), item.estado.value,
                    item.criticidad.value if item.criticidad else "",
                ])
            self._texto(
                "\ufeff" + salida.getvalue(),
                "text/csv; charset=utf-8",
                "incidentes.csv",
            )

        def _bitacora(self, usuario):
            if not usuario.puede("bitacora"):
                return self._error(usuario, "Acceso exclusivo para jefatura.", 403)
            rows = "".join(
                f"<tr><td>{a.momento:%Y-%m-%d %H:%M:%S}</td><td>{escape(a.usuario)}</td>"
                f"<td>{escape(a.descripcion)}</td><td>{escape(a.codigo_incidente or '')}</td></tr>"
                for a in reversed(estado["repo"].bitacora)
            )
            return self._html(self._pagina(
                "Bitácora de auditoría",
                '<div class="tabla-scroll" tabindex="0" role="region" aria-label="Bitácora"><table><thead><tr><th>Fecha</th><th>Usuario</th><th>Acción</th>'
                f"<th>Incidente</th></tr></thead><tbody>{rows}</tbody></table></div>",
                usuario,
            ))

    return ManejadorSIGIS


def ejecutar(puerto=8000):
    """Inicializa y sirve SIGIS solo en la interfaz de loopback local."""
    estado = crear_aplicacion()
    servidor = ThreadingHTTPServer(("127.0.0.1", puerto), crear_manejador(estado))
    print(f"SIGIS disponible en http://127.0.0.1:{servidor.server_port}")
    webbrowser.open(f"http://127.0.0.1:{servidor.server_port}")
    try:
        servidor.serve_forever()
    finally:
        servidor.server_close()
