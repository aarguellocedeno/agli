"""Módulo de bandido contextual (LinUCB compartido): adaptación dinámica ("el cómo").

Un solo modelo lineal compartido por todos los ítems y estudiantes (pocas features):
recompensa esperada = x^T theta_hat  (regresión Ridge)
bono de exploración = sqrt(x^T A^-1 x)  (incertidumbre)
Los pesos theta_hat son auditables: cada uno es el efecto de una feature sobre la recompensa.
"""
from __future__ import annotations

import numpy as np

FEATURE_NAMES = ["bias", "b", "a", "gap(b-theta)", "gap^2", "P(L) del KC", "novedad",
                 "kc0", "kc1", "kc2", "kc3"]


class LinUCB:
    def __init__(self, d: int, alpha: float = 0.3, ridge: float = 1.0):
        self.d, self.alpha = d, alpha
        self.A = ridge * np.eye(d)
        self.b = np.zeros(d)
        self.n_updates = 0

    def weights(self) -> np.ndarray:
        return np.linalg.solve(self.A, self.b)

    def score(self, x: np.ndarray) -> tuple[float, float]:
        """Devuelve (recompensa media estimada, bono de incertidumbre ya multiplicado por alpha)."""
        th = self.weights()
        a_inv_x = np.linalg.solve(self.A, x)
        return float(x @ th), float(self.alpha * np.sqrt(max(x @ a_inv_x, 0.0)))

    def update(self, x: np.ndarray, reward: float) -> None:
        self.A += np.outer(x, x)
        self.b += reward * x
        self.n_updates += 1

    def to_dict(self) -> dict:
        return {"d": self.d, "alpha": self.alpha, "A": self.A.tolist(), "b": self.b.tolist(),
                "n_updates": self.n_updates}

    @classmethod
    def from_dict(cls, d: dict) -> "LinUCB":
        m = cls(d["d"], d["alpha"])
        m.A, m.b, m.n_updates = np.array(d["A"]), np.array(d["b"]), d["n_updates"]
        return m
