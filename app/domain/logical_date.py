"""Fecha lógica con corte configurable (04:00 AM por defecto).

Regla de negocio: todo instante anterior a las 04:00 pertenece al día
calendario anterior. Esto protege a los usuarios nocturnos y es la base de
todo el scoring, el historial y la línea de tiempo.
"""

from __future__ import annotations

from datetime import date, datetime, time, timedelta
from typing import Iterator

from app.core.config import settings

DEFAULT_CUTOFF_HOUR: int = settings.logical_cutoff_hour


def _local_naive(value: datetime) -> datetime:
    """Normaliza datetimes con zona horaria a la hora local naive."""

    if value.tzinfo is not None:
        return value.astimezone().replace(tzinfo=None)
    return value


def get_logical_date_dt(
    now: datetime | None = None, cutoff_hour: int = DEFAULT_CUTOFF_HOUR
) -> date:
    """Devuelve la fecha lógica como objeto ``date``."""

    current = _local_naive(now) if now is not None else datetime.now()
    if current.hour < cutoff_hour:
        return (current - timedelta(days=1)).date()
    return current.date()


def get_logical_date(
    now: datetime | None = None, cutoff_hour: int = DEFAULT_CUTOFF_HOUR
) -> str:
    """Devuelve la fecha lógica en formato ISO ``YYYY-MM-DD``."""

    return get_logical_date_dt(now, cutoff_hour).isoformat()


def logical_date_of_datetime(
    value: datetime, cutoff_hour: int = DEFAULT_CUTOFF_HOUR
) -> str:
    return get_logical_date(value, cutoff_hour)


def parse_logical_date(value: str | date) -> date:
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    return date.fromisoformat(str(value)[:10])


def logical_day_bounds(
    logical_date: str | date, cutoff_hour: int = DEFAULT_CUTOFF_HOUR
) -> tuple[datetime, datetime]:
    """Inicio y fin (exclusivo) del día lógico: 04:00 → 04:00 siguiente."""

    day = parse_logical_date(logical_date)
    start = datetime.combine(day, time(hour=cutoff_hour))
    end = datetime.combine(day + timedelta(days=1), time(hour=cutoff_hour))
    return start, end


def logical_hour_datetime(
    logical_date: str | date, hour: int, cutoff_hour: int = DEFAULT_CUTOFF_HOUR
) -> datetime:
    """Convierte un bloque ``HH:00`` de la línea de tiempo a datetime real.

    Los bloques 00:00–03:00 pertenecen a la madrugada del día calendario
    siguiente al día lógico.
    """

    day = parse_logical_date(logical_date)
    if hour < cutoff_hour:
        day = day + timedelta(days=1)
    return datetime.combine(day, time(hour=hour % 24))


def iter_timeline_hours(
    cutoff_hour: int = DEFAULT_CUTOFF_HOUR,
) -> Iterator[tuple[int, int, str]]:
    """Itera la línea de tiempo 04:00 → 03:00 (24 bloques).

    Yields ``(index, real_hour, "HH:00")`` con ``index`` de 4 a 27.
    """

    for index in range(cutoff_hour, cutoff_hour + 24):
        real_hour = index % 24
        yield index, real_hour, f"{real_hour:02d}:00"


def _next_logical_boundary(
    value: datetime, cutoff_hour: int = DEFAULT_CUTOFF_HOUR
) -> datetime:
    """Frontera 04:00 que cierra el día lógico que contiene ``value``."""

    if value.hour < cutoff_hour:
        return datetime.combine(value.date(), time(hour=cutoff_hour))
    return datetime.combine(value.date() + timedelta(days=1), time(hour=cutoff_hour))


def split_interval_by_logical_date(
    start: datetime,
    end: datetime,
    cutoff_hour: int = DEFAULT_CUTOFF_HOUR,
) -> dict[str, float]:
    """Divide un intervalo entre días lógicos y devuelve minutos por fecha.

    Ejemplo con corte 04:00: 02:00 → 06:00 produce 120 min para el día
    anterior y 120 min para el día actual. Es la base de la penalización
    proporcional de excepciones que cruzan la frontera.
    """

    start = _local_naive(start)
    end = _local_naive(end)
    if end <= start:
        return {}

    result: dict[str, float] = {}
    cursor = start
    guard = 0
    while cursor < end and guard < 10_000:
        guard += 1
        logical = get_logical_date(cursor, cutoff_hour)
        boundary = _next_logical_boundary(cursor, cutoff_hour)
        segment_end = min(end, boundary)
        if segment_end <= cursor:
            # Salvaguarda ante datetimes exactamente en la frontera.
            segment_end = min(end, cursor + timedelta(seconds=1))
        minutes = (segment_end - cursor).total_seconds() / 60.0
        if minutes > 0:
            result[logical] = round(result.get(logical, 0.0) + minutes, 4)
        cursor = segment_end
    return result


