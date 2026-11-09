from datetime import datetime

from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()


class Usuario(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    alias = db.Column(db.String(30), unique=True, nullable=False, index=True)   # sin nombres reales
    estado_json = db.Column(db.Text, nullable=False)      # StudentState (BKT, theta, XP, racha, jefe)
    rec_json = db.Column(db.Text)                         # pregunta pendiente (sobrevive a recargar la página)
    sesion_num = db.Column(db.Integer, default=1, nullable=False)
    sesion_n = db.Column(db.Integer, default=0, nullable=False)   # preguntas respondidas en la sesión actual
    sesion_xp0 = db.Column(db.Integer, default=0, nullable=False)
    creado = db.Column(db.DateTime, default=datetime.utcnow)


class Respuesta(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    usuario_id = db.Column(db.Integer, db.ForeignKey("usuario.id"), index=True, nullable=False)
    sesion_num = db.Column(db.Integer, nullable=False)
    item_id = db.Column(db.String(10), nullable=False)
    kc = db.Column(db.String(80), nullable=False)
    dificultad = db.Column(db.Integer)
    opcion = db.Column(db.String(1), nullable=False)
    correcta = db.Column(db.Boolean, nullable=False)
    tiempo_ms = db.Column(db.Integer)
    p_pred = db.Column(db.Float)               # P(acierto) que predijo el motor antes de responder
    theta = db.Column(db.Float)                # habilidad IRT después de responder
    p_l = db.Column(db.Float)                  # P(dominio) del eje después de responder
    xp = db.Column(db.Integer, default=0)
    racha = db.Column(db.Integer, default=0)
    es_exploracion = db.Column(db.Boolean, default=False)
    es_jefe = db.Column(db.Boolean, default=False)
    fb_json = db.Column(db.Text)               # eventos, insignias nuevas, P(L) antes/después
    creado = db.Column(db.DateTime, default=datetime.utcnow)


class Insignia(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    usuario_id = db.Column(db.Integer, db.ForeignKey("usuario.id"), index=True, nullable=False)
    codigo = db.Column(db.String(40), nullable=False)
    obtenida = db.Column(db.DateTime, default=datetime.utcnow)
    __table_args__ = (db.UniqueConstraint("usuario_id", "codigo"),)


class EstadoMotor(db.Model):
    """Estado compartido del bandido (una sola fila, id=1)."""
    id = db.Column(db.Integer, primary_key=True)
    bandit_json = db.Column(db.Text, nullable=False)
    exposures_json = db.Column(db.Text, nullable=False)
