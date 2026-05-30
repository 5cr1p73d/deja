@echo off
REM Build di Déjà — usa deja.spec come unica fonte di verità.
REM Richiede: venv con PyInstaller installato (pip install pyinstaller).

call "%~dp0venv\Scripts\activate.bat"
if errorlevel 1 (
  echo [build] Impossibile attivare il venv in venv\Scripts. Interrompo.
  exit /b 1
)

echo [build] Pulizia output precedente...
if exist "%~dp0build" rmdir /s /q "%~dp0build"
if exist "%~dp0dist\Deja" rmdir /s /q "%~dp0dist\Deja"

echo [build] PyInstaller (deja.spec)...
pyinstaller --noconfirm "%~dp0deja.spec"
if errorlevel 1 (
  echo [build] Build fallito.
  exit /b 1
)

echo.
echo [build] OK: dist\Deja\Deja.exe
echo [build] Per creare l'installer: compila deja.iss con Inno Setup (iscc deja.iss).
