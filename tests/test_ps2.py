"""vrtools.ps2: the PS2 disc's readers, on synthetic bytes; the disc itself only through VR_PS2_DISC (skipped without)."""

import struct

import numpy as np
import pytest

from vrtools.ps2 import course, disc, model, pac, pat, picture, vcp


# ---- LZSS and archives -------------------------------------------------------------------------------------------

def literals(data: bytes) -> bytes:
    """An LZSS stream of literals only (flag 0xff before every eight bytes)."""
    out = bytearray()
    for k in range(0, len(data), 8):
        chunk = data[k:k + 8]
        out.append((1 << len(chunk)) - 1)
        out += chunk
    return bytes(out)


def pac_file(image: bytes) -> bytes:
    return struct.pack("<II", 1, len(image)) + literals(image)


def archive(files: list[tuple[str, bytes]]) -> bytes:
    head = struct.pack("<I", len(files)).ljust(16, b"\0")
    for name, data in files:
        head += name.encode().ljust(16, b"\0") + struct.pack("<I", len(data)) + b"\0" * 12
    body = b"".join(d + b"\0" * (-len(d) % 64) for _, d in files)
    return head + body


def test_lzss_literals_and_references():
    # flags 0b0000_0101 read LSB first: literal 'a', reference, literal 'b', then a reference into the zero-filled ring
    ring_pos = 4078                                   # where 'a' was written
    ref_a = bytes([ring_pos & 0xFF, ((ring_pos >> 4) & 0xF0) | 0])          # 'a' again, length 3: 'a', 'a', 'a' (overlap)
    zeros = bytes([0x00, 0x01])                                             # position 0 (zeros), length 4
    stream = bytes([0b0000_0101]) + b"a" + ref_a + b"b" + zeros
    assert pac.lzss_decode(stream, 1 + 3 + 1 + 4) == b"aaaab" + b"\0" * 4


def test_lzss_short_stream_raises():
    with pytest.raises(pac.PacError):
        pac.lzss_decode(literals(b"abc"), 10)


def test_archive_entries_pad_to_64():
    files = [("chk.bin", b"x" * 70), ("NORMAL.PAT", b"y" * 5), ("cous00.TM2", b"z" * 64)]
    image = archive(files)
    es = pac.entries(image)
    assert [e.name for e in es] == ["chk.bin", "NORMAL.PAT", "cous00.TM2"]
    assert es[0].offset == 16 + 3 * 32
    assert es[1].offset == es[0].offset + 128 and es[2].offset == es[1].offset + 64
    got = pac.read_pac(pac_file(image))
    assert got == dict(files)
    assert pac.find(got, "COUS00.tm2") == b"z" * 64


def test_archive_size_past_end_raises():
    image = bytearray(archive([("a.bin", b"1234")]))
    image[16 + 16:16 + 20] = struct.pack("<I", 4096)
    with pytest.raises(pac.PacError):
        pac.entries(bytes(image))


def test_pac_magic_checked():
    with pytest.raises(pac.PacError):
        pac.unpack(struct.pack("<II", 2, 0))


# ---- models -------------------------------------------------------------------------------------------------------

def model_file(tris: np.ndarray, uvs: np.ndarray, grey: float = 64.0, fmt: int = 0x1813, texture: str = "cous00.tm2") -> bytes:
    n = len(tris) * 3
    head = struct.pack("<4I", 1, 0, 0, 5)
    for k, name in enumerate(("Frame", "Micro", "Shape", "Hrchy", "Tim2")):
        head += name.encode().ljust(12, b"\0") + struct.pack("<I", 0x100 + 16 * k)
    head += texture.encode().ljust(32, b"\0")
    head = head.ljust(0x100, b"\0")
    pos = np.concatenate([tris.reshape(n, 3), np.ones((n, 1))], 1)
    nrm = np.tile([0.0, -1.0, 0.0, 1.0], (n, 1))
    uv = np.concatenate([uvs.reshape(n, 2), np.tile([1.0, 0.0], (n, 1))], 1)
    col = np.tile([grey, grey, grey, 128.0], (n, 1))
    arrays = np.concatenate([pos, nrm, uv, col]).astype("<f4").tobytes()
    return head + struct.pack("<4I", 0, n * 16, fmt, n) + arrays + b"\0" * 1168


