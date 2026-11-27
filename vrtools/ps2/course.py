"""One course's files gathered from its three archives (`CCnn.PAC`, `CCBINnn.PAC` one player, `CCDIVnn.PAC` split screen).

Courses (docs/spike/2026-11-phase90-ps2-disc-recon.md §2): 0 Big Forest, 1 Bay Bridge, 2 Acropolis (the arcade's),
3 Mountain, 4 Island, 5 Beltway (additional). The PS2 frame maps onto the arcade's as arcade = (−x, −y, −z) + the host's
start: scale 1, measured on the three shared courses (§3.1; the y flip from the collision heights, §6).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

import numpy as np

from vrtools.ps2 import model, pac, pat, picture, vcp

NAMES = ("BIG FOREST", "BAY BRIDGE", "ACROPOLIS", "MOUNTAIN", "ISLAND", "BELTWAY")
PREFIXES = ("BIG", "BAY", "ACR", "MOU", "ILA", "MEG")
ADDITIONAL = (3, 4, 5)
ATLAS_WIDTH = 128
SKY_WIDTH = 256


def archive_names(index: int) -> tuple[str, str, str]:
    return f"CC{index:02d}.PAC", f"CCBIN{index:02d}.PAC", f"CCDIV{index:02d}.PAC"


@dataclass
class Ps2Course:
    index: int
    road: list[vcp.CollisionSet]                 # AT sections, in order
    walls: list[vcp.CollisionSet]                # KB sections
    paths: dict[str, np.ndarray]                 # NORMAL, DIRLINE, PIT00, PIT01, RETURN, CAM (those present)
    checkpoints: model.Mesh | None               # chk.bin: the gate planes
    sections: list[model.Mesh]                   # one-player scenery, NN.bin in order
    props: list[model.Mesh]                      # one-player trNN.bin
    tunnels: list[model.Mesh]                    # tunNN.bin
    shadows: list[model.Mesh]                    # CCKG/CCSH
    split_sections: list[model.Mesh]             # split-screen scenery
    split_props: list[model.Mesh]
    atlases: dict[str, picture.Picture]          # cous00 (and cous00b), 128 x 128
    skies: dict[str, picture.Picture] = field(default_factory=dict)   # sky0a..sky3b, sea0..3: 256 x 256
    banners: list[model.Mesh] = field(default_factory=list)  # CCnn st01/st02: the checkpoint banners (white panel, "C.P"
                                                             # lettering as faces), world coordinates; st00 is the START banner
    start_banner: list[model.Mesh] = field(default_factory=list)   # st00
    flags: list[model.Mesh] = field(default_factory=list)    # fl00/fl01: the start's flags, their first pose (animated on the PS2)

    @property
    def name(self) -> str:
        return NAMES[self.index]

    @property
    def prefix(self) -> str:
        return PREFIXES[self.index]


def _numbered(files: dict[str, bytes], pattern: str) -> list[tuple[str, bytes]]:
    rx = re.compile(pattern, re.I)
    return sorted(((k, v) for k, v in files.items() if rx.fullmatch(k)), key=lambda kv: kv[0].lower())


def _meshes(items: list[tuple[str, bytes]]) -> list[model.Mesh]:
    out = []
    for _, data in items:
        if model.is_model(data):
            out.extend(model.meshes(data))
    return out


def load_course(index: int, cc: bytes, ccbin: bytes, ccdiv: bytes | None = None) -> Ps2Course:
    """A course from its three `.PAC` files' bytes (the split-screen one optional)."""
    a = pac.read_pac(cc)
    b = pac.read_pac(ccbin)
    d = pac.read_pac(ccdiv) if ccdiv is not None else {}
    pre = PREFIXES[index]
    road = [vcp.read_vcp(v) for _, v in _numbered(a, rf"{pre}_AT\d+\.VCP")]
    walls = [vcp.read_vcp(v) for _, v in _numbered(a, rf"{pre}_KB\d+\.VCP")]
    paths = {}
    for key, rx in (("NORMAL", r"NORMAL\.PAT"), ("DIRLINE", r"DIRLINE\.PAT"), ("PIT00", r"PIT00\.PAT"), ("PIT01", r"PIT01\.PAT"),
                    ("RETURN", r"RETURN\d+\.PAT"), ("CAM", r"CAM\d+\.PAT")):
        hit = _numbered(a, rx)
        if hit:
            paths[key] = pat.read_pat(hit[0][1])
    chk = _meshes(_numbered(a, r"chk\.bin"))
    atlases = {k.split(".")[0].lower(): picture.decode(v, ATLAS_WIDTH) for k, v in _numbered(b, r"cous00b?\.tm2")}
    skies = {k.split(".")[0].lower(): picture.decode(v, SKY_WIDTH) for k, v in _numbered(a, r"(sky\d[ab]|sea\d)\.tm2")}
    return Ps2Course(
        index, road, walls, paths, chk[0] if chk else None,
        _meshes(_numbered(b, r"\d+\.bin")), _meshes(_numbered(b, r"tr\d+\.bin")), _meshes(_numbered(b, r"tun\d+\.bin")),
        _meshes(_numbered(b, r"CC(KG|SH)\d+\.bin")),
        _meshes(_numbered(d, r"\d+\.bin")), _meshes(_numbered(d, r"tr\d+\.bin")), atlases, skies,
        _meshes(_numbered(a, r"st0[12]\.bin")), _meshes(_numbered(a, r"st00\.bin")), _meshes(_numbered(a, r"fl\d+\.bin")))


def load_from_disc(disc, index: int, split: bool = True) -> Ps2Course:
    """A course read from an open `disc.Ps2Disc`."""
    cc, ccbin, ccdiv = (disc.read(f"DATA/COURSE/{n}") for n in archive_names(index))
    return load_course(index, cc, ccbin, ccdiv if split else None)


def swatch_colours(mesh: model.Mesh, atlas: picture.Picture, shade: bool = True) -> np.ndarray:
    """(triangles, 3) uint8: the atlas colour under each triangle's corners' mean texture coordinate (wrapped), times the
    mean vertex grey / 128 when `shade` (the PS2 modulates the texture by the vertex colour, 128 = 1.0). On the scenery
    99-100 % of triangles sample a single swatch (§3.2)."""
    h, w = atlas.pixels.shape
    uv = mesh.uvs.reshape(-1, 3, 2).mean(axis=1) % 1.0
    px = np.clip((uv[:, 0] * w).astype(int), 0, w - 1)
    py = np.clip((uv[:, 1] * h).astype(int), 0, h - 1)
    rgb = atlas.rgb()[py, px].astype(float)
    if shade:
        grey = mesh.colours[:, :3].reshape(-1, 3, 3).mean(axis=(1, 2)) / 128.0
        rgb = rgb * grey[:, None]
    return np.clip(rgb, 0, 255).astype(np.uint8)
