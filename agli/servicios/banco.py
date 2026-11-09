"""Banco de preguntas + clave de respuestas + imágenes. Decide qué preguntas están 'activas'.

Una pregunta está activa si tiene respuesta correcta (A-D) y, cuando depende de una figura, existe su imagen
en static/img/preguntas/<id>.(png|jpg|jpeg|webp|svg). En modo demo, la clave faltante se rellena con letras
de prueba (no verificadas) para poder ver la app.

La clave (data/clave_respuestas.csv) usa las letras del ORDEN ORIGINAL del dataset (columnas opcion_a..opcion_d).
En el dataset la correcta es siempre opcion_a, así que en pantalla las opciones se reordenan: la correcta queda
repartida de forma pareja entre A, B, C y D. El orden es fijo por pregunta (igual para todos y en cada recarga),
así la letra guardada en cada respuesta siempre significa lo mismo.
"""
from __future__ import annotations

import hashlib
import random
import re
from pathlib import Path

import pandas as pd

# slug estable, nombre corto para la interfaz
KC_INFO = {
    "Intercambio de energía entre los ecosistemas": ("energia", "Intercambio de energía"),
    "Procesos vitales y organización de los seres vivos": ("procesos", "Procesos vitales"),
    "Relación entre seres vivos y ecosistemas del mundo": ("relacion", "Seres vivos y ecosistemas"),
    "Herencia y mecanismos de evolución": ("herencia", "Herencia y evolución"),
}
SEMILLA_ORDEN = 7  # cambiarla reordena todas las opciones en pantalla
EXT = ("png", "jpg", "jpeg", "webp", "svg")
FIGURA = re.compile(
    r"(siguiente|anterior)\s+(figura|gr[aá]fica|esquema|imagen|tabla|ilustraci[oó]n|representaci[oó]n gr[aá]fica)"
    r"|informaci[oó]n de la tabla|siguiente es (un|una) (esquema|representaci[oó]n)"
    r"|en la (figura|imagen|gr[aá]fica|tabla)", re.I)


def kc_slug(kc: str) -> str:
    return KC_INFO.get(kc, (re.sub(r"\W+", "_", kc.lower())[:20], kc))[0]


def kc_nombre(kc: str) -> str:
    return KC_INFO.get(kc, (None, kc))[1]


class Banco:
    def __init__(self, ruta_banco: Path, ruta_clave: Path, dir_img: Path, demo: bool = False):
        # sep=None: acepta coma o punto y coma (Excel en español guarda con ;)
        df = pd.read_csv(ruta_banco, encoding="utf-8-sig", sep=None, engine="python")
        clave = self._leer_clave(ruta_clave)
        self.items: dict[str, dict] = {}
        self.sin_clave: list[str] = []
        self.sin_imagen: list[str] = []
        self.demo = demo
        posiciones = self._posiciones_equilibradas(list(df.id))
        for r in df.itertuples():
            c = clave.get(r.id, {})
            letra = str(c.get("respuesta_correcta", "")).strip().upper()
            letra = letra if letra in ("A", "B", "C", "D") else ""
            demo_letra = False
            if not letra and demo:
                letra, demo_letra = "ABCD"[int(hashlib.md5(r.id.encode()).hexdigest(), 16) % 4], True
            texto = " ".join(str(getattr(r, k)) for k in
                             ["enunciado", "opcion_a", "opcion_b", "opcion_c", "opcion_d"])
            flag = str(c.get("requiere_figura", "")).strip()
            requiere = (flag == "1") if flag in ("0", "1") else bool(FIGURA.search(texto))
            imagen = next((f"{r.id}.{e}" for e in EXT if (dir_img / f"{r.id}.{e}").exists()), None)
            activa = bool(letra) and (not requiere or imagen is not None)
            if not letra:
                self.sin_clave.append(r.id)
            elif requiere and imagen is None:
                self.sin_imagen.append(r.id)
            originales = {"A": str(r.opcion_a), "B": str(r.opcion_b),
                          "C": str(r.opcion_c), "D": str(r.opcion_d)}
            opciones, clave_vista = self._reordenar(r.id, originales, letra, posiciones[r.id])
            self.items[r.id] = {
                "id": r.id, "enunciado": str(r.enunciado).strip(), "kc": r.eje_tematico,
                "competencia": r.competencia_men, "dificultad": int(r.dificultad),
                "opciones": opciones, "clave_original": letra,
                "clave": clave_vista, "clave_demo": demo_letra, "requiere_figura": requiere,
                "imagen": imagen, "activa": activa,
            }
        self.activos = {i for i, it in self.items.items() if it["activa"]}

    @staticmethod
    def _posiciones_equilibradas(ids: list[str]) -> dict[str, str]:
        """Letra donde se mostrará la respuesta correcta de cada pregunta: ~25 % en cada letra."""
        letras = list("ABCD" * (len(ids) // 4 + 1))[: len(ids)]
        random.Random(SEMILLA_ORDEN).shuffle(letras)
        return dict(zip(ids, letras))

    @staticmethod
    def _reordenar(item_id: str, originales: dict, correcta: str, destino: str) -> tuple[dict, str]:
        """Pone la opción correcta en `destino` y baraja las demás (orden fijo por pregunta)."""
        if not correcta:
            return originales, ""
        otras = [originales[k] for k in "ABCD" if k != correcta]
        random.Random(f"{SEMILLA_ORDEN}:{item_id}").shuffle(otras)
        orden = iter(otras)
        return {k: (originales[correcta] if k == destino else next(orden)) for k in "ABCD"}, destino

    @staticmethod
    def _leer_clave(ruta: Path) -> dict:
        if not Path(ruta).exists():
            return {}
        # sep=None: acepta coma o punto y coma (Excel en español guarda con ;)
        d = pd.read_csv(ruta, encoding="utf-8-sig", sep=None, engine="python", dtype=str).fillna("")
        d.columns = [c.strip() for c in d.columns]
        return d.set_index("id").to_dict("index")

    def resumen(self) -> str:
        n = len(self.items)
        s = [f"Banco: {len(self.activos)} de {n} preguntas activas."]
        if self.sin_clave:
            s.append(f"  Sin respuesta correcta en data/clave_respuestas.csv: {len(self.sin_clave)} preguntas.")
        if self.sin_imagen:
            s.append(f"  Requieren figura y no tienen imagen en static/img/preguntas/: "
                     f"{', '.join(self.sin_imagen)}")
        if self.demo:
            s.append("  MODO DEMO: las respuestas faltantes son letras de prueba, no verificadas.")
        return "\n".join(s)
