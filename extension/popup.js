// extension/popup.js — Déjà Bridge
const $ = (id) => document.getElementById(id);

async function load() {
  const c = await chrome.storage.local.get(["excludedDomains", "enabled"]);
  $("enabled").checked = c.enabled !== false;
  $("excluded").value = (c.excludedDomains || []).join("\n");
}

function normDomain(s) {
  s = (s || "").trim().toLowerCase();
  if (!s) return "";
  if (s.includes("://") || s.includes("/")) {
    try { s = new URL(s.includes("://") ? s : "http://" + s).hostname; } catch (e) { s = s.split("/")[0]; }
  }
  s = s.replace(/^\.+/, "");
  if (s.startsWith("www.")) s = s.slice(4);
  return s;
}

async function save() {
  const domains = $("excluded").value
    .split("\n")
    .map(normDomain)
    .filter(Boolean);
  await chrome.storage.local.set({
    enabled: $("enabled").checked,
    excludedDomains: domains
  });
  $("saved").textContent = "Salvato ✓";
  setTimeout(() => { $("saved").textContent = ""; }, 1500);
}

document.addEventListener("DOMContentLoaded", load);
$("save").addEventListener("click", save);
