"""Lecture d'une sauvegarde PC (GTASAsf1.b ... GTASAsf8.b).

Format documenté sur https://gtamods.com/wiki/Saves_(GTA_SA) : 28 blocs
préfixés par "BLOCK", identiques pour toutes les versions PC.
"""

import struct
from datetime import datetime
from pathlib import Path

from .model import Pickup, Snapshot, Tag

BLOCK = b"BLOCK"
SAVE_SIZE = 0x31800
B_SIMPLE, B_SCRIPT, B_PICKUPS, B_STATS, B_TAGS = 0, 1, 6, 16, 20


def _split_blocks(data: bytes) -> list[bytes]:
    starts = []
    i = data.find(BLOCK)
    while i >= 0 and len(starts) < 28:
        starts.append(i + len(BLOCK))
        i = data.find(BLOCK, i + len(BLOCK))
    blocks = []
    for n, s in enumerate(starts):
        end = starts[n + 1] - len(BLOCK) if n + 1 < len(starts) else len(data)
        blocks.append(data[s:end])
    return blocks


def list_saves(folder: Path) -> list[Path]:
    saves = [p for p in folder.glob("GTASAsf*.b") if p.is_file()]
    return sorted(saves, key=lambda p: p.stat().st_mtime, reverse=True)


def read_save(path: Path) -> Snapshot:
    data = path.read_bytes()
    if len(data) < 0x1000 or not data.startswith(BLOCK):
        raise ValueError(f"{path.name} n'est pas une sauvegarde GTA SA")
    blocks = _split_blocks(data)
    if len(blocks) < 25:
        raise ValueError(f"{path.name} : sauvegarde incomplète ({len(blocks)} blocs)")

    simple = blocks[B_SIMPLE]
    name = simple[4:104].split(b"\0")[0].decode("latin-1", "replace").strip()
    snap = Snapshot(source="save", label="")

    # Caméra = position approximative du joueur au moment de la sauvegarde
    cx, cy, cz = struct.unpack_from("<3f", simple, 0x70)
    if abs(cx) < 4000 and abs(cy) < 4000:
        snap.player = (cx, cy, cz, 0.0)

    script = blocks[B_SCRIPT]
    size = struct.unpack_from("<I", script, 0)[0]
    snap.globals_raw = bytes(script[4:4 + min(size, len(script) - 4)])

    stats = blocks[B_STATS]
    if len(stats) >= 0x148 + 223 * 4:
        snap.stats_float = list(struct.unpack_from("<82f", stats, 0))
        snap.stats_int = list(struct.unpack_from("<223i", stats, 0x148))

    pk = blocks[B_PICKUPS]
    if len(pk) >= 620 * 32:
        snap.pickups = []
        for i in range(620):
            x, y, z = struct.unpack_from("<3h", pk, i * 32 + 0x10)
            model = struct.unpack_from("<h", pk, i * 32 + 0x18)[0]
            ptype = pk[i * 32 + 0x1C]
            if ptype:
                snap.pickups.append(Pickup(model, ptype, x / 8.0, y / 8.0, z / 8.0))
        snap.pickups_reliable = True

    tags = blocks[B_TAGS]
    if len(tags) >= 4:
        count = struct.unpack_from("<I", tags, 0)[0]
        if 0 < count <= 150 and len(tags) >= 4 + count:
            snap.tags = [Tag(None, None, None, tags[4 + i]) for i in range(count)]

    when = datetime.fromtimestamp(path.stat().st_mtime).strftime("%d/%m %H:%M")
    slot = path.stem.replace("GTASAsf", "")
    snap.label = f"Sauvegarde n°{slot} « {name} » ({when})"
    snap.diagnostics = {"Fichier": str(path), "Nom": name, "Variables globales": len(snap.globals_raw) // 4}
    return snap
