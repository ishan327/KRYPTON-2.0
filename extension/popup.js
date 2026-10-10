const $ = id => document.getElementById(id);

async function render() {
  const { usage, focus, rules } = await getLocal(["usage", "focus", "rules"]);
  const r = { ...DEFAULT_RULES, ...(rules || {}) };
  const settings = { limitMinutes: r.limit_minutes };
  const today = new Date().toLocaleDateString("en-CA");
  const u = usage && usage.date === today ? usage : { study: 0, distracted: 0 };
  const counter = focus?.counter || 0;
  const frac = Math.min(1, counter / (settings.limitMinutes * 60));
  $("arc").style.strokeDashoffset = String(327 * (1 - frac));
  $("used").textContent = fmtMin(counter);
  $("limit").textContent = `of ${settings.limitMinutes}m scroll`;
  $("study").textContent = fmtMin(u.study);
  $("distracted").textContent = fmtMin(u.distracted);
  const lockedNow = focus?.locked && focus.lockUntil > Date.now();
  $("locked").style.display = lockedNow ? "block" : "none";
  if (lockedNow) $("locked").textContent = `🔒 Locked until ${new Date(focus.lockUntil).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}`;
}

async function loadMode() {
  try {
    const s = await api("/api/settings");
    $("dot").className = "dot on";
    $("conn").textContent = "backend online";
    document.querySelectorAll("#modes button").forEach(b => b.classList.toggle("active", b.dataset.mode === s.mode));
  } catch (e) {
    $("dot").className = "dot off";
    $("conn").textContent = "backend offline";
  }
}

document.querySelectorAll("#modes button").forEach(b => b.onclick = async () => {
  try { await api("/api/settings", { mode: b.dataset.mode }); } catch (e) { /* shown by status */ }
  loadMode();
});
api("/api/public-url").then(p => {
  if (!p.url) return;
  $("share").hidden = false;
  $("shareUrl").textContent = p.url.replace("https://", "");
  $("shareUrl").title = `${p.url} · ${p.accounts}/${p.max} accounts`;
  $("copyLink").onclick = () => { navigator.clipboard.writeText(p.url); $("copyLink").textContent = "Copied"; };
}).catch(() => {});
$("parent").onclick =() => chrome.tabs.create({ url: chrome.runtime.getURL("parent.html") });
$("open").onclick =() => chrome.tabs.create({ url: chrome.runtime.getURL("app.html") });
$("lock").onclick = async () => {
  await chrome.runtime.sendMessage({ type: "lockNow", host: "manual lock" });
  render();
};
chrome.storage.onChanged.addListener(render);
render();
loadMode();
