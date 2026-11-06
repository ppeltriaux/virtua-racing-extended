"""Load the MAME `vr` ROM set into contiguous region images.

Layout follows MAME src/mame/sega/model1.cpp (vr ROM_START). All multi-ROM
regions are interleaved here so callers see flat little-endian byte strings
addressed the way the V60 / TGP see them.
"""

from __future__ import annotations

import struct
import zipfile
from dataclasses import dataclass
from pathlib import Path

PROGRAM_PAIR = ("epr-14882.14", "epr-14883.15")          # V60 0x200000, 1 MB
BOOT_PAIR = ("epr-14878a.4", "epr-14879a.5")             # V60 0xfc0000, 256 KB
DATA_PAIRS = (("mpr-14880.6", "mpr-14881.7"), ("mpr-14884.8", "mpr-14885.9"),
              ("mpr-14886.10", "mpr-14887.11"), ("mpr-14888.12", "mpr-14889.13"))  # V60 0x1000000, 4 MB
POLY_PAIRS = (("mpr-14890.26", "mpr-14891.27"), ("mpr-14892.28", "mpr-14893.29"),
              ("mpr-14894.30", "mpr-14895.31"), ("mpr-14896.32", "mpr-14897.33"))  # 16 MB, LE32 words
COPRO_LANES = ("mpr-14898.39", "mpr-14899.40", "mpr-14900.41", "mpr-14901.42")      # 2 MB, byte lanes
TGP_PROGRAM = "315-5573.bin"

# The 13 files of MAME 0.289's `vr` set this tool never reads (TGP tables, other data, the 315-5571/2 PALs, the sound
# CPU and PCM ROMs, the I/O board EEPROM): MAME refuses to run without them, so `vrtools check` reports them too.
OTHER_FILES: dict[str, tuple[int, int]] = {
    "opr14742.bin": (0x20000, 0x446A1085), "opr14743.bin": (0x20000, 0xE8953554),
    "opr-14744.58": (0x20000, 0x730EA9E0), "opr-14745.59": (0x20000, 0x4C934D96),
    "opr-14746.62": (0x20000, 0x2A266CBD), "opr-14747.63": (0x20000, 0xA4AD5E19),
    "opr14748.bin": (0x20000, 0x4A532CB8),
    "315-5571.bin": (0x2000, 0x1233DB2A), "315-5572.bin": (0x2000, 0x66785906),
    "epr-14870a.7": (0x20000, 0x919D9B75), "mpr-14873.32": (0x200000, 0xB1965190), "mpr-14876.4": (0x200000, 0xBA6B2327),
    "93c45.bin": (0x80, 0x65AAC303),
}

REQUIRED_FILES = (*PROGRAM_PAIR, *BOOT_PAIR, *(f for p in DATA_PAIRS for f in p),
                  *(f for p in POLY_PAIRS for f in p), *COPRO_LANES, TGP_PROGRAM)

# Expected (size, crc32) per file, from MAME 0.289 `-listxml vr`.
EXPECTED: dict[str, tuple[int, int]] = {
    "epr-14882.14": (0x80000, 0x547D75AD), "epr-14883.15": (0x80000, 0x6BFAD8B1),
    "epr-14878a.4": (0x20000, 0x6D69E695), "epr-14879a.5": (0x20000, 0xD45AF9DD),
    "mpr-14880.6": (0x80000, 0xADC7C208), "mpr-14881.7": (0x80000, 0xE5AB89DF),
    "mpr-14884.8": (0x80000, 0x6CF9C026), "mpr-14885.9": (0x80000, 0xF65C9262),
    "mpr-14886.10": (0x80000, 0x92868734), "mpr-14887.11": (0x80000, 0x10C7C636),
    "mpr-14888.12": (0x80000, 0x04BFDC5B), "mpr-14889.13": (0x80000, 0xC49F0486),
    "mpr-14890.26": (0x200000, 0xDCBE006B), "mpr-14891.27": (0x200000, 0x25832B38),
    "mpr-14892.28": (0x200000, 0x5136F3BA), "mpr-14893.29": (0x200000, 0x1C531ADA),
    "mpr-14894.30": (0x200000, 0x830A71BC), "mpr-14895.31": (0x200000, 0xAF027AC5),
    "mpr-14896.32": (0x200000, 0x382091DC), "mpr-14897.33": (0x200000, 0x74873195),
    "mpr-14898.39": (0x80000, 0x61DA2BB6), "mpr-14899.40": (0x80000, 0x2CD58BEE),
    "mpr-14900.41": (0x80000, 0xAA7C017D), "mpr-14901.42": (0x80000, 0x175B7A9A),
    "315-5573.bin": (0x2000, 0x3335A19B),
}

