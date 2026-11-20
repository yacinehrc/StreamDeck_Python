"""
winshell.py — fonctions Windows sans dépendance (ctypes uniquement) :

  * list_start_apps()  : toutes les applis du menu Démarrer (classiques + Microsoft Store)
  * launch_app(app_id) : lance une appli de cette liste
  * icon_png(name)     : icône réelle d'une appli ou d'un fichier, en PNG (jusqu'à 256 px)
  * hotkey(keys)       : envoie un raccourci clavier (ex. ["ctrl", "shift", "m"])

Les fonctions d'icônes utilisent COM : appelle com_init() une fois dans le thread
qui les utilise.
"""
from __future__ import annotations

import ctypes
import json
import os
import struct
import subprocess
import zlib
from ctypes import wintypes

CREATE_NO_WINDOW = 0x08000000

# =====================================================================
#  Liste et lancement des applications
# =====================================================================
_SKIP_WORDS = ("uninstall", "désinstall", "desinstall", "readme", "read me", "release notes")
_SKIP_EXT = (".url", ".txt", ".chm", ".htm", ".html", ".pdf", ".rtf", ".ini")


def list_start_apps() -> list[dict]:
    """[{id, name}] via la commande PowerShell Get-StartApps (Windows 10/11)."""
    script = ("[Console]::OutputEncoding=[Text.Encoding]::UTF8;"
              "Get-StartApps | Select-Object Name,AppID | ConvertTo-Json -Compress")
    out = subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", script],
                         capture_output=True, timeout=40, creationflags=CREATE_NO_WINDOW)
    text = out.stdout.decode("utf-8-sig", errors="replace").strip() or "[]"
    data = json.loads(text)
    if isinstance(data, dict):
        data = [data]
    apps, seen = [], set()
    for item in data:
        name, app_id = item.get("Name"), item.get("AppID")
        if not name or not app_id or app_id in seen:
            continue
        low = f"{name} {app_id}".lower()
        if any(w in low for w in _SKIP_WORDS):
            continue
        if app_id.lower().startswith(("http://", "https://")) or app_id.lower().endswith(_SKIP_EXT):
            continue
        seen.add(app_id)
        apps.append({"id": app_id, "name": name})
    apps.sort(key=lambda a: a["name"].lower())
    return apps


def launch_app(app_id: str):
    try:
        os.startfile("shell:AppsFolder\\" + app_id)
    except OSError:
        subprocess.Popen(["explorer.exe", "shell:AppsFolder\\" + app_id])


# =====================================================================
#  Raccourcis clavier
# =====================================================================
_VK = {"ctrl": 0x11, "shift": 0x10, "alt": 0x12, "win": 0x5B,
       "esc": 0x1B, "enter": 0x0D, "tab": 0x09, "space": 0x20, "backspace": 0x08,
       "delete": 0x2E, "insert": 0x2D, "home": 0x24, "end": 0x23, "pageup": 0x21,
       "pagedown": 0x22, "up": 0x26, "down": 0x28, "left": 0x25, "right": 0x27,
       "printscreen": 0x2C, "pause": 0x13, "capslock": 0x14, "numlock": 0x90,
       "volumeup": 0xAF, "volumedown": 0xAE, "volumemute": 0xAD, "playpause": 0xB3,
       "nexttrack": 0xB0, "prevtrack": 0xB1, "-": 0xBD, "=": 0xBB, ",": 0xBC, ".": 0xBE,
       ";": 0xBA, "/": 0xBF}
_EXTENDED = {0x5B, 0x2E, 0x2D, 0x24, 0x23, 0x21, 0x22, 0x26, 0x28, 0x25, 0x27, 0x2C}


def vk_code(key: str) -> int | None:
    if key in _VK:
        return _VK[key]
    if len(key) == 1 and key.isalnum():
        return ord(key.upper())
    if key.startswith("f") and key[1:].isdigit() and 1 <= int(key[1:]) <= 24:
        return 0x70 + int(key[1:]) - 1
    return None


def hotkey(keys: list[str]):
    user32 = ctypes.windll.user32
    codes = [vk_code(k) for k in keys]
    if None in codes:
        raise ValueError(f"touche inconnue dans {keys}")
    for vk in codes:
        user32.keybd_event(vk, 0, 1 if vk in _EXTENDED else 0, 0)
    for vk in reversed(codes):
        user32.keybd_event(vk, 0, (1 if vk in _EXTENDED else 0) | 2, 0)


