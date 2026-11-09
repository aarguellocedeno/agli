(function () {
  "use strict";

  // Pregunta: habilitar "Comprobar", medir tiempo de respuesta, atajos A-D.
  var form = document.getElementById("form-pregunta");
  if (form) {
    var inicio = performance.now();
    var boton = document.getElementById("comprobar");
    var tiempo = document.getElementById("tiempo_ms");
    var radios = form.querySelectorAll('input[name="opcion"]');

    radios.forEach(function (r) {
      r.addEventListener("change", function () { boton.disabled = false; });
    });
    form.addEventListener("submit", function () {
      tiempo.value = Math.round(performance.now() - inicio);
      boton.disabled = true;           // evita doble envío
    });
    document.addEventListener("keydown", function (e) {
      if (e.ctrlKey || e.metaKey || e.altKey) return;
      var letra = e.key.toUpperCase();
      if (["A", "B", "C", "D"].indexOf(letra) === -1) return;
      var r = form.querySelector('input[name="opcion"][value="' + letra + '"]');
      if (r) { r.checked = true; r.dispatchEvent(new Event("change", { bubbles: true })); }
    });
  }

  var menosMovimiento = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

  // Acierto o sesión completa: lluvia de células y hojas.
  var confeti = document.querySelector(".confeti[data-fiesta]");
  if (confeti && !menosMovimiento) {
    var colores = ["#34C98A", "#7EE2C4", "#FFC23D", "#F7A3C6", "#7C6BE0", "#A6E07A", "#4FC3D1", "#F27365"];
    for (var i = 0; i < 46; i++) {
      var p = document.createElement("i");
      if (Math.random() < 0.4) p.className = "hoja";
      p.style.setProperty("--x", (Math.random() * 100).toFixed(1) + "vw");
      p.style.setProperty("--t", (8 + Math.random() * 12).toFixed(0) + "px");
      p.style.setProperty("--c", colores[i % colores.length]);
      p.style.setProperty("--d", (2.2 + Math.random() * 1.8).toFixed(2) + "s");
      p.style.setProperty("--w", (Math.random() * 0.6).toFixed(2) + "s");
      p.style.setProperty("--vx", ((Math.random() - 0.5) * 160).toFixed(0) + "px");
      p.style.setProperty("--rot", ((Math.random() - 0.5) * 900).toFixed(0) + "deg");
      confeti.appendChild(p);
    }
    setTimeout(function () { confeti.innerHTML = ""; }, 5000);
  }

  // Resultado: el XP sube hasta su valor (solo si la persona no pidió menos movimiento).
  var xp = document.querySelector(".xp-num");
  if (xp && !menosMovimiento) {
    var meta = parseInt(xp.getAttribute("data-valor"), 10);
    var t0 = performance.now();
    (function paso(ahora) {
      var p = Math.min(1, (ahora - t0) / 700);
      xp.textContent = "+" + Math.round(meta * (1 - Math.pow(1 - p, 3)));
      if (p < 1) requestAnimationFrame(paso);
    })(t0);
  }
})();
