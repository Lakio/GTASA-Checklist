"""Carte interactive : fond radar du jeu + marqueurs (collectibles, lieux, joueur)."""

import html
import math

from PySide6.QtCore import QPoint, QPointF, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import (QBrush, QColor, QPainter, QPainterPath, QPen, QPixmap,
                           QPolygonF)
from PySide6.QtWidgets import (QGraphicsEllipseItem, QGraphicsItem, QGraphicsPathItem,
                               QGraphicsPixmapItem, QGraphicsScene, QGraphicsView, QLabel)

from .gamefiles import map_to_world, world_to_map

LAYERS = {
    # id: (libellé, couleur, rayon en px)
    "places": ("Missions & activités", "#e74c3c", 7),
    "tags": ("Tags", "#2ecc71", 5),
    "snapshots": ("Photos", "#e84393", 5),
    "horseshoes": ("Fers à cheval", "#f1c40f", 5),
    "oysters": ("Huîtres", "#00cec9", 5),
    "stunts": ("Sauts uniques", "#e67e22", 5),
}
DONE_COLOR = QColor(120, 120, 120)


def rich_text(layer: str, text: str) -> str:
    """Titre = nom du calque, puis le détail (une ligne par ligne de texte)."""
    label, color, _r = LAYERS[layer]
    lines = [html.escape(line) for line in text.splitlines()]
    body = lines[0] and f"<b>{lines[0]}</b>"
    rest = "<br>".join(lines[1:])
    return (f'<span style="color:{color}">●</span> <span style="color:#9aa4b2">{html.escape(label)}</span>'
            f"<br>{body}" + (f"<br>{rest}" if rest else ""))


class Marker(QGraphicsEllipseItem):
    """Point de taille fixe à l'écran, quel que soit le zoom."""

    def __init__(self, layer: str, x: float, y: float, tooltip: str, done: bool | None):
        _, color, radius = LAYERS[layer]
        self.info = rich_text(layer, tooltip)
        r = radius if done is not True else radius * 0.7
        super().__init__(-r, -r, 2 * r, 2 * r)
        self.layer = layer
        self.done = done
        self.world = (x, y)
        self.setFlag(QGraphicsItem.ItemIgnoresTransformations)
        fill = QColor(color) if done is not True else DONE_COLOR
        if done is True:
            fill.setAlpha(150)
        self.setBrush(QBrush(fill))
        pen = QPen(QColor("white") if done is None else QColor(20, 20, 20, 200))
        pen.setWidthF(1.6 if done is None else 1.0)
        if done is None:
            pen.setStyle(Qt.DashLine)
        self.setPen(pen)
        self.setToolTip(self.info)
        self.setZValue(10 if done is not True else 5)
        self.setAcceptHoverEvents(True)

    def hoverEnterEvent(self, event):
        self.setScale(1.5)
        super().hoverEnterEvent(event)

    def hoverLeaveEvent(self, event):
        self.setScale(1.0)
        super().hoverLeaveEvent(event)


class PlayerArrow(QGraphicsPathItem):
    def __init__(self):
        path = QPainterPath()
        path.addPolygon(QPolygonF([QPointF(0, -13), QPointF(9, 10), QPointF(0, 5), QPointF(-9, 10),
                                   QPointF(0, -13)]))
        super().__init__(path)
        self.setFlag(QGraphicsItem.ItemIgnoresTransformations)
        self.setBrush(QBrush(QColor("#3498db")))
        pen = QPen(QColor("white"))
        pen.setWidthF(2)
        self.setPen(pen)
        self.setZValue(100)
        self.setToolTip("CJ")


