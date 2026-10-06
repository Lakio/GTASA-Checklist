"""Démarrage : préparation des données tirées des fichiers du jeu, puis fenêtre."""

import sys
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QFont, QIcon, QPalette, QPixmap
from PySide6.QtWidgets import QApplication, QFileDialog, QMessageBox, QSplashScreen

from . import APP_NAME, gamefiles
from .catalog import EXPORT_LISTS, LOC, item_spot_specs
from .ui_main import MainWindow

def resource(rel: str) -> Path:
    """Fichier fourni avec l'appli (dans l'exe PyInstaller ou à côté des sources)."""
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent.parent))
    return base / rel


DATA_VERSION = 2   # à incrémenter si le format des fichiers générés change


def prepare_game_data(game_dir: str | None,
                      splash: QSplashScreen | None) -> tuple[str | None, dict, dict]:
    """Génère (une seule fois) la carte radar, les collectibles et les spawns d'export."""
    def say(text):
        if splash:
            splash.showMessage(text, Qt.AlignBottom | Qt.AlignHCenter, QColor("white"))
            QApplication.processEvents()

    meta = gamefiles.load_json("generated.json", {})
    fresh = meta.get("game_dir") == game_dir and meta.get("version") == DATA_VERSION
    map_path = gamefiles.app_dir() / "radar_map.png"
    known = gamefiles.load_json("collectibles.json", {})
    spawns = gamefiles.load_json("exports.json", {})

    if game_dir and (not fresh or not known):
        say("Lecture des collectibles dans main.scm…")
        try:
            known = gamefiles.extract_collectibles(Path(game_dir) / "data" / "script" / "main.scm")
            gamefiles.save_json("collectibles.json", known)
        except OSError as exc:
            print("main.scm illisible :", exc, file=sys.stderr)
    if game_dir and (not fresh or not spawns):
        say("Recherche des véhicules d'export (main.scm, IPL)…")
        try:
            models = [model for vehicles in EXPORT_LISTS for _name, model in vehicles]
            spawns = gamefiles.extract_export_spawns(game_dir, models)
            gamefiles.save_json("exports.json", spawns)
        except (OSError, ValueError) as exc:
            print("Spawns d'export non générés :", exc, file=sys.stderr)
    if game_dir and (not fresh or not gamefiles.load_json("places.json", {})):
        say("Localisation des activités (main.scm, IPL)…")
        try:
            candidates = gamefiles.extract_place_candidates(game_dir)
            gamefiles.save_json("places.json",
                                gamefiles.resolve_spots(candidates, item_spot_specs(), LOC))
        except (OSError, ValueError) as exc:
            print("Lieux non générés :", exc, file=sys.stderr)
    if game_dir and (not fresh or not map_path.exists()):
        say("Construction de la carte à partir de gta3.img…")
        try:
            gamefiles.build_radar_map(game_dir, map_path)
        except (OSError, ValueError) as exc:
            print("Carte non générée :", exc, file=sys.stderr)
    if game_dir:
        gamefiles.save_json("generated.json", {"game_dir": game_dir, "version": DATA_VERSION})
    return (str(map_path) if map_path.exists() else None), known, spawns


def apply_theme(app: QApplication) -> None:
    """Thème sombre sobre, indépendant du thème Windows."""
    app.setStyle("Fusion")
    p = QPalette()
    colors = {
        QPalette.Window: "#1f2329", QPalette.WindowText: "#e6e6e6",
        QPalette.Base: "#16191d", QPalette.AlternateBase: "#1c2025",
        QPalette.Text: "#e6e6e6", QPalette.Button: "#2a2f36", QPalette.ButtonText: "#e6e6e6",
        QPalette.ToolTipBase: "#2a2f36", QPalette.ToolTipText: "#f0f0f0",
        QPalette.Highlight: "#3d6b4f", QPalette.HighlightedText: "#ffffff",
        QPalette.PlaceholderText: "#7d8590", QPalette.Link: "#6fcf97",
    }
    for role, color in colors.items():
        p.setColor(role, QColor(color))
    p.setColor(QPalette.Disabled, QPalette.Text, QColor("#6b7280"))
    p.setColor(QPalette.Disabled, QPalette.ButtonText, QColor("#6b7280"))
    app.setPalette(p)
    app.setStyleSheet("""
        QToolTip { border: 1px solid #3a4049; padding: 4px; }
        QTreeWidget { border: 1px solid #2c3138; }
        QTreeWidget::item { padding: 2px 0; }
        QHeaderView::section { background: #2a2f36; border: 0; border-right: 1px solid #1f2329;
                               padding: 4px 6px; }
        QProgressBar { border: 1px solid #3a4049; border-radius: 4px; background: #16191d;
                       text-align: center; height: 18px; }
        QProgressBar::chunk { background: #3f8f5f; border-radius: 3px; }
        QLineEdit { border: 1px solid #3a4049; border-radius: 4px; padding: 4px 6px;
                    background: #16191d; }
        QPushButton { border: 1px solid #3a4049; border-radius: 4px; padding: 4px 10px;
                      background: #2a2f36; }
        QPushButton:hover { background: #343a42; }
        QGraphicsView { border: 1px solid #2c3138; }
    """)


def main() -> int:
    QApplication.setHighDpiScaleFactorRoundingPolicy(Qt.HighDpiScaleFactorRoundingPolicy.PassThrough)
    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setWindowIcon(QIcon(str(resource("assets/icon.ico"))))
    apply_theme(app)

    game_dir = gamefiles.find_game_dir()
    if not game_dir:
        QMessageBox.information(None, APP_NAME, (
            "Dossier de GTA San Andreas introuvable.\n\n"
            "Indique le dossier d'installation (celui qui contient gta_sa.exe) pour générer "
            "la carte et la position des collectibles. Tu peux annuler : la checklist "
            "fonctionnera quand même."))
        chosen = QFileDialog.getExistingDirectory(None, "Dossier de GTA San Andreas")
        if chosen and gamefiles.is_game_dir(chosen):
            game_dir = chosen
            settings = gamefiles.load_json("settings.json", {})
            settings["game_dir"] = chosen
            gamefiles.save_json("settings.json", settings)

    pix = QPixmap(460, 140)
    pix.fill(QColor("#1e272e"))
    splash = QSplashScreen(pix)
    splash.setFont(QFont(app.font().family(), 11))
    splash.show()
    map_path, known, spawns = prepare_game_data(game_dir, splash)

    win = MainWindow(game_dir, map_path, known, spawns)
    win.show()
    splash.finish(win)
    return app.exec()
