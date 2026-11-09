"""Validación del motor integrado (sanity checks, NO evidencia pedagógica).

1. Recuperación de parámetros del EM de BKT con datos sintéticos de parámetros conocidos.
2. Simulación de estudiantes (proceso generador BKT + efecto de dificultad por ítem) y comparación de
   políticas: aleatoria vs BKT+IRT+ZPD (sin bandido) vs motor completo (BKT+IRT+LinUCB).
Uso: python evaluate.py [n_estudiantes] [pasos]
"""
import json
import sys
from pathlib import Path

import numpy as np
from sklearn.metrics import roc_auc_score, brier_score_loss

from agli_engine import AdaptiveEngine, EngineParams
from agli_engine.bandit_module import LinUCB, FEATURE_NAMES
from agli_engine.bkt_module import BKTParams, fit_bkt
from agli_engine.irt_module import sigmoid

AQUI = Path(__file__).resolve().parent
N_EST = int(sys.argv[1]) if len(sys.argv) > 1 else 300
PASOS = int(sys.argv[2]) if len(sys.argv) > 2 else 40


def chequeo_em():
    rng = np.random.default_rng(0)
    real = BKTParams(prior=0.3, learn=0.15, slip=0.12, guess=0.22)
    seqs = []
    for _ in range(400):
        L = rng.random() < real.prior
        y = []
        for _ in range(10):
            y.append(int(rng.random() < (1 - real.slip if L else real.guess)))
            L = L or (rng.random() < real.learn)
        seqs.append(y)
    est, _ = fit_bkt(seqs, n_restarts=10)
    return {"real": real.to_dict(), "estimado": {k: round(v, 3) for k, v in est.to_dict().items()}}


class Mundo:
    """Estudiantes sintéticos: dominio latente por KC (BKT) + habilidad general + dificultad por ítem."""

    def __init__(self, params: EngineParams, rng):
        self.P, self.rng = params, rng
        self.b_true = {i.id: i.b + rng.normal(0, 0.25) for i in params.items}   # error de calibración
        self.b_mean = float(np.mean([i.b for i in params.items]))

    def nuevo(self):
        L = {k: self.rng.random() < p.prior for k, p in self.P.bkt.items()}
        return {"L": L, "theta": self.rng.normal(0, 0.6)}

    def p_true(self, s, it):
        bkt = self.P.bkt[it.kc]
        base = (1 - bkt.slip) if s["L"][it.kc] else bkt.guess
        z = np.log(base / (1 - base)) + it.a * (s["theta"] - (self.b_true[it.id] - self.b_mean))
        return float(sigmoid(z))

    def responder(self, s, it):
        p = self.p_true(s, it)
        y = self.rng.random() < p
        if not s["L"][it.kc]:                                  # oportunidad de aprender
            s["L"][it.kc] = self.rng.random() < self.P.bkt[it.kc].learn
        return bool(y), p


def correr(politica, params, n_est, pasos, seed=1):
    rng = np.random.default_rng(seed)
    mundo = Mundo(params, rng)
    alpha = 0.0 if politica == "zpd_sin_bandido" else params.hyper["alpha"]
    eng = AdaptiveEngine(params, bandit=LinUCB(len(FEATURE_NAMES), alpha=alpha))
    items = params.items
    acc, ptrue, explora, jefes, dominios, expos = [], [], [], 0, 0, {}
    th_hat, th_true, pl_fin, dom_fin, racha_prot = [], [], [], [], 0
    ppred, yy, repetidas = [], [], 0
    for _ in range(n_est):
        s, st = mundo.nuevo(), eng.new_student()
        for _ in range(pasos):
            if politica == "aleatoria":
                it = items[rng.integers(len(items))]
                rec = None
            else:
                rec = eng.next_item(st)
                it = eng.by_id[rec.item_id]
            y, p = mundo.responder(s, it)
            acc.append(y); ptrue.append(p); expos[it.id] = expos.get(it.id, 0) + 1
            if rec is not None:
                ppred.append(rec.p_pred); yy.append(int(y))
                fb = eng.submit(st, rec, y)
                explora.append(rec.is_exploration)
                jefes += any(e.startswith("jefe_desbloqueado") for e in fb["eventos"])
                dominios += sum(e.startswith("kc_dominado") for e in fb["eventos"])
                racha_prot += "racha_protegida" in fb["eventos"]
            else:  # la política aleatoria solo actualiza BKT/IRT para poder medir el rastreo
                rec2 = type("R", (), {"item_id": it.id, "p_pred": 0.5, "is_boss": True,
                                      "is_exploration": False, "x": []})()
                eng.submit(st, rec2, y)
        th_hat.append(st.theta); th_true.append(s["theta"])
        for k in params.kcs:
            pl_fin.append(st.p_l[k]); dom_fin.append(int(s["L"][k]))
    ptrue = np.array(ptrue)
    return {
        "acierto_real": float(np.mean(acc)),
        "P_acierto_predicha_media": float(np.mean(ppred)) if ppred else None,
        "Brier_P_predicha_en_el_lazo": float(brier_score_loss(yy, ppred)) if ppred else None,
        "AUC_P_predicha_en_el_lazo": float(roc_auc_score(yy, ppred)) if ppred else None,
        "pct_exploracion": float(np.mean(explora)) if explora else None,
        "items_usados_de_81": len(expos),
        "exposicion_max_item": int(max(expos.values())),
        "AUC_P(L)_final_vs_dominio_real": float(roc_auc_score(dom_fin, pl_fin)),
        "Brier_P(L)_final": float(brier_score_loss(dom_fin, pl_fin)),
        "corr_theta_est_vs_real": float(np.corrcoef(th_hat, th_true)[0, 1]),
        "jefes_desbloqueados_por_estudiante": jefes / n_est,
        "kc_dominados_por_estudiante": dominios / n_est,
        "rachas_protegidas_por_estudiante": racha_prot / n_est,
    }


def main():
    params = EngineParams.load(AQUI / "params" / "engine_params.json")
    out = {"chequeo_EM_BKT": chequeo_em(), "simulacion": {}}
    for pol in ["aleatoria", "zpd_sin_bandido", "motor_completo"]:
        out["simulacion"][pol] = correr(pol, params, N_EST, PASOS)
    (AQUI / "params" / "reporte_simulacion.json").write_text(json.dumps(out, indent=2, ensure_ascii=False))
    print(json.dumps(out, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
