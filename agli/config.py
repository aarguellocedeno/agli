import os
from pathlib import Path

BASE = Path(__file__).resolve().parent


class Config:
    SECRET_KEY = os.environ.get("AGLI_SECRET", "cambia-esta-clave-en-produccion")
    SQLALCHEMY_DATABASE_URI = "sqlite:///" + (BASE / "instance" / "agli.db").as_posix()
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    SESION_LEN = 10                                   # preguntas por sesión de repaso
    # AGLI_DEMO=1 rellena claves faltantes con letras de PRUEBA (no verificadas). Solo para ver la app.
    DEMO = os.environ.get("AGLI_DEMO", "0") == "1"
    # Token para /admin/exportar (CSV con todas las respuestas). Sin token, la ruta no existe.
    ADMIN_TOKEN = os.environ.get("AGLI_ADMIN_TOKEN")

    RUTA_BANCO = BASE / "banco_biologia_81_dificultad.csv"
    RUTA_CLAVE = BASE / "data" / "clave_respuestas.csv"
    DIR_IMAGENES = BASE / "static" / "img" / "preguntas"
    RUTA_PARAMS = BASE / "params" / "engine_params.json"
