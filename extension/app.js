const $ = id => document.getElementById(id);
let CATALOG = {};
let selectedChapters = new Set();

// ---------------- navigation ----------------
function showTab(name) {
  document.querySelectorAll("#nav button").forEach(b => b.classList.toggle("active", b.dataset.tab === name));
  document.querySelectorAll(".panel").forEach(p => p.classList.toggle("active", p.id === "tab-" + name));
  $("ctxbar").style.display = ["focus", "settings", "agent", "marks", "revise", "progress", "langlab", "school"].includes(name) ? "none" : "";
  if (name === "school") renderSchool();
  if (name === "langlab" && !$("labOut").innerHTML) renderLab();
  if (name === "revise") renderRevise();
  if (name === "progress") renderProgress();
  if (name === "focus") renderFocus();
  if (name === "settings") renderSettings();
  if (name === "marks") { renderMarks(); loadPinCard(); }
  if (name === "agent") $("agentInput").focus();
  try { localStorage.setItem("krypton.tab", name); } catch (e) { /* storage blocked */ }
}
document.querySelectorAll("#nav button").forEach(b => b.onclick = () => showTab(b.dataset.tab));

// ---------------- backend status + mode ----------------
async function refreshStatus() {
  try {
    const s = await api("/api/status");
    $("dot").className = "dot on";
    $("conn").textContent = `online · ${s.library.books} books`;
    document.querySelectorAll("#modes button").forEach(b => b.classList.toggle("active", b.dataset.mode === s.settings.mode));
    return s;
  } catch (e) {
    $("dot").className = "dot off";
    $("conn").textContent = "backend offline";
    return null;
  }
}
document.querySelectorAll("#modes button").forEach(b => b.onclick = async () => {
  try { await api("/api/settings", { mode: b.dataset.mode }); } catch (e) { /* status shows it */ }
  refreshStatus();
});

// ---------------- class / subject / chapter context ----------------
async function loadCatalog() {
  try { CATALOG = await api("/api/catalog"); } catch (e) { CATALOG = {}; }
  const settings = await getSettings();
  const classes = Object.keys(CATALOG).map(Number).sort((a, b) => a - b);
  $("cls").innerHTML = (classes.length ? classes : [1, 2, 3, 4, 5, 6, 7, 8, 9, 10])
    .map(c => `<option value="${c}">Class ${c}</option>`).join("");
  $("cls").value = String(settings.studyClass || 10);
  if (!$("cls").value) $("cls").selectedIndex = $("cls").options.length - 1;
  fillSubjects(settings.studySubject);
}

function fillSubjects(prefer) {
  const subs = Object.keys(CATALOG[$("cls").value] || {}).sort();
  $("subject").innerHTML = subs.map(s => `<option>${esc(s)}</option>`).join("") || `<option value="">—</option>`;
  if (prefer && subs.includes(prefer)) $("subject").value = prefer;
  else { const sci = subs.find(s => /science/i.test(s)) || subs.find(s => /math/i.test(s)); if (sci) $("subject").value = sci; }
  fillChapters();
}

function fillChapters() {
  selectedChapters.clear();
  const books = (CATALOG[$("cls").value] || {})[$("subject").value] || [];
  $("chapMenu").innerHTML = `<div class="tools"><button type="button" class="btn-ghost" id="chAll">Select all</button>
      <button type="button" class="btn-ghost" id="chNone">Clear</button></div>` +
    books.map(b => `<div class="book">${esc(b.title)}</div>` + b.chapters.map(c =>
      `<label><input type="checkbox" value="${esc(b.code)}:${c.ch}"> <span>Ch ${c.ch} · ${esc(c.title)}</span></label>`).join("")).join("");
  $("chapMenu").querySelectorAll("input").forEach(i => i.onchange = () => {
    i.checked ? selectedChapters.add(i.value) : selectedChapters.delete(i.value);
    chapLabel();
  });
  $("chAll").onclick = () => { $("chapMenu").querySelectorAll("input").forEach(i => { i.checked = true; selectedChapters.add(i.value); }); chapLabel(); };
  $("chNone").onclick = () => { $("chapMenu").querySelectorAll("input").forEach(i => { i.checked = false; }); selectedChapters.clear(); chapLabel(); };
  chapLabel();
  saveSettings({ studyClass: Number($("cls").value), studySubject: $("subject").value });
}

function chapLabel() {
  const n = selectedChapters.size;
  if (!n) { $("chapBtn").textContent = "All chapters ▾"; return; }
  const first = $("chapMenu").querySelector(`input[value="${CSS.escape([...selectedChapters][0])}"]`);
  $("chapBtn").textContent = n === 1 ? first.nextElementSibling.textContent + " ▾" : `${n} chapters selected ▾`;
}

$("cls").onchange = () => fillSubjects();
$("subject").onchange = fillChapters;
$("chapBtn").onclick = e => { e.stopPropagation(); $("chapMenu").classList.toggle("open"); };
document.addEventListener("click", e => { if (!e.target.closest(".chap-picker")) $("chapMenu").classList.remove("open"); });

function context() {
  return { cls: Number($("cls").value) || null, subject: $("subject").value || null, chapters: [...selectedChapters] };
}

// ---------------- requests ----------------
document.querySelectorAll("form.ask").forEach(form => form.onsubmit = async e => {
  e.preventDefault();
  const feature = form.dataset.feature;
  const fd = Object.fromEntries(new FormData(form));
  const body = { ...context(), query: fd.query || "" };
  if (fd.count) body.count = Number(fd.count);
  if (fd.difficulty) body.difficulty = fd.difficulty;
  if (fd.paper_type) body.paper_type = fd.paper_type;
  if (fd.days) body.days = Number(fd.days);
  const out = $("out-" + feature);
  const btn = form.querySelector("button");
  btn.disabled = true;
  out.innerHTML = `<div class="card loading"><div class="spin"></div><div>${loadingText(feature)}</div></div>`;
  chrome.storage.local.set({ lastStudy: { cls: body.cls, subject: body.subject, chapters: body.chapters, query: body.query } });
  try {
    const res = await api("/api/" + feature, body);
    RENDER[feature](out, res, body);
    if (feature !== "quiz") api("/api/xp", { event: feature }).then(gainXp, () => {});
  } catch (err) {
    out.innerHTML = `<div class="err"><b>Couldn't reach Krypton's backend.</b><br>${esc(err.message)}<br>
      <span class="muted">Start it with <code>start_krypton.bat</code> in the krypton folder.</span></div>`;
  } finally { btn.disabled = false; }
});

function loadingText(f) {
  const mode = document.querySelector("#modes button.active")?.dataset.mode;
  const who = mode === "groq" ? "Groq AI" : mode === "local" ? "your GPU" : "the offline engine";
  return { explain: `Reading the NCERT pages and preparing a line-by-line lesson with ${who}…`,
           flashcards: `Making flashcards with ${who}…`, quiz: `Writing quiz questions with ${who}…`,
           paper: `Setting a CBSE-pattern paper with ${who}… (local AI can take a minute)`,
           guide: `Planning your study days with ${who}…`, mindmap: `Drawing your mind map with ${who}…` }[f];
}

function metaBar(res) {
  const notes = (res.notes || []).length ? `<div class="note">⚠ ${res.notes.map(esc).join("<br>")}${res.engine === "offline" ? "<br>Used the offline textbook engine instead." : ""}</div>` : "";
  return `${notes}<div class="meta"><span class="pill engine ${res.engine}">${ENGINE_LABEL[res.engine] || res.engine}</span>
    <span class="pill">${esc(res.model)}</span><span class="pill">${(res.ms / 1000).toFixed(1)}s</span></div>`;
}

function sourcesBlock(res) {
  if (!res.sources?.length) return "";
  return `<details class="sources"><summary>📚 NCERT sources (${res.sources.length})</summary><ul>
    ${res.sources.map(s => `<li>[${esc(s.id)}] ${esc(s.label)} — page ${esc(s.page)}</li>`).join("")}</ul></details>`;
}

