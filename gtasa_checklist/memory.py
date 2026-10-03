"""Lecture en direct de la mémoire de gta_sa.exe (lecture seule).

Les adresses de la version 1.0 US sont connues. Pour les autres versions
(Steam, Rockstar Games Launcher...), les structures sont retrouvées en
balayant l'image de l'exécutable à la recherche de motifs caractéristiques,
puis mémorisées par build dans %APPDATA%/GTASA_Checklist/addresses.json.
"""

import ctypes
import ctypes.wintypes as wt
import math
import struct
import time
from pathlib import Path

import numpy as np

from . import gamefiles
from .model import (MODEL_HORSESHOE, MODEL_OYSTER, MODEL_SNAPSHOT, Pickup, Snapshot,
                    StuntJump, Tag)

PROCESS_NAMES = {"gta_sa.exe", "gta-sa.exe", "gta_sa_compact.exe"}

# Adresses absolues de la 1.0 US (base 0x400000), utilisées en priorité si valides
V10 = {
    "script_space": 0xA49960,
    "stats_int": 0xB79000,
    "stats_float": 0xB79380,
    "tag_desc": 0xA9A8C0,
    "pickups": 0x9788C0,
    "ped_pool_ptr": 0xB74490,
}

PED_STRIDE = 0x7C4          # taille d'un emplacement du pool de piétons (CCopPed)
NUM_PICKUPS = 620
PICKUP_SIZE = 0x20
MAX_TAGS = 150
STUNT_SIZE = 0x44
COLLECT_MODELS = {MODEL_SNAPSHOT: "snapshots", MODEL_HORSESHOE: "horseshoes",
                  MODEL_OYSTER: "oysters"}

# --------------------------------------------------------------- Win32

k32 = ctypes.WinDLL("kernel32", use_last_error=True)

PROCESS_VM_READ = 0x0010
PROCESS_QUERY_INFORMATION = 0x0400
TH32CS_SNAPPROCESS = 0x2
TH32CS_SNAPMODULE = 0x8
TH32CS_SNAPMODULE32 = 0x10
MEM_COMMIT = 0x1000
PAGE_NOACCESS = 0x01
PAGE_GUARD = 0x100
STILL_ACTIVE = 259


class PROCESSENTRY32W(ctypes.Structure):
    _fields_ = [("dwSize", wt.DWORD), ("cntUsage", wt.DWORD), ("th32ProcessID", wt.DWORD),
                ("th32DefaultHeapID", ctypes.c_size_t), ("th32ModuleID", wt.DWORD),
                ("cntThreads", wt.DWORD), ("th32ParentProcessID", wt.DWORD),
                ("pcPriClassBase", ctypes.c_long), ("dwFlags", wt.DWORD),
                ("szExeFile", ctypes.c_wchar * 260)]


class MODULEENTRY32W(ctypes.Structure):
    _fields_ = [("dwSize", wt.DWORD), ("th32ModuleID", wt.DWORD), ("th32ProcessID", wt.DWORD),
                ("GlblcntUsage", wt.DWORD), ("ProccntUsage", wt.DWORD),
                ("modBaseAddr", ctypes.c_void_p), ("modBaseSize", wt.DWORD),
                ("hModule", wt.HMODULE), ("szModule", ctypes.c_wchar * 256),
                ("szExePath", ctypes.c_wchar * 260)]


class MEMORY_BASIC_INFORMATION(ctypes.Structure):
    _fields_ = [("BaseAddress", ctypes.c_void_p), ("AllocationBase", ctypes.c_void_p),
                ("AllocationProtect", wt.DWORD), ("PartitionId", wt.WORD),
                ("RegionSize", ctypes.c_size_t), ("State", wt.DWORD),
                ("Protect", wt.DWORD), ("Type", wt.DWORD)]


k32.CreateToolhelp32Snapshot.restype = wt.HANDLE
k32.CreateToolhelp32Snapshot.argtypes = [wt.DWORD, wt.DWORD]
k32.Process32FirstW.argtypes = [wt.HANDLE, ctypes.POINTER(PROCESSENTRY32W)]
k32.Process32NextW.argtypes = [wt.HANDLE, ctypes.POINTER(PROCESSENTRY32W)]
k32.Module32FirstW.argtypes = [wt.HANDLE, ctypes.POINTER(MODULEENTRY32W)]
k32.OpenProcess.restype = wt.HANDLE
k32.OpenProcess.argtypes = [wt.DWORD, wt.BOOL, wt.DWORD]
k32.CloseHandle.argtypes = [wt.HANDLE]
k32.ReadProcessMemory.argtypes = [wt.HANDLE, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_size_t,
                                  ctypes.POINTER(ctypes.c_size_t)]
