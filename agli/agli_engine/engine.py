"""Motor integrado BKT + IRT 2PL + LinUCB (+ gamificación).

Flujo por pregunta
  1. BKT decide el KC (eje temático): el de menor P(dominio) aún no dominado.
  2. IRT estima P(acierto) de cada ítem candidato del KC (theta + a, b calibrados),
     corregida por un "stacker" logístico que mezcla IRT y BKT.
  3. LinUCB puntúa cada candidato: utilidad ZPD + recompensa aprendida + bono de incertidumbre.
  4. Tras la respuesta: se actualizan BKT, theta, pesos del bandido y la gamificación.

Cada recomendación devuelve sus componentes (auditable) y una explicación en español.
El estado del estudiante es un dict JSON-serializable (columna JSON en SQLite/SQLAlchemy).
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field, asdict
from pathlib import Path

import numpy as np

from . import gamification as gm
from .bandit_module import LinUCB, FEATURE_NAMES
from .bkt_module import BKTParams
from .irt_module import estimate_theta, p_irt, sigmoid


def logit(p: float) -> float:
    p = min(max(p, 1e-4), 1 - 1e-4)
    return float(np.log(p / (1 - p)))


@dataclass(frozen=True)
class Item:
    id: str
    kc: str
    dificultad: int
    a: float
    b: float
    sd_b: float = 0.0


@dataclass
class EngineParams:
    kcs: list[str]
    bkt: dict[str, BKTParams]
    items: list[Item]
    stacker: dict
    hyper: dict

    @classmethod
    def load(cls, path: str | Path) -> "EngineParams":
        d = json.loads(Path(path).read_text(encoding="utf-8"))
        return cls(
            kcs=d["kcs"],
            bkt={k: BKTParams.from_dict(v) for k, v in d["bkt"].items()},
            items=[Item(**i) for i in d["items"]],
            stacker=d["stacker"],
            hyper=d["hyper"],
        )


@dataclass
class StudentState:
    p_l: dict[str, float]
    theta: float = 0.0
    history: list[dict] = field(default_factory=list)   # {"item": id, "correct": 0/1}
    xp: int = 0
    streak: int = 0
    best_streak: int = 0
    dominados: list[str] = field(default_factory=list)
    boss: dict | None = None                              # {"kc","restantes","aciertos"}

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "StudentState":
        return cls(**d)


@dataclass
class Recommendation:
    item_id: str
    kc: str
    p_pred: float
    is_exploration: bool
    is_boss: bool
    explicacion: str
    componentes: dict
    x: list[float]


class AdaptiveEngine:
    def __init__(self, params: EngineParams, bandit: LinUCB | None = None,
                 exposures: dict[str, int] | None = None, activos: set[str] | None = None):
        """`activos`: ids de ítems que se pueden servir (p. ej. con clave de respuesta e imagen)."""
        self.P = params
        self.h = params.hyper
        self.by_id = {i.id: i for i in params.items}
        self.by_kc = {k: [i for i in params.items if i.kc == k and (activos is None or i.id in activos)]
                      for k in params.kcs}
        self.kcs_activos = [k for k in params.kcs if self.by_kc[k]]
        self.bandit = bandit or LinUCB(len(FEATURE_NAMES), alpha=self.h["alpha"])
        self.exposures = exposures if exposures is not None else {}

    # ------------------------------------------------------------ estado
    def new_student(self) -> StudentState:
        return StudentState(p_l={k: self.P.bkt[k].prior for k in self.P.kcs})

    # ------------------------------------------------------- probabilidades
    def p_pred(self, st: StudentState, it: Item) -> float:
        """P(acierto) = stacker( IRT(theta; a, b), BKT(P(L) del KC) )."""
        s = self.P.stacker
        pi = p_irt(st.theta, it.a, it.b)
        pb = self.P.bkt[it.kc].p_correct(st.p_l[it.kc])
        return float(sigmoid(s["w0"] + s["w_irt"] * logit(pi) + s["w_bkt"] * logit(pb)))

    def context(self, st: StudentState, it: Item) -> np.ndarray:
        gap = it.b - st.theta
        onehot = [1.0 if it.kc == k else 0.0 for k in self.P.kcs]
        novelty = 1 / np.sqrt(1 + self.exposures.get(it.id, 0))
        return np.array([1.0, it.b, it.a, gap, gap ** 2, st.p_l[it.kc], novelty] + onehot)

    # ------------------------------------------------------------ selección
    def _choose_kc(self, st: StudentState) -> str:
        abiertos = [k for k in self.kcs_activos if k not in st.dominados] or list(self.kcs_activos)
        vistos = {h["item"] for h in st.history}
        con_nuevos = [k for k in abiertos if any(i.id not in vistos for i in self.by_kc[k])]
        if not con_nuevos:                     # ejes pendientes agotados: repasar otro eje con preguntas nuevas
            con_nuevos = [k for k in self.kcs_activos if any(i.id not in vistos for i in self.by_kc[k])]
        abiertos = con_nuevos or abiertos      # evitar repetir preguntas mientras queden nuevas
        ultimos = [self.by_id[h["item"]].kc for h in st.history[-3:]]
        if len(ultimos) == 3 and len(set(ultimos)) == 1 and len(abiertos) > 1:
            abiertos = [k for k in abiertos if k != ultimos[0]] or abiertos  # intercalar temas
        return min(abiertos, key=lambda k: st.p_l[k])

    def _candidates(self, st: StudentState, kc: str) -> list[Item]:
        vistos = {h["item"] for h in st.history}
        c = [i for i in self.by_kc[kc] if i.id not in vistos]
        if not c:  # banco agotado en el KC: repetir, evitando los 5 últimos
            recientes = {h["item"] for h in st.history[-5:]}
            c = [i for i in self.by_kc[kc] if i.id not in recientes] or self.by_kc[kc]
        return c

    def next_item(self, st: StudentState) -> Recommendation:
        if st.boss:
            return self._boss_item(st)
        kc = self._choose_kc(st)
        target, w_zpd = self.h["target_prob"], self.h["w_zpd"]
        filas = []
        for it in self._candidates(st, kc):
            p = self.p_pred(st, it)
            zpd = 1 - 2 * abs(p - target)
            x = self.context(st, it)
            mean_hat, bonus = self.bandit.score(x)
            filas.append((w_zpd * zpd + mean_hat + bonus, it, p, zpd, mean_hat, bonus, x))
        best = max(filas, key=lambda f: f[0])
        greedy = max(filas, key=lambda f: f[3])           # lo que elegiría un ZPD puro
        _, it, p, zpd, mean_hat, bonus, x = best
        # exploración = el bandido sacrificó utilidad ZPD apreciable (>0.10 ≈ 5 pts de P) por información
        explora = (greedy[3] - zpd) > self.h.get("umbral_exploracion", 0.10)
        razon = (f"Eje «{kc}»: tu probabilidad de dominio es {st.p_l[kc]:.0%}, la más baja entre "
                 f"los ejes pendientes. Pregunta con ~{p:.0%} de acierto esperado "
                 f"(objetivo {target:.0%}).")
        if explora:
            razon += " Es una pregunta de exploración: ayuda al sistema a calibrarse."
        return Recommendation(it.id, kc, p, explora, False, razon,
                              {"zpd": zpd, "recompensa_estimada": mean_hat, "bono_incertidumbre": bonus,
                               "theta": st.theta, "P_L": st.p_l[kc]}, x.tolist())

    def _boss_item(self, st: StudentState) -> Recommendation:
        kc = st.boss["kc"]
        vistos = {h["item"] for h in st.history}
        c = sorted(self.by_kc[kc], key=lambda i: (i.id in vistos, -i.b))
        it = c[0]
        p = self.p_pred(st, it)
        return Recommendation(it.id, kc, p, False, True,
                              f"¡Jefe del eje «{kc}»! {st.boss['restantes']} pregunta(s) difíciles "
                              f"para consolidar el dominio.", {"theta": st.theta},
                              self.context(st, it).tolist())

    # --------------------------------------------------------- actualización
    def submit(self, st: StudentState, rec: Recommendation, correct: bool) -> dict:
        it = self.by_id[rec.item_id]
        theta_antes, pl_antes = st.theta, st.p_l[it.kc]
        eventos: list[str] = []

        # 1) BKT
        st.p_l[it.kc] = self.P.bkt[it.kc].update(pl_antes, correct)
        # 2) IRT: theta MAP con todo el historial
        st.history.append({"item": it.id, "correct": int(correct)})
        hs = [self.by_id[h["item"]] for h in st.history]
        st.theta = estimate_theta(np.array([i.a for i in hs]), np.array([i.b for i in hs]),
                                  np.array([h["correct"] for h in st.history]))
        # 3) Bandido (solo si el ítem lo eligió el bandido, no el jefe)
        if not rec.is_boss:
            p = rec.p_pred
            ganancia = float(np.clip((st.p_l[it.kc] - pl_antes) / 0.15, 0, 1))
            recompensa = 0.5 * 4 * p * (1 - p) + 0.5 * ganancia
            self.bandit.update(np.array(rec.x), recompensa)
        self.exposures[it.id] = self.exposures.get(it.id, 0) + 1

        # 4) Gamificación
        xp = 0
        if correct:
            xp = gm.xp_por_acierto(it.b, theta_antes, boss=rec.is_boss)
            st.xp += xp
            st.streak += 1
            st.best_streak = max(st.best_streak, st.streak)
        elif gm.racha_protegida(rec.is_exploration, rec.p_pred):
            eventos.append("racha_protegida")
        else:
            st.streak = 0

        # 5) Jefe de eje
        thr = self.h["mastery_threshold"]
        if st.boss:
            st.boss["restantes"] -= 1
            st.boss["aciertos"] += int(correct)
            if st.boss["restantes"] == 0:
                if st.boss["aciertos"] >= self.h["boss_pass"]:
                    st.dominados.append(st.boss["kc"])
                    eventos.append(f"kc_dominado:{st.boss['kc']}")
                else:
                    eventos.append(f"jefe_fallido:{st.boss['kc']}")
                st.boss = None
        elif pl_antes < thr <= st.p_l[it.kc] and it.kc not in st.dominados:
            st.boss = {"kc": it.kc, "restantes": self.h["boss_len"], "aciertos": 0}
            eventos.append(f"jefe_desbloqueado:{it.kc}")

        return {"correct": bool(correct), "xp": xp, "xp_total": st.xp, "nivel": gm.nivel(st.xp),
                "racha": st.streak, "theta": st.theta, "P_L": dict(st.p_l), "eventos": eventos}
