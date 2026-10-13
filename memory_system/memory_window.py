"""Embeddable memory archive panel for NOVA's existing main window."""

from __future__ import annotations

from pathlib import Path
from typing import Callable, Any

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QListWidget,
    QListWidgetItem, QFrame, QTextBrowser, QSizePolicy,
)

from .memory_reader import load_memory
from .memory_cards import build_categories, build_memory_cards
from .memory_canvas import MemoryCanvas


STYLESHEET = """
QWidget#memoryRoot { background: #07111D; color: #DDF8FF; }
QFrame#memorySidebar, QFrame#memoryDetails { background: #091A28; border: 1px solid #17394A; border-radius: 10px; }
QLabel#eyebrow { color: #55E7FF; font: 700 9pt 'Consolas'; }
QLabel#sectionTitle { color: #DDF8FF; font: 600 12pt 'Segoe UI'; }
QLabel#muted { color: #82A9BA; }
QPushButton { background: #102A3A; color: #DDF8FF; border: 1px solid #286177; border-radius: 6px; padding: 7px 10px; }
QPushButton:hover { background: #164056; border-color: #55E7FF; }
QPushButton:checked { background: #164056; border-color: #55E7FF; color: #55E7FF; }
QListWidget { background: transparent; border: none; outline: none; color: #DDF8FF; }
QListWidget::item { padding: 9px 7px; border-radius: 5px; }
QListWidget::item:selected { background: #123449; border: 1px solid #286177; }
QTextBrowser { background: #071521; color: #DDF8FF; border: 1px solid #17394A; border-radius: 7px; padding: 8px; }
"""