// ---------------- renderers ----------------
const RENDER = {
  explain(out, res) {
    const d = res.data;
    out.innerHTML = metaBar(res) + `<div class="card">
      <h2 style="margin-top:0">${esc(d.title)}</h2>
      <div class="lines">${d.lines.map((l, i) => `<div class="line"><div class="n">${i + 1}</div>
        <div><q>${esc(l.text)}</q><div class="ex">${esc(l.explanation)}</div></div></div>`).join("")}</div>
      ${d.summary ? `<div class="summary"><b>In short:</b> ${esc(d.summary)}</div>` : ""}
      ${d.example ? `<div class="summary"><b>Remember it like this:</b> ${esc(d.example)}</div>` : ""}
      ${d.key_terms?.length ? `<h4>Key terms</h4><div class="terms">${d.key_terms.map(t => `<div class="term"><b>${esc(t.term)}</b><br>${esc(t.meaning)}</div>`).join("")}</div>` : ""}
      ${d.check_questions?.length ? `<h4>Check yourself</h4><ol>${d.check_questions.map(q => `<li>${esc(q)}</li>`).join("")}</ol>` : ""}
      <div class="toolbar" style="margin-top:16px">
        <button class="btn-primary" id="explainPdf">⬇ Download PDF</button>
        <button class="btn-ghost" id="toCards">🃏 Make flashcards on this</button>
        <button class="btn-ghost" id="toQuiz">❓ Quiz me on this</button></div>
      ${sourcesBlock(res)}</div>`;
    const q = document.querySelector('#tab-explain input[name="query"]').value;
    $("explainPdf").onclick = () => downloadPdf("explain", d, res.sources, $("explainPdf"));
    $("toCards").onclick = () => jump("flashcards", q);
    $("toQuiz").onclick = () => jump("quiz", q);
  },

  flashcards(out, res) {
    const d = res.data;
    out.innerHTML = metaBar(res) + `<div class="toolbar">
        <button class="btn-primary" id="cardsPdf">⬇ Download PDF</button>
        <button class="btn-ghost" id="shuffle">🔀 Shuffle</button><button class="btn-ghost" id="flipAll">↻ Flip all</button>
        <button class="btn-ghost" id="saveDeck">💾 Save deck</button><button class="btn-ghost" id="csv">⬇ Export CSV (Anki)</button></div>
      <div class="deck" id="deck"></div>${sourcesBlock(res)}`;
    let cards = d.cards.slice();
    const draw = () => {
      $("deck").innerHTML = cards.map((c, i) => `<div class="flip"><div class="in">
        <div class="f"><span class="idx">${i + 1}/${cards.length}</span>${esc(c.front)}</div>
        <div class="b">${esc(c.back)}</div></div></div>`).join("");
      $("deck").querySelectorAll(".flip").forEach(f => f.onclick = () => f.classList.toggle("on"));
    };
    draw();
    $("cardsPdf").onclick = () => downloadPdf("flashcards", { title: d.title, cards }, res.sources, $("cardsPdf"));
    $("shuffle").onclick = () => { cards.sort(() => Math.random() - .5); draw(); };
    $("flipAll").onclick = () => $("deck").querySelectorAll(".flip").forEach(f => f.classList.toggle("on"));
    $("csv").onclick = () => download(`${d.title || "krypton"}-flashcards.csv`,
      cards.map(c => [c.front, c.back].map(x => `"${String(x).replace(/"/g, '""')}"`).join(",")).join("\n"));
    $("saveDeck").onclick = async () => {
      const { decks = [] } = await getLocal(["decks"]);
      const ctx = context();
      decks.unshift({ title: d.title || "Deck", cls: ctx.cls, subject: ctx.subject, cards, saved: Date.now() });
      await chrome.storage.local.set({ decks: decks.slice(0, 50) });
      $("saveDeck").textContent = "✓ Saved";
      renderDecks();
    };
  },

  quiz(out, res) {
    const qs = res.data.questions;
    let i = 0, score = 0;
    const answers = [];
    const step = () => {
      if (i >= qs.length) return finish();
      const q = qs[i];
      out.innerHTML = metaBar(res) + `<div class="card qcard">
        <div class="qprog"><div style="width:${(i / qs.length) * 100}%"></div></div>
        <div class="muted">Question ${i + 1} of ${qs.length} · Score ${score}</div>
        <div class="qtext">${esc(q.question)}</div>
        <div class="opts">${q.options.map((o, j) => `<button class="opt" data-j="${j}"><span class="k">${"ABCD"[j]}</span><span>${esc(o)}</span></button>`).join("")}</div>
        <div id="qx"></div></div>`;
      out.querySelectorAll(".opt").forEach(b => b.onclick = () => {
        const j = Number(b.dataset.j);
        const ok = j === q.answer_index;
        if (ok) score++;
        answers.push(ok);
        const ctx = context();
        api("/api/attempts", { items: [{ ...q, chosen: j, cls: ctx.cls, subject: ctx.subject }] }).then(gainXp, () => {});
        out.querySelectorAll(".opt").forEach(x => { x.disabled = true; if (Number(x.dataset.j) === q.answer_index) x.classList.add("right"); });
        if (!ok) b.classList.add("wrong");
        $("qx").innerHTML = `<div class="expl">${ok ? "✅ Correct!" : "❌ Not quite."} ${esc(q.explanation || "")}</div>
          <div class="row" style="margin-top:12px"><button class="btn-primary" id="next">${i + 1 < qs.length ? "Next →" : "See score"}</button></div>`;
        $("next").onclick = () => { i++; step(); };
      });
    };
    const finish = async () => {
      const pct = Math.round((score / qs.length) * 100);
      const { quizHistory = [] } = await getLocal(["quizHistory"]);
      const ctx = context();
      quizHistory.unshift({ title: res.data.title || "Quiz", subject: ctx.subject, cls: ctx.cls, score, total: qs.length, at: Date.now() });
      await chrome.storage.local.set({ quizHistory: quizHistory.slice(0, 50) });
      api("/api/xp", { event: "quiz_done" }).then(gainXp, () => {});
      if (score === qs.length) api("/api/xp", { event: "quiz_perfect" }).then(gainXp, () => {});
      out.innerHTML = metaBar(res) + `<div class="card score"><div class="muted">Your score</div>
        <div class="big grad">${score}/${qs.length}</div><div>${pct >= 80 ? "🔥 Excellent!" : pct >= 50 ? "👍 Good — revise the ones you missed." : "📖 Read the chapter again and retry."}</div>
        <div class="row" style="justify-content:center;margin-top:16px"><button class="btn-primary" id="retry">Retry these</button></div></div>
        <div class="card" style="margin-top:12px"><h4 style="margin-top:0">Review</h4>${qs.map((q, k) =>
          `<p>${answers[k] ? "✅" : "❌"} <b>${esc(q.question)}</b><br><span class="muted">Answer: ${esc(q.options[q.answer_index])}</span></p>`).join("")}</div>${sourcesBlock(res)}`;
      $("retry").onclick = () => { i = 0; score = 0; answers.length = 0; step(); };
    };
    step();
  },

  paper(out, res) {
    const d = res.data;
    let n = 0;
    const qhtml = q => {
      n++;
      const opts = q.options?.length ? `<div class="popts">${q.options.map((o, j) => `<div>(${"abcd"[j]}) ${esc(o)}</div>`).join("")}</div>` : "";
      const passage = q.passage ? `<div class="passage">${esc(q.passage)}</div>` : "";
      const subs = q.subparts?.length ? `<ol type="i">${q.subparts.map(s => `<li>${esc(s.q)} <b>(${esc(s.marks)})</b><div class="ans">${esc(s.answer || "")}</div></li>`).join("")}</ol>` : "";
      const or = q.or?.q ? `<div class="orq">OR</div><div>${esc(q.or.q)}</div><div class="ans">${esc(q.or.answer || "")}</div>` : "";
      return `<div class="pq"><div>${n}.</div><div>${esc(q.q)}${passage}${opts}${subs}<div class="ans">Answer: ${esc(q.answer || "")}</div>${or}</div><div class="m">${esc(q.marks)}</div></div>`;
    };
    out.innerHTML = metaBar(res) + `<div class="toolbar">
        <button class="btn-primary" id="print">🖨 Print / Save PDF</button>
        <button class="btn-ghost" id="ans">👁 Show answer key</button></div>
      <div class="paper" id="paperDoc">
        <div class="ph"><div>KRYPTON PRACTICE SERIES</div><h2>${esc(d.title)}</h2>
          <div>Class ${esc(d.class)} · ${esc(d.subject || "")}</div>
          <div class="sub"><span>Time allowed: ${esc(d.time)}</span><span>Maximum marks: ${esc(d.max_marks)}</span></div></div>
        <div class="instr"><b>General Instructions:</b><ol>${(d.instructions || []).map(x => `<li>${esc(x)}</li>`).join("")}</ol></div>
        ${d.sections.map(s => `<div class="sec">${esc(s.name)}</div><div class="sech">${esc(s.title || "")}</div>${s.questions.map(qhtml).join("")}`).join("")}
        <div style="text-align:center;margin-top:24px">*** End of question paper ***</div>
      </div>${sourcesBlock(res)}`;
    $("print").onclick = () => window.print();
    $("ans").onclick = () => {
      const on = $("paperDoc").classList.toggle("show-ans");
      $("ans").textContent = on ? "🙈 Hide answer key" : "👁 Show answer key";
    };
  },

  mindmap(out, res) {
    const d = res.data;
    out.innerHTML = metaBar(res) + `<div class="toolbar"><button class="btn-primary" id="mapPdf">⬇ Download PDF</button>
        <button class="btn-ghost" id="mapCards">🃏 Flashcards from this map</button></div>
      <div class="card mapwrap">${res.svg}</div>
      <p class="muted small-note">Hover (or tap) any box to see what it means.</p>${sourcesBlock(res)}`;
    $("mapPdf").onclick = () => downloadPdf("mindmap", d, res.sources, $("mapPdf"));
    $("mapCards").onclick = () => jump("flashcards", d.center || d.title);
  },

  guide(out, res) {
    const d = res.data;
    const list = (t, arr) => arr?.length ? `<div class="card"><h4 style="margin-top:0">${t}</h4><ul>${arr.map(x => `<li>${esc(x)}</li>`).join("")}</ul></div>` : "";
    out.innerHTML = metaBar(res) + `<div class="card"><h2 style="margin-top:0">${esc(d.title)}</h2><p>${esc(d.overview || "")}</p>
      <div class="days">${d.days.map(x => `<div class="day"><div class="d">DAY ${esc(x.day)}</div><b>${esc(x.focus || "")}</b>
        <ul>${(x.tasks || []).map(t => `<li>${esc(t)}</li>`).join("")}</ul></div>`).join("")}</div></div>
      <div class="lists">${list("🎯 Key topics", d.key_topics)}${list("💡 Tips", d.tips)}${list("⚠ Common mistakes", d.common_mistakes)}${list("📝 Exam strategy", d.exam_strategy)}</div>
      ${sourcesBlock(res)}`;
  },
};

function jump(tab, query) {
  showTab(tab);
  const input = document.querySelector(`#tab-${tab} input[name="query"]`);
  input.value = query;
  document.querySelector(`#tab-${tab} form`).requestSubmit();
}

async function downloadPdf(kind, data, sources, btn) {
  const label = btn.textContent;
  btn.disabled = true;
  btn.textContent = "⏳ Making PDF…";
  try {
    const ctx = context();
    const res = await fetch(API + "/api/pdf", { method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ kind, data, sources: sources || [], meta: `Class ${ctx.cls || ""} · ${ctx.subject || ""} · ${{ explain: "Line-by-line lesson", flashcards: "Flashcards", mindmap: "Mind map" }[kind]}` }) });
    if (!res.ok) throw new Error((await res.json().catch(() => ({}))).detail || res.statusText);
    const a = document.createElement("a");
    a.href = URL.createObjectURL(await res.blob());
    a.download = `Krypton - ${(data.title || kind).replace(/[\\/:*?"<>|]/g, "-")}${kind === "flashcards" ? " (flashcards)" : ""}.pdf`;
    a.click();
    btn.textContent = "✓ Downloaded";
  } catch (err) {
    btn.textContent = "PDF failed";
    alert("Couldn't make the PDF: " + err.message);
  } finally {
    btn.disabled = false;
    setTimeout(() => { btn.textContent = label; }, 2500);
  }
}

