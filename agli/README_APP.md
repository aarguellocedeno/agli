# AGLI — App web (Flask + SQLAlchemy + SQLite)

## Arrancar (Windows PowerShell)
```
pip install -r requirements.txt
python crear_clave.py          # genera/actualiza data\clave_respuestas.csv (conserva lo que ya escribiste)
$env:AGLI_DEMO="1"; python app.py     # ver la app con claves de PRUEBA  ->  http://127.0.0.1:5000
```
Con la clave ya llena puedes arrancar sin `AGLI_DEMO`: `python app.py`.

## Lo que falta para pruebas con estudiantes
1. **Clave de respuestas.** En el banco original la opción correcta es siempre `opcion_a`; `crear_clave.py` llena
   `data\clave_respuestas.csv` con esa letra (orden original). Si alguna pregunta tiene otra correcta, cámbiala ahí a mano.
   En pantalla las opciones se reordenan para que la correcta quede repartida entre A, B, C y D (orden fijo por pregunta,
   ver `SEMILLA_ORDEN` en `servicios/banco.py`). La letra que se guarda en cada respuesta es la que vio el estudiante.
2. **20 preguntas dependen de una figura/tabla** que el CSV no trae (lista en la salida de `crear_clave.py`; revisa la bandera `requiere_figura`).
   Guarda cada imagen como `static\img\preguntas\<id>.png` (ej. `q_06.png`); mientras no exista, esa pregunta se omite.
3. Define `AGLI_SECRET` (clave de sesión) y, si quieres exportar datos, `AGLI_ADMIN_TOKEN`:
   `/admin/exportar?token=...` descarga todas las respuestas en CSV (alias, ítem, acierto, tiempo, P(acierto) predicha, θ, P(dominio)…).
4. Estudiantes menores: la app solo pide un **alias** (sin nombres reales). Falta el consentimiento informado, que va fuera de la app.

## Estructura
```
app.py              rutas Flask (entrar, practicar, responder, resultado, resumen, progreso, exportar)
models.py           Usuario, Respuesta, Insignia, EstadoMotor (bandido compartido)
servicios/banco.py  banco + clave + imágenes; decide qué preguntas están activas
servicios/insignias.py   catálogo y reglas de insignias
templates/ static/  interfaz (HTML + CSS + JS sin dependencias; atajos de teclado A-D)
agli_engine/        motor BKT + IRT + LinUCB (ver README.md)
prueba_flujo.py     prueba de humo del flujo completo (modo demo, BD temporal)
```
Cada respuesta se guarda con P(acierto) predicha, θ y P(dominio): sirve para el análisis de la tesis.
