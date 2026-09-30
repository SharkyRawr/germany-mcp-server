"""Validation for values used in upstream URL paths and coordinates."""

import math
import re


def road_name(value: str) -> str:
    value = value.strip().upper()
    if not re.fullmatch(r"A[1-9][0-9]{0,2}", value):
        raise ValueError("Autobahn muss eine Bezeichnung wie A1 oder A61 sein.")
    return value


def coordinates(lat: float | None, lon: float | None) -> None:
    if lat is None or lon is None:
        raise ValueError("lat und lon müssen gemeinsam angegeben werden.")
    if not math.isfinite(lat) or not -90 <= lat <= 90:
        raise ValueError("lat muss zwischen -90 und 90 liegen.")
    if not math.isfinite(lon) or not -180 <= lon <= 180:
        raise ValueError("lon muss zwischen -180 und 180 liegen.")
