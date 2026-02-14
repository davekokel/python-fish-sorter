from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional, Tuple


def rc_to_well(r0: int, c0: int) -> str:
    # r0 is 0-indexed row; render A..Z, AA.. (Excel-style base-26)
    r = int(r0) + 1
    if r <= 0:
        row = "A"
    else:
        parts = []
        while r > 0:
            r -= 1
            parts.append(chr(ord("A") + (r % 26)))
            r //= 26
        row = "".join(reversed(parts))

    col = int(c0) + 1
    if col < 1:
        col = 1
    return f"{row}{col}"


def well_to_rc(well: str) -> Optional[Tuple[int, int]]:
    # parse A1..Z999, AA1.. etc (Excel-style base-26)
    if not isinstance(well, str):
        return None
    m = re.match(r"^\s*([A-Za-z]+)\s*([0-9]+)\s*$", well)
    if not m:
        return None

    row_txt = m.group(1).upper()
    col_txt = m.group(2)

    r0 = 0
    for ch in row_txt:
        if ch < "A" or ch > "Z":
            return None
        r0 = r0 * 26 + (ord(ch) - ord("A") + 1)
    r0 -= 1  # to 0-index

    try:
        c0 = int(col_txt) - 1
    except Exception:
        return None

    if r0 < 0 or c0 < 0:
        return None
    return (r0, c0)


def all_wells(rows: int, cols: int) -> list[str]:
    out: list[str] = []
    rr = max(0, int(rows))
    cc = max(0, int(cols))
    for r in range(rr):
        for c in range(cc):
            out.append(rc_to_well(r, c))
    return out


@dataclass
class ULBRGrid:
    # Base anchors in stage units (um).
    #
    # anchor_mode:
    #   - "center": ul/br represent A1 center and last well center (legacy 2-point linear model)
    #   - "vertex_ul": ul_x/ul_y represent the UL VERTEX of A1, and we compute per-well center using
    #                  x_step/y_step derived from row/col reference points (recommended).
    ul_x: float
    ul_y: float
    br_x: float
    br_y: float
    rows: int
    cols: int

    anchor_mode: str = "center"

    # Optional reference points for vertex-based calibration.
    # These are also vertex points (same vertex as ul_x/ul_y), not centers.
    col_ref_x: Optional[float] = None
    col_ref_y: Optional[float] = None
    col_ref_c: int = 0  # column index (0-indexed) of col_ref point

    row_ref_x: Optional[float] = None
    row_ref_y: Optional[float] = None
    row_ref_r: int = 0  # row index (0-indexed) of row_ref point

    def _step_vectors_vertex(self) -> Optional[Tuple[Tuple[float, float], Tuple[float, float]]]:
        # Returns (col_step, row_step) as 2D vectors in um per 1 column/row.
        if (self.col_ref_x is None) or (self.col_ref_y is None) or (self.col_ref_c <= 0):
            return None
        if (self.row_ref_x is None) or (self.row_ref_y is None) or (self.row_ref_r <= 0):
            return None

        cx = (float(self.col_ref_x) - float(self.ul_x)) / float(self.col_ref_c)
        cy = (float(self.col_ref_y) - float(self.ul_y)) / float(self.col_ref_c)

        rx = (float(self.row_ref_x) - float(self.ul_x)) / float(self.row_ref_r)
        ry = (float(self.row_ref_y) - float(self.ul_y)) / float(self.row_ref_r)

        return (cx, cy), (rx, ry)

    def xy_for_rc(self, r0: int, c0: int) -> Tuple[float, float]:
        rows = max(1, int(self.rows))
        cols = max(1, int(self.cols))
        rr = int(r0)
        cc = int(c0)

        if str(self.anchor_mode).strip().lower() == "vertex_ul":
            steps = self._step_vectors_vertex()
            if steps is not None:
                (cx, cy), (rx, ry) = steps
                # vertex of requested well
                vx = float(self.ul_x) + float(cc) * cx + float(rr) * rx
                vy = float(self.ul_y) + float(cc) * cy + float(rr) * ry
                # center = vertex + half step in each direction
                x = vx + 0.5 * (cx + rx)
                y = vy + 0.5 * (cy + ry)
                return x, y

            # Fallback (if refs not present): treat ul/br as centers (same as legacy)
            # so behavior stays sane rather than failing hard.
            pass

        # Legacy: ul/br are centers of A1 and last well.
        r = float(rr) / float(rows - 1) if rows > 1 else 0.0
        c = float(cc) / float(cols - 1) if cols > 1 else 0.0
        x = float(self.ul_x) + c * (float(self.br_x) - float(self.ul_x))
        y = float(self.ul_y) + r * (float(self.br_y) - float(self.ul_y))
        return x, y

    def xy_for_well(self, well: str) -> Optional[Tuple[float, float]]:
        rc = well_to_rc(well)
        if rc is None:
            return None
        r0, c0 = rc
        if r0 >= int(self.rows) or c0 >= int(self.cols):
            return None
        return self.xy_for_rc(r0, c0)
