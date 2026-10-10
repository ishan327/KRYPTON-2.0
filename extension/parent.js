const $ = id => document.getElementById(id);
let TOKEN = null;
try { TOKEN = sessionStorage.getItem("krypton.parent"); } catch (e) { /* storage blocked */ }

const papi = (path, body, method) => api(path, body, { method, headers: TOKEN ? { "X-Parent-Token": TOKEN } : {} });
const say = (id, text, ok) => { $(id).textContent = text; $(id).className = "msg " + (ok ? "good" : "bad"); };

function setToken(t) {
  TOKEN = t;
  try { t ? sessionStorage.setItem("krypton.parent", t) : sessionStorage.removeItem("krypton.parent"); } catch (e) { /* ignore */ }
}

function show(view) {
  ["setup", "login", "board"].forEach(v => { $(v).hidden = v !== view; });
}

// Where parents go online: the server this extension is connected to, else the site it was downloaded from.
async function onlineSite() {
  if (API !== LOCAL_API) return API;
  try { return (await (await fetch(chrome.runtime.getURL("preset.json"))).json()).server || null; } catch (e) { return null; }
}

async function start() {
  const site = await onlineSite();
  if (API !== LOCAL_API && site) { location.replace(site + "/parent-view"); return; }  // connected to an online Krypton
  let st;
  try { st = await api("/api/parent/status"); } catch (e) {
    // No Krypton running on this laptop (e.g. a friend's laptop): send parents to the online Parent view
    if (site) { location.replace(site + "/parent-view"); return; }
    document.body.innerHTML = `<div class="gate"><div class="card">
      <h3>👪 Parent view</h3><p class="muted">This laptop doesn't run its own Krypton. Parents can open the online Parent view on the Krypton website:
      <b>your Krypton link + /parent-view</b> (e.g. krypton-2-0.onrender.com/parent-view), then log in with the child's username and parent PIN.</p>
      <p class="muted small-note">If this is the main Krypton laptop, start it with <b>start_krypton.bat</b> and reload.</p></div></div>`;
    return;
  }
  if (!st.setup) return show("setup");
  if (TOKEN) {
    try { await loadBoard(); return; } catch (e) { setToken(null); }
  }
  show("login");
}

$("setupForm").onsubmit = async e => {
  e.preventDefault();
  if ($("sPw").value !== $("sPw2").value) return say("setupMsg", "Passwords don't match.");
  say("setupMsg", "Checking the Groq key…", true);
  try {
    const r = await api("/api/parent/setup", { groq_api_key: $("sKey").value.trim(), password: $("sPw").value });
    setToken(r.token);
    await loadBoard();
  } catch (err) { say("setupMsg", err.message); }
};

$("loginForm").onsubmit = async e => {
  e.preventDefault();
  try {
    setToken((await api("/api/parent/login", { password: $("lPw").value })).token);
    await loadBoard();
  } catch (err) { say("loginMsg", err.message); }
};
$("forgot").onclick = () => { $("resetBox").hidden = !$("resetBox").hidden; };
$("resetBtn").onclick = async () => {
  try {
    setToken((await api("/api/parent/reset", { groq_api_key: $("rKey").value.trim(), new_password: $("rPw").value })).token);
    await loadBoard();
  } catch (err) { say("loginMsg", err.message); }
};
$("logout").onclick = () => { setToken(null); show("login"); };

document.querySelectorAll("#ptabs button").forEach(b => b.onclick = () => {
  document.querySelectorAll("#ptabs button").forEach(x => x.classList.toggle("active", x === b));
  document.querySelectorAll(".ppanel").forEach(p => p.classList.toggle("active", p.id === "p-" + b.dataset.p));
});

