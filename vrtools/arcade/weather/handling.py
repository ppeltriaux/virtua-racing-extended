"""Weather stage 5: the wet handling, as the owner approved it after driving the prototype (spec 5.7; Pascal: "hangling is good now!").
A module of the storm's carrier (weather/carrier.py: its RAM contract) with eight hook sites in the game's own physics code.

Pascal's brief (17 Nov 2026): "when pressing full gas on lower gear 1/2/3 it wheels might sleep, braking hard might also trigger a slide
and cornering should feel slightly wider but just for a bit i dont want the game to feel strange, i prefer the risk is cornering for too
long and loosing control". Ported (rewritten from the listings, the values the approved ones) from spike 54 as phases 55, 58 and 59
left it (branch `spike54-handling-v2` at 258a86e, `spike/p54_handling.py`) and as spike 70 joined it (`spike/p70_storm.py`: the stubs
on the storm's switch, the state cleared outside the race); the recon of the game's code: docs/spike/2026-11-phase50-handling-recon.md
(branch `phase50-handling-recon`). The values are tune.HandlingTune's (the design's table); the prototype's other constants are named
below.

THE SITES (boot ROM, main's listing; each a "boot site" block of weather/layout.py's table, its original bytes checked by the carrier)
  slide  0xfed8be `cmp.h #222, 154[R25]` -> jmp; back to 0xfed8c6 `bgt`. The slide routine (0xfed8b0, from the race handler, the glide
         and the pit sequence) writes R0 before reading it on every path from 0xfed8c6, 0xfed8e3 and 0xfed97e; R1 only on its decay path.
  brake  0xfed178 `cmpf.s #-1820.0, R11` -> jmp; back to 0xfed180. R11 the net force (the routine's output here), R10 the brake force
         (read); R0 is written before read on every path from 0xfed180, 0xfed18a and 0xfed190 (0xfed1ae, 0xfed219; 0xfed303 sets it).
  wspin  0xfed190 `cmpf.s #1040.0, R11` -> jmp; back to 0xfed198. The slip path writes R12 (the traction, stored at 0xfed1ec) and R0;
         R0 is written before read from 0xfed198, 0xfed1ec and 0xfed1f3; R13 and R14 are the game's (kept).
  steer  0xfeb2df `sub.h R0, 6A[R25]; mov.h 6A[R25], R0` -> jmp; back to 0xfeb2e7 `sub.h EB[R25], R0` (sets the flags). From 0xfeb339
         the steering routine and its caller's next routine write R0 before reading it.
  engine 0xffa390 `mov.w 15A[R19], R0; cmp.w #7D0, R0` -> jmp; back to 0xffa39c `bge` (the routine's own compare). R0 is the engine
         sound's level (the output), R19 the player.
  grip   0xfeb43d `mov.w 5011A8[PC], R20` (PC-relative; the stub's dry path reads the same address in the absolute form) -> jmp;
         back to 0xfeb444 `add.w R14, R20` (sets the flags). R20 the output.
  squeal 0xffa46e `sub.w #16C, R0` -> jmp; back to 0xffa475 `test.w R0` (sets the flags). R0 in and out, R19 the player.
  opp    0xfec7a7 `mov.w R0, 48[R25]; mov.w 19C[R25], R19` -> jmp; back to 0xfec7b0 `cmp.w 501320[PC], R19` (sets the flags).
         R0 the car's working performance (in, and out scaled), R25 the car (an opponent, the attract's demo car, or the player in
         the steering fade-in).

THE STUBS (boot ROM, the block "handling stubs" of the layout table): per site `cmp.b #1, WEATHER_BYTE; bne dry; cmp.b #0, SWITCH;
be dry; jmp <the wet routine>; dry: <the site's original instructions>; jmp <the site's end>` (every site a `jmp` then nops never run:
the prototype called three of its stubs with `jsr`; a jump back costs a DRY pass less, 15 calls a pass at the opponents'). In a DRY game the
weather byte is 0: the first test, its branch, the original instructions and the jump back; the stubs change only the flags, which the
original instructions set again (or, for the grip and the opponents', the instruction after the site sets them). The weather byte 1 and
SWITCH 1 mean the storm's image is in RAM (carrier contract).

THE WET ROUTINES (the storm image): each tests the race mode (0x501138 = 0x14) first and otherwise jumps to its stub's dry label, so
the countdown, the goal and results, and the states where SWITCH stays 1 outside a rain mode (mode 0x1d; the test menu entered from a
RAIN race, whose loop runs none of the hooked code) take the game's own instructions. A routine saves every register it writes that is
neither its site's output nor dead at its exits (pushed after the mode test, popped at every exit), and leaves at each exit the flags
the code there needs. The gate of every player rule (`emit_gate`): the player's race handler 0xfe8e18 (not the start, pit or post-goal
handlers), no put-back glide ([0x501160] <= 0), pit state +0x191 = 0, and not under cover: bit 7 of the player's segment flag +0x152,
the game's own tunnel flag (the tunnel sound's test at 0xffa67b), as Pascal chose for tunnels ("A": dry inside, wet again outside).
  slide:  in the race on the race handler, not gliding: the spin cool-down counts down (under cover too); then, under the gate, the
          slide S (+0x14e) builds by L/20 (the game's own `div.h #14`) while |L| (+0x154) > slide_threshold, only with the gas (+0x109)
          above slide_gas and no spin-out running and the brake not locked (else S drains x 7/8, the game's own 0xfed97e); after a
          growth, |S| >= spin_slide above spin_kmh km/h with the cool-down 0, no crash and no spin-out already asked: the game's flat
          spin-out (flag bit 15 for S > 0, 16 for S < 0, as 0xfebf2d / 0xfebf39), S := 0 (the path keeps the turn it had), the
          cool-down spin_cooldown, the game's sound 0xb012. Out of the gate: the site's own threshold, 546.
  brake:  in the race the slip mark is cleared (the wheelspin routine, after this one, sets it again); out of the gate or while a
          spin-out or a crash runs a lock ends (and its count) and the game's own clamp applies; locks after lock_frames logic frames
          with the brake (+0x105) >= lock_brake at >= lock_kmh km/h (the lock timer +0x64 re-armed: the game's sound 0xb01d and its
          smoke again); released when the brake < release_brake or at <= release_kmh km/h; locked: the force of a lift (the net force
          with the brake term R10 put back: drag, engine braking), never driving (Pascal, of the lock: "A", releasing the brake gives
          grip back at once); unlocked with the brake down: the clamp brake_clamp; the pedal up: the game's own.
  wspin:  under the gate, in gears 1..wheelspin_gears (+0x156), the gas above FULL_GAS, below wheelspin_fade_kmh km/h, the drive force
          above WS_FORCE: the traction is the game's own rule (1 - (F - 1040) / 1040, at least 0.5; 1 at or below 1040) x m, m =
          wheelspin_m0 + (1 - wheelspin_m0) km/h / wheelspin_fade_kmh, at least WS_FLOOR; stored with the game's smoke timer (0xfed1ec);
          the slip mark set; the engine note +REV_UP a logic frame up to REV_MAX. Without slip the note falls by REV_DN; out of the gate
          it is 0.
  steer:  while locked (in the race, on the race handler): the yaw turn and the straight-line assist skipped (+0x177 := 0), to 0xfeb339:
          the car keeps its heading.
  engine: under the gate the engine sound's level reads rpm + the engine note (the physics rpm untouched).
  grip:   under the gate the grip base [0x5011a8] + grip_change.
  squeal: under the gate |L| - squeal_from (dry 364), at least SLIP_SQUEAL while the wheels slip.
  opp:    in the race, every car but the player ([0x501320]): the working performance x opponents (also under cover: Pascal's "A"
          was the player's grip; the design keeps the opponents' factor on).
`frame` (the carrier's SHOW passes, after the rain's): the time guard tested, then outside the race mode the state cleared (the lock,
the cool-down, the slip mark, the lock count, the engine note), as the joined prototype did at every scenery call outside 0x14. No
`start` (the carrier zeroes the cells at every load) and no `release` (nothing outside the module's RAM is changed: the game's own
fields written in a race are the game's, reset at the next race's start).

Differences from the prototype (each in the stage's findings): the one gate for every player rule (the prototype gated the grip, the
squeal and the engine note by the race and the cover only: the squeal and the engine note run from the race HUD every pass, also in a
glide or a pit stop, where a stale slip mark or engine note could sound); the brake clamp the design's -1583.0 (the prototype's
-1820 / 1.15 = -1582.61); the values immediates of the build (the prototype read a table in ROM); WS_DUR (0, off, in the approved set),
its counter, DRY_COVER and RAIN_ON gone (always on; DRY is the weather byte); the lock's x 1.0 of the lift force not multiplied."""
from __future__ import annotations