class MemoryWindow(QWidget):
    """Memory viewer intended to be inserted into a QMainWindow layout.

    Args:
        memory: Optional live memory dictionary owned by NOVA.
        memory_file: Path to NOVA's existing memory.json.
        memory_provider: Optional callable returning the latest memory dict.
    """

    def __init__(
        self,
        memory: dict[str, Any] | None = None,
        memory_file: str | Path | None = None,
        memory_provider: Callable[[], dict[str, Any] | None] | None = None,
        parent: QWidget | None = None,
    ):
        super().__init__(parent)
        self.setObjectName("memoryRoot")
        self.setMinimumSize(760, 480)
        self.setStyleSheet(STYLESHEET)
        self._memory = memory
        self._memory_file = Path(memory_file) if memory_file else None
        self._memory_provider = memory_provider
        self._data: dict[str, Any] = {}
        self._categories: list[dict] = []
        self._cards: list[dict] = []
        self._selected_category = ""
        self._selected_memory: dict | None = None
        self._build_ui()
        self.refresh_memory()

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(10)

        header = QHBoxLayout()
        title_box = QVBoxLayout()
        eyebrow = QLabel("N O V A   /   LOCAL MEMORY SYSTEM")
        eyebrow.setObjectName("eyebrow")
        title = QLabel("Memory Archive")
        title.setObjectName("sectionTitle")
        subtitle = QLabel("Browse the memories NOVA has saved on this device.")
        subtitle.setObjectName("muted")
        title_box.addWidget(eyebrow)
        title_box.addWidget(title)
        title_box.addWidget(subtitle)
        header.addLayout(title_box, 1)
        self.refresh_button = QPushButton("↻  Refresh")
        self.refresh_button.clicked.connect(self.refresh_memory)
        header.addWidget(self.refresh_button, 0, Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        root.addLayout(header)

        body = QHBoxLayout()
        body.setSpacing(10)

        self.sidebar = QFrame()
        self.sidebar.setObjectName("memorySidebar")
        self.sidebar.setMinimumWidth(150)
        self.sidebar.setMaximumWidth(220)
        side_layout = QVBoxLayout(self.sidebar)
        side_layout.setContentsMargins(10, 12, 10, 10)
        side_layout.addWidget(QLabel("FOLDERS"))
        self.category_list = QListWidget()
        self.category_list.currentItemChanged.connect(self._on_category_list_changed)
        side_layout.addWidget(self.category_list, 1)
        self.item_count_label = QLabel("0 memories")
        self.item_count_label.setObjectName("muted")
        side_layout.addWidget(self.item_count_label)
        body.addWidget(self.sidebar, 0)

        self.canvas = MemoryCanvas()
        self.canvas.category_selected.connect(self.open_category)
        self.canvas.memory_selected.connect(self.show_memory_details)
        self.canvas.back_requested.connect(self.show_all_folders)
        self.canvas.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        body.addWidget(self.canvas, 1)

        self.details = QFrame()
        self.details.setObjectName("memoryDetails")
        self.details.setMinimumWidth(190)
        self.details.setMaximumWidth(290)
        detail_layout = QVBoxLayout(self.details)
        detail_layout.setContentsMargins(12, 12, 12, 12)
        detail_layout.setSpacing(8)
        detail_heading = QLabel("MEMORY DETAILS")
        detail_heading.setObjectName("eyebrow")
        self.detail_title = QLabel("Select a memory")
        self.detail_title.setObjectName("sectionTitle")
        self.detail_title.setWordWrap(True)
        self.detail_category = QLabel("No item selected")
        self.detail_category.setObjectName("muted")
        self.detail_content = QTextBrowser()
        self.detail_content.setOpenExternalLinks(False)
        self.detail_content.setPlaceholderText("Choose a card in the hologram to inspect its content.")
        self.detail_content.setText("Choose a memory card to view its saved content here.")
        detail_layout.addWidget(detail_heading)
        detail_layout.addWidget(self.detail_title)
        detail_layout.addWidget(self.detail_category)
        detail_layout.addWidget(self.detail_content, 1)
        body.addWidget(self.details, 0)

        root.addLayout(body, 1)
        self.status_label = QLabel("LOCAL VIEW · READ ONLY · MEMORY FILE IS NOT MODIFIED")
        self.status_label.setObjectName("muted")
        root.addWidget(self.status_label)

    def refresh_memory(self):
        self._data = load_memory(
            memory_file=self._memory_file,
            memory=self._memory,
            memory_provider=self._memory_provider,
        )
        self._cards = build_memory_cards(self._data)
        self._categories = build_categories(self._data)
        self.canvas.set_categories(self._categories)
        self._populate_category_list()
        self.item_count_label.setText(f"{len(self._cards)} memories")
        load_error = self._data.get("_load_error")
        if load_error:
            self.status_label.setText(f"MEMORY LOAD WARNING · {load_error}")
        else:
            self.status_label.setText(f"LOCAL VIEW · READ ONLY · {len(self._cards)} MEMORY ITEMS")
        self.show_all_folders()

    def _populate_category_list(self):
        self.category_list.blockSignals(True)
        self.category_list.clear()
        for category in self._categories:
            item = QListWidgetItem(f'{category["label"]}   ·   {category["count"]}')
            item.setData(Qt.ItemDataRole.UserRole, category["id"])
            self.category_list.addItem(item)
        self.category_list.blockSignals(False)

    def _on_category_list_changed(self, current, previous=None):
        if current is None:
            return
        category = current.data(Qt.ItemDataRole.UserRole)
        if category:
            self.open_category(category)

    def open_category(self, category: str):
        self._selected_category = category
        matches = [card for card in self._cards if card.get("category") == category]
        self.canvas.show_cards(category, matches)
        self._selected_memory = None
        self.detail_title.setText("Select a memory")
        label = next((c["label"] for c in self._categories if c["id"] == category), category.title())
        self.detail_category.setText(label)
        self.detail_content.setText("Select a card in the hologram to inspect its content.")
        self._sync_category_selection(category)

    def _sync_category_selection(self, category: str):
        self.category_list.blockSignals(True)
        for index in range(self.category_list.count()):
            item = self.category_list.item(index)
            if item.data(Qt.ItemDataRole.UserRole) == category:
                self.category_list.setCurrentItem(item)
                break
        self.category_list.blockSignals(False)

    def show_all_folders(self):
        self._selected_category = ""
        self._selected_memory = None
        self.canvas.show_folders()
        self.category_list.clearSelection()
        self.detail_title.setText("Select a memory")
        self.detail_category.setText("Memory archive")
        self.detail_content.setText("Open a folder, then select a memory card to inspect it.")

    def show_memory_details(self, item: dict):
        self._selected_memory = item
        self.detail_title.setText(str(item.get("title", "Untitled memory")))
        self.detail_category.setText(f'{item.get("category_label", "Memory")}  ·  {item.get("kind", "saved").replace("_", " ").title()}')
        content = str(item.get("content", ""))
        self.detail_content.setPlainText(content)

    def reload_from_nova(self, memory: dict[str, Any] | None = None):
        """Optional integration hook if NOVA wants to pass a refreshed dict."""
        if memory is not None:
            self._memory = memory
        self.refresh_memory()
