"""Capa de aplicación: conecta el motor adaptativo con la base de datos y prepara los datos para las vistas."""
from __future__ import annotations

import json
import random
import threading
from dataclasses import asdict

from agli_engine import AdaptiveEngine, EngineParams, StudentState, Recommendation
from agli_engine import gamification as gm
from agli_engine.bandit_module import LinUCB, FEATURE_NAMES
from models import db, Usuario, Respuesta, Insignia, EstadoMotor
from . import insignias as ins
from .banco import kc_nombre, kc_slug

# --- geometría de la "colonia": 20 células en rejilla de 5x4 que se tiñen del centro hacia afuera
N_CEL = 20
_pos = [(r, c) for r in range(4) for c in range(5)]
_orden = sorted(range(N_CEL), key=lambda i: ((_pos[i][0] - 1.5) ** 2 + (_pos[i][1] - 2.0) ** 2, i))
RANK = [0] * N_CEL
for _k, _i in enumerate(_orden):
    RANK[_i] = _k
_rng = random.Random(11)
JITTER = [(round(_rng.uniform(-14, 14), 1), round(_rng.uniform(-14, 14), 1), round(_rng.uniform(.80, 1.0), 2))
          for _ in range(N_CEL)]


def celulas(pl: float) -> list[dict]:
    n_on = round(pl * N_CEL)
    return [{"rank": RANK[i], "on": RANK[i] < n_on, "dx": JITTER[i][0], "dy": JITTER[i][1], "s": JITTER[i][2]}
            for i in range(N_CEL)]