function download(name, text) {
  const a = document.createElement("a");
  a.href = URL.createObjectURL(new Blob([text], { type: "text/csv" }));
  a.download = name.replace(/[\\/:*?"<>|]/g, "-");
  a.click();
}

async function renderDecks() {
  const { decks = [] } = await getLocal(["decks"]);
  $("decks").innerHTML = decks.length ? `<h4 style="margin-top:0">💾 Saved decks</h4>` + decks.map((d, i) =>
    `<div class="deckrow"><span>${esc(d.title)} <span class="muted">· ${d.cards.length} cards · Class ${esc(d.cls)} ${esc(d.subject || "")}</span></span>
     <span class="row"><button class="btn-ghost" data-open="${i}">Open</button><button class="btn-ghost" data-del="${i}">✕</button></span></div>`).join("") : "";
  $("decks").querySelectorAll("[data-open]").forEach(b => b.onclick = () => {
    const d = decks[Number(b.dataset.open)];
    RENDER.flashcards($("out-flashcards"), { data: { title: d.title, cards: d.cards }, engine: "offline", model: "saved deck", ms: 0, notes: [] });
    window.scrollTo({ top: 0, behavior: "smooth" });
  });
  $("decks").querySelectorAll("[data-del]").forEach(b => b.onclick = async () => {
    decks.splice(Number(b.dataset.del), 1);
    await chrome.storage.local.set({ decks });
    renderDecks();
  });
}

// ---------------- focus & stats ----------------
async function renderFocus() {
  let r;
  try { r = await api("/api/rules"); await chrome.storage.local.set({ rules: r }); }
  catch (e) { r = { ...DEFAULT_RULES, ...((await getLocal(["rules"])).rules || {}) }; }
  const row = (k, v) => `<div class="r"><span>${k}</span><b>${v}</b></div>`;
  $("rulesView").innerHTML = row("Focus lock", r.focus_enabled ? "On" : "Off") +
    row("Scrolling allowed", `${r.limit_minutes} min`) + row("Then locked for", `${r.lock_minutes} min`) +
    row("Early unlock with quiz", r.allow_quiz_unlock ? `Yes (${r.unlock_pass}/3 correct)` : "No") +
    row("Blocked sites", `${r.blocked_sites.length} sites`) +
    (r.parent_setup ? "" : `<div class="note">No parent account yet — a parent should open the Parent board to set a password.</div>`);
  const s = { limitMinutes: r.limit_minutes, blockedSites: r.blocked_sites };
  const { usage, focus, history = [], quizHistory = [] } = await getLocal(["usage", "focus", "history", "quizHistory"]);
  const today = new Date().toLocaleDateString("en-CA");
  const u = usage && usage.date === today ? usage : { sites: {}, distracted: 0, study: 0, locks: 0, unlocks: 0 };
  $("kpis").innerHTML = `<div class="kpi"><b>${fmtMin(u.study)}</b><span>studied</span></div>
    <div class="kpi"><b>${fmtMin(u.distracted)}</b><span>on distracting sites</span></div>
    <div class="kpi"><b>${u.unlocks || 0}/${u.locks || 0}</b><span>tasks done / locks</span></div>`;
  const blocked = s.blockedSites;
  const sites = Object.entries(u.sites || {}).sort((a, b) => b[1] - a[1]).slice(0, 8);
  const max = Math.max(1, ...sites.map(x => x[1]));
  $("siteBars").innerHTML = sites.length ? sites.map(([h, sec]) => {
    const bad = blocked.some(d => h === d || h.endsWith("." + d));
    return `<div class="bar"><span class="name">${bad ? "🔴" : "🟢"} ${esc(h)}</span><div class="t"><div class="${bad ? "bad" : ""}" style="width:${(sec / max) * 100}%"></div></div><span>${fmtMin(sec)}</span></div>`;
  }).join("") : `<div class="muted">No browsing tracked yet today.</div>`;
  const days = [...history.slice(-6), { date: today, study: u.study, distracted: u.distracted }];
  const wmax = Math.max(60, ...days.map(d => Math.max(d.study || 0, d.distracted || 0)));
  $("week").innerHTML = days.map(d => `<div class="wk"><div class="cols">
      <div class="s" title="studied ${fmtMin(d.study)}" style="height:${((d.study || 0) / wmax) * 100}%"></div>
      <div class="x" title="distracted ${fmtMin(d.distracted)}" style="height:${((d.distracted || 0) / wmax) * 100}%"></div></div>
      <div class="lbl">${esc(d.date.slice(5))}</div></div>`).join("");
  $("quizHistory").innerHTML = quizHistory.length ? quizHistory.slice(0, 8).map(q =>
    `<div>${q.score / q.total >= .8 ? "🔥" : q.score / q.total >= .5 ? "👍" : "📖"} <b>${q.score}/${q.total}</b> — ${esc(q.title)} <span class="muted">(Class ${esc(q.cls)} ${esc(q.subject || "")}, ${new Date(q.at).toLocaleDateString()})</span></div>`).join("")
    : "No quizzes yet — take one in the Quiz tab.";
  const lockedNow = focus?.locked && focus.lockUntil > Date.now();
  $("focusMsg").textContent = lockedNow ? `🔒 Distracting sites are locked until ${new Date(focus.lockUntil).toLocaleTimeString()}.`
    : `Scrolling used: ${fmtMin(focus?.counter || 0)} of ${s.limitMinutes}m before the next lock.`;
}

const openParent = () => chrome.tabs.create({ url: chrome.runtime.getURL("parent.html") });
$("openParent").onclick = openParent;
$("openParent2").onclick = openParent;
$("lockNow").onclick = async () => {
  await chrome.runtime.sendMessage({ type: "lockNow", host: "manual lock" });
  $("focusMsg").textContent = "🔒 Locked! Open YouTube or Instagram in a new tab to see the lock screen.";
};

// ---------------- my marks ----------------
async function renderMarks() {
  let d;
  try { d = await api("/api/profile"); } catch (e) { $("markList").innerHTML = `<div class="err">Backend offline.</div>`; return; }
  const p = d.profile;
  $("pName").value = p.name || ""; $("pCls").value = p.cls || ""; $("pSchool").value = p.school || ""; $("pGoal").value = p.goal || "";
  $("subjList").innerHTML = [...new Set(Object.values(CATALOG).flatMap(Object.keys))].map(s => `<option value="${esc(s)}">`).join("");
  if (!$("mDate").value) $("mDate").value = new Date().toLocaleDateString("en-CA");
  const recs = d.records;
  const bySub = {};
  recs.forEach(r => (bySub[r.subject] = bySub[r.subject] || []).push((r.marks / r.max_marks) * 100));
  const avgs = Object.entries(bySub).map(([s, a]) => [s, a.reduce((x, y) => x + y, 0) / a.length]).sort((a, b) => b[1] - a[1]);
  $("subjBars").innerHTML = avgs.map(([s, v]) => `<div class="bar"><span class="name">${v >= 75 ? "🟢" : v >= 50 ? "🟡" : "🔴"} ${esc(s)}</span>
      <div class="t"><div class="${v < 50 ? "bad" : ""}" style="width:${v}%"></div></div><span>${Math.round(v)}%</span></div>`).join("")
    || `<div class="muted">Add your first exam result →</div>`;
  $("markList").innerHTML = recs.length ? recs.slice().reverse().map(r => `<div class="deckrow"><span><b>${esc(r.exam)}</b> · ${esc(r.subject)}
      <span class="muted">${esc(r.date || "")}</span></span><span class="row"><b>${r.marks}/${r.max_marks}</b>
      <span class="pill">${Math.round((r.marks / r.max_marks) * 100)}%</span><button class="btn-ghost" data-del="${esc(r.id)}">✕</button></span></div>`).join("")
    : `<div class="muted">No exams yet.</div>`;
  $("markList").querySelectorAll("[data-del]").forEach(b => b.onclick = async () => {
    await api("/api/records/" + b.dataset.del, undefined, { method: "DELETE" });
    renderMarks();
  });
}
// Parent PIN (website accounts only): lets a parent see this student's progress at /parent-view
async function loadPinCard() {
  try {
    const s = await api("/api/my-parent-pin");
    $("pinCard").hidden = !s.web_account;
    $("pinMsg").textContent = s.set ? "✓ A parent PIN is set. Saving a new one replaces it." : "";
  } catch (e) { $("pinCard").hidden = true; }
}
$("pinSave").onclick = async () => {
  try { await api("/api/my-parent-pin", { pin: $("pinIn").value }); $("pinIn").value = ""; $("pinMsg").textContent = "✓ Saved — tell your parent the PIN."; }
  catch (err) { $("pinMsg").textContent = err.message; }
};

$("profileForm").onsubmit = async e => {
  e.preventDefault();
  await api("/api/profile", { name: $("pName").value.trim(), cls: Number($("pCls").value) || null, school: $("pSchool").value.trim(), goal: $("pGoal").value.trim() });
  $("profileMsg").textContent = " ✓ Saved";
};
$("markForm").onsubmit = async e => {
  e.preventDefault();
  try {
    await api("/api/records", { exam: $("mExam").value.trim(), subject: $("mSubject").value.trim(),
      marks: Number($("mMarks").value), max_marks: Number($("mMax").value), date: $("mDate").value });
    $("markMsg").textContent = " ✓ Added";
    $("mMarks").value = "";
    renderMarks();
  } catch (err) { $("markMsg").textContent = " " + err.message; }
};

// ---------------- agent ----------------
let agentHistory = [];
try { agentHistory = JSON.parse(sessionStorage.getItem("krypton.agent") || "[]"); } catch (e) { agentHistory = []; }

function bubble(role, html) {
  const div = document.createElement("div");
  div.className = "bubble " + role;
  div.innerHTML = html;
  $("msgs").appendChild(div);
  $("msgs").scrollTop = $("msgs").scrollHeight;
  return div;
}
const fmtText = t => esc(t).replace(/```(\w*)\n?([\s\S]*?)```/g, (_, l, c) => `<pre>${c}</pre>`)
  .replace(/\*\*(.+?)\*\*/g, "<b>$1</b>").replace(/`([^`]+)`/g, "<code>$1</code>").replace(/\n/g, "<br>");

agentHistory.forEach(m => bubble(m.role === "user" ? "me" : "bot", fmtText(m.content)));

async function sendAgent(text) {
  if (!text.trim()) return;
  bubble("me", esc(text));
  agentHistory.push({ role: "user", content: text });
  const wait = bubble("bot", `<div class="loading" style="padding:4px"><div class="spin"></div>Thinking…</div>`);
  const btn = $("agentForm").querySelector("button");
  btn.disabled = true;
  try {
    const res = await api("/api/agent", { messages: agentHistory });
    const steps = res.steps.filter(s => s.tool !== "offline").map(s =>
      `<span class="step">🔧 ${esc(s.tool)}${Object.values(s.args)[0] ? " · " + esc(Object.values(s.args)[0]).slice(0, 50) : ""}</span>`).join("");
    const notes = res.notes?.length ? `<div class="note">⚠ ${res.notes.map(esc).join("<br>")}</div>` : "";
    wait.innerHTML = notes + (steps ? `<div class="steps">${steps}</div>` : "") + fmtText(res.reply || "Done.") +
      `<div class="meta" style="margin:8px 0 0"><span class="pill engine ${res.engine}">${ENGINE_LABEL[res.engine] || res.engine}</span><span class="pill">${(res.ms / 1000).toFixed(1)}s</span></div>`;
    agentHistory.push({ role: "assistant", content: res.reply || "Done." });
    if (voiceOn || spokenTurn) speak(res.reply || "Done.", wait);
    spokenTurn = false;
    try { sessionStorage.setItem("krypton.agent", JSON.stringify(agentHistory.slice(-30))); } catch (e) { /* ignore */ }
    for (const a of res.actions || []) runAction(a);
  } catch (err) {
    wait.innerHTML = `<div class="err">${esc(err.message)}</div>`;
  } finally { btn.disabled = false; }
}

function runAction(a) {
  if (a.type === "open_tab") chrome.tabs.create({ url: a.url, active: false });
  else if (a.type === "web_search") chrome.tabs.create({ url: "https://www.google.com/search?q=" + encodeURIComponent(a.query), active: false });
  else if (a.type === "open_krypton" && RENDER[a.tool]) setTimeout(() => jump(a.tool, a.topic), 600);
}

// ---------------- voice: speak replies, hear instructions ----------------
let voiceOn = false, spokenTurn = false;
try { voiceOn = localStorage.getItem("krypton.voice") === "1"; } catch (e) { /* ignore */ }
const voiceBtn = () => { $("agentVoice").textContent = voiceOn ? "🔊" : "🔇"; $("agentVoice").classList.toggle("on", voiceOn); };
voiceBtn();
$("agentVoice").onclick = () => {
  voiceOn = !voiceOn;
  try { localStorage.setItem("krypton.voice", voiceOn ? "1" : "0"); } catch (e) { /* ignore */ }
  if (!voiceOn) stopVoice();
  voiceBtn();
};

// Turn maths/science symbols into words so they're read properly instead of skipped or mangled.
const SUB = { "₀": "0", "₁": "1", "₂": "2", "₃": "3", "₄": "4", "₅": "5", "₆": "6", "₇": "7", "₈": "8", "₉": "9" };
function speakable(text) {
  let t = text.replace(/```[\s\S]*?```/g, " (the code is shown on screen) ")
    .replace(/https?:\/\/\S+/g, " the link ")
    .replace(/[\u{1F300}-\u{1FAFF}\u{2600}-\u{27BF}\u{FE0F}]/gu, " ")
    .replace(/([A-Za-z])([₀-₉]+)/g, (_, a, d) => `${a} ${[...d].map(c => SUB[c]).join("")} `)   // H₂O -> H 2 O
    .replace(/([A-Za-z)])\s*\^\s*2\b|([A-Za-z0-9)])²/g, "$1$2 squared ")
    .replace(/([A-Za-z)])\s*\^\s*3\b|([A-Za-z0-9)])³/g, "$1$2 cubed ")
    .replace(/\^\s*(-?\d+)/g, " to the power $1 ")
    .replace(/√\s*/g, " square root of ")
    .replace(/(\d)\s*°\s*C\b/g, "$1 degrees Celsius").replace(/°/g, " degrees ")
    .replace(/(\d)\s*%/g, "$1 percent")
    .replace(/(\d)\s*\/\s*(\d)/g, "$1 by $2")
    .replace(/(\d)\s*[x×]\s*(\d)/g, "$1 times $2")
    .replace(/(\d|\))\s*[-−–]\s*(\d|\()/g, "$1 minus $2");
  const words = [["→", " gives "], ["⟶", " gives "], ["⇌", " is in equilibrium with "], ["≠", " is not equal to "],
    ["≤", " is less than or equal to "], ["≥", " is greater than or equal to "], ["≈", " is approximately "],
    ["=", " equals "], ["+", " plus "], ["×", " times "], ["÷", " divided by "], ["±", " plus or minus "],
    ["<", " is less than "], [">", " is greater than "], ["π", " pi "], ["Δ", " delta "], ["θ", " theta "],
    ["λ", " lambda "], ["μ", " micro "], ["Ω", " ohms "], ["∞", " infinity "], ["∴", " therefore "],
    ["∵", " because "], ["½", " half "], ["¼", " one quarter "], ["¾", " three quarters "], ["∠", " angle "], ["⊥", " is perpendicular to "], ["∥", " is parallel to "], ["&", " and "], ["@", " at "]];
  for (const [s, w] of words) t = t.split(s).join(w);
  return t.replace(/^\s*[-•*]\s+/gm, "").replace(/^\s*(\d+)\.\s+/gm, "$1, ").replace(/[*_`#|~\\[\]{}]/g, " ")
    .replace(/\s+/g, " ").trim();
}

