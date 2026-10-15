# Validación QA de SIGIS

**Fecha de ejecución:** 14 de octubre de 2026
**Alcance:** suite de negocio reconstruida y rutas web implementadas en esta rama.
**Entorno:** Windows, Python 3.15.0; solo biblioteca estándar.

## Contexto

Al iniciar esta tarea, el repositorio y sus ramas locales contenían únicamente
los puntos de entrada, persistencia, indicadores, patrones y reporte DOCX. No
existían `pruebas_negocio.py`, el modelo, los enums, las excepciones, los
servicios ni `sigis/web/`. Por ello, las pruebas descritas aquí son una suite
nueva de 64 escenarios que acompaña a la implementación reconstruida; no son
una recuperación ni una repetición de casos preexistentes.

## Pruebas automatizadas

Comando ejecutado:

```powershell
python pruebas_negocio.py
```

| Métrica | Resultado |
|---|---:|
| Pruebas ejecutadas | 64 |
| Exitosas | 64 |
| Fallidas | 0 |
| Errores/excepciones inesperadas | 0 |

También se ejecutaron `python -m compileall -q main.py web.py
pruebas_negocio.py sigis` y `git diff --check`; ambos finalizaron correctamente.
El análisis de problemas del workspace no reportó errores.

### Cobertura incluida

- Hash y verificación de contraseña, autenticación y bloqueo por tres intentos.
- Autorización de analistas y jefatura, incluidas operaciones de equipos y
  Bitácora.
- Factory Method para alertas Wazuh, Sophos y reporte de usuario.
- Las nueve combinaciones de impacto/urgencia, límites inválidos y Strategy
  alternativo.
- Fechas y campos obligatorios al registrar incidentes; equipo desconocido o
  inhabilitado; correlativo y filtrado.
- Búsqueda, estado e indisponibilidad de equipos.
- Asignación, clasificación, contención, escalamiento, falso positivo y cierre.
- Inmutabilidad de acciones de auditoría y plazo legal de 48 horas.
- MTTD, MTTR, tasa de falsos positivos, resumen mensual, round-trip JSON y
  estructura ZIP de un DOCX.

**Casos negativos y excepciones probados:** fechas inconsistentes y campos
vacíos (`DatoInvalidoError`), entidades inexistentes (`NoEncontradoError`),
estado no permitido (`EstadoInvalidoError`), permisos insuficientes
(`PermisoDenegadoError`) y credenciales incorrectas/cuenta bloqueada
(`AutenticacionError`).

**Ejemplo para explicar oralmente:** la prueba `registro_rechaza_detección_anterior`
intenta guardar un incidente cuya detección antecede a la ocurrencia. El
servicio rechaza la entrada antes de incorporarla al repositorio, porque una
detección no puede ocurrir antes del evento que detecta.

## Validación de interfaz y rutas

El servidor se inició con `python web.py 8743`, respondió en
`http://127.0.0.1:8743` y se verificó la pantalla de inicio de sesión en el
navegador integrado. La web escucha en loopback, no en una interfaz de red
pública. Las comprobaciones posteriores se hicieron en una instancia de
demostración; los flujos de escritura se repitieron en una instancia temporal
para no alterar la base de datos local.

| Área | Comprobación observada | Resultado |
|---|---|---|
| Panel | Sesión `analista1`; panel muestra 12 alertas y 6 casos abiertos | PASS |
| Incidentes | Listado carga 12 casos con código, detección, equipo, amenaza, estado y criticidad | PASS |
| Filtros | Búsqueda textual `Ransomware` devuelve 2 registros en la muestra | PASS |
| Descargar CSV | HTTP 200, tipo `text/csv`; 13 líneas (cabecera y 12 registros) | PASS |
| Registrar incidente | Formulario disponible; registro válido completado en instancia temporal | PASS |
| Detalle | `/incidentes/INC-2026-0002` responde HTTP 200 | PASS |
| Asignación | Jefatura asigna un caso a `analista1` en instancia temporal | PASS |
| Contención | Analista contiene un caso en instancia temporal | PASS |
| Escalamiento | Jefatura escala un caso en instancia temporal | PASS |
| Falso positivo | Jefatura descarta una alerta con motivo en instancia temporal | PASS |
| Cierre | Cierre con causa raíz completado en instancia temporal | PASS |
| Equipos | Listado de equipos responde HTTP 200 | PASS |
| Indicadores | Resumen mensual responde HTTP 200 | PASS |
| Reporte mensual | Reporte textual HTTP 200; descarga Word HTTP 200 con tipo DOCX | PASS |
| Bitácora | Analista recibe HTTP 403; jefatura obtiene HTTP 200 | PASS |