async function loadBoard() {
  const d = await papi("/api/parent/overview");
  show("board");
  const p = d.profile || {};
  $("who").textContent = p.name ? `${p.name} · Class ${p.cls}` : "Student profile not filled yet";
  const todayKey = new Date().toLocaleDateString("en-CA");
  const days = Object.values(d.usage || {});
  const t = (d.usage || {})[todayKey] || { study: 0, distracted: 0, locks: 0, unlocks: 0, sites: {} };
  const recs = d.records || [];
  const avg = recs.length ? Math.round(recs.reduce((s, r) => s + (r.marks / r.max_marks) * 100, 0) / recs.length) : null;
  $("pk").innerHTML = `<div class="kpi"><b>${fmtMin(t.study)}</b><span>studied today</span></div>
    <div class="kpi"><b>${fmtMin(t.distracted)}</b><span>on distracting sites</span></div>
    <div class="kpi"><b>${t.locks || 0}</b><span>locks today</span></div>
    <div class="kpi"><b>${avg === null ? "—" : avg + "%"}</b><span>average exam score</span></div>`;
  const last7 = days.slice(-7);
  const wmax = Math.max(60, ...last7.map(x => Math.max(x.study || 0, x.distracted || 0)));
  $("pweek").innerHTML = last7.map(x => `<div class="wk"><div class="cols">
      <div class="s" style="height:${((x.study || 0) / wmax) * 100}%" title="studied ${fmtMin(x.study)}"></div>
      <div class="x" style="height:${((x.distracted || 0) / wmax) * 100}%" title="distracted ${fmtMin(x.distracted)}"></div></div>
      <div class="lbl">${esc(x.date.slice(5))}</div></div>`).join("") || `<div class="muted">No data yet.</div>`;
  const sites = Object.entries(t.sites || {}).sort((a, b) => b[1] - a[1]).slice(0, 8);
  const smax = Math.max(1, ...sites.map(s => s[1]));
  const blocked = d.rules.blocked_sites;
  $("psites").innerHTML = sites.map(([h, s]) => {
    const bad = blocked.some(b => h === b || h.endsWith("." + b));
    return `<div class="bar"><span class="name">${bad ? "🔴" : "🟢"} ${esc(h)}</span><div class="t"><div class="${bad ? "bad" : ""}" style="width:${(s / smax) * 100}%"></div></div><span>${fmtMin(s)}</span></div>`;
  }).join("") || `<div class="muted">No browsing tracked yet today.</div>`;
  $("pquiz").innerHTML = (d.quizzes || []).slice(0, 10).map(q =>
    `<div>${q.score / q.total >= .8 ? "🔥" : q.score / q.total >= .5 ? "👍" : "📖"} <b>${q.score}/${q.total}</b> — ${esc(q.title)} <span class="muted">(${new Date(q.at).toLocaleDateString()})</span></div>`).join("") || "No quizzes yet.";
  // rules
  const r = d.rules;
  $("rOn").checked = r.focus_enabled;
  $("rLimit").value = r.limit_minutes;
  $("rLock").value = r.lock_minutes;
  $("rQuiz").value = r.allow_quiz_unlock ? "1" : "0";
  $("rPass").value = String(r.unlock_pass);
  $("rSites").value = r.blocked_sites.join("\n");
  // marks
  $("mStudent").textContent = p.name ? `${p.name}'s exam marks` : "Exam marks";
  $("mTable").innerHTML = recs.length ? `<table><tr><th>Exam</th><th>Subject</th><th>Marks</th><th>%</th><th>Date</th></tr>${
    recs.slice().reverse().map(x => `<tr><td>${esc(x.exam)}</td><td>${esc(x.subject)}</td><td>${x.marks}/${x.max_marks}</td>
      <td>${Math.round((x.marks / x.max_marks) * 100)}%</td><td>${esc(x.date || "")}</td></tr>`).join("")}</table>`
    : `<p class="muted">No marks added yet. The student adds them in Krypton → My Marks.</p>`;
  $("keyHint").textContent = d.settings.groq_key_set ? `Current key: ${d.settings.groq_key_hint}` : "No key set.";
  loadWebUsers();
  loadSchool();
}

