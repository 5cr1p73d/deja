// Costanti del sito condivise (download, versione, link).
// Override possibile via env pubbliche (NEXT_PUBLIC_*).

export const APP_VERSION = process.env.NEXT_PUBLIC_APP_VERSION || "1.0.0";

export const REPO_URL =
  process.env.NEXT_PUBLIC_REPO_URL || "https://github.com/5cr1p73d/deja";

// Pagina release di GitHub (lì viene pubblicato l'installer .exe).
export const DOWNLOAD_URL =
  process.env.NEXT_PUBLIC_DOWNLOAD_URL || `${REPO_URL}/releases`;

// Installer Windows (Inno Setup) pubblicato nelle Release. In alternativa è
// disponibile anche la build portatile zip `Deja-${APP_VERSION}-win64.zip`.
export const INSTALLER_NAME =
  process.env.NEXT_PUBLIC_INSTALLER_NAME || `Deja-Setup-${APP_VERSION}.exe`;

// Dimensione indicativa dell'installer (lzma2/max su onedir torch + modelli).
export const INSTALLER_SIZE = process.env.NEXT_PUBLIC_INSTALLER_SIZE || "~265 MB";
