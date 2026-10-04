"""Lecture des fichiers du jeu installé : main.scm (collectibles) et gta3.img (carte radar)."""

import io
import json
import os
import struct
import winreg
from pathlib import Path

from PIL import Image

MAP_TILES = 12            # la carte radar fait 12 x 12 tuiles
TILE_PX = 128
WORLD_HALF = 3000.0       # le monde va de -3000 à +3000 sur les deux axes

# Opcodes du main.scm qui créent les collectibles (x, y, z en flottants)
COLLECTIBLE_OPCODES = {0x0958: "snapshots", 0x0959: "horseshoes", 0x095A: "oysters"}


def app_dir() -> Path:
    base = Path(os.environ.get("APPDATA", Path.home())) / "GTASA_Checklist"
    base.mkdir(parents=True, exist_ok=True)
    return base


def load_json(name: str, default):
    path = app_dir() / name
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return default


def save_json(name: str, data) -> None:
    path = app_dir() / name
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    tmp.replace(path)


def is_game_dir(path: str | Path | None) -> bool:
    return bool(path) and (Path(path) / "data" / "script" / "main.scm").is_file()


def find_game_dir() -> str | None:
    """Cherche le dossier d'installation (réglage, registre, emplacements courants)."""
    saved = load_json("settings.json", {}).get("game_dir")
    if is_game_dir(saved):
        return saved

    candidates = []
    reg_keys = [
        (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\Rockstar Games\GTA San Andreas\Installation", "ExePath"),
        (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Rockstar Games\GTA San Andreas\Installation", "ExePath"),
        (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\Rockstar Games\Grand Theft Auto San Andreas", "InstallFolder"),
        (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall\Steam App 12120", "InstallLocation"),
    ]
    for hive, key, value in reg_keys:
        try:
            with winreg.OpenKey(hive, key) as k:
                v = str(winreg.QueryValueEx(k, value)[0]).strip('"')
                candidates.append(Path(v).parent if v.lower().endswith(".exe") else Path(v))
        except OSError:
            pass
    for drive in "CDEFG":
        for sub in (r"Rockstar Games\Grand Theft Auto San Andreas", r"Rockstar Games\GTA San Andreas",
                    r"Program Files (x86)\Rockstar Games\GTA San Andreas",
                    r"Program Files\Rockstar Games\GTA San Andreas",
                    r"Program Files (x86)\Steam\steamapps\common\Grand Theft Auto San Andreas",
                    r"Games\GTA San Andreas"):
            candidates.append(Path(f"{drive}:\\") / sub)
    for c in candidates:
        if is_game_dir(c):
            return str(c)
    return None


def saves_dir() -> Path:
    docs = Path.home() / "Documents"
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                            r"Software\Microsoft\Windows\CurrentVersion\Explorer\User Shell Folders") as k:
            docs = Path(os.path.expandvars(winreg.QueryValueEx(k, "Personal")[0]))
    except OSError:
        pass
    return docs / "GTA San Andreas User Files"


# ---------------------------------------------------------------- main.scm

def extract_collectibles(main_scm: Path) -> dict[str, list[tuple[float, float, float]]]:
    """Positions des 50 photos, 50 fers à cheval et 50 huîtres (dans l'ordre du script)."""
    data = main_scm.read_bytes()
    out: dict[str, list] = {k: [] for k in COLLECTIBLE_OPCODES.values()}
    for opcode, kind in COLLECTIBLE_OPCODES.items():
        needle = struct.pack("<H", opcode)
        i = data.find(needle)
        while i >= 0:
            p, xyz = i + 2, []
            for _ in range(3):
                if p + 5 > len(data) or data[p] != 0x06:   # 0x06 = flottant immédiat
                    break
                xyz.append(struct.unpack_from("<f", data, p + 1)[0])
                p += 5
            if len(xyz) == 3 and all(abs(v) < 4000 for v in xyz):
                pt = tuple(xyz)
                if pt not in out[kind]:
                    out[kind].append(pt)
            i = data.find(needle, i + 1)
    return out


def scm_signature(main_scm: Path) -> tuple[int, bytes] | None:
    """Décalage et octets du segment des modèles : invariant, sert à retrouver
    l'espace script dans la mémoire du jeu."""
    try:
        with open(main_scm, "rb") as f:
            head = f.read(16)
            if head[:3] != b"\x02\x00\x01":
                return None
            seg2 = struct.unpack_from("<i", head, 3)[0]
            f.seek(seg2)
            needle = f.read(64)
        return (seg2, needle) if len(needle) == 64 else None
    except OSError:
        return None


# ------------------------------------------------------------- carte radar

def _img_entries(img: Path) -> dict[str, tuple[int, int]]:
    with open(img, "rb") as f:
        head = f.read(8)
        if head[:4] != b"VER2":
            raise ValueError("Archive IMG non reconnue (VER2 attendu)")
        count = struct.unpack_from("<I", head, 4)[0]
        raw = f.read(32 * count)
    entries = {}
    for i in range(count):
        offset, streaming, archive = struct.unpack_from("<IHH", raw, 32 * i)
        name = raw[32 * i + 8:32 * i + 32].split(b"\0")[0].decode("latin-1").lower()
        entries[name] = (offset * 2048, (streaming or archive) * 2048)
    return entries


def _decode_texture(txd: bytes) -> Image.Image:
    """Première texture d'un TXD PC (D3D8/D3D9), DXT ou non compressée."""
    if struct.unpack_from("<I", txd, 0)[0] != 0x16:
        raise ValueError("TXD invalide")
    o = 12
    o += 12 + struct.unpack_from("<I", txd, o + 4)[0]       # struct du dictionnaire
    if struct.unpack_from("<I", txd, o)[0] != 0x15:
        raise ValueError("Texture native absente")
    o += 12                                                  # en-tête texture native
    o += 12                                                  # en-tête struct
    platform = struct.unpack_from("<I", txd, o)[0]
    raster_fmt = struct.unpack_from("<I", txd, o + 72)[0]
    fourcc = txd[o + 76:o + 80]
    width, height, depth, _levels, _rtype, flags = struct.unpack_from("<HHBBBB", txd, o + 80)
    p = o + 88
    size = struct.unpack_from("<I", txd, p)[0]
    pixels = txd[p + 4:p + 4 + size]

    if platform == 8:                                        # D3D8 : DXT dans "flags"
        fourcc = {1: b"DXT1", 3: b"DXT3", 5: b"DXT5"}.get(flags, b"\0\0\0\0")
    if fourcc in (b"DXT1", b"DXT3", b"DXT5"):
        dds = struct.pack("<4sIIIIIII44xII4sIIIII5I", b"DDS ", 124, 0x81007, height, width,
                          len(pixels), 0, 1, 32, 4, fourcc, 0, 0, 0, 0, 0, 0x1000, 0, 0, 0, 0)
        return Image.open(io.BytesIO(dds + pixels)).convert("RGB")
    if depth == 32:
        return Image.frombuffer("RGBA", (width, height), pixels, "raw", "BGRA", 0, 1).convert("RGB")
    raise ValueError(f"Format de texture non géré ({raster_fmt:#x}, {fourcc!r})")


def build_radar_map(game_dir: str, out: Path) -> Path:
    img_path = Path(game_dir) / "models" / "gta3.img"
    entries = _img_entries(img_path)
    size = MAP_TILES * TILE_PX
    canvas = Image.new("RGB", (size, size), (98, 132, 166))
    with open(img_path, "rb") as f:
        for k in range(MAP_TILES * MAP_TILES):
            entry = entries.get(f"radar{k:02d}.txd")
            if not entry:
                continue
            f.seek(entry[0])
            try:
                tile = _decode_texture(f.read(entry[1]))
            except (ValueError, OSError, struct.error):
                continue
            if tile.size != (TILE_PX, TILE_PX):
                tile = tile.resize((TILE_PX, TILE_PX))
            canvas.paste(tile, ((k % MAP_TILES) * TILE_PX, (k // MAP_TILES) * TILE_PX))
    # Agrandissement x2 lissé pour un zoom plus agréable
    canvas = canvas.resize((size * 2, size * 2), Image.LANCZOS)
    canvas.save(out)
    return out


# --------------------------------------------------- véhicules garés (spawns)

def vehicle_ids(game_dir: str) -> dict[str, int]:
    """Nom du modèle (vehicles.ide) -> identifiant."""
    ids = {}
    text = (Path(game_dir) / "data" / "vehicles.ide").read_text(encoding="latin-1")
    for line in text.splitlines():
        parts = [p.strip() for p in line.split("#")[0].split(",")]
        if len(parts) > 4 and parts[0].isdigit():
            ids.setdefault(parts[1].lower(), int(parts[0]))
    return ids


def _scm_params(data: bytes, p: int, count: int) -> list | None:
    """Lit `count` paramètres typés d'une instruction SCM (None si format inattendu)."""
    values = []
    for _ in range(count):
        t = data[p]
        if t == 0x01:
            values.append(struct.unpack_from("<i", data, p + 1)[0]); p += 5
        elif t in (0x02, 0x03):                                  # variable : valeur inconnue
            values.append(None); p += 3
        elif t == 0x04:
            values.append(struct.unpack_from("<b", data, p + 1)[0]); p += 2
        elif t == 0x05:
            values.append(struct.unpack_from("<h", data, p + 1)[0]); p += 3
        elif t == 0x06:
            values.append(struct.unpack_from("<f", data, p + 1)[0]); p += 5
        else:
            return None
    return values


def extract_car_generators(game_dir: str) -> list[tuple[float, float, float, int, str]]:
    """Tous les générateurs de véhicules garés : (x, y, z, modèle, source).

    source = "script" (main.scm, opcode 014B : certains ne s'activent qu'à une
    étape de l'histoire) ou "carte" (sections cars des IPL : toujours actifs).
    """
    gens = []
    data = (Path(game_dir) / "data" / "script" / "main.scm").read_bytes()
    i = data.find(b"\x4b\x01")
    while i >= 0:
        try:
            v = _scm_params(data, i + 2, 12)
        except (IndexError, struct.error):
            v = None
        if v and all(isinstance(c, float) and abs(c) < 4000 for c in v[:3]) \
                and isinstance(v[4], int) and 400 <= v[4] <= 611:
            gens.append((v[0], v[1], v[2], v[4], "script"))
        i = data.find(b"\x4b\x01", i + 1)

    for ipl in (Path(game_dir) / "data" / "maps").rglob("*.ipl"):
        in_cars = False
        for line in ipl.read_text(encoding="latin-1").splitlines():
            s = line.split("#")[0].strip()
            if s in ("cars", "end"):
                in_cars = s == "cars"
            elif in_cars and s:
                parts = [p.strip() for p in s.split(",")]
                try:
                    gens.append((float(parts[0]), float(parts[1]), float(parts[2]),
                                 int(parts[4]), "carte"))
                except (ValueError, IndexError):
                    pass

    # IPL binaires (« bnry ») rangés dans gta3.img
    img = Path(game_dir) / "models" / "gta3.img"
    with open(img, "rb") as f:
        for name, (offset, size) in _img_entries(img).items():
            if not name.endswith(".ipl"):
                continue
            f.seek(offset)
            raw = f.read(size)
            if raw[:4] != b"bnry":
                continue
            count, start = struct.unpack_from("<i", raw, 20)[0], struct.unpack_from("<i", raw, 0x3C)[0]
            for k in range(max(0, count)):
                if start + 48 * (k + 1) > len(raw):
                    break
                x, y, z, _angle, model = struct.unpack_from("<4fi", raw, start + 48 * k)
                gens.append((x, y, z, model, "carte"))
    return gens


def extract_export_spawns(game_dir: str, models: list[str]) -> dict[str, list]:
    """Points d'apparition des véhicules demandés : {modèle: [[x, y, z, source], ...]}."""
    ids = vehicle_ids(game_dir)
    wanted = {ids[m]: m for m in models if m in ids}
    out: dict[str, list] = {m: [] for m in models}
    for x, y, z, model, source in extract_car_generators(game_dir):
        if model in wanted:
            spot = [round(x, 1), round(y, 1), round(z, 1), source]
            if spot not in out[wanted[model]]:
                out[wanted[model]].append(spot)
    for spots in out.values():
        spots.sort(key=lambda s: s[3] != "carte")             # toujours actifs d'abord
    return out


def world_to_map(x: float, y: float, map_size: float) -> tuple[float, float]:
    s = map_size / (2 * WORLD_HALF)
    return (x + WORLD_HALF) * s, (WORLD_HALF - y) * s


def map_to_world(px: float, py: float, map_size: float) -> tuple[float, float]:
    s = map_size / (2 * WORLD_HALF)
    return px / s - WORLD_HALF, WORLD_HALF - py / s
