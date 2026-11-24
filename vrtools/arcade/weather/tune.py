"""The weather feature's tune values, one frozen dataclass per module; the defaults are the design's values
(docs/superpowers/specs/2026-11-18-weather-storm-design.md). Stage 3 adds CoverTune, stage 4 LightningTune, stage 5 HandlingTune, stage 6
SoundTune. `Tunes` (weather Task 6J, the join): the one rule for tunes, one field per module by its name; install_weather,
carrier.install / default_modules and every registry factory take it, and each module gets its own field and no other."""
from __future__ import annotations

from dataclasses import dataclass, field, fields


@dataclass(frozen=True)
class ScreenTune:
    """The COURSE WEATHER screen (spec 5.1; each a session lead's call, not yet Pascal's decision, except the hold, which Pascal
    drove in out/p71weather).

    timeout_s: the screen's countdown in the game's displayed seconds (the select countdown shows its timer >> 5 and steps it once a
    logic frame, so 32 steps a displayed second: 10 is the timer 0x140, as COURSE DIRECTION's); the countdown locks the choice shown,
    DRY unless the player steered to RAIN.
    rain_word: the second choice's label and the HUD word in a RAIN race (at most 5 letters: the label slots are 6 bytes, NUL
    included).
    hold_frames: logic frames the COURSE DIRECTION screen shows its lock look before the weather screen opens (16: 34 video frames,
    about 0.59 s)."""
    timeout_s: int = 10
    rain_word: str = "RAIN"
    hold_frames: int = 16

    def __post_init__(self):
        if not 1 <= self.timeout_s <= 11:              # the timer stays below 0x180, where the select's state 1 plays its voice cue
            raise ValueError(f"timeout_s {self.timeout_s}: 1..11")
        if not (1 <= len(self.rain_word) <= 5 and self.rain_word.isascii() and self.rain_word.isalpha() and self.rain_word.isupper()):
            raise ValueError(f"rain_word {self.rain_word!r}: 1..5 capital letters")
        if not 1 <= self.hold_frames <= 255:           # counted down in one byte
            raise ValueError(f"hold_frames {self.hold_frames}: 1..255")

    @property
    def timer(self) -> int:
        """The select countdown's start value: 32 steps a displayed second."""
        return 32 * self.timeout_s


@dataclass(frozen=True)
class RainTune:
    """The rain (spec 5.3, as the owner approved it in spike 48: "the rain is good").

    drops: the falling drops, in `clusters` clusters of 5 (each cluster one of 8 shapes of 5 boxes): 300 in 60.
    splash_range: a drop landing deeper than this (view units, about 1.06 m) leaves no splash: 35 (Pascal, of drops ending without
    one: "it look like they're floating").
    splash_frames: logic frames a splash lasts, one stage a frame (the stage shapes are drawn for 6)."""
    drops: int = 300
    clusters: int = 60
    splash_range: float = 35.0
    splash_frames: int = 6

    def __post_init__(self):
        if not 1 <= self.clusters <= 60 or self.drops != 5 * self.clusters:   # the cells hold 60; a cluster is 5 drops
            raise ValueError(f"drops {self.drops} in clusters {self.clusters}: 5 a cluster, 60 clusters at most")
        if not 3.0 < self.splash_range <= 45.0:                               # nearer than 3 none is drawn; the volume ends at 45
            raise ValueError(f"splash_range {self.splash_range}: over 3, at most 45")
        if self.splash_frames != 6:
            raise ValueError(f"splash_frames {self.splash_frames}: the splash's stage shapes are drawn for 6")


