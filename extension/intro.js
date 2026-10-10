// Cinematic Krypton intro (~3 s): light streaks converge, a crystal forms, the letters reveal with a shine.
// Plays once per browser session, click anywhere to skip, and never blocks the app if something fails.
(() => {
  try {
    if (sessionStorage.getItem("krypton.intro")) return;
    sessionStorage.setItem("krypton.intro", "1");
  } catch (e) { return; }
  if (matchMedia("(prefers-reduced-motion: reduce)").matches) return;

  const css = name => getComputedStyle(document.documentElement).getPropertyValue(name).trim() || "#5cff6a";
  const el = document.createElement("div");
  el.id = "kintro";
  el.innerHTML = `
    <style>
      #kintro { position: fixed; inset: 0; z-index: 2147483646; background: #000; display: grid; place-items: center; overflow: hidden;
        cursor: pointer; transition: opacity .6s ease, transform .6s ease; font-family: "Segoe UI", system-ui, sans-serif; }
      #kintro.out { opacity: 0; transform: scale(1.06); pointer-events: none; }
      #kintro canvas { position: absolute; inset: 0; width: 100%; height: 100%; }
      #kintro .word { position: relative; display: flex; gap: .18em; font-size: clamp(34px, 7vw, 86px); font-weight: 800; letter-spacing: .12em;
        color: #fff; margin-top: 210px; }
      #kintro .word span { opacity: 0; transform: translateY(18px) scale(.9); filter: blur(6px);
        animation: kin .55s cubic-bezier(.2,.9,.3,1) forwards; text-shadow: 0 0 24px var(--kglow); }
      #kintro .word::after { content: ""; position: absolute; top: 0; bottom: 0; width: 30%; left: -40%;
        background: linear-gradient(100deg, transparent, rgba(255,255,255,.75), transparent); mix-blend-mode: overlay; animation: shine 1s 1.9s ease-in-out forwards; }
      #kintro .tag { position: absolute; bottom: 18%; color: rgba(255,255,255,.7); letter-spacing: .4em; font-size: 13px; text-transform: uppercase;
        opacity: 0; animation: fade .8s 2.1s forwards; }
      #kintro .skip { position: absolute; bottom: 22px; right: 26px; color: rgba(255,255,255,.35); font-size: 12px; letter-spacing: .1em; }
      @keyframes kin { to { opacity: 1; transform: none; filter: none; } }
      @keyframes shine { to { left: 120%; } }
      @keyframes fade { to { opacity: 1; } }
    </style>
    <canvas></canvas>
    <div class="word">${[..."KRYPTON"].map((c, i) => `<span style="animation-delay:${1.05 + i * 0.09}s">${c}</span>`).join("")}</div>
    <div class="tag">Study smarter · Scroll less</div>
    <div class="skip">click to skip</div>`;
  const glow = css("--accent");
  el.style.setProperty("--kglow", glow);
  (document.body || document.documentElement).appendChild(el);

  const cv = el.querySelector("canvas"), ctx = cv.getContext("2d");
  const dpr = Math.min(2, devicePixelRatio || 1);
  const size = () => { cv.width = innerWidth * dpr; cv.height = innerHeight * dpr; };
  size();
  const hex = h => { const m = h.replace("#", "").match(/^(..)(..)(..)$/); return m ? m.slice(1).map(x => parseInt(x, 16)) : [92, 255, 106]; };
  const cols = [css("--lime"), css("--accent"), css("--accent2")].map(hex);
  const N = 70, streaks = Array.from({ length: N }, (_, i) => ({ a: Math.random() * Math.PI * 2, r: 1.2 + Math.random(), sp: 0.6 + Math.random() * 0.8, c: cols[i % 3] }));
  const V = [[0, 1.3, 0], [0, -1.3, 0], [1, 0, 0], [-1, 0, 0], [0, 0, 1], [0, 0, -1]];
  const F = [[0, 2, 4], [0, 4, 3], [0, 3, 5], [0, 5, 2], [1, 4, 2], [1, 3, 4], [1, 5, 3], [1, 2, 5]];
  const t0 = performance.now();
  let done = false;

  function frame(now) {
    if (done) return;
    const t = (now - t0) / 1000, w = cv.width, h = cv.height, cx = w / 2, cy = h / 2 - 40 * dpr, R = Math.min(w, h) * 0.45;
    ctx.fillStyle = "rgba(0,0,0,0.28)";
    ctx.fillRect(0, 0, w, h);
    // 1) streaks rush inward (0 - 1.1 s)
    const p = Math.min(1, t / 1.1);
    streaks.forEach(s => {
      const d = R * s.r * (1 - p * s.sp * 1.15);
      if (d <= 0) return;
      const x = cx + Math.cos(s.a) * d, y = cy + Math.sin(s.a) * d;
      const x2 = cx + Math.cos(s.a) * (d + 60 * dpr), y2 = cy + Math.sin(s.a) * (d + 60 * dpr);
      const g = ctx.createLinearGradient(x, y, x2, y2);
      g.addColorStop(0, `rgba(${s.c},0.95)`); g.addColorStop(1, `rgba(${s.c},0)`);
      ctx.strokeStyle = g; ctx.lineWidth = 2.2 * dpr;
      ctx.beginPath(); ctx.moveTo(x, y); ctx.lineTo(x2, y2); ctx.stroke();
    });
    // 2) flash + crystal forms and spins (from 0.9 s)
    if (t > 0.9) {
      const q = Math.min(1, (t - 0.9) / 0.5), k = 70 * dpr * (0.4 + 0.6 * q), ay = t * 1.6, ax = 0.45;
      if (t < 1.3) { ctx.fillStyle = `rgba(255,255,255,${0.5 * (1 - (t - 0.9) / 0.4)})`; ctx.fillRect(0, 0, w, h); }
      const P = V.map(([x, y, z]) => {
        const x1 = x * Math.cos(ay) + z * Math.sin(ay), z1 = -x * Math.sin(ay) + z * Math.cos(ay);
        return [x1, y * Math.cos(ax) - z1 * Math.sin(ax), y * Math.sin(ax) + z1 * Math.cos(ax)];
      });
      ctx.save(); ctx.shadowColor = glow; ctx.shadowBlur = 40 * dpr;
      F.map(f => ({ f, z: f.reduce((s, n) => s + P[n][2], 0) / 3 })).sort((a, b) => a.z - b.z).forEach(({ f }, i) => {
        const c = cols[i % 3], light = 0.55 + 0.45 * ((i % 4) / 3);
        ctx.beginPath();
        f.forEach((n, j) => (j ? ctx.lineTo : ctx.moveTo).call(ctx, cx + P[n][0] * k, cy - P[n][1] * k));
        ctx.closePath();
        ctx.fillStyle = `rgba(${c.map(v => Math.round(v * light)).join(",")},${0.9 * q})`;
        ctx.fill();
        ctx.strokeStyle = `rgba(255,255,255,${0.4 * q})`; ctx.lineWidth = dpr; ctx.stroke();
      });
      ctx.restore();
    }
    requestAnimationFrame(frame);
  }
  requestAnimationFrame(frame);

  const finish = () => {
    if (done) return;
    done = true;
    el.classList.add("out");
    setTimeout(() => el.remove(), 650);
  };
  el.addEventListener("click", finish);
  addEventListener("keydown", finish, { once: true });
  addEventListener("resize", size);
  setTimeout(finish, 3300);
})();
