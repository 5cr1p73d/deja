"""Launcher di prova della nuova AppShell (port da overlay → app).
Avvio: python run_shell.py   (finestra vera, niente cattura/DB)
"""
import sys
from PyQt6.QtWidgets import QApplication

app = QApplication(sys.argv)
from ui import theme
theme.load_fonts(app)
from ui.app_shell import AppShell

w = AppShell()
w.show()
sys.exit(app.exec())
