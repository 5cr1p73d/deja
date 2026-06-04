// extension/background.js — Déjà Bridge (service worker MV3)
// Traccia la tab attiva e manda lo stato (dominio, login, escluso) all'host
// nativo di Déjà via native messaging. Nessuna porta di rete.
const HOST = "com.deja.bridge";

let port = null;
let loginByTab = {};   // tabId -> bool (rilevato dal content script)
let excluded = [];     // domini esclusi (da storage)
let enabled = true;

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

function isExcluded(domain) {
  if (!domain) return false;
  return excluded.some(d => domain === d || domain.endsWith("." + d));
}

async function loadCfg() {
  const c = await chrome.storage.local.get(["excludedDomains", "enabled"]);
  excluded = (c.excludedDomains || []).map(s => String(s).toLowerCase().replace(/^\.+/, "").trim()).filter(Boolean);
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
  send({
    type: "state",
    tab: {
      domain: domain,
      url: tab.url,
      is_login: !!loginByTab[tab.id],
      is_excluded: isExcluded(domain)
    }
  });
}

function boot() {
  loadCfg().then(pushActive);
  try { chrome.alarms.create("hb", { periodInMinutes: 0.5 }); } catch (e) {}
}

chrome.runtime.onInstalled.addListener(boot);
chrome.runtime.onStartup.addListener(boot);
chrome.alarms.onAlarm.addListener(a => { if (a.name === "hb") pushActive(); });
chrome.storage.onChanged.addListener(() => { loadCfg().then(pushActive); });
chrome.tabs.onActivated.addListener(() => pushActive());
chrome.tabs.onUpdated.addListener((id, info) => { if (info.url || info.status === "complete") pushActive(); });
chrome.windows.onFocusChanged.addListener(() => pushActive());
chrome.tabs.onRemoved.addListener(id => { delete loginByTab[id]; });
chrome.runtime.onMessage.addListener((msg, sender) => {
  if (msg && msg.type === "login" && sender.tab) {
    loginByTab[sender.tab.id] = !!msg.is_login;
    pushActive();
  }
});

// avvio immediato (service worker appena sveglio)
boot();
