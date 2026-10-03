"""État du jeu lu en mémoire ou dans une sauvegarde."""

import struct
import time
from dataclasses import dataclass, field

# Modèles des pickups collectibles
MODEL_OYSTER = 953
MODEL_HORSESHOE = 954
MODEL_SNAPSHOT = 1253
TAG_SPRAYED_ALPHA = 228  # CTagManager::ALPHA_TAGGED

# Statistiques (eStats.h)
STAT_PROGRESS_MADE = 0
STAT_TOTAL_PROGRESS = 1
FIRST_INT_STAT = 120
STAT_SNAPSHOTS_TAKEN = 231
STAT_HORSESHOES_COLLECTED = 241
STAT_OYSTERS_COLLECTED = 243
STAT_TAGS_SPRAYED = 322

COLLECT_TOTALS = {"tags": 100, "snapshots": 50, "horseshoes": 50, "oysters": 50}


@dataclass
class Pickup:
    model: int
    type: int
    x: float
    y: float
    z: float


@dataclass
class Tag:
    x: float | None
    y: float | None
    z: float | None
    alpha: int

    @property
    def sprayed(self) -> bool:
        return self.alpha >= TAG_SPRAYED_ALPHA


@dataclass
class StuntJump:
    x: float
    y: float
    z: float
    done: bool
    found: bool


@dataclass
class Snapshot:
    source: str                                   # "memory" ou "save"
    label: str                                    # texte pour la barre d'état
    globals_raw: bytes = b""                      # espace des variables globales
    stats_float: list[float] | None = None        # 82 stats float
    stats_int: list[int] | None = None            # stats 120..342
    pickups: list[Pickup] | None = None           # collectibles encore présents
    pickups_reliable: bool = False                # True si le tableau complet a été lu
    tags: list[Tag] | None = None
    stunts: list[StuntJump] | None = None
    player: tuple[float, float, float, float] | None = None  # x, y, z, cap (radians)
    timestamp: float = field(default_factory=time.time)
    diagnostics: dict = field(default_factory=dict)

    # -- Variables globales --------------------------------------------
    def g(self, var: int) -> int:
        off = var * 4
        if off + 4 > len(self.globals_raw):
            return 0
        return struct.unpack_from("<i", self.globals_raw, off)[0]

    @property
    def has_globals(self) -> bool:
        return len(self.globals_raw) > 4 * 3000

    # -- Statistiques --------------------------------------------------
    def stat(self, stat_id: int) -> float | None:
        if stat_id < 82:
            if self.stats_float and stat_id < len(self.stats_float):
                return self.stats_float[stat_id]
            return None
        if self.stats_int and 0 <= stat_id - FIRST_INT_STAT < len(self.stats_int):
            return float(self.stats_int[stat_id - FIRST_INT_STAT])
        return None

    @property
    def progress_percent(self) -> float | None:
        made, total = self.stat(STAT_PROGRESS_MADE), self.stat(STAT_TOTAL_PROGRESS)
        if made is None or not total or total <= 0:
            return None
        return max(0.0, min(100.0, made * 100.0 / total))
