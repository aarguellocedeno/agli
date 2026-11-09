"""Calibración offline: ajusta BKT, IRT 2PL y el stacker; valida con los splits del CSV.

Uso:  python calibrate.py [bkt_interacciones.csv] [banco_biologia_81_dificultad.csv]
Salida: params/engine_params.json  (lo que carga el motor)  +  params/reporte_calibracion.json
"""
import json
import sys
import warnings
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import roc_auc_score, log_loss, brier_score_loss
from sklearn.model_selection import GroupKFold

from agli_engine.bkt_module import fit_bkt, BKTParams
from agli_engine.irt_module import fit_irt, estimate_theta, sigmoid

warnings.filterwarnings("ignore")
AQUI = Path(__file__).resolve().parent
RUTA_CSV = sys.argv[1] if len(sys.argv) > 1 else AQUI / "bkt_interacciones.csv"
RUTA_BANCO = sys.argv[2] if len(sys.argv) > 2 else AQUI / "banco_biologia_81_dificultad.csv"
SALIDA = AQUI / "params"
SALIDA.mkdir(exist_ok=True)

HYPER = {"target_prob": 0.72, "mastery_threshold": 0.85, "alpha": 0.3, "w_zpd": 1.0,
         "boss_len": 3, "boss_pass": 2}


def logit(p):
    p = np.clip(p, 1e-4, 1 - 1e-4)
    return np.log(p / (1 - p))


def cargar():
    df = pd.read_csv(RUTA_CSV)
    banco = pd.read_csv(RUTA_BANCO, encoding="utf-8-sig")
    df["kc"] = df["question_id"].map(banco.set_index("id")["eje_tematico"])
    assert df["kc"].notna().all(), "question_id fuera del banco"
    df["t"] = df.groupby("student_id").cumcount()
    return df, banco


def calibrar_bkt(train, kcs):
    params, rep = {}, {}
    for kc in kcs:
        seqs = [g["correct"].tolist() for _, g in train[train.kc == kc].groupby("student_id")]
        p, ll = fit_bkt(seqs)
        params[kc] = p
        rep[kc] = {**p.to_dict(), "loglik": ll, "n_secuencias": len(seqs),
                   "aciertos": float(train[train.kc == kc]["correct"].mean())}
    return params, rep


def calibrar_irt(train, banco):
    ids = banco["id"].tolist()
    j_of = {q: j for j, q in enumerate(ids)}
    studs = {s: k for k, s in enumerate(sorted(train.student_id.unique()))}
    stud = train.student_id.map(studs).to_numpy()
    item = train.question_id.map(j_of).to_numpy()
    y = train.correct.to_numpy()
    dif = banco["dificultad"].to_numpy()
    # Etapa 1: 1PL con prior débil -> escala empírica de b por nivel de `dificultad`
    _, _, b1, _ = fit_irt(stud, item, y, len(studs), len(ids), np.zeros(len(ids)),
                          sd_b=2.0, fix_a=True)
    b0_nivel = {int(d): float(b1[dif == d].mean()) for d in sorted(set(dif))}
    b0 = np.array([b0_nivel[int(d)] for d in dif])
    # Etapa 2: 2PL con prior de b anclado en el nivel empírico
    _, a, b, sd = fit_irt(stud, item, y, len(studs), len(ids), b0, sd_b=0.5, sd_loga=0.3)
    n_obs = np.bincount(item, minlength=len(ids))
    return a, b, sd, n_obs, b0_nivel, b1


