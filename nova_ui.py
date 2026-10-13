
import math

from PySide6.QtCore import Qt, QTimer, Signal, QPoint
from PySide6.QtGui import (
    QColor, QPainter, QPen, QBrush, QFont, QRadialGradient
)
from PySide6.QtWidgets import (
    QApplication,
    QMainWindow,
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QPushButton,
    QLabel,
    QFrame,
    QSizePolicy,
    QInputDialog,
    QLineEdit,
    QStackedWidget,
    QScrollArea,
)

from memory_system.memory_window import MemoryWindow


class OrbWidget(QWidget):
    clicked = Signal()

    def __init__(self, large=False, parent=None):
        super().__init__(parent)

        self.large = large
        self.active = False
        self.speaking = False
        self.listening = False
        self.status = "WAITING FOR NOVA"

        self.audio_level = 0.0
        self.target_audio_level = 0.0
        self.phase = 0.0
        self.orbit_phase = 0.0

        self._drag_position = None
        self._dragged = False

        if large:
            self.setMinimumSize(420, 440)
            self.setSizePolicy(
                QSizePolicy.Policy.Expanding,
                QSizePolicy.Policy.Expanding,
            )
        else:
            self.setFixedSize(189, 189)
            self.setWindowFlags(
                Qt.WindowType.FramelessWindowHint
                | Qt.WindowType.WindowStaysOnTopHint
                | Qt.WindowType.Tool
            )
            self.setAttribute(
                Qt.WidgetAttribute.WA_TranslucentBackground
            )

        self.setCursor(Qt.CursorShape.PointingHandCursor)

        self.timer = QTimer(self)
        self.timer.timeout.connect(self.animate)
        self.timer.start(16)

    def animate(self):
        self.orbit_phase += 0.025

        if self.speaking:
            self.phase += 0.085
            self.audio_level += (
                self.target_audio_level - self.audio_level
            ) * 0.32
        else:
            self.audio_level += (0.0 - self.audio_level) * 0.35
            if self.audio_level < 0.005:
                self.audio_level = 0.0

        self.update()

    def set_status(self, status):
        self.status = str(status).strip().upper()
        normalized = self.status.lower()

        listening_phrases = (
            "say your command",
            "listening for answer",
            "waiting for command",
            "listening",
            "명령 대기",
            "사용자 음성",
        )

        thinking_phrases = (
            "thinking",
            "processing",
            "searching",
            "생각",
            "검색",
            "처리",
        )

        self.listening = any(
            phrase in normalized for phrase in listening_phrases
        )

        self.active = (
            not self.listening
            and any(
                phrase in normalized
                for phrase in thinking_phrases
            )
        )

        self.update()

    def set_active(self, active):
        self.active = bool(active)
        self.update()

    def set_speaking(self, speaking):
        self.speaking = bool(speaking)
        if not self.speaking:
            self.target_audio_level = 0.0
        self.update()

    def set_audio_level(self, level):
        try:
            level = float(level)
        except (TypeError, ValueError):
            return

        self.target_audio_level = (
            max(0.0, min(1.0, level))
            if self.speaking else 0.0
        )

    def get_orb_colors(self):
        if self.listening:
            return {
                "ring": QColor(255, 145, 35),
                "bright": QColor(255, 190, 85),
                "glow": QColor(255, 105, 15),
                "core": QColor(75, 32, 8),
                "text": QColor(255, 220, 175),
            }

        return {
            "ring": QColor(35, 190, 255),
            "bright": QColor(80, 225, 255),
            "glow": QColor(0, 130, 255),
            "core": QColor(3, 23, 58),
            "text": QColor(210, 250, 255),
        }

    def mousePressEvent(self, event):
        if (
            not self.large
            and event.button() == Qt.MouseButton.LeftButton
        ):
            self._dragged = False
            self._drag_position = (
                event.globalPosition().toPoint()
                - self.frameGeometry().topLeft()
            )
            event.accept()

    def mouseMoveEvent(self, event):
        if (
            not self.large
            and self._drag_position is not None
            and event.buttons() & Qt.MouseButton.LeftButton
        ):
            current = event.globalPosition().toPoint()
            if (
                current
                - (
                    self.frameGeometry().topLeft()
                    + self._drag_position
                )
            ).manhattanLength() > 5:
                self._dragged = True

            if self._dragged:
                self.move(current - self._drag_position)

            event.accept()

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            dragged = self._dragged
            self._drag_position = None
            self._dragged = False

            if not self.large and not dragged:
                self.clicked.emit()

            event.accept()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        width = self.width()
        height = self.height()
        cx = width / 2
        cy = height / 2

        colors = self.get_orb_colors()
        ring_color = colors["ring"]
        bright_color = colors["bright"]
        glow_color = colors["glow"]
        core_color = colors["core"]
        text_color = colors["text"]

        size = min(width, height)
        core_radius = size * (0.105 if self.large else 0.145)
        ring_radius = size * (0.205 if self.large else 0.225)
        max_bar_length = size * (0.055 if self.large else 0.060)
        max_radius = size * 0.43

        level = self.audio_level if self.speaking else 0.0
        pulse = (
            math.sin(self.phase * 2) * 0.5 + 0.5
            if self.speaking else 0.0
        )

        for index in range(4):
            radius = ring_radius + index * size * 0.035
            if radius > max_radius:
                continue

            alpha = (
                max(22, 100 - index * 20)
                if self.speaking
                else max(15, 55 - index * 10)
            )

            color = QColor(ring_color)
            color.setAlpha(alpha)
            painter.setPen(QPen(color, 1.2 if index == 0 else 0.8))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawEllipse(
                QPoint(int(cx), int(cy)),
                int(radius),
                int(radius),
            )

        painter.save()
        painter.translate(cx, cy)

        for ring_index in range(3):
            radius = ring_radius + size * (
                0.035 + ring_index * 0.035
            )
            if radius > max_radius:
                continue

            painter.save()
            speed = 12 if ring_index % 2 == 0 else -9
            painter.rotate(
                self.orbit_phase * speed * (ring_index + 1)
            )

            alpha = (
                125 - ring_index * 25
                if self.speaking
                else 45 - ring_index * 10
            )

            color = QColor(bright_color)
            color.setAlpha(max(12, alpha))
            painter.setPen(
                QPen(color, 2 if ring_index == 0 else 1)
            )

            arc_count = 12 + ring_index * 4
            arc_span = 360 / arc_count

            for i in range(arc_count):
                if i % 3 == 0:
                    continue

                painter.drawArc(
                    int(-radius),
                    int(-radius),
                    int(radius * 2),
                    int(radius * 2),
                    int(i * arc_span * 16),
                    int(arc_span * 0.58 * 16),
                )

            painter.restore()

        painter.restore()

        for index in range(72):
            angle = (
                2 * math.pi * index / 72
                + self.phase * 0.12
            )

            wave = (
                math.sin(index * 0.73 + self.phase * 2.2)
                + math.sin(index * 0.29 - self.phase * 1.4)
            ) * 0.5

            motion = (
                level * (0.30 + 0.70 * abs(wave))
                if self.speaking else 0.0
            )

            bar_length = max_bar_length * motion
            inner = ring_radius + size * 0.015
            outer = min(inner + bar_length, max_radius)

            x1 = cx + math.cos(angle) * inner
            y1 = cy + math.sin(angle) * inner
            x2 = cx + math.cos(angle) * outer
            y2 = cy + math.sin(angle) * outer

            brightness = (
                int(max(90, min(255, 150 + level * 105)))
                if self.speaking else 90
            )

            color = QColor(bright_color)
            color.setAlpha(brightness)

            painter.setPen(
                QPen(
                    color,
                    2.0 if index % 3 == 0 else 1.2,
                    Qt.PenStyle.SolidLine,
                    Qt.PenCapStyle.RoundCap,
                )
            )

            painter.drawLine(
                int(x1), int(y1), int(x2), int(y2)
            )

        glow_radius = core_radius * (
            1.35 + level * 0.25 + pulse * 0.12
        )

        gradient = QRadialGradient(cx, cy, glow_radius)

        glow_center = QColor(glow_color)
        glow_center.setAlpha(110 if self.speaking else 75)

        glow_middle = QColor(glow_color)
        glow_middle.setAlpha(65 if self.speaking else 40)

        glow_edge = QColor(glow_color)
        glow_edge.setAlpha(0)

        gradient.setColorAt(0.0, glow_center)
        gradient.setColorAt(0.45, glow_middle)
        gradient.setColorAt(1.0, glow_edge)

        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(gradient))
        painter.drawEllipse(
            QPoint(int(cx), int(cy)),
            int(glow_radius),
            int(glow_radius),
        )

        border_color = QColor(bright_color)
        border_color.setAlpha(230)

        fill_color = QColor(core_color)
        fill_color.setAlpha(235)

        painter.setPen(QPen(border_color, 1.5))
        painter.setBrush(fill_color)
        painter.drawEllipse(
            QPoint(int(cx), int(cy)),
            int(core_radius),
            int(core_radius),
        )

        for index in range(3):
            radius = core_radius * (0.25 + index * 0.23)
            color = QColor(bright_color)
            color.setAlpha(210 - index * 45)
            painter.setPen(QPen(color, 1))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawEllipse(
                QPoint(int(cx), int(cy)),
                int(radius),
                int(radius),
            )

        painter.setPen(text_color)
        font_size = (
            max(12, int(size * 0.035))
            if self.large else 10
        )

        font = QFont("Segoe UI", font_size)
        font.setBold(True)
        font.setLetterSpacing(
            QFont.SpacingType.AbsoluteSpacing,
            1.5 if self.large else 0.7,
        )
        painter.setFont(font)

        painter.drawText(
            0,
            int(cy - core_radius * 0.45),
            width,
            int(core_radius * 0.9),
            Qt.AlignmentFlag.AlignCenter,
            "NOVA",
        )

        status_color = QColor(bright_color)
        status_color.setAlpha(225)
        painter.setPen(status_color)

        painter.setFont(
            QFont("Consolas", 10 if self.large else 8)
        )

        if self.speaking:
            display_status = "SPEAKING"
        elif self.listening:
            display_status = "LISTENING"
        elif self.active:
            display_status = "THINKING"
        else:
            display_status = "SYSTEM READY"

        label_y = min(
            height - 8,
            int(cy + max_radius + size * 0.045),
        )

        painter.drawText(
            0,
            label_y - 15,
            width,
            20,
            Qt.AlignmentFlag.AlignHCenter,
            display_status,
        )

        painter.end()