def iso_to_logical_date(
    value: str | datetime | None, cutoff_hour: int = DEFAULT_CUTOFF_HOUR
) -> str | None:
    """Convierte un ISO timestamp legacy a fecha lógica local."""

    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return get_logical_date(value, cutoff_hour)
    text = str(value).strip()
    if len(text) == 10:
        try:
            return date.fromisoformat(text).isoformat()
        except ValueError:
            return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        try:
            parsed = datetime.strptime(text[:19], "%Y-%m-%dT%H:%M:%S")
        except ValueError:
            return text[:10] if len(text) >= 10 else None
    return get_logical_date(parsed, cutoff_hour)


def dates_between(start: str, end: str) -> list[str]:
    """Lista inclusiva de fechas ISO entre ``start`` y ``end``."""

    first = parse_logical_date(start)
    last = parse_logical_date(end)
    if last < first:
        return []
    return [(first + timedelta(days=i)).isoformat() for i in range((last - first).days + 1)]


def missing_dates(last_date: str, today: str) -> list[str]:
    """Días intermedios entre el último acceso y hoy (excluyendo ambos)."""

    try:
        first = parse_logical_date(last_date) + timedelta(days=1)
        last = parse_logical_date(today)
    except ValueError:
        return []
    result: list[str] = []
    while first < last:
        result.append(first.isoformat())
        first += timedelta(days=1)
    return result


def week_start_monday(day: str | date) -> date:
    d = parse_logical_date(day)
    return d - timedelta(days=d.weekday())


def period_key_for_date(day: str, period: str) -> str:
    """Agrupa una fecha en las 7 granularidades del Historial Detallado."""

    d = parse_logical_date(day)
    if period == "day":
        return d.isoformat()
    if period == "week":
        return week_start_monday(d).isoformat()
    if period == "month":
        return f"{d.year:04d}-{d.month:02d}"
    if period == "quarter":
        return f"{d.year:04d}-Q{(d.month - 1) // 3 + 1}"
    if period == "quadrimester":
        return f"{d.year:04d}-C{(d.month - 1) // 4 + 1}"
    if period == "semester":
        return f"{d.year:04d}-S{1 if d.month <= 6 else 2}"
    if period == "year":
        return f"{d.year:04d}"
    return d.isoformat()


def period_label(key: str, period: str) -> tuple[str, str]:
    """Etiquetas humanas en español para el Historial Detallado."""

    meses = [
        "ene",
        "feb",
        "mar",
        "abr",
        "may",
        "jun",
        "jul",
        "ago",
        "sep",
        "oct",
        "nov",
        "dic",
    ]
    meses_largo = [
        "Enero",
        "Febrero",
        "Marzo",
        "Abril",
        "Mayo",
        "Junio",
        "Julio",
        "Agosto",
        "Septiembre",
        "Octubre",
        "Noviembre",
        "Diciembre",
    ]
    dias = ["Domingo", "Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado"]
    try:
        if period == "day":
            d = parse_logical_date(key)
            # dias está ordenado Domingo→Sábado; date.weekday() va Lunes→Domingo.
            return key, dias[(d.weekday() + 1) % 7]
        if period == "week":
            start = parse_logical_date(key)
            end = start + timedelta(days=6)
            fmt = lambda dt: f"{dt.day} {meses[dt.month - 1]}"  # noqa: E731
            return f"Semana del {fmt(start)}", f"{fmt(start)} – {fmt(end)} {end.year}"
        if period == "month":
            year, month = key.split("-")
            return f"{meses_largo[int(month) - 1]} {year}", "Mes"
        if period == "quarter":
            year, quarter = key.split("-Q")
            return f"Trimestre {quarter} {year}", f"Q{quarter} · {year}"
        if period == "quadrimester":
            year, number = key.split("-C")
            return f"Cuatrimestre {number} {year}", f"C{number} · {year}"
        if period == "semester":
            year, number = key.split("-S")
            return f"Semestre {number} {year}", f"S{number} · {year}"
        if period == "year":
            return f"Año {key}", "Anual"
    except (ValueError, IndexError):
        pass
    return key, ""
