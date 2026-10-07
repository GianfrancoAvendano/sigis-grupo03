# SIGIS — Sistema de Gestión de Incidentes de Seguridad de la Información

Trabajo Final del curso **IS275 – Fundamentos de Programación 2**
Caso real: área de Tecnologías de la Información de **Madison Latam**

---

## Cómo ejecutar

El sistema tiene **dos interfaces sobre el mismo núcleo de negocio**. Ninguna de
las dos contiene reglas: las dos llaman a los mismos métodos de `sigis/servicios.py`.

**Interfaz web** (la que se muestra en el video):

```bash
python web.py
```

Se abre solo el navegador en `http://127.0.0.1:8000`. Si ese puerto está ocupado,
`python web.py 8080`. Para detenerlo, Ctrl + C en la consola.

**Interfaz de consola** (el menú que pide el enunciado):

```bash
python main.py
```

Ninguna de las dos requiere instalar nada: solo Python 3.8 o superior y la
librería estándar. El servidor web está hecho con `http.server`, que viene
incluido en Python.

**Usuarios de prueba**

| Usuario | Contraseña | Perfil | Qué puede hacer |
|---|---|---|---|
| `jefe_ti` | `jefe123` | Jefatura | Todo: asignar, bitácora, configuración |
| `analista1` | `clave123` | Analista | Registrar, atender, contener, cerrar |

La primera vez se cargan datos de ejemplo: 5 usuarios, 6 equipos y 12 incidentes
repartidos en **tres meses** (el actual y los dos anteriores), para que el reporte
y los indicadores muestren resultados distintos según el periodo que se elija.
A partir de ahí el sistema **conserva lo que registres**: todo se guarda solo en
`datos/sigis.json`, con una copia de respaldo diaria. Para empezar de cero,
borra la carpeta `datos/`.

## Cómo ejecutar las pruebas

```bash
python pruebas_negocio.py
```

Son **64 pruebas** sobre los métodos de negocio. Todas deben pasar.
Prueban el núcleo, así que valen igual para la consola y para la web.

---

## Estructura del proyecto

```
main.py                 Punto de entrada de la interfaz de consola
web.py                  Punto de entrada de la interfaz web
pruebas_negocio.py      64 pruebas unitarias
sigis/
  ├── excepciones.py    Excepciones propias (todas heredan de SIGISError)
  ├── almacen.py        Guardado y carga en JSON, con respaldo diario
  ├── enums.py          Enumeraciones y PARÁMETROS configurables
  ├── modelo.py         Clases del dominio (Usuario, Equipo, Incidente…)
  ├── patrones.py       Singleton, Factory, Strategy y Observer
  ├── servicios.py      Reglas de negocio RN-01 a RN-09      ← NÚCLEO
  ├── indicadores.py    MTTD, MTTR, SLA, falsos positivos, reporte mensual
  ├── consola.py        Lectura validada de teclado
  ├── menus.py          Las 18 pantallas en consola          ← interfaz 1
  ├── reporte_docx.py   Reporte mensual en Word, armado con zipfile (sin dependencias)
  ├── datos_demo.py     Datos de ejemplo
  └── web/
      ├── servidor.py   Rutas HTTP y llamadas a los servicios  ← interfaz 2
      └── plantillas.py HTML y estilos de cada pantalla
```

Las dos interfaces suman unas 1 800 líneas y **no repiten ni una regla de
negocio**: si se cambia la fórmula de la criticidad en `servicios.py`, cambia
en las dos al mismo tiempo. Esa es la razón de haber separado las capas
(sección D.2.6 del informe).

---

## Dónde está cada cosa que pide el enunciado

Esta tabla es para la **exposición**: te dice en qué archivo y clase señalar
cuando el profesor pregunte por cada requisito.

