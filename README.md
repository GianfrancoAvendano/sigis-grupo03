# SIGIS — Sistema de Gestión de Incidentes de Seguridad

Proyecto académico para IS275 — Fundamentos de Programación 2. El sistema
incluye interfaz web y de consola sobre un mismo núcleo de servicios, una
persistencia JSON local y pruebas automatizadas de reglas de negocio.

## Requisitos y ejecución

- Python 3.8 o superior.
- No se requieren paquetes externos.

Iniciar la interfaz web:

```powershell
python web.py
```

La web escucha únicamente en `127.0.0.1:8000` y abre el navegador. Para elegir
otro puerto, por ejemplo el 8080:

```powershell
python web.py 8080
```

Detén el servidor con `Ctrl+C`. La aplicación de consola se inicia con:

```powershell
python main.py
```

Ejecuta estos comandos desde la carpeta del proyecto. En VS Code, abre
`main.py` o `web.py` antes de usar **Ejecutar archivo de Python**. Los archivos
de `sigis/`, como `almacen.py`, son módulos internos y no se ejecutan
directamente: sus imports relativos necesitan el contexto del paquete.

### Cuentas de demostración

| Usuario | Contraseña | Perfil |
|---|---|---|
| `jefe_ti` | `jefe123` | Jefatura; acceso a la bitácora y administración |
| `analista1` | `clave123` | Analista; registro y atención de incidentes |
| `analista2` | `clave456` | Analista |
| `analista3` | `clave789` | Analista |
| `auditor` | `auditor123` | Analista |

Tres intentos de contraseña incorrecta bloquean la cuenta. Las claves se
almacenan como resúmenes SHA-256; no se guarda la contraseña en claro.

## Pruebas

Ejecuta las 64 pruebas de negocio y las 2 pruebas de inicio con:

```powershell
python pruebas_negocio.py
```

La suite cubre autenticación y permisos, Factory y Strategy, combinaciones de
criticidad, validaciones de incidentes, transición de estados, equipos,
bitácora, notificación legal, indicadores, persistencia y generación DOCX.
La documentación de resultados está en [QA_VALIDACION.md](QA_VALIDACION.md).

Las 13 pruebas HTTP de pantallas se ejecutan por separado o junto con las
anteriores. Siempre usan un servidor local y archivos temporales:

```powershell
python pruebas_web.py
python -m unittest pruebas_negocio pruebas_web -v
```

## Funcionalidades disponibles

- Panel con total de alertas, casos abiertos, último incidente y notificaciones
  ANPD pendientes próximas a vencer o vencidas.
- Listado con filtros combinables por texto, estado, origen, criticidad y fechas
  de detección; exportación CSV del mismo resultado filtrado.
- Registro de incidentes de Wazuh, Sophos o reportes de usuarios.
- Clasificación por impacto y urgencia; contención, escalamiento, falso positivo
  y cierre con causa raíz.
- Asignación de incidentes y administración de equipos, con comprobaciones de
  autorización realizadas también en la capa de servicios.
- Alta de equipos y cambio entre operativo, cuarentena, inhabilitado y
  mantenimiento, disponibles solo para jefatura.
- Detalle con historial del incidente, lección aprendida, motivo de descarte y
  estado de notificación ANPD; formularios independientes para cada acción.
- Indicadores mensuales y reporte mensual en texto o Word.
- Bitácora de auditoría solo visible para el perfil de jefatura.
- Aviso de plazo legal de 48 horas para incidentes que involucren datos
  personales.
- Persistencia en `datos/sigis.json` y copia diaria de respaldo. `datos/` es
  estado local y está excluido del control de versiones.

La lección aprendida se almacena cuando se proporciona, pero es opcional; la
regla de cierre exige causa raíz. La regla de equipo inhabilitado impide
registrar nuevos incidentes en ese equipo, no establece un bloqueo adicional
para cerrar incidentes existentes.

## Estructura

```text
main.py                    Punto de entrada de consola
web.py                     Punto de entrada web
pruebas_negocio.py          64 escenarios de negocio y 2 pruebas de inicio
pruebas_web.py              13 pruebas HTTP con datos temporales
sigis/
  almacen.py               Serialización y persistencia JSON
  consola.py               Validación de entradas de terminal
  datos_demo.py            Cuentas, equipos e incidentes ficticios
  enums.py                 Estados, criticidad y parámetros
  excepciones.py           Excepciones de dominio
  indicadores.py           Indicadores y reporte mensual en texto
  menus.py                 Interfaz de consola
  modelo.py                Usuarios, equipos e incidentes
  patrones.py              Singleton, Factory, Strategy y Observer
  reporte_docx.py          Generación de reportes Word sin dependencias
  servicios.py             Autenticación y reglas de aplicación
  web/
    plantillas.py          Estructura y estilo de páginas HTML
    servidor.py            Rutas HTTP, formularios y sesiones locales
```

### Pantallas web

| Pantalla | Ruta | Acceso |
|---|---|---|
| Inicio de sesión | `/login` | Sin sesión |
| Panel y alertas legales | `/panel` | Usuario autenticado |
| Listado, filtros y CSV | `/incidentes`, `/incidentes.csv` | Usuario autenticado |
| Registro de incidente | `/incidentes/nuevo` | Permiso de registro |
| Detalle, atención e historial | `/incidentes/<codigo>` | Acciones según perfil y estado |
| Inventario de equipos | `/equipos` | Usuario autenticado |
| Alta y cambio de estado de equipos | `/equipos/nuevo`, formulario en `/equipos` | Jefatura |
| Indicadores | `/indicadores` | Usuario autenticado |
| Reporte mensual y Word | `/reporte`, `/reporte.docx` | Usuario autenticado |
| Bitácora de auditoría | `/bitacora` | Jefatura |

### Organización por responsabilidad

La interfaz HTTP y su presentación están en `sigis/web/`. No corresponde
mover los demás módulos a esa carpeta:

| Ubicación | Responsabilidad y motivo |
|---|---|
| `sigis/web/servidor.py` | Rutas, sesiones, protección CSRF y formularios HTTP. |
| `sigis/web/plantillas.py` | Documento HTML, navegación y estilos adaptables. |
| `web.py` | Lanzador web en la raíz; permite `python web.py` sin ejecutar módulos internos. |
| `main.py`, `sigis/menus.py`, `sigis/consola.py` | Interfaz de terminal alternativa; no son componentes web. |
| `sigis/servicios.py`, `modelo.py`, `enums.py`, `excepciones.py`, `patrones.py` | Reglas de negocio y dominio compartidos por consola y web. |
| `sigis/almacen.py`, `datos_demo.py` | Persistencia y carga de demostración compartidas. |
| `sigis/indicadores.py`, `reporte_docx.py` | Cálculos e informes independientes de la interfaz. |
| `pruebas_negocio.py`, `pruebas_web.py`, `datos/` | Verificación y estado local; no forman parte de la presentación web. |

Se conserva la consola sin duplicar reglas de negocio en la web. Las tablas
web tienen desplazamiento interno en pantallas estrechas; los formularios
incluyen validaciones y las operaciones autenticadas usan tokens CSRF.

## Datos de demostración

Los registros generados por `datos_demo.py` son ficticios. Se cargan en el
primer inicio y se conservan después en `datos/`. Para volver a cargar la
demostración desde cero, detén el programa y elimina únicamente la carpeta
local `datos/`.
