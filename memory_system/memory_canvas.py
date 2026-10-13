"""Interactive neon folder/card canvas for NOVA's memory viewer."""

from __future__ import annotations

from PySide6.QtCore import Qt, QRectF, QPointF, Signal
from PySide6.QtGui import QColor, QFont, QPainter, QPen, QLinearGradient, QBrush
from PySide6.QtWidgets import QWidget


BG = QColor("#07111D")
CYAN = QColor("#55E7FF")
BLUE = QColor("#4D8DFF")
TEXT = QColor("#DDF8FF")
MUTED = QColor("#82A9BA")
PANEL = QColor("#0B1D2C")


class MemoryCanvas(QWidget):
    """Painted canvas. Pointer events are deliberately kept independent of UI logic.

    A future MediaPipe adapter can call `pointer_press`, `pointer_move`, and
    `pointer_release` with canvas-local coordinates to reuse the same behavior.
    """
    category_selected = Signal(str)
    memory_selected = Signal(object)
    back_requested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumSize(420, 360)
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.mode = "folders"
        self.categories: list[dict] = []
        self.memories: list[dict] = []
        self.current_category = ""
        self.folder_rects: list[tuple[QRectF, dict]] = []
        self.card_rects: list[tuple[QRectF, dict]] = []
        self.card_positions: dict[str, QPointF] = {}
        self.selected_id: str | None = None
        self._pressed_id: str | None = None
        self._press_pos = QPointF()
        self._drag_offset = QPointF()
        self._dragging = False
        self._hover_pos = QPointF(-1, -1)

    def set_categories(self, categories: list[dict]):
        self.categories = list(categories)
        self.update()

    def show_folders(self):
        self.mode = "folders"
        self.current_category = ""
        self.memories = []
        self.selected_id = None
        self._pressed_id = None
        self.update()

    def show_cards(self, category: str, memories: list[dict]):
        self.mode = "cards"
        self.current_category = category
        self.memories = list(memories)
        self.selected_id = None
        self._pressed_id = None
        self.card_positions.clear()
        self.update()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.fillRect(self.rect(), BG)
        self._draw_grid(painter)
        self._draw_header(painter)
        if self.mode == "folders":
            self._draw_folders(painter)
        else:
            self._draw_cards(painter)
        painter.end()

    def _draw_grid(self, p: QPainter):
        p.save()
        pen = QPen(QColor(45, 123, 151, 32), 1)
        p.setPen(pen)
        step = 28
        for x in range(0, self.width(), step):
            p.drawLine(x, 0, x, self.height())
        for y in range(0, self.height(), step):
            p.drawLine(0, y, self.width(), y)
        p.restore()

    def _draw_header(self, p: QPainter):
        p.save()
        p.setPen(CYAN)
        p.setFont(QFont("Consolas", 10, QFont.Weight.Bold))
        title = "NOVA  /  MEMORY ARCHIVE"
        p.drawText(QRectF(22, 14, self.width() - 44, 24), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, title)
        p.setPen(QPen(QColor(85, 231, 255, 100), 1))
        p.drawLine(22, 43, self.width() - 22, 43)
        if self.mode == "cards":
            back = QRectF(22, 54, 94, 28)
            p.setBrush(QColor(17, 49, 67, 230))
            p.setPen(QPen(CYAN, 1))
            p.drawRoundedRect(back, 7, 7)
            p.setPen(TEXT)
            p.setFont(QFont("Segoe UI", 9, QFont.Weight.DemiBold))
            p.drawText(back, Qt.AlignmentFlag.AlignCenter, "‹  FOLDERS")
            label = next((c["label"] for c in self.categories if c["id"] == self.current_category), self.current_category.title())
            p.setPen(TEXT)
            p.setFont(QFont("Segoe UI", 13, QFont.Weight.DemiBold))
            p.drawText(QRectF(130, 54, self.width() - 150, 28), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, label.upper())
        else:
            p.setPen(MUTED)
            p.setFont(QFont("Segoe UI", 9))
            p.drawText(QRectF(22, 48, self.width() - 44, 22), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                       "SELECT A FOLDER TO EXPLORE SAVED MEMORIES")
        p.restore()

    def _draw_folders(self, p: QPainter):
        self.folder_rects.clear()
        items = self.categories
        if not items:
            p.setPen(MUTED)
            p.setFont(QFont("Segoe UI", 11))
            p.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, "No memory categories found")
            return
        margin = 22
        top = 84
        gap_x, gap_y = 16, 16
        cols = 2 if self.width() < 760 else 3
        card_w = max(120.0, (self.width() - margin * 2 - gap_x * (cols - 1)) / cols)
        card_h = 112.0
        for index, item in enumerate(items):
            row, col = divmod(index, cols)
            rect = QRectF(margin + col * (card_w + gap_x), top + row * (card_h + gap_y), card_w, card_h)
            self.folder_rects.append((rect, item))
            hovered = rect.contains(self._hover_pos)
            self._draw_folder(p, rect, item, hovered)

    def _draw_folder(self, p: QPainter, rect: QRectF, item: dict, hovered: bool):
        p.save()
        fill = QColor("#102A3A") if hovered else QColor("#0A1C2A")
        p.setBrush(QBrush(fill))
        p.setPen(QPen(CYAN if hovered else QColor(62, 156, 181, 150), 1.3))
        p.drawRoundedRect(rect, 10, 10)
        # Stylised folder tab and outline.
        x, y = rect.x() + 16, rect.y() + 15
        folder = QRectF(x, y + 7, 38, 25)
        tab = QRectF(x + 2, y, 17, 10)
        p.setBrush(QColor(32, 113, 140, 110))
        p.setPen(QPen(CYAN, 1.2))
        p.drawRoundedRect(tab, 3, 3)
        p.drawRoundedRect(folder, 4, 4)
        p.setPen(TEXT)
        p.setFont(QFont("Segoe UI", 10, QFont.Weight.DemiBold))
        p.drawText(QRectF(rect.x() + 16, rect.y() + 52, rect.width() - 32, 20), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, item["label"])
        p.setPen(MUTED)
        p.setFont(QFont("Segoe UI", 8))
        p.drawText(QRectF(rect.x() + 16, rect.y() + 76, rect.width() - 32, 18), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                   f'{item.get("count", 0)} ITEMS  ·  OPEN FOLDER')
        p.restore()

    def _draw_cards(self, p: QPainter):
        self.card_rects.clear()
        if not self.memories:
            p.setPen(MUTED)
            p.setFont(QFont("Segoe UI", 11))
            p.drawText(QRectF(22, 94, self.width() - 44, self.height() - 110), Qt.AlignmentFlag.AlignCenter,
                       "This folder is empty.\nNew memories saved by NOVA will appear here.")
            return
        margin, top, gap_x, gap_y = 22, 94, 14, 14
        cols = 1 if self.width() < 650 else 2
        card_w = max(180.0, (self.width() - margin * 2 - gap_x * (cols - 1)) / cols)
        card_h = 104.0
        for index, item in enumerate(self.memories):
            row, col = divmod(index, cols)
            default = QPointF(margin + col * (card_w + gap_x), top + row * (card_h + gap_y))
            pos = self.card_positions.get(item["id"], default)
            rect = QRectF(pos.x(), pos.y(), card_w, card_h)
            self.card_positions.setdefault(item["id"], QPointF(pos))
            self.card_rects.append((rect, item))
            hovered = rect.contains(self._hover_pos)
            selected = item["id"] == self.selected_id
            p.save()
            p.setBrush(QColor("#102B3B") if hovered or selected else QColor("#0A1B29"))
            edge = CYAN if selected or hovered else QColor(58, 145, 174, 170)
            p.setPen(QPen(edge, 1.5 if selected else 1.0))
            p.drawRoundedRect(rect, 9, 9)
            p.setPen(QPen(QColor(85, 231, 255, 90), 1))
            p.drawLine(rect.x() + 12, rect.y() + 31, rect.right() - 12, rect.y() + 31)
            p.setPen(CYAN)
            p.setFont(QFont("Segoe UI", 9, QFont.Weight.DemiBold))
            title = item.get("title", "Untitled memory")
            p.drawText(QRectF(rect.x() + 12, rect.y() + 8, rect.width() - 24, 20), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, self._elide(title, 32))
            p.setPen(TEXT)
            p.setFont(QFont("Segoe UI", 8))
            content = item.get("content", "").replace("\n", " ")
            p.drawText(QRectF(rect.x() + 12, rect.y() + 39, rect.width() - 24, 42), Qt.TextFlag.TextWordWrap, self._elide(content, 105))
            p.setPen(MUTED)
            p.setFont(QFont("Consolas", 7))
            p.drawText(QRectF(rect.x() + 12, rect.bottom() - 19, rect.width() - 24, 12), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                       "DRAG TO REPOSITION  ·  CLICK TO INSPECT")
            p.restore()
        # Paint the current card count at the bottom if there is room.
        p.setPen(QColor(130, 169, 186, 150))
        p.setFont(QFont("Consolas", 8))
        p.drawText(QRectF(22, self.height() - 22, self.width() - 44, 14), Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
                   f"{len(self.memories)} MEMORY ITEMS")

    @staticmethod
    def _elide(text: str, limit: int) -> str:
        text = str(text)
        return text if len(text) <= limit else text[:max(0, limit - 1)] + "…"

    def mousePressEvent(self, event):
        if event.button() != Qt.MouseButton.LeftButton:
            return super().mousePressEvent(event)
        self.pointer_press(event.position())

    def mouseMoveEvent(self, event):
        self._hover_pos = event.position()
        if event.buttons() & Qt.MouseButton.LeftButton:
            self.pointer_move(event.position())
        else:
            self.update()
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.pointer_release(event.position())
        super().mouseReleaseEvent(event)

    def pointer_press(self, point: QPointF):
        self._press_pos = QPointF(point)
        self._dragging = False
        if self.mode == "cards":
            for rect, item in reversed(self.card_rects):
                if rect.contains(point):
                    self._pressed_id = item["id"]
                    pos = self.card_positions.get(item["id"], QPointF(rect.x(), rect.y()))
                    self._drag_offset = point - pos
                    return
            if QRectF(22, 54, 94, 28).contains(point):
                self.back_requested.emit()
        else:
            for rect, item in self.folder_rects:
                if rect.contains(point):
                    self.category_selected.emit(item["id"])
                    return

    def pointer_move(self, point: QPointF):
        if not self._pressed_id:
            self._hover_pos = QPointF(point)
            self.update()
            return
        if (point - self._press_pos).manhattanLength() > 5:
            self._dragging = True
        if self._dragging:
            card = next((item for item in self.memories if item["id"] == self._pressed_id), None)
            if card is not None:
                rect = next((r for r, i in self.card_rects if i["id"] == self._pressed_id), QRectF(0, 0, 220, 100))
                x = max(8.0, min(float(self.width()) - rect.width() - 8, point.x() - self._drag_offset.x()))
                y = max(88.0, min(float(self.height()) - rect.height() - 8, point.y() - self._drag_offset.y()))
                self.card_positions[self._pressed_id] = QPointF(x, y)
                self.update()

    def pointer_release(self, point: QPointF):
        if self.mode == "cards" and self._pressed_id:
            item = next((item for item in self.memories if item["id"] == self._pressed_id), None)
            if item is not None and not self._dragging:
                self.selected_id = item["id"]
                self.memory_selected.emit(item)
            self._pressed_id = None
            self._dragging = False
            self._hover_pos = QPointF(point)
            self.update()