k32.VirtualQueryEx.restype = ctypes.c_size_t
k32.VirtualQueryEx.argtypes = [wt.HANDLE, ctypes.c_void_p, ctypes.POINTER(MEMORY_BASIC_INFORMATION),
                               ctypes.c_size_t]
k32.GetExitCodeProcess.argtypes = [wt.HANDLE, ctypes.POINTER(wt.DWORD)]
INVALID_HANDLE = wt.HANDLE(-1).value


def find_game_process() -> int | None:
    snap = k32.CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS, 0)
    if snap == INVALID_HANDLE:
        return None
    try:
        entry = PROCESSENTRY32W()
        entry.dwSize = ctypes.sizeof(entry)
        ok = k32.Process32FirstW(snap, ctypes.byref(entry))
        while ok:
            if entry.szExeFile.lower() in PROCESS_NAMES:
                return entry.th32ProcessID
            ok = k32.Process32NextW(snap, ctypes.byref(entry))
    finally:
        k32.CloseHandle(snap)
    return None


def _main_module(pid: int) -> tuple[int, int, str] | None:
    snap = k32.CreateToolhelp32Snapshot(TH32CS_SNAPMODULE | TH32CS_SNAPMODULE32, pid)
    if snap == INVALID_HANDLE:
        return None
    try:
        entry = MODULEENTRY32W()
        entry.dwSize = ctypes.sizeof(entry)
        if k32.Module32FirstW(snap, ctypes.byref(entry)):
            return entry.modBaseAddr, entry.modBaseSize, entry.szExePath
    finally:
        k32.CloseHandle(snap)
    return None


class GameNotRunning(Exception):
    pass


