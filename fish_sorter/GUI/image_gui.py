import logging
import numpy as np
import re
from typing import List, Optional, Union, Callable

from pymmcore_plus import CMMCorePlus
from qtpy.QtCore import QSize, Qt
from qtpy.QtGui import QColor
from qtpy.QtWidgets import (
    QGridLayout,
    QPushButton,
    QSizePolicy,
    QHBoxLayout,
    QWidget
)

from fish_sorter.constants import CAM_PX_UM, CAM_X_PX, CAM_Y_PX


class ImageWidget(QWidget):

    def __init__(self, viewer, on_workflow: Optional[Callable[[], None]] = None, parent: QWidget | None=None):
        """
        :param viewer: napari viewer to use
        :type viewer: napari.Viewer
        :param on_workflow: callback to return to Workflow panel (Qt shell). If None, legacy fallback is attempted.
        """

        super().__init__(parent=parent)
        self.mmc = CMMCorePlus().instance()
        self.viewer = viewer
        self.on_workflow = on_workflow

        self.mosaic_btn = QPushButton("Stitch mosaic")
        self.class_btn = QPushButton("Classify")
        self.workflow_btn = QPushButton("Workflow")

        self.crosshair_layer = 'crosshairs'
        self.workflow_btn.setToolTip("Return to Workflow")
        self.workflow_btn.clicked.connect(self._go_workflow)

        layout = QHBoxLayout()
        layout.addWidget(self.mosaic_btn)
        layout.addWidget(self.class_btn)
        layout.addWidget(self.workflow_btn)
        self.setLayout(layout)

    def _create_crosshairs(self):
        self.viewer.reset_view()
        preview_layer = None
        for layer in self.viewer.layers:
            if layer.name == 'preview':
                preview_layer = layer
                break

        if preview_layer is None:
            return

        try:
            h, w = preview_layer.data.shape[-2], preview_layer.data.shape[-1]
        except Exception:
            return

        ymid = float(h) / 2.0
        xmid = float(w) / 2.0

        lines = [
            [[ymid, 0.0], [ymid, float(w)]],
            [[0.0, xmid], [float(h), xmid]],
        ]
        if self.crosshair_layer in self.viewer.layers:
            del self.viewer.layers[self.crosshair_layer]

        layer = self.viewer.add_shapes(
            lines,
            shape_type='line',
            edge_color='yellow',
            edge_width=25,
            name=self.crosshair_layer,
            blending='translucent'
        )
        layer.editable = False
        layer.selectable = False

    def get_mag(self):
        logging.info('Getting the magnification')

        obj_devs = self.mmc.guessObjectiveDevices()
        if not obj_devs:
            logging.warning("No objective device found (sim mode). Using default magnification.")
            mag = 1.0
            self.pixel_size_um = CAM_PX_UM / mag
            self.fov_h = CAM_Y_PX * self.pixel_size_um
            self.fov_w = CAM_X_PX * self.pixel_size_um
            return

        obj_dev = obj_devs[0]
        obj_label = self.mmc.getStateLabel(obj_dev)

        match = re.search(r'([\d.]+)x', obj_label)
        if match:
            mag = float(match.group(1))
            logging.info(f'Magnification: {mag}')
        else:
            mag = 1.0
            logging.warning(f'Could not parse magnfication from label {obj_label}')

        self.pixel_size_um = CAM_PX_UM / mag
        self.fov_h = CAM_Y_PX * self.pixel_size_um
        self.fov_w = CAM_X_PX * self.pixel_size_um

    def _go_workflow(self):
        # Qt shell path
        if self.on_workflow is not None:
            try:
                self.on_workflow()
                return
            except Exception:
                pass

        # Legacy fallback (napari-as-shell)
        try:
            fp = getattr(self.viewer.window._qt_window, "_fishpicker", None)
            if fp is None:
                return
            fp.show_right_panel("Workflow")
        except Exception:
            pass

    def toggle_crosshairs(self):
        self._toggle_crosshairs()

    def _toggle_crosshairs(self):
        if self.crosshair_layer in self.viewer.layers:
            del self.viewer.layers[self.crosshair_layer]
        else:
            self.get_mag()
            self._create_crosshairs()