from dataclasses import dataclass

from vrtools.arcade.romset import RomSet
from vrtools.arcade.v60asm import Block, asm
from vrtools.arcade.weather import WEATHER_BYTE, carrier
from vrtools.arcade.weather.carrier import MODE, SWITCH, emit_guard_time
from vrtools.arcade.weather.tune import HandlingTune

# ---- the game's cells, routines and the player's fields --------------------------------------------------------------------------
RACE = 0x14                             # the race mode (0x501138)
PLAYER_PTR = 0x501320                   # the player's entity pointer
PLAYER_HANDLER = 0xFE8E18               # the player's race handler (+0xa)
GLIDE = 0x501160                        # the put-back glide's timer (> 0 while gliding)
GRIP_BASE = 0x5011A8                    # the grip base (392 in a single-cabinet race)
SOUND = 0xFFA24B                        # the game's sound request (R0 the command; keeps every other register)
SPIN_SOUND = 0xB012                     # the spin-out's sound (as the grass spin-out's trigger plays it)
HANDLER, FLAGS, KMH, CRASH, LOCK_TIMER, SPINOUT = 0xA, 0x0, 0x14, 0x56, 0x64, 0x6C
BRAKE, GAS, SLIDE, SEGFLAG, LAT, GEAR, ASSIST, PIT = 0x105, 0x109, 0x14E, 0x152, 0x154, 0x156, 0x177, 0x191
SPIN_ASKED = 0x18000                    # flag bits 15 / 16: a spin-out asked (S > 0 / S < 0)
# the game's code the wet routines continue in
SLIDE_GROWN = 0xFED8E3                  # +0x14c = S/4, flag bit 11, the drive board, rsr
SLIDE_DECAY = 0xFED97E                  # S x 7/8, +0x14c = S
BRAKE_LOCK = 0xFED18A                   # bsr 0xfed303 (the lock timer, sound 0xb01d, smoke), br 0xfed1f3
BRAKE_FREE = 0xFED190                   # the wheelspin test (a site: its stub)
WSPIN_SLIP = 0xFED1EC                   # the traction R12 stored, the smoke timer
WSPIN_GRIP = 0xFED1F3                   # the force applied with the traction +0x5c (1.0, written at 0xfed16f)
STEER_ON = 0xFEB339                     # the grip update
ENGINE_ON = 0xFFA39C                    # the engine level's clamp (its `bge` on the site's compare)
# ---- the prototype's constants that are not the design's table (spike 54/59, unchanged) ----------------------------------------
SLIDE_DIV_BYTES = bytes.fromhex("a320f41400")   # `div.h #14, R0`: the game's own L/20 (0xfed8d9)
SLIDE_READ_BYTES = bytes.fromhex("1b20395401")  # `mov.h 154[R25], R0` (0xfed8d4)
SLIDE_ADD_BYTES = bytes.fromhex("8200394e01")   # `add.h R0, 14E[R25]` (0xfed8de)
FULL_GAS = 179                          # the wheelspin's "full gas": above 179 of 255 (70 %)
WS_FORCE = 850.0                        # the rain wheelspin from this drive force (the game's own from 1040)
OWN_FORCE, OWN_SLOPE, OWN_FLOOR = 1040.0, 0x3A7C0FB9, 0.5   # the game's own traction rule (1/1040 as the game's float, 0xfed1b9)
WS_FLOOR = 0.1                          # the rain traction never below this
REV_UP, REV_MAX, REV_DN = 1200, 6000, 1500  # the engine note while slipping (rpm added to the sound only)
SLIP_SQUEAL = 180                       # while slipping the squeal at least that of |L| = squeal_from + this (level 4 of 7)
# ---- the module ----------------------------------------------------------------------------------------------------------------
NAMES = ("slide", "brake", "wspin", "steer", "engine", "grip", "squeal", "opp")
CELLS = (("state", 4), ("slip_rev", 4), ("fires", 4), ("locks", 4), ("lock_frames", 4), ("slip_frames", 4), ("steer_skips", 4))
# state's bytes: the lock (1 locked), the spin cool-down, the slip mark (1 the wheels slipped this logic frame), the lock count
LOCK, COOL, SLIP, LOCKC = 0, 1, 2, 3
STUB_AT = 0xFFFEA0                      # the stubs' block (weather/layout.py: "handling stubs")
_PLACEHOLDER = 0x522000                 # a RAM address of the final encoding's length (jmp abs)


