/* =====================================================================
   Stream Deck DIY — interface web v2 (vanilla JS, sans dépendance)
   ===================================================================== */
"use strict";
(function () {

  // ------------------------------------------------------------------ outils
  const $ = (s, r) => (r || document).querySelector(s);
  function h(tag, props) {
    const el = document.createElement(tag);
    const kids = Array.prototype.slice.call(arguments, 2);
    (function add(list) {
      for (const k of list) {
        if (k == null || k === false) continue;
        if (Array.isArray(k)) add(k);
        else el.append(k.nodeType ? k : document.createTextNode(String(k)));
      }
    })(kids);
    if (props) for (const k in props) {
      const v = props[k];
      if (v == null || v === false) continue;
      if (k === "class") el.className = v;
      else if (k === "html") el.innerHTML = v;
      else if (k === "style" && typeof v === "object") Object.assign(el.style, v);
      else if (k.slice(0, 2) === "on") el.addEventListener(k.slice(2), v);
      else if (k === "value" || k === "checked" || k === "selected") el[k] = v;
      else el.setAttribute(k, v === true ? "" : v);
    }
    return el;
  }
  const clone = o => JSON.parse(JSON.stringify(o));
  const pad = n => String(n).padStart(2, "0");
  const ls = {
    get(k) { try { return localStorage.getItem(k); } catch (e) { return null; } },
    set(k, v) { try { localStorage.setItem(k, v); } catch (e) { /* stockage indisponible */ } },
    del(k) { try { localStorage.removeItem(k); } catch (e) { /* idem */ } },
  };
  function svg(name) { return h("span", { class: "svg", html: svgIcon(name) }); }
  function hexToRgb(hex) {
    const n = parseInt((hex || "#000000").slice(1), 16);
    return [(n >> 16) & 255, (n >> 8) & 255, n & 255];
  }
  function hexA(hex, a) { const c = hexToRgb(hex); return `rgba(${c[0]},${c[1]},${c[2]},${a})`; }
  function lum(hex) {
    const c = hexToRgb(hex).map(v => { v /= 255; return v <= .03928 ? v / 12.92 : Math.pow((v + .055) / 1.055, 2.4); });
    return .2126 * c[0] + .7152 * c[1] + .0722 * c[2];
  }
  let toastTimer = null;
  function toast(msg) {
    const t = $("#toast");
    t.textContent = msg; t.classList.add("show");
    clearTimeout(toastTimer); toastTimer = setTimeout(() => t.classList.remove("show"), 2600);
  }

  // ------------------------------------------------------------------ données
  const TYPES = {
    vol_down: { name: "Volume −", icon: "vol-down", group: "Son", label: "Vol -" },
    vol_up: { name: "Volume +", icon: "vol-up", group: "Son", label: "Vol +" },
    mute: { name: "Muet", icon: "mute", group: "Son", label: "Muet" },
    volume: { name: "Curseur de volume", icon: "volume", group: "Son", label: "Volume" },
    play: { name: "Lecture / pause", icon: "play-pause", group: "Multimédia", label: "Lecture" },
    prev: { name: "Piste précédente", icon: "prev", group: "Multimédia", label: "Préc." },
    next: { name: "Piste suivante", icon: "next", group: "Multimédia", label: "Suiv." },
    app: { name: "Application du PC", icon: "grid", group: "Lancer", label: "" },
    file: { name: "Programme, fichier ou dossier", icon: "folder", group: "Lancer", label: "Dossier" },
    url: { name: "Site web", icon: "globe", group: "Lancer", label: "Site" },
    hotkey: { name: "Raccourci clavier", icon: "keyboard", group: "Lancer", label: "Raccourci" },
    clock: { name: "Horloge", icon: "clock", group: "Divers", label: "Horloge" },
    page: { name: "Aller à une page", icon: "arrow-right", group: "Divers", label: "Page" },
    empty: { name: "Case vide", icon: null, group: "Divers", label: "" },
  };
  const PRESETS = {
    nuit: { label: "Nuit", bg1: "#0e1016", bg2: "#1d1638", bgStyle: "gradient", tile: "#262b38", text: "#ffffff", accent: "#00beff", style: "solid" },
    neon: { label: "Néon", bg1: "#07060f", bg2: "#240a3d", bgStyle: "gradient", tile: "#ff2bd6", text: "#ffffff", accent: "#39f3ff", style: "outline" },
    oled: { label: "OLED noir", bg1: "#000000", bg2: "#000000", bgStyle: "solid", tile: "#161616", text: "#ffffff", accent: "#ffffff", style: "solid" },
    ocean: { label: "Océan", bg1: "#03192b", bg2: "#0a4a6b", bgStyle: "gradient", tile: "#1a7fa8", text: "#e8fbff", accent: "#3fe0d0", style: "glass" },
    sunset: { label: "Coucher de soleil", bg1: "#2a0c24", bg2: "#7a3010", bgStyle: "gradient", tile: "#d9573b", text: "#fff5ea", accent: "#ffc04d", style: "glass" },
    foret: { label: "Forêt", bg1: "#09160f", bg2: "#173322", bgStyle: "gradient", tile: "#22543a", text: "#effbe9", accent: "#8be28b", style: "solid" },
    clair: { label: "Clair", bg1: "#eef0f5", bg2: "#dde3ee", bgStyle: "gradient", tile: "#ffffff", text: "#1b1f2a", accent: "#2460c8", style: "solid" },
    verre: { label: "Verre", bg1: "#1b2a6b", bg2: "#7a2f8f", bgStyle: "gradient", tile: "#ffffff", text: "#ffffff", accent: "#ffd166", style: "glass" },
  };
  const PALETTE = ["#2460c8", "#1e88e5", "#00acc1", "#11806a", "#2e7d32", "#7cb342", "#f9a825", "#fb8c00",
    "#e64a19", "#c8323c", "#d81b60", "#8e24aa", "#5b3fb0", "#3949ab", "#546e7a", "#262b38", "#000000", "#ffffff"];
  const EMOJIS = "🎮 🎧 🎵 🎬 📺 💬 📷 🎙️ 🔇 🔊 ⭐ ❤️ 🔥 ⚡ 🚀 ☕ 🍕 🏠 💼 📁 📧 🗓️ 🌐 🛒 🎨 💡 🔒 ⏰ 🌙 ☀️ 👋 ✅ ❌ 🟢 🔴 🎯 🧠 📈 🎤 🕹️".split(" ");
  const FONTS = {
    system: "system-ui, -apple-system, 'Segoe UI', Roboto, sans-serif",
    rounded: "'Nunito', 'Varela Round', 'Quicksand', ui-rounded, 'Arial Rounded MT Bold', system-ui, sans-serif",
    mono: "ui-monospace, 'Roboto Mono', 'Cascadia Mono', Consolas, monospace",
    serif: "Georgia, 'Noto Serif', 'Times New Roman', serif",
    condensed: "'Roboto Condensed', 'Arial Narrow', sans-serif-condensed, sans-serif",
  };
  const JOURS = ["dimanche", "lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi"];
  const MOIS = ["janvier", "février", "mars", "avril", "mai", "juin", "juillet", "août", "septembre", "octobre", "novembre", "décembre"];

  const S = {
    cfg: null, draft: null, editing: false, page: 0, vol: null, muted: false, offline: false,
    pin: ls.get("deck_pin"), apps: null, sel: null, tab: "tiles", editPage: 0,
    lastTouch: Date.now(), bigOpen: false, bigAuto: false, volDrag: false,
  };
  const C = () => (S.editing ? S.draft : S.cfg);

  // ------------------------------------------------------------------ API
  async function api(path, opts) {
    opts = opts || {};
    const headers = { "Content-Type": "application/json" };
    if (opts.auth) headers["X-Pin"] = S.pin || "";
    const r = await fetch(path, {
      method: opts.body ? "POST" : "GET", headers, cache: "no-store",
      body: opts.body ? JSON.stringify(opts.body) : undefined,
    });
    let data = null;
    try { data = await r.json(); } catch (e) { /* pas de JSON */ }
    if (!r.ok) { const err = new Error((data && data.error) || ("Erreur " + r.status)); err.status = r.status; throw err; }
    return data;
  }

  // ------------------------------------------------------------------ thème
  function applyTheme(cfg) {
    const t = cfg.theme, st = document.body.style;
    st.setProperty("--bg1", t.bg1);
    st.setProperty("--bg2", t.bgStyle === "gradient" ? t.bg2 : t.bg1);
    st.setProperty("--tile", t.tile);
    st.setProperty("--text", t.text);
    st.setProperty("--accent", t.accent);
    st.setProperty("--radius", t.radius + "px");
    st.setProperty("--gap", t.gap + "px");
    st.setProperty("--label", t.labelSize + "px");
    st.setProperty("--is", t.iconScale);
    st.setProperty("--font", FONTS[t.font] || FONTS.system);
    document.body.className = ["style-" + t.style, "fx-" + t.pressFx, t.showLabels ? "" : "nolabels",
      t.topBar ? "" : "notop"].join(" ");
    const meta = document.querySelector('meta[name="theme-color"]');
    if (meta) meta.setAttribute("content", t.bg1);
  }

  // ------------------------------------------------------------------ boutons
  function fileHasIcon(p) {
    if (!p) return false;
    if (/^[a-z][a-z0-9+.-]+:/i.test(p)) return false;          // lien « discord:// », « spotify: »
    return /[\\/]/.test(p);                                        // vrai chemin
  }
  function letter(label) {
    return h("span", { class: "letter" }, ((label || "?").trim()[0] || "?").toUpperCase());
  }
  // Icône de secours (si le PC n'a pas pu fournir le logo) : pictogramme deviné d'après le nom
  const GUESS = [
    [/brave|chrome|firefox|edge|opera|vivaldi|navigat|browser|safari/i, "globe"],
    [/discord|teams|slack|whatsapp|telegram|messenger|signal|skype|messages/i, "chat"],
    [/spotify|music|musique|deezer|itunes|vlc|winamp|audio|son/i, "music"],
    [/steam|epic|battle\.?net|game|jeu|xbox|riot|ubisoft|ea app|gog|minecraft|valorant/i, "gamepad"],
    [/visual studio|vs ?code|code|intellij|pycharm|sublime|notepad|terminal|powershell|cmd|git/i, "code"],
    [/obs|stream|twitch|live/i, "live"],
    [/mail|outlook|thunderbird|gmail/i, "mail"],
    [/photo|paint|gimp|photoshop|figma|illustrator|canva|blender/i, "brush"],
    [/explor|fichier|files|finder|dossier|t[ée]l[ée]chargement|download/i, "folder"],
    [/zoom|meet|cam[ée]ra|webcam/i, "video"],
    [/word|excel|powerpoint|office|docs|pdf|acrobat/i, "file"],
    [/calcul/i, "chart"], [/param|settings|r[ée]glage/i, "sliders"], [/calend|agenda/i, "calendar"],
  ];
  function guessIcon(text, fallback) {
    for (const g of GUESS) if (g[0].test(text || "")) return svg(g[1]);
    return svg(fallback || "grid");
  }
  function pcIcon(kind, id, label) {
    const img = h("img", { alt: "", draggable: "false", loading: "lazy",
      src: "/api/icon?kind=" + kind + "&id=" + encodeURIComponent(id) });
    img.addEventListener("error", () => img.replaceWith(guessIcon(label + " " + id)));
    return img;
  }
  function iconNode(t) {
    const ic = t.icon || { kind: "auto" };
    if (ic.kind === "none") return null;
    if (ic.kind === "builtin" && ic.value) return svg(ic.value);
    if (ic.kind === "emoji" && ic.value) return h("span", { class: "emoji" }, ic.value);
    if (ic.kind === "image" && ic.value) return h("img", { src: ic.value, alt: "", draggable: "false" });
    if (t.type === "app" && t.app && t.app.id) return pcIcon("app", t.app.id, t.label || t.app.name);
    if (t.type === "file" && fileHasIcon(t.path)) return pcIcon("file", t.path, t.label);
    if (t.type === "file") return guessIcon((t.label || "") + " " + (t.path || ""), "folder");
    const info = TYPES[t.type];
    return info && info.icon ? svg(info.icon) : null;
  }
  function tileEl(t, cfg, cols) {
    const th = cfg.theme;
    const bg = t.bg || th.tile;
    let fg = t.fg;
    if (!fg) fg = th.style === "solid" && lum(bg) > .55 && lum(th.text) > .5 ? "#14161c" :
      (th.style === "solid" && lum(bg) < .18 && lum(th.text) < .3 ? "#ffffff" : th.text);
    const el = h("div", { class: "tile t-" + t.type + (t.fg ? " customfg" : ""), "data-id": t.id });
    el.style.gridColumn = "span " + Math.min(t.span || 1, cols);
    el.style.setProperty("--tbg", bg);
    el.style.setProperty("--tbga", hexA(bg, .38));
    el.style.setProperty("--tfg", fg);
    el.style.setProperty("--tline", t.bg || (lum(th.tile) < .2 ? th.accent : th.tile));
    if (t.type === "empty") { el.classList.add("empty"); return el; }
    if (t.type === "clock") {
      el.append(h("div", { class: "tclock" }, fmtTime(new Date(), cfg.clock, false)));
      if (t.label) el.append(h("div", { class: "tlabel" }, t.label));
      return el;
    }
    if (t.type === "volume") {
      el.append(h("div", { class: "ticon" }, iconNode(t)), h("div", { class: "vtrack" }, h("div", { class: "vfill" })),
        h("div", { class: "vpct" }, ""));
      return el;
    }
    const icon = iconNode(t);
    if (icon) el.append(h("div", { class: "ticon" }, icon)); else el.classList.add("labelonly");
    if (t.label) el.append(h("div", { class: "tlabel" }, t.label));
    if (t.type === "mute" && S.muted) el.classList.add("on");
    return el;
  }
  function gridRows(page) {
    let rows = 1, col = 0;
    for (const t of page.tiles) {
      const span = Math.min(t.span || 1, page.cols);
      if (col + span > page.cols) { rows++; col = 0; }
      col += span;
    }
    return rows;
  }
  function layoutGrid(grid, page, cfg) {
    const rows = gridRows(page);
    grid.style.gridTemplateColumns = "repeat(" + page.cols + ", minmax(0, 1fr))";
    grid.style.gridTemplateRows = "repeat(" + rows + ", minmax(0, 1fr))";
    const r = grid.getBoundingClientRect();
    const gap = cfg.theme.gap;
    const th = (r.height - gap * (rows - 1)) / rows;
    const tw = (r.width - gap * (page.cols - 1)) / page.cols;
    grid.style.setProperty("--th", Math.max(24, Math.min(th, tw * 1.05)) + "px");
  }
  function findTile(id, cfg) {
    for (const p of (cfg || S.cfg).pages) for (const t of p.tiles) if (t.id === id) return t;
    return null;
  }

  // ------------------------------------------------------------------ deck
  function renderDeck(anim) {
    const cfg = S.cfg;
    if (!cfg) return;
    if (!S.editing) applyTheme(cfg);
    if (S.page >= cfg.pages.length) S.page = 0;
    const page = cfg.pages[S.page];
    $("#pageTitle").textContent = cfg.pages.length > 1 ? page.name : "";
    const grid = $("#grid");
    grid.innerHTML = "";
    grid.className = anim ? "slide-" + anim : "";
    for (const t of page.tiles) grid.append(tileEl(t, cfg, page.cols));
    layoutGrid(grid, page, cfg);
    const dots = $("#dots");
    dots.innerHTML = "";
    if (cfg.pages.length > 1) cfg.pages.forEach((p, i) =>
      dots.append(h("button", { class: i === S.page ? "on" : "", "aria-label": p.name, onclick: () => goPage(i) })));
    updateLive();
  }
  function goPage(i) {
    const n = S.cfg.pages.length;
    const target = Math.max(0, Math.min(n - 1, i));
    if (target === S.page) return;
    const dir = target > S.page ? "l" : "r";
    S.page = target;
    renderDeck(dir);
  }

  function fire(t) {
    if (S.cfg.theme.haptic && navigator.vibrate) { try { navigator.vibrate(12); } catch (e) { /* ignoré */ } }
    if (t.type === "mute") { S.muted = !S.muted; updateLive(); }
    api("/api/press", { body: { id: t.id } }).catch(() => toast("PC injoignable — le script tourne-t-il ?"));
  }
  function activate(t) {
    if (t.type === "page") return goPage(t.target || 0);
    if (t.type === "clock") return openBig(false);
    fire(t);
  }

  let volTimer = null, volPending = null;
  function sliderMove(e, el) {
    const r = el.querySelector(".vtrack").getBoundingClientRect();
    const v = Math.round(Math.max(0, Math.min(1, (e.clientX - r.left) / r.width)) * 100);
    S.vol = v; S.volDrag = true; updateLive();
    volPending = v;
    if (!volTimer) volTimer = setTimeout(function send() {
      volTimer = null;
      if (volPending == null) return;
      const lvl = volPending; volPending = null;
      api("/api/volume", { body: { level: lvl } }).catch(() => { /* ignoré */ });
    }, 90);
  }

  function bindDeck() {
    const grid = $("#grid");
    let s = null;
    grid.addEventListener("pointerdown", e => {
      wake();
      const el = e.target.closest(".tile");
      s = { x: e.clientX, y: e.clientY, el, moved: false, t: null };
      if (!el) return;
      const t = findTile(el.dataset.id);
      if (!t || t.type === "empty") return;
      s.t = t;
      el.classList.add("pressed");
      if (t.type === "volume") {
        s.slider = true;
        try { el.setPointerCapture(e.pointerId); } catch (err) { /* ignoré */ }
        sliderMove(e, el);
        return;
      }
      if (t.type === "vol_up" || t.type === "vol_down") {
        fire(t); s.fired = true;
        const cur = s;
        cur.repeat = setTimeout(function rep() { fire(t); cur.repeat = setTimeout(rep, 130); }, 450);
      }
    });
    grid.addEventListener("pointermove", e => {
      if (!s) return;
      if (s.slider) return sliderMove(e, s.el);
      if (Math.abs(e.clientX - s.x) > 14 || Math.abs(e.clientY - s.y) > 14) {
        s.moved = true; clearTimeout(s.repeat);
        if (s.el) s.el.classList.remove("pressed");
      }
    });
    const end = (e, cancel) => {
      if (!s) return;
      const cur = s; s = null;
      clearTimeout(cur.repeat);
      if (cur.el) cur.el.classList.remove("pressed");
      if (cur.slider) { setTimeout(() => { S.volDrag = false; }, 600); return; }
      const dx = e.clientX - cur.x, dy = e.clientY - cur.y;
      if (cur.moved && Math.abs(dx) > 60 && Math.abs(dx) > Math.abs(dy)) return goPage(S.page + (dx < 0 ? 1 : -1));
      if (cancel || cur.moved || !cur.t || cur.fired) return;
      activate(cur.t);
    };
    grid.addEventListener("pointerup", e => end(e, false));
    grid.addEventListener("pointercancel", e => end(e, true));
  }

  // ------------------------------------------------------------------ heure & état
  function fmtTime(d, clk, withSec) {
    let hh = d.getHours();
    let suffix = "";
    if (!clk.h24) { suffix = hh < 12 ? " AM" : " PM"; hh = hh % 12 || 12; }
    return (clk.h24 ? pad(hh) : hh) + ":" + pad(d.getMinutes()) + (withSec ? ":" + pad(d.getSeconds()) : "") + suffix;
  }
  function fmtDate(d) {
    const txt = JOURS[d.getDay()] + " " + d.getDate() + " " + MOIS[d.getMonth()];
    return txt.charAt(0).toUpperCase() + txt.slice(1);
  }

  function updateLive() {
    const cfg = S.cfg;
    if (!cfg) return;
    const now = new Date();
    $("#clockBtn").textContent = fmtTime(now, cfg.clock, false);
    const vol = $("#vol");
    vol.classList.toggle("muted", !!S.muted);
    $("#volFill").style.width = (S.vol == null ? 0 : S.vol) + "%";
    $("#volPct").textContent = S.offline ? "hors ligne" : (S.vol == null ? "" : (S.muted ? "muet" : S.vol + "%"));
    document.querySelectorAll("#grid .tclock").forEach(el => { el.textContent = fmtTime(now, cfg.clock, false); });
    document.querySelectorAll("#grid .t-mute").forEach(el => el.classList.toggle("on", !!S.muted));
    document.querySelectorAll("#grid .t-volume").forEach(el => {
      el.querySelector(".vfill").style.width = (S.vol || 0) + "%";
      el.querySelector(".vpct").textContent = S.vol == null ? "–" : (S.muted ? "muet" : S.vol + "%");
    });
    if (S.bigOpen) {
      const c = cfg.clock;
      $("#bigTime").textContent = fmtTime(now, c, false);
      $("#bigSec").textContent = c.seconds ? pad(now.getSeconds()) : "";
      $("#bigDate").textContent = c.date ? fmtDate(now) : "";
    }
  }
  function openBig(auto) {
    const c = S.cfg.clock, big = $("#bigclock");
    S.bigOpen = true; S.bigAuto = auto;
    big.hidden = false;
    big.classList.toggle("dim", !!(auto && c.dim));
    $("#bigTime").style.color = c.color;
    $("#bigSec").style.color = c.accent;
    $("#bigDate").style.color = c.color;
    updateLive();
  }
  function closeBig() { S.bigOpen = false; $("#bigclock").hidden = true; }
  function wake() { S.lastTouch = Date.now(); }

  async function poll() {
    try {
      const st = await api("/api/state");
      S.offline = false;
      if (!S.volDrag) S.vol = st.volume;
      S.muted = st.muted;
      if (S.cfg && st.rev !== S.cfg.rev && !S.editing) {
        S.cfg = await api("/api/config");
        renderDeck();
      }
    } catch (e) { S.offline = true; }
    updateLive();
  }

  function tick() {
    updateLive();
    const c = S.cfg && S.cfg.clock;
    if (c && c.screensaver > 0 && !S.bigOpen && !S.editing &&
        Date.now() - S.lastTouch > c.screensaver * 60000) openBig(true);
  }

  function maybeFullscreen() {
    if (!S.cfg || !S.cfg.theme.fullscreenOnTap || S.editing) return;
    const d = document.documentElement;
    if (document.fullscreenElement || !d.requestFullscreen) return;
    d.requestFullscreen().catch(() => { /* refusé par le navigateur */ });
  }

  // =================================================================== PARAMÈTRES
  function pinDialog() {
    return new Promise(resolve => {
      const input = h("input", { type: "tel", inputmode: "numeric", maxlength: "8", autocomplete: "off", placeholder: "••••" });
      const msg = h("div", { class: "hint" }, "Le code s'affiche dans la console du PC au lancement du script.");
      const box = h("div", { class: "pinbox" },
        h("h2", {}, "Code PIN"), msg, input,
        h("div", { class: "row", style: { justifyContent: "center" } },
          h("button", { class: "btn", onclick: () => close(false) }, "Annuler"),
          h("button", { class: "btn primary", onclick: submit }, "Valider")));
      const modal = h("div", { class: "modal" }, box);
      input.addEventListener("keydown", e => { if (e.key === "Enter") submit(); });
      $("#modalRoot").append(modal);
      setTimeout(() => input.focus(), 50);
      function close(ok) { modal.remove(); resolve(ok); }
      async function submit() {
        try {
          const r = await api("/api/auth", { body: { pin: input.value.trim() } });
          if (r.ok) { S.pin = input.value.trim(); ls.set("deck_pin", S.pin); return close(true); }
          msg.textContent = "Code incorrect (5 essais par minute).";
        } catch (e) { msg.textContent = "PC injoignable."; }
        box.classList.remove("shake"); void box.offsetWidth; box.classList.add("shake");
        input.select();
      }
    });
  }
  async function ensurePin() {
    if (S.pin) {
      try {
        const r = await api("/api/auth", { body: { pin: S.pin } });
        if (r.ok) return true;
      } catch (e) { toast("PC injoignable"); return false; }
      S.pin = null; ls.del("deck_pin");
    }
    return pinDialog();
  }

  async function openSettings() {
    if (!(await ensurePin())) return;
    if (document.fullscreenElement && document.exitFullscreen) document.exitFullscreen().catch(() => { /* ignoré */ });
    S.draft = clone(S.cfg);
    S.editing = true; S.editPage = S.page; S.sel = null; S.tab = "tiles";
    renderSettings();
  }
  function closeSettings() {
    S.editing = false; S.draft = null;
    $("#modalRoot").innerHTML = "";
    applyTheme(S.cfg);
    renderDeck();
  }
  function cancelSettings() {
    const changed = JSON.stringify(S.draft) !== JSON.stringify(S.cfg);
    if (changed && !window.confirm("Abandonner les modifications ?")) return;
    closeSettings();
  }
  async function saveSettings() {
    try {
      await api("/api/config", { auth: true, body: { config: S.draft } });
      S.cfg = await api("/api/config");
      closeSettings();
      toast("Enregistré ✓");
    } catch (e) {
      if (e.status === 403) { S.pin = null; ls.del("deck_pin"); toast("Code PIN refusé"); }
      else toast("Erreur : " + e.message);
    }
  }

  const D = () => S.draft;
  const curPage = () => D().pages[Math.min(S.editPage, D().pages.length - 1)];
  const selTile = () => (S.sel ? curPage().tiles.find(t => t.id === S.sel) : null);
  function newId() { return "t" + Math.random().toString(16).slice(2, 10); }

  function renderSettings() {
    const prevBody = $(".sheet-body");
    const scroll = prevBody ? prevBody.scrollTop : 0;
    const prevEditor = $("#editorCol");
    const edScroll = prevEditor ? prevEditor.scrollTop : 0;
    applyTheme(D());
    const tabs = [["tiles", "Boutons"], ["pages", "Pages"], ["look", "Apparence"], ["clock", "Horloge"], ["backup", "Sauvegarde"]];
    const body = h("div", { class: "sheet-body" },
      S.tab === "tiles" ? tabTiles() : S.tab === "pages" ? tabPages() : S.tab === "look" ? tabLook() :
        S.tab === "clock" ? tabClock() : tabBackup());
    const sheet = h("div", { class: "sheet" },
      h("div", { class: "sheet-head" },
        h("b", { class: "title" }, "Paramètres"),
        h("div", { class: "tabs" }, tabs.map(([k, l]) =>
          h("button", { class: S.tab === k ? "on" : "", onclick: () => { S.tab = k; renderSettings(); } }, l))),
        h("button", { class: "btn ghost", onclick: cancelSettings }, "Annuler"),
        h("button", { class: "btn primary", onclick: saveSettings }, svg("check"), "Enregistrer")),
      body);
    const root = $("#modalRoot");
    root.innerHTML = "";
    root.append(h("div", { class: "modal" }, sheet));
    requestAnimationFrame(() => {
      layoutPreview();
      const b = $(".sheet-body"); if (b) b.scrollTop = scroll;
      const ed = $("#editorCol"); if (ed) ed.scrollTop = edScroll;
    });
  }

  // ---------- aperçu ----------
  function previewBox(tall) {
    return h("div", { class: "preview" + (tall ? " tall" : ""), id: "preview" }, h("div", { class: "pgrid", id: "pgrid" }));
  }
  function layoutPreview() {
    const grid = $("#pgrid");
    if (!grid) return;
    const page = curPage();
    grid.innerHTML = "";
    for (const t of page.tiles) {
      const el = tileEl(t, D(), page.cols);
      if (t.id === S.sel) el.classList.add("sel");
      if (t.type === "empty") { el.classList.add("ghost"); el.style.border = "2px dashed rgba(127,127,127,.5)"; }
      if (t.type === "volume") {
        el.querySelector(".vfill").style.width = (S.vol || 40) + "%";
        el.querySelector(".vpct").textContent = (S.vol == null ? 40 : S.vol) + "%";
      }
      el.addEventListener("click", () => {
        if (S.tab !== "tiles") { S.tab = "tiles"; }
        S.sel = t.id; renderSettings();
      });
      grid.append(el);
    }
    layoutGrid(grid, page, D());
  }
  const refreshPreview = () => requestAnimationFrame(layoutPreview);

  // ---------- onglet Boutons ----------
  function pageChips() {
    return h("div", { class: "pagechips" }, D().pages.map((p, i) =>
      h("button", { class: i === S.editPage ? "on" : "", onclick: () => { S.editPage = i; S.sel = null; renderSettings(); } }, p.name)));
  }
  function tabTiles() {
    const page = curPage();
    const left = h("div", {},
      pageChips(),
      previewBox(true),
      h("div", { class: "row", style: { marginTop: "10px" } },
        h("button", { class: "btn", onclick: addTile }, svg("plus"), "Ajouter un bouton"),
        h("span", { class: "hint" }, page.tiles.length + " bouton(s) · " + page.cols + " colonnes")));
    const t = selTile();
    const right = h("div", { id: "editorCol" }, t ? tileEditor(t) :
      h("div", { class: "card empty-hint" }, svg("pencil"), "Touche un bouton de l'aperçu pour le modifier,",
        "ou ajoute-en un nouveau."));
    return h("div", { class: "split" }, left, right);
  }
  function addTile() {
    const t = { id: newId(), type: "app", label: "", span: 1, bg: "", fg: "", icon: { kind: "auto", value: "" },
      app: { id: "", name: "" } };
    curPage().tiles.push(t);
    S.sel = t.id;
    renderSettings();
    openAppPicker(t);
  }

  function field(label, control, hint) {
    return h("div", { class: "field" }, h("label", {}, label), control, hint ? h("div", { class: "hint" }, hint) : null);
  }
  function seg(options, value, onpick) {
    return h("div", { class: "seg" }, options.map(([v, l]) =>
      h("button", { class: String(v) === String(value) ? "on" : "", onclick: () => onpick(v) }, l)));
  }
  function colorPicker(value, onpick, allowTheme, themeLabel) {
    const chips = [];
    if (allowTheme) chips.push(h("button", { class: "swatch theme" + (!value ? " on" : ""), title: themeLabel || "Thème", onclick: () => onpick("") }));
    for (const c of PALETTE) chips.push(h("button", { class: "swatch" + (value === c ? " on" : ""), style: { background: c }, onclick: () => onpick(c) }));
    const custom = h("input", { type: "color", value: value || "#888888" });
    custom.addEventListener("input", () => onpick(custom.value, true));
    custom.addEventListener("change", () => onpick(custom.value));
    return h("div", { class: "chips" }, chips, custom);
  }

  function tileEditor(t) {
    const page = curPage();
    const idx = page.tiles.indexOf(t);
    const rerender = () => renderSettings();
    const groups = {};
    for (const k in TYPES) (groups[TYPES[k].group] = groups[TYPES[k].group] || []).push(k);
    const typeSel = h("select", { onchange: e => changeType(t, e.target.value) },
      Object.keys(groups).map(g => h("optgroup", { label: g }, groups[g].map(k => h("option", { value: k }, TYPES[k].name)))));
    typeSel.value = t.type;

    const specific = [];
    if (t.type === "app") {
      const cur = t.app && t.app.id
        ? h("button", { class: "appcur", onclick: () => openAppPicker(t) }, pcIcon("app", t.app.id, t.app.name), h("b", {}, t.app.name), h("span", { class: "spacer" }), "Changer")
        : h("button", { class: "btn primary", onclick: () => openAppPicker(t) }, svg("search"), "Choisir une application");
      specific.push(field("Application", cur, "Liste des applications installées sur ton PC (menu Démarrer)."));
    } else if (t.type === "file") {
      const inp = h("input", { type: "text", value: t.path || "", placeholder: "C:\\Program Files\\OBS Studio\\bin\\64bit\\obs64.exe" });
      inp.addEventListener("input", () => { t.path = inp.value; });
      inp.addEventListener("change", rerender);
      specific.push(field("Chemin ou commande", inp,
        "Programme (.exe), raccourci (.lnk), dossier, fichier, commande (« code ») ou lien d'appli (« steam:// »)."));
    } else if (t.type === "url") {
      const inp = h("input", { type: "url", value: t.url || "", placeholder: "https://www.youtube.com" });
      inp.addEventListener("input", () => { t.url = inp.value; });
      specific.push(field("Adresse du site", inp, "S'ouvre dans le navigateur par défaut du PC."));
    } else if (t.type === "hotkey") {
      const inp = h("input", { type: "text", value: t.keys || "", placeholder: "ctrl+shift+m" });
      inp.addEventListener("input", () => { t.keys = inp.value; });
      const ex = ["ctrl+c", "ctrl+v", "ctrl+z", "alt+tab", "win+d", "win+shift+s", "ctrl+shift+m", "ctrl+shift+esc", "win+e", "f5"];
      specific.push(field("Combinaison de touches", h("div", {}, inp,
        h("div", { class: "chips", style: { marginTop: "8px" } }, ex.map(k =>
          h("button", { class: "chip", onclick: () => { t.keys = k; if (!t.label || t.label === TYPES.hotkey.label) t.label = k; rerender(); } }, k)))),
        "Touches : ctrl, shift, alt, win, a–z, 0–9, f1–f24, esc, enter, tab, space, delete, home, end, up, down, left, right, printscreen…"));
    } else if (t.type === "page") {
      const sel = h("select", { onchange: e => { t.target = +e.target.value; refreshPreview(); } },
        D().pages.map((p, i) => h("option", { value: i }, (i + 1) + ". " + p.name)));
      sel.value = String(t.target || 0);
      specific.push(field("Page de destination", sel));
    }

    const label = h("input", { type: "text", value: t.label || "", maxlength: "40", placeholder: "Texte sous l'icône" });
    label.addEventListener("input", () => { t.label = label.value; refreshPreview(); });

    return h("div", {},
      h("div", { class: "card" }, h("h3", {}, "Action"), field("Type de bouton", typeSel), specific, field("Libellé", label)),
      t.type === "empty" || t.type === "clock" ? null : h("div", { class: "card" }, h("h3", {}, "Icône"), iconEditor(t)),
      t.type === "empty" ? null : h("div", { class: "card" }, h("h3", {}, "Couleurs"),
        field("Fond", colorPicker(t.bg, (c, live) => { t.bg = c; live ? refreshPreview() : rerender(); }, true, "Couleur du thème")),
        field("Texte et icône", colorPicker(t.fg, (c, live) => { t.fg = c; live ? refreshPreview() : rerender(); }, true, "Automatique"))),
      h("div", { class: "card" }, h("h3", {}, "Position et taille"),
        field("Largeur (en cases)", seg(Array.from({ length: page.cols }, (_, i) => [i + 1, String(i + 1)]), t.span || 1,
          v => { t.span = v; rerender(); })),
        h("div", { class: "row" },
          h("button", { class: "btn sm", onclick: () => move(t, -1), disabled: idx === 0 }, svg("arrow-left"), "Avant"),
          h("button", { class: "btn sm", onclick: () => move(t, 1), disabled: idx === page.tiles.length - 1 }, "Après", svg("arrow-right")),
          h("button", { class: "btn sm", onclick: () => duplicate(t) }, svg("copy"), "Dupliquer"),
          D().pages.length > 1 ? moveToPageSelect(t) : null,
          h("button", { class: "btn sm danger", onclick: () => removeTile(t) }, svg("trash"), "Supprimer"))));
  }
  function changeType(t, type) {
    const oldDefault = (TYPES[t.type] || {}).label;
    const oldApp = t.app && t.app.name;
    t.type = type;
    delete t.app; delete t.path; delete t.url; delete t.keys; delete t.target;
    if (type === "app") t.app = { id: "", name: "" };
    if (type === "file") t.path = "";
    if (type === "url") t.url = "";
    if (type === "hotkey") t.keys = "";
    if (type === "page") t.target = 0;
    if (type === "volume") t.span = curPage().cols;
    if (!t.label || t.label === oldDefault || t.label === oldApp) t.label = TYPES[type].label;
    t.icon = { kind: "auto", value: "" };
    renderSettings();
    if (type === "app") openAppPicker(t);
  }
  function move(t, d) {
    const arr = curPage().tiles, i = arr.indexOf(t), j = i + d;
    if (j < 0 || j >= arr.length) return;
    arr[i] = arr[j]; arr[j] = t;
    renderSettings();
  }
  function duplicate(t) {
    const arr = curPage().tiles, c = clone(t);
    c.id = newId();
    arr.splice(arr.indexOf(t) + 1, 0, c);
    S.sel = c.id;
    renderSettings();
  }
  function removeTile(t) {
    const arr = curPage().tiles;
    arr.splice(arr.indexOf(t), 1);
    S.sel = null;
    renderSettings();
  }
  function moveToPageSelect(t) {
    const sel = h("select", { style: { width: "auto" } }, h("option", { value: "" }, "Déplacer vers…"),
      D().pages.map((p, i) => i === S.editPage ? null : h("option", { value: i }, p.name)));
    sel.addEventListener("change", () => {
      if (sel.value === "") return;
      const arr = curPage().tiles;
      arr.splice(arr.indexOf(t), 1);
      D().pages[+sel.value].tiles.push(t);
      S.editPage = +sel.value;
      renderSettings();
    });
    return sel;
  }

  function iconEditor(t) {
    const ic = t.icon = t.icon || { kind: "auto", value: "" };
    const set = (kind, value) => { t.icon = { kind, value: value || "" }; renderSettings(); };
    const autoLabel = t.type === "app" || (t.type === "file" && fileHasIcon(t.path)) ? "Icône de l'appli" : "Automatique";
    const parts = [seg([["auto", autoLabel], ["builtin", "Bibliothèque"], ["emoji", "Emoji"], ["image", "Image"], ["none", "Aucune"]],
      ic.kind, k => set(k, k === ic.kind ? ic.value : (k === "builtin" ? (TYPES[t.type].icon || "star") : k === "emoji" ? "🎮" : "")))];
    if (ic.kind === "builtin") {
      parts.push(h("div", { class: "iconpick", style: { marginTop: "10px" } }, ICON_NAMES.map(n =>
        h("button", { class: ic.value === n ? "on" : "", title: n, onclick: () => set("builtin", n) }, svg(n)))));
    } else if (ic.kind === "emoji") {
      const inp = h("input", { type: "text", value: ic.value, maxlength: "16", style: { marginTop: "10px", fontSize: "22px" } });
      inp.addEventListener("input", () => { t.icon.value = inp.value; refreshPreview(); });
      parts.push(inp, h("div", { class: "iconpick emojipick", style: { marginTop: "8px" } }, EMOJIS.map(em =>
        h("button", { class: ic.value === em ? "on" : "", onclick: () => set("emoji", em) }, em))),
        h("div", { class: "hint" }, "Tu peux aussi coller n'importe quel emoji du clavier du téléphone."));
    } else if (ic.kind === "image") {
      const file = h("input", { type: "file", accept: "image/*", style: { display: "none" } });
      file.addEventListener("change", async () => {
        if (!file.files[0]) return;
        try { set("image", await fileToIcon(file.files[0])); } catch (e) { toast("Image illisible"); }
      });
      parts.push(h("div", { class: "row", style: { marginTop: "10px" } },
        ic.value ? h("img", { src: ic.value, style: { width: "56px", height: "56px", objectFit: "contain", borderRadius: "10px", background: "#0e1016" } }) : null,
        h("button", { class: "btn", onclick: () => file.click() }, svg("image"), ic.value ? "Changer d'image" : "Choisir une image"), file),
        h("div", { class: "hint" }, "Photo ou logo depuis le téléphone ; redimensionné automatiquement (PNG 128 px)."));
    }
    return h("div", {}, parts);
  }
  function fileToIcon(f) {
    return new Promise((resolve, reject) => {
      const fr = new FileReader();
      fr.onerror = reject;
      fr.onload = () => {
        const img = new Image();
        img.onerror = reject;
        img.onload = () => {
          const size = 128, c = document.createElement("canvas");
          c.width = c.height = size;
          const r = Math.min(size / img.width, size / img.height), w = img.width * r, hh = img.height * r;
          c.getContext("2d").drawImage(img, (size - w) / 2, (size - hh) / 2, w, hh);
          resolve(c.toDataURL("image/png"));
        };
        img.src = fr.result;
      };
      fr.readAsDataURL(f);
    });
  }

  // ---------- sélecteur d'application ----------
  async function openAppPicker(t) {
    const list = h("div", { class: "applist" }, h("div", { class: "empty-hint" }, "Chargement de la liste des applications…"));
    const search = h("input", { type: "search", placeholder: "Rechercher (chrome, discord, steam…)" });
    const modal = h("div", { class: "modal" }, h("div", { class: "sheet small" },
      h("div", { class: "sheet-head" }, h("b", {}, "Choisir une application"), h("span", { class: "spacer" }),
        h("button", { class: "btn sm", onclick: () => load(true) }, "Actualiser"),
        h("button", { class: "btn sm", onclick: () => modal.remove() }, svg("x"))),
      h("div", { style: { padding: "10px 12px 4px" } }, search),
      h("div", { class: "sheet-body" }, list)));
    $("#modalRoot").append(modal);
    search.addEventListener("input", draw);
    async function load(refresh) {
      list.innerHTML = "";
      list.append(h("div", { class: "empty-hint" }, refresh ? "Actualisation…" : "Chargement…"));
      try {
        S.apps = (!refresh && S.apps) || await api("/api/apps" + (refresh ? "?refresh=1" : ""), { auth: true });
      } catch (e) {
        list.innerHTML = ""; list.append(h("div", { class: "empty-hint" }, "Impossible de lire la liste : " + e.message));
        return;
      }
      draw();
    }
    function draw() {
      const q = search.value.trim().toLowerCase();
      const items = (S.apps || []).filter(a => !q || a.name.toLowerCase().indexOf(q) >= 0);
      list.innerHTML = "";
      if (!items.length) list.append(h("div", { class: "empty-hint" }, q ? "Aucun résultat." : "Aucune application trouvée."));
      for (const a of items.slice(0, 400)) {
        list.append(h("button", { class: "approw" + (t.app && t.app.id === a.id ? " on" : ""), onclick: () => pick(a) },
          pcIcon("app", a.id, a.name), h("span", {}, a.name)));
      }
    }
    function pick(a) {
      const old = t.app && t.app.name;
      if (t.type !== "app") { t.type = "app"; delete t.path; delete t.url; delete t.keys; delete t.target; }
      t.app = { id: a.id, name: a.name };
      if (!t.label || t.label === old || t.label === TYPES.app.label) t.label = a.name.slice(0, 40);
      if (t.icon.kind === "none" || t.icon.kind === "auto") t.icon = { kind: "auto", value: "" };
      modal.remove();
      renderSettings();
    }
    load(false);
    setTimeout(() => search.focus(), 80);
  }

  // ---------- onglet Pages ----------
  function tabPages() {
    const pages = D().pages;
    return h("div", { style: { maxWidth: "720px" } },
      h("div", { class: "card" }, h("h3", {}, "Pages"),
        pages.map((p, i) => {
          const name = h("input", { type: "text", value: p.name, maxlength: "30" });
          name.addEventListener("input", () => { p.name = name.value; });
          return h("div", { class: "card", style: { background: "#12141b" } },
            h("div", { class: "row" }, h("b", {}, "Page " + (i + 1)), h("span", { class: "spacer" }),
              h("button", { class: "btn sm", disabled: i === 0, onclick: () => swapPage(i, i - 1) }, "▲"),
              h("button", { class: "btn sm", disabled: i === pages.length - 1, onclick: () => swapPage(i, i + 1) }, "▼"),
              h("button", { class: "btn sm danger", disabled: pages.length === 1, onclick: () => delPage(i) }, svg("trash"))),
            field("Nom", name),
            field("Colonnes", seg([[2, "2"], [3, "3"], [4, "4"], [5, "5"], [6, "6"], [7, "7"], [8, "8"]], p.cols,
              v => { p.cols = v; p.tiles.forEach(t => { if (t.span > v) t.span = v; }); renderSettings(); })),
            h("div", { class: "hint" }, p.tiles.length + " bouton(s). Balaye l'écran à gauche/droite pour changer de page."));
        }),
        h("button", { class: "btn primary", onclick: addPage }, svg("plus"), "Ajouter une page")));
  }
  function addPage() {
    D().pages.push({ name: "Page " + (D().pages.length + 1), cols: 4, tiles: [] });
    S.editPage = D().pages.length - 1;
    renderSettings();
  }
  function swapPage(i, j) {
    const p = D().pages, tmp = p[i];
    p[i] = p[j]; p[j] = tmp;
    for (const pg of p) for (const t of pg.tiles) if (t.type === "page") {
      if (t.target === i) t.target = j; else if (t.target === j) t.target = i;
    }
    renderSettings();
  }
  function delPage(i) {
    const p = D().pages;
    if (p[i].tiles.length && !window.confirm("Supprimer « " + p[i].name + " » et ses " + p[i].tiles.length + " boutons ?")) return;
    p.splice(i, 1);
    for (const pg of p) for (const t of pg.tiles) if (t.type === "page" && t.target >= i) t.target = Math.max(0, t.target - 1);
    S.editPage = 0;
    renderSettings();
  }

  // ---------- onglet Apparence ----------
  function rangeField(label, obj, key, min, max, step, unit, live) {
    const out = h("output", {}, fmtNum(obj[key], unit));
    const r = h("input", { type: "range", min, max, step, value: obj[key] });
    r.addEventListener("input", () => {
      obj[key] = step < 1 ? parseFloat(r.value) : parseInt(r.value, 10);
      out.textContent = fmtNum(obj[key], unit);
      if (live) live();
    });
    return field(label, h("div", { class: "rangerow" }, r, out));
  }
  function fmtNum(v, unit) { return unit === "%" ? Math.round(v * 100) + "%" : v + (unit || ""); }
  function toggle(label, obj, key, after) {
    const c = h("input", { type: "checkbox", checked: !!obj[key] });
    c.addEventListener("change", () => { obj[key] = c.checked; if (after) after(); });
    return h("label", { class: "toggle" }, h("span", {}, label), c);
  }
  function colorRow(label, obj, key) {
    const c = h("input", { type: "color", value: obj[key] });
    c.addEventListener("input", () => { obj[key] = c.value; obj.preset = "perso"; applyTheme(D()); refreshPreview(); });
    return h("div", { class: "toggle" }, h("span", {}, label), c);
  }
  function tabLook() {
    const th = D().theme;
    const live = () => { applyTheme(D()); refreshPreview(); };
    return h("div", { class: "split" },
      h("div", {}, pageChips(), previewBox(true), h("div", { class: "hint" }, "Aperçu en direct.")),
      h("div", { id: "editorCol" },
        h("div", { class: "card" }, h("h3", {}, "Thèmes"),
          h("div", { class: "presets" }, Object.keys(PRESETS).map(k => {
            const p = PRESETS[k];
            return h("button", {
              class: "preset" + (th.preset === k ? " on" : ""),
              style: { background: "linear-gradient(150deg," + p.bg1 + "," + (p.bgStyle === "gradient" ? p.bg2 : p.bg1) + ")", color: p.text },
              onclick: () => { Object.assign(th, p); delete th.label; th.preset = k; renderSettings(); },
            }, p.label, h("span", { class: "dots" }, h("i", { style: { background: p.tile } }), h("i", { style: { background: p.accent } })));
          }))),
        h("div", { class: "card" }, h("h3", {}, "Couleurs"),
          colorRow("Fond", th, "bg1"),
          (() => {
            const c = h("input", { type: "checkbox", checked: th.bgStyle === "gradient" });
            c.addEventListener("change", () => { th.bgStyle = c.checked ? "gradient" : "solid"; live(); });
            return h("label", { class: "toggle" }, h("span", {}, "Fond en dégradé"), c);
          })(),
          colorRow("Deuxième couleur du dégradé", th, "bg2"),
          colorRow("Boutons", th, "tile"),
          colorRow("Texte", th, "text"),
          colorRow("Accent (sélection, volume, muet)", th, "accent"),
          h("button", { class: "btn sm", style: { marginTop: "8px" }, onclick: () => {
            D().pages.forEach(p => p.tiles.forEach(t => { t.bg = ""; t.fg = ""; }));
            renderSettings(); toast("Couleurs des boutons réinitialisées");
          } }, "Retirer les couleurs perso des boutons")),
        h("div", { class: "card" }, h("h3", {}, "Boutons"),
          field("Style", seg([["solid", "Plein"], ["outline", "Contour"], ["glass", "Verre"]], th.style, v => { th.style = v; renderSettings(); })),
          field("Effet à l'appui", seg([["scale", "Enfoncement"], ["glow", "Lueur"], ["none", "Aucun"]], th.pressFx, v => { th.pressFx = v; renderSettings(); })),
          rangeField("Arrondi des coins", th, "radius", 0, 40, 1, " px", live),
          rangeField("Espacement", th, "gap", 0, 30, 1, " px", live),
          rangeField("Taille des icônes", th, "iconScale", .15, .8, .01, "%", live),
          rangeField("Taille du texte", th, "labelSize", 8, 32, 1, " px", live),
          field("Police", seg([["system", "Standard"], ["rounded", "Arrondie"], ["condensed", "Étroite"], ["mono", "Mono"], ["serif", "Serif"]],
            th.font, v => { th.font = v; renderSettings(); })),
          toggle("Afficher les libellés", th, "showLabels", live)),
        h("div", { class: "card" }, h("h3", {}, "Comportement"),
          toggle("Barre du haut (heure, volume)", th, "topBar", live),
          toggle("Plein écran au premier toucher", th, "fullscreenOnTap"),
          toggle("Vibration à l'appui", th, "haptic"),
          rangeField("Pas du volume (+/−)", D(), "volume_step", 1, 20, 1, " %"))));
  }

  // ---------- onglet Horloge ----------
  function tabClock() {
    const c = D().clock;
    const now = new Date();
    const prev = h("div", { class: "clockprev" },
      h("div", { class: "t", style: { color: c.color } }, fmtTime(now, c, false)),
      c.seconds ? h("div", { class: "s", style: { color: c.accent } }, pad(now.getSeconds())) : null,
      c.date ? h("div", { class: "d", style: { color: c.color } }, fmtDate(now)) : null);
    const rr = () => renderSettings();
    const color = (label, key) => {
      const inp = h("input", { type: "color", value: c[key] });
      inp.addEventListener("change", () => { c[key] = inp.value; rr(); });
      return h("div", { class: "toggle" }, h("span", {}, label), inp);
    };
    return h("div", { style: { maxWidth: "640px" } }, prev,
      h("div", { class: "card" }, h("h3", {}, "Affichage"),
        toggle("Format 24 h", c, "h24", rr), toggle("Secondes", c, "seconds", rr), toggle("Date", c, "date", rr),
        color("Couleur de l'heure", "color"), color("Couleur des secondes", "accent")),
      h("div", { class: "card" }, h("h3", {}, "Écran de veille"),
        field("Afficher l'horloge en grand après", seg([[0, "Jamais"], [1, "1 min"], [2, "2 min"], [5, "5 min"], [10, "10 min"], [30, "30 min"]],
          c.screensaver, v => { c.screensaver = v; rr(); })),
        toggle("Assombrir l'horloge en veille (protège l'écran)", c, "dim")));
  }

  // ---------- onglet Sauvegarde ----------
  function tabBackup() {
    const file = h("input", { type: "file", accept: "application/json,.json", style: { display: "none" } });
    file.addEventListener("change", () => {
      const f = file.files[0];
      if (!f) return;
      const fr = new FileReader();
      fr.onload = () => {
        try {
          const data = JSON.parse(fr.result);
          if (!data || !Array.isArray(data.pages) || !data.theme) throw new Error("format");
          delete data.pin; delete data.rev;
          S.draft = Object.assign(clone(S.cfg), data);
          S.editPage = 0; S.sel = null;
          toast("Configuration importée — touche Enregistrer pour l'appliquer");
          renderSettings();
        } catch (e) { toast("Fichier invalide"); }
      };
      fr.readAsText(f);
    });
    const exportCfg = () => {
      const data = clone(D()); delete data.rev;
      const blob = new Blob([JSON.stringify(data, null, 2)], { type: "application/json" });
      const a = h("a", { href: URL.createObjectURL(blob), download: "streamdeck-config.json" });
      document.body.append(a); a.click(); a.remove();
    };
    return h("div", { style: { maxWidth: "640px" } },
      h("div", { class: "card" }, h("h3", {}, "Exporter / importer"),
        h("div", { class: "row" },
          h("button", { class: "btn", onclick: exportCfg }, svg("download"), "Exporter la configuration"),
          h("button", { class: "btn", onclick: () => file.click() }, svg("upload"), "Importer un fichier"), file),
        h("div", { class: "hint" }, "Pratique pour garder plusieurs profils (travail, jeu, stream) ou partager ta config.")),
      h("div", { class: "card" }, h("h3", {}, "Réinitialiser"),
        h("button", { class: "btn danger", onclick: () => {
          Object.assign(D().theme, PRESETS.nuit, { radius: 18, gap: 10, iconScale: .42, labelSize: 15, showLabels: true,
            font: "system", pressFx: "scale" });
          delete D().theme.label; D().theme.preset = "nuit";
          renderSettings(); toast("Apparence réinitialisée (pense à Enregistrer)");
        } }, "Remettre l'apparence par défaut")),
      h("div", { class: "card" }, h("h3", {}, "Infos"),
        h("div", { class: "hint" }, "Le code PIN se change dans le fichier config.json sur le PC (clé « pin »), puis relance du script."),
        h("div", { class: "hint" }, "Les réglages sont enregistrés sur le PC : tous les écrans connectés se mettent à jour.")));
  }

  // =================================================================== démarrage
  async function boot() {
    $("#gearBtn").append(svg("gear"));
    $("#fabGear").append(svg("gear"));
    $("#gearBtn").addEventListener("click", openSettings);
    $("#fabGear").addEventListener("click", openSettings);
    $("#clockBtn").addEventListener("click", () => openBig(false));
    $("#bigclock").addEventListener("pointerdown", e => { e.preventDefault(); wake(); closeBig(); });
    document.addEventListener("pointerdown", wake, true);
    document.addEventListener("pointerup", maybeFullscreen);
    document.addEventListener("keydown", e => { if (e.key === "Escape" && S.editing) cancelSettings(); });
    window.addEventListener("resize", () => { renderDeck(); if (S.editing) refreshPreview(); });
    bindDeck();
    for (;;) {
      try { S.cfg = await api("/api/config"); break; }
      catch (e) { toast("Connexion au PC…"); await new Promise(r => setTimeout(r, 2000)); }
    }
    document.body.classList.remove("loading");
    renderDeck();
    poll();
    setInterval(poll, 1000);
    setInterval(tick, 1000);
  }
  boot();
})();