# =====================================================================
#  Icônes -> PNG
# =====================================================================
class GUID(ctypes.Structure):
    _fields_ = [("Data1", wintypes.DWORD), ("Data2", wintypes.WORD),
                ("Data3", wintypes.WORD), ("Data4", ctypes.c_ubyte * 8)]


class SHFILEINFOW(ctypes.Structure):
    _fields_ = [("hIcon", ctypes.c_void_p), ("iIcon", ctypes.c_int),
                ("dwAttributes", wintypes.DWORD), ("szDisplayName", wintypes.WCHAR * 260),
                ("szTypeName", wintypes.WCHAR * 80)]


class ICONINFO(ctypes.Structure):
    _fields_ = [("fIcon", wintypes.BOOL), ("xHotspot", wintypes.DWORD),
                ("yHotspot", wintypes.DWORD), ("hbmMask", ctypes.c_void_p),
                ("hbmColor", ctypes.c_void_p)]


class BITMAP(ctypes.Structure):
    _fields_ = [("bmType", wintypes.LONG), ("bmWidth", wintypes.LONG),
                ("bmHeight", wintypes.LONG), ("bmWidthBytes", wintypes.LONG),
                ("bmPlanes", wintypes.WORD), ("bmBitsPixel", wintypes.WORD),
                ("bmBits", ctypes.c_void_p)]


class BITMAPINFOHEADER(ctypes.Structure):
    _fields_ = [("biSize", wintypes.DWORD), ("biWidth", wintypes.LONG),
                ("biHeight", wintypes.LONG), ("biPlanes", wintypes.WORD),
                ("biBitCount", wintypes.WORD), ("biCompression", wintypes.DWORD),
                ("biSizeImage", wintypes.DWORD), ("biXPelsPerMeter", wintypes.LONG),
                ("biYPelsPerMeter", wintypes.LONG), ("biClrUsed", wintypes.DWORD),
                ("biClrImportant", wintypes.DWORD)]


class BITMAPINFO(ctypes.Structure):
    _fields_ = [("bmiHeader", BITMAPINFOHEADER), ("bmiColors", wintypes.DWORD * 4)]


class SIZE(ctypes.Structure):
    _fields_ = [("cx", wintypes.LONG), ("cy", wintypes.LONG)]


IID_IShellItemImageFactory = GUID(0xBCC18B79, 0xBA16, 0x442F,
                                  (ctypes.c_ubyte * 8)(0x80, 0xC4, 0x8A, 0x59, 0xC3, 0x0C, 0x46, 0x3B))
SIIGBF_BIGGERSIZEOK, SIIGBF_ICONONLY = 0x1, 0x4
IID_IImageList = GUID(0x46EB5926, 0x582E, 0x4017,
                      (ctypes.c_ubyte * 8)(0x9F, 0xDF, 0xE8, 0x99, 0x8D, 0xAA, 0x09, 0x50))
SHIL_EXTRALARGE, SHIL_JUMBO = 2, 4
SHGFI_PIDL, SHGFI_SYSICONINDEX = 0x8, 0x4000
ILD_TRANSPARENT = 0x1

_api = None


def _load_api():
    global _api
    if _api:
        return _api
    shell32 = ctypes.WinDLL("shell32")
    ole32 = ctypes.WinDLL("ole32")
    user32 = ctypes.WinDLL("user32")
    gdi32 = ctypes.WinDLL("gdi32")
    vp = ctypes.c_void_p
    shell32.SHParseDisplayName.argtypes = [wintypes.LPCWSTR, vp, ctypes.POINTER(vp), wintypes.ULONG, vp]
    shell32.SHParseDisplayName.restype = ctypes.c_long
    shell32.SHGetFileInfoW.argtypes = [vp, wintypes.DWORD, ctypes.POINTER(SHFILEINFOW), wintypes.UINT, wintypes.UINT]
    shell32.SHGetFileInfoW.restype = ctypes.c_size_t
    shell32.SHCreateItemFromParsingName.argtypes = [wintypes.LPCWSTR, vp, ctypes.POINTER(GUID), ctypes.POINTER(vp)]
    shell32.SHCreateItemFromParsingName.restype = ctypes.c_long
    shell32.SHGetImageList.argtypes = [ctypes.c_int, ctypes.POINTER(GUID), ctypes.POINTER(vp)]
    shell32.SHGetImageList.restype = ctypes.c_long
    ole32.CoTaskMemFree.argtypes = [vp]
    ole32.CoInitializeEx.argtypes = [vp, wintypes.DWORD]
    ole32.CoInitializeEx.restype = ctypes.c_long
    user32.GetIconInfo.argtypes = [vp, ctypes.POINTER(ICONINFO)]
    user32.GetIconInfo.restype = wintypes.BOOL
    user32.DestroyIcon.argtypes = [vp]
    user32.GetDC.argtypes = [vp]
    user32.GetDC.restype = vp
    user32.ReleaseDC.argtypes = [vp, vp]
    gdi32.GetObjectW.argtypes = [vp, ctypes.c_int, vp]
    gdi32.GetDIBits.argtypes = [vp, vp, wintypes.UINT, wintypes.UINT, vp, ctypes.POINTER(BITMAPINFO), wintypes.UINT]
    gdi32.GetDIBits.restype = ctypes.c_int
    gdi32.DeleteObject.argtypes = [vp]
    _api = (shell32, ole32, user32, gdi32)
    return _api