La consola también se ejecutó con entrada agotada: cargó 5 usuarios, 6 equipos
y 12 incidentes, manejó EOF y guardó el repositorio antes de salir.

## Pruebas negativas obligatorias

| Caso | Escenario y entrada | Esperado según la implementación | Resultado real | Estado / evidencia |
|---|---|---|---|---|
| 1 | Registrar por la web con ocurrencia `2026-10-14 12:00` y detección `2026-10-14 11:00` | Rechazar fechas invertidas y mostrar validación | HTTP 400; el texto de error menciona que la detección no puede anteceder a la ocurrencia | **PASS**; POST de `/incidentes/nuevo`, sin crear un caso |
| 2 | Cerrar `INC-2026-0002` con causa raíz vacía | Rechazar cierre | HTTP 400; respuesta incluye “causa raíz” | **PASS**; POST de `/incidentes/INC-2026-0002/acciones` |
| 3 | Cerrar con causa raíz y sin lección aprendida | Cierre permitido; lección opcional según `ServicioIncidentes.cerrar` | Cierre completado; la lección queda `None` | **PASS**; flujo de cierre web en instancia temporal y prueba de negocio |
| 4 | Cerrar un incidente cuyo equipo esté inhabilitado | La RN-09 impide registrar casos nuevos en equipos inhabilitados, pero no define una condición que impida cerrar uno existente | El cierre con causa raíz se completó con el equipo inhabilitado | **PASS (comportamiento permitido)**; escenario de negocio `cierre_con_causa_raíz` |
| 5 | Escribir tres contraseñas incorrectas para `analista2` | Bloquear la cuenta | Intentos 1–3 recibieron HTTP 401; tras el tercero, el estado `bloqueado` fue verdadero. El intento siguiente mostró “La cuenta está bloqueada” | **PASS**; ejecutado en servidor temporal para no bloquear la cuenta demo persistente |
| 6 | Acceder como `analista1` a Bitácora | Denegar acceso exclusivo de jefatura | Analista: HTTP 403. `jefe_ti`: HTTP 200 | **PASS**; rutas `/bitacora` con ambas sesiones |

No se guardó una captura de pantalla como archivo del repositorio. La evidencia
anterior corresponde a respuestas HTTP, contenido de respuesta, conteos y la
vista del navegador observada durante esta ejecución.

## Evaluación heurística de Nielsen

Escala: 0 = no es problema; 1 = cosmético; 2 = menor; 3 = mayor;
4 = catastrófico. Se evaluaron las páginas realmente implementadas; no se
atribuyen hallazgos a pantallas que no existen.