def test_model_one_triangle_list():
    tris = np.array([[[0, 0, 0], [1, 0, 0], [0, 0, 1]], [[1, 0, 0], [1, 0, 1], [0, 0, 1]]], float)
    uvs = np.full((2, 3, 2), 0.25)
    data = model_file(tris, uvs)
    assert model.is_model(data)
    assert list(model.chunks(data))[:4] == ["Frame", "Micro", "Shape", "Hrchy"]
    ms = model.meshes(data)
    assert len(ms) == 1 and len(ms[0]) == 2 and ms[0].format == 0x1813
    np.testing.assert_allclose(ms[0].triangles, tris)
    np.testing.assert_allclose(ms[0].uvs, 0.25)
    assert model.texture_names(data) == ["cous00.tm2"]


def test_model_rejects_non_model():
    with pytest.raises(model.ModelError):
        model.chunks(b"\0" * 64)


# ---- collision and points -----------------------------------------------------------------------------------------

def vcp_file(tris: np.ndarray, attrs: list[int], tail: bytes = b"\0\0") -> bytes:
    out = struct.pack("<4if2I", -6, -40, 16, 13, 6.0, len(tris), len(tris))
    for t, a in zip(tris, attrs):
        v = np.concatenate([t, np.ones((3, 1))], 1).astype("<f4").tobytes()
        out += v + struct.pack("<8I", 0, 0, 0x12345678, 0, a, 0, 0, 0)
    return out + tail


def test_vcp_triangles_and_kinds():
    tris = np.array([[[0, 0, 0], [5, 0, 0], [0, 0, 5]], [[0, -9, 0], [0, 1, 0], [0, 0, 5]]], float)
    s = vcp.read_vcp(vcp_file(tris, [0x0A00, 0x1401], tail=b"\0" * 10))
    assert s.bounds == (-6, -40, 16, 13) and s.cell == 6.0 and len(s) == 2 and s.tail == 10
    np.testing.assert_allclose(s.triangles, tris)
    assert s.kinds.tolist() == [vcp.KIND_TARMAC, vcp.KIND_KERB]
    m = vcp.merged([s, s])
    assert len(m) == 4 and m.tail == 20


def test_vcp_counts_must_agree():
    data = bytearray(vcp_file(np.zeros((1, 3, 3)), [0]))
    data[24:28] = struct.pack("<I", 2)
    with pytest.raises(vcp.VcpError):
        vcp.read_vcp(bytes(data))


def test_pat_points_and_densify():
    pts = [(0.0, 0.0, 0.0), (0.0, 0.0, -10.0), (10.0, 0.0, -10.0)]
    data = struct.pack("<I", 3) + b"".join(struct.pack("<3f", *p) + b"\0" * 20 for p in pts)
    p = pat.read_pat(data)
    np.testing.assert_allclose(p, pts)
    d = pat.densify(p[:, [0, 2]], step=1.0)
    assert len(d) == int(np.ceil(10 + 10 + np.hypot(10, 10)))
    with pytest.raises(pat.PatError):
        pat.read_pat(data[:-1])


# ---- pictures -----------------------------------------------------------------------------------------------------

def test_picture_8bit_clut_order():
    clut = np.zeros((256, 4), np.uint8)
    for i in range(256):
        clut[i] = (i, 0, 0, 0x80)
    stored = picture.unswizzle_clut(clut)             # the swap is its own inverse
    px = np.array([[8, 16], [15, 23]], np.uint8)
    data = b"\0" * 64 + px.tobytes() + stored.tobytes()
    p = picture.decode(data, 2)
    assert p.rgb()[:, :, 0].tolist() == [[8, 16], [15, 23]]


def test_picture_4bit_low_nibble_first():
    clut = np.array([(k * 16, k, 0, 0x80) for k in range(16)], np.uint8)
    data = b"\0" * 64 + bytes([0x21, 0x43]) + clut.tobytes()
    p = picture.decode(data, 4, bpp=4)
    assert p.pixels.tolist() == [[1, 2, 3, 4]]