@dataclass(frozen=True)
class Site:
    name: str
    addr: int
    original: bytes
    @property
    def back(self) -> int:
        return self.addr + len(self.original)


# Each site jumps to its stub, which jumps back to the site's end (no call: no stack, its nops never run).
SITES = (Site("slide", 0xFED8BE, bytes.fromhex("ba80f42202395401")),
         Site("brake", 0xFED178, bytes.fromhex("5ca0f40080e3c46b")),
         Site("wspin", 0xFED190, bytes.fromhex("5ca0f4000082446b")),
         Site("steer", 0xFEB2DF, bytes.fromhex("aa00196a1b20196a")),
         Site("engine", 0xFFA390, bytes.fromhex("2d20335a01bc20f4d0070000")),
         Site("grip", 0xFEB43D, bytes.fromhex("2d34f26b5d51ff")),
         Site("squeal", 0xFFA46E, bytes.fromhex("ac20f46c010000")),
         Site("opp", 0xFEC7A7, bytes.fromhex("2d0019482d33399c01")))
SITE = {s.name: s for s in SITES}


def dry_bytes(s: Site) -> bytes:
    """The site's original instructions as its stub's dry path runs them: as they are, but the grip's PC-relative read of the grip
    base in the absolute form (the same read, the same length)."""
    return asm("mov.w abs,reg", GRIP_BASE, "r20") if s.name == "grip" else s.original