| Lo que exige el enunciado | Dónde está |
|---|---|
| Menú de ejecución de las opciones | `menus.py` → `Aplicacion.menu_principal()`; en la web, la barra de navegación de `web/plantillas.py` |
| Funcionalidades de **control** | `servicios.py` → `ServicioEquipos`, `ServicioIncidentes` (registrar, listar, buscar, editar, dar de baja) |
| Funcionalidades de **cálculo** | `indicadores.py` → `CalculadoraIndicadores` (MTTD, MTTR, cumplimiento, tasa de FP, carga, horas de indisponibilidad, reincidencia) |
| **Clases** y relaciones | `modelo.py`. Composición: `Incidente` contiene una lista de `AccionAuditoria`. Asociación: `Incidente` referencia un `Equipo` |
| **Herencia** | `Usuario` → `Analista`, `JefeTI`  ·  `Incidente` → `IncidenteWazuh`, `IncidenteSophos`, `IncidenteReporteUsuario` |
| **Polimorfismo** | `opciones_menu()` y `puede()` en `Usuario`; `descripcion_origen()` y `peso_confiabilidad()` en `Incidente`. Cada subclase responde distinto al mismo mensaje |
| **Encapsulamiento** | `Usuario.__hash_clave` usa *name mangling*: ninguna clase lo lee por su nombre. Se compara con `verificar_clave()` y solo `almacen.py` lo obtiene, con `obtener_hash()`, para guardarlo (se guarda el resumen SHA-256, nunca la clave). `AccionAuditoria` expone properties de solo lectura |
| **Patrones de diseño** | `patrones.py` (ver abajo) |
| **Pruebas** a los métodos de negocio | `pruebas_negocio.py`, 64 casos |
| **Estilo PEP 8** | Verificado con `pycodestyle --max-line-length=99` (límite que la propia PEP 8 admite si el equipo lo acuerda): 0 observaciones |
| **Interfaz gráfica** (web) | `web.py` + `sigis/web/`. Segunda interfaz sobre el mismo núcleo, sin duplicar reglas |
| **Exportación** (HU-21) | Reporte mensual a **Word (.docx)** y a `.txt`, y lista de incidentes a `.csv`. Disponible en la web y en la consola |
| **Control de excepciones** | `excepciones.py` + `try/except` en cada operación de `menus.py` + validación en `consola.py` |

---

## Los cuatro patrones de diseño

| Patrón | Clase | Por qué se usó |
|---|---|---|
| **Singleton** | `Repositorio` | Un solo almacén de datos en memoria. Por más veces que se escriba `Repositorio()`, siempre es el mismo objeto — evita tener dos listas de incidentes desincronizadas, que es justo el problema P-01 del informe |
| **Factory Method** | `FabricaIncidentes` | Crea la subclase correcta según el origen de la alerta. El resto del programa pide "un incidente de Wazuh" sin conocer la clase `IncidenteWazuh` |
| **Strategy** | `EstrategiaCriticidad` | Permite cambiar la fórmula de la criticidad sin tocar la clase `Incidente`. Hay dos estrategias implementadas y se puede alternar entre ellas desde la pantalla P-17 |
| **Observer** | `Notificador` | Al ocurrir un evento avisa a los tres observadores suscritos: `BitacoraAuditoria` (RN-08), `AlertaPlazoLegal` (RN-06) y `GuardadoAutomatico` (persistencia). Agregar un comportamiento nuevo no obliga a modificar los servicios |

---

## Las reglas de negocio implementadas

| Regla | Qué dice | Dónde se cumple |
|---|---|---|
| RN-01 | Criticidad = impacto × urgencia | `patrones.CriticidadPorMatriz` |
| RN-02/03 | Escalas de impacto y urgencia | `enums.ESCALA_IMPACTO`, `ESCALA_URGENCIA` |
| RN-04 | Tiempos objetivo por criticidad | `enums.TIEMPOS_OBJETIVO` |
| RN-05 | Fórmulas de los indicadores | `indicadores.CalculadoraIndicadores` |
| RN-06 | Plazo de 48 h para notificar a la ANPD | `Incidente.fecha_limite_notificacion()` |
| RN-07 | No se cierra sin causa raíz | `ServicioIncidentes.cerrar()` |
| RN-08 | Bitácora de auditoría inalterable | `patrones.BitacoraAuditoria` + `AccionAuditoria` |
| RN-09 | Equipo fuera de servicio no admite nuevo caso | `Equipo.inhabilitar()` / `devolver()` |

