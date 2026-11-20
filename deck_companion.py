#!/usr/bin/env python3
"""
deck_companion.py — StreamDeck Python : télécommande tactile pour le PC.

  * Télécommande web entièrement personnalisable (smartphone / tablette) :
    pages, boutons, icônes réelles des applis du PC, thèmes, couleurs, horloge…
    Tout se règle depuis le bouton ⚙ de l'interface (protégé par un code PIN).
  * Boîtier USB (ESP32 / Leonardo) : reçoit VOL_UP, MUTE, APP:2… et renvoie
    l'heure, le volume et les libellés.

Windows (pycaw, icônes natives), Linux (pactl, xdotool, .desktop), macOS (osascript).

Usage :
    python deck_companion.py                 # interface web (téléphone, tablette, navigateur)
    python deck_companion.py --open          # + ouvre l'interface sur ce PC
    python deck_companion.py --serial        # + boîtier USB ESP32/Arduino (optionnel)

Licence MIT.
"""
from __future__ import annotations

import argparse
import calendar
import copy
import hashlib
import hmac
import json
import mimetypes
import os
import platform
import queue
import random
import re
import secrets
import shlex
import subprocess
import sys
import threading
import time
from concurrent.futures import Future
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

SYSTEM = platform.system()          # "Windows", "Linux", "Darwin"
HERE = Path(__file__).resolve().parent
WEB_DIR = HERE / "web"
ICON_CACHE = HERE / "icons_cache"
BAUD = 115200
KNOWN_VIDS = {0x1A86, 0x10C4, 0x2341, 0x2A03, 0x1B4F, 0x303A}
LEGACY_COMMANDS = {"VOL_UP", "VOL_DOWN", "MUTE", "PLAY", "NEXT", "PREV"}

if SYSTEM == "Windows":
    import winshell  # noqa: E402  (module local)


def log(*args):
    print(time.strftime("[%H:%M:%S]"), *args, flush=True)


# =====================================================================
#  Volume système
# =====================================================================
class Volume:
    def get(self):
        return None

    def set(self, level: int):
        pass

    def step(self, delta: int):
        cur = self.get()
        self.set(max(0, min(100, (cur[0] if cur else 50) + delta)))

    def toggle_mute(self):
        pass


class WindowsVolume(Volume):
    def __init__(self):
        from pycaw.pycaw import AudioUtilities, IAudioEndpointVolume
        speakers = AudioUtilities.GetSpeakers()
        ep = getattr(speakers, "EndpointVolume", None)
        if ep is None:
            from ctypes import POINTER, cast
            from comtypes import CLSCTX_ALL
            iface = speakers.Activate(IAudioEndpointVolume._iid_, CLSCTX_ALL, None)
            ep = cast(iface, POINTER(IAudioEndpointVolume))
        self.ep = ep

    def get(self):
        return round(self.ep.GetMasterVolumeLevelScalar() * 100), bool(self.ep.GetMute())

    def set(self, level):
        self.ep.SetMasterVolumeLevelScalar(max(0.0, min(1.0, level / 100)), None)

    def step(self, delta):
        super().step(delta)
        if delta > 0 and self.ep.GetMute():
            self.ep.SetMute(0, None)

    def toggle_mute(self):
        self.ep.SetMute(0 if self.ep.GetMute() else 1, None)


class WindowsKeysVolume(Volume):
    def step(self, delta):
        winshell.hotkey(["volumeup" if delta > 0 else "volumedown"])

    def toggle_mute(self):
        winshell.hotkey(["volumemute"])


class LinuxVolume(Volume):
    SINK = "@DEFAULT_SINK@"

    def _run(self, *args):
        return subprocess.run(["pactl", *args], capture_output=True, text=True, timeout=2).stdout

    def get(self):
        try:
            level = int(self._run("get-sink-volume", self.SINK).split("%")[0].split()[-1])
            return level, "yes" in self._run("get-sink-mute", self.SINK)
        except Exception:
            return None

    def set(self, level):
        self._run("set-sink-volume", self.SINK, f"{int(level)}%")

    def toggle_mute(self):
        self._run("set-sink-mute", self.SINK, "toggle")


class MacVolume(Volume):
    def _osa(self, script):
        return subprocess.run(["osascript", "-e", script], capture_output=True,
                              text=True, timeout=2).stdout.strip()

    def get(self):
        try:
            return (int(self._osa("output volume of (get volume settings)")),
                    self._osa("output muted of (get volume settings)") == "true")
        except Exception:
            return None

    def set(self, level):
        self._osa(f"set volume output volume {int(level)}")

    def toggle_mute(self):
        self._osa("set volume output muted not (output muted of (get volume settings))")


def make_volume() -> Volume:
    if SYSTEM == "Windows":
        try:
            return WindowsVolume()
        except Exception as e:
            log("pycaw indisponible, repli sur les touches volume :", e)
            return WindowsKeysVolume()
    return {"Linux": LinuxVolume, "Darwin": MacVolume}.get(SYSTEM, Volume)()