# ==================================================================================================================== the stubs
def stub_block(entries: dict[str, int], at: int = STUB_AT, trace: int | None = None) -> Block:
    """The eight stubs at `at` (labels: each site's name and name + "_dry"); `entries`: the wet routines' RAM addresses. `trace`
    (a measurement build only, never shipped): a RAM byte written with 0xf0 + the site's index before the dry path's jump back."""
    b = Block(at)
    for k, s in enumerate(SITES):
        b.label(s.name)
        b.emit("cmp.b imm,abs", 1, WEATHER_BYTE)
        b.branch("bne", s.name + "_dry")
        b.emit("cmp.b imm,abs", 0, SWITCH)
        b.branch("be", s.name + "_dry")
        b.emit("jmp abs", entries[s.name])
        b.label(s.name + "_dry")
        b.raw(dry_bytes(s))
        if trace is not None:
            b.emit("mov.b imm,abs", 0xF0 + k, trace)
        b.emit("jmp abs", s.back)
    return b


def stub_labels(at: int = STUB_AT, trace: int | None = None) -> dict[str, int]:
    """Each stub's entry and dry label (they do not depend on the RAM addresses: `jmp abs` has one length)."""
    b = stub_block({n: _PLACEHOLDER for n in NAMES}, at, trace)
    return {k: b.addr(k) for s in SITES for k in (s.name, s.name + "_dry")}


def site_bytes(s: Site, at: int = STUB_AT, trace: int | None = None) -> bytes:
    """The site's new bytes: `jmp` to its stub, then `nop` to the site's length (never run)."""
    call = asm("jmp abs", stub_labels(at, trace)[s.name])
    return call + b"\xcd" * (len(s.original) - len(call))


# ==================================================================================================================== the wet routines
# Planted faults (test builds only, never shipped: tests/test_weather_handling.py's RED evidence for the excluded states): each drops
# one term of the gate or widens the race-mode test. "cover": no tunnel-flag test; "glide": no glide test; "pit": no race-handler
# and no pit-state test; "countdown": the countdown's modes (0x12, 0x13) taken as the race; "goal": the goal's and results' (to 0x1c);
# "player": the opponents' factor not skipping the player's car.
FAULTS = ("cover", "glide", "pit", "countdown", "goal", "player")


def emit_gate(b: Block, car: str, out: str, fault: str | None = None) -> None:
    """To `out` unless the player (`car`) is on its race handler, not gliding, not in a pit stop and not under cover."""
    emit_driving(b, car, out, fault)
    emit_open(b, car, out, fault)


def emit_driving(b: Block, car: str, out: str, fault: str | None = None) -> None:
    """To `out` unless the player (`car`) is on its race handler and not in a put-back glide."""
    if fault != "pit":
        b.emit("cmp.w imm,disp[reg]", PLAYER_HANDLER, HANDLER, car)
        b.branch("bne", out)
    if fault != "glide":
        b.emit("cmp.w imm,abs", 0, GLIDE)                # flags of [GLIDE] - 0
        b.branch("bgt", out)


def emit_open(b: Block, car: str, out: str, fault: str | None = None) -> None:
    """To `out` when the player (`car`) is in a pit stop (+0x191 nonzero) or under cover (the tunnel flag)."""
    if fault != "pit":
        b.emit("cmp.h imm,disp[reg]", 0, PIT, car)
        b.branch("bne", out)
    if fault != "cover":
        b.raw(bytes([0x87, 0x80, 0xE7, 0x20 | int(car[1:]), SEGFLAG & 0xFF, SEGFLAG >> 8]))   # test1 #7, 152[car]: Z clear: covered
        b.branch("bne", out)


class _Traced(Block):
    """A Block whose every `jmp abs` is preceded, in a measurement build (`trace` a RAM byte), by `mov.b #exit, trace`; `exits`:
    exit number -> (routine, target). Without `trace` it emits exactly what Block does."""

    def __init__(self, at: int, trace: int | None = None):
        super().__init__(at)
        self.trace, self.exits, self.routine = trace, {}, None

    def emit(self, form: str, *args) -> None:
        if self.trace is not None and form == "jmp abs":
            eid = len(self.exits) + 1
            self.exits[eid] = (self.routine, args[0])
            super().emit("mov.b imm,abs", eid, self.trace)
        super().emit(form, *args)