| # | Heurística de Nielsen | Qué encontraste o "Cumple" | Pantalla | Severidad | Evidencia |
|---|---|---|---|---:|---|
| 1 | Visibilidad del estado del sistema | Cumple | Panel y detalle | 0 | El panel muestra conteos; después de una acción satisfactoria se vuelve al detalle con estado actualizado. |
| 2 | Relación entre el sistema y el mundo real | Cumple | Registro y detalle | 0 | Etiquetas en español corresponden al flujo: ocurrencia, detección, equipo, contención y causa raíz. |
| 3 | Control y libertad del usuario | No hay acción explícita “Cancelar” en el formulario ni opción de deshacer una acción enviada | Registro y detalle | 2 | Los formularios pueden abandonarse mediante navegación, pero no ofrecen control dedicado para cancelar ni deshacer cambios. |
| 4 | Consistencia y estándares | Cumple | Páginas autenticadas | 0 | Se conserva cabecera, navegación, idioma y estilo de formularios/tablas entre las vistas inspeccionadas. |
| 5 | Prevención de errores | Cumple | Registro y cierre | 0 | Campos obligatorios del formulario y validación de fechas/causa raíz en servicios; los dos envíos inválidos fueron rechazados. |
| 6 | Reconocer antes que recordar | Cumple | Listado y detalle de incidentes | 0 | El listado presenta código, fechas, equipo, amenaza, estado y criticidad; el detalle presenta contexto del caso. |
| 7 | Flexibilidad y eficiencia de uso | El filtro permite solo búsqueda textual; no ofrece filtros combinables por estado, origen, criticidad o periodo | Filtros de incidentes | 2 | La interfaz ofrece una caja “Texto de equipo o amenaza”; la búsqueda textual funciona, pero no hay controles para los demás criterios. |
| 8 | Diseño estético y minimalista | Las celdas de la tabla se estrechan y envuelven identificadores/estados en una ventana angosta | Listado de incidentes | 2 | Captura observada en el navegador a ancho reducido: códigos y estados ocupan varias líneas, dificultando escanear las filas. |
| 9 | Ayudar a reconocer, diagnosticar y recuperarse de errores | Cumple | Registro y acciones | 0 | Las entradas inválidas muestran un mensaje y enlace de regreso a incidentes; los errores de fecha y cierre fueron comprensibles. |
| 10 | Ayuda y documentación | No hay acceso a ayuda o guía desde la navegación de la aplicación | Navegación | 2 | El menú autenticado no contiene enlace de ayuda; la orientación está solo en el README del proyecto. |

Los hallazgos heurísticos son observaciones de usabilidad, no fallos de reglas de
negocio. El filtro textual y el diseño de tabla no impidieron las rutas o
acciones probadas, pero conviene considerarlos en una iteración de interfaz.

## Actualización web del 15 de octubre de 2026

Esta actualización complementa la evidencia histórica anterior. Se contrastaron
las pantallas de consola y las funciones del README con las rutas HTTP reales.

- Completadas las pantallas de alta y cambio de estado de equipos para jefatura;
  los intentos de administración de un analista reciben HTTP 403.
- Corregido el cierre de sesión: el formulario ahora envía el token CSRF y la
  sesión queda invalidada. Una solicitud sin token sigue recibiendo HTTP 403.
- Separados los formularios de atención: escalamiento y falso positivo ya no
  comparten dos campos `motivo` dentro de una misma solicitud.
- Incorporados filtros combinables y CSV con los mismos criterios, cancelación
  en altas, historial por incidente y visualización del estado/plazo ANPD.
- Corregido `crear_aplicacion(ruta_guardado)`: carga y guarda en la ruta indicada,
  sin leer el archivo habitual cuando se configura una instancia temporal.
- Conservados fuera de `sigis/web/` los módulos de dominio, persistencia,
  informes y consola. El README incluye la justificación y la matriz de rutas.

Verificación automatizada: `python pruebas_web.py`, **13 pruebas HTTP exitosas**.
Incluye ciclo completo de incidente, descarte, equipos, permisos, CSRF, filtros,
entradas inválidas, escape HTML, descargas y aislamiento de datos.

Verificación en navegador con datos temporales: panel, listado, registro,
equipos, alta de equipos, indicadores, reporte y bitácora respondieron HTTP 200
a anchos de 1366 y 390 px, sin desbordamiento horizontal del documento. También
se comprobaron el detalle abierto/cerrado y el alta/cambio de estado de un equipo
desde sus controles. Se inspeccionaron capturas de la lista móvil y del detalle
en escritorio; no se agregan imágenes de evidencia al repositorio.