class MapView(QGraphicsView):
    coordsHovered = Signal(float, float)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setScene(QGraphicsScene(self))
        self.setRenderHints(QPainter.Antialiasing | QPainter.SmoothPixmapTransform)
        self.setDragMode(QGraphicsView.ScrollHandDrag)
        self.setTransformationAnchor(QGraphicsView.AnchorUnderMouse)
        self.setViewportUpdateMode(QGraphicsView.SmartViewportUpdate)
        self.setBackgroundBrush(QColor(98, 132, 166))
        self.setMouseTracking(True)
        self.map_size = 1536.0
        self.markers: dict[str, list[Marker]] = {k: [] for k in LAYERS}
        self.visible_layers = set(LAYERS)
        self.show_done = True
        self.follow_player = False
        self.player = PlayerArrow()
        self.player.setVisible(False)
        self.scene().addItem(self.player)
        self._highlight = QGraphicsEllipseItem(-16, -16, 32, 32)
        self._highlight.setFlag(QGraphicsItem.ItemIgnoresTransformations)
        hl_pen = QPen(QColor("#ffffff"))
        hl_pen.setWidthF(3)
        self._highlight.setPen(hl_pen)
        self._highlight.setZValue(90)
        self._highlight.setVisible(False)
        self.scene().addItem(self._highlight)
        self._hl_timer = QTimer(self)
        self._hl_timer.setSingleShot(True)
        self._hl_timer.timeout.connect(lambda: self._highlight.setVisible(False))
        self._fitted = False
        self._entries: dict[str, list] = {k: [] for k in LAYERS}
        self._selected: tuple[str, int] | None = None
        self._press_pos = None
        # enfant de la vue (pas du viewport) : sinon il défile avec la carte
        self.info = QLabel(self)
        self.info.setTextFormat(Qt.RichText)
        self.info.setWordWrap(True)
        self.info.setMaximumWidth(360)
        self.info.setStyleSheet("QLabel { background: rgba(22, 25, 29, 235); color: #e6e6e6; "
                                "border: 1px solid #3a4049; border-radius: 6px; padding: 8px 10px; }")
        self.info.hide()

    # -- Fond ----------------------------------------------------------
    def set_background(self, path: str | None):
        pix = QPixmap(path) if path else QPixmap()
        if pix.isNull():
            self.map_size = 1536.0
            self._draw_grid()
        else:
            self.map_size = float(pix.width())
            item = QGraphicsPixmapItem(pix)
            item.setTransformationMode(Qt.SmoothTransformation)
            item.setZValue(-10)
            self.scene().addItem(item)
        self.scene().setSceneRect(QRectF(0, 0, self.map_size, self.map_size))

    def _draw_grid(self):
        pen = QPen(QColor(255, 255, 255, 60))
        step = self.map_size / 12
        for i in range(13):
            self.scene().addLine(i * step, 0, i * step, self.map_size, pen)
            self.scene().addLine(0, i * step, self.map_size, i * step, pen)

    def to_scene(self, x: float, y: float) -> QPointF:
        return QPointF(*world_to_map(x, y, self.map_size))

    # -- Marqueurs -----------------------------------------------------
    def set_markers(self, layer: str, entries: list[tuple[float, float, str, bool | None]]):
        if entries == self._entries[layer]:
            return                      # rien n'a changé : garder les points (infobulles stables)
        self._entries[layer] = list(entries)
        for m in self.markers[layer]:
            self.scene().removeItem(m)
        self.markers[layer] = []
        for x, y, tip, done in entries:
            m = Marker(layer, x, y, tip, done)
            m.setPos(self.to_scene(x, y))
            self.scene().addItem(m)
            self.markers[layer].append(m)
        self._apply_visibility(layer)
        if self._selected and self._selected[0] == layer:
            idx = self._selected[1]
            if idx < len(self.markers[layer]):
                self._show_info(self.markers[layer][idx])
            else:
                self._hide_info()

    def set_layer_visible(self, layer: str, visible: bool):
        (self.visible_layers.add if visible else self.visible_layers.discard)(layer)
        self._apply_visibility(layer)

    def set_show_done(self, show: bool):
        self.show_done = show
        for layer in LAYERS:
            self._apply_visibility(layer)

    def _apply_visibility(self, layer: str):
        on = layer in self.visible_layers
        for m in self.markers[layer]:
            m.setVisible(on and (self.show_done or m.done is not True))

    def set_player(self, player):
        if not player:
            self.player.setVisible(False)
            return
        x, y, _z, heading = player
        self.player.setPos(self.to_scene(x, y))
        self.player.setRotation(-math.degrees(heading))
        self.player.setVisible(True)
        if self.follow_player:
            self.centerOn(self.player)

    def center_on_player(self):
        if self.player.isVisible():
            self.centerOn(self.player)

    def focus_world(self, x: float, y: float, zoom: float = 3.0):
        pt = self.to_scene(x, y)
        current = self.transform().m11()
        target = zoom * self._fit_scale()
        if current < target:
            self.scale(target / current, target / current)
        self.centerOn(pt)
        self._highlight.setPos(pt)
        self._highlight.setVisible(True)
        self._hl_timer.start(2500)

    # -- Zoom / navigation ---------------------------------------------
    def _fit_scale(self) -> float:
        vp = self.viewport().rect()
        return min(vp.width(), vp.height()) / self.map_size if self.map_size else 1.0

    def fit(self):
        self.resetTransform()
        s = self._fit_scale()
        self.scale(s, s)
        self.centerOn(self.map_size / 2, self.map_size / 2)

    def showEvent(self, event):
        super().showEvent(event)
        if not self._fitted:
            self._fitted = True
            QTimer.singleShot(0, self.fit)

    def wheelEvent(self, event):
        factor = 1.25 if event.angleDelta().y() > 0 else 0.8
        current = self.transform().m11()
        fit = self._fit_scale()
        new = max(fit * 0.8, min(current * factor, fit * 40))
        self.scale(new / current, new / current)

    # -- Clic sur un point : panneau d'info ------------------------------
    def _marker_at(self, pos):
        for item in self.items(pos):
            if isinstance(item, (Marker, PlayerArrow)) and item.isVisible():
                return item
        return None

    def _show_info(self, item):
        if isinstance(item, Marker):
            self._selected = (item.layer, self.markers[item.layer].index(item))
            self.info.setText(item.info)
            self._highlight.setPos(item.pos())
            self._highlight.setVisible(True)
            self._hl_timer.stop()
        else:
            self._selected = None
            self.info.setText(f"<b>CJ</b><br>{html.escape(item.toolTip())}")
        self.info.adjustSize()
        self.info.move(self.viewport().geometry().topLeft() + QPoint(10, 10))
        self.info.show()
        self.info.raise_()

    def _hide_info(self):
        self._selected = None
        self.info.hide()
        self._highlight.setVisible(False)

    def mousePressEvent(self, event):
        self._press_pos = event.position().toPoint()
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event):
        super().mouseReleaseEvent(event)
        pos = event.position().toPoint()
        if self._press_pos is None or (pos - self._press_pos).manhattanLength() > 4:
            return                      # c'était un déplacement de la carte
        item = self._marker_at(pos)
        if item:
            self._show_info(item)
        else:
            self._hide_info()

    def mouseMoveEvent(self, event):
        super().mouseMoveEvent(event)
        p = self.mapToScene(event.position().toPoint())
        self.coordsHovered.emit(*map_to_world(p.x(), p.y(), self.map_size))
