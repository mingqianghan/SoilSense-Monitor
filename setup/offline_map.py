"""
Offline-map tile cache.

Downloads Google satellite tiles + the Leaflet JS/CSS bundle while the app
is online, so the same Leaflet view can be rendered offline next time the
app launches. Tiles live as individual files under `assets/tiles/{z}/{x}/{y}.png`;
Leaflet assets sit under `assets/leaflet/`. A manifest records the bbox and
zoom levels that have been cached.

Designed to run silently in the background. Skips tiles already on disk so
re-runs are cheap.
"""
from __future__ import annotations
import json
import math
import os
import urllib.request

from PyQt6.QtCore import QThread, pyqtSignal


# ── slippy-map tile math ─────────────────────────────────────────────────
def _lat_lon_to_tile(lat: float, lon: float, zoom: int) -> tuple[int, int]:
    lat_r = math.radians(lat)
    n = 1 << zoom
    x = int((lon + 180.0) / 360.0 * n)
    y = int((1.0 - math.log(math.tan(lat_r) + 1.0 / math.cos(lat_r))
             / math.pi) / 2.0 * n)
    return x, y


# ── paths ────────────────────────────────────────────────────────────────
TILES_DIR        = "assets/tiles"
LEAFLET_DIR      = "assets/leaflet"
LEAFLET_JS_PATH  = os.path.join(LEAFLET_DIR, "leaflet.js")
LEAFLET_CSS_PATH = os.path.join(LEAFLET_DIR, "leaflet.css")
MANIFEST_PATH    = "assets/tiles_manifest.json"

_LEAFLET_JS_URL  = "https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"
_LEAFLET_CSS_URL = "https://unpkg.com/leaflet@1.9.4/dist/leaflet.css"


def tiles_cache_available() -> bool:
    """True when there's enough on disk to render an offline Leaflet view."""
    return (
        os.path.isdir(TILES_DIR)
        and os.path.exists(LEAFLET_JS_PATH)
        and os.path.exists(LEAFLET_CSS_PATH)
        and os.path.exists(MANIFEST_PATH)
    )


def cached_manifest() -> dict | None:
    try:
        with open(MANIFEST_PATH) as f:
            return json.load(f)
    except Exception:
        return None


class TileCacheDownloader(QThread):
    """Background QThread: download Google satellite tiles for the marker
    bbox at the configured zoom levels, plus the Leaflet bundle if missing.
    Skips files already on disk. Emits `done(downloaded, total)` when finished.
    """

    done = pyqtSignal(int, int)

    _TILE_URL  = "https://mt1.google.com/vt/lyrs=s&x={x}&y={y}&z={z}"
    _UA        = "Mozilla/5.0 (CommInterface tile cache)"
    _MAX_TILES = 1200

    def __init__(self, markers: list[dict],
                 zooms: tuple[int, ...] = (17, 18, 19, 20),
                 padding_deg: float = 0.0018,
                 parent=None):
        super().__init__(parent)
        self.markers = markers
        self.zooms   = zooms
        self.padding = padding_deg

    # ── public ────────────────────────────────────────────────────────────
    def run(self):
        downloaded = 0
        total      = 0
        try:
            self._fetch_leaflet_assets()
            downloaded, total = self._fetch_tiles()
        except Exception as e:
            print(f"[tile cache] aborted: {e}")
        self.done.emit(downloaded, total)

    # ── leaflet assets (CDN → local) ──────────────────────────────────────
    def _fetch_leaflet_assets(self) -> None:
        os.makedirs(LEAFLET_DIR, exist_ok=True)
        for url, path in (
            (_LEAFLET_JS_URL,  LEAFLET_JS_PATH),
            (_LEAFLET_CSS_URL, LEAFLET_CSS_PATH),
        ):
            if os.path.exists(path):
                continue
            try:
                self._download_to(url, path)
            except Exception as e:
                print(f"[tile cache] leaflet asset {url}: {e}")

    # ── tile grid ─────────────────────────────────────────────────────────
    def _fetch_tiles(self) -> tuple[int, int]:
        if not self.markers:
            return 0, 0

        lats = [m["latitude"]  for m in self.markers]
        lons = [m["longitude"] for m in self.markers]
        north = max(lats) + self.padding
        south = min(lats) - self.padding
        east  = max(lons) + self.padding
        west  = min(lons) - self.padding

        # Build list of needed tiles across all zooms
        needed: list[tuple[int, int, int]] = []
        for z in self.zooms:
            x_min, y_min = _lat_lon_to_tile(north, west, z)
            x_max, y_max = _lat_lon_to_tile(south, east, z)
            for ty in range(y_min, y_max + 1):
                for tx in range(x_min, x_max + 1):
                    needed.append((z, tx, ty))

        if len(needed) > self._MAX_TILES:
            print(f"[tile cache] capping at {self._MAX_TILES}/{len(needed)} tiles")
            needed = needed[: self._MAX_TILES]

        downloaded = 0
        for z, tx, ty in needed:
            tile_path = os.path.join(TILES_DIR, str(z), str(tx), f"{ty}.png")
            if os.path.exists(tile_path):
                continue
            try:
                os.makedirs(os.path.dirname(tile_path), exist_ok=True)
                self._download_to(self._TILE_URL.format(x=tx, y=ty, z=z),
                                  tile_path)
                downloaded += 1
            except Exception as e:
                print(f"[tile cache] tile {z}/{tx}/{ty}: {e}")
                continue

        # Manifest reflects the bbox + zooms we covered (best-effort, even
        # if some tiles failed — partial coverage is still useful offline).
        try:
            with open(MANIFEST_PATH, "w") as f:
                json.dump({
                    "north": north, "south": south,
                    "east":  east,  "west":  west,
                    "zooms": list(self.zooms),
                }, f)
        except Exception as e:
            print(f"[tile cache] manifest: {e}")

        return downloaded, len(needed)

    # ── helpers ───────────────────────────────────────────────────────────
    def _download_to(self, url: str, path: str) -> None:
        req = urllib.request.Request(url, headers={"User-Agent": self._UA})
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = resp.read()
        tmp = path + ".tmp"
        with open(tmp, "wb") as f:
            f.write(data)
        os.replace(tmp, path)


# ── bounds helpers (used by HomeGui to decide if cache is still fresh) ───
def cached_bounds_cover(markers: list[dict], margin_deg: float = 1e-4) -> bool:
    """True if the cached manifest's bbox contains every marker."""
    if not markers:
        return True
    manifest = cached_manifest()
    if not manifest:
        return False
    lats = [m["latitude"]  for m in markers]
    lons = [m["longitude"] for m in markers]
    return (
        manifest.get("north", -90)  >= max(lats) - margin_deg
        and manifest.get("south", 90)  <= min(lats) + margin_deg
        and manifest.get("east",  -180) >= max(lons) - margin_deg
        and manifest.get("west",   180) <= min(lons) + margin_deg
    )
