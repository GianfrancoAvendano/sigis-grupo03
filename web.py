"""
SIGIS - Sistema de Gestion de Incidentes de Seguridad de la Informacion
IS275 - Fundamentos de Programacion 2
Caso: area de Tecnologias de la Informacion de Madison Latam

INTERFAZ WEB.  Ejecucion:   python web.py   [puerto]

Es la misma aplicacion que `main.py`, con otra interfaz. Las reglas de
negocio RN-01 a RN-09 viven en `sigis/servicios.py` y no se duplican:
tanto el menu de consola como esta web llaman a los mismos metodos.

No requiere instalar nada: usa solo la libreria estandar de Python.
"""

import sys

from sigis.web import ejecutar


def main():
    puerto = 8000
    if len(sys.argv) > 1:
        try:
            puerto = int(sys.argv[1])
        except ValueError:
            print(f"  Puerto invalido: {sys.argv[1]}. Se usara el 8000.")
    try:
        ejecutar(puerto)
    except OSError as err:
        print(f"\n  No se pudo iniciar el servidor en el puerto {puerto}: {err}")
        print(f"  Pruebe con otro puerto, por ejemplo:  python web.py {puerto + 1}\n")


if __name__ == "__main__":
    main()