def _mode(b: Block, name: str, dry: int, fault: str | None = None) -> None:
    """The routine's first test: the race mode, else the stub's dry path."""
    b.label(name)
    if isinstance(b, _Traced):
        b.routine = name
    if fault in ("countdown", "goal"):
        lo, hi = (0x12, RACE) if fault == "countdown" else (RACE, 0x1C)
        b.emit("cmp.b imm,abs", lo, MODE)
        b.branch("blt", name + "_out")                   # flags of MODE - lo (the modes are small positive bytes)
        b.emit("cmp.b imm,abs", hi, MODE)
        b.branch("ble", name + "_race")
        b.label(name + "_out")
        b.emit("jmp abs", dry)
        b.label(name + "_race")
        return
    b.emit("cmp.b imm,abs", RACE, MODE)
    b.branch("be", name + "_race")
    b.emit("jmp abs", dry)
    b.label(name + "_race")


def _signed_h(b: Block, disp: int, reg: str) -> None:
    """reg := the signed halfword at disp[R25]."""
    b.emit("movz.hw disp[reg],reg", disp, "r25", reg)
    b.emit("shl.w imm,reg", 16, reg)
    b.emit("sha.w imm,reg", -16, reg)


def _rev_down(b: Block, note: int, k: str) -> None:
    """The engine note -= REV_DN, not below 0 (R0)."""
    b.emit("mov.w abs,reg", note, "r0")
    b.emit("sub.w imm,reg", REV_DN, "r0")
    b.emit("cmp.w imm,reg", 0, "r0")
    b.branch("bge", k)
    b.emit("mov.w imm,reg", 0, "r0")
    b.label(k)
    b.emit("mov.w reg,abs", "r0", note)


