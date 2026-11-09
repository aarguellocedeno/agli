"""Módulo BKT: macro-rastreo curricular ("el porqué").

Un KC (componente de conocimiento) = un eje temático del banco.
Parámetros interpretables: P(L0), P(T), P(G), P(S).
Todo en NumPy puro: sirve tanto para ajustar offline (EM) como para actualizar online.
"""
from __future__ import annotations

from dataclasses import dataclass, asdict

import numpy as np


@dataclass(frozen=True)
class BKTParams:
    prior: float   # P(L0)
    learn: float   # P(T)
    slip: float    # P(S)
    guess: float   # P(G)

    def p_correct(self, p_l: float) -> float:
        """P(acierto) antes de ver la respuesta."""
        return p_l * (1 - self.slip) + (1 - p_l) * self.guess

    def posterior(self, p_l: float, correct: bool) -> float:
        """P(dominio | respuesta observada), teorema de Bayes."""
        if correct:
            num = p_l * (1 - self.slip)
            den = num + (1 - p_l) * self.guess
        else:
            num = p_l * self.slip
            den = num + (1 - p_l) * (1 - self.guess)
        return num / den

    def update(self, p_l: float, correct: bool) -> float:
        """P(L_{t+1}) tras responder: posterior + oportunidad de aprender."""
        post = self.posterior(p_l, correct)
        return post + (1 - post) * self.learn

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "BKTParams":
        return cls(**{k: float(d[k]) for k in ("prior", "learn", "slip", "guess")})


# ---------------------------------------------------------------- ajuste EM
BOUNDS = {  # cotas habituales para evitar el modelo degenerado (identificabilidad)
    "prior": (0.01, 0.99),
    "learn": (0.001, 0.60),
    "slip": (0.01, 0.30),
    "guess": (0.01, 0.40),
}


def _clip(name: str, v: float) -> float:
    lo, hi = BOUNDS[name]
    return float(min(max(v, lo), hi))


def _forward_backward(y: np.ndarray, p: BKTParams):
    T = len(y)
    e = np.empty((T, 2))  # e[t, s] = P(y_t | estado s); s=0 no dominado, s=1 dominado
    e[:, 0] = np.where(y == 1, p.guess, 1 - p.guess)
    e[:, 1] = np.where(y == 1, 1 - p.slip, p.slip)
    A = np.array([[1 - p.learn, p.learn], [0.0, 1.0]])
    alpha = np.zeros((T, 2))
    c = np.zeros(T)
    a0 = np.array([1 - p.prior, p.prior]) * e[0]
    c[0] = a0.sum()
    alpha[0] = a0 / c[0]
    for t in range(1, T):
        a = (alpha[t - 1] @ A) * e[t]
        c[t] = a.sum()
        alpha[t] = a / c[t]
    beta = np.ones((T, 2))
    for t in range(T - 2, -1, -1):
        beta[t] = (A @ (e[t + 1] * beta[t + 1])) / c[t + 1]
    gamma = alpha * beta
    xi01 = sum(alpha[t, 0] * A[0, 1] * e[t + 1, 1] * beta[t + 1, 1] / c[t + 1]
               for t in range(T - 1))
    return gamma, xi01, float(np.log(c).sum())


def fit_bkt(sequences: list[list[int]], n_restarts: int = 20, max_iter: int = 300,
            tol: float = 1e-7, seed: int = 42) -> tuple[BKTParams, float]:
    """EM (Baum-Welch) sobre secuencias de aciertos (una por estudiante) de un KC."""
    rng = np.random.default_rng(seed)
    seqs = [np.asarray(s, dtype=int) for s in sequences if len(s) > 0]
    best, best_ll = None, -np.inf
    for r in range(n_restarts):
        p = BKTParams(prior=rng.uniform(0.1, 0.9), learn=rng.uniform(0.02, 0.4),
                      slip=rng.uniform(0.02, 0.25), guess=rng.uniform(0.05, 0.35))
        prev = -np.inf
        for _ in range(max_iter):
            g0 = n_first = xi = g_unl = g_unl_all = g_unl_ok = g_lrn = g_lrn_bad = 0.0
            ll = 0.0
            for y in seqs:
                gamma, xi01, l = _forward_backward(y, p)
                ll += l
                g0 += gamma[0, 1]
                n_first += 1
                xi += xi01
                g_unl += gamma[:-1, 0].sum()
                g_unl_all += gamma[:, 0].sum()
                g_unl_ok += (gamma[:, 0] * (y == 1)).sum()
                g_lrn += gamma[:, 1].sum()
                g_lrn_bad += (gamma[:, 1] * (y == 0)).sum()
            p = BKTParams(
                prior=_clip("prior", g0 / n_first),
                learn=_clip("learn", xi / max(g_unl, 1e-9)),
                slip=_clip("slip", g_lrn_bad / max(g_lrn, 1e-9)),
                guess=_clip("guess", g_unl_ok / max(g_unl_all, 1e-9)),
            )
            if abs(ll - prev) < tol:
                break
            prev = ll
        if ll > best_ll:
            best, best_ll = p, ll
    return best, best_ll