let audioCtx = null, voiceNodes = [];
function stopVoice() {
  speechSynthesis.cancel();
  voiceNodes.forEach(n => { try { n.stop(); } catch (e) { /* already stopped */ } });
  voiceNodes = [];
}

function impulse(ctx, seconds, decay) {
  const len = ctx.sampleRate * seconds, buf = ctx.createBuffer(2, len, ctx.sampleRate);
  for (let ch = 0; ch < 2; ch++) {
    const d = buf.getChannelData(ch);
    for (let i = 0; i < len; i++) d[i] = (Math.random() * 2 - 1) * Math.pow(1 - i / len, decay);
  }
  return buf;
}

// Deep, dark, echoing "villain" voice: Windows male voice -> pitched down -> dark EQ -> sub-octave growl -> echo + reverb.
async function scaryVoice(text, el) {
  const res = await fetch(API + "/api/tts", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ text }) });
  if (!res.ok) throw new Error("no server voice");
  audioCtx = audioCtx || new AudioContext();
  const ctx = audioCtx;
  const buf = await ctx.decodeAudioData(await res.arrayBuffer());
  const out = ctx.createGain(); out.gain.value = 0.9; out.connect(ctx.destination);
  const low = ctx.createBiquadFilter(); low.type = "lowshelf"; low.frequency.value = 220; low.gain.value = 7;
  const dark = ctx.createBiquadFilter(); dark.type = "highshelf"; dark.frequency.value = 3200; dark.gain.value = -9;
  const shaper = ctx.createWaveShaper();
  const curve = new Float32Array(1024);
  for (let i = 0; i < 1024; i++) { const x = i / 512 - 1; curve[i] = Math.tanh(2.2 * x); }
  shaper.curve = curve;
  low.connect(dark).connect(shaper);
  const dry = ctx.createGain(); dry.gain.value = 0.75; shaper.connect(dry).connect(out);
  const verb = ctx.createConvolver(); verb.buffer = impulse(ctx, 2.6, 2.4);
  const wet = ctx.createGain(); wet.gain.value = 0.38; shaper.connect(verb).connect(wet).connect(out);
  const delay = ctx.createDelay(); delay.delayTime.value = 0.27;
  const fb = ctx.createGain(); fb.gain.value = 0.28;
  const echo = ctx.createGain(); echo.gain.value = 0.22;
  shaper.connect(delay).connect(fb).connect(delay); delay.connect(echo).connect(out);
  const main = ctx.createBufferSource(); main.buffer = buf; main.playbackRate.value = 0.8; main.connect(low);
  const growl = ctx.createBufferSource(); growl.buffer = buf; growl.playbackRate.value = 0.8; growl.detune.value = -1200;
  const gg = ctx.createGain(); gg.gain.value = 0.18; growl.connect(gg).connect(low);   // an octave lower, underneath
  if (ctx.state === "suspended") await ctx.resume();
  const t = ctx.currentTime + 0.05;
  main.start(t); growl.start(t);
  voiceNodes = [main, growl];
  el?.classList.add("speaking");
  main.onended = () => el?.classList.remove("speaking");
}

// Which Indian language a piece of text is in, from its script (Devanagari defaults to Hindi).
const SCRIPT_TAGS = [[/[ঀ-৿]/, "bn-IN"], [/[਀-੿]/, "pa-IN"], [/[઀-૿]/, "gu-IN"], [/[଀-୿]/, "or-IN"],
  [/[஀-௿]/, "ta-IN"], [/[ఀ-౿]/, "te-IN"], [/[ಀ-೿]/, "kn-IN"], [/[ഀ-ൿ]/, "ml-IN"],
  [/[؀-ۿ]/, "ur-IN"], [/[᱐-᱿]/, "sat-IN"], [/[ꯀ-꯿]/, "mni-IN"], [/[ऀ-ॿ]/, "hi-IN"]];

// speak(text, el) = Krypton's deep voice; speak(text, el, "ta-IN") = natural voice for language practice.
async function speak(text, el, langTag) {
  stopVoice();
  const clean = speakable(text);
  if (!clean) return;
  const tag = langTag || (SCRIPT_TAGS.find(([re]) => re.test(clean)) || [])[1];
  if (!tag) {
    try { return await scaryVoice(clean, el); } catch (e) { /* fall back to the browser voice */ }
  }
  const voices = speechSynthesis.getVoices();
  const base = (tag || "en").split("-")[0];
  const pick = tag ? (voices.find(v => v.lang.toLowerCase() === tag.toLowerCase()) || voices.find(v => v.lang.toLowerCase().startsWith(base)))
    : voices.find(v => /david|male|ravi|guy/i.test(v.name) && v.lang.startsWith("en")) || voices.find(v => v.lang.startsWith("en"));
  if (tag && !pick && langTag) toastMsg(`No ${tag} voice installed in Chrome — showing text only.`);
  const parts = clean.match(/[^.!?।]+[.!?।]?/g) || [clean];  // Chrome cuts off long utterances
  parts.forEach((p, i) => {
    const u = new SpeechSynthesisUtterance(p.trim());
    if (pick) u.voice = pick;
    u.lang = pick?.lang || tag || "en-US";
    u.pitch = langTag ? 1 : 0.1;   // practice = natural; Krypton = as deep as the browser goes
    u.rate = langTag ? 0.85 : 0.82;
    if (i === 0) u.onstart = () => el?.classList.add("speaking");
    if (i === parts.length - 1) u.onend = () => el?.classList.remove("speaking");
    speechSynthesis.speak(u);
  });
}
speechSynthesis.getVoices(); // warm up the voice list

let recorder = null, chunks = [], recTimer = null;
$("agentMic").onclick = async () => {
  if (recorder?.state === "recording") return recorder.stop();
  stopVoice();
  let stream;
  try { stream = await navigator.mediaDevices.getUserMedia({ audio: true }); }
  catch (e) { bubble("bot", `<div class="err">🎤 Microphone blocked. Click the 🔒/🎤 icon in the address bar, allow the microphone, then try again.</div>`); return; }
  chunks = [];
  recorder = new MediaRecorder(stream, { mimeType: MediaRecorder.isTypeSupported("audio/webm;codecs=opus") ? "audio/webm;codecs=opus" : "" });
  recorder.ondataavailable = e => e.data.size && chunks.push(e.data);
  recorder.onstop = async () => {
    clearTimeout(recTimer);
    stream.getTracks().forEach(t => t.stop());
    $("agentMic").classList.remove("rec");
    $("agentMic").textContent = "⏳";
    $("agentInput").placeholder = "Understanding what you said…";
    try {
      const blob = new Blob(chunks, { type: recorder.mimeType || "audio/webm" });
      const res = await fetch(API + "/api/transcribe", { method: "POST", headers: { "Content-Type": blob.type }, body: blob });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || res.statusText);
      if (data.text) { spokenTurn = true; sendAgent(data.text); }
    } catch (err) {
      bubble("bot", `<div class="err">🎤 ${esc(err.message)}</div>`);
    } finally {
      $("agentMic").textContent = "🎤";
      $("agentInput").placeholder = "Ask, or tap 🎤 and say what to do…";
    }
  };
  recorder.start();
  $("agentMic").classList.add("rec");
  $("agentMic").textContent = "⏹";
  $("agentInput").placeholder = "Listening… tap ⏹ when you're done";
  recTimer = setTimeout(() => recorder.state === "recording" && recorder.stop(), 30000);
};

$("agentForm").onsubmit = e => { e.preventDefault(); const t = $("agentInput").value; $("agentInput").value = ""; sendAgent(t); };
$("agentClear").onclick = () => {
  agentHistory = [];
  try { sessionStorage.removeItem("krypton.agent"); } catch (e) { /* ignore */ }
  [...$("msgs").children].slice(1).forEach(c => c.remove());
};
document.querySelectorAll(".chip").forEach(c => c.onclick = () => sendAgent(c.textContent));

// ---------------- settings ----------------
async function renderSettings() {
  const st = await refreshStatus();
  if (!st) { $("sys").innerHTML = `<div class="err">Backend offline — run <code>start_krypton.bat</code>.</div>`; return; }
  const s = st.settings;
  $("groqModel").value = s.groq_model;
  $("ollamaModel").value = s.ollama_model;
  $("agentWorkspace").value = s.agent_workspace || "";
  const ol = st.ollama;
  const row = (k, v, ok) => `<div class="r"><span>${k}</span><span>${ok === true ? "✅" : ok === false ? "❌" : "⚠️"} ${v}</span></div>`;
  $("sys").innerHTML =
    row("NCERT library", `${st.library.books} books · ${st.library.chapters} chapters · ${st.library.chunks.toLocaleString()} passages`, st.library.chunks > 0) +
    row("Groq key", s.groq_key_set ? `set (${esc(s.groq_key_hint)})` : "not set", s.groq_key_set ? true : null) +
    row("Ollama", ol.running ? "running" : "not running", ol.running) +
    row("Local model", ol.has_model ? esc(ol.model) + " ready" : esc(ol.model) + " not downloaded", ol.has_model ? true : null) +
    row("Offline engine", "always available", true) +
    row("Current mode", ENGINE_LABEL[s.mode], true);
}
$("refreshSys").onclick = renderSettings;