@dataclass(frozen=True)
class CoverTune:
    """Cover (spec 5.4, as the owner approved it in spikes 57 and 68: "the long tunnel in metropolis is perfect", "short tunnel is
    good"; weather/cover.py).

    near: a cover box this near the camera (units, in the box's own frame) can hold clusters: 80.
    exit_angle: a tunnel mouth within this angle of the view direction (degrees) is in view, its curtain shown: 50 (the view's
    half-width is about 50).
    curtain_scale: a long-tunnel curtain cluster's scale at most (spike 57's GCAP): 2.0.
    roof_clusters: the clusters walked under the pits roof's curtain, the others hidden (spike 68: "the number of clusters is the
    knob"; 30 cost about 1.3 ms more): 24."""
    near: float = 80.0
    exit_angle: float = 50.0
    curtain_scale: float = 2.0
    roof_clusters: int = 24

    def __post_init__(self):
        if not 20.0 <= self.near <= 200.0:                 # a box's circle grows with it; the long tunnel's mouths are 40 units wide
            raise ValueError(f"near {self.near}: 20..200")
        if not 10.0 <= self.exit_angle <= 80.0:
            raise ValueError(f"exit_angle {self.exit_angle}: 10..80 degrees")
        if not 1.0 <= self.curtain_scale <= 4.0:
            raise ValueError(f"curtain_scale {self.curtain_scale}: 1..4")
        if not 1 <= self.roof_clusters <= 60:              # the rain's clusters
            raise ValueError(f"roof_clusters {self.roof_clusters}: 1..60")


AIM_DEFAULT = (12.0, 40.0)              # degrees off the view, each side: the approved placement ("beside the course", placement B)
AIM_STREET = (2.0, 10.0)                # down the street (task 8: Metropolis)
METROPOLIS_ENTRY = 6                    # Metropolis's menu entry (rain.METROPOLIS)
AIM_MAX = 40.0                          # degrees: the top of an aim range (the approved range's; the in-view check passes 43 at most)


def _aim_ok(r) -> bool:
    return isinstance(r, tuple) and len(r) == 2 and 0.0 <= r[0] < r[1] <= AIM_MAX


@dataclass(frozen=True)
class LightningTune:
    """Lightning (spec 5.5, as the owner approved it in spike 60/62 and the joined spike 70).

    interval_s: seconds of race between a strike's end and the next strike's start, at random in this range (20-40: the session
    lead's call, "tunable; Pascal did not answer on the interval"). A test-only tune shortens it for the stress build (0.4-1.2).
    distance: units from the car to the bolt's foot, at random in this range (placement B: Pascal, "B").
    stroke_scale: the rods' thickness against spike 56's first build (0.55: "this is it, 45 is great keep it").
    max_onsets_per_s: full-screen flash onsets allowed within ONSET_WINDOW logic frames (1.04 s); the spec's hard rule is three.
    aim_deg: the placement's directions, degrees off the camera's horizontal view direction on either side (lightning.NANG evenly
      from low to high): the approved 12-40 (placement B, "beside the course").
    aim_by_entry: ((menu entry, (low, high)), ...): a course's own aim range instead of aim_deg (task 8). Metropolis (entry 6) aims
      down the street, 2-10: its facades stand 80-105 units high beside the road and hid the bolt (the owner: "the thinder get
      hidden by the building"; on spike 85's play set: "i think that works better on metropolis"). Each range 0 <= low < high <=
      AIM_MAX; an entry listed once."""
    interval_s: tuple = (20.0, 40.0)
    distance: tuple = (300.0, 800.0)
    stroke_scale: float = 0.55
    max_onsets_per_s: int = 3
    aim_deg: tuple = AIM_DEFAULT
    aim_by_entry: tuple = ((METROPOLIS_ENTRY, AIM_STREET),)

    def __post_init__(self):
        lo, hi = self.interval_s
        if not 0.1 <= lo <= hi <= 600.0:
            raise ValueError(f"interval_s {self.interval_s}: 0.1 <= low <= high <= 600")
        lo, hi = self.distance
        if not 100.0 <= lo < hi <= 1000.0:                 # the grids reach 1 024 units from the origin; nearer than 100 is the scenery's
            raise ValueError(f"distance {self.distance}: 100 <= low < high <= 1000")
        if not 0.2 <= self.stroke_scale <= 1.0:
            raise ValueError(f"stroke_scale {self.stroke_scale}: 0.2..1.0")
        if not 1 <= self.max_onsets_per_s <= 3:            # never more than three (spec 5.5)
            raise ValueError(f"max_onsets_per_s {self.max_onsets_per_s}: 1..3")
        if not _aim_ok(self.aim_deg):
            raise ValueError(f"aim_deg {self.aim_deg}: (low, high) degrees, 0 <= low < high <= {AIM_MAX}")
        seen = set()
        for item in self.aim_by_entry:
            if not (isinstance(item, tuple) and len(item) == 2 and isinstance(item[0], int) and 0 <= item[0] <= 255
                    and _aim_ok(item[1])) or item[0] in seen:
                raise ValueError(f"aim_by_entry {self.aim_by_entry}: (entry 0..255 once, (low, high) with 0 <= low < high <= {AIM_MAX})")
            seen.add(item[0])

    def aim_for(self, entry: int) -> tuple:
        """The aim range of menu entry `entry`: its own in aim_by_entry, else aim_deg."""
        return dict(self.aim_by_entry).get(entry, self.aim_deg)


