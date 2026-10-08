"""Évaluation des règles du catalogue à partir d'un Snapshot."""

from dataclasses import dataclass, field

from .model import (COLLECT_TOTALS, MODEL_HORSESHOE, MODEL_OYSTER, MODEL_SNAPSHOT,
                    STAT_HORSESHOES_COLLECTED, STAT_OYSTERS_COLLECTED, STAT_SNAPSHOTS_TAKEN,
                    STAT_TAGS_SPRAYED, Snapshot)

RACES_WON = 2300          # tableau $RACES_WON[27]
CHILIAD_NEXT_RACE = 1799
CHILIAD_ALL_DONE = 1801
EXPORT_CURRENT_LIST = 1049
EXPORT_SLOTS = 1060       # 10 drapeaux pour la liste en cours
EXPORT_ALL_DONE = 1184
CATALINA_ROBBERIES = (714, 715, 716, 717)

PICKUP_MODELS = {"snapshots": MODEL_SNAPSHOT, "horseshoes": MODEL_HORSESHOE,
                 "oysters": MODEL_OYSTER}
COUNT_STATS = {"tags": STAT_TAGS_SPRAYED, "snapshots": STAT_SNAPSHOTS_TAKEN,
               "horseshoes": STAT_HORSESHOES_COLLECTED, "oysters": STAT_OYSTERS_COLLECTED}


@dataclass
class CollectState:
    """État de chaque collectible : positions + ramassé / pas ramassé / inconnu."""
    points: dict[str, list[tuple[float, float, float]]] = field(default_factory=dict)
    done: dict[str, list[bool | None]] = field(default_factory=dict)
    counts: dict[str, int | None] = field(default_factory=dict)


def compute_collectibles(snap: Snapshot | None, known: dict, tag_positions: list) -> CollectState:
    st = CollectState()

    for kind, model in PICKUP_MODELS.items():
        pts = known.get(kind, [])
        st.points[kind] = pts
        flags: list[bool | None] = [None] * len(pts)
        if snap and snap.pickups is not None and snap.pickups_reliable:
            present = [p for p in snap.pickups if p.model == model and p.type != 0]
            for i, (x, y, z) in enumerate(pts):
                flags[i] = not any(abs(p.x - x) < 1.5 and abs(p.y - y) < 1.5 for p in present)
        st.done[kind] = flags

    # Tags : positions apprises en mémoire (ou cache), état par index
    tags = snap.tags if snap else None
    pts, flags = [], []
    if tags:
        for i, t in enumerate(tags):
            if t.x is not None:
                pos = (t.x, t.y, t.z)
            elif i < len(tag_positions) and tag_positions[i]:
                pos = tuple(tag_positions[i])
            else:
                pos = None
            pts.append(pos)
            flags.append(t.sprayed)
    else:
        pts = [tuple(p) if p else None for p in tag_positions]
        flags = [None] * len(pts)
    st.points["tags"] = pts
    st.done["tags"] = flags

    for kind in COLLECT_TOTALS:
        count = None
        if kind == "tags" and tags:
            count = sum(1 for t in tags if t.sprayed)
        elif snap:
            v = snap.stat(COUNT_STATS[kind])
            if v is not None:
                count = int(v)
        if count is None:
            fl = st.done.get(kind) or []
            if fl and all(f is not None for f in fl):
                count = sum(1 for f in fl if f)
        st.counts[kind] = count
    return st


def evaluate(rule, snap: Snapshot | None, coll: CollectState) -> bool | None:
    """True = fait, False = pas fait, None = inconnu (pas de données)."""
    if rule is None:
        return None
    op = rule[0]

    if op in ("any", "all"):
        results = [evaluate(r, snap, coll) for r in rule[1]]
        if op == "any":
            if any(r is True for r in results):
                return True
            return None if any(r is None for r in results) else False
        if any(r is False for r in results):
            return False
        return None if any(r is None for r in results) else True

    if op == "collect":
        count = coll.counts.get(rule[1])
        return None if count is None else count >= COLLECT_TOTALS[rule[1]]

    if snap is None or not snap.has_globals:
        return None
    g = snap.g

    if op == "g>=":
        return g(rule[1]) >= rule[2]
    if op == "g!=0":
        return g(rule[1]) != 0
    if op == "race":
        return g(RACES_WON + rule[1]) != 0
    if op == "chiliad":
        return g(CHILIAD_ALL_DONE) != 0 or g(CHILIAD_NEXT_RACE) > rule[1]
    if op == "robberies>=":
        return sum(1 for v in CATALINA_ROBBERIES if g(v) != 0) >= rule[1]
    if op == "export":
        lst, slot = rule[1], rule[2]
        if g(EXPORT_ALL_DONE) != 0:
            return True
        cur = g(EXPORT_CURRENT_LIST)
        if cur > lst:
            return True
        if cur < lst:
            return False
        return g(EXPORT_SLOTS + slot) != 0
    raise ValueError(f"Règle inconnue : {rule!r}")
