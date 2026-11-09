"""Prueba de humo del flujo completo con el cliente de Flask (modo demo, base de datos temporal).
Uso: python prueba_flujo.py"""
import random
import re
import tempfile
from pathlib import Path

from app import create_app

tmp = Path(tempfile.mkdtemp()) / "prueba.db"
app = create_app({"DEMO": True, "TESTING": True, "ADMIN_TOKEN": "t0ken",
                  "SQLALCHEMY_DATABASE_URI": "sqlite:///" + tmp.as_posix()})
c = app.test_client()
rng = random.Random(3)


def csrf(html):
    return re.search(r'name="csrf" value="([^"]+)"', html).group(1)


def ok(r, donde):
    assert r.status_code == 200, f"{donde}: {r.status_code}"
    return r.get_data(as_text=True)


# acceso sin sesión -> redirige
assert c.get("/practicar").status_code == 302
# CSRF ausente -> 400
assert c.post("/entrar", data={"alias": "x"}).status_code == 400

html = ok(c.get("/entrar"), "entrar")
assert 'name="alias"' in html
r = c.post("/entrar", data={"alias": "<script>", "csrf": csrf(html)})
assert "Escribe un alias" in ok(r, "alias inválido")
r = c.post("/entrar", data={"alias": "Sofía", "csrf": csrf(html)})
assert r.status_code == 302

eventos, jefes, sesiones = set(), 0, 1
for n in range(1, 26):
    r = c.get("/practicar")
    if r.status_code == 302:                                  # sesión completa -> resumen -> nueva sesión
        res = ok(c.get("/resumen"), "resumen")
        assert "Terminaste la sesión" in res
        c.post("/nueva-sesion", data={"csrf": csrf(res)})
        sesiones += 1
        r = c.get("/practicar")
    html = ok(r, "practicar")
    letras = re.findall(r'name="opcion" value="([A-D])"', html)
    assert letras == ["A", "B", "C", "D"], letras
    jefes += "jefe-banda" in html
    r = c.post("/responder", data={"opcion": rng.choice(letras), "tiempo_ms": rng.randint(2000, 40000),
                                   "csrf": csrf(html)})
    assert r.status_code == 302 and r.headers["Location"].endswith("/resultado")
    res = ok(c.get("/resultado"), "resultado")
    assert "veredicto" in res
    for e in re.findall(r'class="(ev-\w+)"', res):
        eventos.add(e)
    # recargar /practicar sin responder no debe cambiar la pregunta
html1 = ok(c.get("/practicar"), "p1")
html2 = ok(c.get("/practicar"), "p2")
assert re.search(r'<p>(.{30})', html1.split('class="enunciado"')[1]).group(1) == \
       re.search(r'<p>(.{30})', html2.split('class="enunciado"')[1]).group(1), "la pregunta cambió al recargar"

prog = ok(c.get("/progreso"), "progreso")
assert "Tus colonias" in prog and "Insignias" in prog
# POST sin opción válida no rompe
r = c.post("/responder", data={"opcion": "Z", "csrf": csrf(html1)})
assert r.status_code == 302

# exportación protegida
assert c.get("/admin/exportar").status_code == 404
assert c.get("/admin/exportar?token=mal").status_code == 404
exp = ok(c.get("/admin/exportar?token=t0ken"), "exportar")
filas = exp.strip().splitlines()
print("filas exportadas:", len(filas) - 1, "| columnas:", len(filas[0].split(",")))
assert len(filas) - 1 == 25

assert c.get("/salir").status_code == 302
print("sesiones:", sesiones, "| preguntas de jefe vistas:", jefes, "| tipos de evento:", sorted(eventos))
print("OK: flujo completo sin errores")