def replay(df, items_by_id, bkt):
    """Predicciones online (antes de cada respuesta) sin mirar el futuro."""
    filas = []
    for s, g in df.groupby("student_id", sort=False):
        pl = {k: p.prior for k, p in bkt.items()}
        hist_a, hist_b, hist_y = [], [], []
        for r in g.itertuples():
            it = items_by_id[r.question_id]
            th = estimate_theta(np.array(hist_a), np.array(hist_b), np.array(hist_y))
            pi = float(sigmoid(it["a"] * (th - it["b"])))
            pb = bkt[r.kc].p_correct(pl[r.kc])
            filas.append((s, r.t, r.split, r.kc, it["dificultad"], pi, pb, r.correct))
            pl[r.kc] = bkt[r.kc].update(pl[r.kc], bool(r.correct))
            hist_a.append(it["a"]); hist_b.append(it["b"]); hist_y.append(r.correct)
    return pd.DataFrame(filas, columns=["student_id", "t", "split", "kc", "dif", "p_irt", "p_bkt", "y"])


def metricas(y, p):
    return {"AUC": float(roc_auc_score(y, p)), "logloss": float(log_loss(y, p)),
            "brier": float(brier_score_loss(y, p)), "n": int(len(y))}


def main():
    df, banco = cargar()
    kcs = sorted(banco["eje_tematico"].unique())
    train = df[df.split == "train"]

    bkt, rep_bkt = calibrar_bkt(train, kcs)
    a, b, sd, n_obs, b0_nivel, b1 = calibrar_irt(train, banco)
    items = [{"id": q, "kc": k, "dificultad": int(d), "a": float(a[j]), "b": float(b[j]),
              "sd_b": float(sd[j])}
             for j, (q, k, d) in enumerate(zip(banco["id"], banco["eje_tematico"], banco["dificultad"]))]
    items_by_id = {i["id"]: i for i in items}

    rp = replay(df[df.split != "train"], items_by_id, bkt)
    pre, te = rp[rp.split == "predict"], rp[rp.split == "test"]

    def X(d):
        return np.c_[logit(d.p_irt), logit(d.p_bkt)]

    # Stacker ajustado en `predict`; evaluado en `test` y con CV agrupada por estudiante en `predict`
    lr = LogisticRegression(C=1e6).fit(X(pre), pre.y)
    cv = np.zeros(len(pre))
    for tr_i, va_i in GroupKFold(5).split(pre, groups=pre.student_id):
        m = LogisticRegression(C=1e6).fit(X(pre.iloc[tr_i]), pre.y.iloc[tr_i])
        cv[va_i] = m.predict_proba(X(pre.iloc[va_i]))[:, 1]
    stacker = {"w0": float(lr.intercept_[0]), "w_irt": float(lr.coef_[0][0]),
               "w_bkt": float(lr.coef_[0][1])}
    base = float(train.correct.mean())

    reporte = {
        "filas": {s: int((df.split == s).sum()) for s in ["train", "predict", "test"]},
        "bkt": rep_bkt,
        "irt": {"b0_empirico_por_dificultad": b0_nivel,
                "a_media": float(a.mean()), "a_min": float(a.min()), "a_max": float(a.max()),
                "b_rango": [float(b.min()), float(b.max())], "n_obs_por_item_media": float(n_obs.mean())},
        "stacker": stacker,
        "validacion_test": {
            "base_media_train": metricas(te.y, np.full(len(te), base)),
            "solo_BKT": metricas(te.y, te.p_bkt),
            "solo_IRT": metricas(te.y, te.p_irt),
            "BKT+IRT (stacker)": metricas(te.y, lr.predict_proba(X(te))[:, 1]),
        },
        "validacion_predict_cv": {
            "solo_BKT": metricas(pre.y, pre.p_bkt),
            "solo_IRT": metricas(pre.y, pre.p_irt),
            "BKT+IRT (stacker, CV)": metricas(pre.y, cv),
        },
    }
    (SALIDA / "reporte_calibracion.json").write_text(json.dumps(reporte, indent=2, ensure_ascii=False))
    (SALIDA / "engine_params.json").write_text(json.dumps({
        "kcs": kcs, "bkt": {k: v.to_dict() for k, v in bkt.items()}, "items": items,
        "stacker": stacker, "hyper": HYPER}, indent=2, ensure_ascii=False))
    print(json.dumps(reporte, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
