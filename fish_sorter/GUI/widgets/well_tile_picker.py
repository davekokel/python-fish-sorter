from __future__ import annotations

from typing import Callable, Iterable, Optional

from qtpy.QtCore import Qt
from qtpy.QtWidgets import (
    QDialog,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)


class WellTilePickerWidget(QWidget):
    """
    Grid of clickable well tiles.

    - wells: iterable of well labels ("A1", "B03", ...)
    - columns: number of tile columns
    - on_pick: callback well->None
    """

    def __init__(
        self,
        wells: Iterable[str],
        columns: int = 12,
        on_pick: Optional[Callable[[str], None]] = None,
        parent: QWidget | None = None,
    ):
        super().__init__(parent=parent)
        self._on_pick = on_pick
        self._columns = max(1, int(columns))

        root = QVBoxLayout(self)
        root.setContentsMargins(8, 8, 8, 8)
        root.setSpacing(8)

        self.grid = QGridLayout()
        self.grid.setHorizontalSpacing(6)
        self.grid.setVerticalSpacing(6)

        container = QWidget()
        container.setLayout(self.grid)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(container)

        root.addWidget(scroll)

        self.set_wells(list(wells))

    def set_wells(self, wells: list[str]) -> None:
        while self.grid.count():
            item = self.grid.takeAt(0)
            w = item.widget()
            if w is not None:
                w.setParent(None)

        r = 0
        c = 0
        for w in wells:
            b = QPushButton(str(w))
            b.setMinimumWidth(52)
            b.setMinimumHeight(32)
            b.clicked.connect(lambda _=False, ww=str(w): self._picked(ww))
            self.grid.addWidget(b, r, c)
            c += 1
            if c >= self._columns:
                c = 0
                r += 1

    def _picked(self, well: str) -> None:
        if self._on_pick is not None:
            try:
                self._on_pick(str(well))
            except Exception:
                pass


class WellTilePickerDialog(QDialog):
    """
    Modal dialog wrapper around WellTilePickerWidget.
    Sized relative to parent (right pane) so it doesn't dominate the UI.
    """

    def __init__(
        self,
        wells: list[str],
        columns: int = 12,
        title: str = "Pick a well",
        parent: QWidget | None = None,
        width_frac: float = 0.55,
        height_frac: float = 0.55,
        min_w: int = 340,
        min_h: int = 260,
    ):
        super().__init__(parent=parent)
        self.setWindowTitle(title)
        self.selected: Optional[str] = None

        root = QVBoxLayout(self)
        root.setContentsMargins(8, 8, 8, 8)
        root.setSpacing(8)

        root.addWidget(QLabel(title))

        self.picker = WellTilePickerWidget(wells=wells, columns=columns, on_pick=self._on_pick)
        root.addWidget(self.picker, stretch=1)

        row = QWidget()
        h = QHBoxLayout(row)
        h.setContentsMargins(0, 0, 0, 0)
        h.addStretch(1)

        btn_close = QPushButton("Close")
        btn_close.clicked.connect(self.reject)
        h.addWidget(btn_close)

        root.addWidget(row)

        pw = None
        ph = None
        try:
            if parent is not None:
                pw = int(parent.width())
                ph = int(parent.height())
        except Exception:
            pw = None
            ph = None

        if pw and ph and pw > 0 and ph > 0:
            w = max(min_w, int(pw * float(width_frac)))
            h2 = max(min_h, int(ph * float(height_frac)))
            self.resize(w, h2)
        else:
            self.resize(520, 420)

    def _on_pick(self, well: str) -> None:
        self.selected = str(well)
        self.accept()
