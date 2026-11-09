"""Genera data/clave_respuestas.csv, la plantilla donde se registra la respuesta correcta de cada pregunta.

Columnas:
  id                 id de la pregunta en el banco
  respuesta_correcta A, B, C o D según el ORDEN ORIGINAL del dataset (columnas opcion_a..opcion_d).
                     En el dataset la correcta es siempre opcion_a, así que las vacías se llenan con "A".
                     Si una pregunta tiene otra correcta, cámbiala aquí a mano (se conserva al volver a ejecutar).
                     La app reordena las opciones en pantalla, así que no todas se ven en la A.
  requiere_figura    1 si el enunciado depende de una imagen/tabla/gráfica que el CSV no trae
                     (marcada automáticamente por heurística: REVÍSALA a mano)
  nota               inicio del enunciado, para identificar la pregunta al llenar la clave

Si el archivo ya existe, conserva las respuestas y banderas que ya escribiste.
Las imágenes se guardan como static/img/preguntas/<id>.png (o .jpg/.webp/.svg).
Uso: python crear_clave.py
"""
import re
from pathlib import Path

import pandas as pd

AQUI = Path(__file__).resolve().parent
BANCO = AQUI / "banco_biologia_81_dificultad.csv"
CLAVE = AQUI / "data" / "clave_respuestas.csv"
CORRECTA_DATASET = "A"   # en el banco original la respuesta correcta está en opcion_a

FIGURA = re.compile(
    r"(siguiente|anterior)\s+(figura|gr[aá]fica|esquema|imagen|tabla|ilustraci[oó]n|representaci[oó]n gr[aá]fica)"
    r"|informaci[oó]n de la tabla|siguiente es (un|una) (esquema|representaci[oó]n)"
    r"|en la (figura|imagen|gr[aá]fica|tabla)",
    re.I)


def main():
    banco = pd.read_csv(BANCO, encoding="utf-8-sig")
    previo = {}
    if CLAVE.exists():
        p = pd.read_csv(CLAVE, encoding="utf-8-sig", sep=None, engine="python", dtype=str).fillna("")
        previo = p.set_index("id").to_dict("index")
    filas = []
    for r in banco.itertuples():
        texto = " ".join(str(getattr(r, c)) for c in ["enunciado", "opcion_a", "opcion_b", "opcion_c", "opcion_d"])
        auto = "1" if FIGURA.search(texto) else "0"
        ant = previo.get(r.id, {})
        filas.append({"id": r.id,
                      "respuesta_correcta": ant.get("respuesta_correcta", "").strip() or CORRECTA_DATASET,
                      "requiere_figura": ant.get("requiere_figura", auto) or auto,
                      "nota": " ".join(str(r.enunciado).split())[:80]})
    CLAVE.parent.mkdir(exist_ok=True)
    out = pd.DataFrame(filas)
    out.to_csv(CLAVE, index=False, encoding="utf-8-sig")
    fig = out[out.requiere_figura == "1"]
    print(f"Plantilla en {CLAVE}")
    print(f"  preguntas: {len(out)} | con respuesta: {(out.respuesta_correcta != '').sum()} | "
          f"posiblemente con figura: {len(fig)}")
    print("  con figura (agrega static/img/preguntas/<id>.png o se omiten):", ", ".join(fig.id))
    por_eje = banco.assign(f=banco.id.isin(fig.id)).groupby("eje_tematico").f.agg(["size", "sum"])
    print(por_eje.rename(columns={"size": "preguntas", "sum": "con_figura"}).to_string())


if __name__ == "__main__":
    main()
