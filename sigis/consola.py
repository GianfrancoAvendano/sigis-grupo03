"""Lectura y validación de entradas para la interfaz de consola."""

from datetime import datetime

from .excepciones import DatoInvalidoError


def leer_texto(mensaje, obligatorio=True):
    texto = input(mensaje).strip()
    if obligatorio and not texto:
        raise DatoInvalidoError("Este campo es obligatorio.")
    return texto


def leer_entero(mensaje, minimo=None, maximo=None):
    texto = input(mensaje).strip()
    try:
        numero = int(texto)
    except ValueError as error:
        raise DatoInvalidoError("Ingrese un número entero válido.") from error
    if ((minimo is not None and numero < minimo)
            or (maximo is not None and numero > maximo)):
        raise DatoInvalidoError("El número está fuera del rango permitido.")
    return numero


def leer_fecha(mensaje):
    texto = input(mensaje).strip()
    try:
        return datetime.fromisoformat(texto)
    except ValueError as error:
        raise DatoInvalidoError("Use el formato AAAA-MM-DD HH:MM.") from error


def leer_opcion(mensaje, opciones):
    opcion = leer_texto(mensaje)
    if opcion not in {str(valor) for valor in opciones}:
        raise DatoInvalidoError("Seleccione una opción disponible.")
    return opcion
