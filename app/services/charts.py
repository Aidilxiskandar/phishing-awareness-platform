"""Pure geometry helpers for the inline-SVG dashboard charts (no DB, no web)."""
from __future__ import annotations

import math


def donut(segments: list[dict], r: int = 54) -> dict:
    """Precompute stroke-dasharray geometry for an SVG donut chart.

    Each segment becomes a full circle whose visible arc is `dash` long,
    offset so the segments sit end to end. Rendered with a rotate(-90) so the
    first segment starts at 12 o'clock.
    """
    circ = 2 * math.pi * r
    total = sum(s["value"] for s in segments)
    out, offset = [], 0.0
    for s in segments:
        frac = (s["value"] / total) if total else 0.0
        dash = frac * circ
        out.append({
            **s,
            "dash": round(dash, 2),
            "gap": round(circ - dash, 2),
            "offset": round(-offset, 2),
            "pct": round(frac * 100),
        })
        offset += dash
    return {"segments": out, "circ": round(circ, 2), "r": r, "total": total}


def trend(series: list[dict], w: int = 560, h: int = 170) -> dict:
    """Precompute polyline points + area path for the phish-prone % line chart.

    series: ordered list of {"name": str, "rate": float} (one point per campaign).
    """
    pad_l, pad_r, pad_t, pad_b = 12, 12, 16, 22
    pw, ph = w - pad_l - pad_r, h - pad_t - pad_b
    n = len(series)
    top = max(10, math.ceil((max((s["rate"] for s in series), default=0) or 10) / 10) * 10)
    pts = []
    for i, s in enumerate(series):
        x = pad_l + (pw * i / (n - 1) if n > 1 else pw / 2)
        y = pad_t + ph * (1 - s["rate"] / top)
        pts.append({"x": round(x, 1), "y": round(y, 1), **s})
    poly = " ".join(f'{p["x"]},{p["y"]}' for p in pts)
    if pts:
        base = pad_t + ph
        area = (f'M {pts[0]["x"]},{base} '
                + " ".join(f'L {p["x"]},{p["y"]}' for p in pts)
                + f' L {pts[-1]["x"]},{base} Z')
    else:
        area = ""
    gridlines = [{"y": round(pad_t + ph * (1 - frac), 1), "val": round(top * frac)}
                 for frac in (0, 0.5, 1)]
    return {"w": w, "h": h, "points": poly, "area": area, "pts": pts,
            "top": top, "base": round(pad_t + ph, 1), "gridlines": gridlines}


def multi_trend(series: list[dict], keys: list[str], w: int = 560, h: int = 190) -> dict:
    """Several % lines over the same campaigns, sharing one y-scale.

    series: ordered rows (one per campaign) carrying each of `keys` as a number.
    Returns per-key polyline points plus x positions for the axis labels.
    """
    pad_l, pad_r, pad_t, pad_b = 12, 40, 16, 26
    pw, ph = w - pad_l - pad_r, h - pad_t - pad_b
    n = len(series)
    peak = max((float(s[k]) for s in series for k in keys), default=0.0)
    top = max(10, math.ceil(peak / 10) * 10)
    xs = [round(pad_l + (pw * i / (n - 1) if n > 1 else pw / 2), 1) for i in range(n)]
    lines = {}
    for k in keys:
        pts = [{"x": xs[i], "y": round(pad_t + ph * (1 - float(s[k]) / top), 1),
                "val": float(s[k]), "name": s.get("name", "")}
               for i, s in enumerate(series)]
        lines[k] = {"pts": pts, "points": " ".join(f'{p["x"]},{p["y"]}' for p in pts)}
    gridlines = [{"y": round(pad_t + ph * (1 - frac), 1), "val": round(top * frac)}
                 for frac in (0, 0.5, 1)]
    labels = [{"x": xs[i], "name": s.get("name", "")} for i, s in enumerate(series)]
    return {"w": w, "h": h, "top": top, "lines": lines, "gridlines": gridlines,
            "labels": labels, "base": round(pad_t + ph, 1), "x0": pad_l, "x1": w - pad_r}


def bars(series: list[dict], key: str, w: int = 560, h: int = 120) -> dict:
    """Vertical bar geometry for a count per campaign (e.g. scanner clicks)."""
    pad_l, pad_r, pad_t, pad_b = 12, 40, 12, 22
    pw, ph = w - pad_l - pad_r, h - pad_t - pad_b
    n = len(series)
    top = max(1, max((int(s[key]) for s in series), default=0))
    slot = pw / n if n else pw
    bw = max(4.0, min(36.0, slot * 0.5))
    out = []
    for i, s in enumerate(series):
        v = int(s[key])
        bh = ph * v / top
        cx = pad_l + slot * i + slot / 2
        out.append({"x": round(cx - bw / 2, 1), "y": round(pad_t + ph - bh, 1),
                    "w": round(bw, 1), "h": round(bh, 1), "cx": round(cx, 1),
                    "val": v, "name": s.get("name", "")})
    return {"w": w, "h": h, "bars": out, "top": top, "base": round(pad_t + ph, 1),
            "x0": pad_l, "x1": w - pad_r}
