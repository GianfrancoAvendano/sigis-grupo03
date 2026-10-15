"""Funciones pequeñas para generar las páginas HTML de SIGIS."""

from html import escape


def pagina(titulo, contenido, usuario=None, csrf=""):
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
            f'<input type="hidden" name="csrf" value="{escape(csrf, quote=True)}">'
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
*{{box-sizing:border-box}}nav{{flex-wrap:wrap}}main{{min-width:0}}
header form{{margin:0}}h1{{font-size:1.8rem;overflow-wrap:anywhere}}
h2{{font-size:1.25rem}}h3{{font-size:1.05rem;margin-top:0}}
input,select,textarea{{display:block;max-width:100%;font:inherit}}
input[type=checkbox]{{display:inline-block}}button{{font:inherit}}
label input,label select,label textarea{{margin-top:.3rem}}
section{{background:transparent;border:0;border-radius:0;padding:1rem 0}}
.cards section{{border-bottom:3px solid #174f80}}
.tabla-scroll{{max-width:100%;overflow-x:auto;border:1px solid #dce2e8}}
.tabla-scroll table{{min-width:660px}}th,td{{vertical-align:top}}
td:first-child,td:nth-child(2){{white-space:nowrap}}
.filtros,.acciones{{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,250px),1fr));gap:1rem}}
.acciones form.card{{margin:0;border:0;border-top:1px solid #dce2e8;border-radius:0;background:transparent;padding:1rem 0}}
.comandos{{display:flex;gap:.75rem;align-items:center;flex-wrap:wrap}}
.comandos .button{{margin:0}}.aviso{{border-left:4px solid #bb7a12;padding-left:1rem}}
pre{{white-space:pre-wrap;overflow-wrap:anywhere;background:white;padding:1rem;border:1px solid #dce2e8}}
:focus-visible{{outline:3px solid #bd7c16;outline-offset:3px}}
@media(max-width:640px){{header{{padding:1rem;gap:.75rem}}nav{{flex-basis:100%;gap:.75rem}}
main{{margin:1rem auto}}h1{{font-size:1.5rem}}.tabla-scroll select{{min-width:180px}}}}
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
