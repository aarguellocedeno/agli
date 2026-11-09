"""Reglas de gamificación (DDA): XP por brecha de dificultad, salvavidas de racha, niveles."""
from __future__ import annotations

BASE_XP = 100
XP_POR_NIVEL = 600
MULT_MAX = 3.0
P_RACHA_PROTEGIDA = 0.25  # si P(acierto) predicha < 0.25 el fallo no es "culpa" del estudiante


def xp_por_acierto(b: float, theta: float, boss: bool = False) -> int:
    """Más XP cuanto más difícil era el ítem respecto a la habilidad actual."""
    mult = min(MULT_MAX, max(1.0, (b - theta) + 1.5))
    return int(BASE_XP * mult * (2 if boss else 1))


def nivel(xp: int) -> int:
    return 1 + xp // XP_POR_NIVEL


def racha_protegida(es_exploracion: bool, p_pred: float) -> bool:
    """Un fallo en un ítem puesto por el algoritmo (exploración o muy difícil) no rompe la racha."""
    return es_exploracion or p_pred < P_RACHA_PROTEGIDA