// ---------------- which Krypton server the extension uses ----------------
async function setServer(conf) {
  await chrome.storage.local.set({ server: conf, rules: null });  // background worker reads this
  try {
    if (conf) { localStorage.setItem("krypton.serverUrl", conf.url); localStorage.setItem("krypton.serverToken", conf.token); }
    else { localStorage.removeItem("krypton.serverUrl"); localStorage.removeItem("krypton.serverToken"); }
  } catch (e) { /* ignore */ }
  chrome.runtime.sendMessage({ type: "serverChanged" });
  location.reload();
}
function showServer() {
  if (!chrome?.storage?.local || location.protocol.startsWith("http")) return;
  chrome.storage.local.get(["server"]).then(({ server }) => {
    $("srvNow").innerHTML = server?.url ? `Connected to <b>${esc(server.url)}</b> as <b>@${esc(server.username || "")}</b>.` : "Using <b>this laptop</b> (default).";
    if (server?.url) $("srvUrl").value = server.url;
  });
}
$("srvConnect").onclick = async () => {
  const url = $("srvUrl").value.trim().replace(/\/+$/, "");
  if (!/^https:\/\/.+/.test(url)) { $("srvMsg").textContent = "Paste the full https:// link of the online Krypton."; return; }
  $("srvMsg").textContent = "Connecting…";
  try {
    const r = await fetch(url + "/api/auth/login", { method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ username: $("srvUser").value, password: $("srvPw").value }) });
    const d = await r.json();
    if (!r.ok) throw new Error(d.detail || "Couldn't log in");
    await setServer({ url, token: d.token, username: d.user.username });
  } catch (err) { $("srvMsg").textContent = "Couldn't connect: " + err.message + " (if it's a Render free site, open it once in a tab to wake it, then retry)."; }
};
$("srvLocal").onclick = () => setServer(null);
showServer();
$("saveSettings").onclick = async () => {
  const body = { groq_model: $("groqModel").value.trim(), ollama_model: $("ollamaModel").value.trim(),
                 agent_workspace: $("agentWorkspace").value.trim() || null };
  try {
    await api("/api/settings", body);
    $("settingsMsg").textContent = "✓ Saved.";
  } catch (e) { $("settingsMsg").textContent = "Couldn't save: " + e.message; }
  renderSettings();
};

// ---------------- study time ----------------
setInterval(() => {
  if (document.visibilityState === "visible" && document.hasFocus()) chrome.runtime.sendMessage({ type: "studyTick", sec: 5 });
}, 5000);

// ---------------- XP, streaks, badges ----------------
function toastMsg(text) {
  let box = document.querySelector(".toastx");
  if (!box) { box = document.createElement("div"); box.className = "toastx"; document.body.appendChild(box); }
  const t = document.createElement("div");
  t.textContent = text;
  box.appendChild(t);
  setTimeout(() => t.remove(), 3200);
}

function gainXp(res) {
  if (!res) return;
  if (res.gained) toastMsg(`+${res.gained} XP ⭐`);
  (res.new_badges || []).forEach(b => toastMsg(`${b.icon} Badge unlocked: ${b.name}!`));
  if (res.xp?.level || res.xp?.gained) gainXp(res.xp);
  refreshGame();
}

async function refreshGame() {
  try {
    const [g, r] = await Promise.all([api("/api/game"), api("/api/review")]);
    $("gStreak").textContent = `🔥 ${g.streak} day${g.streak === 1 ? "" : "s"}`;
    $("gLevel").textContent = `Lv ${g.level} · ${g.title}`;
    $("gBar").style.width = `${Math.min(100, ((g.xp - g.level_from) / (g.level_to - g.level_from)) * 100)}%`;
    $("gXp").textContent = `${g.xp} XP`;
    $("gToday").textContent = `${g.today}/${g.goal} today`;
    $("dueBadge").hidden = !r.due_count;
    $("dueBadge").textContent = r.due_count;
  } catch (e) { /* backend offline */ }
}
$("gamebox").onclick = () => showTab("progress");

async function renderProgress() {
  const g = await api("/api/game");
  const pct = Math.min(100, ((g.xp - g.level_from) / (g.level_to - g.level_from)) * 100);
  $("levelCard").innerHTML = `<div class="muted">LEVEL</div><div class="lv grad">${g.level}</div><div class="ttl">${esc(g.title)}</div>
    <div class="gbar"><div style="width:${pct}%"></div></div><div class="muted small-note">${g.xp - g.level_from} / ${g.level_to - g.level_from} XP to level ${g.level + 1}</div>
    <div class="stats"><div class="kpi"><b>🔥 ${g.streak}</b><span>day streak</span></div>
      <div class="kpi"><b>${g.today}/${g.goal}</b><span>XP today</span></div><div class="kpi"><b>${g.best_streak}</b><span>best streak</span></div></div>`;
  $("heat").innerHTML = g.calendar.map(c => `<div class="${c.xp >= g.goal ? "h3" : c.xp >= g.goal / 2 ? "h2" : c.xp > 0 ? "h1" : ""}" title="${esc(c.date)}: ${c.xp} XP"></div>`).join("");
  $("badges").innerHTML = g.badges.map(b => `<div class="bdg ${b.earned ? "" : "locked"}"><div class="i">${b.icon}</div><b>${esc(b.name)}</b>
    <span>${b.earned ? "Earned " + esc(b.earned) : esc(b.desc)}</span></div>`).join("");
  let me = "You";
  try { me = (await api("/api/profile")).profile.name || "You"; } catch (e) { /* ignore */ }
  const rows = [...g.friends.map(f => ({ ...f, me: false })), { name: me, xp: g.xp, streak: g.streak, level: g.level, me: true }]
    .sort((a, b) => b.xp - a.xp);
  $("board").innerHTML = `<div class="lb muted"><span>#</span><span>Name</span><span>XP</span><span>Level</span><span>Streak</span></div>` +
    rows.map((r, i) => `<div class="lb ${r.me ? "me" : ""}"><span class="rk">${["🥇", "🥈", "🥉"][i] || i + 1}</span><span>${esc(r.name)}${r.me ? " (you)" : ""}</span>
      <b>${r.xp}</b><span>Lv ${r.level}</span><span>🔥 ${r.streak}</span></div>`).join("");
  $("myCode").value = g.my_code;
}
$("copyCode").onclick = () => { navigator.clipboard.writeText($("myCode").value); $("friendMsg").textContent = "✓ Copied — send it to your friends."; };
$("addFriend").onclick = async () => {
  try { await api("/api/game/friend", { code: $("friendCode").value }); $("friendCode").value = ""; $("friendMsg").textContent = "✓ Friend added."; renderProgress(); }
  catch (err) { $("friendMsg").textContent = err.message; }
};

// ---------------- revise (weak spots + spaced repetition) ----------------
async function renderRevise() {
  const r = await api("/api/review");
  $("revStart").innerHTML = r.due_count
    ? `<p><b>${r.due_count}</b> question${r.due_count === 1 ? "" : "s"} due today.</p><button class="btn-primary" id="revGo">Start revision →</button>`
    : `<p class="muted">🎉 Nothing due right now. Take quizzes — any mistakes will show up here for revision.</p>`;
  $("revBoxes").innerHTML = r.boxes.map((n, i) => `<div><b>${n}</b>Box ${i + 1}<br><span>${["today", "1 day", "3 days", "7 days", "14 days"][i]}</span></div>`).join("") +
    "" ;
  $("weakList").innerHTML = r.weak.length ? r.weak.map((w, i) => `<div class="weak"><span><b>${esc(w.title)}</b><br>
      <span class="muted">Class ${esc(w.cls)} ${esc(w.subject)} · ${w.wrong} wrong of ${w.total}</span></span>
      <span class="row"><b>${w.accuracy}%</b><button class="btn-ghost" data-w="${i}">Explain</button><button class="btn-ghost" data-q="${i}">Quiz</button></span>
      <div class="t"><div style="width:${w.accuracy}%"></div></div></div>`).join("")
    : `<p class="muted">No weak chapters yet — great, or take a few quizzes first.</p>`;
  const go = (tab, w) => {
    $("cls").value = String(w.cls); fillSubjects(w.subject);
    const box = $("chapMenu").querySelector(`input[value="${CSS.escape(w.key)}"]`);
    if (box) { box.checked = true; selectedChapters.add(w.key); chapLabel(); }
    jump(tab, "");
  };
  $("weakList").querySelectorAll("[data-w]").forEach(b => b.onclick = () => go("explain", r.weak[b.dataset.w]));
  $("weakList").querySelectorAll("[data-q]").forEach(b => b.onclick = () => go("quiz", r.weak[b.dataset.q]));
  if ($("revGo")) $("revGo").onclick = () => reviewSession(r.due);
  $("revOut").innerHTML = "";
}

function reviewSession(cards) {
  let i = 0, right = 0;
  const out = $("revOut");
  const step = () => {
    if (i >= cards.length) {
      out.innerHTML = `<div class="card score"><div class="muted">Revision done</div><div class="big grad">${right}/${cards.length}</div>
        <div>Correct cards move up a box and come back later. Missed ones return tomorrow.</div></div>`;
      renderRevise(); refreshGame();
      return;
    }
    const c = cards[i];
    out.innerHTML = `<div class="card qcard"><div class="qprog"><div style="width:${(i / cards.length) * 100}%"></div></div>
      <div class="muted">Card ${i + 1} of ${cards.length} · Box ${c.box} · ${esc(c.chapter?.title || "")}</div>
      <div class="qtext">${esc(c.question)}</div>
      <div class="opts">${c.options.map((o, j) => `<button class="opt" data-j="${j}"><span class="k">${"ABCD"[j]}</span><span>${esc(o)}</span></button>`).join("")}</div>
      <div id="rx"></div></div>`;
    out.querySelectorAll(".opt").forEach(b => b.onclick = async () => {
      out.querySelectorAll(".opt").forEach(x => { x.disabled = true; });
      const res = await api("/api/review/answer", { id: c.id, choice: Number(b.dataset.j) });
      gainXp(res);
      if (res.correct) right++;
      out.querySelectorAll(".opt").forEach(x => { if (x.querySelector("span:last-child").textContent === res.answer) x.classList.add("right"); });
      if (!res.correct) b.classList.add("wrong");
      $("rx").innerHTML = `<div class="expl">${res.correct ? (res.mastered ? "🏆 Mastered! This card is retired." : `✅ Correct — moved to box ${res.box}, next review ${esc(res.next_due)}.`)
        : "❌ Back to box 1 — you'll see it again tomorrow."} ${esc(res.explanation || "")}</div>
        <div class="row" style="margin-top:12px"><button class="btn-primary" id="rnext">${i + 1 < cards.length ? "Next →" : "Finish"}</button></div>`;
      $("rnext").onclick = () => { i++; step(); };
    });
  };
  step();
}

// ---------------- snap & solve (step-by-step tutor, no answers) ----------------
let snapData = null, tutorSession = null;

function setSnapImage(file) {
  if (!file || !file.type.startsWith("image/")) return;
  const reader = new FileReader();
  reader.onload = () => shrinkImage(reader.result).then(url => {
    snapData = url;
    $("snapImg").src = url; $("snapImg").hidden = false; $("dropMsg").hidden = true;
    $("readBtn").disabled = false;
    readQuestion();
  });
  reader.readAsDataURL(file);
}

function shrinkImage(url, max = 1600) {
  return new Promise(resolve => {
    const img = new Image();
    img.onload = () => {
      const k = Math.min(1, max / Math.max(img.width, img.height));
      const c = document.createElement("canvas");
      c.width = img.width * k; c.height = img.height * k;
      c.getContext("2d").drawImage(img, 0, 0, c.width, c.height);
      resolve(c.toDataURL("image/jpeg", 0.88));
    };
    img.src = url;
  });
}