def com_init():
    _, ole32, _, _ = _load_api()
    ole32.CoInitializeEx(None, 0x2)          # COINIT_APARTMENTTHREADED


def _dib(hbm, w, h):
    _, _, user32, gdi32 = _load_api()
    bmi = BITMAPINFO()
    bmi.bmiHeader = BITMAPINFOHEADER(40, w, -h, 1, 32, 0, 0, 0, 0, 0, 0)
    buf = (ctypes.c_ubyte * (w * h * 4))()
    hdc = user32.GetDC(None)
    try:
        lines = gdi32.GetDIBits(hdc, hbm, 0, h, buf, ctypes.byref(bmi), 0)
    finally:
        user32.ReleaseDC(None, hdc)
    return bytearray(buf) if lines else None


def _hicon_to_rgba(hicon):
    _, _, user32, gdi32 = _load_api()
    ii = ICONINFO()
    if not user32.GetIconInfo(hicon, ctypes.byref(ii)):
        return None
    try:
        if not ii.hbmColor:
            return None                          # icône monochrome : on ignore
        bm = BITMAP()
        gdi32.GetObjectW(ii.hbmColor, ctypes.sizeof(bm), ctypes.byref(bm))
        w, h = bm.bmWidth, bm.bmHeight
        px = _dib(ii.hbmColor, w, h)
        if px is None:
            return None
        if not any(px[3::4]) and ii.hbmMask:     # pas de canal alpha : on utilise le masque
            mask = _dib(ii.hbmMask, w, h)
            if mask:
                px[3::4] = bytes(0 if m else 255 for m in mask[0::4])
        px[0::4], px[2::4] = px[2::4], px[0::4]  # BGRA -> RGBA
        return px, w, h
    finally:
        if ii.hbmColor:
            gdi32.DeleteObject(ii.hbmColor)
        if ii.hbmMask:
            gdi32.DeleteObject(ii.hbmMask)