@dataclass(frozen=True)
class HandlingTune:
    """The wet handling (spec 5.7's one table, every value the owner's approved behaviour after driving spike 54/59: "hangling is good
    now!"). Each applies only in a RAIN race's race mode, on the player's race handler, outside a put-back glide and a pit stop and not
    under cover (the opponents' factor: in the race mode, under cover too). The dry column is the game's own.

    slide_threshold: the slide (+0x14e) starts building when the lateral demand |L| (+0x154) exceeds this (dry 546).
    slide_gas: it builds, and can end in a spin, only with the gas above this (of 255); at or below it drains as in the dry.
    spin_slide, spin_kmh, spin_cooldown: a held slide |S| >= spin_slide above spin_kmh km/h ends in the game's flat 360-degree
    spin-out (not the crash flip); then no other for spin_cooldown logic frames (about 1.4-1.8 s of full lock at speed).
    grip_change: added to the grip base (dry 392).
    wheelspin_m0, wheelspin_fade_kmh, wheelspin_gears: at full gas in gears 1..wheelspin_gears the traction is the game's own times
    wheelspin_m0 at a standstill, rising to times 1 at wheelspin_fade_kmh (0-100 km/h 1.96 s against 1.69).
    lock_brake_pct, lock_frames, lock_kmh: the brake at or above lock_brake_pct % for lock_frames logic frames at lock_kmh km/h or
    more locks the front wheels (steering has no effect, the car slows as on a lift); released below release_brake_pct % of brake
    or at release_kmh km/h or less (Pascal: "A", release the brake).
    brake_clamp: the braking force clamp (dry -1820).
    squeal_from: the tyre squeal from |L| above this (dry 364).
    opponents: the opponents' working performance factor (dry 1)."""
    slide_threshold: int = 420
    slide_gas: int = 128
    spin_slide: int = 0x900
    spin_kmh: int = 100
    spin_cooldown: int = 77
    grip_change: int = -16
    wheelspin_m0: float = 0.6
    wheelspin_fade_kmh: int = 60
    wheelspin_gears: int = 3
    lock_brake_pct: int = 80
    lock_frames: int = 8
    lock_kmh: int = 100
    release_brake_pct: int = 40
    release_kmh: int = 20
    brake_clamp: float = -1583.0
    squeal_from: int = 280
    opponents: float = 0.97

    def __post_init__(self):
        checks = {"slide_threshold": 0 < self.slide_threshold < 0x7FFF, "slide_gas": 0 <= self.slide_gas < 255,
                  "spin_slide": 0 < self.spin_slide < 0x8000, "spin_kmh": 0 <= self.spin_kmh < 400,
                  "spin_cooldown": 1 <= self.spin_cooldown <= 255, "grip_change": -255 < self.grip_change < 255,
                  "wheelspin_m0": 0.1 <= self.wheelspin_m0 <= 1.0, "wheelspin_fade_kmh": 1 <= self.wheelspin_fade_kmh < 400,
                  "wheelspin_gears": 0 <= self.wheelspin_gears <= 7, "lock_brake_pct": 1 <= self.lock_brake_pct <= 100,
                  "lock_frames": 1 <= self.lock_frames <= 255, "lock_kmh": 0 <= self.lock_kmh < 400,
                  "release_brake_pct": 0 <= self.release_brake_pct < self.lock_brake_pct, "release_kmh": 0 <= self.release_kmh < 400,
                  "brake_clamp": -1820.0 <= self.brake_clamp < 0.0, "squeal_from": 0 < self.squeal_from < 0x7FFF,
                  "opponents": 0.5 <= self.opponents <= 1.0}
        bad = [k for k, ok in checks.items() if not ok]
        if bad:
            raise ValueError(f"HandlingTune: out of range: {', '.join(f'{k}={getattr(self, k)!r}' for k in bad)}")

    @property
    def lock_brake(self) -> int:
        """The brake pedal value (0..255) that locks: 80 % is 204."""
        return round(255 * self.lock_brake_pct / 100)

    @property
    def release_brake(self) -> int:
        """The brake pedal value below which a lock releases: 40 % is 102."""
        return round(255 * self.release_brake_pct / 100)


