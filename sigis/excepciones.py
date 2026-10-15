"""Excepciones de dominio de SIGIS."""


class SIGISError(Exception):
    """Error esperado de operación o validación del sistema."""


class DatoInvalidoError(SIGISError):
    """Un dato suministrado no cumple las reglas de validación."""


class NoEncontradoError(SIGISError):
    """No se encontró el recurso solicitado."""


class PermisoDenegadoError(SIGISError):
    """El usuario autenticado no tiene permiso para la operación."""


class EstadoInvalidoError(SIGISError):
    """La operación no está permitida en el estado actual del recurso."""


class AutenticacionError(SIGISError):
    """Credenciales incorrectas o cuenta bloqueada."""
