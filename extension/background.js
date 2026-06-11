// extension/background.js — Déjà Bridge (service worker MV3)
// Traccia la tab attiva e manda lo stato (dominio, login, escluso) all'host
// nativo di Déjà via native messaging. Nessuna porta di rete.
const HOST = "com.deja.bridge";

let port = null;
let excluded = [];     // domini esclusi (da storage.local)
let enabled = true;

// IMPORTANTE: il service worker MV3 viene ucciso quando è idle e perderebbe lo
// stato in memoria. `loginByTab` è quindi persistito in chrome.storage.session
// (sopravvive ai riavvii del worker), altrimenti dopo ~30s is_login tornerebbe
// false e gli screenshot di login non verrebbero più saltati.
async function getLoginMap() {
  try { const c = await chrome.storage.session.get("loginByTab"); return c.loginByTab || {}; }
  catch (e) { return {}; }
}
async function setLogin(tabId, v) {
  const m = await getLoginMap();
  if (v) m[tabId] = true; else delete m[tabId];
  try { await chrome.storage.session.set({ loginByTab: m }); } catch (e) {}
}
async function clearLogin(tabId) {
  const m = await getLoginMap();
  if (m[tabId] !== undefined) {
    delete m[tabId];
    try { await chrome.storage.session.set({ loginByTab: m }); } catch (e) {}
  }
}

function connect() {
  try {
    port = chrome.runtime.connectNative(HOST);
    port.onDisconnect.addListener(() => { port = null; });
  } catch (e) {
    port = null;
  }
}

function send(obj) {
  if (!port) connect();
  try {
    if (port) port.postMessage(obj);
  } catch (e) {
    port = null;
  }
}

function domainOf(url) {
  try { return new URL(url).hostname.toLowerCase(); } catch (e) { return ""; }
}

function normDomain(s) {
  s = String(s || "").trim().toLowerCase();
  if (!s) return "";
  if (s.includes("://") || s.includes("/")) {
    try { s = new URL(s.includes("://") ? s : "http://" + s).hostname; } catch (e) { s = s.split("/")[0]; }
  }
  s = s.replace(/^\.+/, "");
  if (s.startsWith("www.")) s = s.slice(4);
  return s;
}

function isExcluded(domain) {
  if (!domain) return false;
  return excluded.some(d => domain === d || domain.endsWith("." + d));
}

async function loadCfg() {
  const c = await chrome.storage.local.get(["excludedDomains", "enabled"]);
  excluded = (c.excludedDomains || []).map(normDomain).filter(Boolean);
  enabled = c.enabled !== false; // default ON nell'estensione; il vero gate è in Déjà
}

async function pushActive() {
  if (!enabled) return;
  let tab = null;
  try {
    const tabs = await chrome.tabs.query({ active: true, lastFocusedWindow: true });
    tab = tabs && tabs[0];
  } catch (e) {}
  if (!tab || !tab.url) {
    send({ type: "state", tab: { domain: "", url: "", is_login: false, is_excluded: false } });
    return;
  }
  const domain = domainOf(tab.url);
  const m = await getLoginMap();
  send({
    type: "state",
    tab: {
      domain: domain,
      url: tab.url,
      is_login: !!m[tab.id],
      is_excluded: isExcluded(domain)
    }
  });
}

function boot() {
  loadCfg().then(pushActive);
  try { chrome.alarms.create("hb", { periodInMinutes: 0.5 }); } catch (e) {}
}

// ── Eventi browser (download / tab / visite) ────────────────────────────────
// Inviati SEMPRE all'host come {type:"event"}: il filtro vero è in Déjà
// (Impostazioni → Eventi, chiavi webev_*, tutto OFF di default) che scarta
// dallo spool ciò che l'utente non ha attivato. Qui si rispettano comunque
// il toggle estensione e i domini esclusi.
function sendEvent(category, action, data) {
  if (!enabled) return;
  send({ type: "event", event: Object.assign({ category: category, action: action }, data || {}) });
}

function isWebUrl(u) {
  return typeof u === "string" && (u.startsWith("http://") || u.startsWith("https://"));
}

chrome.tabs.onCreated.addListener(tab => {
  const url = (tab && tab.url) || "";
  const domain = domainOf(url);
  if (isExcluded(domain)) return;
  sendEvent("tab", "opened", { url: isWebUrl(url) ? url : "", domain: domain, title: (tab && tab.title) || "" });
});

// guard: se il permesso "downloads" non è ancora concesso (estensione vecchia
// non ricaricata) chrome.downloads è undefined e NON deve uccidere il worker.
if (chrome.downloads && chrome.downloads.onCreated) {

chrome.downloads.onCreated.addListener(d => {
  const domain = domainOf(d.url || d.finalUrl || "");
  if (isExcluded(domain)) return;
  sendEvent("download", "started", {
    url: d.url || "", final_url: d.finalUrl || "", domain: domain,
    filename: d.filename || "", mime: d.mime || "", bytes: d.totalBytes || 0
  });
});

chrome.downloads.onChanged.addListener(delta => {
  if (!delta.state || delta.state.current !== "complete") return;
  try {
    chrome.downloads.search({ id: delta.id }, items => {
      const it = items && items[0];
      if (!it) return;
      const domain = domainOf(it.url || "");
      if (isExcluded(domain)) return;
      sendEvent("download", "completed", {
        url: it.url || "", domain: domain, filename: it.filename || "",
        mime: it.mime || "", bytes: it.fileSize || it.totalBytes || 0
      });
    });
  } catch (e) {}
});

}

// Visite: page-load completi (URL+titolo, MAI il contenuto — quello è "page").
// Le tab di login non vengono mai registrate (parità col privacy bridge).
async function maybeVisit(tabId, tab) {
  const url = (tab && tab.url) || "";
  if (!isWebUrl(url)) return;
  const domain = domainOf(url);
  if (isExcluded(domain)) return;
  const m = await getLoginMap();
  if (m[tabId]) return;
  sendEvent("visit", "visited", { url: url, domain: domain, title: (tab && tab.title) || "" });
}

chrome.runtime.onInstalled.addListener(boot);
chrome.runtime.onStartup.addListener(boot);
chrome.alarms.onAlarm.addListener(a => { if (a.name === "hb") pushActive(); });
chrome.storage.onChanged.addListener((changes, area) => { if (area === "local") loadCfg().then(pushActive); });
chrome.tabs.onActivated.addListener(() => pushActive());
chrome.tabs.onUpdated.addListener((id, info, tab) => {
  if (info.url || info.status === "complete") pushActive();
  if (info.status === "complete") maybeVisit(id, tab);
});
chrome.windows.onFocusChanged.addListener(() => pushActive());
chrome.tabs.onRemoved.addListener(id => { clearLogin(id); sendEvent("tab", "closed", { tab_id: id }); });
chrome.runtime.onMessage.addListener((msg, sender) => {
  if (!msg) return;
  if (msg.type === "login" && sender.tab) {
    setLogin(sender.tab.id, msg.is_login).then(pushActive);
  } else if (msg.type === "page" && enabled) {
    const domain = (msg.page && msg.page.domain) || "";
    if (isExcluded(domain)) return;
    getLoginMap().then(m => {
      if (sender.tab && m[sender.tab.id]) return;  // tab di login: niente ingest
      send({ type: "page", page: msg.page });
    });
  }
});

// avvio immediato (service worker appena sveglio)
boot();
