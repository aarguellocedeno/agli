"""Módulo IRT 2PL: micro-calibración de dificultad ("el qué").

- Calibración offline (MAP conjunta) con prior de b anclado en la `dificultad` etiquetada.
- Estimación online de theta (MAP, Newton) con prior N(0, 1): no necesita historial masivo.
Sin parámetro c (pseudo-adivinanza): con 81 ítems no hay N para un 3PL fiable.
"""
from __future__ import annotations

import numpy as np
from scipy.optimize import minimize


def sigmoid(z):
    return 1.0 / (1.0 + np.exp(-z))


def p_irt(theta: float, a: float, b: float) -> float:
    return float(sigmoid(a * (theta - b)))


def fisher_info(theta: float, a: float, b: float) -> float:
    p = p_irt(theta, a, b)
    return a * a * p * (1 - p)


def fit_irt(stud: np.ndarray, item: np.ndarray, y: np.ndarray, n_stud: int, n_item: int,
            b0: np.ndarray, sd_b: float, sd_loga: float = 0.3, fix_a: bool = False):
    """Estimación MAP conjunta de theta_s, log a_j, b_j. Devuelve (theta, a, b, sd_b_post)."""
    S, J = n_stud, n_item
    y = y.astype(float)

    def f(x):
        th, la, b = x[:S], x[S:S + J], x[S + J:]
        if fix_a:
            la = np.zeros(J)
        a = np.exp(la)
        z = a[item] * (th[stud] - b[item])
        p = sigmoid(z)
        eps = 1e-12
        nll = -(y * np.log(p + eps) + (1 - y) * np.log(1 - p + eps)).sum()
        nll += 0.5 * (th ** 2).sum() + 0.5 * ((la / sd_loga) ** 2).sum() \
            + 0.5 * (((b - b0) / sd_b) ** 2).sum()
        r = p - y
        gth = np.bincount(stud, weights=r * a[item], minlength=S) + th
        gla = np.bincount(item, weights=r * a[item] * (th[stud] - b[item]), minlength=J) \
            + la / sd_loga ** 2
        gb = np.bincount(item, weights=-r * a[item], minlength=J) + (b - b0) / sd_b ** 2
        if fix_a:
            gla = np.zeros(J)
        return nll, np.concatenate([gth, gla, gb])

    x0 = np.concatenate([np.zeros(S), np.zeros(J), b0])
    res = minimize(f, x0, jac=True, method="L-BFGS-B", options={"maxiter": 500})
    th, la, b = res.x[:S], res.x[S:S + J], res.x[S + J:]
    a = np.ones(J) if fix_a else np.exp(la)
    p = sigmoid(a[item] * (th[stud] - b[item]))
    info = np.bincount(item, weights=a[item] ** 2 * p * (1 - p), minlength=J) + 1 / sd_b ** 2
    return th, a, b, 1 / np.sqrt(info)


def estimate_theta(a: np.ndarray, b: np.ndarray, y: np.ndarray,
                   prior_mu: float = 0.0, prior_sd: float = 1.0, iters: int = 25) -> float:
    """theta MAP dado el historial (a_j, b_j, y_j). Sin historial -> prior_mu."""
    if len(y) == 0:
        return prior_mu
    a, b, y = map(np.asarray, (a, b, y))
    th = prior_mu
    for _ in range(iters):
        p = sigmoid(a * (th - b))
        g = (a * (y - p)).sum() - (th - prior_mu) / prior_sd ** 2
        h = (a * a * p * (1 - p)).sum() + 1 / prior_sd ** 2
        step = g / h
        th = float(np.clip(th + step, -4, 4))
        if abs(step) < 1e-6:
            break
    return th
