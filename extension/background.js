// Krypton service worker: screen-time tracking, parent-controlled timed lock, usage sync.
importScripts("shared.js");

const today = () => new Date().toLocaleDateString("en-CA");
const normHost = h => (h || "").replace(/^www\./, "").toLowerCase();
const isBlocked = (host, list) => list.some(d => host === d || host.endsWith("." + d));

let queue = Promise.resolve();
const serial = fn => (queue = queue.then(fn, fn));

async function getRules() {
  const { rules } = await getLocal(["rules"]);
  return { ...DEFAULT_RULES, ...(rules || {}) };
}

async function syncRules() {
  try { await chrome.storage.local.set({ rules: await api("/api/rules") }); } catch (e) { /* offline: keep cached rules */ }
}

async function syncUsage() {
  const { usage, quizHistory } = await getLocal(["usage", "quizHistory"]);
  if (!usage) return;
  try { await api("/api/usage", { day: usage, quizzes: quizHistory || [] }); } catch (e) { /* offline */ }
}

async function state() {
  const s = await getLocal(["usage", "focus", "lastStudy"]);
  let usage = s.usage;
  if (!usage || usage.date !== today()) {
    const history = (await getLocal(["history"])).history || [];
    if (usage) {
      history.push({ date: usage.date, distracted: usage.distracted, study: usage.study, locks: usage.locks });
      await chrome.storage.local.set({ history: history.slice(-30) });
    }
    usage = { date: today(), sites: {}, distracted: 0, study: 0, locks: 0, unlocks: 0 };
  }
  const focus = { counter: 0, locked: false, host: "", lockUntil: 0, ...(s.focus || {}) };
  if (focus.locked && Date.now() >= focus.lockUntil) { // lock time is over
    focus.locked = false;
    focus.counter = 0;
    await chrome.storage.local.set({ focus });
    notifyBackend("unlock", focus.host, 0);
  }
  return { usage, focus, lastStudy: s.lastStudy || null };
}

async function notifyBackend(type, host, minutes) {
  try { await api("/api/focus/event", { type, host, minutes }); } catch (e) { /* backend offline: fine */ }
}

async function lock(host, focus, rules, usedMinutes) {
  focus.locked = true;
  focus.host = host;
  focus.lockUntil = Date.now() + rules.lock_minutes * 60000;
  await chrome.storage.local.set({ focus });
  notifyBackend("lock", host, usedMinutes);
}

async function handle(msg) {
  const rules = await getRules();
  switch (msg.type) {
    case "check": return serial(async () => {
      const host = normHost(msg.host);
      const { focus } = await state();
      const blocked = isBlocked(host, rules.blocked_sites);
      return { blocked, locked: rules.focus_enabled && blocked && focus.locked, lockUntil: focus.lockUntil,
               allowQuiz: rules.allow_quiz_unlock, lockMinutes: rules.lock_minutes };
    });
    case "tick": return serial(async () => {
      const host = normHost(msg.host);
      const sec = Math.min(msg.sec || 5, 10);
      const { usage, focus } = await state();
      usage.sites[host] = (usage.sites[host] || 0) + sec;
      const blocked = isBlocked(host, rules.blocked_sites);
      let justLocked = false;
      if (blocked) {
        usage.distracted += sec;
        if (rules.focus_enabled && !focus.locked) {
          focus.counter += sec;
          if (focus.counter >= rules.limit_minutes * 60) { usage.locks += 1; justLocked = true; }
        }
      }
      await chrome.storage.local.set({ usage, focus });
      if (justLocked) await lock(host, focus, rules, rules.limit_minutes);
      return { blocked, locked: rules.focus_enabled && blocked && focus.locked, lockUntil: focus.lockUntil,
               remaining: Math.max(0, rules.limit_minutes * 60 - focus.counter) };
    });
    case "studyTick": return serial(async () => {
      const { usage } = await state();
      usage.study += Math.min(msg.sec || 5, 10);
      await chrome.storage.local.set({ usage });
      return { ok: true };
    });
    case "lockNow": return serial(async () => {
      const { usage, focus } = await state();
      usage.locks += 1;
      await chrome.storage.local.set({ usage });
      await lock(msg.host || "demo", focus, rules, focus.counter / 60);
      return { ok: true };
    });
    case "challenge": {
      if (!rules.allow_quiz_unlock) return { error: "Quiz unlock is turned off by your parent." };
      const { lastStudy } = await state();
      const ls = lastStudy || {};
      const settings = await getSettings();
      return api("/api/focus/challenge", {
        cls: ls.cls || settings.studyClass || 10, subject: ls.subject || settings.studySubject || null,
        chapters: ls.chapters || [], query: ls.query || "",
      });
    }
    case "verify": {
      const res = await api("/api/focus/verify", { challenge_id: msg.challenge_id, answers: msg.answers });
      if (res.passed) await unlock();
      return res;
    }
    case "unlockOffline": // backend unreachable: content script verified a built-in maths task
      if (rules.allow_quiz_unlock) await unlock();
      return { ok: rules.allow_quiz_unlock };
    case "serverChanged":  // switched between this laptop and an online Krypton: fetch that server's rules now
      await syncRules();
      return { ok: true };
    case "openApp":
      chrome.tabs.create({ url: chrome.runtime.getURL("app.html") });
      return { ok: true };
    default:
      return { error: "unknown message" };
  }
}