# =====================================================================
#  Raccourcis clavier & multimédia
# =====================================================================
KEY_ALIASES = {"control": "ctrl", "ctl": "ctrl", "cmd": "win", "command": "win", "super": "win",
               "meta": "win", "windows": "win", "escape": "esc", "return": "enter", "del": "delete",
               "pgup": "pageup", "pgdn": "pagedown", "pgdown": "pagedown", "prtsc": "printscreen",
               "impr": "printscreen", "espace": "space", "entree": "enter", "entrée": "enter",
               "suppr": "delete", "maj": "shift", "haut": "up", "bas": "down", "gauche": "left",
               "droite": "right"}
_GENERIC_KEYS = {"ctrl", "shift", "alt", "win", "esc", "enter", "tab", "space", "backspace", "delete",
                 "insert", "home", "end", "pageup", "pagedown", "up", "down", "left", "right",
                 "printscreen", "pause", "capslock", "numlock", "volumeup", "volumedown", "volumemute",
                 "playpause", "nexttrack", "prevtrack", "-", "=", ",", ".", ";", "/"}


def parse_hotkey(text: str) -> list[str]:
    keys = [KEY_ALIASES.get(k.strip().lower(), k.strip().lower()) for k in str(text).split("+") if k.strip()]
    if not 1 <= len(keys) <= 5:
        raise ValueError("raccourci vide ou trop long")
    for k in keys:
        ok = (k in _GENERIC_KEYS or (len(k) == 1 and k.isalnum())
              or (k.startswith("f") and k[1:].isdigit() and 1 <= int(k[1:]) <= 24))
        if not ok:
            raise ValueError(f"touche inconnue : {k}")
    return keys


_XDO = {"ctrl": "ctrl", "shift": "shift", "alt": "alt", "win": "super", "esc": "Escape", "enter": "Return",
        "tab": "Tab", "space": "space", "backspace": "BackSpace", "delete": "Delete", "insert": "Insert",
        "home": "Home", "end": "End", "pageup": "Prior", "pagedown": "Next", "up": "Up", "down": "Down",
        "left": "Left", "right": "Right", "printscreen": "Print", "volumeup": "XF86AudioRaiseVolume",
        "volumedown": "XF86AudioLowerVolume", "volumemute": "XF86AudioMute", "playpause": "XF86AudioPlay",
        "nexttrack": "XF86AudioNext", "prevtrack": "XF86AudioPrev"}


def send_hotkey(keys: list[str]):
    if SYSTEM == "Windows":
        winshell.hotkey(keys)
    elif SYSTEM == "Linux":
        combo = "+".join(_XDO.get(k, k.upper() if k.startswith("f") and len(k) > 1 else k) for k in keys)
        subprocess.Popen(["xdotool", "key", combo])
    elif SYSTEM == "Darwin":
        mods = {"ctrl": "control down", "shift": "shift down", "alt": "option down", "win": "command down"}
        main = [k for k in keys if k not in mods]
        using = ", ".join(mods[k] for k in keys if k in mods)
        if len(main) == 1 and len(main[0]) == 1:
            script = f'tell application "System Events" to keystroke "{main[0]}"'
            if using:
                script += f" using {{{using}}}"
            subprocess.Popen(["osascript", "-e", script])
        else:
            log("Raccourci non géré sur macOS :", keys)


def media_key(name: str):
    if SYSTEM == "Windows":
        winshell.hotkey([{"PLAY": "playpause", "NEXT": "nexttrack", "PREV": "prevtrack"}[name]])
    elif SYSTEM == "Linux":
        subprocess.Popen(["playerctl", {"PLAY": "play-pause", "NEXT": "next", "PREV": "previous"}[name]])
    elif SYSTEM == "Darwin":
        verb = {"PLAY": "playpause", "NEXT": "next track", "PREV": "previous track"}[name]
        subprocess.Popen(["osascript", "-e", f'tell application "Spotify" to {verb}'])