async function readQuestion() {
  if (!snapData) return;
  $("snapMsg").textContent = "🔍 Reading your photo…";
  try {
    const r = await api("/api/tutor/read", { image: snapData, kind: "question" });
    $("snapQ").value = r.text;
    $("snapMsg").textContent = "✓ Check the question below, fix anything misread, then start solving.";
  } catch (err) { $("snapMsg").textContent = "Couldn't read the photo: " + err.message + " — you can type the question instead."; }
}

$("drop").onclick = () => $("snapFile").click();
$("drop").onkeydown = e => { if (e.key === "Enter") $("snapFile").click(); };
$("snapFile").onchange = e => setSnapImage(e.target.files[0]);
$("drop").ondragover = e => { e.preventDefault(); $("drop").classList.add("over"); };
$("drop").ondragleave = () => $("drop").classList.remove("over");
$("drop").ondrop = e => { e.preventDefault(); $("drop").classList.remove("over"); setSnapImage(e.dataTransfer.files[0]); };
document.addEventListener("paste", e => {
  if (!$("tab-snap").classList.contains("active")) return;
  const f = [...(e.clipboardData?.files || [])].find(x => x.type.startsWith("image/"));
  if (f) setSnapImage(f);
});
$("readBtn").onclick = readQuestion;

let camStream = null;
$("camBtn").onclick = async () => {
  if (camStream) { // second click: take the photo
    const v = $("cam"), c = document.createElement("canvas");
    c.width = v.videoWidth; c.height = v.videoHeight;
    c.getContext("2d").drawImage(v, 0, 0);
    camStream.getTracks().forEach(t => t.stop()); camStream = null;
    v.hidden = true; $("camBtn").textContent = "🎥 Use webcam";
    c.toBlob(b => setSnapImage(new File([b], "cam.jpg", { type: "image/jpeg" })), "image/jpeg", 0.9);
    return;
  }
  try {
    camStream = await navigator.mediaDevices.getUserMedia({ video: { facingMode: "environment" } });
    $("cam").srcObject = camStream; $("cam").hidden = false; $("camBtn").textContent = "📸 Take photo";
  } catch (e) { $("snapMsg").textContent = "Camera blocked — allow it in the address bar, or upload a photo instead."; }
};

$("solveBtn").onclick = async () => {
  const q = $("snapQ").value.trim();
  if (!q) { $("snapMsg").textContent = "Type the question or add a photo first."; return; }
  $("solveBtn").disabled = true;
  $("snapOut").innerHTML = `<div class="card loading"><div class="spin"></div>Krypton is planning the steps (it won't show you the answers)…</div>`;
  try {
    const ctx = context();
    tutorSession = await api("/api/tutor/start", { question: q, cls: ctx.cls, subject: ctx.subject });
    tutorSession.done = [];
    renderStep();
  } catch (err) { $("snapOut").innerHTML = `<div class="err">${esc(err.message)}</div>`; }
  finally { $("solveBtn").disabled = false; }
};

function renderStep(extra = "") {
  const s = tutorSession;
  $("snapOut").innerHTML = `<div class="card stepcard">
      <div class="qbox"><b>Question:</b> ${esc(s.question)}${s.topic ? `<div class="muted small-note">Topic: ${esc(s.topic)}</div>` : ""}</div>
      ${s.done.map((w, i) => `<div class="done">✅ <span><b>Step ${i + 1}:</b> ${esc(w)}</span></div>`).join("")}
      <div class="qprog"><div style="width:${(s.done.length / s.total) * 100}%"></div></div>
      <div class="stepn">STEP ${s.step.n} OF ${s.total}</div>
      <div class="stepgoal">${esc(s.step.goal)}</div>
      <textarea id="stepWork" rows="3" placeholder="Write your working for this step…"></textarea>
      <div class="row" style="margin-top:10px">
        <button class="btn-primary" id="checkStep">Check my step</button>
        <button class="btn-ghost" id="hintBtn">💡 Hint</button>
        <button class="btn-ghost" id="workPhoto">📷 Photo of my working</button>
        <input type="file" id="workFile" accept="image/*" hidden></div>
      <div id="stepFb">${extra}</div></div>`;
  $("stepWork").focus();
  $("checkStep").onclick = checkStep;
  $("stepWork").onkeydown = e => { if (e.key === "Enter" && e.ctrlKey) checkStep(); };
  $("hintBtn").onclick = async () => {
    const h = await api("/api/tutor/hint", { session_id: s.session_id });
    $("stepFb").innerHTML = `<div class="hintbox">💡 ${esc(h.hint)}</div>`;
  };
  $("workPhoto").onclick = () => $("workFile").click();
  $("workFile").onchange = e => {
    const f = e.target.files[0];
    if (!f) return;
    const rd = new FileReader();
    rd.onload = async () => {
      $("stepFb").innerHTML = `<div class="muted">🔍 Reading your working…</div>`;
      try {
        const r = await api("/api/tutor/read", { image: await shrinkImage(rd.result), kind: "work" });
        $("stepWork").value = r.text;
        $("stepFb").innerHTML = `<div class="muted">✓ Read it — check the text, then press "Check my step".</div>`;
      } catch (err) { $("stepFb").innerHTML = `<div class="err">${esc(err.message)}</div>`; }
    };
    rd.readAsDataURL(f);
  };
}

async function checkStep() {
  const work = $("stepWork").value.trim();
  if (!work) return;
  $("checkStep").disabled = true;
  $("stepFb").innerHTML = `<div class="muted">Checking…</div>`;
  try {
    const r = await api("/api/tutor/check", { session_id: tutorSession.session_id, work });
    if (r.xp) gainXp(r.xp);
    if (r.correct) {
      tutorSession.done.push(work);
      if (r.solved) {
        $("snapOut").innerHTML = `<div class="card score"><div class="big">🎉</div><h2>You solved it yourself!</h2>
          <p class="muted">${esc(r.feedback)}</p><div style="text-align:left">${tutorSession.done.map((w, i) => `<div class="done">✅ <span><b>Step ${i + 1}:</b> ${esc(w)}</span></div>`).join("")}</div>
          <div class="row" style="justify-content:center;margin-top:14px"><button class="btn-primary" id="nextQ">Solve another</button></div></div>`;
        $("nextQ").onclick = () => { $("snapOut").innerHTML = ""; $("snapQ").value = ""; $("snapImg").hidden = true; $("dropMsg").hidden = false; snapData = null; window.scrollTo({ top: 0, behavior: "smooth" }); };
        return;
      }
      tutorSession.step = r.step;
      renderStep(`<div class="expl">✅ ${esc(r.feedback)} On to the next step!</div>`);
    } else {
      $("stepFb").innerHTML = `<div class="expl">❌ ${esc(r.feedback)}</div>${r.hint ? `<div class="hintbox">💡 ${esc(r.hint)}</div>` : ""}`;
      $("checkStep").disabled = false;
    }
  } catch (err) { $("stepFb").innerHTML = `<div class="err">${esc(err.message)}</div>`; $("checkStep").disabled = false; }
}

// ---------------- viva (oral exam) ----------------
// Records one spoken answer: first click starts, second click stops. Resolves with the transcript.
function recordSpeech(btn, lang = "") {
  return new Promise(async (resolve, reject) => {
    let stream;
    try { stream = await navigator.mediaDevices.getUserMedia({ audio: true }); }
    catch (e) { return reject(new Error("Microphone blocked — allow it in the address bar, or type your answer.")); }
    stopVoice();
    const parts = [];
    const rec = new MediaRecorder(stream, { mimeType: MediaRecorder.isTypeSupported("audio/webm;codecs=opus") ? "audio/webm;codecs=opus" : "" });
    const label = btn.textContent;
    rec.ondataavailable = e => e.data.size && parts.push(e.data);
    rec.onstop = async () => {
      clearTimeout(timer);
      stream.getTracks().forEach(t => t.stop());
      btn.classList.remove("rec");
      btn.textContent = "⏳ Listening back…";
      try {
        const blob = new Blob(parts, { type: rec.mimeType || "audio/webm" });
        const res = await fetch(API + "/api/transcribe" + (lang ? `?lang=${encodeURIComponent(lang)}` : ""), { method: "POST", headers: { "Content-Type": blob.type }, body: blob });
        const data = await res.json();
        if (!res.ok) throw new Error(data.detail || res.statusText);
        resolve(data.text || "");
      } catch (err) { reject(err); }
      finally { btn.textContent = label; btn.onclick = btn._start; }
    };
    rec.start();
    btn.classList.add("rec");
    btn.textContent = "⏹ Stop answering";
    btn._start = btn.onclick;
    btn.onclick = () => rec.state === "recording" && rec.stop();
    const timer = setTimeout(() => rec.state === "recording" && rec.stop(), 60000);
  });
}

let vivaS = null;
$("vivaGo").onclick = async () => {
  $("vivaGo").disabled = true;
  $("vivaMsg").textContent = "";
  $("vivaOut").innerHTML = `<div class="card loading"><div class="spin"></div>The examiner is preparing your questions…</div>`;
  try {
    const ctx = context();
    vivaS = await api("/api/viva/start", { ...ctx, query: $("vivaTopic").value.trim(), count: Number($("vivaCount").value) });
    vivaS.scores = [];
    askViva(vivaS.question, `Welcome to your viva on ${vivaS.topic}. ${vivaS.total} questions. First question.`);
  } catch (err) { $("vivaOut").innerHTML = `<div class="err">${esc(err.message)}</div>`; }
  finally { $("vivaGo").disabled = false; }
};

function askViva(question, intro = "", note = "") {
  const s = vivaS;
  const hide = $("vivaHide").checked;
  $("vivaOut").innerHTML = `<div class="card stepcard">
      <div class="examiner"><div class="orb" id="orb"></div><div style="flex:1">
        <div class="stepn">${note ? "FOLLOW-UP · " : ""}QUESTION ${s.n} OF ${s.total} · ${esc(s.topic)}</div>
        <div class="vq ${hide ? "hidden" : ""}" id="vq" title="${hide ? "Click to show the question" : ""}">${esc(question)}</div>
        <div class="dots">${Array.from({ length: s.total }, (_, i) => `<i class="${i < s.n - 1 ? "on" : ""}"></i>`).join("")}</div></div></div>
      ${note ? `<div class="expl" style="margin-top:12px">${note}</div>` : ""}
      <textarea id="vivaAns" rows="3" placeholder="Speak with 🎤, or type your answer here…" style="margin-top:14px"></textarea>
      <div class="row" style="margin-top:10px">
        <button class="btn-primary mic" id="vivaMic">🎤 Answer out loud</button>
        <button class="btn-ghost" id="vivaSend">Submit typed answer</button>
        <button class="btn-ghost" id="vivaRepeat">🔁 Repeat question</button>
        <button class="btn-ghost" id="vivaSkip">Skip</button></div>
      <div id="vivaFb"></div></div>`;
  const say = () => speak((intro ? intro + " " : "") + question, $("orb"));
  say();
  intro = "";
  $("vq").onclick = () => $("vq").classList.remove("hidden");
  $("vivaRepeat").onclick = say;
  $("vivaSkip").onclick = () => submitViva("");
  $("vivaSend").onclick = () => submitViva($("vivaAns").value);
  $("vivaMic").onclick = async () => {
    try {
      const text = await recordSpeech($("vivaMic"));
      $("vivaAns").value = text;
      if (text) submitViva(text);
    } catch (err) { $("vivaFb").innerHTML = `<div class="err">🎤 ${esc(err.message)}</div>`; }
  };
}

