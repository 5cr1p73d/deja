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