# =====================================================================
#  Catalogue des applications installées (+ icônes)
# =====================================================================
class AppCatalog:
    def __init__(self):
        self.apps: list[dict] = []
        self.by_id: dict[str, dict] = {}
        self.loaded_at = 0.0
        self.lock = threading.Lock()

    def list(self, refresh=False):
        with self.lock:
            if refresh or not self.apps:
                try:
                    self.apps = self._scan()
                except Exception as e:
                    log("Impossible de lister les applications :", e)
                    self.apps = []
                self.by_id = {a["id"]: a for a in self.apps}
                self.loaded_at = time.time()
                log(f"{len(self.apps)} applications trouvées sur le PC")
            return self.apps

    def _scan(self):
        if SYSTEM == "Windows":
            return winshell.list_start_apps()
        if SYSTEM == "Linux":
            return self._scan_linux()
        if SYSTEM == "Darwin":
            apps = []
            for base in ("/Applications", "/System/Applications", str(Path.home() / "Applications")):
                for p in sorted(Path(base).glob("*.app")):
                    apps.append({"id": str(p), "name": p.stem})
            return apps
        return []

    @staticmethod
    def _scan_linux():
        dirs = [Path("/usr/share/applications"), Path.home() / ".local/share/applications",
                Path("/var/lib/flatpak/exports/share/applications")]
        extra = os.environ.get("DECK_APPS_DIR")
        if extra:
            dirs.insert(0, Path(extra))
        apps, seen = [], set()
        for d in dirs:
            for f in sorted(d.glob("*.desktop")) if d.is_dir() else []:
                entry = {}
                section = None
                for line in f.read_text(encoding="utf-8", errors="ignore").splitlines():
                    if line.startswith("["):
                        section = line.strip()
                    elif section == "[Desktop Entry]" and "=" in line:
                        k, v = line.split("=", 1)
                        entry.setdefault(k.strip(), v.strip())
                if entry.get("NoDisplay") == "true" or entry.get("Type", "Application") != "Application":
                    continue
                if not entry.get("Name") or not entry.get("Exec") or str(f) in seen:
                    continue
                seen.add(str(f))
                apps.append({"id": str(f), "name": entry["Name"], "_exec": entry["Exec"],
                             "_icon": entry.get("Icon", "")})
        apps.sort(key=lambda a: a["name"].lower())
        return apps

    def public(self):
        return [{"id": a["id"], "name": a["name"]} for a in self.list()]

    def launch(self, app_id: str):
        if SYSTEM == "Windows":
            winshell.launch_app(app_id)
        elif SYSTEM == "Linux":
            self.list()
            app = self.by_id.get(app_id)
            if not app:
                raise ValueError("application inconnue")
            cmd = re.sub(r"\s%[a-zA-Z]", "", app["_exec"])
            subprocess.Popen(shlex.split(cmd), start_new_session=True)
        elif SYSTEM == "Darwin":
            subprocess.Popen(["open", "-a", app_id])

    def linux_icon_file(self, app_id: str):
        self.list()
        app = self.by_id.get(app_id)
        name = app.get("_icon") if app else None
        if not name:
            return None
        if os.path.isabs(name) and os.path.isfile(name):
            return name
        roots = [Path("/usr/share/icons/hicolor"), Path.home() / ".local/share/icons/hicolor"]
        for root in roots:
            for size in ("256x256", "192x192", "128x128", "96x96", "64x64", "48x48", "scalable"):
                for ext in (".png", ".svg"):
                    p = root / size / "apps" / (name + ext)
                    if p.is_file():
                        return str(p)
        for ext in (".png", ".svg", ".xpm"):
            p = Path("/usr/share/pixmaps") / (name + ext)
            if p.is_file():
                return str(p)
        return None


class IconService(threading.Thread):
    """Extrait les icônes dans un seul thread (COM sous Windows) avec cache disque."""

    def __init__(self, catalog: AppCatalog):
        super().__init__(daemon=True)
        self.catalog = catalog
        self.jobs: "queue.Queue[tuple[str, str, Future]]" = queue.Queue()
        ICON_CACHE.mkdir(exist_ok=True)

    def get(self, kind: str, ident: str, timeout=8.0):
        key = hashlib.sha1(f"{kind}:{ident}".encode()).hexdigest()
        for ext, ctype in ((".png", "image/png"), (".svg", "image/svg+xml")):
            p = ICON_CACHE / (key + ext)
            if p.is_file():
                return p.read_bytes(), ctype
        if (ICON_CACHE / (key + ".none")).is_file():
            return None
        fut: Future = Future()
        self.jobs.put((kind, ident, fut))
        try:
            data = fut.result(timeout=timeout)
        except Exception:
            return None
        try:
            ICON_CACHE.mkdir(exist_ok=True)
            if not data:
                (ICON_CACHE / (key + ".none")).write_bytes(b"")
            else:
                (ICON_CACHE / (key + (".svg" if "svg" in data[1] else ".png"))).write_bytes(data[0])
        except OSError:
            pass                                   # cache facultatif
        return data or None

    def run(self):
        if SYSTEM == "Windows":
            try:
                winshell.com_init()
            except Exception as e:
                log("COM :", e)
        while True:
            kind, ident, fut = self.jobs.get()
            try:
                fut.set_result(self._extract(kind, ident))
            except Exception as e:
                log("Icône introuvable :", ident, "-", e)
                fut.set_result(None)

    def _extract(self, kind, ident):
        if SYSTEM == "Windows":
            name = ("shell:AppsFolder\\" + ident) if kind == "app" else ident
            png = winshell.icon_png(name)
            return (png, "image/png") if png else None
        if SYSTEM == "Linux" and kind == "app":
            f = self.catalog.linux_icon_file(ident)
            if f and f.endswith((".png", ".svg")):
                return Path(f).read_bytes(), "image/svg+xml" if f.endswith(".svg") else "image/png"
        return None


# =====================================================================
#  Configuration (pages, boutons, thème) — validation stricte
# =====================================================================
TILE_TYPES = {"vol_down", "vol_up", "mute", "play", "next", "prev", "volume", "clock",
              "app", "file", "url", "hotkey", "page", "empty"}
ICON_KINDS = {"auto", "builtin", "emoji", "image", "none"}
COLOR_RE = re.compile(r"^#[0-9a-fA-F]{6}$")
IMAGE_RE = re.compile(r"^data:image/(png|jpeg|webp|gif);base64,[A-Za-z0-9+/=]+$")