async function submitViva(answer) {
  ["vivaMic", "vivaSend", "vivaSkip"].forEach(id => { if ($(id)) $(id).disabled = true; });
  stopVoice();
  $("vivaFb").innerHTML = `<div class="muted" style="margin-top:10px">The examiner is marking your answer…</div>`;
  try {
    const r = await api("/api/viva/answer", { session_id: vivaS.session_id, answer });
    if (r.xp) gainXp(r.xp);
    const stars = n => `<span style="color:#ffd75f">${"★".repeat(n)}</span><span style="opacity:.25">${"★".repeat(5 - n)}</span>`;
    const fb = `<b>${stars(r.score)}</b> ${r.score}/5 — ${esc(r.feedback)}${r.missed?.length ? `<br><span class="muted">Missed: ${r.missed.map(esc).join(" · ")}</span>` : ""}`;
    if (r.follow_up) {
      vivaS.n = r.n;
      askViva(r.follow_up, `${r.feedback} Follow-up question.`, fb);
      return;
    }
    if (r.report) return vivaReport(r.report, fb);
    vivaS.n = r.n + 1;
    const say = `${r.feedback} Next question.`;
    askViva(r.next_question, say, fb);
  } catch (err) {
    $("vivaFb").innerHTML = `<div class="err">${esc(err.message)}</div>`;
    ["vivaMic", "vivaSend", "vivaSkip"].forEach(id => { if ($(id)) $(id).disabled = false; });
  }
}

function vivaReport(rep, lastFb) {
  if (rep.xp) gainXp(rep.xp);
  speak(`Viva complete. You scored ${rep.score} out of ${rep.out_of}. ${rep.verdict}`, null);
  $("vivaOut").innerHTML = `<div class="card score"><div class="muted">Viva complete · ${esc(rep.topic)}</div>
      <div class="big grad">${rep.score}/${rep.out_of}</div><div><b>${rep.percent}%</b> — ${esc(rep.verdict)}</div>
      <div class="muted small-note">Last answer: ${lastFb}</div>
      <div class="row" style="justify-content:center;margin-top:14px"><button class="btn-primary" id="vivaAgain">New viva</button></div></div>
    <div class="card" style="margin-top:12px"><h3>Question by question</h3>${rep.results.map((x, i) => `<div class="vrow">
      <b>Q${i + 1}. ${esc(x.q)}</b> <span class="pill">${x.score}/5</span>
      <div class="muted small-note">You said: ${esc(x.answer || "(skipped)")}</div>
      <div class="small-note">${esc(x.feedback)}</div>
      <div class="expl">✅ Model answer: ${esc(x.ideal)}</div></div>`).join("")}${sourcesBlock(rep)}</div>`;
  $("vivaAgain").onclick = () => { $("vivaOut").innerHTML = ""; window.scrollTo({ top: 0, behavior: "smooth" }); };
}

// ---------------- languages: answer language + Language Lab ----------------
let LANGS = [], labWords = [];
const getStore = (k, d = "") => { try { return localStorage.getItem(k) || d; } catch (e) { return d; } };
const setStore = (k, v) => { try { localStorage.setItem(k, v); } catch (e) { /* ignore */ } };
const labLang = () => LANGS.find(l => l.code === $("labLang").value) || LANGS.find(l => l.code === "hi");
const say = (text, l) => speak(text, null, (l || labLang())?.tts);
const ear = (l, text) => `<button class="btn-ghost" data-say="${esc(text)}" title="Listen">🔊</button>`;
const wireSay = root => root.querySelectorAll("[data-say]").forEach(b => b.onclick = () => say(b.dataset.say));

async function loadLangs() {
  try { LANGS = (await api("/api/lang/list")).languages; } catch (e) { return; }
  const opt = l => `<option value="${l.code}">${esc(l.name)} · ${esc(l.native)}</option>`;
  $("ansLang").innerHTML = `<option value="">Auto (English / Hindi)</option>` + LANGS.map(opt).join("");
  $("ansLang").value = getStore("krypton.lang");
  $("labLang").innerHTML = LANGS.filter(l => l.code !== "en").map(opt).join("");
  $("labLang").value = getStore("krypton.lablang") || (getStore("krypton.lang") && getStore("krypton.lang") !== "en" ? getStore("krypton.lang") : "hi");
}
$("ansLang").onchange = () => {
  setStore("krypton.lang", $("ansLang").value);
  const l = LANGS.find(x => x.code === $("ansLang").value);
  toastMsg(l ? `Krypton will answer in ${l.name} (${l.native})` : "Krypton will answer in English / Hindi");
};
$("labLang").onchange = () => { setStore("krypton.lablang", $("labLang").value); labWords = []; renderLab(); };
document.querySelectorAll("#labTabs button").forEach(b => b.onclick = () => {
  document.querySelectorAll("#labTabs button").forEach(x => x.classList.toggle("active", x === b));
  renderLab();
});
const labKind = () => document.querySelector("#labTabs button.active")?.dataset.lab || "script";
const labLoading = t => { $("labOut").innerHTML = `<div class="card loading"><div class="spin"></div>${t}</div>`; };
const labErr = err => { $("labOut").innerHTML = `<div class="err">${esc(err.message)}</div>`; };

function renderLab() {
  if (!LANGS.length) return;
  ({ script: labScript, words: labWordsView, translate: labTranslate, speak: labSpeak, chat: labChat })[labKind()]();
}

// 🔤 Script trainer: learn the alphabet, then a recognition quiz (works offline, no AI)
async function labScript() {
  const l = labLang();
  labLoading(`Loading the ${l.script} script…`);
  let a;
  try { a = await api("/api/lang/alphabet/" + l.code); } catch (err) { return labErr(err); }
  const grid = list => `<div class="letters">${list.map(x => `<div class="letter" data-ch="${esc(x.char)}"><b>${esc(x.char)}</b><span>${esc(x.sound)}</span></div>`).join("")}</div>`;
  $("labOut").innerHTML = `<div class="card"><div class="row" style="justify-content:space-between;align-items:center">
      <h3 style="margin:0">${esc(l.name)} · ${esc(l.script)} script</h3><button class="btn-primary" id="scriptQuiz">🎯 Quiz me</button></div>
      <p class="muted">Tap a letter to hear it.${l.tts ? "" : ""}</p>
      ${a.vowels.length ? `<h4>Vowels (${a.vowels.length})</h4>${grid(a.vowels)}` : ""}
      <h4>${a.vowels.length ? "Consonants" : "Letters"} (${a.consonants.length})</h4>${grid(a.consonants)}</div>`;
  $("labOut").querySelectorAll(".letter").forEach(d => d.onclick = () => say(d.dataset.ch, l));
  $("scriptQuiz").onclick = () => scriptQuiz([...a.vowels, ...a.consonants], l);
}

function scriptQuiz(all, l) {
  let n = 0, right = 0;
  const round = () => {
    if (n >= 10) {
      $("labOut").innerHTML = `<div class="card score"><div class="muted">${esc(l.script)} letters</div><div class="big grad">${right}/10</div>
        <div class="row" style="justify-content:center;margin-top:12px"><button class="btn-primary" id="again">Again</button><button class="btn-ghost" id="back">Back to letters</button></div></div>`;
      $("again").onclick = () => scriptQuiz(all, l); $("back").onclick = labScript;
      return;
    }
    const pick = all[Math.floor(Math.random() * all.length)];
    const opts = [pick, ...all.filter(x => x.sound !== pick.sound).sort(() => Math.random() - .5).slice(0, 3)].sort(() => Math.random() - .5);
    $("labOut").innerHTML = `<div class="card qcard"><div class="qprog"><div style="width:${n * 10}%"></div></div>
      <div class="muted">Letter ${n + 1} of 10 · score ${right}</div><div class="bigchar native">${esc(pick.char)}</div>
      <div class="opts">${opts.map((o, j) => `<button class="opt" data-j="${j}"><span class="k">${"ABCD"[j]}</span><span>${esc(o.sound)}</span></button>`).join("")}</div>
      <div id="sx"></div></div>`;
    $("labOut").querySelectorAll(".opt").forEach(b => b.onclick = () => {
      const ok = opts[Number(b.dataset.j)] === pick;
      $("labOut").querySelectorAll(".opt").forEach(x => { x.disabled = true; if (opts[Number(x.dataset.j)] === pick) x.classList.add("right"); });
      if (!ok) b.classList.add("wrong");
      if (ok) { right++; api("/api/xp", { event: "lang_letter" }).then(gainXp, () => {}); }
      say(pick.char, l);
      setTimeout(() => { n++; round(); }, 1100);
    });
  };
  round();
}

// 📚 Words: AI vocabulary cards with sound, then a meaning quiz (mistakes go to Revise)
function labWordsView() {
  const l = labLang();
  $("labOut").innerHTML = `<form class="ask card" id="wordsForm"><input id="wordsTopic" placeholder="Topic — e.g. family, school, food, body parts, numbers" autocomplete="off">
      <select id="wordsCount" class="small"><option>6</option><option selected>8</option><option>12</option></select>
      <button class="btn-primary">Teach me ${esc(l.name)} words</button></form><div id="wordsOut"></div>`;
  $("wordsForm").onsubmit = async e => {
    e.preventDefault();
    $("wordsOut").innerHTML = `<div class="card loading"><div class="spin"></div>Preparing ${esc(l.name)} words…</div>`;
    try {
      const r = await api("/api/lang/words", { lang: l.code, topic: $("wordsTopic").value, level: $("labLevel").value, count: Number($("wordsCount").value) });
      labWords = r.words;
      showWords(l);
    } catch (err) { $("wordsOut").innerHTML = `<div class="err">${esc(err.message)}</div>`; }
  };
  if (labWords.length) showWords(l);
}

function showWords(l) {
  $("wordsOut").innerHTML = `<div class="toolbar"><button class="btn-primary" id="wordQuiz">🎯 Quiz me on these</button></div>
    <div class="words">${labWords.map(w => `<div class="wordcard"><div class="row" style="justify-content:space-between;align-items:center">
      <span class="w native">${esc(w.word)}</span>${ear(l, w.word)}</div>
      <div class="tr">${esc(w.translit || "")}</div><div><b>${esc(w.meaning)}</b></div>
      ${w.example ? `<div class="muted small-note"><span class="native" style="font-size:16px">${esc(w.example)}</span> ${ear(l, w.example)}<br>
        <i>${esc(w.example_translit || "")}</i><br>${esc(w.example_meaning || "")}</div>` : ""}</div>`).join("")}</div>`;
  wireSay($("wordsOut"));
  $("wordQuiz").onclick = () => wordQuiz(l);
}

