const $ = id => document.getElementById(id);
let STOKEN = null, DATA = null, STATUS = null;
function prepSetup(st) {
  $("fSchool").hidden = !!st.school_name;
  const free = Array.from({ length: 10 }, (_, i) => String(i + 1)).filter(c => !st.taken_classes.includes(c));
  $("sCls").innerHTML = free.map(c => `<option value="${c}">Class ${c}</option>`).join("");
  const left = st.max_admins - st.admins;
  $("slotInfo").textContent = left > 0 ? `${left} of ${st.max_admins} class-admin accounts left. Each teacher manages their own class.` : "All class-admin accounts are taken — log in instead.";
}
try { STOKEN = sessionStorage.getItem("krypton.school"); } catch (e) { /* storage blocked */ }
const sapi = (path, body, method) => api(path, body, { method, headers: STOKEN ? { "X-School-Token": STOKEN } : {} });
const say = (id, text, ok) => { $(id).textContent = text; $(id).className = "msg " + (ok ? "good" : "bad"); };
const setToken = t => { STOKEN = t; try { t ? sessionStorage.setItem("krypton.school", t) : sessionStorage.removeItem("krypton.school"); } catch (e) { /* ignore */ } };
const show = v => ["setup", "login", "board"].forEach(x => { $(x).hidden = x !== v; });

async function start() {
  let st;
  try { st = await api("/school-api/status"); } catch (e) {
    document.body.innerHTML = `<div class="gate"><div class="card err">School features aren't switched on yet — restart Krypton (desktop shortcut "Krypton - Restart"), then reload this page.</div></div>`;
    return;
  }
  STATUS = st;
  prepSetup(st);
  if (!st.setup) return show("setup");
  $("loginTitle").textContent = `${st.school_name} · class admin login`;
  if (STOKEN) { try { await load(); return; } catch (e) { setToken(null); } }
  show("login");
}

$("setupForm").onsubmit = async e => {
  e.preventDefault();
  try {
    setToken((await api("/school-api/setup", { school_name: $("sName").value, name: $("sAdmin").value, cls: $("sCls").value, username: $("sUser").value, password: $("sPw").value })).token);
    await load();
  } catch (err) { say("setupMsg", err.message); }
};
$("loginForm").onsubmit = async e => {
  e.preventDefault();
  try { setToken((await api("/school-api/login", { username: $("lUser").value, password: $("lPw").value })).token); await load(); }
  catch (err) { say("loginMsg", err.message); }
};
$("logout").onclick = () => { setToken(null); show("login"); };
$("toLogin").onclick = () => show("login");
$("toSetup").onclick = () => show("setup");
document.querySelectorAll("#stabs button").forEach(b => b.onclick = () => {
  document.querySelectorAll("#stabs button").forEach(x => x.classList.toggle("active", x === b));
  document.querySelectorAll(".sp").forEach(p => p.classList.toggle("active", p.id === "s-" + b.dataset.s));
});

async function load() {
  DATA = await sapi("/school-api/overview");
  show("board");
  $("schoolName").textContent = `${DATA.school_name.toUpperCase()} · CLASS ${DATA.me.cls}`;
  $("evAud").innerHTML = `<option value="${esc(DATA.me.cls)}">My class (Class ${esc(DATA.me.cls)})</option><option value="all">Whole school</option>`;
  const today = new Date().toLocaleDateString("en-CA");
  if (!$("evDate").value) $("evDate").value = today;
  if (!$("rpDate").value) $("rpDate").value = today;
  $("rpStudent").innerHTML = DATA.students.map(s => `<option value="${esc(s.id)}">${esc(s.name)}${s.cls ? " · Class " + esc(s.cls) : ""}</option>`).join("");
  $("rpCat").innerHTML = Object.entries(DATA.categories).map(([k, v]) => `<option value="${k}">${esc(v)}</option>`).join("");
  $("rpArea").innerHTML = DATA.areas.map(a => `<option>${esc(a)}</option>`).join("");
  const upcoming = DATA.events.filter(e => e.date >= today);
  $("evList").innerHTML = upcoming.length ? upcoming.map(e => `<div class="item"><div><b>${esc(e.title)}</b>
      <div class="muted small-note">📅 ${esc(e.date)} ${esc(e.time || "")} · ${e.audience === "all" ? "Everyone" : "Class " + esc(e.audience)} · reminder ${e.remind_days} day(s) before</div>
      ${e.description ? `<div class="small-note">${esc(e.description)}</div>` : ""}</div>
      <button class="btn-ghost" data-del-ev="${esc(e.id)}">✕</button></div>`).join("") : `<p class="muted">No upcoming events.</p>`;
  $("rpList").innerHTML = DATA.reports.length ? DATA.reports.slice(0, 40).map(r => `<div class="item"><div>
      <b>${esc(r.student_name)}</b> <span class="tag">${esc(DATA.categories[r.category])}</span> <span class="tag">${esc(r.area)}</span>
      <div class="small-note">${esc(r.note)}</div><div class="muted small-note">${esc(r.date)} · by ${esc(r.by)}</div></div>
      <button class="btn-ghost" data-del-rp="${esc(r.id)}">✕</button></div>`).join("") : `<p class="muted">No reports yet.</p>`;
  $("stList").innerHTML = DATA.students.map(s => {
    const mine = DATA.reports.filter(r => r.student_id === s.id);
    const praise = mine.filter(r => r.category === "praise").length;
    return `<div class="item"><div><b>${esc(s.name)}</b> <span class="muted">${s.cls ? "Class " + esc(s.cls) : ""} ${s.username ? "· @" + esc(s.username) : ""}</span></div>
      <div class="row"><span class="tag">🌟 ${praise}</span><span class="tag">⚠️ ${mine.length - praise}</span></div></div>`;
  }).join("");
  document.querySelectorAll("[data-del-ev]").forEach(b => b.onclick = async () => { await sapi("/school-api/events/" + b.dataset.delEv, undefined, "DELETE"); load(); });
  document.querySelectorAll("[data-del-rp]").forEach(b => b.onclick = async () => { await sapi("/school-api/reports/" + b.dataset.delRp, undefined, "DELETE"); load(); });
}

$("evForm").onsubmit = async e => {
  e.preventDefault();
  try {
    await sapi("/school-api/events", { title: $("evTitle").value, date: $("evDate").value, time: $("evTime").value,
      audience: $("evAud").value, remind_days: Number($("evRemind").value), description: $("evDesc").value });
    say("evMsg", "✓ Posted — parents will be reminded.", true);
    $("evTitle").value = ""; $("evDesc").value = "";
    load();
  } catch (err) { say("evMsg", err.message); }
};
$("rpForm").onsubmit = async e => {
  e.preventDefault();
  try {
    await sapi("/school-api/reports", { student_id: $("rpStudent").value, category: $("rpCat").value, area: $("rpArea").value,
      date: $("rpDate").value, note: $("rpNote").value });
    say("rpMsg", "✓ Sent — the parents can see it now.", true);
    $("rpNote").value = "";
    load();
  } catch (err) { say("rpMsg", err.message); }
};

start();
