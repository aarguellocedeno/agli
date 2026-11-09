"""Catálogo y reglas de insignias."""
from __future__ import annotations

from .banco import KC_INFO, kc_slug, kc_nombre

_FIJAS = {
    "primera": ("🔬", "Primera muestra", "Responde tu primera pregunta."),
    "racha_3": ("🔥", "Racha de 3", "Acierta 3 preguntas seguidas."),
    "racha_5": ("🔥", "Racha de 5", "Acierta 5 preguntas seguidas."),
    "racha_10": ("🔥", "Racha de 10", "Acierta 10 preguntas seguidas."),
    "aciertos_10": ("🌱", "10 aciertos", "Suma 10 respuestas correctas."),
    "aciertos_25": ("🌿", "25 aciertos", "Suma 25 respuestas correctas."),
    "aciertos_50": ("🌳", "50 aciertos", "Suma 50 respuestas correctas."),
    "nivel_2": ("⭐", "Nivel 2", "Llega al nivel 2."),
    "nivel_5": ("🌟", "Nivel 5", "Llega al nivel 5."),
    "valiente": ("🧗", "Pregunta difícil", "Acierta una pregunta de dificultad alta."),
    "jefe": ("🏆", "Jefe vencido", "Vence a tu primer jefe de eje."),
    "sesion": ("🎯", "Sesión completa", "Termina una sesión de repaso."),
}
_ICONO_EJE = {"energia": "⚡", "procesos": "🧫", "relacion": "🌍", "herencia": "🧬"}


def catalogo() -> dict[str, dict]:
    cat = {k: {"icono": v[0], "nombre": v[1], "desc": v[2]} for k, v in _FIJAS.items()}
    for kc in KC_INFO:
        s = kc_slug(kc)
        cat[f"dominio_{s}"] = {"icono": _ICONO_EJE.get(s, "🧪"), "nombre": f"Dominas: {kc_nombre(kc)}",
                               "desc": f"Vence al jefe del eje «{kc_nombre(kc)}»."}
    return cat


def evaluar(*, ya: set[str], n_respuestas: int, n_correctas: int, mejor_racha: int, nivel: int,
            correcta: bool, dificultad: int, eventos: list[str], sesion_completa: bool) -> list[str]:
    """Devuelve los códigos de insignias NUEVAS tras esta respuesta."""
    gana = []
    reglas = [
        ("primera", n_respuestas >= 1),
        ("racha_3", mejor_racha >= 3), ("racha_5", mejor_racha >= 5), ("racha_10", mejor_racha >= 10),
        ("aciertos_10", n_correctas >= 10), ("aciertos_25", n_correctas >= 25),
        ("aciertos_50", n_correctas >= 50),
        ("nivel_2", nivel >= 2), ("nivel_5", nivel >= 5),
        ("valiente", correcta and dificultad >= 3),
        ("sesion", sesion_completa),
    ]
    for ev in eventos:
        if ev.startswith("kc_dominado:"):
            reglas += [("jefe", True), (f"dominio_{kc_slug(ev.split(':', 1)[1])}", True)]
    for codigo, cumple in reglas:
        if cumple and codigo not in ya and codigo not in gana:
            gana.append(codigo)
    return gana
