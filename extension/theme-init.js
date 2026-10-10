// Applies the saved theme before the page paints, and offers a small picker (💎 ☀️ 🌐 🔴).
(() => {
  const THEMES = [["krypton", "💎", "Krypton"], ["light", "☀️", "Light"], ["cyber", "🌐", "Cyber"], ["red", "🔴", "Red"]];
  const apply = t => {
    if (t && t !== "krypton") document.documentElement.setAttribute("data-theme", t);
    else document.documentElement.removeAttribute("data-theme");
  };
  let saved = "krypton";
  try { saved = localStorage.getItem("krypton.theme") || "krypton"; } catch (e) { /* storage blocked */ }
  apply(saved);

  function set(t) {
    apply(t);
    try { localStorage.setItem("krypton.theme", t); } catch (e) { /* ignore */ }
    try { chrome?.storage?.local?.set({ theme: t }); } catch (e) { /* not an extension page */ }  // lock screen follows
    document.querySelectorAll(".themes button").forEach(b => b.classList.toggle("active", b.dataset.theme === t));
  }

  function mount(el) {
    if (!el) return;
    el.classList.add("themes");
    el.innerHTML = THEMES.map(([id, icon, name]) => `<button type="button" data-theme="${id}" title="${name} theme">${icon}</button>`).join("");
    el.querySelectorAll("button").forEach(b => {
      b.classList.toggle("active", b.dataset.theme === (document.documentElement.getAttribute("data-theme") || "krypton"));
      b.onclick = () => set(b.dataset.theme);
    });
  }

  window.KryptonTheme = { set, mount };
  document.addEventListener("DOMContentLoaded", () => document.querySelectorAll("[data-theme-picker]").forEach(mount));
})();
