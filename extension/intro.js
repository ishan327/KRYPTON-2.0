// Krypton cinematic intro (~3.5 s): warp-speed starfield → energy spiral → crystal draws itself → flash →
// logo badge with KRYPTON sliding out + light sweep → tagline types in → logo flies to its place in the app.
// Sound: an original synthesized whoosh + impact + chime (Web Audio, no audio files). 🔊/🔇 toggle, remembered.
// Plays once per session; click to skip; respects reduced motion; any error just opens the app.
(() => {
  try {
    if (sessionStorage.getItem("krypton.intro")) return;
    sessionStorage.setItem("krypton.intro", "1");
  } catch (e) { return; }
  if (matchMedia("(prefers-reduced-motion: reduce)").matches) return;

  try {
    const root = document.documentElement;
    const css = (n, d) => getComputedStyle(root).getPropertyValue(n).trim() || d;
    const hex = h => { const m = h.replace("#", "").match(/^(..)(..)(..)$/); return m ? m.slice(1).map(x => parseInt(x, 16)) : [92, 255, 106]; };
    const C1 = hex(css("--lime", "#b6ff3b")), C2 = hex(css("--accent", "#5cff6a")), C3 = hex(css("--accent2", "#18c9c2"));
    const ACC = css("--accent", "#5cff6a");
    const logoSrc = (document.querySelector("base") || location.protocol.startsWith("chrome")) ? "icons/logo.svg" : "/ext/icons/logo.svg";
    let soundOn = true;
    try { soundOn = localStorage.getItem("krypton.introSound") !== "off"; } catch (e) { /* ignore */ }

    const el = document.createElement("div");
    el.id = "kintro";
    el.innerHTML = `
      <style>
        #kintro { position: fixed; inset: 0; z-index: 2147483646; background: radial-gradient(ellipse at center, #050a08 0%, #000 70%);
          overflow: hidden; cursor: pointer; font-family: "Segoe UI", system-ui, sans-serif; transition: background .7s ease; }
        #kintro.fade { background: transparent; }
        #kintro canvas { position: absolute; inset: 0; width: 100%; height: 100%; transition: opacity .5s; }
        #kintro.fade canvas, #kintro.fade .tag, #kintro.fade .word, #kintro.fade .ctl { opacity: 0; transition: opacity .45s; }
        #kintro .lock { position: absolute; left: 50%; top: 50%; display: flex; align-items: center; gap: 22px; transform: translate(-50%, -50%); }
        #kintro .badge { width: 104px; height: 104px; opacity: 0; transform: scale(.4) rotate(-25deg);
          filter: drop-shadow(0 0 26px ${ACC}); transition: transform .55s cubic-bezier(.2,1.4,.4,1), opacity .3s; }
        #kintro .badge.on { opacity: 1; transform: none; }
        #kintro .clip { overflow: hidden; }
        #kintro .word { position: relative; font-size: clamp(36px, 6.5vw, 78px); font-weight: 800; letter-spacing: .16em; color: #fff;
          transform: translateX(-110%); transition: transform .6s cubic-bezier(.2,.9,.25,1); text-shadow: 0 0 22px ${ACC}; white-space: nowrap; }
        #kintro .word.on { transform: none; }
        #kintro .word::after { content: ""; position: absolute; inset: 0; background: linear-gradient(100deg, transparent 30%, rgba(255,255,255,.95) 50%, transparent 70%);
          background-size: 250% 100%; background-position: 150% 0; mix-blend-mode: overlay; }
        #kintro .word.shine::after { animation: ksweep .9s ease-in-out forwards; }
        #kintro .tag { position: absolute; left: 0; right: 0; top: calc(50% + 78px); text-align: center; color: rgba(255,255,255,.75);
          letter-spacing: .42em; font-size: 13px; text-transform: uppercase; min-height: 18px; }
        #kintro .tag i { display: inline-block; width: 2px; height: 14px; background: ${ACC}; vertical-align: middle; animation: kblink .6s steps(1) infinite; }
        #kintro .ctl { position: absolute; bottom: 20px; right: 22px; display: flex; gap: 14px; align-items: center; color: rgba(255,255,255,.4); font-size: 12px; letter-spacing: .1em; }
        #kintro .ctl button { background: rgba(255,255,255,.08); border: 1px solid rgba(255,255,255,.18); color: #fff; border-radius: 99px; padding: 5px 10px; cursor: pointer; font-size: 14px; }
        @keyframes ksweep { to { background-position: -50% 0; } }
        @keyframes kblink { 50% { opacity: 0; } }
        @media (max-width: 600px) { #kintro .badge { width: 70px; height: 70px; } #kintro .lock { gap: 12px; } #kintro .tag { top: calc(50% + 54px); font-size: 11px; } }
      </style>
      <canvas></canvas>
      <div class="lock"><img class="badge" src="${logoSrc}" alt=""><div class="clip"><div class="word">KRYPTON</div></div></div>
      <div class="tag"></div>
      <div class="ctl"><button type="button" class="snd" title="Intro sound">${soundOn ? "🔊" : "🔇"}</button><span>click to skip</span></div>`;
    (document.body || document.documentElement).appendChild(el);

    // ---------------- sound (original, synthesized) ----------------
    let ac = null;
    function playSound() {
      if (!soundOn) return;
      try {
        ac = ac || new (window.AudioContext || window.webkitAudioContext)();
        if (ac.state === "suspended") ac.resume();
        const now = ac.currentTime - (performance.now() - t0) / 1000;  // align with the animation clock
        const out = ac.createGain(); out.gain.value = 0.55; out.connect(ac.destination);
        // reverb
        const verb = ac.createConvolver(), len = ac.sampleRate * 2.4, ir = ac.createBuffer(2, len, ac.sampleRate);
        for (let ch = 0; ch < 2; ch++) { const d = ir.getChannelData(ch); for (let i = 0; i < len; i++) d[i] = (Math.random() * 2 - 1) * Math.pow(1 - i / len, 3); }
        verb.buffer = ir; const wet = ac.createGain(); wet.gain.value = 0.35; verb.connect(wet).connect(out);
        // 1) rising whoosh (filtered noise sweep) 0.7 s → 2.3 s
        const nb = ac.createBuffer(1, ac.sampleRate * 2, ac.sampleRate), nd = nb.getChannelData(0);
        for (let i = 0; i < nd.length; i++) nd[i] = Math.random() * 2 - 1;
        const noise = ac.createBufferSource(); noise.buffer = nb;
        const bp = ac.createBiquadFilter(); bp.type = "bandpass"; bp.Q.value = 1.2;
        const ng = ac.createGain(); ng.gain.value = 0;
        noise.connect(bp).connect(ng); ng.connect(out); ng.connect(verb);
        const w0 = Math.max(ac.currentTime, now + 0.7);
        bp.frequency.setValueAtTime(250, w0); bp.frequency.exponentialRampToValueAtTime(4200, w0 + 1.5);
        ng.gain.setValueAtTime(0, w0); ng.gain.linearRampToValueAtTime(0.5, w0 + 1.35); ng.gain.exponentialRampToValueAtTime(0.001, w0 + 1.75);
        noise.start(w0); noise.stop(w0 + 1.8);
        // 2) impact at the flash (≈2.25 s): deep thump
        const hit = Math.max(ac.currentTime, now + 2.25);
        const th = ac.createOscillator(), tg = ac.createGain();
        th.type = "sine"; th.frequency.setValueAtTime(120, hit); th.frequency.exponentialRampToValueAtTime(42, hit + 0.5);
        tg.gain.setValueAtTime(0.9, hit); tg.gain.exponentialRampToValueAtTime(0.001, hit + 0.7);
        th.connect(tg).connect(out); th.start(hit); th.stop(hit + 0.75);
        // 3) bright rising chime (E major arpeggio, Lenovo-like feel) with long tail
        [659.25, 830.61, 987.77, 1318.5, 1661.2].forEach((f, i) => {
          const st = hit + 0.05 + i * 0.07;
          [0, 4].forEach(det => {
            const o = ac.createOscillator(), g = ac.createGain();
            o.type = i % 2 ? "triangle" : "sine"; o.frequency.value = f; o.detune.value = det;
            g.gain.setValueAtTime(0, st); g.gain.linearRampToValueAtTime(0.16 - i * 0.015, st + 0.02); g.gain.exponentialRampToValueAtTime(0.0008, st + 2.2);
            o.connect(g); g.connect(out); g.connect(verb); o.start(st); o.stop(st + 2.3);
          });
        });
      } catch (e) { /* no sound, no problem */ }
    }
    const sndBtn = el.querySelector(".snd");
    sndBtn.addEventListener("click", e => {
      e.stopPropagation();  // don't skip the intro
      soundOn = !soundOn;
      sndBtn.textContent = soundOn ? "🔊" : "🔇";
      try { localStorage.setItem("krypton.introSound", soundOn ? "on" : "off"); } catch (er) { /* ignore */ }
      if (soundOn) playSound(); else if (ac) ac.close().then(() => { ac = null; });
    });

    // ---------------- visuals ----------------
    const cv = el.querySelector("canvas"), ctx = cv.getContext("2d");
    const dpr = Math.min(2, devicePixelRatio || 1);
    const size = () => { cv.width = innerWidth * dpr; cv.height = innerHeight * dpr; };
    size();
    const N = innerWidth < 600 ? 160 : 320;
    const stars = Array.from({ length: N }, () => ({ x: (Math.random() - .5) * 2, y: (Math.random() - .5) * 2, z: Math.random() * 1 + .05,
      a: Math.random() * Math.PI * 2, r: .25 + Math.random() * .75, c: [C1, C2, C3][Math.floor(Math.random() * 3)] }));
    const V = [[0, 1.3, 0], [0, -1.3, 0], [1, 0, 0], [-1, 0, 0], [0, 0, 1], [0, 0, -1]];
    const F = [[0, 2, 4], [0, 4, 3], [0, 3, 5], [0, 5, 2], [1, 4, 2], [1, 3, 4], [1, 5, 3], [1, 2, 5]];
    const E = [[0, 2], [0, 3], [0, 4], [0, 5], [1, 2], [1, 3], [1, 4], [1, 5], [2, 4], [4, 3], [3, 5], [5, 2]];
    const t0 = performance.now();
    let done = false, phase = 0;
    const badge = el.querySelector(".badge"), word = el.querySelector(".word"), tag = el.querySelector(".tag");
    const ease = x => 1 - Math.pow(1 - Math.min(1, Math.max(0, x)), 3);

    function frame(now) {
      if (done) return;
      const t = (now - t0) / 1000, w = cv.width, h = cv.height, cx = w / 2, cy = h / 2, S = Math.min(w, h);
      ctx.fillStyle = t < 2.25 ? "rgba(0,0,0,0.32)" : "rgba(0,0,0,0.5)";
      ctx.fillRect(0, 0, w, h);
      // 1) warp starfield (0 → 1.2 s): stars rush toward the camera
      if (t < 1.25) {
        const speed = 0.012 + ease(t / 1.2) * 0.05;
        stars.forEach(s => {
          const pz = s.z; s.z -= speed; if (s.z <= 0.02) { s.z = 1; s.x = (Math.random() - .5) * 2; s.y = (Math.random() - .5) * 2; }
          const k = S * 0.5;
          const x1 = cx + s.x / pz * k, y1 = cy + s.y / pz * k, x2 = cx + s.x / s.z * k, y2 = cy + s.y / s.z * k;
          ctx.strokeStyle = `rgba(${s.c},${Math.min(1, (1 - s.z) * 1.4)})`; ctx.lineWidth = (1 - s.z) * 2.6 * dpr;
          ctx.beginPath(); ctx.moveTo(x1, y1); ctx.lineTo(x2, y2); ctx.stroke();
        });
      }
      // 2) energy spiral pulling in (1.0 → 1.9 s)
      if (t > 1.0 && t < 2.0) {
        const p = ease((t - 1.0) / 0.9);
        stars.forEach((s, i) => {
          if (i % 2) return;
          const ang = s.a + p * 5 + t * 2, rad = S * 0.42 * s.r * (1 - p);
          const x = cx + Math.cos(ang) * rad, y = cy + Math.sin(ang) * rad;
          ctx.fillStyle = `rgba(${s.c},${0.9 * (1 - p * 0.3)})`;
          ctx.beginPath(); ctx.arc(x, y, (1.4 + 2 * (1 - p)) * dpr, 0, Math.PI * 2); ctx.fill();
        });
        const g = ctx.createRadialGradient(cx, cy, 0, cx, cy, S * 0.12 * p);
        g.addColorStop(0, `rgba(${C2},${0.55 * p})`); g.addColorStop(1, "rgba(0,0,0,0)");
        ctx.fillStyle = g; ctx.beginPath(); ctx.arc(cx, cy, S * 0.12 * p, 0, Math.PI * 2); ctx.fill();
      }
      // 3) crystal draws itself, edge by edge, then fills (1.6 → 2.3 s), flash at 2.25 s
      if (t > 1.6 && t < 2.28) {
        const q = ease((t - 1.6) / 0.6), k = S * 0.11, ay = t * 2.2, ax = 0.45;
        const P = V.map(([x, y, z]) => {
          const x1 = x * Math.cos(ay) + z * Math.sin(ay), z1 = -x * Math.sin(ay) + z * Math.cos(ay);
          return [cx + x1 * k, cy - (y * Math.cos(ax) - z1 * Math.sin(ax)) * k, y * Math.sin(ax) + z1 * Math.cos(ax)];
        });
        if (q > 0.55) {
          const fill = (q - 0.55) / 0.45;
          F.map(f => ({ f, z: f.reduce((s, n) => s + P[n][2], 0) / 3 })).sort((a, b) => a.z - b.z).forEach(({ f }, i) => {
            const c = [C1, C2, C3][i % 3];
            ctx.beginPath(); f.forEach((n, j) => (j ? ctx.lineTo : ctx.moveTo).call(ctx, P[n][0], P[n][1])); ctx.closePath();
            ctx.fillStyle = `rgba(${c},${0.85 * fill})`; ctx.fill();
          });
        }
        ctx.save(); ctx.shadowColor = ACC; ctx.shadowBlur = 18 * dpr; ctx.strokeStyle = "rgba(255,255,255,0.9)"; ctx.lineWidth = 1.6 * dpr;
        const shown = Math.floor(E.length * Math.min(1, q * 1.3));
        E.slice(0, shown).forEach(([a, b]) => { ctx.beginPath(); ctx.moveTo(P[a][0], P[a][1]); ctx.lineTo(P[b][0], P[b][1]); ctx.stroke(); });
        ctx.restore();
      }
      if (t > 2.22 && t < 2.6) {  // flash
        ctx.fillStyle = `rgba(255,255,255,${0.75 * (1 - (t - 2.22) / 0.38)})`; ctx.fillRect(0, 0, w, h);
      }
      // 4) logo lock-up + word + tagline
      if (phase === 0 && t > 2.25) { phase = 1; badge.classList.add("on"); }
      if (phase === 1 && t > 2.45) { phase = 2; word.classList.add("on"); setTimeout(() => word.classList.add("shine"), 420); typeTag(); }
      requestAnimationFrame(frame);
    }

    function typeTag() {
      const text = "Study smarter · Scroll less";
      let i = 0;
      const step = () => { if (done) return; tag.innerHTML = text.slice(0, i) + "<i></i>"; if (i++ < text.length) setTimeout(step, 28); };
      step();
    }

    // 5) exit: the badge flies to the logo's spot in the app, the overlay fades away around it
    function finish(fast) {
      if (done) return;
      done = true;
      const target = document.querySelector(".side .brand canvas, .side .brand .gem, .mtop .brand img, .brand canvas, .brand .gem");
      el.classList.add("fade");
      if (!fast && target && badge.classList.contains("on")) {
        const a = badge.getBoundingClientRect(), b = target.getBoundingClientRect();
        if (b.width) {
          badge.style.transition = "transform .7s cubic-bezier(.6,0,.2,1), opacity .7s";
          badge.style.transform = `translate(${b.left + b.width / 2 - (a.left + a.width / 2)}px, ${b.top + b.height / 2 - (a.top + a.height / 2)}px) scale(${b.width / a.width})`;
          setTimeout(() => { badge.style.opacity = "0"; }, 520);
        }
      } else {
        badge.style.opacity = "0";
      }
      el.style.pointerEvents = "none";
      setTimeout(() => el.remove(), 900);
    }

    requestAnimationFrame(frame);
    playSound();
    el.addEventListener("click", () => finish(true));
    addEventListener("keydown", () => finish(true), { once: true });
    addEventListener("resize", size);
    setTimeout(() => finish(false), 3600);
  } catch (e) {
    document.getElementById("kintro")?.remove();  // never block the app
  }
})();