class NOVAWindow(QMainWindow):
    search_requested = Signal(str)
    text_submitted = Signal(str)
    minimized_to_orb = Signal()

    def __init__(self):
        super().__init__()

        self._switching_to_orb = False
        self.memory_page = None
        self.memory_file = None
        self.memory_provider = None

        self.setWindowTitle("NOVA // AI SYSTEM")
        self.resize(1000, 760)
        self.setMinimumSize(700, 600)

        self.setStyleSheet("""
            QMainWindow, QWidget {
                background-color: #050b16;
                color: #d7f5ff;
                font-family: 'Segoe UI';
            }

            QFrame#panel {
                background-color: #071222;
                border: 1px solid #12364d;
                border-radius: 16px;
            }

            QLabel#brand {
                color: #61e3ff;
                font-size: 22pt;
                font-weight: bold;
            }

            QLabel#subtitle {
                color: #518ba7;
                font-size: 9pt;
                letter-spacing: 3px;
            }

            QLabel#statusLabel {
                color: #5ce3ff;
                background-color: #0a1c2b;
                border: 1px solid #16445c;
                border-radius: 7px;
                padding: 9px;
            }

            QPushButton {
                background-color: #0c3045;
                color: #9cecff;
                border: 1px solid #1c6786;
                border-radius: 8px;
                padding: 11px 16px;
            }

            QPushButton:hover {
                background-color: #10445e;
                border-color: #50dfff;
            }

            QPushButton:disabled {
                color: #52778a;
                border-color: #18394a;
                background-color: #0a1a28;
            }

            QLineEdit {
                background-color: #081827;
                color: #d7f5ff;
                border: 1px solid #1c6786;
                border-radius: 9px;
                padding: 12px;
                selection-background-color: #14749a;
            }

            QLineEdit:focus {
                border: 1px solid #50dfff;
            }
        """)

        self.build_ui()

    def build_ui(self):
        root = QWidget()
        self.setCentralWidget(root)

        outer_layout = QVBoxLayout(root)
        outer_layout.setContentsMargins(18, 16, 18, 16)
        outer_layout.setSpacing(0)

        self.stack = QStackedWidget()
        outer_layout.addWidget(self.stack)

        # Home page
        self.home_page = QWidget()
        layout = QVBoxLayout(self.home_page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)

        brand = QLabel("NOVA CORE")
        brand.setObjectName("brand")
        brand.setAlignment(Qt.AlignmentFlag.AlignCenter)

        subtitle = QLabel("VOICE-OPERATED PERSONAL AI")
        subtitle.setObjectName("subtitle")
        subtitle.setAlignment(Qt.AlignmentFlag.AlignCenter)

        layout.addWidget(brand)
        layout.addWidget(subtitle)

        self.status_label = QLabel("INITIALIZING")
        self.status_label.setObjectName("statusLabel")
        self.status_label.setAlignment(
            Qt.AlignmentFlag.AlignCenter
        )
        layout.addWidget(self.status_label)

        input_row = QHBoxLayout()
        input_row.setSpacing(8)

        self.message_input = QLineEdit()
        self.message_input.setPlaceholderText("Message NOVA...")
        self.message_input.setClearButtonEnabled(True)
        self.message_input.returnPressed.connect(self.submit_text)

        self.send_button = QPushButton("SEND")
        self.send_button.setMinimumWidth(92)
        self.send_button.clicked.connect(self.submit_text)

        input_row.addWidget(self.message_input, 1)
        input_row.addWidget(self.send_button)
        layout.addLayout(input_row)

        buttons = QHBoxLayout()

        self.search_button = QPushButton("WEB SEARCH")
        self.search_button.clicked.connect(self.ask_search)

        self.memory_button = QPushButton("MEMORY ARCHIVE")
        self.memory_button.clicked.connect(self.show_memory_archive)

        self.minimize_button = QPushButton("MINIMIZE TO HOLOGRAM")
        self.minimize_button.clicked.connect(self._switch_to_small_orb)

        buttons.addWidget(self.search_button)
        buttons.addWidget(self.memory_button)
        buttons.addWidget(self.minimize_button)

        layout.addLayout(buttons)

        footer = QLabel("NOVA  //  GEMINI + GOOGLE SEARCH")
        footer.setAlignment(Qt.AlignmentFlag.AlignCenter)
        footer.setStyleSheet(
            "color: #416a80; font-size: 8pt; letter-spacing: 1px;"
        )
        layout.addWidget(footer)

        self.stack.addWidget(self.home_page)

    # --------------------------------------------------
    # Memory archive
    # --------------------------------------------------

    def set_memory_archive(self, memory_file=None, memory_provider=None):
        self.memory_file = memory_file
        self.memory_provider = memory_provider

        if self.memory_page is not None:
            self.stack.removeWidget(self.memory_page)
            self.memory_page.deleteLater()
            self.memory_page = None

        page = QWidget()
        page_layout = QVBoxLayout(page)
        page_layout.setContentsMargins(0, 0, 0, 0)
        page_layout.setSpacing(8)

        toolbar = QHBoxLayout()

        title = QLabel("NOVA // MEMORY ARCHIVE")
        title.setStyleSheet(
            "color: #61e3ff; font-size: 16pt; font-weight: bold;"
        )

        back_button = QPushButton("BACK TO NOVA")
        back_button.clicked.connect(self.show_home)

        toolbar.addWidget(title)
        toolbar.addStretch(1)
        toolbar.addWidget(back_button)

        page_layout.addLayout(toolbar)

        self.memory_page = MemoryWindow(
            memory_file=memory_file,
            memory_provider=memory_provider,
            parent=page,
        )

        page_layout.addWidget(self.memory_page, 1)

        self.stack.addWidget(page)

    def show_memory_archive(self):
        if self.memory_page is None:
            self.set_memory_archive(
                memory_file=self.memory_file,
                memory_provider=self.memory_provider,
            )

        self.memory_page.refresh_memory()
        self.stack.setCurrentWidget(self.memory_page.parentWidget())

    def show_home(self):
        self.stack.setCurrentWidget(self.home_page)

    # --------------------------------------------------
    # Text input and search
    # --------------------------------------------------

    def submit_text(self):
        text = self.message_input.text().strip()
        if not text:
            return

        self.message_input.clear()
        self.text_submitted.emit(text)

    def set_input_enabled(self, enabled):
        enabled = bool(enabled)
        self.message_input.setEnabled(enabled)
        self.send_button.setEnabled(enabled)

    def ask_search(self):
        query, accepted = QInputDialog.getText(
            self,
            "NOVA Web Search",
            "What should NOVA search for?",
        )

        if accepted and query.strip():
            self.search_requested.emit(query.strip())

    # --------------------------------------------------
    # Status and animation controls
    # --------------------------------------------------

    def set_status(self, text):
        self.status_label.setText(str(text).strip().upper())

    def set_speaking(self, speaking):
        pass

    def set_audio_level(self, level):
        pass

    # --------------------------------------------------
    # Minimize to floating hologram
    # --------------------------------------------------

    def _switch_to_small_orb(self):
        if self._switching_to_orb:
            return

        self._switching_to_orb = True
        self.hide()
        self.minimized_to_orb.emit()

        QTimer.singleShot(250, self._reset_switch_flag)

    def _reset_switch_flag(self):
        self._switching_to_orb = False

    def closeEvent(self, event):
        event.accept()
        QApplication.quit()
