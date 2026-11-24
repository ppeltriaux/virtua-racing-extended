"""The weather feature (docs/superpowers/specs/2026-11-18-weather-storm-design.md): a COURSE WEATHER screen after COURSE DIRECTION,
DRY or RAIN, and for RAIN a storm. Stage 1 (this package's `screen`) installs the screen, the direction screen's grey-out and
hold, the weather byte, the HUD word and the no-record gate; a RAIN race is otherwise a dry race until the storm's stages add to
it; stage 2 (`carrier`, `rain`) makes RAIN rain: the storm's carrier (its RAM contract in carrier.py's docstring) with the
rain, splashes, overcast grade and grey sky; stage 6 (`sound`, `thunder_gen`) the rain bed and the thunder on the sound board, with
the V60's triggers on the carrier. Every block the feature writes is named in `layout`; its tune values are in `tune`.

The names later stages rely on:
- WEATHER_BYTE: 0 DRY, 1 RAIN from the weather lock to the next clear (every select screen's start, the attract's and linked
  play's course loads), so the attract, linked play and the operator's fixed course are always dry.
- RAIN_MODES: the game's mode bytes (0x501138) in which a RAIN race's storm is on: the countdown and race (0x12-0x14), the results
  (0x15, 0x16), the goal (0x19, 0x1a) and the race-end ranking page's first two (0x1b, 0x1c), as the joined prototype (spike 70)
  had them: it rains through GOAL and RESULT."""
from __future__ import annotations

from vrtools.arcade.romset import RomSet

WEATHER_BYTE = 0x502296                 # the direction word's third byte (dirscreen.DIR_ARMED), free after the direction lock
DRY, RAIN = 0, 1
RAIN_MODES = (0x12, 0x13, 0x14, 0x15, 0x16, 0x19, 0x1A, 0x1B, 0x1C)


def install_weather(rs: RomSet, converted: list | None = None, *, weather: bool = True, tunes=None) -> RomSet:
    """The weather feature on a built ten-course set (the directory, the COURSE DIRECTION screen and the originals' pictures in it:
    `tencourse.ten_course_set` calls this last of all), as a new set; `rs` itself, untouched, when `weather` is False. `tunes`: a
    `tune.Tunes` (the defaults when None; the one rule for tunes: each part gets its own field). Stage 1's screen (`tunes.screen`),
    then stage 2's storm carrier with the registry's modules (cover, lightning, rain, handling, sound's triggers: each its own field
    of `tunes`), then stage 6's sound board (`tunes.sound`). `converted` (the converted courses) is for the storm's modules."""
    if not weather:
        return rs
    from dataclasses import replace
    from vrtools.arcade.weather import carrier, screen, sound
    from vrtools.arcade.weather.tune import Tunes
    tunes = Tunes() if tunes is None else tunes
    if not isinstance(tunes, Tunes):
        raise TypeError(f"install_weather takes a tune.Tunes, not {type(tunes).__name__}")
    out = replace(rs)
    screen.install(out, tunes.screen)               # checks every block of the layout erased first
    out = carrier.install(out, converted, tunes)
    return sound.install_board(out, tunes.sound)
