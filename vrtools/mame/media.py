"""Media for the public page (Phase 13): MAME's AVI captures (496×384, 57.52 fps, 48 kHz stereo PCM) to the kit's
clips (H.264 yuv420p at 2×, AAC, faststart, under 6 MB), native stills, 2× posters, the 1200×630 share card and
the hub's 3:2 shelf card. ffmpeg / ffprobe on PATH; Pillow for the pictures."""
from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

NATIVE = (496, 384)                  # the Model 1's frame as MAME records it
CLIP_MAX_BYTES = 6_000_000           # kit rule 4: each video under about 6 MB
SHARE_SIZE = (1200, 630)
CARD_SIZE = (320, 213)               # the hub's shelf card, 3:2
NAVY = (0x0B, 0x14, 0x46)
FONT_CANDIDATES = ("/System/Library/Fonts/Supplemental/Arial Black.ttf", "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
                   "/Library/Fonts/Arial Bold.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf")


class MediaError(Exception):
    pass


def has_tools() -> bool:
    return bool(shutil.which("ffmpeg") and shutil.which("ffprobe"))


def _run(cmd: list[str]) -> None:
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        raise MediaError(f"{cmd[0]} failed: {proc.stderr[-800:]}")


def probe(path: Path) -> dict:
    """codec, pix_fmt, width, height, duration (s), audio codec (or None) and size of a media file."""
    proc = subprocess.run(["ffprobe", "-v", "error", "-print_format", "json", "-show_streams", "-show_format", str(path)],
                          capture_output=True, text=True)
    if proc.returncode != 0:
        raise MediaError(f"ffprobe failed on {path}: {proc.stderr[-400:]}")
    info = json.loads(proc.stdout)
    video = next((s for s in info["streams"] if s.get("codec_type") == "video"), None)
    audio = next((s for s in info["streams"] if s.get("codec_type") == "audio"), None)
    if video is None:
        raise MediaError(f"{path}: no video stream")
    return {"codec": video.get("codec_name"), "pix_fmt": video.get("pix_fmt"), "width": int(video["width"]),
            "height": int(video["height"]), "duration": float(info["format"].get("duration") or video.get("duration") or 0.0),
            "audio": audio.get("codec_name") if audio else None, "size": Path(path).stat().st_size,
            "color_space": video.get("color_space")}


def encode_clip(avi: Path, out: Path, cuts: list[tuple[float, float]], scale: int = 2,
                max_bytes: int = CLIP_MAX_BYTES) -> dict:
    """The `(start_s, length_s)` cuts of `avi` (a cut may name another source as a third element), joined, scaled by
    `scale` with nearest neighbour, H.264 yuv420p
    (high profile, slow preset) with AAC 128 k and the moov atom first; re-encoded coarser up to three times when
    the file exceeds `max_bytes`, MediaError when it still does. Returns `probe(out)`."""
    if not cuts:
        raise MediaError("no cuts")
    out = Path(out)
    inputs: list[str] = []
    for cut in cuts:                                                   # (start, length) of `avi`, or (start, length, other_avi)
        start, length = cut[0], cut[1]
        src = cut[2] if len(cut) > 2 else avi
        inputs += ["-ss", f"{start:.3f}", "-t", f"{length:.3f}", "-i", str(src)]
    n = len(cuts)
    graph = "".join(f"[{i}:v:0][{i}:a:0]" for i in range(n)) + f"concat=n={n}:v=1:a=1[cv][ca];" \
            f"[cv]scale=iw*{scale}:ih*{scale}:flags=neighbor,format=yuv420p[v]"
    for crf in (20, 23, 26, 29):
        _run(["ffmpeg", "-v", "error", "-y", *inputs, "-filter_complex", graph, "-map", "[v]", "-map", "[ca]",
              "-c:v", "libx264", "-profile:v", "high", "-preset", "slow", "-crf", str(crf), "-r", "57.52",
              "-colorspace", "smpte170m", "-color_primaries", "smpte170m", "-color_trc", "smpte170m", "-color_range", "tv",   # what swscale's RGB→YUV used (BT.601): tagged, so a player does not assume BT.709 at 768 lines
              "-c:a", "aac", "-b:a", "128k", "-movflags", "+faststart", str(out)])
        if out.stat().st_size <= max_bytes:
            return probe(out)
    raise MediaError(f"{out.name}: {out.stat().st_size} bytes at crf 29, over {max_bytes}; shorten the cuts")