async function unlock() {
  return serial(async () => {
    const { usage, focus } = await state();
    focus.locked = false;
    focus.counter = 0;
    focus.lockUntil = 0;
    usage.unlocks += 1;
    await chrome.storage.local.set({ usage, focus });
    notifyBackend("unlock", focus.host, 0);
  });
}

chrome.runtime.onMessage.addListener((msg, sender, sendResponse) => {
  handle(msg).then(sendResponse, e => sendResponse({ error: String(e.message || e) }));
  return true;
});

// School reminders: a desktop notification for each upcoming event (once) and each new behaviour report.
async function syncSchool() {
  let f;
  try { f = await api("/api/school/feed"); } catch (e) { return; }
  const { schoolSeen = [] } = await getLocal(["schoolSeen"]);
  const seen = new Set(schoolSeen);
  const notify = (id, title, message) => {
    if (seen.has(id)) return;
    seen.add(id);
    try { chrome.notifications.create(id, { type: "basic", iconUrl: "icons/icon128.png", title, message, priority: 1 }); } catch (e) { /* ignore */ }
  };
  const when = d => d === 0 ? "today" : d === 1 ? "tomorrow" : `in ${d} days`;
  f.events.filter(e => e.remind).forEach(e =>
    notify("ev-" + e.id, `🔔 ${f.school_name || "School"}: ${e.title}`, `${when(e.days_left)} · ${e.date} ${e.time || ""}\n${e.description || ""}`.trim()));
  f.reports.forEach(r =>
    notify("rp-" + r.id, `📝 ${f.school_name || "School"}: ${(f.categories || {})[r.category] || r.category} (${r.area})`, r.note));
  await chrome.storage.local.set({ schoolSeen: [...seen].slice(-300) });
}
chrome.notifications?.onClicked.addListener(() => chrome.tabs.create({ url: chrome.runtime.getURL("parent.html") }));

chrome.alarms.onAlarm.addListener(a => { if (a.name === "sync") { syncRules(); syncUsage(); syncSchool(); } });

async function init() {
  chrome.alarms.create("sync", { periodInMinutes: 1 });
  await syncRules();
}
chrome.runtime.onStartup.addListener(init);
chrome.runtime.onInstalled.addListener(async ({ reason }) => {
  const { settings } = await getLocal(["settings"]);
  if (!settings) await chrome.storage.local.set({ settings: DEFAULT_SETTINGS });
  await init();
  if (reason === "install") chrome.tabs.create({ url: chrome.runtime.getURL("app.html") });
});
