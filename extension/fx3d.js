// Krypton 3D effects: tilting cards, a spinning crystal logo, and a 🧊 on/off switch.
// Built to fail quietly: if anything goes wrong the page simply stays flat.
(() => {
  try {
    const touch = matchMedia("(hover: none)").matches || /iPhone|iPad|iPod/.test(navigator.userAgent);
    const reduced = matchMedia("(prefers-reduced-motion: reduce)").matches;
    let on = true;
    try { on = localStorage.getItem("krypton.3d") !== "off"; } catch (e) { /* storage blocked */ }
    const root = document.documentElement;
    const setOn = v => {
      on = v;
      root.classList.toggle("fx3d", v);
      try { localStorage.setItem("krypton.3d", v ? "on" : "off"); } catch (e) { /* ignore */ }
      document.querySelectorAll(".fx3d-toggle").forEach(b => { b.textContent = v ? "🧊 3D: on" : "🧊 3D: off"; });
    };
    setOn(on && !reduced);

    // ---------- tilt toward the mouse ----------
    const SEL = ".card:not(.ctx):not(.chat):not(.mapwrap), .wordcard, .day, .bdg, .kpi, .term, .line, .flip, .gamebox, .stat, .letter";
    let current = null, frame = 0, lastEv = null;
    const reset = el => { if (!el) return; el.style.removeProperty("--rx"); el.style.removeProperty("--ry"); el.classList.remove("lift"); };
    const apply = () => {
      frame = 0;
      const e = lastEv, el = current;
      if (!el || !e) return;
      const r = el.getBoundingClientRect();
      const px = (e.clientX - r.left) / r.width, py = (e.clientY - r.top) / r.height;
      const strength = r.height > 420 ? 1.5 : r.height > 220 ? 3.5 : 7;   // big panels barely move
      el.style.setProperty("--ry", `${((px - 0.5) * 2 * strength).toFixed(2)}deg`);
      el.style.setProperty("--rx", `${((0.5 - py) * 2 * strength).toFixed(2)}deg`);
      el.style.setProperty("--mx", `${(px * 100).toFixed(1)}%`);
      el.style.setProperty("--my", `${(py * 100).toFixed(1)}%`);
    };
    if (!touch) {
      document.addEventListener("mousemove", e => {
        if (!on) return;
        const el = e.target.closest?.(SEL);
        if (el !== current) {
          reset(current);
          current = el;
          if (el) { el.classList.add("tilt", "lift"); }
        }
        lastEv = e;
        if (current && !frame) frame = requestAnimationFrame(apply);
      }, { passive: true });
      document.addEventListener("mouseleave", () => { reset(current); current = null; });
    }

    // ---------- spinning crystal (pure canvas, no libraries) ----------
    const V = [[0, 1.25, 0], [0, -1.25, 0], [1, 0, 0], [-1, 0, 0], [0, 0, 1], [0, 0, -1]];
    const F = [[0, 2, 4], [0, 4, 3], [0, 3, 5], [0, 5, 2], [1, 4, 2], [1, 3, 4], [1, 5, 3], [1, 2, 5]];
    const css = name => getComputedStyle(root).getPropertyValue(name).trim();
    function hexRgb(h) {
      const m = h.replace("#", "").match(/^([0-9a-f]{2})([0-9a-f]{2})([0-9a-f]{2})$/i);
      return m ? m.slice(1).map(x => parseInt(x, 16)) : [92, 255, 106];
    }
    function crystal(canvas, size) {
      const dpr = Math.min(2, devicePixelRatio || 1);
      canvas.width = canvas.height = size * dpr;
      canvas.style.width = canvas.style.height = size + "px";
      const ctx = canvas.getContext("2d");
      let t = Math.random() * 6, running = true;
      const draw = () => {
        if (!running) return;
        if (!canvas.isConnected) { running = false; return; }
        const cols = [css("--lime"), css("--accent"), css("--accent2")].map(hexRgb);
        const s = size * dpr, cx = s / 2, cy = s / 2, k = s * 0.36;
        const ay = t, ax = 0.45 + Math.sin(t * 0.7) * 0.15;
        const P = V.map(([x, y, z]) => {
          let x1 = x * Math.cos(ay) + z * Math.sin(ay), z1 = -x * Math.sin(ay) + z * Math.cos(ay);
          let y1 = y * Math.cos(ax) - z1 * Math.sin(ax), z2 = y * Math.sin(ax) + z1 * Math.cos(ax);
          return [x1, y1, z2];
        });
        ctx.clearRect(0, 0, s, s);
        F.map(f => ({ f, z: (P[f[0]][2] + P[f[1]][2] + P[f[2]][2]) / 3 }))
          .sort((a, b) => a.z - b.z)
          .forEach(({ f }, i) => {
            const [a, b, c] = f.map(n => P[n]);
            const ux = b[0] - a[0], uy = b[1] - a[1], uz = b[2] - a[2], vx = c[0] - a[0], vy = c[1] - a[1], vz = c[2] - a[2];
            const nx = uy * vz - uz * vy, ny = uz * vx - ux * vz, nz = ux * vy - uy * vx, len = Math.hypot(nx, ny, nz) || 1;
            const light = Math.max(0.25, (nx * -0.3 + ny * 0.6 + nz * 0.75) / len);
            const col = cols[i % 3];
            ctx.beginPath();
            [a, b, c].forEach(([x, y], j) => (j ? ctx.lineTo : ctx.moveTo).call(ctx, cx + x * k, cy - y * k));
            ctx.closePath();
            ctx.fillStyle = `rgba(${col.map(v => Math.min(255, Math.round(v * light + 30 * light))).join(",")},0.92)`;
            ctx.fill();
            ctx.strokeStyle = "rgba(255,255,255,0.35)";
            ctx.lineWidth = dpr * 0.8;
            ctx.stroke();
          });
        t += on ? 0.018 : 0;
        requestAnimationFrame(draw);
      };
      draw();
    }
    function mountCrystals() {
      // Replace the flat diamond logo next to "KRYPTON" with a spinning 3D crystal (not on phones: keep them light)
      if (touch) return;
      document.querySelectorAll(".brand > .gem").forEach(g => {
        const c = document.createElement("canvas");
        c.className = "crystal3d";
        const big = g.closest(".gate, body > .card") || document.title.includes("Sign in");
        g.replaceWith(c);
        crystal(c, big ? 46 : 30);
      });
    }

    // ---------- the 🧊 switch (added to the sidebar / popup automatically) ----------
    function mountToggle() {
      const host = document.querySelector(".side-foot") || document.querySelector(".actions");
      if (!host || host.querySelector(".fx3d-toggle")) return;
      const b = document.createElement("button");
      b.type = "button";
      b.className = "btn-ghost fx3d-toggle";
      b.textContent = on ? "🧊 3D: on" : "🧊 3D: off";
      b.onclick = () => setOn(!on);
      host.appendChild(b);
    }

    const start = () => { try { mountCrystals(); mountToggle(); } catch (e) { /* stay flat */ } };
    document.readyState === "loading" ? document.addEventListener("DOMContentLoaded", start) : start();
  } catch (e) {
    document.documentElement.classList.remove("fx3d");  // anything odd: flat, normal Krypton
  }
})();
