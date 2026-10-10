// Runs the extension's app page as a normal website for web accounts:
// adds the login token to API calls and stands in for the chrome.* extension APIs.
(() => {
  const token = localStorage.getItem("krypton.token");
  const user = localStorage.getItem("krypton.user") || "me";
  if (!token) { location.replace("/login"); return; }
  window.KRYPTON_API = location.origin;

  const rawFetch = window.fetch.bind(window);
  window.fetch = (url, opts = {}) => {
    const u = String(url);
    const ours = u.startsWith("/api") || u.startsWith(location.origin + "/api");
    if (ours) opts = { ...opts, headers: { ...(opts.headers || {}), "X-User-Token": token } };
    return rawFetch(url, opts).then(r => {
      if (ours && r.status === 401) { localStorage.removeItem("krypton.token"); location.replace("/login"); }
      return r;
    });
  };

  // chrome.storage -> this browser's localStorage, kept separate per account
  const key = "krypton.ext." + user;
  const read = () => { try { return JSON.parse(localStorage.getItem(key) || "{}"); } catch (e) { return {}; } };
  const listeners = [];
  window.chrome = {
    storage: {
      local: {
        get: async keys => { const all = read(), out = {}; (Array.isArray(keys) ? keys : [keys]).forEach(k => { if (k in all) out[k] = all[k]; }); return out; },
        set: async obj => { localStorage.setItem(key, JSON.stringify({ ...read(), ...obj })); listeners.forEach(l => l(obj, "local")); },
      },
      onChanged: { addListener: l => listeners.push(l) },
    },
    runtime: { sendMessage: async () => ({}), getURL: p => p === "app.html" ? "/" : "/ext/" + p, onMessage: { addListener() {} } },
    tabs: { create: ({ url }) => window.open(url, "_blank", "noopener") },
  };

  // Hide what only the laptop owner's extension can do (focus lock, parent board, AI-mode switch).
  const css = document.createElement("style");
  css.textContent = `nav [data-tab="focus"], nav [data-tab="settings"], .side-foot .seg, .side-foot > .label { display: none !important; }
    .webuser { display: flex; justify-content: space-between; align-items: center; gap: 8px; font-size: 13px; }
    .webuser button { padding: 6px 10px; font-size: 12px; }`;
  document.head.appendChild(css);
  document.addEventListener("DOMContentLoaded", () => {
    const foot = document.querySelector(".side-foot");
    if (!foot) return;
    const box = document.createElement("div");
    box.className = "webuser";
    box.innerHTML = `<span>👤 <b></b></span><button class="btn-ghost">Log out</button>`;
    box.querySelector("b").textContent = "@" + user;
    box.querySelector("button").onclick = async () => {
      try { await fetch("/api/auth/logout", { method: "POST" }); } catch (e) { /* ignore */ }
      localStorage.removeItem("krypton.token");
      location.replace("/login");
    };
    foot.prepend(box);
  });
})();
