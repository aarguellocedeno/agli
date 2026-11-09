"""Demo: una sesión de un estudiante simulado, mostrando las decisiones y su explicación.
Muestra además cómo guardar/restaurar el estado como JSON (para SQLAlchemy)."""
import json
from pathlib import Path

import numpy as np

from agli_engine import AdaptiveEngine, EngineParams, StudentState

AQUI = Path(__file__).resolve().parent
rng = np.random.default_rng(7)
eng = AdaptiveEngine(EngineParams.load(AQUI / "params" / "engine_params.json"))
st = eng.new_student()

for paso in range(1, 13):
    rec = eng.next_item(st)                      # 1) el motor elige
    it = eng.by_id[rec.item_id]
    correcto = rng.random() < rec.p_pred         # 2) aquí iría la respuesta real del estudiante
    fb = eng.submit(st, rec, correcto)           # 3) se actualiza todo
    print(f"{paso:>2}. {it.id} [{it.kc[:28]}] dif={it.dificultad} P≈{rec.p_pred:.2f} "
          f"{'✔' if correcto else '✘'} +{fb['xp']}XP racha={fb['racha']} nivel={fb['nivel']} "
          f"θ={fb['theta']:+.2f} {fb['eventos'] or ''}")
    if paso in (1, 12):
        print("    →", rec.explicacion)

# Persistencia: el estado del estudiante es un dict JSON (columna JSON / Text en SQLAlchemy)
guardado = json.dumps(st.to_dict())
st2 = StudentState.from_dict(json.loads(guardado))
assert st2.p_l == st.p_l and st2.history == st.history
print("\nP(dominio) por eje:", {k[:25]: round(v, 2) for k, v in st.p_l.items()})