class GameMemory:
    """Connexion à un processus gta_sa.exe et lecture des structures utiles."""

    def __init__(self, pid: int, main_scm_hint: str | None = None):
        self.pid = pid
        self.handle = k32.OpenProcess(PROCESS_VM_READ | PROCESS_QUERY_INFORMATION, False, pid)
        if not self.handle:
            raise PermissionError("Impossible d'ouvrir le processus du jeu "
                                  "(lance l'appli avec les mêmes droits que le jeu).")
        mod = None
        for _ in range(20):                  # le module peut ne pas être prêt au lancement
            mod = _main_module(pid)
            if mod:
                break
            time.sleep(0.1)
        if not mod:
            self.close()
            raise GameNotRunning("Module principal introuvable")
        self.base, self.size, self.exe_path = mod
        self.game_dir = str(Path(self.exe_path).parent)
        self.build_key = self._build_key()
        self.version = self._detect_version()
        self.addr: dict[str, int] = {}
        self._image: bytes | None = None
        self._last_scan = 0.0
        self._tag_pos: dict[int, tuple] = {}
        self._scm = self._load_scm_signature(main_scm_hint)
        cache = gamefiles.load_json("addresses.json", {})
        self.addr.update({k: v for k, v in cache.get(self.build_key, {}).items()})

    # -- Bas niveau ------------------------------------------------------
    def close(self):
        if self.handle:
            k32.CloseHandle(self.handle)
            self.handle = None

    def alive(self) -> bool:
        code = wt.DWORD()
        return bool(self.handle) and k32.GetExitCodeProcess(self.handle, ctypes.byref(code)) \
            and code.value == STILL_ACTIVE

    def read(self, addr: int, size: int) -> bytes | None:
        if addr <= 0 or size <= 0:
            return None
        buf = ctypes.create_string_buffer(size)
        got = ctypes.c_size_t()
        if not k32.ReadProcessMemory(self.handle, ctypes.c_void_p(addr), buf, size, ctypes.byref(got)):
            return None
        return buf.raw[:got.value] if got.value == size else None

    def u32(self, addr: int) -> int | None:
        b = self.read(addr, 4)
        return struct.unpack("<I", b)[0] if b else None

    def i32(self, addr: int) -> int | None:
        b = self.read(addr, 4)
        return struct.unpack("<i", b)[0] if b else None

    def _build_key(self) -> str:
        try:
            with open(self.exe_path, "rb") as f:
                head = f.read(4096)
            pe = struct.unpack_from("<I", head, 0x3C)[0]
            stamp = struct.unpack_from("<I", head, pe + 8)[0]
            return f"{self.size:x}-{stamp:x}"
        except (OSError, struct.error):
            return f"{self.size:x}"

    def _detect_version(self) -> str:
        # Valeurs utilisées par les autosplitters (tduva/LiveSplit-ASL)
        if self.size == 18313216:
            if self.i32(self.base + 0x42457C) == 38079:
                return "1.0 US"
            if self.i32(self.base + 0x4245BC) == 38079:
                return "1.0 EU"
            return "1.0"
        if self.size == 34471936:
            return "1.01"
        if self.size in (9691136, 9981952):
            return "Steam"
        return "Rockstar Launcher / autre"

    def _load_scm_signature(self, hint):
        for d in (self.game_dir, hint):
            if d:
                sig = gamefiles.scm_signature(Path(d) / "data" / "script" / "main.scm")
                if sig:
                    return sig
        return None

    def _read_image(self) -> bytes:
        """Copie de toute l'image de l'exécutable (sections non lisibles = zéros)."""
        out = bytearray(self.size)
        addr, end = self.base, self.base + self.size
        mbi = MEMORY_BASIC_INFORMATION()
        while addr < end:
            if not k32.VirtualQueryEx(self.handle, ctypes.c_void_p(addr), ctypes.byref(mbi),
                                      ctypes.sizeof(mbi)):
                break
            region_end = min(end, (mbi.BaseAddress or 0) + mbi.RegionSize)
            if mbi.State == MEM_COMMIT and not (mbi.Protect & (PAGE_NOACCESS | PAGE_GUARD)):
                chunk = self.read(addr, region_end - addr)
                if chunk:
                    out[addr - self.base:region_end - self.base] = chunk
            addr = max(region_end, addr + 0x1000)
        return bytes(out)

    def _in_image(self, p: int) -> bool:
        return self.base <= p < self.base + self.size

    # -- Recherche des structures ----------------------------------------
    def _save_cache(self):
        cache = gamefiles.load_json("addresses.json", {})
        cache[self.build_key] = self.addr
        gamefiles.save_json("addresses.json", cache)

    def resolve(self, force: bool = False) -> None:
        """Trouve les adresses manquantes (balayage limité à une fois toutes les 5 s)."""
        wanted = ("script_space", "stats_int", "tag_desc", "pickups_anchor", "ped_pool_ptr")
        missing = [k for k in wanted if k not in self.addr]
        if not missing or (not force and time.time() - self._last_scan < 5):
            return
        self._last_scan = time.time()
        self._image = None
        changed = False
        for key in missing:
            finder = getattr(self, f"_find_{key}")
            try:
                value = finder()
            except (OSError, ValueError, struct.error):
                value = None
            if value:
                self.addr[key] = value
                changed = True
        self._image = None        # libère ~10-18 Mo
        if changed:
            self._save_cache()

    def image(self) -> bytes:
        if self._image is None:
            self._image = self._read_image()
        return self._image

    def _ints(self) -> np.ndarray:
        img = self.image()
        return np.frombuffer(img, dtype="<i4", count=len(img) // 4)

    def _find_script_space(self) -> int | None:
        if not self._scm:
            return None
        seg2, needle = self._scm
        cand = V10["script_space"]
        if self.read(cand + seg2, len(needle)) == needle:
            return cand
        img = self.image()
        i = img.find(needle)
        while i >= 0:
            ss = self.base + i - seg2
            if self.read(ss, 3) == b"\x02\x00\x01":
                return ss
            i = img.find(needle, i + 1)
        return None

    def _find_stats_int(self) -> int | None:
        """Tableau des stats entières : les totaux de photos/fers/huîtres valent 50."""
        def ok(arr):
            return (arr[112] == 50 and arr[122] == 50 and arr[124] == 50
                    and 0 <= arr[111] <= 50 and 0 <= arr[121] <= 50 and 0 <= arr[123] <= 50)

        raw = self.read(V10["stats_int"], 223 * 4)
        if raw and ok(struct.unpack("<223i", raw)):
            return V10["stats_int"]
        a = self._ints()
        n = len(a) - 223
        if n <= 0:
            return None
        m = (a[112:112 + n] == 50) & (a[122:122 + n] == 50) & (a[124:124 + n] == 50)
        for i in np.nonzero(m)[0]:
            if ok(a[i:i + 223]):
                return self.base + int(i) * 4
        return None

    def _find_tag_desc(self) -> int | None:
        """CTagManager : 150 x {CEntity*, alpha} suivis de ms_numTags et ms_numTagged."""
        def check(desc_addr):
            raw = self.read(desc_addr, MAX_TAGS * 8 + 8)
            if not raw:
                return False
            num, tagged = struct.unpack_from("<ii", raw, MAX_TAGS * 8)
            if not (20 <= num <= MAX_TAGS and 0 <= tagged <= num):
                return False
            ptrs = struct.unpack_from(f"<{MAX_TAGS * 2}I", raw, 0)[0::2]
            return (all(0x10000 < p < 0xFFFF0000 for p in ptrs[:num])
                    and all(p == 0 for p in ptrs[num:]))

        if check(V10["tag_desc"]):
            return V10["tag_desc"]
        a = self._ints()
        start = MAX_TAGS * 2
        nums = a[start:len(a) - 1]
        cand = np.nonzero((nums >= 20) & (nums <= MAX_TAGS) & (a[start + 1:] >= 0)
                          & (a[start + 1:] <= nums))[0]
        for c in cand:
            i = int(c) + start                      # index de ms_numTags
            desc = i - start
            if a[desc] != 0 and check(self.base + desc * 4):
                return self.base + desc * 4
        return None

    def _find_pickups_anchor(self) -> int | None:
        """Un pickup collectible connu, pour situer le tableau CPickups::aPickUps."""
        raw = self.read(V10["pickups"], NUM_PICKUPS * PICKUP_SIZE)
        if raw and self.version.startswith("1.0"):
            return V10["pickups"]
        known = gamefiles.load_json("collectibles.json", {})
        img = self.image()
        for kind_model, kind in COLLECT_MODELS.items():
            for x, y, z in known.get(kind, []):
                needle = struct.pack("<3h", int(x * 8), int(y * 8), int(z * 8))
                i = img.find(needle)
                while i >= 0:
                    rec = i - 0x10
                    if rec >= 0 and struct.unpack_from("<h", img, rec + 0x18)[0] == kind_model:
                        return self.base + rec
                    i = img.find(needle, i + 1)
        return None

    def _find_ped_pool_ptr(self) -> int | None:
        """CPools::ms_pPedPool : validé avec le handle du joueur ($3 = scplayer)."""
        handle = self.global_var(3)
        if not handle:
            return None
        if self._player_from_pool_ptr(V10["ped_pool_ptr"], handle):
            return V10["ped_pool_ptr"]
        a = self._ints().view("<u4")
        heap = (a > 0x10000) & (a < 0xFFFF0000)
        heap &= ~((a >= self.base) & (a < self.base + self.size))
        # CPools : suite de pointeurs vers des en-têtes de pools alloués côte à côte
        run = np.convolve(heap.astype(np.int8), np.ones(8, dtype=np.int8), "valid") == 8
        win = np.lib.stride_tricks.sliding_window_view(a.astype(np.int64), 8)
        run &= (win.max(axis=1) - win.min(axis=1)) < 0x4000
        for i in np.nonzero(run)[0]:
            ptr_addr = self.base + int(i) * 4
            if self._player_from_pool_ptr(ptr_addr, handle):
                return ptr_addr
        return None

    # -- Lecture -----------------------------------------------------------
    def global_var(self, var: int) -> int | None:
        ss = self.addr.get("script_space")
        return self.i32(ss + var * 4) if ss else None

    def _player_from_pool_ptr(self, ptr_addr: int, handle: int):
        pool = self.u32(ptr_addr)
        header = self.read(pool, 12) if pool else None
        if not header:
            return None
        storage, slots, capacity = struct.unpack("<IIi", header)
        idx = handle >> 8
        if not (0 < capacity <= 20000 and 0 <= idx < capacity and storage and slots):
            return None
        slot = self.read(slots + idx, 1)
        if not slot or slot[0] != (handle & 0xFF):
            return None
        ped = storage + idx * PED_STRIDE
        matrix = self.u32(ped + 0x14)
        m = self.read(matrix, 0x3C) if matrix else None
        if not m:
            return None
        fx, fy = struct.unpack_from("<2f", m, 0x10)
        x, y, z = struct.unpack_from("<3f", m, 0x30)
        if not (abs(x) < 6000 and abs(y) < 6000 and -200 < z < 3000):
            return None
        return x, y, z, math.atan2(-fx, fy)

    def _entity_pos(self, ent: int):
        raw = self.read(ent, 0x18)
        if not raw:
            return None
        matrix = struct.unpack_from("<I", raw, 0x14)[0]
        if matrix:
            m = self.read(matrix + 0x30, 12)
            if m:
                return struct.unpack("<3f", m)
        return struct.unpack_from("<3f", raw, 4)

    def snapshot(self) -> Snapshot:
        if not self.alive():
            raise GameNotRunning()
        self.resolve()
        snap = Snapshot(source="memory", label=f"Jeu en direct — version {self.version}")
        diag = {"Version": self.version, "Exécutable": self.exe_path, "Build": self.build_key}

        ss = self.addr.get("script_space")
        if ss and self._scm:
            raw = self.read(ss, self._scm[0])
            if raw:
                snap.globals_raw = raw

        si = self.addr.get("stats_int")
        if si:
            raw = self.read(si, 223 * 4)
            if raw:
                snap.stats_int = list(struct.unpack("<223i", raw))
            fl = self.read(si + 0x380, 82 * 4)
            if fl:
                floats = list(struct.unpack("<82f", fl))
                if 0 < floats[1] < 5000 and 0 <= floats[0] <= floats[1]:
                    snap.stats_float = floats

        td = self.addr.get("tag_desc")
        if td:
            snap.tags = self._read_tags(td)
            snap.stunts = self._read_stunts(td)

        anchor = self.addr.get("pickups_anchor")
        if anchor:
            snap.pickups = self._read_pickups(anchor)
            snap.pickups_reliable = snap.pickups is not None

        pp = self.addr.get("ped_pool_ptr")
        handle = self.global_var(3)
        if pp and handle:
            snap.player = self._player_from_pool_ptr(pp, handle)

        for key, value in self.addr.items():
            diag[key] = f"{value:#x}"
        snap.diagnostics = diag
        return snap

    def _read_tags(self, desc: int) -> list[Tag] | None:
        raw = self.read(desc, MAX_TAGS * 8 + 8)
        if not raw:
            return None
        num = struct.unpack_from("<i", raw, MAX_TAGS * 8)[0]
        if not 0 < num <= MAX_TAGS:
            return None
        tags = []
        for i in range(num):
            ent, alpha = struct.unpack_from("<IB", raw, i * 8)
            pos = self._tag_pos.get(ent)
            if pos is None and ent:
                pos = self._entity_pos(ent)
                if pos and abs(pos[0]) < 6000 and abs(pos[1]) < 6000:
                    self._tag_pos[ent] = pos
                else:
                    pos = None
            tags.append(Tag(*(pos or (None, None, None)), alpha))
        return tags

    def _stunt_manager(self, tag_desc: int) -> tuple[int, int, int, int] | None:
        """CStuntJumpManager est juste avant CTagManager : pointeur du pool, puis
        le nombre de sauts 0x14 octets plus loin (-0x38/-0x24 en 1.0, -0x20/-0x0C
        sur la version Rockstar Launcher)."""
        raw = self.read(tag_desc - 0x80, 0x80)
        if not raw:
            return None
        for off in range(0, 0x80 - 0x18, 4):
            pool, num = struct.unpack_from("<I", raw, off)[0], struct.unpack_from("<i", raw, off + 0x14)[0]
            if not (0 < num <= 256 and 0x10000 < pool < 0xFFFF0000):
                continue
            header = self.read(pool, 12)
            if header:
                storage, slots, capacity = struct.unpack("<IIi", header)
                if num <= capacity <= 1024 and storage and slots:
                    return storage, slots, capacity, num
        return None

    def _read_stunts(self, tag_desc: int) -> list[StuntJump] | None:
        found = self._stunt_manager(tag_desc)
        if not found:
            return None
        storage, slots, capacity, num = found
        flags = self.read(slots, capacity)
        data = self.read(storage, capacity * STUNT_SIZE)
        if not flags or not data:
            return None
        jumps = []
        for i in range(capacity):
            if flags[i] & 0x80:
                continue
            x1, y1, z1, x2, y2, z2 = struct.unpack_from("<6f", data, i * STUNT_SIZE)
            done, found = data[i * STUNT_SIZE + 0x40], data[i * STUNT_SIZE + 0x41]
            jumps.append(StuntJump((x1 + x2) / 2, (y1 + y2) / 2, (z1 + z2) / 2,
                                   bool(done), bool(found)))
        return jumps if len(jumps) == num else None

    def _read_pickups(self, anchor: int) -> list[Pickup] | None:
        """Lit une fenêtre couvrant forcément tout le tableau, garde les collectibles."""
        if self.version.startswith("1.0") and anchor == V10["pickups"]:
            start, count = anchor, NUM_PICKUPS
        else:
            start, count = anchor - (NUM_PICKUPS - 1) * PICKUP_SIZE, 2 * NUM_PICKUPS - 1
        raw = self.read(start, count * PICKUP_SIZE)
        if not raw:
            return None
        out = []
        for i in range(count):
            o = i * PICKUP_SIZE
            model = struct.unpack_from("<h", raw, o + 0x18)[0]
            if model not in COLLECT_MODELS:
                continue
            ptype = raw[o + 0x1C]
            if ptype == 0 or ptype > 22:
                continue
            x, y, z = struct.unpack_from("<3h", raw, o + 0x10)
            out.append(Pickup(model, ptype, x / 8.0, y / 8.0, z / 8.0))
        return out