TICK_S = 0.0179                         # the sound program's tick (its main loop runs once a YM3438 timer tick: 17.9 ms nominal,
                                        # 17.957 ms measured in MAME 0.289); the delays' ticks are counted at 17.9 as the prototype


@dataclass(frozen=True)
class SoundTune:
    """The storm's sound (spec 5.6; weather/sound.py). The rain's level is the owner's settled one; the thunder's level and the
    ducking are out/p75storm's, which lowered the joined set's after Pascal's "everything is good but level of the thunder is too
    high", and are settled: on the joined build (20 Nov 2026) "thunder level is good".

    rain_db: the rain bed's level under its voice's full level (Pascal: "now the rain is a bit too loud, id say in between before and
    now": -7.1, level byte 0x26). The program's fade-in steps the level byte by 8 from 0x7e, so it lands exactly only on the bytes
    0x06 + 8 k up to 0x76 (-1.1, -2.6, -4.1, -5.6, -7.1, -8.6 ... -22.1 dB): the value is snapped to that grid (the prototype's
    `--rain`); quieter is refused (the prototype clamped it to 0x76).
    thunder_db: every thunder voice this far under round 4's level (0 or a negative multiple of 1.5 dB, at most -6: the distant
    swell's fade-in lands on it exactly). out/p75storm: -1.5.
    duck_db: how far every other sample voice (engine, music, effects, rain) is pulled down under a close, medium and distant thunder
    (multiples of 0.375 dB, the chip's level step). out/p75storm: 4.125 / 3.0 / 2.25 (its `--duck 4` with the shares 1 / 0.75 / 0.6).
    delays_s: the thunder's wait after the strike, close / medium / distant: whole ticks of the program (0.30 / 0.61 / 0.90 s).
    bands: the strike distances (view units) the bands are cut at: close under 467, medium under 633, distant beyond. Stage 4's
    lightning computes the band (its cell `strike_band`); the join holds it to these."""
    rain_db: float = -7.1
    thunder_db: float = -1.5
    duck_db: tuple = (4.125, 3.0, 2.25)
    delays_s: tuple = (0.3, 0.6, 0.9)
    bands: tuple = (467, 633)

    def __post_init__(self):
        if not -22.85 <= self.rain_db <= -1.1:                     # 0x76 (-22.1 dB) and half a step: snapped to 0x76 at most
            raise ValueError(f"rain_db {self.rain_db}: -22.1 .. -1.1 (level bytes 0x06 .. 0x76)")
        k = -self.thunder_db / 1.5
        if not (0 <= k <= 4 and abs(k - round(k)) < 1e-9):
            raise ValueError(f"thunder_db {self.thunder_db}: 0, -1.5, -3, -4.5 or -6")
        if len(self.duck_db) != 3 or any(not (0 <= d <= 0x7F * 0.375 and abs(d / 0.375 - round(d / 0.375)) < 1e-9)
                                         for d in self.duck_db):
            raise ValueError(f"duck_db {self.duck_db}: three multiples of 0.375 dB, 0 .. 47.6")
        if len(self.delays_s) != 3 or any(not 5 <= round(s / TICK_S) <= 0xFF for s in self.delays_s):
            raise ValueError(f"delays_s {self.delays_s}: three waits of 5 .. 255 ticks (0.09 .. 4.56 s)")
        if len(self.bands) != 2 or not 0 < self.bands[0] < self.bands[1]:
            raise ValueError(f"bands {self.bands}: two increasing distances")

    @property
    def rain_level(self) -> int:
        """The rain's MultiPCM level byte (total level = byte / 2, 0.375 dB a step), snapped to 0x06 + 8 k."""
        tl = -self.rain_db / 0.375
        return min(0x06 + 8 * max(0, round((2 * tl - 0x06) / 8)), 0x76)

    @property
    def thunder_steps(self) -> int:
        """Added to every thunder voice's level byte (8 = 1.5 dB)."""
        return 8 * round(-self.thunder_db / 1.5)

    @property
    def duck_steps(self) -> tuple:
        """The duck's depth per band in level steps (0.375 dB)."""
        return tuple(round(d / 0.375) for d in self.duck_db)

    @property
    def delay_ticks(self) -> tuple:
        return tuple(round(s / TICK_S) for s in self.delays_s)