class Juego:
    def __init__(self, params_path, banco, sesion_len: int):
        self.banco, self.sesion_len = banco, sesion_len
        self.params = EngineParams.load(params_path)
        self.engine = AdaptiveEngine(self.params, activos=banco.activos)
        self.lock = threading.RLock()
        self.catalogo = ins.catalogo()
        self.boss_len = self.params.hyper["boss_len"]
        self.boss_pass = self.params.hyper["boss_pass"]

    # ------------------------------------------------------- estado compartido del bandido
    def cargar_global(self) -> None:
        fila = db.session.get(EstadoMotor, 1)
        if fila:
            b = json.loads(fila.bandit_json)
            if b["d"] == len(FEATURE_NAMES):
                self.engine.bandit = LinUCB.from_dict(b)
                self.engine.exposures = json.loads(fila.exposures_json)

    def _guardar_global(self) -> None:
        fila = db.session.get(EstadoMotor, 1) or EstadoMotor(id=1, bandit_json="", exposures_json="")
        fila.bandit_json = json.dumps(self.engine.bandit.to_dict())
        fila.exposures_json = json.dumps(self.engine.exposures)
        db.session.add(fila)

    # ------------------------------------------------------------------ usuarios
    def estado(self, u: Usuario) -> StudentState:
        return StudentState.from_dict(json.loads(u.estado_json))

    def obtener_o_crear(self, alias: str) -> Usuario:
        u = Usuario.query.filter(db.func.lower(Usuario.alias) == alias.lower()).first()
        if not u:
            u = Usuario(alias=alias, estado_json=json.dumps(self.engine.new_student().to_dict()))
            db.session.add(u)
            db.session.commit()
        return u

    # ------------------------------------------------------------- flujo de práctica
    def pregunta_actual(self, u: Usuario):
        with self.lock:
            st = self.estado(u)
            rec = None
            if u.rec_json:
                d = json.loads(u.rec_json)
                if d["item_id"] in self.banco.activos:
                    rec = Recommendation(**d)
            if rec is None:
                rec = self.engine.next_item(st)
                u.rec_json = json.dumps(asdict(rec))
                db.session.commit()
            return rec, st

    def responder(self, u: Usuario, opcion: str, tiempo_ms: int):
        with self.lock:
            if not u.rec_json:
                return None
            rec = Recommendation(**json.loads(u.rec_json))
            item = self.banco.items[rec.item_id]
            st = self.estado(u)
            correcta = opcion == item["clave"]
            pl_antes, racha_antes, xp_antes = st.p_l[rec.kc], st.streak, st.xp
            fb = self.engine.submit(st, rec, correcta)

            u.sesion_n += 1
            n_resp = Respuesta.query.filter_by(usuario_id=u.id).count() + 1
            n_ok = Respuesta.query.filter_by(usuario_id=u.id, correcta=True).count() + int(correcta)
            ya = {i.codigo for i in Insignia.query.filter_by(usuario_id=u.id)}
            nuevas = ins.evaluar(ya=ya, n_respuestas=n_resp, n_correctas=n_ok, mejor_racha=st.best_streak,
                                 nivel=fb["nivel"], correcta=correcta, dificultad=item["dificultad"],
                                 eventos=fb["eventos"], sesion_completa=u.sesion_n >= self.sesion_len)
            for c in nuevas:
                db.session.add(Insignia(usuario_id=u.id, codigo=c))

            resp = Respuesta(
                usuario_id=u.id, sesion_num=u.sesion_num, item_id=item["id"], kc=item["kc"],
                dificultad=item["dificultad"], opcion=opcion, correcta=correcta, tiempo_ms=tiempo_ms,
                p_pred=rec.p_pred, theta=fb["theta"], p_l=fb["P_L"][rec.kc], xp=fb["xp"], racha=fb["racha"],
                es_exploracion=rec.is_exploration, es_jefe=rec.is_boss,
                fb_json=json.dumps({
                    "eventos": fb["eventos"], "insignias": nuevas, "pl_antes": pl_antes,
                    "pl_despues": fb["P_L"][rec.kc], "racha_antes": racha_antes, "clave": item["clave"],
                    "xp_total": fb["xp_total"], "nivel": fb["nivel"], "nivel_antes": gm.nivel(xp_antes),
                    "clave_demo": item["clave_demo"],
                }))
            db.session.add(resp)
            u.estado_json = json.dumps(st.to_dict())
            u.rec_json = None
            self._guardar_global()
            db.session.commit()
            return resp

    def nueva_sesion(self, u: Usuario) -> None:
        u.sesion_num += 1
        u.sesion_n = 0
        u.sesion_xp0 = self.estado(u).xp
        db.session.commit()

    # ----------------------------------------------------------- datos para las vistas
    def colonia(self, kc: str, st: StudentState, pl: float | None = None) -> dict:
        pl = st.p_l[kc] if pl is None else pl
        return {"kc": kc, "slug": kc_slug(kc), "nombre": kc_nombre(kc), "pl": pl, "pct": round(pl * 100),
                "n_on": round(pl * N_CEL), "dominado": kc in st.dominados, "celulas": celulas(pl)}

    def panel(self, st: StudentState) -> dict:
        xp_nivel = st.xp % gm.XP_POR_NIVEL
        return {"nivel": gm.nivel(st.xp), "xp": st.xp, "xp_nivel": xp_nivel, "xp_meta": gm.XP_POR_NIVEL,
                "pct_xp": round(100 * xp_nivel / gm.XP_POR_NIVEL), "racha": st.streak,
                "mejor_racha": st.best_streak,
                "colonias": [self.colonia(k, st) for k in self.engine.kcs_activos]}

    def segmentos(self, u: Usuario) -> list:
        """Un valor por pregunta de la sesión: True acierto, False error, None pendiente."""
        rs = (Respuesta.query.filter_by(usuario_id=u.id, sesion_num=u.sesion_num)
              .order_by(Respuesta.id).all())
        seg = [r.correcta for r in rs][: self.sesion_len]
        return seg + [None] * (self.sesion_len - len(seg))

    def textos_eventos(self, eventos: list[str]) -> list[dict]:
        out = []
        for e in eventos:
            tipo, _, kc = e.partition(":")
            nombre = kc_nombre(kc) if kc else ""
            if tipo == "racha_protegida":
                out.append({"tipo": "proteccion", "texto": "Racha protegida: era un reto extra, tu racha sigue intacta."})
            elif tipo == "jefe_desbloqueado":
                out.append({"tipo": "jefe", "texto": f"Desbloqueaste el jefe de «{nombre}». Las próximas "
                            f"{self.boss_len} preguntas son difíciles: acierta {self.boss_pass} para dominar el eje."})
            elif tipo == "kc_dominado":
                out.append({"tipo": "dominio", "texto": f"Dominas «{nombre}»."})
            elif tipo == "jefe_fallido":
                out.append({"tipo": "fallo", "texto": f"El jefe de «{nombre}» te ganó esta vez. Sigue practicando el eje y vuelve a enfrentarlo."})
        return out

    def resumen_sesion(self, u: Usuario, st: StudentState) -> dict:
        rs = (Respuesta.query.filter_by(usuario_id=u.id, sesion_num=u.sesion_num)
              .order_by(Respuesta.id).all())
        nuevas = []
        for r in rs:
            nuevas += json.loads(r.fb_json)["insignias"]
        return {"n": len(rs), "aciertos": sum(r.correcta for r in rs),
                "xp": st.xp - u.sesion_xp0, "mejor_racha": max([r.racha for r in rs] or [0]),
                "ejes": sorted({kc_nombre(r.kc) for r in rs}),
                "insignias": [dict(self.catalogo[c], codigo=c) for c in nuevas if c in self.catalogo],
                "segmentos": [r.correcta for r in rs]}

    def vista_progreso(self, u: Usuario, st: StudentState) -> dict:
        todas = Respuesta.query.filter_by(usuario_id=u.id).order_by(Respuesta.id.desc()).all()
        ganadas = {i.codigo: i.obtenida for i in Insignia.query.filter_by(usuario_id=u.id)}
        medallas = [dict(v, codigo=k, ganada=k in ganadas) for k, v in self.catalogo.items()]
        return {"total": len(todas), "aciertos": sum(r.correcta for r in todas),
                "pct": round(100 * sum(r.correcta for r in todas) / len(todas)) if todas else 0,
                "recientes": todas[:12], "medallas": medallas, "n_medallas": len(ganadas)}