V60_PROGRAM = 0x200000
V60_BOOT = 0xFC0000
V60_DATA = 0x1000000


class RomSetError(Exception):
    pass


def _lanes2(a: bytes, b: bytes) -> bytes:
    out = bytearray(len(a) + len(b))
    out[0::2] = a
    out[1::2] = b
    return bytes(out)


def _words32(a: bytes, b: bytes) -> bytes:
    """ROM a supplies bytes 0-1 and ROM b bytes 2-3 of each LE32 word (ROM_LOAD32_WORD at 0 and 2)."""
    out = bytearray(len(a) + len(b))
    out[0::4] = a[0::2]
    out[1::4] = a[1::2]
    out[2::4] = b[0::2]
    out[3::4] = b[1::2]
    return bytes(out)


@dataclass(frozen=True)
class RomSet:
    program: bytes
    boot: bytes
    data: bytes
    polygons: bytes
    copro_data: bytes
    tgp_program: bytes

    @classmethod
    def from_files(cls, files: dict[str, bytes]) -> "RomSet":
        missing = [n for n in REQUIRED_FILES if n not in files]
        if missing:
            raise RomSetError("ROM set is missing (is it a current MAME `vr` set?): " + ", ".join(missing))
        groups = [PROGRAM_PAIR, BOOT_PAIR, *DATA_PAIRS, *POLY_PAIRS, COPRO_LANES]
        bad = [f"{n} ({len(files[n])} bytes, expected {len(files[g[0]])} like {g[0]})"
               for g in groups for n in g[1:] if len(files[n]) != len(files[g[0]])]
        if bad:
            raise RomSetError("ROM size mismatch within a pair/lane group: " + "; ".join(bad))
        copro = bytearray(4 * len(files[COPRO_LANES[0]]))
        for i, name in enumerate(COPRO_LANES):
            copro[i::4] = files[name]
        return cls(
            program=_lanes2(*(files[n] for n in PROGRAM_PAIR)),
            boot=b"".join(files[n] for n in BOOT_PAIR),          # ROM_LOAD, not interleaved: 0xfc0000 and 0xfe0000
            data=b"".join(_lanes2(files[a], files[b]) for a, b in DATA_PAIRS),
            polygons=b"".join(_words32(files[a], files[b]) for a, b in POLY_PAIRS),
            copro_data=bytes(copro),
            tgp_program=files[TGP_PROGRAM],
        )

    @classmethod
    def from_zip(cls, path: Path, verify: bool = True) -> "RomSet":
        """Load a `vr.zip`; verify=False accepts patched sets (sizes still checked, CRCs not)."""
        problems = []
        with zipfile.ZipFile(path) as z:
            infos = {Path(i.filename).name: i for i in z.infolist()}
            for name, (size, crc) in EXPECTED.items():
                if name not in infos:
                    continue                                   # reported as missing by from_files
                info = infos[name]
                if info.file_size != size:
                    problems.append(f"{name}: size {info.file_size:#x}, expected {size:#x}")
                elif verify and info.CRC != crc:
                    problems.append(f"{name}: crc32 {info.CRC:08x}, expected {crc:08x}")
            files = {n: z.read(infos[n].filename) for n in REQUIRED_FILES if n in infos}
        missing = [n for n in REQUIRED_FILES if n not in files]
        if missing or problems:
            raise RomSetError(f"{path}: not a good MAME 0.289 `vr` set. "
                              + (f"Missing: {', '.join(missing)}. " if missing else "")
                              + (f"Mismatched: {'; '.join(problems)}" if problems else ""))
        return cls.from_files(files)

    def read_v60(self, addr: int, n: int) -> bytes:
        for base, region in ((V60_PROGRAM, self.program), (V60_BOOT, self.boot), (V60_DATA, self.data)):
            if base <= addr and addr + n <= base + len(region):
                return region[addr - base:addr - base + n]
        raise RomSetError(f"V60 address {addr:#x} (+{n}) is not in a ROM region")

    def poly_word(self, index: int) -> int:
        return struct.unpack_from("<I", self.polygons, index * 4)[0]

    def poly_float(self, index: int) -> float:
        return struct.unpack_from("<f", self.polygons, index * 4)[0]

    def to_files(self) -> dict[str, bytes]:
        """Inverse of from_files: split the regions back into the lane files."""
        files: dict[str, bytes] = {}
        files[PROGRAM_PAIR[0]], files[PROGRAM_PAIR[1]] = self.program[0::2], self.program[1::2]
        half = len(self.boot) // 2
        files[BOOT_PAIR[0]], files[BOOT_PAIR[1]] = self.boot[:half], self.boot[half:]
        step = len(self.data) // len(DATA_PAIRS)
        for i, (a, b) in enumerate(DATA_PAIRS):
            chunk = self.data[i * step:(i + 1) * step]
            files[a], files[b] = chunk[0::2], chunk[1::2]
        step = len(self.polygons) // len(POLY_PAIRS)
        for i, (a, b) in enumerate(POLY_PAIRS):
            chunk = self.polygons[i * step:(i + 1) * step]
            ra = bytearray(len(chunk) // 2); rb = bytearray(len(chunk) // 2)
            ra[0::2], ra[1::2] = chunk[0::4], chunk[1::4]
            rb[0::2], rb[1::2] = chunk[2::4], chunk[3::4]
            files[a], files[b] = bytes(ra), bytes(rb)
        for i, name in enumerate(COPRO_LANES):
            files[name] = self.copro_data[i::4]
        files[TGP_PROGRAM] = self.tgp_program
        return files

    def to_zip(self, path: Path, source: Path | None = None) -> None:
        """Write the set as a MAME-loadable zip; extra members of `source` (e.g. a vformula/ clone) are copied. The
        source is never written: the same file under another spelling (a case-insensitive volume), a link or a
        firmlink is refused by `samefile`, and the zip is written to a temporary file beside `path` and renamed into
        place, so an interrupted write cannot leave a truncated set."""
        import os
        files = self.to_files()
        path = Path(path)
        if source is not None and path.exists() and os.path.samefile(source, path):
            raise RomSetError(f"refusing to overwrite the source set {Path(source)} in place")
        tmp = path.with_name(path.name + ".part")
        with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as z:
            for name, blob in files.items():
                z.writestr(name, blob)
            if source is not None:
                with zipfile.ZipFile(source) as src:
                    for info in src.infolist():
                        if Path(info.filename).name not in files:
                            z.writestr(info, src.read(info.filename))
        os.replace(tmp, path)

    def dump_regions(self, out_dir: Path) -> list[Path]:
        out_dir = Path(out_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        written = []
        for name, blob in (("v60_program.bin", self.program), ("v60_boot.bin", self.boot),
                           ("v60_data.bin", self.data), ("polygons.bin", self.polygons),
                           ("copro_data.bin", self.copro_data), ("tgp_program.bin", self.tgp_program)):
            p = out_dir / name
            p.write_bytes(blob)
            written.append(p)
        return written
