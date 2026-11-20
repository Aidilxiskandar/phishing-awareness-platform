"""Resolve a training module's video into render-ready info for the template."""
from __future__ import annotations

from pathlib import Path

# <repo>/app/static — this module lives in <repo>/app/services/.
_STATIC_DIR = Path(__file__).resolve().parent.parent / "static"


def video_info(module) -> dict | None:
    """Supports local files served from /static (native <video>) and YouTube/Vimeo
    links (embedded iframe). For a local file we report whether it exists on disk
    yet, so the page can show a 'drop your clip here' placeholder until it's added.
    """
    url = (module.video_url or "").strip()
    if not url:
        return None
    low = url.lower()
    if "youtube.com/watch" in low or "youtu.be/" in low or "youtube.com/embed" in low:
        vid = url.split("v=")[-1].split("&")[0] if "watch" in low else url.rstrip("/").split("/")[-1]
        return {"kind": "youtube", "embed": f"https://www.youtube.com/embed/{vid}",
                "ready": True, "url": url}
    if "vimeo.com" in low:
        vid = url.rstrip("/").split("/")[-1]
        return {"kind": "vimeo", "embed": f"https://player.vimeo.com/video/{vid}",
                "ready": True, "url": url}
    # Treat anything else as a (local) file source.
    ready = True
    if url.startswith("/static/"):
        ready = (_STATIC_DIR.parent / url.lstrip("/")).exists()
    return {"kind": "file", "url": url, "ready": ready,
            "poster": (module.video_poster or "").strip()}
