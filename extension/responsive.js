// Phone layout helpers: top bar with ☰ menu (slides the sidebar out) and a bottom tab bar. Fails quietly.
(() => {
  try {
    const side = document.querySelector(".side");
    const nav = document.getElementById("nav");
    if (!side || !nav) return;
    const top = document.createElement("div");
    top.className = "mtop";
    top.innerHTML = `<button type="button" aria-label="Menu">☰</button><div class="brand"><img src="icons/logo.svg" alt="" width="24" height="24">KRYPTON</div><span style="width:38px"></span>`;
    const shade = document.createElement("div");
    shade.className = "mshade";
    document.body.prepend(shade);
    document.body.prepend(top);
    const close = () => { side.classList.remove("open"); shade.classList.remove("on"); };
    top.querySelector("button").onclick = () => { side.classList.add("open"); shade.classList.add("on"); };
    shade.onclick = close;
    nav.addEventListener("click", e => { if (e.target.closest("button")) close(); });

    // bottom tabs: the five most used sections
    const picks = [["agent", "🤖", "Agent"], ["explain", "🧠", "Explain"], ["quiz", "❓", "Quiz"], ["revise", "🎯", "Revise"], ["progress", "🏆", "Progress"]];
    const bar = document.createElement("div");
    bar.className = "mnav";
    bar.innerHTML = picks.map(([t, i, l]) => `<button type="button" data-m="${t}"><span>${i}</span>${l}</button>`).join("");
    document.body.appendChild(bar);
    bar.querySelectorAll("button").forEach(b => b.onclick = () => {
      nav.querySelector(`[data-tab="${b.dataset.m}"]`)?.click();
      window.scrollTo({ top: 0 });
    });
    const sync = () => {
      const active = nav.querySelector("button.active")?.dataset.tab;
      bar.querySelectorAll("button").forEach(b => b.classList.toggle("active", b.dataset.m === active));
    };
    new MutationObserver(sync).observe(nav, { subtree: true, attributes: true, attributeFilter: ["class"] });
    sync();
  } catch (e) { /* keep the normal layout */ }
})();
