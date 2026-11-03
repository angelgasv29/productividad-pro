"""Enumeraciones de dominio compartidas por ORM, DTOs y servicios."""

from __future__ import annotations

from enum import Enum


class ModuleType(str, Enum):
    HABITS = "habits"
    ROUTINES = "routines"
    BACKLOG = "backlog"


class RoutineCategory(str, Enum):
    COMER = "Comer"
    LIMPIAR = "Limpiar"
    EJERCICIO = "Ejercicio"
    COMPRAR = "Comprar"
    DESCANSAR = "Descansar"
    RECREACION = "Recreacion"


class Priority(str, Enum):
    ALTA = "Alta"
    MEDIA = "Media"
    BAJA = "Baja"


class TaskTag(str, Enum):
    TRABAJO = "Trabajo"
    PERSONAL = "Personal"
    ESTUDIO = "Estudio"
    FINANZAS = "Finanzas"


class ImpactLevel(str, Enum):
    LEVE = "Leve"
    ALTA = "Alta"


class ExceptionArea(str, Enum):
    HABITOS = "Hábitos"
    RUTINAS = "Rutinas"
    BACKLOG = "Backlog"
    GENERAL = "General"


class Horizon(str, Enum):
    SEMANAL = "semanal"
    MENSUAL = "mensual"
    TRIMESTRAL = "trimestral"
    CUATRIMESTRAL = "cuatrimestral"
    SEMESTRAL = "semestral"
    ANUAL = "anual"


class TimerPhase(str, Enum):
    WORK = "work"
    BREAK = "break"


class ScoreScope(str, Enum):
    GLOBAL = "global"
    WORKSPACE = "workspace"


MODULE_LABELS: dict[ModuleType, str] = {
    ModuleType.HABITS: "Hábitos",
    ModuleType.ROUTINES: "Rutinas",
    ModuleType.BACKLOG: "Backlog",
}

DAY_NAMES: list[str] = ["Dom", "Lun", "Mar", "Mié", "Jue", "Vie", "Sáb"]