DEFAULT_THEME = {"preset": "nuit", "bg1": "#0e1016", "bg2": "#1d1638", "bgStyle": "gradient",
                 "tile": "#262b38", "text": "#ffffff", "accent": "#00beff", "style": "solid",
                 "radius": 18, "gap": 10, "iconScale": 0.42, "labelSize": 15, "showLabels": True,
                 "font": "system", "topBar": True, "fullscreenOnTap": True, "pressFx": "scale",
                 "haptic": True}
DEFAULT_CLOCK = {"h24": True, "seconds": True, "date": True, "color": "#ffffff",
                 "accent": "#ff9600", "screensaver": 2, "dim": True}
NUMERIC_LIMITS = {"radius": (0, 40), "gap": (0, 30), "iconScale": (0.15, 0.8),
                  "labelSize": (8, 32), "screensaver": (0, 120)}
ENUMS = {"bgStyle": {"solid", "gradient"}, "style": {"solid", "outline", "glass"},
         "font": {"system", "rounded", "mono", "serif", "condensed"},
         "pressFx": {"scale", "glow", "none"}}


def new_id():
    return "t" + secrets.token_hex(4)


def tile(type_, label="", icon=None, bg="", **extra):
    t = {"id": new_id(), "type": type_, "label": label, "span": 1, "bg": bg, "fg": "",
         "icon": icon or {"kind": "auto", "value": ""}}
    t.update(extra)
    return t


def default_config(legacy_apps=None):
    apps = legacy_apps or [
        {"label": "Brave", "windows": "brave", "linux": "brave-browser", "mac": "Brave Browser"},
        {"label": "Discord", "windows": "discord://", "linux": "discord", "mac": "Discord"},
        {"label": "Spotify", "windows": "spotify:", "linux": "spotify", "mac": "Spotify"},
        {"label": "VS Code", "windows": "code", "linux": "code", "mac": "Visual Studio Code"}]
    key = {"Windows": "windows", "Linux": "linux", "Darwin": "mac"}.get(SYSTEM, "linux")
    app_tiles = [tile("file", a.get("label", "App"), path=a.get(key) or a.get("cmd") or "",
                      bg="#5b3fb0") for a in apps[:4]]
    return {
        "version": 2,
        "pin": f"{random.randint(0, 9999):04d}",
        "volume_step": 4,
        "theme": dict(DEFAULT_THEME),
        "clock": dict(DEFAULT_CLOCK),
        "pages": [
            {"name": "Principal", "cols": 4, "tiles": [
                tile("vol_down", "Vol -", bg="#2460c8"), tile("mute", "Muet", bg="#c8323c"),
                tile("vol_up", "Vol +", bg="#2460c8"), tile("clock", "Horloge"),
                *app_tiles,
                tile("prev", "Préc."), tile("play", "Lecture"), tile("next", "Suiv."),
                tile("page", "Raccourcis", {"kind": "builtin", "value": "grid"}, bg="#11806a", target=1)]},
            {"name": "Raccourcis", "cols": 4, "tiles": [
                tile("hotkey", "Capture", {"kind": "builtin", "value": "screenshot"}, keys="win+shift+s"),
                tile("hotkey", "Bureau", {"kind": "builtin", "value": "monitor"}, keys="win+d"),
                tile("hotkey", "Gestionnaire", {"kind": "builtin", "value": "chart"}, keys="ctrl+shift+esc"),
                tile("hotkey", "Discord mute", {"kind": "builtin", "value": "mic-off"}, bg="#c8323c",
                     keys="ctrl+shift+m"),
                tile("url", "YouTube", {"kind": "emoji", "value": "▶️"}, url="https://www.youtube.com"),
                tile("url", "Gmail", {"kind": "builtin", "value": "mail"}, url="https://mail.google.com"),
                tile("file", "Téléchargements", {"kind": "builtin", "value": "download"},
                     path=str(Path.home() / "Downloads")),
                tile("page", "Retour", {"kind": "builtin", "value": "arrow-left"}, bg="#11806a", target=0),
                {**tile("volume", "Volume"), "span": 4}]},
        ],
    }


def _num(v, lo, hi, default):
    try:
        v = float(v)
    except (TypeError, ValueError):
        return default
    v = max(lo, min(hi, v))
    return int(v) if isinstance(default, int) and not isinstance(default, bool) else v


def _clean_section(src, defaults):
    out = {}
    src = src if isinstance(src, dict) else {}
    for k, d in defaults.items():
        v = src.get(k, d)
        if isinstance(d, bool):
            out[k] = bool(v)
        elif k in NUMERIC_LIMITS:
            out[k] = _num(v, *NUMERIC_LIMITS[k], d)
        elif k in ENUMS:
            out[k] = v if v in ENUMS[k] else d
        elif isinstance(d, str) and d.startswith("#"):
            out[k] = v if isinstance(v, str) and COLOR_RE.match(v) else d
        else:
            out[k] = str(v)[:30]
    return out


def _clean_icon(icon):
    if not isinstance(icon, dict) or icon.get("kind") not in ICON_KINDS:
        return {"kind": "auto", "value": ""}
    kind, value = icon["kind"], str(icon.get("value", ""))
    if kind == "builtin":
        value = re.sub(r"[^a-z0-9-]", "", value)[:30]
    elif kind == "emoji":
        value = value[:16]
    elif kind == "image":
        if len(value) > 400_000 or not IMAGE_RE.match(value):
            return {"kind": "auto", "value": ""}
    else:
        value = ""
    return {"kind": kind, "value": value}