def wet_code(at: int, lay: carrier.Layout, t: HandlingTune, fault: str | None = None, trace: int | None = None,
             stub_at: int = STUB_AT) -> Block:
    """The wet routines (one per site, labelled by its name) and `frame`, at `at` in the image. `fault` (a test build's planted
    fault, FAULTS) and `trace` (a measurement build's RAM byte written with the exit's number before every exit; the numbers in the
    Block's `exits`): never in a shipped build."""
    dry = {n: v for n, v in stub_labels(stub_at, trace).items() if n.endswith("_dry")}
    st = lay.cell("handling", "state")
    lock, cool, slip, lockc = st + LOCK, st + COOL, st + SLIP, st + LOCKC
    note = lay.cell("handling", "slip_rev")
    fires, locks, lock_frames = lay.cell("handling", "fires"), lay.cell("handling", "locks"), lay.cell("handling", "lock_frames")
    slip_frames, steer_skips = lay.cell("handling", "slip_frames"), lay.cell("handling", "steer_skips")
    b = _Traced(at, trace)

    # ---- slide (R0 dead at every exit; R1 saved)
    _mode(b, "slide", dry["slide_dry"], fault)
    b.emit("push reg", "r1")
    emit_driving(b, "r25", "s_dry", fault)
    b.emit("cmp.b imm,abs", 0, cool)                     # the spin cool-down counts down (under cover too)
    b.branch("be", "s_cooled")
    b.emit("movz.bw abs,reg", cool, "r0")
    b.emit("sub.w imm,reg", 1, "r0")
    b.emit("mov.b reg,abs", "r0", cool)
    b.label("s_cooled")
    emit_open(b, "r25", "s_dry", fault)
    b.emit("cmp.b imm,disp[reg]", 0, SPINOUT, "r25")     # a spin-out runs: the slide only drains
    b.branch("bne", "s_decay")
    b.emit("cmp.b imm,abs", 0, lock)                     # the brake locked: no slide
    b.branch("bne", "s_decay")
    b.emit("movz.hw disp[reg],reg", GAS, "r25", "r0")   # at or below slide_gas: the slide drains, no spin
    b.emit("cmp.w imm,reg", t.slide_gas, "r0")
    b.branch("ble", "s_decay")
    _signed_h(b, LAT, "r0")                              # R0 = L, R1 = |L|
    b.emit("mov.w reg,reg", "r0", "r1")
    b.emit("cmp.w imm,reg", 0, "r1")
    b.branch("bge", "s_abs")
    b.emit("mov.w imm,reg", 0, "r1")
    b.emit("sub.w reg,reg", "r0", "r1")
    b.label("s_abs")
    b.emit("cmp.w imm,reg", t.slide_threshold, "r1")
    b.branch("ble", "s_decay")
    b.raw(SLIDE_READ_BYTES)                              # S += L / 20, the game's own three instructions
    b.raw(SLIDE_DIV_BYTES)
    b.raw(SLIDE_ADD_BYTES)
    b.emit("cmp.b imm,abs", 0, cool)                     # held too long on the gas: the flat spin-out
    b.branch("bne", "s_grown")
    b.emit("cmp.b imm,disp[reg]", 0, CRASH, "r25")
    b.branch("bne", "s_grown")
    b.emit("cmp.w imm,disp[reg]", t.spin_kmh, KMH, "r25")
    b.branch("ble", "s_grown")
    b.emit("mov.w disp[reg],reg", FLAGS, "r25", "r0")
    b.emit("and.w imm,reg", SPIN_ASKED, "r0")
    b.branch("bne", "s_grown")
    _signed_h(b, SLIDE, "r0")                            # R0 = S
    b.emit("cmp.w imm,reg", 0, "r0")
    b.branch("bge", "s_pos")
    b.emit("mov.w imm,reg", 0, "r1")
    b.emit("sub.w reg,reg", "r0", "r1")
    b.emit("cmp.w imm,reg", t.spin_slide, "r1")
    b.branch("blt", "s_grown")
    b.emit("mov.w imm,reg", 0x10000, "r1")               # S < 0: bit 16
    b.branch("br", "s_fire")
    b.label("s_pos")
    b.emit("cmp.w imm,reg", t.spin_slide, "r0")
    b.branch("blt", "s_grown")
    b.emit("mov.w imm,reg", 0x8000, "r1")                # S > 0: bit 15
    b.label("s_fire")
    b.emit("or.w reg,disp[reg]", "r1", FLAGS, "r25")
    b.emit("mov.h imm,disp[reg]", 0, SLIDE, "r25")       # the slide washes out: the path keeps the turn it had
    b.emit("mov.b imm,abs", t.spin_cooldown, cool)
    b.emit("add.w imm,abs", 1, fires)
    b.emit("mov.w imm,reg", SPIN_SOUND, "r0")
    b.emit("jsr abs", SOUND)
    b.label("s_grown")
    b.emit("pop reg", "r1")
    b.emit("jmp abs", SLIDE_GROWN)
    b.label("s_decay")
    b.emit("pop reg", "r1")
    b.emit("jmp abs", SLIDE_DECAY)
    b.label("s_dry")
    b.emit("pop reg", "r1")
    b.emit("jmp abs", dry["slide_dry"])

    # ---- brake (R11 the output; R10 read; R0 dead at every exit)
    _mode(b, "brake", dry["brake_dry"], fault)
    b.emit("mov.b imm,abs", 0, slip)                     # the wheelspin routine (after this one) sets it again
    emit_gate(b, "r25", "b_off", fault)
    b.emit("cmp.b imm,disp[reg]", 0, SPINOUT, "r25")
    b.branch("bne", "b_off")
    b.emit("cmp.b imm,disp[reg]", 0, CRASH, "r25")
    b.branch("bne", "b_off")
    b.emit("movz.hw disp[reg],reg", BRAKE, "r25", "r0")  # R0 = the brake pedal
    b.emit("cmp.b imm,abs", 0, lock)
    b.branch("be", "b_unlocked")
    b.emit("cmp.w imm,reg", t.release_brake, "r0")       # locked: eased below release_brake, or slow: grip back at once
    b.branch("blt", "b_release")
    b.emit("cmp.w imm,disp[reg]", t.release_kmh, KMH, "r25")
    b.branch("ble", "b_release")
    b.branch("br", "b_locked")
    b.label("b_unlocked")
    b.emit("cmp.w imm,reg", t.lock_brake, "r0")
    b.branch("blt", "b_reset")
    b.emit("cmp.w imm,disp[reg]", t.lock_kmh, KMH, "r25")
    b.branch("blt", "b_reset")
    b.emit("movz.bw abs,reg", lockc, "r0")
    b.emit("add.w imm,reg", 1, "r0")
    b.emit("mov.b reg,abs", "r0", lockc)
    b.emit("cmp.w imm,reg", t.lock_frames, "r0")
    b.branch("blt", "b_normal")
    b.emit("mov.b imm,abs", 1, lock)                     # the wheels lock now
    b.emit("mov.b imm,disp[reg]", 0, LOCK_TIMER, "r25")  # the lock timer re-armed: 0xb01d and the smoke start again
    b.emit("add.w imm,abs", 1, locks)
    b.branch("br", "b_locked")
    b.label("b_off")
    b.emit("mov.b imm,abs", 0, lock)
    b.emit("mov.b imm,abs", 0, lockc)
    b.branch("br", "b_dry")
    b.label("b_release")
    b.emit("mov.b imm,abs", 0, lock)
    b.label("b_reset")
    b.emit("mov.b imm,abs", 0, lockc)
    b.label("b_normal")
    b.emit("cmp.h imm,disp[reg]", 0, BRAKE, "r25")       # the pedal up: the game's own (its off-road drag at the clamp)
    b.branch("be", "b_dry")
    b.emit("cmpf.s imm,reg", t.brake_clamp, "r11")
    b.branch("bgt", "b_free")
    b.emit("mov.w imm,reg", _bits(t.brake_clamp), "r11")
    b.emit("mov.w imm,abs", 0, note)
    b.emit("jmp abs", BRAKE_LOCK)
    b.label("b_free")
    b.emit("jmp abs", BRAKE_FREE)
    b.label("b_locked")                                  # the brake gone: the force of a lift, never driving
    b.emit("addf.s reg,reg", "r10", "r11")               # R10 = curve(pedal) x 1820, taken off R11 at 0xfed16c
    b.emit("cmpf.s imm,reg", 0.0, "r11")
    b.branch("ble", "b_lifted")
    b.emit("mov.w imm,reg", 0, "r11")
    b.label("b_lifted")
    b.emit("add.w imm,abs", 1, lock_frames)
    b.emit("mov.w imm,abs", 0, note)
    b.emit("jmp abs", BRAKE_LOCK)                        # the lock timer keeps 0xb01d and the smoke going
    b.label("b_dry")
    b.emit("jmp abs", dry["brake_dry"])

    # ---- wspin (R12 the output on the slip path; R13, R14 saved; R0 dead at every exit)
    _mode(b, "wspin", dry["wspin_dry"], fault)
    b.emit("pushm imm", (1 << 13) | (1 << 14))
    emit_gate(b, "r25", "w_zero", fault)
    b.emit("cmp.w imm,disp[reg]", t.wheelspin_gears, GEAR, "r25")   # gear index >= the gears: the game's own rule
    b.branch("bge", "w_own")
    b.emit("movz.hw disp[reg],reg", GAS, "r25", "r0")
    b.emit("cmp.w imm,reg", FULL_GAS, "r0")
    b.branch("ble", "w_own")                             # eased off: the game's own traction at once
    b.emit("cmp.w imm,disp[reg]", t.wheelspin_fade_kmh, KMH, "r25")
    b.branch("bge", "w_own")
    b.emit("cmpf.s imm,reg", WS_FORCE, "r11")
    b.branch("ble", "w_grip")
    b.emit("movf.s imm,reg", 1.0, "r13")                 # R13 = the game's own traction for this force
    b.emit("cmpf.s imm,reg", OWN_FORCE, "r11")
    b.branch("ble", "w_own1")
    b.emit("mov.w reg,reg", "r11", "r13")
    b.emit("subf.s imm,reg", OWN_FORCE, "r13")
    b.emit("mulf.s imm,reg", OWN_SLOPE, "r13")
    b.emit("negf.s reg,reg", "r13", "r13")
    b.emit("addf.s imm,reg", 1.0, "r13")
    b.emit("cmpf.s imm,reg", OWN_FLOOR, "r13")
    b.branch("bge", "w_own1")
    b.emit("movf.s imm,reg", OWN_FLOOR, "r13")
    b.label("w_own1")
    b.emit("mov.w disp[reg],reg", KMH, "r25", "r12")     # m = M0 + (1 - M0) km/h / fade
    b.emit("cvt.ws reg,reg", "r12", "r12")
    b.emit("divf.s imm,reg", float(t.wheelspin_fade_kmh), "r12")
    b.emit("movf.s imm,reg", 1.0, "r14")
    b.emit("subf.s imm,reg", t.wheelspin_m0, "r14")
    b.emit("mulf.s reg,reg", "r14", "r12")
    b.emit("addf.s imm,reg", t.wheelspin_m0, "r12")
    b.emit("mulf.s reg,reg", "r13", "r12")               # the traction: the game's own x m
    b.emit("cmpf.s imm,reg", WS_FLOOR, "r12")
    b.branch("bge", "w_floor")
    b.emit("mov.w imm,reg", _bits(WS_FLOOR), "r12")
    b.label("w_floor")
    b.emit("mov.b imm,abs", 1, slip)
    b.emit("add.w imm,abs", 1, slip_frames)
    b.emit("mov.w abs,reg", note, "r0")                  # the engine note climbs
    b.emit("add.w imm,reg", REV_UP, "r0")
    b.emit("cmp.w imm,reg", REV_MAX, "r0")
    b.branch("ble", "w_note")
    b.emit("mov.w imm,reg", REV_MAX, "r0")
    b.label("w_note")
    b.emit("mov.w reg,abs", "r0", note)
    b.emit("popm imm", (1 << 13) | (1 << 14))
    b.emit("jmp abs", WSPIN_SLIP)
    b.label("w_grip")
    _rev_down(b, note, "w_g0")
    b.emit("popm imm", (1 << 13) | (1 << 14))
    b.emit("jmp abs", WSPIN_GRIP)
    b.label("w_own")
    _rev_down(b, note, "w_o0")
    b.emit("popm imm", (1 << 13) | (1 << 14))
    b.emit("jmp abs", dry["wspin_dry"])
    b.label("w_zero")
    b.emit("mov.w imm,abs", 0, note)
    b.emit("popm imm", (1 << 13) | (1 << 14))
    b.emit("jmp abs", dry["wspin_dry"])

    # ---- steer (no register)
    _mode(b, "steer", dry["steer_dry"], fault)
    b.emit("cmp.b imm,abs", 0, lock)
    b.branch("be", "t_dry")
    b.emit("cmp.w imm,disp[reg]", PLAYER_HANDLER, HANDLER, "r25")
    b.branch("bne", "t_dry")
    b.emit("mov.w imm,disp[reg]", 0, ASSIST, "r25")      # the assist's counter starts again after the lock
    b.emit("add.w imm,abs", 1, steer_skips)
    b.emit("jmp abs", STEER_ON)
    b.label("t_dry")
    b.emit("jmp abs", dry["steer_dry"])

    # ---- engine (R0 the output; R19 the player)
    eng = SITE["engine"].original
    _mode(b, "engine", dry["engine_dry"], fault)
    b.raw(eng[:5])                                       # mov.w 15A[R19], R0
    emit_gate(b, "r19", "e_out", fault)
    b.emit("add.w abs,reg", note, "r0")
    b.label("e_out")
    b.raw(eng[5:])                                       # cmp.w #7D0, R0: its flags for 0xffa39c's bge
    b.emit("jmp abs", ENGINE_ON)

    # ---- grip (R20 the output)
    _mode(b, "grip", dry["grip_dry"], fault)
    b.emit("mov.w abs,reg", GRIP_BASE, "r20")
    emit_gate(b, "r25", "g_out", fault)
    b.emit("add.w imm,reg", t.grip_change, "r20")
    b.label("g_out")
    b.emit("jmp abs", SITE["grip"].back)

    # ---- squeal (R0 in and out; R19 the player)
    _mode(b, "squeal", dry["squeal_dry"], fault)
    emit_gate(b, "r19", "q_dry", fault)
    b.emit("sub.w imm,reg", t.squeal_from, "r0")
    b.emit("cmp.b imm,abs", 0, slip)
    b.branch("be", "q_out")
    b.emit("cmp.w imm,reg", SLIP_SQUEAL, "r0")
    b.branch("bge", "q_out")
    b.emit("mov.w imm,reg", SLIP_SQUEAL, "r0")
    b.label("q_out")
    b.emit("jmp abs", SITE["squeal"].back)
    b.label("q_dry")
    b.emit("jmp abs", dry["squeal_dry"])

    # ---- opp (R0 in and out, scaled; R25 the car)
    _mode(b, "opp", dry["opp_dry"], fault)
    if fault != "player":
        b.emit("cmp.w abs,reg", PLAYER_PTR, "r25")       # not the player (the steering fade-in runs this code for it)
        b.branch("be", "o_dry")
    b.emit("mulf.s imm,reg", t.opponents, "r0")
    b.raw(SITE["opp"].original)                          # the site's own two instructions store it (and load R19)
    b.emit("jmp abs", SITE["opp"].back)
    b.label("o_dry")
    b.emit("jmp abs", dry["opp_dry"])

    # ---- frame: outside the race the state cleared
    b.label("frame")
    emit_guard_time(b, "f_out")
    b.emit("cmp.b imm,abs", RACE, MODE)
    b.branch("be", "f_out")
    b.emit("mov.w imm,abs", 0, st)
    b.emit("mov.w imm,abs", 0, note)
    b.label("f_out")
    b.emit("rsr")
    return b


