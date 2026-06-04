// extension/content.js — Déjà Bridge
// Rileva schermate di login (campo password visibile o URL tipico) e segnala
// al background. Conservativo: nel dubbio segnala login=true (meglio saltare
// un frame che catturare credenziali).
(function () {
  function hasVisiblePassword() {
    const inputs = document.querySelectorAll('input[type="password"]');
    for (const el of inputs) {
      try {
        const r = el.getBoundingClientRect();
        if (r.width > 0 && r.height > 0 && el.offsetParent !== null) return true;
      } catch (e) {}
    }
    return false;
  }

  function urlLooksLogin() {
    const u = (location.href || "").toLowerCase();
    return /(\/login|\/log-in|\/signin|\/sign-in|\/signup|\/sign-up|\/register|\/registration|\/create-account|\/auth(\/|$)|\/account\/login|\/sessions\/new|accounts\.google\.|login\.microsoftonline|appleid\.apple\.|oauth|\/sso)/.test(u);
  }

  let last = null;
  function check() {
    const v = hasVisiblePassword() || urlLooksLogin();
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
})();