def _clean_tile(t, ids: set):
    if not isinstance(t, dict) or t.get("type") not in TILE_TYPES:
        raise ValueError("type de bouton invalide")
    tid = str(t.get("id", ""))[:20]
    if not re.match(r"^[A-Za-z0-9_-]+$", tid) or tid in ids:
        tid = new_id()
    ids.add(tid)
    out = {"id": tid, "type": t["type"], "label": str(t.get("label", ""))[:40],
           "span": int(_num(t.get("span", 1), 1, 8, 1)),
           "bg": t.get("bg") if isinstance(t.get("bg"), str) and COLOR_RE.match(t.get("bg")) else "",
           "fg": t.get("fg") if isinstance(t.get("fg"), str) and COLOR_RE.match(t.get("fg")) else "",
           "icon": _clean_icon(t.get("icon"))}
    typ = t["type"]
    if typ == "app":
        app = t.get("app") if isinstance(t.get("app"), dict) else {}
        out["app"] = {"id": str(app.get("id", ""))[:600], "name": str(app.get("name", ""))[:80]}
    elif typ == "file":
        out["path"] = str(t.get("path", ""))[:600]
    elif typ == "url":
        url = str(t.get("url", ""))[:2000]
        if url and not re.match(r"^https?://", url, re.I):
            raise ValueError("l'adresse web doit commencer par http:// ou https://")
        out["url"] = url
    elif typ == "hotkey":
        keys = str(t.get("keys", ""))[:60]
        if keys:
            parse_hotkey(keys)
        out["keys"] = keys
    elif typ == "page":
        out["target"] = int(_num(t.get("target", 0), 0, 49, 0))
    return out


def clean_config(cfg: dict, pin: str) -> dict:
    if not isinstance(cfg, dict):
        raise ValueError("configuration invalide")
    pages = cfg.get("pages")
    if not isinstance(pages, list) or not 1 <= len(pages) <= 50:
        raise ValueError("il faut entre 1 et 50 pages")
    ids: set = set()
    clean_pages = []
    for p in pages:
        if not isinstance(p, dict):
            raise ValueError("page invalide")
        tiles = p.get("tiles", [])
        if not isinstance(tiles, list) or len(tiles) > 80:
            raise ValueError("80 boutons maximum par page")
        clean_pages.append({"name": str(p.get("name", "Page"))[:30] or "Page",
                            "cols": int(_num(p.get("cols", 4), 1, 8, 4)),
                            "tiles": [_clean_tile(t, ids) for t in tiles]})
    return {"version": 2, "pin": pin, "auto_matched": bool(cfg.get("auto_matched", False)),
            "match_rev": int(_num(cfg.get("match_rev", 0), 0, 99, 0)),
            "volume_step": int(_num(cfg.get("volume_step", 4), 1, 20, 4)),
            "theme": _clean_section(cfg.get("theme"), DEFAULT_THEME),
            "clock": _clean_section(cfg.get("clock"), DEFAULT_CLOCK),
            "pages": clean_pages}