function wordQuiz(l) {
  let i = 0, right = 0;
  const order = [...labWords].sort(() => Math.random() - .5);
  const step = () => {
    if (i >= order.length) {
      $("wordsOut").innerHTML = `<div class="card score"><div class="muted">${esc(l.name)} words</div><div class="big grad">${right}/${order.length}</div>
        <div>Missed words are waiting in 🎯 Revise.</div><div class="row" style="justify-content:center;margin-top:12px"><button class="btn-ghost" id="backW">Back to the words</button></div></div>`;
      $("backW").onclick = () => showWords(l);
      return;
    }
    const w = order[i];
    const opts = [w.meaning, ...labWords.filter(x => x !== w).map(x => x.meaning).sort(() => Math.random() - .5).slice(0, 3)].sort(() => Math.random() - .5);
    const q = { question: `What does “${w.word}” (${w.translit || ""}) mean?`, options: opts, answer_index: opts.indexOf(w.meaning), explanation: `${w.word} = ${w.meaning}` };
    $("wordsOut").innerHTML = `<div class="card qcard"><div class="qprog"><div style="width:${(i / order.length) * 100}%"></div></div>
      <div class="muted">Word ${i + 1} of ${order.length}</div><div class="bigchar native" style="font-size:54px">${esc(w.word)}</div>
      <div class="opts">${opts.map((o, j) => `<button class="opt" data-j="${j}"><span class="k">${"ABCD"[j]}</span><span>${esc(o)}</span></button>`).join("")}</div></div>`;
    say(w.word, l);
    $("wordsOut").querySelectorAll(".opt").forEach(b => b.onclick = () => {
      const j = Number(b.dataset.j), ok = j === q.answer_index;
      if (ok) right++;
      $("wordsOut").querySelectorAll(".opt").forEach(x => { x.disabled = true; if (Number(x.dataset.j) === q.answer_index) x.classList.add("right"); });
      if (!ok) b.classList.add("wrong");
      api("/api/attempts", { items: [{ ...q, chosen: j, tag: { code: l.code, name: l.name } }] }).then(gainXp, () => {});
      setTimeout(() => { i++; step(); }, 1100);
    });
  };
  step();
}

// ✍️ Translate: English sentence → your translation → marked out of 5 with the correct version
function labTranslate() {
  const l = labLang();
  $("labOut").innerHTML = `<div class="card"><div class="row" style="justify-content:space-between;align-items:center">
      <h3 style="margin:0">Translate into ${esc(l.name)}</h3><button class="btn-ghost" id="newSent">🔄 New sentence</button></div>
      <div class="qtext" id="engSent" style="margin:14px 0">…</div>
      <textarea id="trAns" rows="3" placeholder="Write it in ${esc(l.name)} (${esc(l.script)} script) — or in Latin letters if you can't type the script yet"></textarea>
      <div class="row" style="margin-top:10px"><button class="btn-primary" id="trCheck">Check my translation</button>
        ${l.voice_in ? `<button class="btn-ghost mic" id="trMic">🎤 Say it instead</button>` : ""}</div>
      <div id="trOut"></div></div>`;
  const fresh = async () => {
    $("engSent").textContent = "…"; $("trAns").value = ""; $("trOut").innerHTML = "";
    try { $("engSent").textContent = (await api("/api/lang/sentence", { lang: l.code, level: $("labLevel").value })).english; }
    catch (err) { $("trOut").innerHTML = `<div class="err">${esc(err.message)}</div>`; }
  };
  $("newSent").onclick = fresh;
  if ($("trMic")) $("trMic").onclick = async () => {
    try { $("trAns").value = await recordSpeech($("trMic"), l.code); } catch (err) { $("trOut").innerHTML = `<div class="err">🎤 ${esc(err.message)}</div>`; }
  };
  $("trCheck").onclick = async () => {
    $("trCheck").disabled = true;
    $("trOut").innerHTML = `<div class="muted" style="margin-top:10px">Checking…</div>`;
    try {
      const r = await api("/api/lang/check", { lang: l.code, english: $("engSent").textContent, answer: $("trAns").value });
      gainXp(r.xp);
      $("trOut").innerHTML = `<div class="expl" style="margin-top:12px"><b style="color:#ffd75f">${"★".repeat(r.score)}</b><span style="opacity:.25">${"★".repeat(5 - r.score)}</span> ${r.score}/5 — ${esc(r.feedback)}
        <div style="margin-top:8px">✅ <span class="native">${esc(r.correct)}</span> ${ear(l, r.correct)}<br><i>${esc(r.correct_translit)}</i></div></div>
        <div class="row" style="margin-top:10px"><button class="btn-primary" id="nextSent">Next sentence →</button></div>`;
      wireSay($("trOut"));
      $("nextSent").onclick = fresh;
    } catch (err) { $("trOut").innerHTML = `<div class="err">${esc(err.message)}</div>`; }
    finally { $("trCheck").disabled = false; }
  };
  fresh();
}

// 🎤 Speak: listen, say it, see how close you were
async function labSpeak() {
  const l = labLang();
  if (!l.voice_in) {
    $("labOut").innerHTML = `<div class="card"><h3>🎤 Speaking practice</h3><p class="muted">Speech recognition doesn't support ${esc(l.name)} yet, so Krypton can't check your pronunciation in it.
      Practise with 🔤 Script, 📚 Words (tap 🔊 to listen and repeat) and 💬 Chat instead.</p></div>`;
    return;
  }
  if (!labWords.length) {
    labLoading(`Getting ${l.name} phrases to practise…`);
    try { labWords = (await api("/api/lang/words", { lang: l.code, topic: "greetings and everyday phrases", level: $("labLevel").value, count: 8 })).words; }
    catch (err) { return labErr(err); }
  }
  const pool = labWords.flatMap(w => [{ t: w.word, tr: w.translit, m: w.meaning }, ...(w.example ? [{ t: w.example, tr: w.example_translit, m: w.example_meaning }] : [])]);
  const next = () => {
    const p = pool[Math.floor(Math.random() * pool.length)];
    $("labOut").innerHTML = `<div class="card stepcard" style="text-align:center"><div class="muted">Say this in ${esc(l.name)}</div>
      <div class="bigchar native" style="font-size:44px">${esc(p.t)}</div><div class="tr" style="color:var(--accent)"><i>${esc(p.tr || "")}</i></div>
      <div class="muted">${esc(p.m || "")}</div>
      <div class="row" style="justify-content:center;margin-top:14px"><button class="btn-ghost" id="spListen">🔊 Listen first</button>
        <button class="btn-primary mic" id="spMic">🎤 Say it</button><button class="btn-ghost" id="spNext">Next →</button></div><div id="spOut"></div></div>`;
    $("spListen").onclick = () => say(p.t, l);
    $("spNext").onclick = next;
    $("spMic").onclick = async () => {
      try {
        const heard = await recordSpeech($("spMic"), l.code);
        const r = await api("/api/lang/speak", { lang: l.code, target: p.t, heard });
        gainXp(r.xp);
        $("spOut").innerHTML = `<div class="expl" style="margin-top:14px"><b>${r.match}% match</b> — ${esc(r.verdict)}<br>
          <span class="muted">Krypton heard:</span> <span class="native" style="font-size:18px">${esc(r.heard || "(nothing)")}</span></div>`;
      } catch (err) { $("spOut").innerHTML = `<div class="err">${esc(err.message)}</div>`; }
    };
  };
  next();
}

// 💬 Chat: role-play a real situation in the language, with gentle corrections
let labChatMsgs = [];
function labChat() {
  const l = labLang();
  labChatMsgs = [];
  $("labOut").innerHTML = `<div class="card"><div class="row" style="align-items:center">
      <select id="scen" style="flex:1"><option>chatting with a new friend at school</option><option>buying vegetables at a market</option>
        <option>asking for directions to the railway station</option><option>ordering food at a restaurant</option>
        <option>visiting the doctor</option><option>talking to a teacher about homework</option></select>
      <button class="btn-primary" id="chatStart">Start role-play</button></div></div>
    <div class="card chat" style="margin-top:12px;height:460px"><div class="msgs" id="lcMsgs"></div>
      <form class="ask composer" id="lcForm"><input id="lcIn" placeholder="Reply in ${esc(l.name)} (or Latin letters)…" autocomplete="off">
        ${l.voice_in ? `<button type="button" class="btn-ghost mic" id="lcMic">🎤</button>` : ""}<button class="btn-primary">Send</button></form></div>`;
  const turn = async () => {
    const wait = document.createElement("div");
    wait.className = "bubble bot"; wait.textContent = "…"; $("lcMsgs").appendChild(wait);
    try {
      const r = await api("/api/lang/chat", { lang: l.code, scenario: $("scen").value, messages: labChatMsgs });
      labChatMsgs.push({ role: "assistant", content: r.reply });
      wait.innerHTML = `${r.correction ? `<div class="hintbox" style="margin:0 0 8px">✏️ ${esc(r.correction)}</div>` : ""}
        <div class="native">${esc(r.reply)}</div><div style="color:var(--accent)"><i>${esc(r.translit)}</i></div>
        <div class="muted small-note">${esc(r.meaning)}</div><div style="margin-top:6px">${ear(l, r.reply)}</div>`;
      wireSay(wait);
      say(r.reply, l);
    } catch (err) { wait.innerHTML = `<div class="err">${esc(err.message)}</div>`; }
    $("lcMsgs").scrollTop = $("lcMsgs").scrollHeight;
  };
  $("chatStart").onclick = () => { labChatMsgs = []; $("lcMsgs").innerHTML = ""; turn(); };
  $("lcForm").onsubmit = e => {
    e.preventDefault();
    const t = $("lcIn").value.trim();
    if (!t) return;
    $("lcIn").value = "";
    labChatMsgs.push({ role: "user", content: t });
    const me = document.createElement("div");
    me.className = "bubble me";
    me.textContent = t;
    $("lcMsgs").appendChild(me);
    turn();
  };
  if ($("lcMic")) $("lcMic").onclick = async () => {
    try { $("lcIn").value = await recordSpeech($("lcMic"), l.code); } catch (err) { toastMsg("🎤 " + err.message); }
  };
}

// ---------------- school notices (events + behaviour notes) ----------------
async function renderSchool() {
  let f;
  try { f = await api("/api/school/feed"); }
  catch (e) {
    $("schoolEvents").innerHTML = `<p class="muted">School notices switch on after Krypton restarts.</p>`;
    $("schoolReports").innerHTML = "";
    return;
  }
  const when = e => e.days_left === 0 ? "today" : e.days_left === 1 ? "tomorrow" : `in ${e.days_left} days`;
  $("schoolEvents").innerHTML = f.events.length ? f.events.map(e => `<div class="deckrow"><span>
      ${e.remind ? "🔔 " : ""}<b>${esc(e.title)}</b><br><span class="muted small-note">📅 ${esc(e.date)} ${esc(e.time || "")} · ${when(e)}</span>
      ${e.description ? `<br><span class="small-note">${esc(e.description)}</span>` : ""}</span></div>`).join("")
    : `<p class="muted">No upcoming events${f.school_name ? " from " + esc(f.school_name) : ""}.</p>`;
  $("schoolReports").innerHTML = f.reports.length ? f.reports.map(r => `<div class="deckrow"><span>
      <b>${esc(f.categories[r.category] || r.category)}</b> · ${esc(r.area)}<br><span class="small-note">${esc(r.note)}</span>
      <br><span class="muted small-note">${esc(r.date)} · ${esc(r.by)}</span></span></div>`).join("")
    : `<p class="muted">No notes from school yet.</p>`;
}
async function refreshSchoolBadge() {
  try {
    const f = await api("/api/school/feed");
    const n = f.events.filter(e => e.remind).length;
    $("schoolBadge").hidden = !n;
    $("schoolBadge").textContent = n;
  } catch (e) { /* not switched on yet */ }
}
$("staffLink").onclick = e => {
  e.preventDefault();
  window.open(location.protocol.startsWith("http") ? "/school" : chrome.runtime.getURL("school.html"), "_blank");
};

// ---------------- boot ----------------
(async () => {
  await refreshStatus();
  await loadCatalog();
  await loadLangs();
  renderDecks();
  refreshGame();
  refreshSchoolBadge();
  let tab = "explain";
  try { tab = localStorage.getItem("krypton.tab") || tab; } catch (e) { /* storage blocked */ }
  showTab(tab);
  setInterval(refreshStatus, 15000);
})();