@dataclass(frozen=True)
class Tunes:
    """The one rule for tunes (weather Task 6J, the join): one field per module that has a tune, named as the module (carrier.Module.name;
    `screen` for stage 1's screen), each its own dataclass with the design's defaults. weather.install_weather hands `screen` to the
    screen, the whole to carrier.install, `sound` to the sound board; each factory of carrier.REGISTRY hands its module its own field
    and no other. A field holding another class is refused (TypeError naming it)."""
    screen: ScreenTune = field(default_factory=ScreenTune)
    cover: CoverTune = field(default_factory=CoverTune)
    lightning: LightningTune = field(default_factory=LightningTune)
    rain: RainTune = field(default_factory=RainTune)
    handling: HandlingTune = field(default_factory=HandlingTune)
    sound: SoundTune = field(default_factory=SoundTune)

    def __post_init__(self):
        kinds = {"screen": ScreenTune, "cover": CoverTune, "lightning": LightningTune, "rain": RainTune, "handling": HandlingTune,
                 "sound": SoundTune}
        for f in fields(self):
            v = getattr(self, f.name)
            if not isinstance(v, kinds[f.name]):
                raise TypeError(f"Tunes.{f.name}: a {kinds[f.name].__name__}, not {type(v).__name__}")
        # the bounds between two modules' tunes the code relies on (the final review's W6): the cover walks roof_clusters of the
        # rain's clusters under the pits roof (its cluster index runs over the rain's cells: more than the rain has would run into
        # the next module's cells)
        if self.cover.roof_clusters > self.rain.clusters:
            raise ValueError(f"cover.roof_clusters {self.cover.roof_clusters} is more than rain.clusters {self.rain.clusters}")

    def of(self, name: str):
        """The tune of the module `name` (KeyError naming it when no module of that name has one)."""
        if name not in {f.name for f in fields(self)}:
            raise KeyError(f"no tune for a module named {name!r}")
        return getattr(self, name)