async function loadSchool() {
  let f;
  try { f = await api("/api/school/feed"); } catch (e) { $("pEvents").innerHTML = `<p class="muted">School features switch on after Krypton restarts.</p>`; return; }
  const when = e => e.days_left === 0 ? "today" : e.days_left === 1 ? "tomorrow" : `in ${e.days_left} days`;
  const soon = f.events.filter(e => e.remind);
  $("pRemind").innerHTML = soon.length ? `<div class="note" style="font-size:14px">🔔 <b>Reminder from ${esc(f.school_name || "school")}:</b> ${soon.map(e => `${esc(e.title)} — ${when(e)} (${esc(e.date)} ${esc(e.time || "")})`).join(" · ")}</div>` : "";
  $("pEvents").innerHTML = f.events.length ? f.events.map(e => `<div class="deckrow"><span>${e.remind ? "🔔 " : ""}<b>${esc(e.title)}</b>
      <br><span class="muted small-note">📅 ${esc(e.date)} ${esc(e.time || "")} · ${when(e)}</span>${e.description ? `<br><span class="small-note">${esc(e.description)}</span>` : ""}</span></div>`).join("")
    : `<p class="muted">No upcoming school events.</p>`;
  $("pReports").innerHTML = f.reports.length ? f.reports.map(r => `<div class="deckrow"><span><b>${esc(f.categories[r.category] || r.category)}</b> · ${esc(r.area)}
      <br><span class="small-note">${esc(r.note)}</span><br><span class="muted small-note">${esc(r.date)} · ${esc(r.by)}</span></span></div>`).join("")
    : `<p class="muted">No behaviour reports from school.</p>`;
}

async function loadWebUsers() {
  const w = await papi("/api/parent/users");
  $("pubUrl").innerHTML = w.public_url ? `Public link: <b>${esc(w.public_url)}</b> · ${w.users.length}/${w.max} accounts`
    : `Not shared right now — start <b>start_krypton_public.bat</b> to get a link. ${w.users.length}/${w.max} accounts.`;
  $("webUsers").innerHTML = w.users.length ? `<table><tr><th>Username</th><th>Name</th><th>Joined</th><th></th></tr>${w.users.map(u =>
    `<tr><td>@${esc(u.username)}</td><td>${esc(u.name)}</td><td>${new Date(u.created * 1000).toLocaleDateString()}</td>
     <td><button class="btn-danger" data-u="${esc(u.id)}">Remove</button></td></tr>`).join("")}</table>` : `<p class="muted">No web accounts yet.</p>`;
  $("webUsers").querySelectorAll("[data-u]").forEach(b => b.onclick = async () => {
    if (!confirm("Remove this account? They will be logged out and can't sign in again.")) return;
    await papi("/api/parent/users/" + b.dataset.u, undefined, "DELETE");
    loadWebUsers();
  });
}

$("rulesForm").onsubmit = async e => {
  e.preventDefault();
  try {
    await papi("/api/parent/rules", {
      focus_enabled: $("rOn").checked, limit_minutes: Number($("rLimit").value), lock_minutes: Number($("rLock").value),
      allow_quiz_unlock: $("rQuiz").value === "1", unlock_pass: Number($("rPass").value),
      blocked_sites: $("rSites").value.split(/\s+/).filter(Boolean),
    });
    await chrome.storage.local.set({ rules: await api("/api/rules") }); // apply immediately
    say("rulesMsg", "✓ Saved — the new rules apply right away.", true);
  } catch (err) { say("rulesMsg", err.message); if (/login/i.test(err.message)) show("login"); }
};

$("pwForm").onsubmit = async e => {
  e.preventDefault();
  try { setToken((await papi("/api/parent/password", { password: $("nPw").value })).token); say("pwMsg", "✓ Password changed.", true); }
  catch (err) { say("pwMsg", err.message); }
};
$("keyForm").onsubmit = async e => {
  e.preventDefault();
  say("keyMsg", "Checking…", true);
  try { await papi("/api/parent/groq-key", { password: $("nKey").value.trim() }); say("keyMsg", "✓ Key updated.", true); $("nKey").value = ""; loadBoard(); }
  catch (err) { say("keyMsg", err.message); }
};

start();