def test_swatch_colour_times_vertex_grey():
    tris = np.zeros((1, 3, 3))
    uvs = np.array([[[0.6, -0.9], [0.61, -0.9], [0.6, -0.89]]])     # wraps to (0.6, 0.1): column 1, row 0 of a 2x2 atlas
    m = model.meshes(model_file(tris, uvs, grey=64.0))[0]
    atlas = picture.Picture(np.array([[0, 1], [2, 3]], np.uint8),
                            np.array([(0, 0, 0, 128), (200, 100, 50, 128), (0, 0, 0, 128), (0, 0, 0, 128)], np.uint8))
    assert course.swatch_colours(m, atlas).tolist() == [[100, 50, 25]]
    assert course.swatch_colours(m, atlas, shade=False).tolist() == [[200, 100, 50]]


# ---- the disc image -----------------------------------------------------------------------------------------------

def _dir_record(name: bytes, extent: int, size: int, flags: int = 0) -> bytes:
    length = 33 + len(name) + (1 - len(name) % 2)
    rec = bytearray(length)
    rec[0] = length
    rec[2:6] = struct.pack("<I", extent)
    rec[10:14] = struct.pack("<I", size)
    rec[25] = flags
    rec[32] = len(name)
    rec[33:33 + len(name)] = name
    return bytes(rec)


def test_mode2_image_reads_files(tmp_path):
    body = b"hello PS2"
    root = _dir_record(b"\x00", 18, 2048, 2) + _dir_record(b"\x01", 18, 2048, 2) + _dir_record(b"SYSTEM.CNF;1", 19, len(body))
    pvd = bytearray(2048)
    pvd[0:6] = b"\x01CD001"
    pvd[156:190] = _dir_record(b"\x00", 18, 2048, 2)[:34]
    sectors = [bytes(2048)] * 16 + [bytes(pvd), bytes(2048), root.ljust(2048, b"\0"), body.ljust(2048, b"\0")]
    raw = b"".join(b"\0" * 24 + s + b"\0" * 280 for s in sectors)
    (tmp_path / "t.bin").write_bytes(raw)
    (tmp_path / "t.cue").write_text('FILE "t.bin" BINARY\n  TRACK 01 MODE2/2352\n    INDEX 01 00:00:00\n')
    d = disc.Ps2Disc(tmp_path / "t.cue")
    assert [e.path for e in d.entries()] == ["SYSTEM.CNF"]
    assert d.read("SYSTEM.CNF") == body


@pytest.fixture
def ps2_disc_path():
    p = disc.ps2_disc()
    if p is None or not p.exists():
        pytest.skip(f"set {disc.ENV} to the PS2 disc .cue")
    return p


def test_disc_additional_courses(ps2_disc_path):
    d = disc.Ps2Disc(ps2_disc_path)
    assert d.read("SYSTEM.CNF").startswith(b"BOOT2")
    want = {3: (14, 59), 4: (12, 41), 5: (14, 97)}                  # (collision sections, racing-line points), recon §2-§3
    for i, (sections, points) in want.items():
        c = course.load_from_disc(d, i)
        assert len(c.road) == len(c.walls) == sections
        assert len(c.paths["NORMAL"]) == points
        assert len(c.sections) >= sections and c.split_sections          # one list per texture a file uses
        assert "cous00" in c.atlases and "sky0a" in c.skies
    assert "PIT00" in course.load_from_disc(d, 4, split=False).paths


def test_model_one_list_per_texture():
    tris = np.zeros((1, 3, 3))
    uvs = np.full((1, 3, 2), 0.25)
    first = model_file(tris, uvs, texture="cous00.tm2")
    n = 3
    second = struct.pack("<4I", 1, n * 16, 0x1813, n) + np.concatenate(
        [np.tile([1.0, 2.0, 3.0, 1.0], (n, 1)), np.tile([0.0, -1.0, 0.0, 1.0], (n, 1)), np.tile([0.5, 0.5, 1.0, 0.0], (n, 1)),
         np.tile([64.0, 64.0, 64.0, 128.0], (n, 1))]).astype("<f4").tobytes()
    data = first[:-1168] + second + b"\0" * 1168
    data = data.replace(b"cous00.tm2".ljust(32, b"\0"), b"cous00.tm2\0\0cous00b.tm2".ljust(32, b"\0"), 1)
    ms = model.meshes(data)
    assert [m.texture for m in ms] == [0, 1]
    assert [m.texture_name for m in ms] == ["cous00.tm2", "cous00b.tm2"]