---

## Tres preguntas que te pueden hacer, y la respuesta

**¿Por qué usaste Singleton para el repositorio?**
Porque el problema central del caso es que la información del incidente está
en tres lugares distintos. Si el programa pudiera crear varios repositorios,
estaríamos reproduciendo el mismo problema en el código.

**¿Para qué sirve el Strategy si solo hay una forma de calcular la criticidad?**
Hay dos implementadas. La segunda existe porque la matriz impacto × urgencia
es una propuesta del grupo que la jefatura todavía no valida (Tabla 11 del
informe). Si mañana cambia el criterio, se cambia la estrategia y no se toca
ni la clase `Incidente` ni los servicios.

**¿Dónde se guardan los datos?**
En `datos/sigis.json`, y no lo guarda ningún servicio: lo hace el observador
`GuardadoAutomatico` cada vez que ocurre un evento. Así, cualquier operación
que se agregue en el futuro queda persistida sin tocar la capa de negocio.
Además se genera una copia de respaldo por día, que es lo que exige el
Reglamento de la Ley 29733 al responsable del tratamiento.

**¿Cómo generan un Word sin instalar python-docx?**
Un archivo .docx es, por dentro, un ZIP con documentos XML. Como Python trae
`zipfile` en su librería estándar, `sigis/reporte_docx.py` arma el XML del
documento y lo empaqueta. El archivo abre en Word con títulos, tablas con
cabecera y colores. Ninguna cifra se recalcula ahí: usa la misma
`CalculadoraIndicadores` que el reporte de texto.

**¿La web y la consola no duplican el código?**
No. Las dos son capas de presentación: leen datos, llaman a `servicios.py` y
dibujan el resultado. Las reglas RN-01 a RN-09 existen una sola vez. La prueba
está en las 64 pruebas unitarias: no abren ninguna interfaz y aun así validan
todo el comportamiento del sistema.

**¿Por qué no usaron un framework web como Django o Flask?**
Porque el sistema debe poder ejecutarse sin instalar nada. El servidor está
hecho con `http.server` de la librería estándar, y eso mantiene la promesa de
que basta con Python para correr el proyecto completo.

**¿El reporte de un mes mezcla datos de otros meses?**
No. Cada incidente cuenta en el mes en que se **detectó**. Las horas de
indisponibilidad también se reparten por periodo: si un equipo se inhabilitó
el 31 de julio a las 20:00 y se devolvió el 1 de agosto a las 06:00, cuatro
horas van a julio y seis a agosto. Para eso cada equipo guarda el historial de
sus periodos fuera de servicio (`Equipo.periodos_indisponible`).

**¿Por qué los falsos positivos no entran en el MTTR?**
Porque el MTTR mide cuánto demora resolver un incidente *real*. Si se
incluyeran, el indicador mejoraría artificialmente cada vez que llega una
alerta falsa. Por la misma razón tampoco entran en el porcentaje de cumplimiento: un falso
positivo descartado en diez minutos no es un incidente atendido a tiempo.
Sí cuentan, en cambio, para la tasa de falsos positivos, que es
el indicador que sirve para ajustar las reglas de Wazuh y Sophos.

---

## Nota sobre los datos

Los datos de `datos_demo.py` son **ficticios**, elaborados por el grupo para
efectos de demostración. No corresponden a información real de la empresa:
no contienen direcciones IP, nombres de usuarios, clientes ni hallazgos reales.

---

## Pendiente para la entrega final

- [x] Diagrama de clases UML del modelo (punto E.2)
- [x] Diagrama de clases de los patrones de diseño (punto E.3)
- [x] Interfaz web sobre el mismo núcleo de negocio
- [ ] Video demostrativo del funcionamiento (punto E.4)
- [ ] Conclusiones y recomendaciones (puntos F y G)
- [ ] Repositorio Git con los commits por integrante (punto J)
