"""
SIGIS - Sistema de Gestion de Incidentes de Seguridad de la Informacion
IS275 - Fundamentos de Programacion 2
Caso: area de Tecnologias de la Informacion de Madison Latam

Ejecucion:      python main.py
Usuarios demo:  jefe_ti / jefe123        (perfil Jefatura)
                analista1 / clave123     (perfil Analista)

La informacion se guarda sola en datos/sigis.json: la primera vez el
programa carga datos de ejemplo, y a partir de ahi conserva lo que se
registre. Para empezar de cero, borre esa carpeta.
"""

from sigis import almacen
from sigis.datos_demo import cargar
from sigis.menus import Aplicacion
from sigis.servicios import construir_sistema


def main():
    repo, auth, equipos, incidentes = construir_sistema()

    if almacen.cargar(repo):
        incidentes.alerta_plazo.reconstruir()
        print(f"  Datos cargados de la sesion anterior: "
              f"{len(repo.usuarios)} usuarios, {len(repo.equipos)} equipos, "
              f"{len(repo.incidentes)} incidentes.")
    else:
        try:
            resumen = cargar(auth, equipos, incidentes)
            print(f"  Primera ejecucion. Datos de ejemplo cargados: "
                  f"{resumen['usuarios']} usuarios, {resumen['equipos']} equipos, "
                  f"{resumen['incidentes']} incidentes.")
        except Exception as err:                      # pragma: no cover
            print(f"  No se pudieron cargar los datos de ejemplo: {err}")

    aplicacion = Aplicacion(repo, auth, equipos, incidentes)
    try:
        aplicacion.ejecutar()
    except KeyboardInterrupt:
        print("\n\n  Ejecucion interrumpida por el usuario.\n")
    except EOFError:
        # Ocurre si la entrada estandar se agota (por ejemplo, al ejecutar
        # el programa con un archivo de entrada o al pulsar Ctrl+D).
        print("\n\n  Fin de la entrada de datos. Se cierra el sistema.\n")
    finally:
        if almacen.guardar(repo):
            print(f"  Informacion guardada en {almacen.ARCHIVO}\n")
        else:
            print("  AVISO: no se pudo guardar la informacion en disco.\n")


if __name__ == "__main__":
    main()