def still(avi: Path, at_s: float, out: Path) -> Path:
    """One frame at native size as PNG."""
    _run(["ffmpeg", "-v", "error", "-y", "-ss", f"{at_s:.3f}", "-i", str(avi), "-frames:v", "1", str(out)])
    return Path(out)


def poster(avi: Path, at_s: float, out: Path, scale: int = 2) -> Path:
    """One frame scaled by `scale` with nearest neighbour, as PNG (the video's poster)."""
    _run(["ffmpeg", "-v", "error", "-y", "-ss", f"{at_s:.3f}", "-i", str(avi), "-frames:v", "1",
          "-vf", f"scale=iw*{scale}:ih*{scale}:flags=neighbor", str(out)])
    return Path(out)


def _font(size: int):
    from PIL import ImageFont
    for path in FONT_CANDIDATES:
        if Path(path).exists():
            return ImageFont.truetype(path, size)
    return ImageFont.load_default(size)


def share_card(still_png: Path, title: str, subtitle: str, out: Path, accent: str = "#ff8a00") -> Path:
    """A 1200×630 JPEG for link previews: the still at 2× in a pixel frame on the left, the title and subtitle on
    the right over the hub's navy, a thin accent rule under the title."""
    from PIL import Image, ImageDraw
    canvas = Image.new("RGB", SHARE_SIZE, NAVY)
    shot = Image.open(still_png).convert("RGB")
    sw, sh = 744, 576                                              # 1.5× of 496×384, fits the 630 with a margin
    shot = shot.resize((sw, sh), Image.NEAREST)
    x0, y0 = 28, (SHARE_SIZE[1] - sh) // 2
    draw = ImageDraw.Draw(canvas)
    draw.rectangle((x0 - 6, y0 - 6, x0 + sw + 5, y0 + sh + 5), outline=(255, 255, 255), width=6)
    canvas.paste(shot, (x0, y0))
    tx = x0 + sw + 36
    width = SHARE_SIZE[0] - tx - 28
    size = 44
    font = _font(size)
    lines = _wrap(draw, title, font, width)
    while len(lines) > 3 and size > 24:
        size -= 4; font = _font(size); lines = _wrap(draw, title, font, width)
    y = 150
    for line in lines:
        draw.text((tx, y), line, font=font, fill=(255, 210, 0))
        y += int(size * 1.25)
    draw.rectangle((tx, y + 10, tx + 140, y + 18), fill=accent)
    y += 40
    sub_font = _font(22)
    for line in _wrap(draw, subtitle, sub_font, width):
        draw.text((tx, y), line, font=sub_font, fill=(255, 255, 255))
        y += 30
    draw.text((tx, SHARE_SIZE[1] - 60), "continuearcade.com", font=_font(20), fill=(0x4D, 0xE3, 0xFF))
    canvas.save(out, "JPEG", quality=88, optimize=True)
    return Path(out)


def _wrap(draw, text: str, font, width: int) -> list[str]:
    words, lines, cur = text.split(), [], ""
    for w in words:
        trial = (cur + " " + w).strip()
        if draw.textlength(trial, font=font) <= width or not cur:
            cur = trial
        else:
            lines.append(cur); cur = w
    if cur:
        lines.append(cur)
    return lines


def card_crop(still_png: Path, out: Path) -> Path:
    """The hub's 320×213 shelf card: a 3:2 crop of the still's centre (496×331), scaled with nearest neighbour."""
    from PIL import Image
    im = Image.open(still_png).convert("RGB")
    w, h = im.size
    ch = round(w * 2 / 3)
    top = max(0, (h - ch) // 2)
    im = im.crop((0, top, w, top + ch)).resize(CARD_SIZE, Image.NEAREST)
    im.save(out, "PNG")
    return Path(out)
