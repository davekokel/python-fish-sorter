from __future__ import annotations

from qtpy.QtWidgets import (
    QComboBox,
    QDoubleSpinBox,
    QGroupBox,
    QGridLayout,
    QLabel,
    QListWidget,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)


def build_imaging_stage_ui(p):
    root = QVBoxLayout(p)
    root.setContentsMargins(8, 8, 8, 8)
    root.setSpacing(10)

    root.addWidget(QLabel("Imaging Stage / Plate"))

    status = QGroupBox("Status")
    sg = QGridLayout(status)
    sg.setContentsMargins(8, 8, 8, 8)
    sg.setHorizontalSpacing(10)
    sg.setVerticalSpacing(8)

    p.lbl_dev = QLabel("XY stage: -")
    p.lbl_xy = QLabel("X: -    Y: -")
    sg.addWidget(p.lbl_dev, 0, 0, 1, 3)
    sg.addWidget(p.lbl_xy, 0, 3, 1, 3)

    p.btn_refresh = QPushButton("Refresh")
    p.btn_refresh.clicked.connect(p.stageio.refresh)
    sg.addWidget(p.btn_refresh, 1, 0)

    root.addWidget(status)

    ctrl = QGroupBox("Controls")
    cg = QGridLayout(ctrl)
    cg.setContentsMargins(8, 8, 8, 8)
    cg.setHorizontalSpacing(10)
    cg.setVerticalSpacing(8)

    cg.addWidget(QLabel("Step (um)"), 0, 0)
    p.step_um = QDoubleSpinBox()
    p.step_um.setDecimals(1)
    p.step_um.setRange(0.1, 50000.0)
    p.step_um.setValue(100.0)
    cg.addWidget(p.step_um, 0, 1)

    p.btn_xm = QPushButton("X -")
    p.btn_xp = QPushButton("X +")
    p.btn_ym = QPushButton("Y -")
    p.btn_yp = QPushButton("Y +")

    p.btn_xm.clicked.connect(lambda: p.stageio.jog(-p.step_um.value(), 0.0))
    p.btn_xp.clicked.connect(lambda: p.stageio.jog(+p.step_um.value(), 0.0))
    p.btn_ym.clicked.connect(lambda: p.stageio.jog(0.0, -p.step_um.value()))
    p.btn_yp.clicked.connect(lambda: p.stageio.jog(0.0, +p.step_um.value()))

    cg.addWidget(p.btn_xm, 1, 0)
    cg.addWidget(p.btn_xp, 1, 1)
    cg.addWidget(p.btn_ym, 1, 2)
    cg.addWidget(p.btn_yp, 1, 3)

    cg.addWidget(QLabel("Go to X (um)"), 2, 0)
    p.goto_x = QDoubleSpinBox()
    p.goto_x.setDecimals(1)
    p.goto_x.setRange(-1e9, 1e9)
    cg.addWidget(p.goto_x, 2, 1)

    cg.addWidget(QLabel("Go to Y (um)"), 2, 2)
    p.goto_y = QDoubleSpinBox()
    p.goto_y.setDecimals(1)
    p.goto_y.setRange(-1e9, 1e9)
    cg.addWidget(p.goto_y, 2, 3)

    p.btn_goto = QPushButton("Go")
    p.btn_goto.clicked.connect(p.stageio.goto)
    cg.addWidget(p.btn_goto, 2, 4)

    root.addWidget(ctrl)

    calib = QGroupBox("Grid calibration (vertex-based)")
    gg = QGridLayout(calib)
    gg.setContentsMargins(8, 8, 8, 8)
    gg.setHorizontalSpacing(10)
    gg.setVerticalSpacing(8)

    p.mode = QComboBox()
    p.mode.addItems(["ulbr (2-point)", "affine (UL+RowRef+ColRef)"])
    gg.addWidget(QLabel("Mode"), 0, 0)
    gg.addWidget(p.mode, 0, 1, 1, 2)

    p.btn_crosshairs = QPushButton("Toggle crosshairs")
    p.btn_crosshairs.clicked.connect(p.toggle_crosshairs)
    gg.addWidget(p.btn_crosshairs, 0, 4)

    p.rows = QSpinBox(); p.rows.setRange(1, 99); p.rows.setValue(8)
    p.cols = QSpinBox(); p.cols.setRange(1, 99); p.cols.setValue(12)
    p.rows.valueChanged.connect(p.wells.update_well_list)
    p.cols.valueChanged.connect(p.wells.update_well_list)

    gg.addWidget(QLabel("Rows"), 1, 0)
    gg.addWidget(p.rows, 1, 1)
    gg.addWidget(QLabel("Cols"), 1, 2)
    gg.addWidget(p.cols, 1, 3)

    gg.addWidget(QLabel("Label"), 2, 0)
    gg.addWidget(QLabel("Well / vertex"), 2, 1)
    gg.addWidget(QLabel("X (um)"), 2, 2)
    gg.addWidget(QLabel("Y (um)"), 2, 3)
    gg.addWidget(QLabel("Actions"), 2, 4)

    p._anchor_names = ["UL", "BR", "RowRef", "ColRef"]
    p._anchors_ui = {}

    r0 = 3
    for i, nm in enumerate(p._anchor_names):
        rr = r0 + i
        gg.addWidget(QLabel(nm), rr, 0)

        combo = QComboBox()
        combo.setEditable(False)
        gg.addWidget(combo, rr, 1)

        sx = QDoubleSpinBox(); sx.setDecimals(1); sx.setRange(-1e9, 1e9)
        sy = QDoubleSpinBox(); sy.setDecimals(1); sy.setRange(-1e9, 1e9)
        gg.addWidget(sx, rr, 2)
        gg.addWidget(sy, rr, 3)

        btns = QWidget()
        bgl = QGridLayout(btns)
        bgl.setContentsMargins(0, 0, 0, 0)
        bgl.setHorizontalSpacing(6)
        bgl.setVerticalSpacing(4)

        btn_goto = QPushButton("Go to")
        btn_set = QPushButton("Set = current XY")

        bgl.addWidget(btn_goto, 0, 0)
        bgl.addWidget(btn_set, 0, 1)

        gg.addWidget(btns, rr, 4)

        p._anchors_ui[nm] = {
            "combo": combo,
            "x": sx,
            "y": sy,
            "btn_goto": btn_goto,
            "btn_set": btn_set,
        }

        btn_goto.clicked.connect(lambda _=False, nn=nm: p.anchors.goto_anchor_requested(nn))
        btn_set.clicked.connect(lambda _=False, nn=nm: p.anchors.set_anchor_from_current(nn))

    gg.addWidget(QLabel("Well"), 7, 0)
    p.well = QComboBox()
    gg.addWidget(p.well, 7, 1)

    p.btn_refresh_wells = QPushButton("Update wells")
    p.btn_refresh_wells.clicked.connect(p.wells.update_well_list)
    gg.addWidget(p.btn_refresh_wells, 7, 2)

    p.btn_goto_well = QPushButton("Go to well")
    p.btn_goto_well.clicked.connect(p.wells.goto_selected_well)
    gg.addWidget(p.btn_goto_well, 7, 3)

    p.btn_well_tiles = QPushButton("Well tiles…")
    p.btn_well_tiles.clicked.connect(p.wells.open_well_tiles)
    gg.addWidget(p.btn_well_tiles, 7, 4)

    root.addWidget(calib)

    presets = QGroupBox("Grid presets (truth)")
    pg = QGridLayout(presets)
    pg.setContentsMargins(8, 8, 8, 8)
    pg.setHorizontalSpacing(10)
    pg.setVerticalSpacing(8)

    p.grid_list = QListWidget()
    pg.addWidget(p.grid_list, 0, 0, 6, 4)

    p.btn_grid_new = QPushButton("New")
    p.btn_grid_new.clicked.connect(p.presets.grid_preset_new)
    pg.addWidget(p.btn_grid_new, 0, 4)

    p.btn_grid_save = QPushButton("Save current → selected")
    p.btn_grid_save.clicked.connect(p.presets.grid_preset_save_selected)
    pg.addWidget(p.btn_grid_save, 1, 4)

    p.btn_grid_apply = QPushButton("Load selected")
    p.btn_grid_apply.clicked.connect(p.presets.grid_preset_apply_selected)
    pg.addWidget(p.btn_grid_apply, 2, 4)

    p.btn_grid_delete = QPushButton("Delete selected")
    p.btn_grid_delete.clicked.connect(p.presets.grid_preset_delete_selected)
    pg.addWidget(p.btn_grid_delete, 3, 4)

    p.btn_grid_rename = QPushButton("Rename selected")
    p.btn_grid_rename.clicked.connect(p.presets.grid_preset_rename_selected)
    pg.addWidget(p.btn_grid_rename, 4, 4)

    root.addWidget(presets, stretch=1)

    p.status = QLabel("Status: -")
    root.addWidget(p.status)

    p.wells.update_well_list()
