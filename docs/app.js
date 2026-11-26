/* ছবিঘর — hash-routed static catalogue. Data: films.json (built by scripts/build_data.py). */
(function () {
  "use strict";
  const $ = (s, el = document) => el.querySelector(s);
  const view = $("#view");
  let FILMS = [], BY_ID = {};

  const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const key = (s) => s.normalize("NFKD").replace(/[̀-ͯ]/g, "").toLowerCase();
  const enc = encodeURIComponent;
  const decade = (y) => `${Math.floor(y / 10) * 10}s`;
  const SECTION = { indian: "Indian classics", world: "World classics" };

  /* ---------- theme ---------- */
  $("#theme").addEventListener("click", () => {
    const t = document.documentElement.dataset.theme === "dark" ? "light" : "dark";
    document.documentElement.dataset.theme = t;
    try { localStorage.setItem("chhobighor.theme", t); } catch (e) { /* ignore */ }
  });

  /* ---------- pieces ---------- */
  function thumb(src) {
    return src.kind === "yt" ? `https://i.ytimg.com/vi/${src.id}/hqdefault.jpg` : `https://archive.org/services/img/${src.id}`;
  }
  // A film uploaded in parts plays from the chosen part on through the rest, as one YouTube queue.
  function embed(src, part = 0) {
    if (src.kind !== "yt") return `https://archive.org/embed/${src.id}?autoplay=1`;
    const id = src.parts ? src.parts[part] : src.id;
    const rest = src.parts ? src.parts.slice(part + 1) : [];
    return `https://www.youtube-nocookie.com/embed/${id}?autoplay=1&rel=0&modestbranding=1&cc_load_policy=1&cc_lang_pref=en&hl=en${rest.length ? `&playlist=${rest.join(",")}` : ""}`;
  }
  function watchUrl(src) {
    return src.kind === "yt" ? `https://www.youtube.com/watch?v=${src.id}` : `https://archive.org/details/${src.id}`;
  }
  function screen(f, src, extra = "") {
    return `<div class="screen ${extra}" data-title="${esc(f.t)}"><img src="${thumb(src)}" alt="" loading="lazy" onerror="this.replaceWith(Object.assign(document.createElement('div'),{className:'noimg',textContent:this.parentNode.dataset.title}))"></div>`;
  }
  function people(list, kind) {
    return list.map((n) => `<a href="#/${kind}/${enc(n)}">${esc(n)}</a>`).join("");
  }
  function card(f) {
    const mins = f.src[0].mins;
    return `<a class="card" href="#/film/${f.id}">
      <div style="position:relative">${screen(f, f.src[0])}${mins ? `<span class="tag">${Math.floor(mins / 60)}h ${String(mins % 60).padStart(2, "0")}m</span>` : ""}</div>
      <h3>${esc(f.t)}</h3><p>${f.y} · ${esc(f.d.join(" & "))} · ${esc(f.l)}</p></a>`;
  }
  const grid = (list) => list.length ? `<div class="grid">${list.map(card).join("")}</div>` : `<p class="empty"><b>No films here yet</b>Try another filter.</p>`;
  function counts(list, fn) {
    const m = new Map();
    list.forEach((f) => [].concat(fn(f)).forEach((k) => m.set(k, (m.get(k) || 0) + 1)));
    return m;
  }
  function chipRow(label, m, current, href, order) {
    const keys = [...m.keys()].sort(order || ((a, b) => m.get(b) - m.get(a) || a.localeCompare(b)));
    if (keys.length < 2) return "";
    return `<div class="row"><span class="lab">${label}</span><div class="chips">
      <a class="chip" href="${href(null)}" aria-pressed="${current == null}">All</a>
      ${keys.map((k) => `<a class="chip" href="${href(k)}" aria-pressed="${current === k}">${esc(k)}<b>${m.get(k)}</b></a>`).join("")}</div></div>`;
  }
  function setNav(name) {
    document.querySelectorAll(".nav a").forEach((a) => (a.dataset.nav === name ? a.setAttribute("aria-current", "page") : a.removeAttribute("aria-current")));
  }
  function render(html, nav, title) {
    view.innerHTML = html;
    setNav(nav);
    document.title = title ? `${title} · ছবিঘর Chhobighor` : "ছবিঘর · Chhobighor: classic films, free to watch";
    window.scrollTo(0, 0);
    view.focus({ preventScroll: true });
  }

  /* ---------- the player: a thumbnail until clicked, then the source's own embed ---------- */
  view.addEventListener("click", (e) => {
    const part = e.target.closest("[data-part]");
    if (part) return play($(".film > .screen"), +part.dataset.part);
    const go = e.target.closest(".go");
    if (!go) return;
    play(go.closest(".screen"), 0);
  });
  function play(scr, part) {
    const f = BY_ID[scr.dataset.film], src = f.src[+scr.dataset.src || 0];
    scr.classList.add("playing");
    scr.innerHTML = `<iframe src="${embed(src, part)}" title="${esc(f.t)}" allow="autoplay; encrypted-media; picture-in-picture; fullscreen" allowfullscreen referrerpolicy="strict-origin-when-cross-origin"></iframe>`;
  }
  function partsRow(f, i = 0) {
    const p = f.src[i].parts;
    return p ? `<div class="parts"><span class="lab">On YouTube in ${p.length} parts, played one after another</span><div class="chips">${
      p.map((_, n) => `<button class="chip" type="button" data-part="${n}">Part ${n + 1}</button>`).join("")}</div></div>` : "";
  }
  function player(f, i = 0, cls = "big") {
    const src = f.src[i];
    return `<div class="screen ${cls}" data-film="${f.id}" data-src="${i}" data-title="${esc(f.t)}">
      <img src="${thumb(src)}" alt="" onerror="this.replaceWith(Object.assign(document.createElement('div'),{className:'noimg',textContent:this.parentNode.dataset.title}))">
      <button class="go" type="button" aria-label="Play ${esc(f.t)}"><span><svg aria-hidden="true"><use href="#play"/></svg></span></button></div>`;
  }

  /* ---------- pages ---------- */
  // Today's feature and shelves change daily but are the same for everyone that day.
  const DAY = (() => { const d = new Date(); return `${d.getFullYear()}-${d.getMonth()}-${d.getDate()}`; })();
  const hash = (s) => { let h = 2166136261; for (const c of s) h = Math.imul(h ^ c.charCodeAt(0), 16777619); return h >>> 0; };
  const daily = (list) => [...list].sort((a, b) => hash(DAY + a.id) - hash(DAY + b.id));
  function home() {
    const f = daily(FILMS)[0];
    const shelf = (s) => {
      const list = FILMS.filter((x) => x.s === s);
      if (!list.length) return "";
      const pick = daily(list).slice(0, 8);
      return `<section><div class="head"><h2>${SECTION[s]}</h2><a href="#/${s}">All ${list.length} →</a></div>${grid(pick)}</section>`;
    };
    const dec = counts(FILMS, (x) => decade(x.y)), lang = counts(FILMS, (x) => x.l), dir = counts(FILMS, (x) => x.d), gen = counts(FILMS, (x) => x.g);
    const topDirs = [...dir.keys()].sort((a, b) => dir.get(b) - dir.get(a) || a.localeCompare(b)).slice(0, 16);
    render(`
      <div class="hero">${player(f)}
        <div class="txt"><span class="lab">Today's feature</span><h1>${esc(f.t)}</h1>
          <p class="meta">${f.y} · ${esc(f.l)} · directed by ${people(f.d, "director")}</p>
          ${f.cast.length ? `<p class="meta">With ${esc(f.cast.slice(0, 3).join(", "))}</p>` : ""}
          <div class="acts"><a class="pill" href="#/film/${f.id}">About this film</a></div></div></div>
      ${shelf("indian")}${shelf("world")}
      <section><div class="head"><h2>By genre</h2></div><div class="chips">${[...gen.keys()].sort((a, b) => gen.get(b) - gen.get(a) || a.localeCompare(b)).map((k) => `<a class="chip" href="#/genre/${enc(k)}">${esc(k)}<b>${gen.get(k)}</b></a>`).join("")}</div></section>
      <section class="split">
        <div><div class="head"><h2>By decade</h2></div><div class="chips">${[...dec.keys()].sort().map((k) => `<a class="chip" href="#/decade/${k}">${k}<b>${dec.get(k)}</b></a>`).join("")}</div>
          <div class="head" style="margin-top:28px"><h2>By language</h2></div><div class="chips">${[...lang.keys()].sort((a, b) => lang.get(b) - lang.get(a)).map((k) => `<a class="chip" href="#/language/${enc(k)}">${esc(k)}<b>${lang.get(k)}</b></a>`).join("")}</div></div>
        <div><div class="head"><h2>Directors</h2><a href="#/directors">All →</a></div><div class="chips">${topDirs.map((k) => `<a class="chip" href="#/director/${enc(k)}">${esc(k)}<b>${dir.get(k)}</b></a>`).join("")}</div></div>
      </section>`, "home");
  }

  // A filterable list: base set + optional decade/language filters from the query string.
  function listing(base, { title, sub, nav, path, q }) {
    const dec = q.get("decade"), lang = q.get("language"), gen = q.get("genre"), sort = q.get("sort") || "year";
    const href = (k, v) => { const p = new URLSearchParams(q); v == null ? p.delete(k) : p.set(k, v); const s = p.toString(); return `#${path}${s ? "?" + s : ""}`; };
    let list = base.filter((f) => (!dec || decade(f.y) === dec) && (!lang || f.l === lang) && (!gen || f.g.includes(gen)));
    list.sort(sort === "title" ? (a, b) => a.t.localeCompare(b.t) : (a, b) => a.y - b.y || a.t.localeCompare(b.t));
    const filters = [
      path.startsWith("/decade") ? "" : chipRow("Decade", counts(base, (f) => decade(f.y)), dec, (k) => href("decade", k), (a, b) => a.localeCompare(b)),
      path.startsWith("/language") ? "" : chipRow("Language", counts(base, (f) => f.l), lang, (k) => href("language", k)),
      path.startsWith("/genre") ? "" : chipRow("Genre", counts(base, (f) => f.g), gen, (k) => href("genre", k)),
    ].join("");
    render(`<div class="pagehead"><span class="lab">${list.length} film${list.length === 1 ? "" : "s"}</span><h1>${esc(title)}</h1>${sub ? `<p>${sub}</p>` : ""}</div>
      <div class="filters">${filters}<div class="row"><span class="lab">Order</span><div class="chips">
        <a class="chip" href="${href("sort", null)}" aria-pressed="${sort === "year"}">By year</a><a class="chip" href="${href("sort", "title")}" aria-pressed="${sort === "title"}">A–Z</a></div></div></div>
      ${grid(list)}`, nav, title);
  }

  function peopleIndex(kind) {
    const m = counts(FILMS, (f) => (kind === "director" ? f.d : f.cast));
    const names = [...m.keys()].sort((a, b) => a.localeCompare(b));
    const title = kind === "director" ? "Directors" : "Actors";
    const draw = (filter) => {
      const k = key(filter || "");
      const shown = names.filter((n) => key(n).includes(k));
      let out = "", letter = "";
      shown.forEach((n) => {
        const L = key(n)[0].toUpperCase();
        if (L !== letter) { letter = L; out += `<h3>${L}</h3>`; }
        out += `<a href="#/${kind}/${enc(n)}">${esc(n)}<span>${m.get(n)}</span></a>`;
      });
      $(".people").innerHTML = out || `<p class="hint">No one by that name.</p>`;
    };
    render(`<div class="pagehead"><span class="lab">${names.length} names</span><h1>${title}</h1></div>
      <input class="filterbox" type="search" placeholder="Filter by name" aria-label="Filter ${title.toLowerCase()} by name"><div class="people"></div>`, kind === "director" ? "directors" : "actors", title);
    draw("");
    $(".filterbox").addEventListener("input", (e) => draw(e.target.value));
  }

  function film(id) {
    const f = BY_ID[id];
    if (!f) return render(`<p class="empty"><b>Film not found</b><a href="#/">Back to the hall</a></p>`, "", "Not found");
    const more = (label, list, href) => list.length ? `<section><div class="head"><h2>${label}</h2>${href ? `<a href="${href}">All →</a>` : ""}</div>${grid(list.slice(0, 4))}</section>` : "";
    const byDir = FILMS.filter((x) => x.id !== f.id && x.d.some((d) => f.d.includes(d)));
    const sameDec = FILMS.filter((x) => x.id !== f.id && x.s === f.s && decade(x.y) === decade(f.y) && !byDir.includes(x));
    const credit = (s) => s.kind === "yt"
      ? `Shared on YouTube by <b>${esc(s.by)}</b>, the film's rights holder or licensed distributor.`
      : `In the public domain, from the <b>Internet Archive</b>'s film collection.`;
    render(`<div class="film">${player(f)}${partsRow(f)}
      <div class="info"><div>
        <span class="lab">${SECTION[f.s]}</span><h1>${esc(f.t)}</h1>${f.a && f.a !== f.t ? `<p class="alt">${esc(f.a)}</p>` : ""}
        <p class="meta"><a href="#/decade/${decade(f.y)}">${f.y}</a> · <a href="#/language/${enc(f.l)}">${esc(f.l)}</a> · ${esc(f.c)}${f.src[0].mins ? ` · ${f.src[0].mins} min` : ""}</p>
        <dl><dt>Director${f.d.length > 1 ? "s" : ""}</dt><dd>${people(f.d, "director")}</dd>
        ${f.g.length ? `<dt>Genre</dt><dd>${people(f.g, "genre")}</dd>` : ""}
        ${f.cast.length ? `<dt>Cast</dt><dd>${people(f.cast, "actor")}</dd>` : ""}</dl></div>
        <aside class="credit"><span class="lab">Where it plays from</span>${f.src.map((s) => `<p>${credit(s)}</p>`).join("")}
          <div class="srcs">${f.src.map((s, i) => `${f.src.length > 1 ? `<button class="pill" type="button" data-switch="${i}">Play from ${s.kind === "yt" ? "YouTube" : "Archive"}</button>` : ""}<a class="pill" href="${watchUrl(s)}" target="_blank" rel="noopener">Open on ${s.kind === "yt" ? "YouTube" : "archive.org"} ↗</a>`).join("")}</div></aside>
      </div>
      ${more(`More by ${f.d.join(" & ")}`, byDir, f.d.length === 1 ? `#/director/${enc(f.d[0])}` : "")}
      ${more(`Also from the ${decade(f.y)}`, sameDec, `#/decade/${decade(f.y)}`)}</div>`, f.s, f.t);
    view.querySelectorAll("[data-switch]").forEach((b) => b.addEventListener("click", () => {
      $(".film > .screen").outerHTML = player(f, +b.dataset.switch);
      const row = $(".film > .parts");
      if (row) row.outerHTML = partsRow(f, +b.dataset.switch);
      else $(".film > .screen").insertAdjacentHTML("afterend", partsRow(f, +b.dataset.switch));
    }));
  }

  function search(qs) {
    const k = key(qs.trim());
    const list = k ? FILMS.filter((f) => key([f.t, f.a, ...f.d, ...f.g, ...f.cast].join(" | ")).includes(k)) : [];
    render(`<div class="pagehead"><span class="lab">${list.length} found</span><h1>“${esc(qs)}”</h1></div>${k ? grid(list) : ""}`, "", `Search: ${qs}`);
  }

  function about() {
    const n = { indian: FILMS.filter((f) => f.s === "indian").length, world: FILMS.filter((f) => f.s === "world").length };
    render(`<div class="pagehead"><span class="lab">About</span><h1>A picture house of the classics</h1></div>
      <div class="about"><p><span class="bn">ছবিঘর</span> (Chhobighor, “the picture house”) gathers ${n.indian} Indian and ${n.world} world film classics that anyone can watch, free and legally.</p>
      <h2>Where the films come from</h2>
      <ul><li><b>Rights holders' own YouTube channels</b>: the studios and licensed distributors who own the films and put them up for free viewing.</li>
      <li><b>The Internet Archive</b>: films in its public-domain feature, silent and noir collections.</li></ul>
      <p>Uploads by anyone else are never listed, even when they are easy to find. Each film page names the channel or collection it plays from, and the film plays from there: nothing is copied or hosted here.</p>
      <h2>If something is wrong</h2><p>Public-domain status differs between countries; these films are public domain in the United States. If a film is listed in error, or a link stops working, it will be removed or replaced at the next update.</p></div>`, "about", "About");
  }

  /* ---------- router ---------- */
  function route() {
    const [path, qs] = decodeURIComponent(location.hash.slice(1) || "/").split("?");
    const q = new URLSearchParams(qs || "");
    const [, a, b] = path.split("/");
    if (!FILMS.length) return render(`<p class="empty"><b>The reels are still being fetched</b>No films have been built yet.</p>`, "home");
    if (!a) return home();
    if (a === "indian" || a === "world") return listing(FILMS.filter((f) => f.s === a), { title: SECTION[a], nav: a, path, q,
      sub: a === "indian" ? "From the studios' and distributors' own channels: Hindi, Bengali and other Indian languages." : "Public-domain classics from the silent era on, and Soviet classics from Mosfilm's and Gorky Studio's own channels." });
    if (a === "decade" && b) return listing(FILMS.filter((f) => decade(f.y) === b), { title: `The ${b}`, nav: "", path, q });
    if (a === "language" && b) return listing(FILMS.filter((f) => f.l === b), { title: b === "Silent" ? "Silent films" : `In ${b}`, nav: "", path, q });
    if (a === "genre" && b) return listing(FILMS.filter((f) => f.g.includes(b)), { title: b, sub: "Genre", nav: "", path, q });
    if (a === "director" && b) return listing(FILMS.filter((f) => f.d.includes(b)), { title: b, sub: "Director", nav: "directors", path, q });
    if (a === "actor" && b) return listing(FILMS.filter((f) => f.cast.includes(b)), { title: b, sub: "Actor", nav: "actors", path, q });
    if (a === "directors") return peopleIndex("director");
    if (a === "actors") return peopleIndex("actor");
    if (a === "film" && b) return film(b);
    if (a === "search") return search(b || "");
    if (a === "about") return about();
    render(`<p class="empty"><b>Nothing showing here</b><a href="#/">Back to the hall</a></p>`, "", "Not found");
  }
  window.addEventListener("hashchange", route);

  $("#search").addEventListener("submit", (e) => {
    e.preventDefault();
    const v = $("#q").value.trim();
    if (v) location.hash = `#/search/${enc(v)}`;
  });

  fetch("films.json", { cache: "no-cache" }).then((r) => (r.ok ? r.json() : { films: [] })).catch(() => ({ films: [] })).then((d) => {
    FILMS = d.films || [];
    FILMS.forEach((f) => (BY_ID[f.id] = f));
    route();
  });
})();