def unpremultiply(px: bytearray):
    """Les images du shell sont souvent en alpha prémultiplié : on le retire pour le PNG."""
    for i in range(0, len(px), 4):
        a = px[i + 3]
        if px[i] > a or px[i + 1] > a or px[i + 2] > a:
            return                                   # déjà en alpha « droit »
    for i in range(0, len(px), 4):
        a = px[i + 3]
        if 0 < a < 255:
            px[i] = min(255, px[i] * 255 // a)
            px[i + 1] = min(255, px[i + 1] * 255 // a)
            px[i + 2] = min(255, px[i + 2] * 255 // a)


def _from_image_factory(parse_name: str, size: int = 256):
    """Méthode moderne (celle de l'Explorateur) : IShellItemImageFactory::GetImage.
    Donne le logo en haute définition, y compris pour les applis du Microsoft Store."""
    shell32, _, _, gdi32 = _load_api()
    fac = ctypes.c_void_p()
    if shell32.SHCreateItemFromParsingName(parse_name, None, ctypes.byref(IID_IShellItemImageFactory),
                                           ctypes.byref(fac)) != 0 or not fac.value:
        return None
    vtbl = ctypes.cast(fac, ctypes.POINTER(ctypes.POINTER(ctypes.c_void_p))).contents
    get_image = ctypes.WINFUNCTYPE(ctypes.c_long, ctypes.c_void_p, SIZE, ctypes.c_int,
                                   ctypes.POINTER(ctypes.c_void_p))(vtbl[3])   # GetImage
    release = ctypes.WINFUNCTYPE(ctypes.c_ulong, ctypes.c_void_p)(vtbl[2])
    hbm = ctypes.c_void_p()
    try:
        if get_image(fac, SIZE(size, size), SIIGBF_ICONONLY | SIIGBF_BIGGERSIZEOK, ctypes.byref(hbm)) != 0 \
                or not hbm.value:
            return None
        bm = BITMAP()
        gdi32.GetObjectW(hbm, ctypes.sizeof(bm), ctypes.byref(bm))
        w, h = bm.bmWidth, abs(bm.bmHeight)
        if w <= 0 or h <= 0:
            return None
        px = _dib(hbm, w, h)
        if px is None or not any(px[3::4]):
            return None
        unpremultiply(px)
        px[0::4], px[2::4] = px[2::4], px[0::4]      # BGRA -> RGBA
        return px, w, h
    finally:
        if hbm.value:
            gdi32.DeleteObject(hbm)
        release(fac)


def _from_imagelist(shil, index):
    shell32, _, user32, _ = _load_api()
    piml = ctypes.c_void_p()
    if shell32.SHGetImageList(shil, ctypes.byref(IID_IImageList), ctypes.byref(piml)) != 0 or not piml.value:
        return None
    vtbl = ctypes.cast(piml, ctypes.POINTER(ctypes.POINTER(ctypes.c_void_p))).contents
    get_icon = ctypes.WINFUNCTYPE(ctypes.c_long, ctypes.c_void_p, ctypes.c_int, ctypes.c_uint,
                                  ctypes.POINTER(ctypes.c_void_p))(vtbl[10])      # IImageList::GetIcon
    release = ctypes.WINFUNCTYPE(ctypes.c_ulong, ctypes.c_void_p)(vtbl[2])     # IUnknown::Release
    hicon = ctypes.c_void_p()
    try:
        if get_icon(piml, index, ILD_TRANSPARENT, ctypes.byref(hicon)) != 0 or not hicon.value:
            return None
        return _hicon_to_rgba(hicon)
    finally:
        if hicon.value:
            user32.DestroyIcon(hicon)
        release(piml)


def crop_square(px: bytearray, w: int, h: int, pad: int = 2):
    """Recadre sur la partie visible de l'icône (les petites icônes sont dessinées
    dans un coin de la grande image 256 px) et renvoie un carré."""
    alpha = px[3::4]
    rows = [y for y in range(h) if any(alpha[y * w:(y + 1) * w])]
    if not rows:
        return px, w, h
    y0, y1 = rows[0], rows[-1] + 1
    cols = [x for x in range(w) if any(alpha[y * w + x] for y in range(y0, y1))]
    x0, x1 = cols[0], cols[-1] + 1
    side = max(x1 - x0, y1 - y0) + 2 * pad
    out = bytearray(side * side * 4)
    ox = (side - (x1 - x0)) // 2
    oy = (side - (y1 - y0)) // 2
    for y in range(y0, y1):
        src = px[(y * w + x0) * 4:(y * w + x1) * 4]
        dst = ((oy + y - y0) * side + ox) * 4
        out[dst:dst + len(src)] = src
    return out, side, side


def rgba_to_png(px: bytes, w: int, h: int) -> bytes:
    raw = b"".join(b"\x00" + bytes(px[y * w * 4:(y + 1) * w * 4]) for y in range(h))

    def chunk(tag, data):
        return (struct.pack(">I", len(data)) + tag + data +
                struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF))

    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 6, 0, 0, 0)) +
            chunk(b"IDAT", zlib.compress(raw, 9)) + chunk(b"IEND", b""))


def icon_png(parse_name: str) -> bytes | None:
    """Icône d'un élément du shell : 'shell:AppsFolder\\<AppID>' ou un chemin de fichier."""
    try:
        res = _from_image_factory(parse_name)
        if res:
            return rgba_to_png(*crop_square(*res))
    except Exception:
        pass                                         # on tente l'autre méthode
    shell32, ole32, _, _ = _load_api()
    pidl = ctypes.c_void_p()
    if shell32.SHParseDisplayName(parse_name, None, ctypes.byref(pidl), 0, None) != 0 or not pidl.value:
        return None
    try:
        info = SHFILEINFOW()
        if not shell32.SHGetFileInfoW(pidl, 0, ctypes.byref(info), ctypes.sizeof(info),
                                      SHGFI_PIDL | SHGFI_SYSICONINDEX):
            return None
        index = info.iIcon
    finally:
        ole32.CoTaskMemFree(pidl)
    for shil in (SHIL_JUMBO, SHIL_EXTRALARGE):
        res = _from_imagelist(shil, index)
        if res:
            return rgba_to_png(*crop_square(*res))
    return None