class ConfigStore:
    def __init__(self, path: Path):
        self.path = path
        self.lock = threading.Lock()
        self.rev = int(time.time())
        raw = json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {}
        if raw.get("version") != 2:
            if path.is_file():
                path.with_suffix(".v1.bak").write_text(path.read_text(encoding="utf-8"), encoding="utf-8")
                log("Ancienne configuration convertie (copie : config.v1.bak)")
            raw = default_config(raw.get("apps"))
        pin = str(raw.get("pin", "")) if re.match(r"^\d{4,8}$", str(raw.get("pin", ""))) \
            else f"{random.randint(0, 9999):04d}"
        try:
            self.cfg = clean_config(raw, pin)
        except ValueError as e:
            log("config.json invalide, configuration par défaut utilisée :", e)
            self.cfg = clean_config(default_config(), pin)
        self._write()

    def _write(self):
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(self.cfg, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(tmp, self.path)

    @property
    def pin(self):
        return self.cfg["pin"]

    def public(self):
        with self.lock:
            c = copy.deepcopy(self.cfg)
        c.pop("pin", None)
        c["rev"] = self.rev
        return c

    def save(self, new_cfg: dict):
        cleaned = clean_config(new_cfg, self.pin)
        with self.lock:
            self.cfg = cleaned
            self.rev += 1
            self._write()

    def find_tile(self, tid: str):
        with self.lock:
            for p in self.cfg["pages"]:
                for t in p["tiles"]:
                    if t["id"] == tid:
                        return copy.deepcopy(t)
        return None

    def launch_tiles(self):
        """Boutons « lanceurs » dans l'ordre des pages (pour APP:1..4 du boîtier USB)."""
        with self.lock:
            return [copy.deepcopy(t) for p in self.cfg["pages"] for t in p["tiles"]
                    if t["type"] in ("app", "file", "url", "hotkey")]

    def auto_match(self, catalog: "AppCatalog"):
        """Une seule fois : remplace les lanceurs « commande » (chrome, spotify:…) par
        l'application installée du même nom, pour afficher sa vraie icône."""
        if self.cfg.get("match_rev", 0) < 2:          # v2.1 : Chrome -> Brave
            with self.lock:
                for page in self.cfg["pages"]:
                    for i, t in enumerate(page["tiles"]):
                        if t["label"].strip().lower() in ("chrome", "google chrome"):
                            new = {k: v for k, v in t.items() if k not in ("app", "path")}
                            new.update(type="file", label="Brave", path="brave", icon={"kind": "auto", "value": ""})
                            page["tiles"][i] = new
                            self.cfg["auto_matched"] = False
                self.cfg["match_rev"] = 2
                self.rev += 1
                self._write()
        if self.cfg.get("auto_matched"):
            return
        apps = catalog.list()
        if not apps:
            return
        aliases = {"vs code": "visual studio code", "vscode": "visual studio code"}
        changed = 0
        with self.lock:
            for page in self.cfg["pages"]:
                for i, t in enumerate(page["tiles"]):
                    path = t.get("path", "")
                    is_real_path = re.search(r"[\\/]", path) and not re.match(r"^[a-z][a-z0-9+.-]+:", path, re.I)
                    if t["type"] != "file" or is_real_path:
                        continue
                    want = aliases.get(t["label"].strip().lower(), t["label"].strip().lower())
                    if len(want) < 3:
                        continue
                    best = None
                    for a in apps:
                        name = a["name"].lower()
                        if name == want:
                            best = a
                            break
                        if want in name and (best is None or len(name) < len(best["name"])):
                            best = a
                    if best:
                        new = {k: v for k, v in t.items() if k != "path"}
                        new.update(type="app", app={"id": best["id"], "name": best["name"]})
                        page["tiles"][i] = new
                        changed += 1
            self.cfg["auto_matched"] = True
            if changed:
                self.rev += 1
            self._write()
        if changed:
            log(f"{changed} bouton(s) relié(s) aux applications installées (icônes réelles)")

    def icon_refs(self):
        with self.lock:
            refs = set()
            for p in self.cfg["pages"]:
                for t in p["tiles"]:
                    if t["type"] == "app" and t["app"]["id"]:
                        refs.add(("app", t["app"]["id"]))
                    elif t["type"] == "file" and t.get("path"):
                        refs.add(("file", t["path"]))
            return refs


# =====================================================================
#  Moteur : exécute les actions dans un seul thread
# =====================================================================
def open_target(target: str):
    if SYSTEM == "Windows":
        try:
            os.startfile(target)
        except OSError:
            subprocess.Popen(target, shell=True)      # ex. « code » (script .cmd du PATH)
    elif SYSTEM == "Darwin":
        if "://" in target or target.endswith(":") or os.path.exists(target):
            subprocess.Popen(["open", target])
        else:
            subprocess.Popen(["open", "-a", target])
    else:
        if "://" in target or os.path.exists(target):
            subprocess.Popen(["xdg-open", target], start_new_session=True)
        else:
            subprocess.Popen(shlex.split(target), start_new_session=True)


class Engine(threading.Thread):
    def __init__(self, store: ConfigStore, catalog: AppCatalog):
        super().__init__(daemon=True)
        self.store = store
        self.catalog = catalog
        self.jobs: "queue.Queue[tuple]" = queue.Queue()
        self.state = {"volume": None, "muted": False}
        self.lock = threading.Lock()

    def submit(self, *job):
        self.jobs.put(job)

    def snapshot(self):
        with self.lock:
            return dict(self.state)

    def run(self):
        if SYSTEM == "Windows":
            try:
                import comtypes
                comtypes.CoInitialize()
            except Exception:
                pass
        vol = make_volume()
        while True:
            try:
                job = self.jobs.get(timeout=0.3)
                self.execute(job, vol)
            except queue.Empty:
                pass
            except Exception as e:
                log("Erreur action :", e)
            info = vol.get()
            with self.lock:
                if info:
                    self.state["volume"], self.state["muted"] = info

    def execute(self, job, vol: Volume):
        kind = job[0]
        step = self.store.cfg.get("volume_step", 4)
        if kind == "volset":
            vol.set(int(job[1]))
            return
        if kind == "cmd":
            cmd = job[1]
            if cmd.startswith("APP:"):
                tiles = self.store.launch_tiles()
                idx = int(cmd[4:]) - 1
                if 0 <= idx < len(tiles):
                    self.run_tile(tiles[idx], vol, step)
                return
            self.run_tile({"type": {"VOL_UP": "vol_up", "VOL_DOWN": "vol_down", "MUTE": "mute",
                                    "PLAY": "play", "NEXT": "next", "PREV": "prev"}[cmd]}, vol, step)
            return
        if kind == "tile":
            t = self.store.find_tile(job[1])
            if t:
                self.run_tile(t, vol, step)

    def run_tile(self, t, vol: Volume, step: int):
        typ = t["type"]
        if typ == "vol_up":
            vol.step(+step)
        elif typ == "vol_down":
            vol.step(-step)
        elif typ == "mute":
            vol.toggle_mute()
        elif typ in ("play", "next", "prev"):
            media_key(typ.upper())
        elif typ == "app" and t["app"]["id"]:
            log("Lancement :", t["app"]["name"] or t["app"]["id"])
            self.catalog.launch(t["app"]["id"])
        elif typ == "file" and t.get("path"):
            log("Ouverture :", t["path"])
            open_target(t["path"])
        elif typ == "url" and t.get("url"):
            log("Site :", t["url"])
            open_target(t["url"])
        elif typ == "hotkey" and t.get("keys"):
            send_hotkey(parse_hotkey(t["keys"]))


def local_epoch() -> int:
    return calendar.timegm(time.localtime())


# =====================================================================
#  Liaison série avec le boîtier
# =====================================================================
class SerialLink(threading.Thread):
    def __init__(self, engine: Engine, port: str | None):
        super().__init__(daemon=True)
        self.engine = engine
        self.port = port

    def find_port(self):
        from serial.tools import list_ports
        for p in list_ports.comports():
            if p.vid in KNOWN_VIDS:
                return p.device
        return None

    def send_labels(self, ser):
        tiles = self.engine.store.launch_tiles()[:4]
        for i, t in enumerate(tiles, start=1):
            label = (t.get("label") or f"App {i}")[:15]
            ser.write(f"LBL:{i}:{label}\n".encode("ascii", "replace"))

    def run(self):
        import serial
        while True:
            port = self.port or self.find_port()
            if not port:
                time.sleep(2)
                continue
            try:
                with serial.Serial(port, BAUD, timeout=0.1) as ser:
                    log("Boîtier connecté sur", port)
                    self.session(ser)
            except serial.SerialException as e:
                log("Liaison série perdue :", e)
            time.sleep(2)

    def session(self, ser):
        buf = b""
        last_tick, last_sent, labels_at = 0.0, None, time.time() + 2.5
        while True:
            buf += ser.read(64)
            while b"\n" in buf:
                line, buf = buf.split(b"\n", 1)
                msg = line.decode(errors="ignore").strip()
                if msg == "HELLO":
                    labels_at, last_sent = time.time() + 0.3, None
                elif msg in LEGACY_COMMANDS or re.match(r"^APP:[1-9]$", msg):
                    log("Boîtier ->", msg)
                    self.engine.submit("cmd", msg)
            now = time.time()
            if labels_at and now >= labels_at:
                self.send_labels(ser)
                labels_at = 0
            st = self.engine.snapshot()
            current = (st["volume"], st["muted"])
            if now - last_tick >= 1.0 or current != last_sent:
                ser.write(f"TIME:{local_epoch()}\n".encode())
                if st["volume"] is not None:
                    ser.write(f"VOL:{st['volume']}\nMUTE:{int(st['muted'])}\n".encode())
                last_tick, last_sent = now, current


# =====================================================================
#  Serveur web
# =====================================================================
STATIC_FILES = {"index.html", "style.css", "app.js", "icons.js", "manifest.webmanifest", "icon.svg"}
MAX_BODY = 8 * 1024 * 1024


class AuthGuard:
    """Code PIN + blocage temporaire après 5 essais ratés."""

    def __init__(self, store: ConfigStore):
        self.store = store
        self.fails: list[float] = []
        self.lock = threading.Lock()

    def check(self, pin: str | None) -> bool:
        with self.lock:
            now = time.time()
            self.fails = [t for t in self.fails if now - t < 60]
            if len(self.fails) >= 5:
                return False
            ok = bool(pin) and hmac.compare_digest(str(pin), self.store.pin)
            if not ok:
                self.fails.append(now)
            return ok


def make_handler(engine: Engine, store: ConfigStore, catalog: AppCatalog,
                 icons: IconService, guard: AuthGuard):

    class Handler(BaseHTTPRequestHandler):
        server_version = "StreamDeckPython/2"

        def _send(self, code, body, ctype="application/json", cache="no-store"):
            data = body if isinstance(body, (bytes, bytearray)) else (
                body.encode() if isinstance(body, str) else json.dumps(body, ensure_ascii=False).encode())
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", cache)
            self.send_header("X-Content-Type-Options", "nosniff")
            self.end_headers()
            self.wfile.write(data)

        def _json_body(self):
            n = int(self.headers.get("Content-Length") or 0)
            if n > MAX_BODY:
                raise ValueError("requête trop volumineuse")
            return json.loads(self.rfile.read(n) or b"{}")

        def _authed(self):
            return guard.check(self.headers.get("X-Pin"))

        # ---------------- GET ----------------
        def do_GET(self):
            url = urlparse(self.path)
            q = parse_qs(url.query)
            path = url.path
            if path in ("/", "/index.html"):
                return self._static("index.html")
            if path.lstrip("/") in STATIC_FILES:
                return self._static(path.lstrip("/"))
            if path == "/api/config":
                return self._send(200, store.public())
            if path == "/api/state":
                st = engine.snapshot()
                st["rev"] = store.rev
                st["time"] = local_epoch()
                return self._send(200, st)
            if path == "/api/apps":
                if not self._authed():
                    return self._send(403, {"error": "PIN incorrect"})
                return self._send(200, catalog.public() if not q.get("refresh") else
                                  [{"id": a["id"], "name": a["name"]} for a in catalog.list(refresh=True)])
            if path == "/api/icon":
                kind = q.get("kind", ["app"])[0]
                ident = q.get("id", [""])[0]
                allowed = (kind, ident) in store.icon_refs() or (kind == "app" and ident in catalog.by_id)
                if not allowed:
                    return self._send(404, {"error": "inconnu"})
                res = icons.get(kind, ident)
                if not res:
                    return self._send(404, {"error": "pas d'icône"})
                return self._send(200, res[0], res[1], cache="max-age=86400")
            self._send(404, {"error": "introuvable"})

        def _static(self, name):
            f = WEB_DIR / name
            if not f.is_file():
                return self._send(404, "introuvable", "text/plain")
            ctype = mimetypes.guess_type(name)[0] or "application/octet-stream"
            if name.endswith(".webmanifest"):
                ctype = "application/manifest+json"
            if ctype.startswith("text/") or ctype.endswith("javascript"):
                ctype += "; charset=utf-8"
            self._send(200, f.read_bytes(), ctype)

        # ---------------- POST ----------------
        def do_POST(self):
            path = urlparse(self.path).path
            try:
                body = self._json_body()
            except Exception:
                return self._send(400, {"error": "JSON invalide"})
            if path == "/api/press":
                tid = str(body.get("id", ""))
                if not store.find_tile(tid):
                    return self._send(404, {"error": "bouton inconnu"})
                engine.submit("tile", tid)
                return self._send(200, {"ok": True})
            if path == "/api/volume":
                try:
                    level = max(0, min(100, int(body.get("level"))))
                except (TypeError, ValueError):
                    return self._send(400, {"error": "niveau invalide"})
                engine.submit("volset", level)
                return self._send(200, {"ok": True})
            if path == "/api/auth":
                return self._send(200, {"ok": guard.check(body.get("pin"))})
            if path == "/api/config":
                if not self._authed():
                    return self._send(403, {"error": "PIN incorrect"})
                try:
                    store.save(body.get("config"))
                except (ValueError, TypeError, KeyError) as e:
                    return self._send(400, {"error": str(e)})
                log("Configuration enregistrée depuis", self.client_address[0])
                return self._send(200, {"ok": True, "rev": store.rev})
            self._send(404, {"error": "introuvable"})

        def log_message(self, *args):
            pass

    return Handler


def lan_ip() -> str:
    import socket
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("10.255.255.255", 1))
        return s.getsockname()[0]
    except Exception:
        return "127.0.0.1"
    finally:
        s.close()


