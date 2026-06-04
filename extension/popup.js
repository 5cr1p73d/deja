// extension/popup.js — Déjà Bridge
const $ = (id) => document.getElementById(id);

async function load() {
  const c = await chrome.storage.local.get(["excludedDomains", "enabled"]);
  $("enabled").checked = c.enabled !== false;
  $("excluded").value = (c.excludedDomains || []).join("\n");
}

async function save() {
  const domains = $("excluded").value
    .split("\n")
    .map(s => s.trim().toLowerCase().replace(/^\.+/, ""))
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
