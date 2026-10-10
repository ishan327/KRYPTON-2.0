// Shared by the popup, the app page and the background worker.
// Which Krypton server the extension talks to: this laptop (default) or an online one (e.g. Render),
// chosen in Settings. Pages read a localStorage mirror; the background worker reads chrome.storage.
const LOCAL_API = "http://127.0.0.1:8765";
const pageStore = k => { try { return typeof localStorage !== "undefined" ? localStorage.getItem(k) : null; } catch (e) { return null; } };
const API = globalThis.KRYPTON_API || pageStore("krypton.serverUrl") || LOCAL_API;
const API_TOKEN = globalThis.KRYPTON_API ? null : pageStore("krypton.serverToken");

async function serverConf() {
  if (globalThis.KRYPTON_API) return { url: globalThis.KRYPTON_API, token: null };  // the website itself
  if (typeof localStorage !== "undefined") return { url: API, token: API_TOKEN };
  try {
    const { server } = await chrome.storage.local.get(["server"]);
    if (server?.url) return { url: server.url, token: server.token || null };
  } catch (e) { /* not an extension context */ }
  return { url: LOCAL_API, token: null };
}

// Extension pages connected to an online server: add the account token to direct fetch() calls too
if (typeof window !== "undefined" && API_TOKEN && API !== LOCAL_API) {
  const rawFetch = window.fetch.bind(window);
  window.fetch = (url, opts = {}) => {
    if (String(url).startsWith(API)) opts = { ...opts, headers: { ...(opts.headers || {}), "X-User-Token": API_TOKEN } };
    return rawFetch(url, opts);
  };
}

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
  const conf = await serverConf();
  const headers = { "Content-Type": "application/json", ...(lang ? { "X-Lang": lang } : {}),
                    ...(conf.token ? { "X-User-Token": conf.token } : {}), ...(opts.headers || {}) };
  const res = await fetch(conf.url + path, {
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
