// extension/content.js — Déjà Bridge
// Rileva schermate di login (campo password visibile o URL tipico) e segnala
// al background. Conservativo: nel dubbio segnala login=true (meglio saltare
// un frame che catturare credenziali).
(function () {
  function hasPassword() {
    // Conservativo: basta l'esistenza di un campo password nel DOM (anche se
    // dietro un tab/nascosto) per considerare la pagina sensibile.
    return !!document.querySelector('input[type="password"]');
  }

  function urlLooksLogin() {
    const u = (location.href || "").toLowerCase();
    return /(\/login|\/log[_-]?in|\/signin|\/sign[_-]?in|\/signup|\/sign[_-]?up|\/register|\/registration|\/create[_-]?account|\/auth(\/|$|\?)|\/account\/login|\/sessions\/new|accounts\.google\.|login\.microsoftonline|appleid\.apple\.|oauth|\/sso|\/connexion|\/anmelden|\/iniciar-sesion)/.test(u);
  }

  let last = null;
  function check() {
    const v = hasPassword() || urlLooksLogin();
    if (v !== last) {
      last = v;
      try { chrome.runtime.sendMessage({ type: "login", is_login: v }); } catch (e) {}
    }
    maybeSendPage();
  }

  // ── Ingest contenuto pagina (F2) ──────────────────────────────
  function extractText() {
    const root = document.querySelector("main, article") || document.body;
    let t = (root && root.innerText) ? root.innerText : "";
    return t.replace(/[ \t]{2,}/g, " ").replace(/\n{3,}/g, "\n\n").trim().slice(0, 15000);
  }
  function extractLinks() {
    const set = new Set();
    document.querySelectorAll("a[href]").forEach(a => {
      try {
        const u = new URL(a.getAttribute("href"), location.href).href;
        if (/^https?:/.test(u)) set.add(u);
      } catch (e) {}
    });
    return Array.from(set).slice(0, 50);
  }
  let sentUrl = null;
  function sendPage() {
    if (last === true) return;                  // login: niente ingest
    if (!/^https?:/.test(location.href)) return;
    const text = extractText();
    if (text.length < 80) return;               // pagina vuota/non utile
    try {
      chrome.runtime.sendMessage({
        type: "page",
        page: {
          url: location.href,
          domain: location.hostname.toLowerCase(),
          title: document.title || "",
          text: text,
          links: extractLinks()
        }
      });
    } catch (e) {}
  }
  function maybeSendPage() {
    if (last === true) return;
    if (location.href === sentUrl) return;       // una volta per URL
    sentUrl = location.href;
    setTimeout(sendPage, 1500);                  // lascia renderizzare (SPA)
  }

  check();

  let t = null;
  try {
    const mo = new MutationObserver(() => {
      clearTimeout(t);
      t = setTimeout(check, 400);
    });
    mo.observe(document.documentElement, { childList: true, subtree: true });
  } catch (e) {}

  window.addEventListener("focus", check);
  // Heartbeat leggero: pagine SPA possono mostrare/nascondere il form senza
  // mutazioni rilevate; ricontrolla ogni 3s.
  setInterval(check, 3000);
  // Self-heal: ri-asserisce lo stato login al background ogni 15s, così se il
  // service worker MV3 è ripartito (perdendo lo stato) torna coerente.
  setInterval(() => {
    try { chrome.runtime.sendMessage({ type: "login", is_login: last === true }); } catch (e) {}
  }, 15000);
})();
