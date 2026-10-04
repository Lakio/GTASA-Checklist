"""Fenêtre principale : checklist à gauche, carte à droite."""

from collections import defaultdict
from pathlib import Path

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QAction, QBrush, QColor, QFont, QKeySequence
from PySide6.QtWidgets import (QApplication, QCheckBox, QDialog, QDialogButtonBox,
                               QFileDialog, QHBoxLayout, QHeaderView, QLabel, QLineEdit,
                               QMainWindow, QMenu, QMessageBox, QPlainTextEdit, QProgressBar,
                               QPushButton, QSplitter, QTreeWidget, QTreeWidgetItem,
                               QVBoxLayout, QWidget)

from . import APP_NAME, __version__, gamefiles
from .catalog import EXPORT_LISTS, Item, all_items, build_catalog
from .model import COLLECT_TOTALS, Snapshot
from .rules import CollectState, compute_collectibles, evaluate
from .source import SourceController
from .ui_map import LAYERS, MapView

STATUS_COLORS = {"ok": "#2ecc71", "warn": "#f39c12", "off": "#7f8c8d"}
COLLECT_LABELS = {"tags": "Tag", "snapshots": "Photo", "horseshoes": "Fer à cheval",
                  "oysters": "Huître"}
ROLE_ITEM = Qt.UserRole + 1
INTERIOR_Z = 500.0


