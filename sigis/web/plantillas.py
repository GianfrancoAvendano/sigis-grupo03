"""Funciones pequeñas para generar las páginas HTML de SIGIS."""

from html import escape


def pagina(titulo, contenido, usuario=None):
    menu = ""
    if usuario is not None:
        enlaces = [
            ("Panel", "/panel"),
            ("Incidentes", "/incidentes"),
            ("Equipos", "/equipos"),
            ("Indicadores", "/indicadores"),
            ("Reporte mensual", "/reporte"),
        ]
        if usuario.puede("bitacora"):
            enlaces.append(("Bitácora", "/bitacora"))
        nav = " · ".join(
            f'<a href="{url}">{escape(nombre)}</a>' for nombre, url in enlaces
        )
        menu = (
            f'<header><strong>SIGIS</strong><nav>{nav}</nav>'
            f'<span>{escape(usuario.nombre_completo)}</span>'
            f'<form class="inline" method="post" action="/salir">'
            f'<button>Salir</button></form></header>'
        )
    return f"""<!doctype html>
<html lang="es"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{escape(titulo)} · SIGIS</title>
<style>
body{{margin:0;background:#f4f6f8;color:#182536;font:16px system-ui,sans-serif}}
header{{background:#14233d;color:white;padding:1rem 2rem;display:flex;gap:1.5rem;
align-items:center;flex-wrap:wrap}}nav{{display:flex;gap:1rem;flex:1}}
header a{{color:white}}main{{max-width:1100px;margin:2rem auto;padding:0 1rem}}
section,form.card{{background:white;border:1px solid #dce2e8;border-radius:8px;
padding:1rem;margin:1rem 0}}table{{width:100%;border-collapse:collapse;background:white}}
th,td{{padding:.7rem;border-bottom:1px solid #dce2e8;text-align:left}}
th{{background:#eaf0f5}}label{{display:block;margin:.7rem 0 .25rem}}
input,select,textarea{{padding:.6rem;width:min(100%,36rem);box-sizing:border-box}}
button,.button{{display:inline-block;background:#174f80;color:white;border:0;
border-radius:4px;padding:.65rem 1rem;margin:.5rem .25rem;text-decoration:none;
cursor:pointer}}.inline{{display:inline}}.error{{color:#a32020}}.cards{{display:flex;
gap:1rem;flex-wrap:wrap}}.cards section{{min-width:10rem;flex:1}}
</style></head><body>{menu}<main><h1>{escape(titulo)}</h1>{contenido}</main></body></html>"""


def login(mensaje=""):
    error = f'<p class="error">{escape(mensaje)}</p>' if mensaje else ""
    return pagina(
        "Iniciar sesión",
        f"""{error}<form class="card" method="post" action="/entrar">
<label for="usuario">Usuario</label><input id="usuario" name="usuario" required autofocus>
<label for="clave">Contraseña</label><input id="clave" name="clave" type="password" required>
<button>Ingresar</button></form>""",
    )
