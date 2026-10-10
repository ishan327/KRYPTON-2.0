// Shared by the popup and the app page.
const API = globalThis.KRYPTON_API || "http://127.0.0.1:8765";

const DEFAULT_SETTINGS = { studyClass: 10, studySubject: "" };

// Lock rules are set by the parent on the backend; these apply until the first sync.
const DEFAULT_RULES = {
  focus_enabled: true, limit_minutes: 15, lock_minutes: 30, allow_quiz_unlock: true, unlock_pass: 2,
  blocked_sites: ["youtube.com", "instagram.com", "facebook.com", "x.com", "twitter.com", "reddit.com",
                  "snapchat.com", "tiktok.com", "netflix.com", "hotstar.com", "primevideo.com", "pinterest.com"],
};

async function api(path, body, opts = {}) {
  let lang = "";
  try { lang = localStorage.getItem("krypton.lang") || ""; } catch (e) { /* storage blocked */ }
  const headers = { "Content-Type": "application/json", ...(lang ? { "X-Lang": lang } : {}), ...(opts.headers || {}) };
  const res = await fetch(API + path, {
    method: opts.method || (body === undefined ? "GET" : "POST"), headers,
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  if (!res.ok) {
    let msg = res.statusText;
    try { msg = (await res.json()).detail || msg; } catch (e) { /* keep statusText */ }
    throw new Error(msg);
  }
  return res.json();
}

async function getLocal(keys) { return chrome.storage.local.get(keys); }

async function getSettings() {
  const { settings } = await getLocal(["settings"]);
  return { ...DEFAULT_SETTINGS, ...(settings || {}) };
}

async function saveSettings(patch) {
  const s = await getSettings();
  await chrome.storage.local.set({ settings: { ...s, ...patch } });
}

function esc(s) {
  return String(s ?? "").replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}

function fmtMin(sec) {
  const m = Math.round((sec || 0) / 60);
  return m >= 60 ? `${Math.floor(m / 60)}h ${m % 60}m` : `${m}m`;
}

const ENGINE_LABEL = {
  groq: "⚡ Groq cloud",
  local: "🖥 Local GPU",
  offline: "📘 Offline engine",
};