# =====================================================================
def main():
    ap = argparse.ArgumentParser(
        description="StreamDeck Python : télécommande tactile pour ton PC (téléphone, tablette ou navigateur).")
    ap.add_argument("--web-port", type=int, default=8765, help="port de l'interface web (défaut : 8765)")
    ap.add_argument("--host", default="0.0.0.0",
                    help="adresse d'écoute (défaut : tout le réseau local ; 127.0.0.1 = ce PC uniquement)")
    ap.add_argument("--open", action="store_true", help="ouvre l'interface dans le navigateur de ce PC")
    ap.add_argument("--config", default=str(HERE / "config.json"), help="fichier de configuration")
    ap.add_argument("--serial", action="store_true", help="active aussi un boîtier USB (ESP32 / Arduino)")
    ap.add_argument("--port", help="port série du boîtier USB (ex. COM5) ; implique --serial")
    ap.add_argument("--no-web", action="store_true", help="désactive l'interface web (boîtier USB seul)")
    # options des versions précédentes, conservées pour compatibilité
    ap.add_argument("--web", action="store_true", help=argparse.SUPPRESS)
    ap.add_argument("--no-serial", action="store_true", help=argparse.SUPPRESS)
    args = ap.parse_args()

    use_web = not args.no_web
    use_serial = (args.serial or bool(args.port) or (args.web and not args.no_serial)) and not args.no_serial
    if not use_web and not use_serial:
        sys.exit("Rien à faire : retire --no-web ou ajoute --serial")

    store = ConfigStore(Path(args.config))
    catalog = AppCatalog()
    engine = Engine(store, catalog)
    engine.start()
    icons = IconService(catalog)
    icons.start()
    threading.Thread(target=lambda: store.auto_match(catalog), daemon=True).start()  # applis + icônes

    if use_serial:
        try:
            import serial  # noqa: F401
        except ImportError:
            sys.exit("pyserial manquant : pip install pyserial")
        SerialLink(engine, args.port).start()
        log("Recherche du boîtier USB...")

    if use_web:
        handler = make_handler(engine, store, catalog, icons, AuthGuard(store))
        try:
            server = ThreadingHTTPServer((args.host, args.web_port), handler)
        except OSError as e:
            sys.exit(f"Port {args.web_port} indisponible ({e}). Le script tourne peut-être déjà ?")
        threading.Thread(target=server.serve_forever, daemon=True).start()
        local_url = f"http://localhost:{args.web_port}"
        log(f"Sur ce PC             : {local_url}")
        if args.host != "127.0.0.1":
            log(f"Téléphone / tablette  : http://{lan_ip()}:{args.web_port}  (même réseau WiFi)")
        log(f"Code PIN (paramètres) : {store.pin}   (modifiable dans config.json)")
        log("Ctrl+C pour arrêter.")
        if args.open:
            import webbrowser
            webbrowser.open(local_url)

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        log("Arrêt.")


if __name__ == "__main__":
    main()
