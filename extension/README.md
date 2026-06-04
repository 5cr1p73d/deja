# Déjà Bridge — estensione browser

Bridge **privacy** tra il browser e Déjà: quando la tab attiva è una schermata
di **login** o un **sito escluso**, Déjà **non cattura** lo schermo.

Canale **locale e sicuro**: l'estensione parla con Déjà solo tramite *native
messaging* (stdin/stdout, vincolato all'ID dell'estensione). **Nessuna porta di
rete aperta.** L'estensione non manda nulla su internet.

## Installazione (Chrome / Edge / Brave)

1. In **Déjà** → Impostazioni → **Area & Privacy** → sezione *Estensione browser*:
   attiva il toggle.
2. Apri `chrome://extensions` (o `edge://extensions`), abilita **Modalità
   sviluppatore**, clicca **Carica estensione non pacchettizzata** e seleziona
   questa cartella (`extension/`).
3. Copia l'**ID** assegnato all'estensione e incollalo in Déjà nel campo
   *ID estensione*, poi premi **Installa host**.
4. Riavvia il browser (così rilegge l'host native messaging).
5. Nel popup dell'estensione puoi aggiungere i **domini da non catturare**.

## Cosa fa
- Rileva login (campo password visibile o URL tipico di login) → Déjà salta la
  cattura mentre quella tab è in primo piano.
- Domini esclusi (impostabili nel popup o in Déjà) → mai catturati.

## Sicurezza
- Niente server/porte. Solo native messaging gated dall'ID estensione.
- L'host scrive solo un file di stato locale (`web_state.json`); **non** scrive
  nel database di Déjà (unico writer = l'app).
- Tutto **spento di default** in Déjà.

## Stato
- **F1 (questa):** privacy — salta login / siti esclusi.
- **F2 (futuro):** ingest del contenuto pagina per renderlo cercabile in Déjà.
