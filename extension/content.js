// Krypton content script: counts time on the page and shows the focus lock on distracting sites.
(() => {
  if (window.top !== window) return;
  const host = location.hostname;
  let blocked = false, locked = false, host$ = null, mediaTimer = null, warned = false;
  let lockUntil = 0, allowQuiz = true, cdTimer = null;

  const send = msg => new Promise(resolve => {
    try {
      chrome.runtime.sendMessage(msg, r => { void chrome.runtime.lastError; resolve(r || {}); });
    } catch (e) { resolve({}); } // extension reloaded: old script is orphaned
  });

  async function refresh() {
    const r = await send({ type: "check", host });
    blocked = !!r.blocked;
    lockUntil = r.lockUntil || 0;
    allowQuiz = r.allowQuiz !== false;
    setLocked(!!r.locked);
  }

  function setLocked(v) {
    if (v === locked && (v ? host$?.isConnected : true)) return;
    locked = v;
    v ? showLock() : hideLock();
  }

  setInterval(async () => {
    if (document.visibilityState !== "visible" || !document.hasFocus()) return;
    const r = await send({ type: "tick", host, sec: 5 });
    if (r.locked !== undefined) setLocked(!!r.locked);
    if (r.blocked && !r.locked && r.remaining <= 60 && !warned) { warned = true; toast("⏳ 1 minute of scrolling left — Krypton will lock this site soon."); }
    if (r.remaining > 60) warned = false;
  }, 5000);

  chrome.storage.onChanged.addListener((ch, area) => {
    if (area !== "local") return;
    if (ch.settings || (ch.focus && ch.focus.newValue?.locked !== ch.focus.oldValue?.locked)) refresh();
  });
  refresh();

  // ---------------- UI ----------------
  // Lock screen colours follow the theme picked in Krypton (💎 Krypton · ☀️ Light · 🌐 Cyber · 🔴 Red).
  const PALETTES = {
    krypton: { a: "92,255,106", a2: "24,201,194", bgc: "6,12,9", cardc: "16,28,22", accent: "#5cff6a", text: "#e8fff1", muted: "#9fb3a8", ink: "#062010", grad: "linear-gradient(135deg,#b6ff3b,#2ff58a 55%,#18c9c2)" },
    light: { a: "17,161,80", a2: "14,159,151", bgc: "236,244,239", cardc: "255,255,255", accent: "#11a150", text: "#10231a", muted: "#5b7266", ink: "#ffffff", grad: "linear-gradient(135deg,#34d27c,#12b886 55%,#0ea5a0)" },
    cyber: { a: "0,240,255", a2: "255,43,214", bgc: "5,3,15", cardc: "14,10,38", accent: "#00f0ff", text: "#e6f7ff", muted: "#8a90c4", ink: "#05030f", grad: "linear-gradient(135deg,#00f0ff,#7a5cff 50%,#ff2bd6)" },
    red: { a: "255,59,59", a2: "255,138,61", bgc: "14,4,4", cardc: "34,10,10", accent: "#ff3b3b", text: "#ffecec", muted: "#b59595", ink: "#1a0404", grad: "linear-gradient(135deg,#ff9a3d,#ff3b3b 55%,#b3001b)" },
  };
  let theme = "krypton";
  try { chrome.storage.local.get(["theme"], r => { theme = r?.theme || "krypton"; }); } catch (e) { /* orphaned script */ }
  chrome.storage.onChanged.addListener((ch, area) => { if (area === "local" && ch.theme) theme = ch.theme.newValue || "krypton"; });
  const themeVars = () => {
    const p = PALETTES[theme] || PALETTES.krypton;
    return `--a:${p.a}; --a2:${p.a2}; --bgc:${p.bgc}; --cardc:${p.cardc}; --accent:${p.accent}; --text:${p.text}; --muted:${p.muted}; --ink:${p.ink}; --grad:${p.grad};`;
  };
  const CSS = () => `
    :host { all: initial; ${themeVars()} }
    .wrap { position: fixed; inset: 0; z-index: 2147483647; display: grid; place-items: center; overflow: auto;
      background: radial-gradient(1200px 600px at 20% 0%, rgba(var(--a),.18), transparent 60%),
                  radial-gradient(900px 500px at 100% 100%, rgba(var(--a2),.16), transparent 60%), rgba(var(--bgc),.94);
      backdrop-filter: blur(14px); font: 15px/1.5 "Segoe UI", system-ui, sans-serif; color: var(--text); }
    .card { width: min(680px, calc(100vw - 32px)); margin: 24px 0; background: rgba(var(--cardc),.92);
      border: 1px solid rgba(var(--a),.35); border-radius: 20px; padding: 28px 30px;
      box-shadow: 0 0 0 1px rgba(0,0,0,.4), 0 30px 80px rgba(0,0,0,.6), 0 0 60px rgba(var(--a),.15); }
    .brand { display: flex; align-items: center; gap: 10px; letter-spacing: .28em; font-weight: 800; font-size: 13px; color: var(--accent); }
    .gem { width: 26px; height: 26px; border-radius: 7px; background: var(--grad);
      box-shadow: 0 0 18px rgba(var(--a),.7); transform: rotate(45deg); }
    h1 { font-size: 28px; margin: 16px 0 6px; line-height: 1.2; }
    p.sub { color: var(--muted); margin: 0 0 18px; }
    .q { background: rgba(255,255,255,.04); border: 1px solid rgba(255,255,255,.08); border-radius: 14px; padding: 14px 16px; margin: 12px 0; }
    .q b { display: block; margin-bottom: 10px; font-weight: 600; }
    label.opt { display: flex; gap: 10px; align-items: flex-start; padding: 8px 10px; border-radius: 10px; cursor: pointer; border: 1px solid transparent; }
    label.opt:hover { background: rgba(var(--a),.08); }
    label.opt input { accent-color: var(--accent); margin-top: 4px; }
    label.opt.right { border-color: var(--accent); background: rgba(var(--a),.12); }
    label.opt.wrong { border-color: #ff6b6b; background: rgba(255,107,107,.12); }
    .row { display: flex; gap: 10px; flex-wrap: wrap; margin-top: 18px; }
    button { font: 600 15px "Segoe UI", system-ui, sans-serif; border: 0; border-radius: 12px; padding: 12px 18px; cursor: pointer; }
    .primary { background: var(--grad); color: var(--ink); }
    .primary:disabled { opacity: .5; cursor: wait; }
    .ghost { background: rgba(255,255,255,.07); color: var(--text); border: 1px solid rgba(255,255,255,.12); }
    .msg { margin-top: 14px; padding: 12px 14px; border-radius: 12px; }
    .msg.bad { background: rgba(255,107,107,.12); border: 1px solid rgba(255,107,107,.4); }
    .msg.good { background: rgba(var(--a),.12); border: 1px solid rgba(var(--a),.4); }
    .loading { display: flex; gap: 12px; align-items: center; color: var(--muted); padding: 24px 0; }
    .spin { width: 22px; height: 22px; border-radius: 50%; border: 3px solid rgba(var(--a),.2); border-top-color: var(--accent); animation: s 1s linear infinite; }
    @keyframes s { to { transform: rotate(360deg); } }
    .timer { display: inline-flex; gap: 10px; align-items: baseline; margin: 4px 0 10px; padding: 8px 16px; border-radius: 12px;
      background: rgba(var(--a),.08); border: 1px solid rgba(var(--a),.3); color: var(--muted); }
    .timer b { font: 800 26px ui-monospace, Consolas, monospace; color: var(--accent); letter-spacing: .05em; }
    .pill { display: inline-block; font-size: 12px; padding: 2px 10px; border-radius: 99px; background: rgba(255,255,255,.08); color: var(--muted); margin-left: 8px; }
    .toast { position: fixed; right: 20px; bottom: 20px; z-index: 2147483647; background: rgb(var(--cardc)); color: var(--text);
      border: 1px solid var(--accent); border-radius: 14px; padding: 14px 18px; font: 14px "Segoe UI", system-ui, sans-serif;
      box-shadow: 0 10px 40px rgba(0,0,0,.5); max-width: 340px; }`;

  const esc = s => String(s ?? "").replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

  function toast(text) {
    const h = document.createElement("div");
    const root = h.attachShadow({ mode: "closed" });
    root.innerHTML = `<style>${CSS()}</style><div class="toast">${esc(text)}</div>`;
    document.documentElement.appendChild(h);
    setTimeout(() => h.remove(), 7000);
  }

  let root = null, guard = null, keyBlock = null, challenge = null;

  function showLock() {
    if (host$?.isConnected) return;
    host$ = document.createElement("krypton-lock");
    root = host$.attachShadow({ mode: "closed" });
    root.innerHTML = `<style>${CSS()}</style><div class="wrap"><div class="card" id="card"></div></div>`;
    document.documentElement.appendChild(host$);
    document.documentElement.style.setProperty("overflow", "hidden", "important");
    mediaTimer = setInterval(() => document.querySelectorAll("video,audio").forEach(m => { if (!m.paused) m.pause(); }), 400);
    guard = new MutationObserver(() => { if (locked && !host$.isConnected) document.documentElement.appendChild(host$); });
    guard.observe(document.documentElement, { childList: true });
    keyBlock = e => { if (!e.composedPath().includes(host$)) { e.stopImmediatePropagation(); } };
    ["keydown", "keypress", "keyup", "wheel"].forEach(t => window.addEventListener(t, keyBlock, { capture: true }));
    cdTimer = setInterval(tickCountdown, 1000);
    allowQuiz ? loadChallenge() : waitScreen();
  }

  function tickCountdown() {
    const left = Math.max(0, lockUntil - Date.now());
    const el = root?.getElementById("cd");
    if (el) el.textContent = `${Math.floor(left / 60000)}:${String(Math.floor(left / 1000) % 60).padStart(2, "0")}`;
    if (left <= 0) refresh(); // background clears the lock once the time is over
  }

  function waitScreen() {
    card().innerHTML = header("Your parent set this lock — it opens by itself when the timer ends. Use the time to study!") +
      `<div class="row"><button class="primary" id="study">📚 Study with Krypton</button></div>`;
    root.getElementById("study").onclick = () => send({ type: "openApp" });
    tickCountdown();
  }

  function hideLock() {
    if (!host$) return;
    clearInterval(cdTimer);
    guard?.disconnect();
    clearInterval(mediaTimer);
    ["keydown", "keypress", "keyup", "wheel"].forEach(t => window.removeEventListener(t, keyBlock, { capture: true }));
    document.documentElement.style.removeProperty("overflow");
    host$.remove();
    host$ = null;
  }

  const card = () => root.getElementById("card");

  function header(extra = "") {
    return `<div class="brand"><div class="gem"></div>KRYPTON FOCUS LOCK</div>
      <h1>Time's up on ${esc(host.replace(/^www\./, ""))} 🔒</h1>
      <div class="timer">Unlocks in <b id="cd">--:--</b></div>
      <p class="sub">${allowQuiz ? "You've used your scrolling time. Finish this quick task from your studies to unlock early." : ""} ${extra}</p>`;
  }

  async function loadChallenge() {
    card().innerHTML = header() + `<div class="loading"><div class="spin"></div>Krypton is preparing your task…</div>`;
    const r = await send({ type: "challenge" });
    if (/turned off/i.test(r.error || "")) { allowQuiz = false; return waitScreen(); }
    if (r.error || !r.questions?.length) return mathChallenge();
    challenge = r;
    renderQuestions(r.questions, `<span class="pill">${r.engine === "offline" ? "📘 offline" : r.engine === "local" ? "🖥 local AI" : "⚡ Groq AI"}</span>`,
      `Get ${r.pass_mark} of ${r.questions.length} right to unlock.`);
  }

  function renderQuestions(questions, badge, rule) {
    card().innerHTML = header(rule) + questions.map((q, i) => `
      <div class="q"><b>${i + 1}. ${esc(q.question)}</b>
        ${q.options.map((o, j) => `<label class="opt" data-q="${i}" data-o="${j}"><input type="radio" name="q${i}" value="${j}"> <span>${esc(o)}</span></label>`).join("")}
      </div>`).join("") + `
      <div class="row"><button class="primary" id="submit">Submit answers</button>
        <button class="ghost" id="study">Open Krypton to study</button>${badge}</div><div id="out"></div>`;
    root.getElementById("study").onclick = () => send({ type: "openApp" });
    root.getElementById("submit").onclick = () => submit(questions);
  }

  async function submit(questions) {
    const answers = questions.map((_, i) => {
      const el = root.querySelector(`input[name="q${i}"]:checked`);
      return el ? Number(el.value) : -1;
    });
    const out = root.getElementById("out");
    if (answers.includes(-1)) { out.innerHTML = `<div class="msg bad">Answer all the questions first.</div>`; return; }
    const btn = root.getElementById("submit");
    btn.disabled = true;
    const res = challenge.local ? verifyLocal(answers) : await send({ type: "verify", challenge_id: challenge.challenge_id, answers });
    if (res.error) { out.innerHTML = `<div class="msg bad">${esc(res.error)}</div><div class="row"><button class="ghost" id="again">New task</button></div>`; root.getElementById("again").onclick = loadChallenge; return; }
    res.correct.forEach((ok, i) => {
      root.querySelector(`label[data-q="${i}"][data-o="${answers[i]}"]`)?.classList.add(ok ? "right" : "wrong");
    });
    if (res.passed) {
      if (challenge.local) await send({ type: "unlockOffline" });
      out.innerHTML = `<div class="msg good">✅ ${res.score}/${res.total} — unlocked! Great work. Krypton will check in again later.</div>`;
    } else {
      const review = (res.review || []).map(r => `<div>• ${esc(r.answer)}${r.explanation ? ` — <span style="color:#9fb3a8">${esc(r.explanation)}</span>` : ""}</div>`).join("");
      out.innerHTML = `<div class="msg bad">${res.score}/${res.total} correct — you need ${res.need}. Correct answers:${review}</div>
        <div class="row"><button class="primary" id="again">Try a new task</button></div>`;
      root.getElementById("again").onclick = loadChallenge;
    }
  }

  // Backend offline: a maths task checked right here, so the lock never strands the student.
  function mathChallenge() {
    const qs = [];
    for (let i = 0; i < 3; i++) {
      const a = 12 + Math.floor(Math.random() * 40), b = 3 + Math.floor(Math.random() * 9);
      const ans = a * b;
      const opts = [ans, ans + b, ans - a, ans + 10].sort(() => Math.random() - 0.5);
      qs.push({ question: `${a} × ${b} = ?`, options: opts.map(String), answer_index: opts.indexOf(ans) });
    }
    challenge = { local: true, questions: qs };
    renderQuestions(qs, `<span class="pill">backend offline · maths task</span>`, "Get all 3 right to unlock.");
  }

  function verifyLocal(answers) {
    const correct = challenge.questions.map((q, i) => answers[i] === q.answer_index);
    const score = correct.filter(Boolean).length;
    return { passed: score === 3, score, total: 3, need: 3, correct,
             review: challenge.questions.map(q => ({ answer: q.options[q.answer_index] })) };
  }
})();
