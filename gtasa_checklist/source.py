"""Choix de la source de données (mémoire du jeu ou sauvegarde) dans un thread à part."""

import traceback
from pathlib import Path

from PySide6.QtCore import QObject, QThread, QTimer, Signal, Slot

from . import gamefiles, memory, savefile

POLL_MS = 1000


class SourceWorker(QObject):
    snapshot = Signal(object)          # Snapshot
    status = Signal(str, str)          # niveau ("ok", "warn", "off"), message

    def __init__(self):
        super().__init__()
        self.mode = "auto"             # "auto" ou "save"
        self.save_path: Path | None = None
        self.game_dir: str | None = None
        self._mem: memory.GameMemory | None = None
        self._save_key = None
        self._timer: QTimer | None = None
        self._last_error = ""

    @Slot()
    def start(self):
        self._timer = QTimer(self)
        self._timer.timeout.connect(self.tick)
        self._timer.start(POLL_MS)
        self.tick()

    @Slot(str, str)
    def configure(self, mode: str, save_path: str):
        self.mode = mode
        self.save_path = Path(save_path) if save_path else None
        self._save_key = None
        self.tick()

    @Slot(str)
    def set_game_dir(self, game_dir: str):
        self.game_dir = game_dir or None

    @Slot()
    def rescan(self):
        """Oublie les adresses mémorisées et relance la recherche."""
        cache = gamefiles.load_json("addresses.json", {})
        if self._mem:
            cache.pop(self._mem.build_key, None)
            gamefiles.save_json("addresses.json", cache)
            self._mem.addr.clear()
            self._mem.resolve(force=True)
        self.tick()

    @Slot()
    def tick(self):
        try:
            if self.mode == "save" and not (self.save_path and self.save_path.exists()):
                # la sauvegarde choisie a disparu : retour à la source automatique
                self.mode, self.save_path, self._save_key = "auto", None, None
            if self.mode == "auto" and self._tick_memory():
                return
            self._tick_save()
        except Exception as exc:                       # ne jamais tuer le thread
            msg = f"Erreur : {exc}"
            if msg != self._last_error:
                traceback.print_exc()
                self._last_error = msg
            self.status.emit("warn", msg)

    def _tick_memory(self) -> bool:
        if self._mem and not self._mem.alive():
            self._mem.close()
            self._mem = None
            self._save_key = None
        if not self._mem:
            pid = memory.find_game_process()
            if not pid:
                return False
            try:
                self._mem = memory.GameMemory(pid, self.game_dir)
            except (PermissionError, memory.GameNotRunning) as exc:
                self.status.emit("warn", str(exc))
                return False
            self.status.emit("warn", f"Jeu détecté ({self._mem.version}) — recherche des données…")
            self._mem.resolve(force=True)
        try:
            snap = self._mem.snapshot()
        except memory.GameNotRunning:
            return False
        if not snap.has_globals:
            self.status.emit("warn", f"Jeu détecté ({self._mem.version}) — en attente du "
                                     "chargement d'une partie…")
            return True
        missing = [n for n, ok in (("joueur", snap.player), ("stats", snap.stats_int),
                                   ("tags", snap.tags), ("collectibles", snap.pickups is not None))
                   if not ok]
        text = snap.label + (f" (non trouvé : {', '.join(missing)})" if missing else "")
        self.status.emit("ok" if not missing else "warn", text)
        self.snapshot.emit(snap)
        return True

    def _tick_save(self):
        path = self.save_path if self.mode == "save" else None
        if path is None:
            saves = savefile.list_saves(gamefiles.saves_dir())
            path = saves[0] if saves else None
        if path is None or not path.exists():
            self.status.emit("off", "Jeu non lancé et aucune sauvegarde trouvée")
            self._save_key = None
            return
        st = path.stat()
        key = (str(path), st.st_mtime, st.st_size)
        if key == self._save_key:
            return
        self._save_key = key
        try:
            snap = savefile.read_save(path)
        except (ValueError, OSError, IndexError) as exc:
            self.status.emit("warn", f"Sauvegarde illisible : {exc}")
            return
        prefix = "Jeu non lancé — " if self.mode == "auto" else ""
        self.status.emit("ok", prefix + snap.label)
        self.snapshot.emit(snap)


class SourceController(QObject):
    """Possède le thread et expose des signaux thread-safe vers le worker."""
    configure = Signal(str, str)
    set_game_dir = Signal(str)
    rescan = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.thread = QThread()
        self.worker = SourceWorker()
        self.worker.moveToThread(self.thread)
        self.thread.started.connect(self.worker.start)
        self.configure.connect(self.worker.configure)
        self.set_game_dir.connect(self.worker.set_game_dir)
        self.rescan.connect(self.worker.rescan)

    def start(self):
        self.thread.start()

    def stop(self):
        self.thread.quit()
        self.thread.wait(3000)