class MainWindow(QMainWindow):
    def __init__(self, game_dir: str | None, map_path: str | None, known: dict,
                 spawns: dict | None = None):
        super().__init__()
        self.setWindowTitle(f"{APP_NAME} {__version__}")
        self.resize(1500, 900)
        self.settings = gamefiles.load_json("settings.json", {})
        self.manual: dict[str, bool] = gamefiles.load_json("progress.json", {})
        self.tag_positions: list = gamefiles.load_json("tags.json", [])
        self.game_dir = game_dir
        self.known = known
        # spawns des véhicules d'export, indexés par id d'élément (e_<liste>_<n>)
        spawns = spawns or {}
        self.export_spawns = {f"e_{li}_{si}": spawns.get(model, [])
                              for li, vehicles in enumerate(EXPORT_LISTS)
                              for si, (_name, model) in enumerate(vehicles)}
        self.cats = build_catalog()
        self.items = all_items(self.cats)
        self.snap: Snapshot | None = None
        self.coll = CollectState()
        self.auto: dict[str, bool | None] = {}
        self.last_outdoor = None

        self._build_ui(map_path)
        self._build_menu()
        self.refresh()

        self.source = SourceController(self)
        self.source.worker.game_dir = game_dir
        self.source.worker.snapshot.connect(self.on_snapshot)
        self.source.worker.status.connect(self.on_status)
        if self.settings.get("source_mode") == "save" and self.settings.get("save_path") \
                and Path(self.settings["save_path"]).exists():
            self.source.worker.mode = "save"
            self.source.worker.save_path = Path(self.settings["save_path"])
        self.source.start()

    # ================================================================ UI
    def _build_ui(self, map_path):
        central = QWidget()
        root = QVBoxLayout(central)
        root.setContentsMargins(8, 8, 8, 4)

        # -- En-tête : progression globale et source ----------------------
        head = QHBoxLayout()
        self.lbl_total = QLabel()
        self.lbl_total.setFont(QFont(self.font().family(), 13, QFont.Bold))
        self.bar_total = QProgressBar()
        self.bar_total.setMaximumWidth(320)
        self.bar_total.setTextVisible(True)
        self.lbl_ingame = QLabel()
        self.lbl_ingame.setToolTip("Pourcentage calculé par le jeu (statistique « progression »)")
        head.addWidget(self.lbl_total)
        head.addWidget(self.bar_total)
        head.addSpacing(16)
        head.addWidget(self.lbl_ingame)
        head.addStretch(1)
        self.lbl_source = QLabel()
        self.lbl_source.setTextFormat(Qt.RichText)
        head.addWidget(self.lbl_source)
        root.addLayout(head)

        split = QSplitter(Qt.Horizontal)
        root.addWidget(split, 1)

        # -- Checklist ------------------------------------------------------
        left = QWidget()
        lv = QVBoxLayout(left)
        lv.setContentsMargins(0, 0, 0, 0)
        tools = QHBoxLayout()
        self.search = QLineEdit()
        self.search.setPlaceholderText("Rechercher…")
        self.search.setClearButtonEnabled(True)
        self.search.textChanged.connect(self.apply_filter)
        self.chk_hide_done = QCheckBox("Masquer les terminés")
        self.chk_hide_done.setChecked(self.settings.get("hide_done", False))
        self.chk_hide_done.toggled.connect(self.apply_filter)
        self.chk_hide_done.toggled.connect(self._save_settings)
        self.chk_bonus = QCheckBox("Bonus")
        self.chk_bonus.setToolTip("Afficher aussi ce qui ne compte pas pour le 100 %")
        self.chk_bonus.setChecked(self.settings.get("show_bonus", True))
        self.chk_bonus.toggled.connect(self.refresh)
        self.chk_bonus.toggled.connect(self._save_settings)
        tools.addWidget(self.search, 1)
        tools.addWidget(self.chk_hide_done)
        tools.addWidget(self.chk_bonus)
        lv.addLayout(tools)

        self.tree = QTreeWidget()
        self.tree.setHeaderLabels(["Élément", "État", "Détecté par"])
        self.tree.setUniformRowHeights(True)
        self.tree.setAlternatingRowColors(True)
        self.tree.header().setSectionResizeMode(0, QHeaderView.Stretch)
        self.tree.header().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self.tree.header().setSectionResizeMode(2, QHeaderView.ResizeToContents)
        self.tree.itemChanged.connect(self.on_item_changed)
        self.tree.itemClicked.connect(self.on_item_clicked)
        self.tree.setContextMenuPolicy(Qt.CustomContextMenu)
        self.tree.customContextMenuRequested.connect(self.on_context_menu)
        lv.addWidget(self.tree, 1)
        split.addWidget(left)

        # -- Carte ----------------------------------------------------------
        right = QWidget()
        rv = QVBoxLayout(right)
        rv.setContentsMargins(0, 0, 0, 0)
        layer_bar = QHBoxLayout()
        self.layer_checks: dict[str, QCheckBox] = {}
        hidden = set(self.settings.get("hidden_layers", []))
        for key, (label, color, _r) in LAYERS.items():
            cb = QCheckBox(label.replace("&", "&&"))
            cb.setChecked(key not in hidden)
            cb.setStyleSheet(f"QCheckBox::indicator:checked {{ background: {color}; "
                             f"border: 1px solid #222; border-radius: 3px; }}")
            cb.toggled.connect(lambda on, k=key: self.on_layer_toggled(k, on))
            self.layer_checks[key] = cb
            layer_bar.addWidget(cb)
        layer_bar.addStretch(1)
        rv.addLayout(layer_bar)

        map_bar = QHBoxLayout()
        self.chk_map_done = QCheckBox("Montrer les terminés (gris)")
        self.chk_map_done.setChecked(self.settings.get("map_show_done", True))
        self.chk_follow = QCheckBox("Suivre CJ")
        btn_cj = QPushButton("Centrer sur CJ")
        btn_fit = QPushButton("Carte entière")
        self.lbl_coords = QLabel()
        self.lbl_coords.setMinimumWidth(150)
        map_bar.addWidget(self.chk_map_done)
        map_bar.addWidget(self.chk_follow)
        map_bar.addWidget(btn_cj)
        map_bar.addWidget(btn_fit)
        map_bar.addStretch(1)
        map_bar.addWidget(self.lbl_coords)
        rv.addLayout(map_bar)

        self.map = MapView()
        self.map.set_background(map_path)
        for key in LAYERS:
            self.map.set_layer_visible(key, self.layer_checks[key].isChecked())
        self.map.set_show_done(self.chk_map_done.isChecked())
        self.chk_map_done.toggled.connect(self.on_map_done_toggled)
        self.chk_follow.toggled.connect(lambda on: setattr(self.map, "follow_player", on))
        btn_cj.clicked.connect(self.map.center_on_player)
        btn_fit.clicked.connect(self.map.fit)
        self.map.coordsHovered.connect(
            lambda x, y: self.lbl_coords.setText(f"X {x:7.0f}   Y {y:7.0f}"))
        rv.addWidget(self.map, 1)
        split.addWidget(right)
        split.setStretchFactor(0, 0)
        split.setStretchFactor(1, 1)
        split.setSizes([520, 980])

        self.setCentralWidget(central)
        self._populate_tree()

    def _build_menu(self):
        m = self.menuBar().addMenu("&Fichier")
        act = QAction("Source automatique (jeu, sinon dernière sauvegarde)", self)
        act.triggered.connect(self.use_auto_source)
        m.addAction(act)
        act = QAction("Ouvrir une sauvegarde…", self)
        act.setShortcut(QKeySequence.Open)
        act.triggered.connect(self.choose_save)
        m.addAction(act)
        act = QAction("Dossier du jeu…", self)
        act.triggered.connect(self.choose_game_dir)
        m.addAction(act)
        m.addSeparator()
        act = QAction("Quitter", self)
        act.setShortcut(QKeySequence.Quit)
        act.triggered.connect(self.close)
        m.addAction(act)

        m = self.menuBar().addMenu("&Outils")
        act = QAction("Diagnostic de lecture…", self)
        act.triggered.connect(self.show_diagnostics)
        m.addAction(act)
        act = QAction("Relancer la recherche en mémoire", self)
        act.triggered.connect(lambda: self.source.rescan.emit())
        m.addAction(act)
        act = QAction("Effacer toutes les coches manuelles…", self)
        act.triggered.connect(self.clear_manual)
        m.addAction(act)

        m = self.menuBar().addMenu("&Aide")
        act = QAction("À propos", self)
        act.triggered.connect(self.show_about)
        m.addAction(act)

    def _populate_tree(self):
        self.tree.blockSignals(True)
        self.tree.clear()
        self.cat_nodes: dict[str, QTreeWidgetItem] = {}
        self.item_nodes: dict[str, QTreeWidgetItem] = {}
        bold = QFont(self.tree.font())
        bold.setBold(True)
        for cat in self.cats:
            cnode = QTreeWidgetItem([cat.name, "", ""])
            cnode.setFont(0, bold)
            cnode.setFirstColumnSpanned(False)
            self.tree.addTopLevelItem(cnode)
            self.cat_nodes[cat.id] = cnode
            for it in cat.items:
                parent = cnode
                if it.group:
                    # nouveau sous-groupe à chaque changement de donneur (ordre du jeu)
                    key = it.group
                    last = cnode.child(cnode.childCount() - 1) if cnode.childCount() else None
                    if last is None or last.data(0, ROLE_ITEM) != f"group:{key}":
                        g = QTreeWidgetItem([key, "", ""])
                        g.setData(0, ROLE_ITEM, f"group:{key}")
                        g.setForeground(0, QBrush(QColor("#8e9aaf")))
                        cnode.addChild(g)
                        g.setExpanded(True)
                    parent = cnode.child(cnode.childCount() - 1)
                node = QTreeWidgetItem([it.name, "", ""])
                node.setData(0, ROLE_ITEM, it.id)
                node.setFlags(node.flags() | Qt.ItemIsUserCheckable)
                node.setCheckState(0, Qt.Unchecked)
                tip = []
                if it.note:
                    tip.append(it.note)
                if it.rule is None:
                    tip.append("Pas de détection automatique : coche à la main.")
                if not it.required:
                    tip.append("Ne compte pas pour le 100 %.")
                if it.pos:
                    tip.append("Clic : voir sur la carte" + (" (position approximative)" if it.approx else ""))
                node.setToolTip(0, "\n".join(tip))
                parent.addChild(node)
                self.item_nodes[it.id] = node
            cnode.setExpanded(cat is self.cats[0])
        self.tree.blockSignals(False)

    # ======================================================= Données
    def on_snapshot(self, snap: Snapshot):
        self.snap = snap
        if snap.source == "memory" and snap.tags and any(t.x is not None for t in snap.tags):
            positions = [(t.x, t.y, t.z) if t.x is not None else None for t in snap.tags]
            if positions != self.tag_positions:
                self.tag_positions = positions
                gamefiles.save_json("tags.json", positions)
        self.refresh()

    def on_status(self, level: str, text: str):
        color = STATUS_COLORS.get(level, "#7f8c8d")
        self.lbl_source.setText(f'<span style="color:{color}; font-size:16px">●</span> {text}')

    def effective(self, it: Item) -> bool:
        if it.id in self.manual:
            return self.manual[it.id]
        return self.auto.get(it.id) is True

    def refresh(self):
        self.coll = compute_collectibles(self.snap, self.known, self.tag_positions)
        self.auto = {it.id: evaluate(it.rule, self.snap, self.coll) for it in self.items}
        self._refresh_tree()
        self._refresh_header()
        self._refresh_map()

    def _refresh_tree(self):
        self.tree.blockSignals(True)
        green, grey, orange = QColor("#27ae60"), QColor("#95a5a6"), QColor("#e67e22")
        for cat in self.cats:
            done = total = 0
            for it in cat.items:
                node = self.item_nodes[it.id]
                eff = self.effective(it)
                auto = self.auto.get(it.id)
                node.setCheckState(0, Qt.Checked if eff else Qt.Unchecked)
                node.setText(1, "Fait" if eff else "À faire")
                node.setForeground(1, QBrush(green if eff else orange))
                if it.id in self.manual:
                    node.setText(2, "manuel")
                    node.setForeground(2, QBrush(QColor("#9b59b6")))
                elif auto is None:
                    node.setText(2, "—" if it.rule is None else "inconnu")
                    node.setForeground(2, QBrush(grey))
                else:
                    node.setText(2, "jeu")
                    node.setForeground(2, QBrush(green))
                extra = self._collect_suffix(it)
                node.setText(0, it.name + extra)
                if self.chk_bonus.isChecked() or it.required:
                    total += 1
                    done += eff
            cnode = self.cat_nodes[cat.id]
            cnode.setText(1, f"{done}/{total}")
            cnode.setForeground(1, QBrush(green if total and done == total else grey))
        self.tree.blockSignals(False)
        self.apply_filter()

    def _collect_suffix(self, it: Item) -> str:
        if not it.rule or it.rule[0] not in ("collect", "usj"):
            return ""
        if it.rule[0] == "usj":
            st = self.snap.stunts if self.snap else None
            return f"  ({sum(s.done for s in st)}/{len(st)})" if st else ""
        kind = it.rule[1]
        count = self.coll.counts.get(kind)
        return f"  ({count}/{COLLECT_TOTALS[kind]})" if count is not None else ""

    def _refresh_header(self):
        req = [it for it in self.items if it.required]
        done = sum(self.effective(it) for it in req)
        pct = 100.0 * done / len(req) if req else 0
        self.lbl_total.setText(f"Checklist 100 % : {done}/{len(req)}")
        self.bar_total.setRange(0, len(req))
        self.bar_total.setValue(done)
        self.bar_total.setFormat(f"{pct:.1f} %")
        game_pct = self.snap.progress_percent if self.snap else None
        self.lbl_ingame.setText(f"Progression en jeu : <b>{game_pct:.1f} %</b>"
                                if game_pct is not None else "")

    def _refresh_map(self):
        # Collectibles
        for kind in ("tags", "snapshots", "horseshoes", "oysters"):
            entries = []
            pts = self.coll.points.get(kind, [])
            flags = self.coll.done.get(kind, [])
            for i, p in enumerate(pts):
                if not p:
                    continue
                d = flags[i] if i < len(flags) else None
                state = {True: "ramassé" if kind != "tags" else "tagué",
                         False: "à faire", None: "état inconnu"}[d]
                tip = f"{COLLECT_LABELS[kind]} n°{i + 1} — {state}\nX {p[0]:.0f}  Y {p[1]:.0f}  Z {p[2]:.0f}"
                entries.append((p[0], p[1], tip, d))
            self.map.set_markers(kind, entries)
        # Sauts uniques
        entries = []
        for i, s in enumerate((self.snap.stunts if self.snap else None) or []):
            tip = f"Saut unique n°{i + 1} — {'réussi' if s.done else ('trouvé' if s.found else 'à faire')}"
            entries.append((s.x, s.y, tip, s.done))
        self.map.set_markers("stunts", entries)
        # Lieux des missions et activités (regroupés par position)
        # Véhicules d'export : un point par emplacement de spawn
        entries = []
        by_id = {it.id: it for it in self.items}
        for item_id, spots in self.export_spawns.items():
            it = by_id[item_id]
            done = self.effective(it)
            for n, (x, y, z, source) in enumerate(spots):
                lines = [f"{it.name} — {it.group} — {'livré' if done else 'à livrer'}",
                         f"Point de spawn {n + 1}/{len(spots)}",
                         "Garé en permanence" if source == "carte"
                         else "Garé par le script (peut dépendre de la progression)",
                         f"X {x:.0f}  Y {y:.0f}  Z {z:.0f}"]
                entries.append((x, y, "\n".join(lines), done))
        self.map.set_markers("exports", entries)

        cat_names = {c.id: c.name for c in self.cats}
        by_pos: dict[tuple, list[Item]] = defaultdict(list)
        for it in self.items:
            if it.pos:
                by_pos[it.pos].append(it)
        entries = []
        for pos, its in by_pos.items():
            todo = [it for it in its if not self.effective(it)]
            givers = list(dict.fromkeys(it.group or cat_names[it.category] for it in its))
            lines = [f"{len(todo)} à faire sur {len(its)}"]
            for it in its[:30]:
                lines.append(("✔ " if self.effective(it) else "○ ") + it.name
                             + (f"  ({it.group})" if len(givers) > 1 and it.group else ""))
            if len(its) > 30:
                lines.append(f"… et {len(its) - 30} autres")
            if its[0].approx:
                lines.append("(position approximative)")
            entries.append((pos[0], pos[1], " / ".join(givers) + "\n" + "\n".join(lines), not todo))
        self.map.set_markers("places", entries)
        player = self.snap.player if self.snap else None
        if player and player[2] > INTERIOR_Z:
            # Les intérieurs sont placés en altitude : on garde la dernière position extérieure
            player = self.last_outdoor
            self.map.player.setToolTip("CJ est dans un intérieur (dernière position extérieure)")
        else:
            self.last_outdoor = player or self.last_outdoor
            self.map.player.setToolTip("CJ")
        self.map.set_player(player)

    # ======================================================= Actions
    def apply_filter(self):
        text = self.search.text().strip().lower()
        hide_done = self.chk_hide_done.isChecked()
        show_bonus = self.chk_bonus.isChecked()
        by_id = {it.id: it for it in self.items}
        for cat in self.cats:
            cnode = self.cat_nodes[cat.id]
            any_visible = False
            for gi in range(cnode.childCount()):
                child = cnode.child(gi)
                nodes = [child.child(k) for k in range(child.childCount())] if child.childCount() else [child]
                group_visible = False
                for node in nodes:
                    it = by_id.get(node.data(0, ROLE_ITEM))
                    if not it:
                        continue
                    visible = ((show_bonus or it.required)
                               and not (hide_done and self.effective(it))
                               and (not text or text in it.name.lower()
                                    or text in it.group.lower() or text in cat.name.lower()))
                    node.setHidden(not visible)
                    group_visible |= visible
                child.setHidden(not group_visible)
                any_visible |= group_visible
            cnode.setHidden(not any_visible)
            if text and any_visible:
                cnode.setExpanded(True)

    def on_item_changed(self, node: QTreeWidgetItem, column: int):
        item_id = node.data(0, ROLE_ITEM)
        it = next((i for i in self.items if i.id == item_id), None)
        if not it or column != 0:
            return
        checked = node.checkState(0) == Qt.Checked
        auto = self.auto.get(it.id)
        if checked == bool(auto):
            self.manual.pop(it.id, None)           # retour à la détection auto
        else:
            self.manual[it.id] = checked
        gamefiles.save_json("progress.json", self.manual)
        QTimer.singleShot(0, self.refresh)

    def on_item_clicked(self, node: QTreeWidgetItem, _col: int):
        item_id = node.data(0, ROLE_ITEM)
        it = next((i for i in self.items if i.id == item_id), None)
        if it and self.export_spawns.get(it.id):
            x, y, _z, _src = self.export_spawns[it.id][0]
            self.map.focus_world(x, y)
            self.layer_checks["exports"].setChecked(True)
        elif it and it.pos:
            self.map.focus_world(*it.pos)

    def on_context_menu(self, point):
        node = self.tree.itemAt(point)
        item_id = node.data(0, ROLE_ITEM) if node else None
        if not item_id or item_id not in self.manual:
            return
        menu = QMenu(self)
        act = menu.addAction("Revenir à la détection automatique")
        if menu.exec(self.tree.viewport().mapToGlobal(point)) == act:
            self.manual.pop(item_id, None)
            gamefiles.save_json("progress.json", self.manual)
            self.refresh()

    def on_layer_toggled(self, key: str, on: bool):
        self.map.set_layer_visible(key, on)
        self._save_settings()

    def on_map_done_toggled(self, on: bool):
        self.map.set_show_done(on)
        self._save_settings()

    def use_auto_source(self):
        self.settings["source_mode"] = "auto"
        self._save_settings()
        self.source.configure.emit("auto", "")

    def choose_save(self):
        start = str(gamefiles.saves_dir())
        path, _ = QFileDialog.getOpenFileName(self, "Ouvrir une sauvegarde GTA SA", start,
                                              "Sauvegardes GTA SA (GTASAsf*.b);;Tous (*)")
        if path:
            self.settings["source_mode"] = "save"
            self.settings["save_path"] = path
            self._save_settings()
            self.source.configure.emit("save", path)

    def choose_game_dir(self):
        path = QFileDialog.getExistingDirectory(self, "Dossier d'installation de GTA San Andreas",
                                                self.game_dir or "")
        if not path:
            return
        if not gamefiles.is_game_dir(path):
            QMessageBox.warning(self, APP_NAME, "Ce dossier ne contient pas data/script/main.scm.")
            return
        self.settings["game_dir"] = path
        self._save_settings()
        QMessageBox.information(self, APP_NAME, "Dossier enregistré. Relance l'application pour "
                                                "regénérer la carte et les collectibles.")

    def clear_manual(self):
        if QMessageBox.question(self, APP_NAME, "Effacer toutes les coches manuelles ?") \
                == QMessageBox.Yes:
            self.manual.clear()
            gamefiles.save_json("progress.json", self.manual)
            self.refresh()

    def show_diagnostics(self):
        lines = []
        if not self.snap:
            lines.append("Aucune donnée reçue pour l'instant.")
        else:
            s = self.snap
            lines.append(f"Source : {s.label}")
            for k, v in s.diagnostics.items():
                lines.append(f"  {k} : {v}")
            lines.append("")
            lines.append(f"Variables globales : {len(s.globals_raw) // 4}")
            lines.append(f"Stats : {'oui' if s.stats_int else 'non'}   "
                         f"Progression : {s.progress_percent}")
            lines.append(f"Pickups collectibles présents : "
                         f"{len(s.pickups) if s.pickups is not None else 'non lus'}")
            lines.append(f"Tags : {len(s.tags) if s.tags else 'non lus'}   "
                         f"Sauts : {len(s.stunts) if s.stunts else 'non lus'}")
            lines.append(f"Joueur : {s.player}")
            lines.append("")
            lines.append("Compteurs de missions :")
            counters = {448: "Intro", 452: "Sweet", 453: "Ryder", 454: "Big Smoke", 455: "OG Loc",
                        456: "CRASH LS", 457: "Lowrider", 458: "LS final", 493: "Badlands",
                        491: "Truth", 541: "Garage SF", 542: "Zero", 543: "Woozie", 544: "Wang",
                        545: "Syndicat", 546: "CRASH SF", 593: "Toreno", 597: "Casino",
                        598: "CRASH LV", 599: "Madd Dogg", 600: "Braquage", 626: "Manoir",
                        627: "Grove", 629: "Émeute", 2330: "Courses gagnées"}
            if s.has_globals:
                for var, name in counters.items():
                    lines.append(f"  ${var:<5} {name:<16} = {s.g(var)}")
        lines.append("")
        lines.append("Collectibles connus (main.scm) : " +
                     ", ".join(f"{k} {len(v)}" for k, v in self.known.items()))
        lines.append(f"Spawns d'export : {sum(len(v) for v in self.export_spawns.values())} "
                     f"pour {sum(1 for v in self.export_spawns.values() if v)}/30 véhicules")
        lines.append(f"Positions de tags mémorisées : {sum(1 for p in self.tag_positions if p)}")
        lines.append(f"Dossier des données : {gamefiles.app_dir()}")

        dlg = QDialog(self)
        dlg.setWindowTitle("Diagnostic")
        dlg.resize(640, 640)
        lay = QVBoxLayout(dlg)
        txt = QPlainTextEdit("\n".join(lines))
        txt.setReadOnly(True)
        txt.setFont(QFont("Consolas", 9))
        lay.addWidget(txt)
        buttons = QDialogButtonBox(QDialogButtonBox.Close)
        buttons.rejected.connect(dlg.reject)
        btn_copy = buttons.addButton("Copier", QDialogButtonBox.ActionRole)
        btn_copy.clicked.connect(lambda: QApplication.clipboard().setText(txt.toPlainText()))
        lay.addWidget(buttons)
        dlg.exec()

    def show_about(self):
        QMessageBox.about(self, APP_NAME, (
            f"<b>{APP_NAME} {__version__}</b><br><br>"
            "Checklist du 100 % de GTA San Andreas.<br>"
            "Lit la mémoire du jeu en direct (lecture seule) ou, si le jeu n'est pas lancé, "
            "la dernière sauvegarde.<br><br>"
            "La carte et les positions des collectibles sont extraites de tes fichiers de jeu.<br>"
            "Positions des contacts de mission : approximatives."))

    def _save_settings(self):
        self.settings["hide_done"] = self.chk_hide_done.isChecked()
        self.settings["show_bonus"] = self.chk_bonus.isChecked()
        self.settings["map_show_done"] = self.chk_map_done.isChecked()
        self.settings["hidden_layers"] = [k for k, cb in self.layer_checks.items() if not cb.isChecked()]
        stored = gamefiles.load_json("settings.json", {})
        stored.update(self.settings)
        gamefiles.save_json("settings.json", stored)

    def closeEvent(self, event):
        self._save_settings()
        self.source.stop()
        super().closeEvent(event)
