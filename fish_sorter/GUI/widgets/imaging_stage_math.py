from __future__ import annotations

from typing import Optional, Tuple, Dict, Any, List

from fish_sorter.GUI.widgets.grid_ulbr import well_to_rc


VERTEX_CHOICES = ["C", "UL", "UR", "LL", "LR"]


def row_label(r0: int) -> str:
    r = int(r0) + 1
    if r <= 0:
        return "A"
    parts = []
    while r > 0:
        r -= 1
        parts.append(chr(ord("A") + (r % 26)))
        r //= 26
    return "".join(reversed(parts))


def default_requested_well(anchor_name: str, rows: int, cols: int) -> str:
    rows = int(rows)
    cols = int(cols)
    if rows < 1 or cols < 1:
        return "A1"
    if anchor_name == "UL":
        return "A1"
    if anchor_name == "BR":
        return f"{row_label(rows-1)}{cols}"
    if anchor_name == "RowRef":
        return f"{row_label(rows-1)}1"
    if anchor_name == "ColRef":
        return f"A{cols}"
    return "A1"


def neighbor_wells(well: str, rows: int, cols: int) -> List[str]:
    rc = well_to_rc(well)
    if rc is None:
        return [well]
    r0, c0 = rc
    rows = int(rows)
    cols = int(cols)

    cand = []
    for dr, dc in [(0,0),(0,1),(1,0),(0,-1),(-1,0),(1,1),(1,-1),(-1,1),(-1,-1)]:
        rr = r0 + dr
        cc = c0 + dc
        if rr < 0 or cc < 0 or rr >= rows or cc >= cols:
            continue
        cand.append(f"{row_label(rr)}{cc+1}")

    out = []
    seen = set()
    for w in cand:
        if w not in seen:
            seen.add(w)
            out.append(w)
    return out or [well]


def pack_well_vertex(well: str, vertex: str) -> str:
    v = str(vertex or "C").upper()
    if v not in VERTEX_CHOICES:
        v = "C"
    return f"{str(well).strip()}:{v}"


def unpack_well_vertex(s: str) -> Tuple[str, str]:
    t = str(s or "")
    if ":" not in t:
        return t.strip(), "C"
    a, b = t.split(":", 1)
    w = a.strip()
    v = b.strip().upper()
    if v not in VERTEX_CHOICES:
        v = "C"
    return w, v


def xy_affine(
    target_well: str,
    anchors: Dict[str, Any],
) -> Optional[Tuple[float, float]]:
    """
    Basic affine-ish mapping using:
      UL, RowRef, ColRef anchors.

    NOTE: This assumes mostly axis-aligned grid. It improves mid-grid error vs UL/BR interpolation,
    but does not model rotation/shear unless RowRef/ColRef are chosen appropriately.
    """
    ul = anchors.get("UL")
    rr = anchors.get("RowRef")
    cr = anchors.get("ColRef")
    if not (isinstance(ul, dict) and isinstance(rr, dict) and isinstance(cr, dict)):
        return None

    ul_w = str(ul.get("well") or "")
    rr_w = str(rr.get("well") or "")
    cr_w = str(cr.get("well") or "")
    ul_rc = well_to_rc(ul_w)
    rr_rc = well_to_rc(rr_w)
    cr_rc = well_to_rc(cr_w)
    tgt_rc = well_to_rc(target_well)

    if ul_rc is None or rr_rc is None or cr_rc is None or tgt_rc is None:
        return None

    ul_r, ul_c = ul_rc
    rr_r, rr_c = rr_rc
    cr_r, cr_c = cr_rc
    tr, tc = tgt_rc

    try:
        ulx = float(ul["x_um"]); uly = float(ul["y_um"])
        rrx = float(rr["x_um"]); rry = float(rr["y_um"])
        crx = float(cr["x_um"]); cry = float(cr["y_um"])
    except Exception:
        return None

    dc = (cr_c - ul_c)
    dr = (rr_r - ul_r)
    if dc == 0 or dr == 0:
        return None

    dx_per_col = (crx - ulx) / float(dc)
    dy_per_row = (rry - uly) / float(dr)

    x = ulx + dx_per_col * float(tc - ul_c)
    y = uly + dy_per_row * float(tr - ul_r)
    return float(x), float(y)