def _bits(x: float) -> int:
    from vrtools.arcade.v60asm import float_bits
    return float_bits(x)


def module(rs: RomSet | None = None, tune: HandlingTune | None = None, fault: str | None = None, trace: bool = False,
           stub_at: int = STUB_AT) -> carrier.Module:
    """The handling as a carrier module (`rs` unused: the sites' bytes are checked by the carrier). Test builds only: `fault` one
    of FAULTS (a planted fault), `trace` (every exit and every dry path writes its number to the cell "trace": a measurement build
    whose stubs need a larger block, at `stub_at`)."""
    t = tune or HandlingTune()
    if fault is not None and fault not in FAULTS:
        raise ValueError(f"fault {fault!r}: one of {FAULTS}")
    cells = CELLS + ((("trace", 4),) if trace else ())

    def tr(lay: carrier.Layout) -> int | None:
        return lay.cell("handling", "trace") if trace else None

    def code(lay: carrier.Layout) -> Block:
        return wet_code(lay.code("handling"), lay, t, fault, tr(lay), stub_at)

    def rom(lay: carrier.Layout):
        b = stub_block({n: lay.label("handling", n) for n in NAMES}, stub_at, tr(lay))
        assert {k: b.addr(k) for k in stub_labels(stub_at, tr(lay))} == stub_labels(stub_at, tr(lay))
        return (("handling stubs", b.bytes()),)

    def sites(lay: carrier.Layout):
        return tuple((f"handling site {s.name}", s.original, site_bytes(s, stub_at, tr(lay))) for s in SITES)
    return carrier.Module(name="handling", code=code, cells=cells, rom=rom, sites=sites, frame="frame", entries=NAMES)
