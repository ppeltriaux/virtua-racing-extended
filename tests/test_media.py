"""Media helpers for the public page (Phase 13): MAME AVI captures to clips, stills, posters, the share card and the hub card."""
import subprocess
from pathlib import Path

import pytest

pytestmark = pytest.mark.skipif(not __import__("shutil").which("ffmpeg") or not __import__("shutil").which("ffprobe"),
                                reason="ffmpeg and ffprobe are needed")


def _synthetic_avi(path: Path, seconds: float = 12.0) -> Path:
    """What MAME writes: raw video 496×384 at 57.52 fps with 48 kHz stereo PCM audio."""
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", f"testsrc=size=496x384:rate=57.52",
                    "-f", "lavfi", "-i", "sine=frequency=440:sample_rate=48000", "-ac", "2", "-t", str(seconds),
                    "-c:v", "rawvideo", "-pix_fmt", "bgr24", "-c:a", "pcm_s16le", str(path)], check=True)
    return path


def test_encode_clip_concatenates_cuts_at_2x_and_fits(tmp_path):
    from vrtools.mame.media import encode_clip
    avi = _synthetic_avi(tmp_path / "in.avi")
    out = tmp_path / "clip.mp4"
    p = encode_clip(avi, out, [(1.0, 3.0), (6.0, 4.0)])
    assert p["codec"] == "h264" and p["pix_fmt"] == "yuv420p" and (p["width"], p["height"]) == (992, 768)
    assert 6.8 <= p["duration"] <= 7.2 and p["audio"] == "aac" and p["size"] < 6_000_000
    assert p["color_space"] == "smpte170m"                        # review M5: tagged as the BT.601 matrix swscale used, so players do not guess BT.709
    head = out.read_bytes()[:65536]
    assert b"moov" in head and (b"mdat" not in head or head.index(b"moov") < head.index(b"mdat"))


def test_encode_clip_refuses_what_cannot_fit(tmp_path):
    from vrtools.mame.media import MediaError, encode_clip
    avi = _synthetic_avi(tmp_path / "in.avi", seconds=4.0)
    with pytest.raises(MediaError):
        encode_clip(avi, tmp_path / "clip.mp4", [(0.0, 4.0)], max_bytes=20_000)


def test_still_poster_card_and_crop_sizes(tmp_path):
    from PIL import Image
    from vrtools.mame.media import card_crop, poster, share_card, still
    avi = _synthetic_avi(tmp_path / "in.avi", seconds=3.0)
    s = still(avi, 1.0, tmp_path / "s.png")
    assert Image.open(s).size == (496, 384)
    p = poster(avi, 1.0, tmp_path / "p.png")
    assert Image.open(p).size == (992, 768)
    og = share_card(s, "VIRTUA RACING EXTENDED", "The Saturn's seven courses in the arcade game", tmp_path / "og.jpg")
    im = Image.open(og)
    assert im.size == (1200, 630) and im.format == "JPEG" and og.stat().st_size < 1_000_000
    c = card_crop(s, tmp_path / "card.png")
    assert Image.open(c).size == (320, 213)


def test_run_mame_passes_extra_args(tmp_path, monkeypatch):
    import vrtools.mame.runner as runner
    seen = {}

    class Done:
        returncode = 0
        stdout = "Average speed: 100% (5 seconds)"
        stderr = ""

    def fake_run(cmd, **kw):
        seen["cmd"] = cmd
        return Done()
    monkeypatch.setattr(runner.subprocess, "run", fake_run)
    runner.run_mame(Path("x.lua"), 5, tmp_path, tmp_path, extra_args=["-aviwrite", "x.avi"])
    assert seen["cmd"][-2:] == ["-aviwrite", "x.avi"]
