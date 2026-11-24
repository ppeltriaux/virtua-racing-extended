"""Weather stage 6: the storm's three samples, made by this code at build time (spec 5.6; ported from the recon's generator,
`spike/p66_thunder.py` on branch `phase66-thunder-recon`, its version 2 with round 4's settings "V4"). Nothing is read: no file, no
recording, no third-party audio; pure Python with its own xorshift32 random numbers and IEEE doubles. Guaranteed: the same bytes on
every run of this toolchain (tests/test_weather_sound.py pins their SHA-256 to the prototype's). It uses the C library's exp, log,
tanh, sin and cos, which another platform's libm may round differently in the last bit: such a difference shows as a failed pin.

The sound board's MultiPCM chips play 12-bit signed linear PCM (two points in three bytes; a table entry's start with bit 22 set) and
a sample holds at most 65 535 points. The sound program's pitch table plays note 0x30 at 20 000 Hz, note 0x2c at 15 814.6 Hz and note
0x1c at 6 294.3 Hz (the rates below); a sample is made at the rate of the note that plays it.

  crack   the thunder's impact (Pascal: "the thunder sound is good as A (one crack)"): full scale on the first point, a 1-3 ms broadband
          snap (an N-wave and noise decaying in 1.2 ms), then 150 ms of dense crackle; no low end (high-passed at 250 Hz); 0.35 s at
          20 000 Hz, heavily soft-clipped (drive 6) for loudness at the same peak
  rumble  the boom and the roll: a hard 40-110 Hz boom (4 ms attack, 0.4 s decay), then 40-120 Hz band noise with slow random surges
          (0.9 Hz), a 45-70 Hz sub layer and a 140-600 Hz body with a 6 Hz ripple so small speakers carry it; held 1.6 s, decaying
          over the rest of its 6.5 s at 6 294.3 Hz (the content is below ~1 kHz: the low rate buys the length); drive 6. The distant
          thunder plays it from 0.6 s in (a second table entry into the same data, past the boom)
  rain    a seamless 2 s loop: hiss shaped to 2-7.5 kHz (where a full-throttle engine and the music are weakest), a faint low wash,
          and a patter of droplet ticks (450 a second); its last 0.2 s cross-faded (equal power) into its head; 15 814.6 Hz; drive 4

The owner's path to these (quoted exactly, docs/spike/2026-11-phase66-thunder-recon.md): "the initial sound for the thunder is not good,
it should be louder here it feel like a rock falling in some water, lightning impact is very bang like. the second rumble should have
more bass i think (loudness" (version 2); "actually i like 13!" (crack A with the rumble); "rain is too low i cant hear it and i think
same for the thunder" (round 4: the heavier clipping and the rain's 2-7.5 kHz band)."""
from __future__ import annotations

import math
from dataclasses import dataclass
from functools import lru_cache

CRACK_RATE, RUMBLE_RATE, RAIN_RATE = 20000.0, 6294.3, 15814.6       # Hz: notes 0x30, 0x1c, 0x2c of the sound program's pitch table
CRACK_NOTE, RUMBLE_NOTE, RAIN_NOTE = 0x30, 0x1C, 0x2C
MAX_POINTS = 65535                                                  # a MultiPCM sample's length is a 16-bit count


class Rng:
    """xorshift32 (13, 17, 5): a fixed stream on every platform."""

    def __init__(self, seed: int):
        self.s = (seed & 0xFFFFFFFF) or 0x9E3779B9

    def u32(self) -> int:
        s = self.s
        s ^= (s << 13) & 0xFFFFFFFF
        s ^= s >> 17
        s ^= (s << 5) & 0xFFFFFFFF
        self.s = s
        return s

    def uni(self) -> float:
        """Uniform in [0, 1)."""
        return self.u32() / 4294967296.0

    def white(self) -> float:
        """Uniform in [-1, 1)."""
        return self.uni() * 2.0 - 1.0


# ---- building blocks ------------------------------------------------------------------------------------------------------------
def lowpass(x: list[float], fc: float, fs: float, poles: int = 2) -> list[float]:
    """`poles` one-pole low-pass filters in series at `fc`."""
    a = 1.0 - math.exp(-2.0 * math.pi * fc / fs)
    for _ in range(poles):
        y, out = 0.0, []
        for v in x:
            y += a * (v - y)
            out.append(y)
        x = out
    return x


def highpass(x: list[float], fc: float, fs: float) -> list[float]:
    """The signal less its one-pole low-pass at `fc`."""
    lp = lowpass(x, fc, fs, 1)
    return [v - w for v, w in zip(x, lp)]


def noise(rng: Rng, n: int) -> list[float]:
    return [rng.white() for _ in range(n)]


def mix_in(dst: list[float], src: list[float], at: int, gain: float) -> None:
    """dst[at + i] += gain * src[i], as far as dst reaches."""
    for i, v in enumerate(src):
        j = at + i
        if j >= len(dst):
            break
        dst[j] += gain * v


