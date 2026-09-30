"""Public tool errors must not expose upstream URLs or exception contents."""

import logging
from functools import wraps

import httpx

from src.clients.http import ResponseTooLarge

_logger = logging.getLogger(__name__)


def safe_error(exc: Exception) -> str:
    # Log only the exception class; exception text and tracebacks may contain
    # credentials, request parameters, or internal paths.
    _logger.warning('Tool request failed (%s)', type(exc).__name__)
    if isinstance(exc, ResponseTooLarge):
        return 'Die Datenquelle hat eine zu große Antwort geliefert.'
    if isinstance(exc, (TimeoutError, httpx.TimeoutException)):
        return 'Zeitüberschreitung beim Abrufen der Datenquelle.'
    if isinstance(exc, httpx.HTTPError):
        return 'Die Datenquelle ist derzeit nicht verfügbar.'
    if isinstance(exc, ValueError):
        return 'Ungültige Eingabe oder ungültiges Datenformat der Datenquelle.'
    return 'Die Anfrage konnte nicht verarbeitet werden.'


def safe_tool(function):
    """Protect tools that otherwise let FastMCP echo raw exceptions."""
    @wraps(function)
    async def wrapped(*args, **kwargs):
        try:
            return await function(*args, **kwargs)
        except Exception as exc:
            return {'error': safe_error(exc)}
    return wrapped
