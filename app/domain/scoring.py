"""Motor matemático puro: score, ponderación dinámica, penalizaciones y rachas.

Este módulo no conoce SQLAlchemy ni FastAPI. Recibe números y devuelve
resultados, lo que permite testearlo de forma aislada y reutilizarlo tanto en
el cálculo del día actual como en reconstrucciones históricas.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Iterable, Mapping, Protocol, Sequence

from app.core.config import settings
from app.domain.logical_date import split_interval_by_logical_date

BASE_WEIGHTS: dict[str, float] = {"habits": 0.40, "routines": 0.40, "backlog": 0.20}
HIGH_IMPACT_PENALTY_PER_30_MIN: float = 5.0
LOW_IMPACT_PENALTY_PER_30_MIN: float = 2.0


@dataclass(frozen=True, slots=True)
class ModuleProgress:
    total: int = 0
    completed: int = 0

    @property
    def pct(self) -> float:
        if self.total <= 0:
            return 0.0
        return (self.completed / self.total) * 100.0


@dataclass(frozen=True, slots=True)
class ScoreResult:
    h_total: int
    h_comp: int
    r_total: int
    r_comp: int
    b_total: int
    b_comp: int
    exc_mins: int
    penalty: int
    score: int
    base_score: float
    high_minutes: float = 0.0
    low_minutes: float = 0.0
    weights: dict[str, float] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class ExceptionPenaltySplit:
    logical_date: str
    minutes: float
    high_minutes: float
    low_minutes: float
    penalty: float


class ExceptionLike(Protocol):
    start_time: datetime
    end_time: datetime
    impact: str


def penalty_for_minutes(minutes: float, impact: str) -> float:
    if minutes <= 0:
        return 0.0
    rate = HIGH_IMPACT_PENALTY_PER_30_MIN if impact == "Alta" else LOW_IMPACT_PENALTY_PER_30_MIN
    return (minutes / 30.0) * rate


def dynamic_weights(progress: Mapping[str, ModuleProgress]) -> dict[str, float]:
    """Redistribuye el peso de los módulos sin tareas activas.

    Si un módulo tiene ``total == 0`` su peso se reparte proporcionalmente
    entre los módulos que sí tienen tareas. Si los tres están vacíos, no hay
    pesos y el score base es 0.
    """

    active = {key: BASE_WEIGHTS[key] for key, value in progress.items() if value.total > 0}
    total_weight = sum(active.values())
    if total_weight <= 0:
        return {}
    return {key: weight / total_weight for key, weight in active.items()}


def compute_score(
    habits: ModuleProgress,
    routines: ModuleProgress,
    backlog: ModuleProgress,
    high_minutes: float = 0.0,
    low_minutes: float = 0.0,
) -> ScoreResult:
    """Calcula el score de un ámbito (workspace o global).

    * Ponderación base: Hábitos 40 %, Rutinas 40 %, Backlog 20 %.
    * Módulos vacíos: su peso se redistribuye entre los activos.
    * Los tres vacíos: base 0 (nunca se regalan 100 puntos).
    * Penalización: Alta = 5 pts/30 min; Leve = 2 pts/30 min.
    """

    progress = {
        "habits": habits,
        "routines": routines,
        "backlog": backlog,
    }
    weights = dynamic_weights(progress)
    if not weights:
        base_score = 0.0
    else:
        base_score = sum(progress[key].pct * weight for key, weight in weights.items())

    penalty = penalty_for_minutes(high_minutes, "Alta") + penalty_for_minutes(
        low_minutes, "Leve"
    )
    score = max(0, min(100, round(base_score - penalty)))
    return ScoreResult(
        h_total=habits.total,
        h_comp=habits.completed,
        r_total=routines.total,
        r_comp=routines.completed,
        b_total=backlog.total,
        b_comp=backlog.completed,
        exc_mins=round(high_minutes + low_minutes),
        penalty=round(penalty),
        score=score,
        base_score=round(base_score, 4),
        high_minutes=round(high_minutes, 4),
        low_minutes=round(low_minutes, 4),
        weights=weights,
    )


def score_from_stored_base(
    base_score: float, high_minutes: float, low_minutes: float
) -> tuple[int, int]:
    """Recalcula un día histórico sin depender del estado actual del árbol.

    ``base_score`` se persiste en ``daily_score_history`` precisamente para
    poder borrar una excepción de un día pasado y revertir su penalización sin
    reconstruir tareas que ya fueron reiniciadas.
    """

    penalty = penalty_for_minutes(high_minutes, "Alta") + penalty_for_minutes(
        low_minutes, "Leve"
    )
    return max(0, min(100, round(base_score - penalty))), round(penalty)


def split_exception_penalty(
    start: datetime,
    end: datetime,
    impact: str,
    cutoff_hour: int = settings.logical_cutoff_hour,
) -> list[ExceptionPenaltySplit]:
    """Divide tiempo y penalización de una excepción entre días lógicos."""

    splits = split_interval_by_logical_date(start, end, cutoff_hour)
    result: list[ExceptionPenaltySplit] = []
    for logical_date, minutes in sorted(splits.items()):
        high = minutes if impact == "Alta" else 0.0
        low = minutes if impact != "Alta" else 0.0
        result.append(
            ExceptionPenaltySplit(
                logical_date=logical_date,
                minutes=round(minutes, 4),
                high_minutes=round(high, 4),
                low_minutes=round(low, 4),
                penalty=round(penalty_for_minutes(minutes, impact), 4),
            )
        )
    return result


def aggregate_exception_penalties(
    exceptions: Iterable[ExceptionLike],
    cutoff_hour: int = settings.logical_cutoff_hour,
) -> dict[str, dict[str, float]]:
    """Agrupa minutos y penalización por día lógico para todas las excepciones."""

    result: dict[str, dict[str, float]] = {}
    for exception in exceptions:
        if not exception.start_time or not exception.end_time:
            continue
        for split in split_exception_penalty(
            exception.start_time, exception.end_time, exception.impact, cutoff_hour
        ):
            bucket = result.setdefault(
                split.logical_date,
                {"minutes": 0.0, "high_minutes": 0.0, "low_minutes": 0.0, "penalty": 0.0},
            )
            bucket["minutes"] += split.minutes
            bucket["high_minutes"] += split.high_minutes
            bucket["low_minutes"] += split.low_minutes
            bucket["penalty"] += split.penalty
    return {
        key: {name: round(value, 4) for name, value in bucket.items()}
        for key, bucket in result.items()
    }


def compute_streaks(scores_by_date: Mapping[str, float]) -> tuple[int, int]:
    """Racha actual y máxima. Un día suma solo si su score es >= 60."""

    current = 0
    maximum = 0
    for _day in sorted(scores_by_date):
        if float(scores_by_date[_day]) >= 60:
            current += 1
            maximum = max(maximum, current)
        else:
            current = 0
    return current, maximum


def heatmap_level(score: float | int | None) -> int:
    """Niveles exactos del mapa de calor de 16 semanas."""

    if score is None:
        return 0
    value = float(score)
    if value < 1:
        return 0
    if value < 30:
        return 1
    if value < 50:
        return 2
    if value < 70:
        return 3
    if value < 90:
        return 4
    return 5


def average(values: Sequence[float]) -> int:
    if not values:
        return 0
    return round(sum(values) / len(values))


def last_n_average(scores_by_date: Mapping[str, float], n: int) -> int:
    """Promedio de los últimos ``n`` días *registrados* (no calendario)."""

    ordered = [float(scores_by_date[key]) for key in sorted(scores_by_date)]
    if not ordered:
        return 0
    window = ordered[-n:]
    return average(window)