def flutter(rng: Rng, n: int, fs: float, rate: float, depth: float) -> list[float]:
    """A slow random gain 1 +- depth: random points `rate` a second joined by smoothstep curves."""
    step = max(1, int(fs / rate))
    pts = [rng.white() for _ in range(n // step + 3)]
    out = []
    for i in range(n):
        k, f = divmod(i, step)
        u = f / step
        u = u * u * (3 - 2 * u)
        out.append(1.0 + depth * (pts[k] * (1 - u) + pts[k + 1] * u))
    return out


def bandnoise(rng: Rng, n: int, fs: float, lo: float, hi: float, poles: int = 2) -> list[float]:
    """Noise between `lo` and `hi` (`poles` low-passes, then as many high-passes), peak 1."""
    x = lowpass(noise(rng, n), hi, fs, poles)
    for _ in range(poles):
        x = highpass(x, lo, fs)
    pk = max(1e-9, max(abs(v) for v in x))
    return [v / pk for v in x]


def softclip(y: list[float], drive: float) -> list[float]:
    """Normalised, a tanh curve driven by `drive`, normalised again to full scale: louder for the same peak."""
    pk = max(1e-9, max(abs(v) for v in y))
    y = [math.tanh(drive * v / pk) for v in y]
    pk = max(abs(v) for v in y)
    return [v / pk for v in y]


def fade_out(y: list[float], points: int) -> None:
    """A half-cosine fade over the last `points`."""
    n = len(y)
    for i in range(points):
        y[n - points + i] *= 0.5 * (1 + math.cos(math.pi * i / points))


def snap(rng: Rng, fs: float, at: int, gain: float, y: list[float]) -> None:
    """A gunshot-like snap at `at`: an N-wave (an instant rise to +1 held 0.25 ms, a swing to -0.8 decaying in 0.6 ms, nothing after
    3 ms) plus white noise decaying in 1.2 ms; its first point exactly 1."""
    s = [0.0] * int(0.012 * fs)
    for i in range(len(s)):
        t = i / fs
        nw = 1.0 if t < 0.00025 else (-0.8 * math.exp(-(t - 0.00025) / 0.0006) if t < 0.003 else 0.0)
        s[i] = nw + 0.9 * rng.white() * math.exp(-t / 0.0012)
    s[0] = 1.0
    mix_in(y, s, at, gain)


def crackle(rng: Rng, fs: float, y: list[float], t0: float, length: float, rate0: float, gain: float, tau: float) -> None:
    """The tearing after a snap: random impulses (single points and micro-bursts up to 0.8 ms), `rate0` a second at first, thinning to
    200 a second and fading (time constant `tau`) over `length` seconds from `t0`."""
    t = t0
    while t < t0 + length:
        u = (t - t0) / length
        dens = rate0 * (1.0 - u) ** 1.5 + 200.0
        t += -math.log(1.0 - rng.uni()) / dens
        i = int(t * fs)
        if i >= len(y):
            break
        amp = gain * (0.3 + 0.7 * rng.uni()) * math.exp(-(t - t0) / tau)
        m = 1 + int(rng.uni() * 0.0008 * fs)
        for k in range(m):
            if i + k < len(y):
                y[i + k] += amp * rng.white() * math.exp(-k / max(1.0, 0.25 * m))


# ---- the three samples (round 4's settings: the prototype's V4) ------------------------------------------------------------------
def crack(fs: float = CRACK_RATE, seed: int = 0xC4AC + ord("a"), drive: float = 6.0) -> list[float]:
    """The thunder's crack (the recon's impact A): a snap and a 150 ms crackle, 250 Hz-9 kHz, 0.35 s, positive first point at full
    scale."""
    rng = Rng(seed)
    n = int(fs * 0.35)
    y = [0.0] * n
    snap(rng, fs, 0, 1.0, y)
    crackle(rng, fs, y, 0.002, 0.15, 6000.0, 0.75, 0.06)
    y = highpass(highpass(y, 250.0, fs), 250.0, fs)
    y = lowpass(y, 9000.0, fs, 1)
    fade_out(y, int(0.05 * fs))
    y = softclip(y, drive)
    if y[0] < 0:
        y = [-v for v in y]
    y[0] = 1.0
    return y


def rumble(fs: float = RUMBLE_RATE, seconds: float = 6.5, seed: int = 0xB0B, drive: float = 6.0, body: float = 1.0,
           body_hi: float = 600.0) -> list[float]:
    """The boom and the roll (see the module docstring), the last 0.5 s faded out."""
    rng = Rng(seed)
    n = int(fs * seconds)
    y = [0.0] * n
    boom = bandnoise(rng, int(1.4 * fs), fs, 40.0, 110.0, 2)
    mix_in(y, [v * min(1.0, i / (0.004 * fs)) * math.exp(-i / (0.40 * fs)) for i, v in enumerate(boom)], 0, 1.5)
    low = bandnoise(rng, n, fs, 40.0, 120.0, 2)
    sub = bandnoise(rng, n, fs, 45.0, 70.0, 2)
    mid = bandnoise(rng, n, fs, 140.0, body_hi, 2)
    surge = flutter(rng, n, fs, 0.9, 0.55)
    rip = flutter(rng, n, fs, 6.0, 0.35)
    for i in range(n):
        t = i / fs
        env = min(1.0, t / 0.15) * (1.0 if t < 1.6 else math.exp(-(t - 1.6) / 1.35))
        y[i] += env * surge[i] * (0.80 * low[i] + 0.55 * sub[i] + body * mid[i] * rip[i])
    fade_out(y, int(0.5 * fs))
    return softclip(y, drive)


def rain(fs: float = RAIN_RATE, seconds: float = 2.0, seed: int = 0x4A1, lo: float = 2000.0, hi: float = 7500.0,
         wash_k: float = 0.08, drive: float = 4.0) -> list[float]:
    """The rain bed's loop (see the module docstring): `seconds` long, its point -1 running on into point 0."""
    rng = Rng(seed)
    c = int(0.2 * fs)
    n = int(fs * seconds) + c
    hiss = highpass(highpass(lowpass(noise(rng, n), hi, fs, 1), lo, fs), lo, fs)
    wash = highpass(lowpass(noise(rng, n), 900.0, fs, 2), 150.0, fs)
    y = [0.9 * h + wash_k * w for h, w in zip(hiss, wash)]
    t = 0.0
    while t < n / fs:
        t += -math.log(1.0 - rng.uni()) / 450.0
        i = int(t * fs)
        g = 1 + int(rng.uni() * 0.0015 * fs)
        amp = 0.6 * rng.uni() ** 2
        for k in range(g):
            if i + k < n:
                y[i + k] += amp * rng.white() * math.exp(-k / max(1.0, 0.3 * g))
    m = n - c
    out = y[:m]
    for i in range(c):
        u = i / c
        out[i] = y[i] * math.sin(0.5 * math.pi * u) + y[m + i] * math.cos(0.5 * math.pi * u)
    return softclip(out, drive)


# ---- the chip's format -----------------------------------------------------------------------------------------------------------
def to_s12(y: list[float], seed: int = 0x5EED, loop: bool = False) -> bytes:
    """12-bit signed with TPDF dither, packed as the chip reads it (even point = byte0 << 4 | byte1 & 0xf, odd point = byte2 << 4 |
    byte1 >> 4). A one-shot's last point is 0: the chip loops on it, silence; a loop keeps its last point."""
    rng = Rng(seed)
    q = [max(-2047, min(2047, round(v * 2047.0 + (rng.uni() - rng.uni())))) for v in y]
    if not loop:
        q[-1] = 0
    if len(q) % 2:
        q.append(0)
    out = bytearray()
    for a, b in zip(q[0::2], q[1::2]):
        out += bytes([(a >> 4) & 0xFF, ((b & 0xF) << 4) | (a & 0xF), (b >> 4) & 0xFF])
    return bytes(out)


def s12_points(b: bytes) -> list[int]:
    """The points of 12-bit packed bytes (to_s12's inverse, the padding point included)."""
    pts = []
    for i in range(0, len(b), 3):
        a = (b[i] << 4) | (b[i + 1] & 0xF)
        c = (b[i + 2] << 4) | (b[i + 1] >> 4)
        pts += [a - 4096 if a & 0x800 else a, c - 4096 if c & 0x800 else c]
    return pts


@dataclass(frozen=True)
class Sample:
    name: str
    data: bytes                         # 12-bit packed, as written into the sample ROM
    points: int                         # the sample's length in points (the padding point not counted)
    rate: float                         # Hz, at its note
    note: int                           # the sound program's note that plays it at `rate`
    loop: bool                          # True: the rain's seamless loop (loop point 0); else a one-shot ending on a 0 point


@lru_cache(maxsize=None)
def samples() -> dict[str, Sample]:
    """The three samples: crack, rumble, rain (made once a process: about 0.2 s)."""
    out = {}
    for name, fn, rate, note, loop in (("crack", crack, CRACK_RATE, CRACK_NOTE, False), ("rumble", rumble, RUMBLE_RATE, RUMBLE_NOTE, False),
                                       ("rain", rain, RAIN_RATE, RAIN_NOTE, True)):
        y = fn()
        if len(y) > MAX_POINTS:
            raise ValueError(f"the {name} sample has {len(y)} points, a MultiPCM sample at most {MAX_POINTS}")
        out[name] = Sample(name, to_s12(y, loop=loop), len(y), rate, note, loop)
    return out
