# AGLI — Motor adaptativo integrado (BKT + IRT 2PL + LinUCB)

```
agli_engine/
  bkt_module.py     BKT: P(L0),P(T),P(G),P(S) por eje temático (EM propio en NumPy + actualización online)
  irt_module.py     IRT 2PL: calibración MAP de a,b (prior anclado en `dificultad`) y theta online
  bandit_module.py  LinUCB compartido (11 features, pesos auditables)
  gamification.py   XP por brecha b−θ, racha protegida, niveles
  engine.py         AdaptiveEngine: next_item() / submit()  ← lo que llama Flask
calibrate.py        offline: ajusta todo con bkt_interacciones.csv → params/engine_params.json
evaluate.py         validación: recuperación de parámetros EM + simulación de políticas
demo.py             sesión de ejemplo con explicaciones y serialización del estado
```

## Flujo por pregunta
1. **BKT** elige el eje con menor P(dominio) (sin repetir el mismo eje >3 veces seguidas).
2. **IRT + BKT** → P(acierto) del ítem = `σ(w0 + w_irt·logit(P_IRT) + w_bkt·logit(P_BKT))` (stacker logístico, pesos en `engine_params.json`).
3. **LinUCB** puntúa cada candidato: `utilidad_ZPD + recompensa_estimada + α·incertidumbre`. Recompensa = 0.5·Fisher normalizada + 0.5·ganancia de P(L).
4. `submit()` actualiza BKT, θ, bandido, XP/racha y dispara el **jefe de eje** cuando P(L) cruza 0.85 (3 preguntas difíciles, pasa con 2).

Cada `Recommendation` trae `componentes` y `explicacion` en español (trazabilidad para el comité).

## Integración con Flask
```python
engine = AdaptiveEngine(EngineParams.load("params/engine_params.json"))   # una vez al arrancar
st  = StudentState.from_dict(json.loads(usuario.estado_json))             # por petición
rec = engine.next_item(st)            # guardar rec en sesión (rec.__dict__)
fb  = engine.submit(st, rec, es_correcta)
usuario.estado_json = json.dumps(st.to_dict())
# bandido compartido: persistir engine.bandit.to_dict() y engine.exposures de vez en cuando
```
(Para reconstruir `rec` desde la sesión: `Recommendation(**rec_dict)`.)

## Reproducir
```
pip install numpy scipy pandas scikit-learn
python calibrate.py     # ~40 s
python evaluate.py
python demo.py
```
