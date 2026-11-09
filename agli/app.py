"""AGLI: aplicación web de repaso adaptativo y gamificado (Biología, grado 7).

Ejecutar:   python app.py      →  http://127.0.0.1:5000
Variables:  AGLI_DEMO=1 (claves de prueba) | AGLI_ADMIN_TOKEN=... (habilita /admin/exportar) | AGLI_SECRET=...
"""
import csv
import io
import json
import re
import secrets
from functools import wraps

from flask import (Flask, Response, abort, g, redirect, render_template, request, session, url_for)

from config import BASE, Config
from models import Respuesta, Usuario, db
from servicios.banco import Banco, kc_nombre, kc_slug
from servicios.juego import Juego, celulas

ALIAS_OK = re.compile(r"^[\w .\-áéíóúüñÁÉÍÓÚÜÑ]{2,20}$")


def create_app(overrides: dict | None = None) -> Flask:
    app = Flask(__name__)
    app.config.from_object(Config)
    if overrides:
        app.config.update(overrides)
    (BASE / "instance").mkdir(exist_ok=True)
    db.init_app(app)

    banco = Banco(app.config["RUTA_BANCO"], app.config["RUTA_CLAVE"], app.config["DIR_IMAGENES"],
                  app.config["DEMO"])
    print(banco.resumen())
    if not banco.activos:
        raise RuntimeError(
            "No hay preguntas activas. Ejecuta `python crear_clave.py`, completa la columna "
            "respuesta_correcta en data/clave_respuestas.csv (y agrega las imágenes de las preguntas con figura), "
            "o inicia con AGLI_DEMO=1 para ver la app con claves de prueba.")
    juego = Juego(app.config["RUTA_PARAMS"], banco, app.config["SESION_LEN"])
    with app.app_context():
        db.create_all()
        juego.cargar_global()

    # ------------------------------------------------------------------ utilidades
    @app.before_request
    def proteger_post():
        if request.method == "POST" and (not session.get("csrf") or request.form.get("csrf") != session["csrf"]):
            abort(400)

    @app.context_processor
    def globales():
        if "csrf" not in session:
            session["csrf"] = secrets.token_urlsafe(16)
        return {"csrf": session["csrf"], "demo": app.config["DEMO"], "sesion_len": app.config["SESION_LEN"],
                "kc_nombre": kc_nombre, "kc_slug": kc_slug}

    def requiere_usuario(f):
        @wraps(f)
        def wrapper(*a, **k):
            u = db.session.get(Usuario, session.get("uid")) if session.get("uid") else None
            if not u:
                session.pop("uid", None)
                return redirect(url_for("entrar"))
            g.u = u
            return f(*a, **k)
        return wrapper

    # --------------------------------------------------------------------- rutas
    @app.get("/")
    def inicio():
        return redirect(url_for("practicar" if session.get("uid") else "entrar"))

    @app.route("/entrar", methods=["GET", "POST"])
    def entrar():
        error = None
        if request.method == "POST":
            alias = re.sub(r"\s+", " ", request.form.get("alias", "")).strip()
            if ALIAS_OK.match(alias):
                session["uid"] = juego.obtener_o_crear(alias).id
                return redirect(url_for("practicar"))
            error = "Escribe un alias de 2 a 20 letras o números."
        deco = {"celulas": celulas(0.6), "nombre": "Colonia de ejemplo", "pct": 60}
        return render_template("entrar.html", error=error, deco=deco)

    @app.get("/salir")
    def salir():
        session.pop("uid", None)
        return redirect(url_for("entrar"))

    @app.get("/practicar")
    @requiere_usuario
    def practicar():
        u = g.u
        if u.sesion_n >= app.config["SESION_LEN"]:
            return redirect(url_for("resumen"))
        rec, st = juego.pregunta_actual(u)
        boss_pos = juego.boss_len - st.boss["restantes"] + 1 if (rec.is_boss and st.boss) else None
        return render_template("practicar.html", u=u, item=banco.items[rec.item_id], rec=rec, panel=juego.panel(st),
                               segmentos=juego.segmentos(u), n=u.sesion_n + 1, boss_pos=boss_pos,
                               boss_len=juego.boss_len)

    @app.post("/responder")
    @requiere_usuario
    def responder():
        opcion = request.form.get("opcion", "").upper()
        if opcion not in ("A", "B", "C", "D"):
            return redirect(url_for("practicar"))
        try:
            tiempo = max(0, min(int(request.form.get("tiempo_ms", 0)), 3_600_000))
        except ValueError:
            tiempo = 0
        resp = juego.responder(g.u, opcion, tiempo)
        return redirect(url_for("resultado" if resp else "practicar"))

    @app.get("/resultado")
    @requiere_usuario
    def resultado():
        u = g.u
        r = Respuesta.query.filter_by(usuario_id=u.id).order_by(Respuesta.id.desc()).first()
        if not r:
            return redirect(url_for("practicar"))
        fb = json.loads(r.fb_json)
        st = juego.estado(u)
        item = banco.items[r.item_id]
        niv = [{"tipo": "nivel", "texto": f"Subiste al nivel {fb['nivel']}."}] if fb["nivel"] > fb["nivel_antes"] else []
        return render_template(
            "resultado.html", u=u, r=r, fb=fb, item=item, panel=juego.panel(st),
            col=juego.colonia(r.kc, st, fb["pl_despues"]), desde=round(fb["pl_antes"] * 20),
            pct_antes=round(fb["pl_antes"] * 100), eventos=niv + juego.textos_eventos(fb["eventos"]),
            medallas=[dict(juego.catalogo[c], codigo=c) for c in fb["insignias"] if c in juego.catalogo],
            fin_sesion=u.sesion_n >= app.config["SESION_LEN"], segmentos=juego.segmentos(u))

    @app.get("/resumen")
    @requiere_usuario
    def resumen():
        u = g.u
        if u.sesion_n == 0:
            return redirect(url_for("practicar"))
        st = juego.estado(u)
        return render_template("resumen.html", u=u, panel=juego.panel(st), s=juego.resumen_sesion(u, st),
                               completa=u.sesion_n >= app.config["SESION_LEN"])

    @app.post("/nueva-sesion")
    @requiere_usuario
    def nueva_sesion():
        juego.nueva_sesion(g.u)
        return redirect(url_for("practicar"))

    @app.get("/progreso")
    @requiere_usuario
    def progreso():
        st = juego.estado(g.u)
        return render_template("progreso.html", u=g.u, panel=juego.panel(st), p=juego.vista_progreso(g.u, st),
                               banco=banco)

    @app.get("/admin/exportar")
    def exportar():
        token = app.config["ADMIN_TOKEN"]
        if not token or request.args.get("token") != token:
            abort(404)
        buf = io.StringIO()
        w = csv.writer(buf)
        w.writerow(["alias", "sesion", "item_id", "eje", "dificultad", "opcion", "correcta", "tiempo_ms",
                    "p_pred", "theta", "p_dominio_eje", "xp", "racha", "exploracion", "jefe", "fecha_utc"])
        filas = (db.session.query(Respuesta, Usuario.alias).join(Usuario, Usuario.id == Respuesta.usuario_id)
                 .order_by(Respuesta.id))
        for r, alias in filas:
            w.writerow([alias, r.sesion_num, r.item_id, r.kc, r.dificultad, r.opcion, int(r.correcta), r.tiempo_ms,
                        round(r.p_pred, 4), round(r.theta, 4), round(r.p_l, 4), r.xp, r.racha,
                        int(r.es_exploracion), int(r.es_jefe), r.creado.isoformat()])
        return Response("﻿" + buf.getvalue(), mimetype="text/csv; charset=utf-8",
                        headers={"Content-Disposition": "attachment; filename=agli_respuestas.csv"})

    return app


if __name__ == "__main__":
    create_app().run(debug=True)
