"""Weather stage 2: the storm's carrier. It brings the storm's code and data into spare RAM when a RAIN race starts, runs the storm's
modules once a logic frame after the game's scenery, gives them a switch and two guards, and puts everything back when the storm
ends. Design: docs/superpowers/specs/2026-11-18-weather-storm-design.md (approach 1, sections 5.2 and 6); the stage's plan
docs/superpowers/plans/2026-11-18-weather-stage-2-rain.md. Ported from spike 70's stub (branch `spike70-storm`, `spike/p70_storm.py`).
It never touches the interrupts: no SBR change, no write to the board's interval timer (below, "What was tried and removed").

THE RAM CONTRACT (what a later stage needs; addresses are this module's constants)
=====================================================================================

Memory. RAM 0x520000..0x53efff is the storm's (the boot clears 0x500000..0x53efff at 0xfe1469; nothing else touches this range in a
race, the results, the name entry, the attract or a second game: spike 70's ramcheck). It is laid out once:
  CARRIER_CELLS  0x520000..0x5200ff  the carrier's own cells (below)
  MODULE_CELLS   0x520100..0x521fff  each module's cells, in registry order; ZEROED AT EVERY LOAD (a new storm starts clean)
  IMAGE          0x522000..0x529fff  code: the carrier's routines, then each module's code and static tables
  DATA           0x52a000..0x53efff  data: static tables, then each module's per-course data and copies from the course's bank
Bank 3 (from 0x1df4c0) stores the image, the static data and every course's data; the stub copies them at the load.

The switch. SWITCH (byte 0x520000) is 1 in a logic frame whose scenery call found the storm on: the weather byte
(weather.WEATHER_BYTE) 1, not linked play (0x40dc8c 0), the menu entry (0x501940) under 10 and the mode (0x501138) one of
weather.RAIN_MODES. The stub writes it at every scenery call while the weather byte is 1 or something of the storm is live, before
the game's scenery routine runs; it is 0 in every DRY game. It is STALE (left 1, only the next scenery call clears it): after the
last scenery call of a RAIN race, through the results' last mode 0x1d, the attract's opening frames before its scenery call, and in
the test menu entered from a RAIN race (until the reboot clears the RAM), with the weather byte still 1 and the image in RAM; and
between the weather byte's clear (a select screen's start, the attract's or linked play's load) and the next scenery call. So code
outside the scenery call (a hook site's stub of a later stage, below) tests the WEATHER BYTE first (`cmp.b #1, 502296; bne dry`:
one test in a DRY game), then SWITCH; SWITCH 1 with the weather byte 1 means the image is in RAM (the load runs inside the scenery
call that set it), so calling into it is safe, but it does NOT mean a rain mode: in those stale stretches a hook running outside
the scenery call takes its wet path. A hook that must act only in a rain mode tests the mode byte (0x501138) too.

STATE (byte 0x520001): IDLE 0 (nothing of the storm live), STARTING 1 (copied; the modules'
`start` routines run), SHOW 2 (the modules' `frame` routines run). LOADKEY (word 0x520004) = KEYMAGIC | menu entry while loaded.

A logic frame, as the stub (boot ROM, in place of the hook site 0xfee144's `jsr FF8450`, the scenery routine, the race scene's last
emitter) runs it:
  - DRY (the weather byte 0 and STATE IDLE): `cmp.b #1, WEATHER; be wet; cmp.b #0, STATE; bne wet; jmp FF8450`. Nothing else.
  - Otherwise: the decision; if the storm is off, or on for another menu entry than LOADKEY's, and STATE is not IDLE: the RELEASE
    (each module's `release` in reverse registry order, then STATE IDLE, LOADKEY 0, SWITCH 0);
    SWITCH := the decision; the game's scenery routine; then, when SWITCH is 1:
      STATE IDLE -> the LOAD (this pass is F0, it draws nothing): the module cells zeroed, the common copy list (image, static data)
        and this entry's (per-course data, copies from the course's bank) run with bank switches (0xe00004), the course's bank put
        back, LOADKEY set, STATE STARTING;
      STATE STARTING -> every module's `start` in registry order (each does a FIXED QUOTA of its start-up work a pass and returns
        R0 = 1 while some is left); when all return R0 = 0, STATE SHOW (from the next pass);
      STATE SHOW -> every module's `frame` in registry order.
  So a RAIN race runs: F0 the load; F1.. the starts (as many passes as they need); then the frames. The modules' routines are entered
  by `jsr` with nothing in the registers; they may change R0-R20 and R26-R28 (the carrier saves them) and keep R21-R25 and R29-R31.
  Nothing of the storm runs on the select screens (the scenery routine runs only in the race scene).

Time. The only time the storm reads is the game's own vblank count, the byte 0x500501: the game writes 0 there at its wait's
exit (0xfe1406, where the pass begins) and its vblank interrupt counts it up 17.38 ms later (MAME 0.289's screen: 278 144 cycles of
the 16 MHz V60 a frame). So within a pass it says only "not yet 17.38 ms" (0) or "already late" (nonzero): never how much time is
left. MAME shows a stale picture when a pass runs past its screen update, 18.9 ms in (DEADLINE_MS); the storm's cap is
RAIN_BUSY_MAX_MS, 17.9 ms, the bound of this guard: the game's vblank handler moves the count 17.383-17.387 ms into the pass, and
17.486 ms on some passes (its work before the increment varies: 1 pass of 49 in three heavy 60-s runs); then the unit in flight
(from the move to the next guard test, the trip: at most UNIT_MAX_US, 0.2 ms); then the tail (from the trip to the pass's end: at
most TAIL_US, 160 us); so 17.486 + 0.200 + 0.160 = 17.846 ms, rounded up to 17.9 (the session lead's ruling keeps 17.9 in the
join's round 2). (Stage 2, the rain alone: a 31 us tail, 17.72 -> 17.8; the join, round 1: with five modules the tail after a trip
in the rain's splash loop was the rain's late path visiting every remaining splash slot, up to 40, about 145 us: 182 us measured,
TAIL_US 190, 17.876; round 2 (J2): the late splash path clears the remaining slots in one string fill and keeps the late trims by
the live count, the same picture (findings, the join's round 2), and (J1) the sound's trigger works on a late pass too: tails
measured on the round-2 build 58 us at most naturally, 72 us forced at the splash loop's head with 40 live slots and the trigger
sending a thunder and a rain word, 149 us forced in the first module, every module's late path and the trigger sending both words:
TAIL_US 160. The worst pass measured stays what the findings' "Join" section gives.) THE PREMISE of that derivation (the final
review, lens 1): the count moves while GUARDED storm code is running, so the next guard test trips within a unit. Nothing enforces
it: if the game's own part of a pass (which includes the wet handling's routines, below) is still running at the move, the pass ends
at that part's end plus about 5 us (the stub's return, the body) plus the tail. Measured margin: the game's own part is 10.4-14.1 ms
on the busiest logged RAIN passes and 15.52 ms at most in a DRY race on main, against the move at 17.38 ms. On such a pass
tests/test_weather_rain.py's `post_move_over` reports a storm "unit in flight" over UNIT_MAX_US (from the move to the trip) although
no storm unit is long: read it as the game's own part running late, not a storm unit. Hence the rules for every module:
  - work spread over passes takes a FIXED QUOTA a pass, chosen from measurement so that the pass stays under the cap on the heaviest
    course with the guard only as the backstop (the rain: rain.START_QUOTA clusters a start pass, rain.GRADE_ROWS grade rows a pass);
  - the guard is tested before every unit of work: a unit between two tests never above UNIT_MAX_US (0.2 ms). The rain's longest
    today: 178 us measured between the cluster loop's test and the cluster's first landing test (a cluster's motion, its wraps and
    its scale; the measured gap includes the game's vblank handler when it lands there). tests/test_weather_rain.py's
    `post_move_over` holds every pass at whose end the storm is live and in which the count moved, each part on its own (the join's
    split bound): from the move to the trip (storm_log.lua's B line) at most UNIT_MAX_US, from the trip to the pass's end at most
    TAIL_US (a pass whose count moved after the storm's last test: its whole time to TAIL_US); the sum is reported only. So a later
    stage's long unit shows there even when a run's worst pass stays under the cap (fix round 1: a planted 0.3 ms splash unit fails
    it);
  - the units with no guard test before them, each measured and allowed only as named here (stage 2's figures, the rain alone,
    then the joined build's, re-measured at the join with storm_makeup.lua on Metropolis RAIN, every module on): the work of a pass
    from the game's scenery routine's return to the first guard test: stage 2 47.5-51.5 us (the stub, the body, the rain's setup; on
    the first visible pass also the sky copy); joined 4.9-5.1 us over 3 507 show passes (the stub's return path, the body and the
    cover's first instructions: the cover, first in the order, tests the guard at once; the rain's setup now lies inside a unit
    between two tests, held to UNIT_MAX_US); the LOAD (F0, the copy lists; nothing drawn, nothing else of the storm in that pass):
    stage 2 40 us; joined 83.5 us from the scenery routine's return to the pass's end (five modules' lists, with the game's tail),
    88.5 us on Metropolis with task 8's extra record (its direction table), 84.5 / 89.5 us with W8's interrupt mask (re-measured on
    Big Forest, Bay Bridge reverse and Metropolis both ways; out/p86/w8);
    the RELEASE (every module's `release`: the rain's boot table in one copy, its sky when still ours; the cover's and the
    lightning's cells and sky): stage 2 349 us; joined 360 us (on the attract's opening scene load, 44 668 us DRY); bounded by
    RELEASE_US_MAX (400 us); THE SOUND'S TRIGGER (the join's round 2, J1, the session lead's ruling: exempt from the guard, it
    counts a late pass and sends all the same, so every word goes on the pass it is due; carrier.SOUND_TRIGGER_US): measured from
    its guard test to its last access of its cells (storm_makeup.lua's VR_MAKEUP_SCELLS, Metropolis and Bay Bridge reverse RAIN)
    7.0 us idle (8.0 on a late pass), 14.5 a rain word, 18.5-21.5 a thunder word, 25-29 us a thunder and a rain word on one pass
    (32 at most; the game's vblank handler, when it lands inside, adds its own ~190-240 us, as in any unit). The joined build's longest unit between two guard tests over the twenty races: 151 us (Bay Bridge
    reverse; lightning_log.lua's G lines), its longest unit in flight at the count's move 80 us (B lines). The release runs only at the attract's
    opening scenery call, a pass of the game's own scene load (two vblanks and more: 44.7 ms in a DRY game): never in a race
    (Release, below). A later module's release must stay within RELEASE_US_MAX with the rain's, or be split;
  - THE WET HANDLING'S ROUTINES (weather/handling.py, the join): entered from the game's own physics at its eight hook sites on
    every race pass of a RAIN race, ahead of the storm's frame and with no guard test: 165.46 us a pass with no rule firing, 161-212
    us measured on the trace build (findings, stage 5 and the join). They are part of the game's own part of the pass (THE PREMISE
    above), allowed as named here beside the release and the sound's trigger;
  - nothing of the storm moves the interrupt table (SBR) or writes the interval timer (0xe00008..0xe0000f); the one thing it does to
    the interrupts is the load's mask (below).

What an interrupt can reach (the final review's W8). The game enables one interrupt in play, the vblank (vector 65, 0xfff104, handler
0xfe02bc; vectors 64 and 66-69 only acknowledge). Followed from that handler by every direct branch, bsr, jsr and call (the repo's
disassembler; 550 instructions): no hook site of the weather, no bank register write, no interval timer; its call through the RAM
pointer 0x40DF20 is taken only when that pointer is non-zero, and it is 0 in every mode from the boot to the race (logged each frame).
But its backdrop column update (0xfe02fa -> 0xFFE0E0 -> 0xFFE498 -> 0x279A76, while the byte 0x40DF00 is 0) reads the data bank window
0x100000.. for the sky's columns, on every vblank around a race's start. The storm maps another bank there at one moment only: the
LOAD, whose copy lists put bank 3 (the storm's image, static data and course data) and then a course's own bank (its backdrop
colours) at the window before giving the course's bank back (a course whose data live in bank 3, Big Forest and Alpine, has its own
bank mapped throughout). Measured on fa8f251's build over the twenty RAIN loads (ten courses, both directions; out/p86/w8): the load
holds bank 3 for 45-50 us, 10.2-13.8 ms after the vblank before it and 3.55-7.09 ms before the next (closest: Acropolis normal,
3.55 ms); no interrupt landed inside one, but an interrupt there would read the storm's bank for that column: with the load held
open across a vblank (build's test-only `test_load_spin`, Bay Bridge) the handler read the window 62 times with bank 3 mapped and the
sky showed a wrong backdrop column (8 px at the left edge, rows 60-204) on every picture after the load. The gate byte 0x40DF00 does
not close it (the game sets it in the TEST menu; with it set the handler also skips its uptime counters and coin handling, which
would be lost, not deferred). CLOSED: the load masks interrupts across its copy lists with the game's own pair (IRQ_OFF / IRQ_ON:
`updpsw.w #0, #40000` before the first record, `updpsw.w #FFFFFFFF, #40000` after the course's bank is back; the PSW's interrupt
bit is set at every load measured, so the pair restores it). A vblank that falls due inside is taken right after (within 50 us in
the forced case) and no vblank and no pass is lost (tests/test_weather_carrier.py's test_no_interrupt_reads_the_storms_bank).

The guards (later modules call them before drawing; the rain inlines the same tests in its loops):
  guard_time (`jsr Layout.guard_time`): R0 = 0 while the vblank count is 0, 1 once it has moved (TRIMS_TIME counted). Other
    registers kept. `emit_guard_time(b, late)` emits the same test inline (branch to `late` when late).
  guard_records (`jsr Layout.guard_records` with R0 = the records the object adds): R0 = 0 and the frame's record count 0x5011a0
    raised by them when they fit the budget (0x5011b0, 10 500), else R0 = 1, the count unchanged and TRIMS_REC counted. Other
    registers kept. The storm is emitted after the game's scenery, so only the storm is ever trimmed; a module drawn before the
    rain (stage 4's strike) has priority in both guards by being called first.
  An object drawn: a matrix entry (0xB, 9 floats, 3 floats) and an object entry (1, colour pointer, polygon pointer, the budget word)
  at the display-list pointer 0x5017f4, which the module advances (as spike 48's rain does).

The registry. A module is a `Module`: its `code` (a function of the `Layout` returning one `Block` at `Layout.code(name)`, whose
labels `start` / `frame` / `release` the carrier calls, each optional, and whose labels named in `entries` the Layout exports for
the module's own site stubs), its `cells` (RAM state, zeroed at each load), `tables` (static, in the image), `data` (static, in
DATA), `course_data(entry)` (per menu entry, in bank 3, copied to one DATA place per name sized to the largest), `course_copies(entry)`
(per menu entry: (bank, window address 0x100000..0x1fffff, bytes) copied from that bank at the load; checked; a name TABLE_COPY +
<table> copies into the module's own image table <table> instead of a DATA place: after the common list, which copied the whole
image, so it holds until the next load; at most the table's length; task 8's per-course aim), `copies` (stage 4: the
same for every entry, (name, (bank, window address, bytes)), one DATA place each, in the common list: one copy record, not one an
entry; a module stores such data in a ROM block of its own through `rom`), `rom` ((block name,
bytes) written into ERASED blocks of the module's own in the layout table: polygon objects, colour words, a site's stub; a tuple, or
a function of the settled Layout returning one, so a boot-ROM stub can `jsr` a RAM label) and `sites` (a function of the settled
Layout returning (block name, original bytes, new bytes): HOOK SITES, the game's own code changed in place). A site's block is a
"boot site" or "program site" block of the module's own in the layout table (weather/layout.py's TABLE; `build`'s `table` for a
test), the original and new bytes its size; every site's bytes in the set are checked against the original before anything is
written (PatchError naming the site otherwise; a site declared twice is refused too). THE DRY PATH OF A SITE IS ITS AUTHOR'S DUTY:
in a DRY game it must do what the site's original instructions did and nothing else (for a call site: the stub tests the weather
byte, then SWITCH, and jumps to the original callee, as the scenery call's stub does). THE REGISTERS AT A SITE ARE ITS AUTHOR'S DUTY
TOO (the R0-R20 rule above covers only the routines the carrier calls): a site's stub and the RAM routine it enters must leave every
register and every flag the site's original code relies on exactly as the original instructions would, on the wet path as on the
dry, unless changing a value is the hook's purpose: push and pop what they use (`pushm` / `popm`), and where a test changes the flags
before the original code reads them, show that it does not read them (the callee sets them first, or the site's next instruction
does not test them). tests/test_weather_carrier.py's dummy module is the worked example: its stub and its routine `hit` use no
register (the stub's two compares and `hit`'s `add.w imm,abs` change only the flags), and the flags they change are not read: the
original callee 0xff7c1e sets them (`xor.b R2, R2`) before any test, and the site's code after the call sees the callee's flags, as
before. (The scenery call's stub saves R0-R20 and R26-R28 around its own work; the flags after its return are its last compare's,
which the site's next instruction, `rsr`, does not read.) Each module comes from a factory of REGISTRY, `factory(rs, converted,
tunes)` (`converted`: the build's converted courses, from `install`; `tunes`: a tune.Tunes, of which the factory hands its module
its own field and no other: the join's one rule for tunes); `install(rs, converted, tunes, modules)` lays it all out (the addresses
settle in a few passes), writes the stub, the modules' blocks and their sites. The joined build registers, in this order: `cover`
(stage 3; the rain calls its entry `cluster`), `lightning` (stage 4), `rain` (stage 2), `handling` (stage 5), `sound` (stage 6's triggers).

THE ORDER. The modules' list is REGISTRY's order (or `install`'s / `build`'s `modules`, as given). In a STARTING pass the carrier
calls every module's `start` in that order (all of them each pass until every one returns R0 = 0, so a start already done must
return R0 = 0 again at once); in a SHOW pass every `frame` in that order; at the release every `release` in the REVERSE order.
Cells, code and tables are laid out in the same order. A module
chooses its place by where its factory stands in REGISTRY: first drawn first, so first served by both guards (stage 4's strike
before the rain); a module whose frame must see another's results this pass stands after it.

ANOTHER MODULE'S CELLS. Every module's cells are laid out before any code is made, so a module's `code(lay)` reads a cell another
module owns by name, `lay.cell(owner, name)` (stage 4 reading stage 3's, stage 6 stage 4's), wherever the two stand in the order;
`lay.data_at`, `lay.table` and `lay.label` likewise. When the owning module is absent (or has no such cell) the layout raises
PatchError naming (owner, name) and nothing is built; a builder testing a module alone registers a small stand-in module of the
owner's name that declares the cells it reads (tests/test_weather_carrier.py::test_a_module_reads_another_modules_cell_by_name).
The owner zeroes its cells at each load with all others and writes them in its own routines; a reader must not write them.

Release (Review Focus 2 and 5): at the first scenery call where the storm is off (a non-rain mode with the weather byte 1, or the
weather byte 0 with STATE not IDLE) or the menu entry differs from LOADKEY's (the copy is redone for the new course). In the game's
flow that is the attract's opening (mode 0x2, its fourth frame): every way from a RAIN race to anything else passes the results'
last mode 0x1d and then the attract's opening, also with a coin and START in the results or during the race (fix round 1); the
test menu reboots and a soft reset clears the RAM instead. From the last rain mode to there the grade stays in the colour RAM, but
nothing drawn shows it (0x1d shows the last rain picture; the attract's opening draws nothing that reads the grade, and the game
has already replaced the grey sky with its own palette: tests/test_weather_carrier.py's test_nothing_of_the_storm_shows_after_its_
modes). The selection screens that follow do read the colour RAM (a release leaving the grade shows on them): the release comes
two frames before the first of them, by the game's flow. The branch for another entry while loaded is not reached by the game's
flow (no scenery call between two races that is not the attract's opening); it is kept as defensive code (the session lead's ruling
on fix round 1's F6) and tested on a forced state, the load key poked (test_the_reload_branch_on_a_forced_state). A module's `release` must put back whatever it changed outside its own RAM (the rain: the colour
translation table and the sky), whatever state it was in.

Counters (words): NLOAD 0x520008 loads, NSTART 0x52000c start passes, NSHOW 0x520010 show passes, TRIMS_REC 0x520014 and
TRIMS_TIME 0x520018 (the routines' trims; the rain counts its own in its cells).

What was tried and removed (19 Nov 2026; do not rebuild it). To hold an earlier 17.4 ms cap, a first build swapped SBR to a RAM
copy of the vector table while the storm was loaded, its vblank vector restarting the interval timer (0xe00008) so the count
0xe0000c gave the time since the vblank. The test menu, entered from a RAIN race, keeps SBR as it finds it; its MEMORY TEST writes
test patterns over 0x500000..0x53ffff with interrupts off, the RAM table included, and the next interrupt vectored through them:
MAME stopped with "Unhandled OpCode found : bc35 at 02500007" (main's set, the same inputs, ran on). The session lead's ruling: the
storm never moves the interrupt table; the game's vblank count is its only time, the cap its bound: 17.8 ms at stage 2 (findings,
stage 2), 17.9 ms since the join (Time, above)."""
from __future__ import annotations

import dataclasses
import struct
from dataclasses import dataclass, field
from typing import Callable

from vrtools.arcade.patch import PatchError
from vrtools.arcade.romset import V60_BOOT, V60_PROGRAM, RomSet
from vrtools.arcade.v60asm import Block, asm

TABLE_COPY = "@"                        # a course copy named "@<table>" lands in the module's own image table (Module.course_copies)


# ---- the game's cells and the board's registers --------------------------------------------------------------------------------
VBL = 0x500501                          # the vblank count: 0 at the wait's exit, 1 from the vblank 17.38 ms after it
LIST_PTR = 0x5017F4                     # the display list's write pointer
REC_COUNT = 0x5011A0                    # the frame's record count
BUDGET = 0x5011B0                       # the frame's record budget (budget.BUDGET_CELL: 10 500)
MODE = 0x501138                         # the game's mode byte (weather.RAIN_MODES)
MENU = 0x501940                         # the menu entry 0..9
LINKED = 0x40DC8C                       # nonzero in linked play
BANKREG = 0xE00004                      # (bank << 4) | 1 maps data bank `bank` at the window 0x100000
XLAT = 0x910000                         # the colour-translation RAM
HOOK_SITE = 0xFEE144                    # `jsr FF8450[PC]`: the scenery routine, the race scene's last emitter
HOOK_PATTERN = bytes.fromhex("e8f20ca30000")
SCENERY = 0xFF8450

# ---- the storm's RAM -----------------------------------------------------------------------------------------------------------
STORM_RAM = (0x520000, 0x53F000)
CARRIER_CELLS = 0x520000
SWITCH = CARRIER_CELLS + 0x00           # byte
STATE = CARRIER_CELLS + 0x01            # byte
PENDING = CARRIER_CELLS + 0x02          # byte: a module's start asked for another pass
LOADKEY = CARRIER_CELLS + 0x04
NLOAD, NSTART, NSHOW, TRIMS_REC, TRIMS_TIME = (CARRIER_CELLS + 0x08 + 4 * k for k in range(5))
MODULE_CELLS = (0x520100, 0x522000)
IMAGE = (0x522000, 0x52A000)
DATA = (0x52A000, 0x53F000)
IDLE, STARTING, SHOW = 0, 1, 2
KEYMAGIC = 0x53540000                   # LOADKEY = KEYMAGIC | menu entry

# ---- the guard ---------------------------------------------------------------------------------------------------------------
UNIT_MAX_US = 200                       # the rule for the storm's modules: no unit of work longer than this between two guard tests
TAIL_US = 160                           # the tail from the guard's trip to the pass's end (the join, the session lead's ruling of 19 Nov
                                        # 2026, re-measured in round 2; stage 2's 31 us was one module's returns and the game's list
                                        # submission). Round 1 measured 182 us (195.5 once) after a trip in the rain's splash loop, whose
                                        # late path then visited every remaining slot; round 2 (J2) clears them in one string fill and
                                        # (J1) the sound's trigger sends on a late pass too. Measured on the round-2 build (storm_makeup.lua,
                                        # Metropolis and Bay Bridge reverse RAIN, out/p80j/mk_r2*): natural tails at most 58 us (a trip
                                        # in the cover; 52 in the rain); forced at the splash loop's head with 40 live slots and the
                                        # trigger sending a thunder and a rain word on that pass, 72 us; forced in the first module (every
                                        # module's late path, the worst over the registry order) with the trigger sending both words,
                                        # 149 us (median 132). 160 = 149 and a small allowance
RELEASE_US_MAX = 400                    # the release, one unit (measured 349 us): it runs on the attract's opening scene load only
SOUND_TRIGGER_US = 40                   # the sound's trigger, an allowed unguarded unit (the join's round 2, J1): measured 7 us idle,
                                        # 25-32 us sending a thunder and a rain word on one pass (the contract's list above)
SAVE = 0x1FFFFF | (7 << 26)             # R0-R20, R26-R28
CHUNK = 0x4000                          # halfwords a copy record moves at most


@dataclass(frozen=True)
class Module:
    """A storm module (see the contract above)."""
    name: str
    code: Callable[["Layout"], Block]
    cells: tuple[tuple[str, int], ...] = ()
    tables: tuple[tuple[str, bytes], ...] = ()
    data: tuple[tuple[str, bytes], ...] = ()
    course_data: Callable[[int], dict[str, bytes]] | None = None
    course_copies: Callable[[int], dict[str, tuple[int, int, int]]] | None = None
    copies: tuple[tuple[str, tuple[int, int, int]], ...] = ()
    rom: tuple[tuple[str, bytes], ...] | Callable[["Layout"], tuple[tuple[str, bytes], ...]] = ()
    sites: Callable[["Layout"], tuple[tuple[str, bytes, bytes], ...]] | None = None
    start: str | None = None
    frame: str | None = None
    release: str | None = None
    entries: tuple[str, ...] = ()


@dataclass
class Layout:
    """Where everything of the storm lies (RAM addresses), as `install` settles it."""
    cells: dict = field(default_factory=dict)          # (module, name) -> RAM
    tables: dict = field(default_factory=dict)         # (module, name) -> RAM (in the image)
    data: dict = field(default_factory=dict)           # (module, name) -> RAM (in DATA)
    codes: dict = field(default_factory=dict)          # module -> RAM of its Block
    labels: dict = field(default_factory=dict)         # (module, label) -> RAM
    carrier: dict = field(default_factory=dict)        # the carrier's routines: body, release, guard_time, guard_records
    settled: bool = False                              # the addresses have settled: an unknown name now raises PatchError

    def _get(self, kind: str, store: dict, key) -> int:
        if key in store:
            return store[key]
        if self.settled:
            raise PatchError(f"the storm layout has no {kind} {key!r}")
        return IMAGE[0]                                 # a placeholder until the image settles (an address: the same encoding)

    def _strict(self, kind: str, store: dict, key) -> int:
        if key not in store:                            # cells and data places are laid out before any code: always strict
            raise PatchError(f"the storm layout has no {kind} {key!r}")
        return store[key]

    def cell(self, module: str, name: str) -> int:
        return self._strict("cell", self.cells, (module, name))

    def table(self, module: str, name: str) -> int:
        return self._get("table", self.tables, (module, name))

    def data_at(self, module: str, name: str) -> int:
        return self._strict("data place", self.data, (module, name))

    def code(self, module: str) -> int:
        return self._get("module code", self.codes, module)

    def label(self, module: str, label: str) -> int:
        """A module's `start`, `frame` or `release` label or one of its `entries` (the ones a module declares)."""
        return self._get("label", self.labels, (module, label))

    @property
    def guard_time(self) -> int:
        return self.carrier.get("guard_time", IMAGE[0])

    @property
    def guard_records(self) -> int:
        return self.carrier.get("guard_records", IMAGE[0])


# ---- emitters other modules use ----------------------------------------------------------------------------------------------
def emit_guard_time(b: Block, late: str) -> None:
    """Branch to `late` when the pass is already late (guard_time's test, inline): the game's vblank count 0x500501 has moved since
    the pass's wait (the game writes 0 there at the wait's exit, 0xfe1406; the vblank 17.38 ms into the pass makes it 1)."""
    b.emit("cmp.b imm,abs", 0, VBL)
    b.branch("bne", late)


def emit_copy(b: Block, src: str, dst: str, halfwords: int | str, count: str = "r3") -> None:
    """movcu.h from [src] to [dst], `halfwords` (an immediate or a register); changes `count`, R27 and R28."""
    if isinstance(halfwords, int):
        b.emit("mov.w imm,reg", halfwords, count)
        halfwords = count
    b.emit("movcu.h [reg],reg,[reg],reg", src, halfwords, dst, halfwords)


# ---- the carrier's own code ----------------------------------------------------------------------------------------------------
def carrier_code(at: int, modules: list[Module], lay: Layout) -> Block:
    """In the image: `body` (the pass's dispatch by STATE), `release` (the modules' releases), `guard_time`, `guard_records`."""
    b = Block(at)
    b.label("body")
    b.emit("pushm imm", SAVE)
    b.emit("cmp.b imm,abs", SHOW, STATE)
    b.branch("be", "show")
    b.emit("add.w imm,abs", 1, NSTART)
    b.emit("mov.b imm,abs", 0, PENDING)
    for m in modules:
        if m.start:
            b.emit("jsr abs", lay.label(m.name, m.start))
            b.emit("cmp.w imm,reg", 0, "r0")
            b.branch("be", f"started_{m.name}")
            b.emit("mov.b imm,abs", 1, PENDING)
            b.label(f"started_{m.name}")
    b.emit("cmp.b imm,abs", 0, PENDING)
    b.branch("bne", "body_out")
    b.emit("mov.b imm,abs", SHOW, STATE)
    b.branch("br", "body_out")
    b.label("show")
    b.emit("add.w imm,abs", 1, NSHOW)
    for m in modules:
        if m.frame:
            b.emit("jsr abs", lay.label(m.name, m.frame))
    b.label("body_out")
    b.emit("popm imm", SAVE)
    b.emit("rsr")
    b.label("release")
    b.emit("pushm imm", SAVE)
    for m in reversed(modules):
        if m.release:
            b.emit("jsr abs", lay.label(m.name, m.release))
    b.emit("popm imm", SAVE)
    b.emit("rsr")
    b.label("guard_time")
    emit_guard_time(b, "gt_late")
    b.emit("mov.w imm,reg", 0, "r0")
    b.emit("rsr")
    b.label("gt_late")
    b.emit("add.w imm,abs", 1, TRIMS_TIME)
    b.emit("mov.w imm,reg", 1, "r0")
    b.emit("rsr")
    b.label("guard_records")
    b.emit("add.w reg,abs", "r0", REC_COUNT)
    b.emit("cmp.w abs,abs", BUDGET, REC_COUNT)          # flags of count - budget
    b.branch("bgt", "gr_trim")
    b.emit("mov.w imm,reg", 0, "r0")
    b.emit("rsr")
    b.label("gr_trim")
    b.emit("sub.w reg,abs", "r0", REC_COUNT)
    b.emit("add.w imm,abs", 1, TRIMS_REC)
    b.emit("mov.w imm,reg", 1, "r0")
    b.emit("rsr")
    return b


# ---- the stub (boot ROM) -------------------------------------------------------------------------------------------------------
STUB_LABELS = ("release", "load", "copy_list")


def stub_code(at: int, lay: dict, rain_modes: tuple[int, ...], weather_byte: int) -> Block:
    """The stub at `at` (the hook site's callee), its `release`, `load` and `copy_list`. `lay`: body, release (the image's),
    copydir, banktab, common (the common list), cells_hw (module cells to zero, halfwords)."""
    labels = {k: 0xFFFFFFF0 for k in STUB_LABELS}       # placeholders of the final encodings' length, then the real addresses
    for _ in range(4):
        b = _stub_block(at, lay, rain_modes, weather_byte, labels)
        got = {k: b.addr(k) for k in STUB_LABELS}
        if got == labels:
            return b
        labels = got
    raise PatchError("the storm stub's layout did not settle")


def _stub_block(at, lay, rain_modes, weather_byte, labels) -> Block:
    b = Block(at)
    b.emit("cmp.b imm,abs", 1, weather_byte)            # DRY: these three and the game's routine, nothing else
    b.branch("be", "wet")
    b.emit("cmp.b imm,abs", IDLE, STATE)
    b.branch("bne", "wet")
    b.emit("jmp abs", SCENERY)
    b.label("wet")
    b.emit("pushm imm", SAVE)
    b.emit("mov.w imm,reg", 0, "r9")                    # R9 := the decision
    b.emit("cmp.b imm,abs", 1, weather_byte)
    b.branch("bne", "decided")
    b.emit("cmp.b imm,abs", 0, LINKED)
    b.branch("bne", "decided")
    b.emit("movz.bw abs,reg", MENU, "r0")
    b.emit("cmp.w imm,reg", lay.get("entries", 10), "r0")      # the directory's entries (len(dirs): 10 in every build)
    b.branch("bge", "decided")                          # not a directory entry
    for md in rain_modes:
        b.emit("cmp.b imm,abs", md, MODE)
        b.branch("be", "on")
    b.branch("br", "decided")
    b.label("on")
    b.emit("mov.w imm,reg", 1, "r9")
    b.label("decided")
    b.emit("cmp.b imm,abs", IDLE, STATE)
    b.branch("be", "switch")
    b.emit("cmp.w imm,reg", 0, "r9")
    b.branch("be", "rel")                               # the storm off with something live: put it back
    b.emit("movz.bw abs,reg", MENU, "r0")
    b.emit("or.w imm,reg", KEYMAGIC, "r0")
    b.emit("cmp.w abs,reg", LOADKEY, "r0")
    b.branch("be", "switch")                            # loaded for this entry: go on
    b.label("rel")
    b.emit("jsr abs", labels["release"])                # another entry's, or the storm off: released (then loaded again)
    b.label("switch")
    b.emit("mov.b reg,abs", "r9", SWITCH)
    b.emit("popm imm", SAVE)
    b.emit("jsr abs", SCENERY)
    b.emit("cmp.b imm,abs", 0, SWITCH)
    b.branch("bne", "after")
    b.emit("rsr")
    b.label("after")
    b.emit("pushm imm", SAVE)
    b.emit("cmp.b imm,abs", IDLE, STATE)
    b.branch("bne", "running")
    b.emit("jsr abs", labels["load"])
    b.branch("br", "out")
    b.label("running")
    b.emit("jsr abs", lay["body"])
    b.label("out")
    b.emit("popm imm", SAVE)
    b.emit("rsr")
    # ---- release: the modules' (STATE is not IDLE: the image is in RAM), then the cells
    b.label("release")
    b.emit("jsr abs", lay["release"])
    b.emit("mov.b imm,abs", IDLE, STATE)
    b.emit("mov.w imm,abs", 0, LOADKEY)
    b.emit("mov.b imm,abs", 0, SWITCH)
    b.emit("rsr")
    # ---- load (F0)
    b.label("load")
    b.emit("add.w imm,abs", 1, NLOAD)
    b.emit("mov.w imm,reg", MODULE_CELLS[0], "r11")      # the module cells zeroed (movcfu.h: no source, R26's half as the fill)
    b.emit("mov.w imm,reg", lay["cells_hw"], "r9")
    b.emit("mov.w imm,reg", 0, "r26")
    b.emit("movcfu.h [reg],imm,[reg],reg", "r11", 0, "r11", "r9")
    b.raw(IRQ_OFF)                                      # W8: interrupts masked across the copy lists (the vblank handler reads the
    b.emit("mov.w imm,reg", lay["common"], "r5")        # bank window for the sky backdrop's columns); the game's own form
    b.emit("jsr abs", labels["copy_list"])
    if lay.get("load_spin"):                            # TEST ONLY (build's test_load_spin): bank 3 still mapped here
        b.emit("mov.w imm,reg", lay["load_spin"], "r0")
        b.label("spin")
        b.emit("sub.w imm,reg", 1, "r0")
        b.branch("bne", "spin")
    b.emit("movz.bw abs,reg", MENU, "r5")
    b.emit("mov.w abs(reg),reg", lay["copydir"], "r5", "r5")
    b.emit("jsr abs", labels["copy_list"])
    b.emit("movz.bw abs,reg", MENU, "r2")
    b.emit("movz.bw abs(reg),reg", lay["banktab"], "r2", "r2")
    b.emit("mov.b reg,abs", "r2", BANKREG)              # the course's own bank back
    b.raw(IRQ_ON)                                       # W8: interrupts again (a vblank that fell due inside is taken here)
    b.emit("movz.bw abs,reg", MENU, "r0")
    b.emit("or.w imm,reg", KEYMAGIC, "r0")
    b.emit("mov.w reg,abs", "r0", LOADKEY)
    b.emit("mov.b imm,abs", STARTING, STATE)
    b.emit("rsr")
    # ---- copy_list: R5 = a list of (bank register value, source, destination, halfwords) records, 0-terminated
    b.label("copy_list")
    b.emit("mov.w [reg],reg", "r5", "r2")
    b.emit("cmp.w imm,reg", 0, "r2")
    b.branch("be", "cl_done")
    b.emit("mov.b reg,abs", "r2", BANKREG)
    b.emit("mov.w disp[reg],reg", 4, "r5", "r0")
    b.emit("mov.w disp[reg],reg", 8, "r5", "r1")
    b.emit("mov.w disp[reg],reg", 12, "r5", "r3")
    emit_copy(b, "r0", "r1", "r3")
    b.emit("add.w imm,reg", 16, "r5")
    b.branch("br", "copy_list")
    b.label("cl_done")
    b.emit("rsr")
    return b


# ---- layout and install --------------------------------------------------------------------------------------------------------
def _align(a: int, n: int = 4) -> int:
    return (a + n - 1) // n * n


# THE READERS AFTER THEIR WRITERS (the final review's W6): a module that reads another's cells in the same pass comes after it in
# the frame order: (writer, reader). The rain reads the cover's MODE / WALK / NOSPLASH (written before the cover's first guard, so
# even a late pass leaves them right); the lightning reads the cover's `under_cover`; the sound's triggers read the lightning's
# strike_seq / strike_band of this pass. A module list against this rule is refused when both are present.
READ_AFTER_WRITE = (("cover", "rain"), ("cover", "lightning"), ("lightning", "sound"))


def check_order(modules: list[Module]) -> None:
    """PatchError when a reader of READ_AFTER_WRITE comes before its writer in `modules` (both present)."""
    names = [m.name for m in modules]
    for w, r in READ_AFTER_WRITE:
        if w in names and r in names and names.index(w) > names.index(r):
            raise PatchError(f"the storm module {r} reads the {w}'s cells in the same pass: {w} must come before {r} "
                             f"(the order given: {', '.join(names)})")


def lay_out(modules: list[Module], courses: int = 10) -> tuple[Layout, dict, bytes]:
    """The Layout of `modules` (cells, image, data), the image's pieces and the image's bytes; PatchError when a space overflows or
    the order breaks READ_AFTER_WRITE."""
    check_order(modules)
    lay = Layout()
    a = MODULE_CELLS[0]
    for m in modules:
        for name, size in m.cells:
            lay.cells[(m.name, name)] = a
            a = _align(a + size)
    if a > MODULE_CELLS[1]:
        raise PatchError(f"the storm's module cells need {a - MODULE_CELLS[0]} bytes, {MODULE_CELLS[1] - MODULE_CELLS[0]} at most")
    lay.carrier["cells_end"] = a
    d = DATA[0]
    for m in modules:
        for name, blob in m.data:
            lay.data[(m.name, name)] = d
            d = _align(d + len(blob), 16)
    for m in modules:
        for name, (_, _, n) in m.copies:
            lay.data[(m.name, name)] = d
            d = _align(d + n, 16)
    for m in modules:
        sizes: dict[str, int] = {}
        for e in range(courses):
            for name, blob in (m.course_data(e) if m.course_data else {}).items():
                sizes[name] = max(sizes.get(name, 0), len(blob))
            for name, (_, _, n) in (m.course_copies(e) if m.course_copies else {}).items():
                if not name.startswith(TABLE_COPY):     # a copy into an image table takes no DATA place
                    sizes[name] = max(sizes.get(name, 0), n)
        for name, n in sizes.items():
            lay.data[(m.name, name)] = d
            d = _align(d + n, 16)
    if d > DATA[1]:
        raise PatchError(f"the storm's data need {d - DATA[0]} bytes of RAM, {DATA[1] - DATA[0]} at most")
    lay.carrier["data_end"] = d
    pieces: dict = {}
    for _ in range(8):
        prev = (dict(lay.labels), dict(lay.codes), dict(lay.tables), dict(lay.carrier))
        at = IMAGE[0]
        cb = carrier_code(at, modules, lay)
        pieces["carrier"] = (at, cb.bytes())
        for k in ("body", "release", "guard_time", "guard_records"):
            lay.carrier[k] = cb.addr(k)
        at = _align(at + len(pieces["carrier"][1]))
        for m in modules:
            lay.codes[m.name] = at
            blk = m.code(lay)
            if blk.base != at:
                raise PatchError(f"the storm module {m.name}'s code is not at its address")
            code = blk.bytes()
            for lb in (m.start, m.frame, m.release, *m.entries):
                if lb:
                    lay.labels[(m.name, lb)] = blk.addr(lb)
            pieces[m.name] = (at, code)
            at = _align(at + len(code))
        for m in modules:
            for name, blob in m.tables:
                lay.tables[(m.name, name)] = at
                pieces[(m.name, name)] = (at, blob)
                at = _align(at + len(blob))
        if (dict(lay.labels), dict(lay.codes), dict(lay.tables), dict(lay.carrier)) == prev:
            break
    else:
        raise PatchError("the storm image's layout did not settle")
    lay.settled = True                                  # once more, strict: a name no module has raises, naming it
    carrier_code(IMAGE[0], modules, lay)
    for m in modules:
        m.code(lay)
    if at > IMAGE[1]:
        raise PatchError(f"the storm's image needs {at - IMAGE[0]} bytes of RAM, {IMAGE[1] - IMAGE[0]} at most")
    image = bytearray(b"\xff" * (at - IMAGE[0]))
    for a0, blob in pieces.values():
        image[a0 - IMAGE[0]:a0 - IMAGE[0] + len(blob)] = blob
    if len(image) % 2:
        image += b"\xff"
    return lay, pieces, bytes(image)


def _records(bank: int, src: int, dst: int, nbytes: int, what: str = "copy", banks: int = 16) -> list[bytes]:
    """The copy records (CHUNK halfwords at most each) moving `nbytes` from `src` (a window address of data bank `bank`) to `dst`;
    PatchError naming `what` when the source is not inside the bank window 0x100000..0x1fffff or the set has no bank `bank`."""
    if not (0 <= bank < banks and 0x100000 <= src and src + nbytes + (nbytes & 1) <= 0x200000):
        raise PatchError(f"the storm's copy {what} (bank {bank}, {src:#x}, {nbytes} bytes) is not inside a bank window of the set "
                         f"(banks 0..{banks - 1}, 0x100000..0x1fffff)")
    out, done, hw = [], 0, (nbytes + 1) // 2
    while done < hw:
        k = min(CHUNK, hw - done)
        out.append(struct.pack("<4I", (bank << 4) | 1, src + 2 * done, dst + 2 * done, k))
        done += k
    return out


def _put(rs_parts: dict, space: str, addr: int, blob: bytes) -> None:
    """Write `blob` at `addr` of `space` (program, boot, bank3, polygon) in the mutable copies `rs_parts`, checked erased."""
    region, off = {"program": ("program", addr - V60_PROGRAM), "boot": ("boot", addr - V60_BOOT),
                   "bank3": ("data", 3 * 0x100000 + addr - 0x100000), "polygon": ("polygons", addr)}[space]
    buf = rs_parts[region]
    if off < 0 or off + len(blob) > len(buf):
        raise PatchError(f"the storm's {space} bytes at {addr:#x} ({len(blob)}) reach past the end of the {region} region")
    if any(x != 0xFF for x in buf[off:off + len(blob)]):
        raise PatchError(f"the storm's {space} bytes at {addr:#x} are not erased")
    buf[off:off + len(blob)] = blob


def install(rs: RomSet, converted: list | None = None, tunes=None, modules: list[Module] | None = None) -> RomSet:
    """The carrier with `modules` (default: `default_modules(rs, tunes, converted)`) on `rs`, as a new set (see `build`). `tunes`: a
    tune.Tunes (the defaults when None)."""
    return build(rs, modules if modules is not None else default_modules(rs, tunes, converted))[0]


def _cover_factory(rs: RomSet, converted, tunes) -> Module:
    from vrtools.arcade.weather import cover
    # its tables from rs's faces; the rain's cluster count, a fact of the rain (its clusters are what the cover hides), not a tune
    # of the cover's
    return cover.module(rs, tunes.cover, tunes.rain.clusters)


def _lightning_factory(rs: RomSet, converted, tunes) -> Module:
    from vrtools.arcade.weather import lightning
    return lightning.module(rs, tunes.lightning)


def _rain_factory(rs: RomSet, converted, tunes) -> Module:
    from vrtools.arcade.weather import rain
    return rain.module(rs, tunes.rain)                  # the rain reads the courses from the set's directory, not `converted`


def _handling_factory(rs: RomSet, converted, tunes) -> Module:
    from vrtools.arcade.weather import handling
    return handling.module(rs, tunes.handling)


def _sound_factory(rs: RomSet, converted, tunes) -> Module:
    from vrtools.arcade.weather import sound
    return sound.module(rs, converted, tunes.sound)     # the V60's triggers (the sound board's part: weather.install_weather)


# The registry, in frame order: each factory(rs, converted, tunes) returns a Module (`converted` the build's converted courses,
# `tunes` a tune.Tunes: the factory hands its module its own field, `tunes.<module name>`, and no other: the join's one rule for
# tunes). The join's order: cover, lightning, rain, handling, sound. The cover first (its frame decides the cover before anything is
# drawn); the lightning before the rain (the strike drawn first: served first by both guards, spec 5.5); the handling after the rain
# (its frame routine reads nothing of another module's); the sound's triggers last of all (they read lightning's cells and must see
# this pass's strike).
REGISTRY: list[Callable[[RomSet, list | None, object], Module]] = [_cover_factory, _lightning_factory, _rain_factory,
                                                                   _handling_factory, _sound_factory]


def default_modules(rs: RomSet, tunes=None, converted: list | None = None) -> list[Module]:
    """The registry's modules for `rs` with `tunes` (a tune.Tunes; the defaults when None): the cover, the lightning, the rain, the
    handling and the sound's triggers."""
    from vrtools.arcade.weather.tune import Tunes
    tunes = Tunes() if tunes is None else tunes
    if not isinstance(tunes, Tunes):
        raise TypeError(f"the storm's modules take a tune.Tunes, not {type(tunes).__name__}")
    return [f(rs, converted, tunes) for f in REGISTRY]


def module_named(name: str, rs: RomSet, tunes=None, converted: list | None = None) -> Module:
    """The registry's module `name` alone (its factory `_<name>_factory`), as default_modules would make it (tests pick one by
    name)."""
    from vrtools.arcade.weather.tune import Tunes
    for f in REGISTRY:
        if f.__name__ == f"_{name}_factory":
            return f(rs, converted, Tunes() if tunes is None else tunes)
    raise PatchError(f"the storm's registry has no module {name!r}")


def _sites(rs: RomSet, modules: list[Module], lay: Layout, blk: dict) -> list[tuple[object, bytes]]:
    """Every module's hook sites as (block, new bytes), each checked before anything is written: its block in the table, a site
    block ("boot site" / "program site") of that module, declared once, the original and new bytes the block's size, the set's bytes
    there the original; PatchError naming the site otherwise."""
    from vrtools.arcade.weather import layout
    out, seen = [], set()
    for m in modules:
        for name, old, new in (m.sites(lay) if m.sites else ()):
            if name in seen:
                raise PatchError(f"the storm module {m.name}'s site {name!r} is declared twice")
            seen.add(name)
            b = blk.get(name)
            if b is None or b.space not in ("boot site", "program site") or b.owner != m.name:
                raise PatchError(f"the storm module {m.name}'s site {name!r} is not a site block of its own in the layout table")
            if len(old) != b.size or len(new) != b.size:
                raise PatchError(f"the storm module {m.name}'s site {name!r}: {len(old)} original and {len(new)} new bytes, the "
                                 f"block holds {b.size}")
            got = layout.rom_bytes(rs, b)
            if got != old:
                raise PatchError(f"the storm module {m.name}'s site {name!r} at {b.start:#x}: {got.hex()}, expected {old.hex()}")
            out.append((b, new))
    return out


# W8 (the final review): the game's own instructions for masking interrupts (PSW bit 18), as its main code brackets its critical
# sections with them (0xfe065a / 0xfe06a2 and four more pairs): `updpsw.w #0, #40000` and `updpsw.w #FFFFFFFF, #40000`. The storm's
# load masks interrupts across its copy lists only: from before the first record to after the course's own bank is back.
IRQ_OFF = bytes.fromhex("1380e0f400000400")
IRQ_ON = bytes.fromhex("1380f4fffffffff400000400")
LOAD_SPIN_MAX = 200_000                 # TEST ONLY: `build(test_load_spin=)`'s largest loop count (about 90 ms)


def build(rs: RomSet, modules: list[Module], table: list | None = None, test_load_spin: int = 0) -> tuple[RomSet, dict]:
    """The carrier and `modules` on `rs` (the weather screen installed: the blocks of weather/layout.py's owners "carrier" and the
    modules' still erased), as a new set and a report (where everything went). `table`: the layout table (default
    weather/layout.py's `blocks()`; checked with `layout.check_table`). PatchError when the hook site is not the game's
    `jsr FF8450`, a module's site holds other bytes than its original, a block overflows, is not erased or is not in the table.
    `test_load_spin` (TEST ONLY, 0 in every build): a delay loop of that many turns in the load right after the common list, while
    bank 3 is still mapped, so that a vblank interrupt lands inside the load (the final review's W8 test)."""
    if not (type(test_load_spin) is int and 0 <= test_load_spin <= LOAD_SPIN_MAX):
        raise PatchError(f"test_load_spin {test_load_spin!r}: an int 0..{LOAD_SPIN_MAX} (test only)")
    from vrtools.arcade.directory import decode_directory
    from vrtools.arcade.weather import RAIN_MODES as rain_modes, WEATHER_BYTE as weather_byte, layout
    table = list(table) if table is not None else layout.blocks()
    layout.check_table(table)
    site = rs.boot[HOOK_SITE - V60_BOOT:HOOK_SITE - V60_BOOT + len(HOOK_PATTERN)]
    if site != HOOK_PATTERN:
        raise PatchError(f"the scenery call at {HOOK_SITE:#x}: {site.hex()}, expected {HOOK_PATTERN.hex()}")
    dirs = decode_directory(rs)
    lay, pieces, image = lay_out(modules, len(dirs))
    blk = {b.name: b for b in table}
    hook_sites = _sites(rs, modules, lay, blk)          # all checked before anything is written
    parts = {r: bytearray(getattr(rs, r)) for r in ("program", "boot", "data", "polygons")}
    banks = len(rs.data) // 0x100000
    # bank 3: the image, the static data, every course's data
    common, at3 = [], {}
    img_blk = blk["storm image"]
    if len(image) > img_blk.size:
        raise PatchError(f"the storm image ({len(image)} bytes) does not fit its block ({img_blk.size})")
    _put(parts, "bank3", img_blk.start, image)
    common += _records(3, img_blk.start, IMAGE[0], len(image), "storm image", banks)
    a = blk["storm data"].start
    for m in modules:
        for name, blob in m.data:
            blob = blob + b"\xff" * (len(blob) % 2)
            if a + len(blob) > blk["storm data"].start + blk["storm data"].size:
                raise PatchError(f"the storm's static data do not fit their block at {name}")
            _put(parts, "bank3", a, blob)
            common += _records(3, a, lay.data_at(m.name, name), len(blob), f"{m.name} {name}", banks)
            at3[(m.name, name)] = a
            a = _align(a + len(blob), 16)
    static_end = a
    for m in modules:                                   # the modules' static copies from a bank (stage 4): the common list too
        for name, (bank, src, n) in m.copies:
            common += _records(bank, src, lay.data_at(m.name, name), n, f"{m.name} {name}", banks)
    per_entry = {}
    a = blk["storm course data"].start
    for e, d in enumerate(dirs):
        recs = []
        for m in modules:
            for name, blob in (m.course_data(e) if m.course_data else {}).items():
                blob = blob + b"\xff" * (len(blob) % 2)
                if a + len(blob) > blk["storm course data"].start + blk["storm course data"].size:
                    raise PatchError(f"the storm's course data do not fit their block at entry {e} {name}")
                _put(parts, "bank3", a, blob)
                recs += _records(3, a, lay.data_at(m.name, name), len(blob), f"{m.name} {name}", banks)
                a = _align(a + len(blob), 16)
            for name, (bank, src, n) in (m.course_copies(e) if m.course_copies else {}).items():
                if name.startswith(TABLE_COPY):
                    tname = name[len(TABLE_COPY):]
                    if tname not in dict(m.tables):
                        raise PatchError(f"the storm module {m.name}'s copy {name!r} (entry {e}) names no image table of its own")
                    size = len(dict(m.tables)[tname])
                    if not (0 < n and n + (n & 1) <= size):          # _records copies (n + 1) // 2 halfwords
                        raise PatchError(f"the storm module {m.name}'s copy {name!r} (entry {e}, {n} bytes) does not fit its image "
                                         f"table {tname!r} ({size} bytes)")
                    dst = lay.table(m.name, tname)
                else:
                    dst = lay.data_at(m.name, name)
                recs += _records(bank, src, dst, n, f"{m.name} {name} (entry {e})", banks)
        per_entry[e] = b"".join(recs) + struct.pack("<I", 0)
    common_blob = b"".join(common) + struct.pack("<I", 0)
    # the modules' ROM blocks (erased blocks of their own; their bytes may be made from the settled Layout)
    rom_used = {}
    for m in modules:
        for name, blob in (m.rom(lay) if callable(m.rom) else m.rom):
            b = blk.get(name)
            if b is None or b.space not in layout.ERASED or b.owner != m.name:
                raise PatchError(f"the storm module {m.name}'s ROM block {name!r} is not an erased block of its own in the layout table")
            if len(blob) > b.size:
                raise PatchError(f"the storm's {name} ({len(blob)} bytes) does not fit its block ({b.size})")
            _put(parts, b.space, b.start, blob)
            rom_used[name] = len(blob)
    # the stub, its lists and tables
    sb = blk["storm stub"]
    slay = {"body": lay.carrier["body"], "release": lay.carrier["release"], "cells_hw": (lay.carrier["cells_end"] - MODULE_CELLS[0]) // 2,
            "copydir": sb.start, "banktab": sb.start, "common": sb.start, "load_spin": test_load_spin, "entries": len(dirs)}
    for _ in range(4):
        code = stub_code(sb.start, slay, rain_modes, weather_byte)
        n = len(code.bytes())
        new = dict(slay)
        new["copydir"] = _align(sb.start + n)
        new["banktab"] = new["copydir"] + 4 * len(dirs)
        new["common"] = _align(new["banktab"] + len(dirs))
        if new == slay:
            break
        slay = new
    else:
        raise PatchError("the storm stub's layout did not settle")
    lists, pos = {}, slay["common"] + len(common_blob)
    for e in range(len(dirs)):
        lists[e] = pos
        pos += len(per_entry[e])
    if pos > sb.start + sb.size:
        raise PatchError(f"the storm stub and its lists ({pos - sb.start} bytes) do not fit their block ({sb.size})")
    stub = code.bytes()
    blob = (stub + b"\xff" * (slay["copydir"] - sb.start - len(stub)) + struct.pack(f"<{len(dirs)}I", *(lists[e] for e in range(len(dirs))))
            + bytes((d.bank << 4) | 1 for d in dirs))
    blob += b"\xff" * (slay["common"] - sb.start - len(blob)) + common_blob + b"".join(per_entry[e] for e in range(len(dirs)))
    _put(parts, "boot", sb.start, blob)
    hb = Block(HOOK_SITE)
    hb.emit("jsr abs", sb.start)
    call = hb.bytes()
    parts["boot"][HOOK_SITE - V60_BOOT:HOOK_SITE - V60_BOOT + len(call)] = call
    for b, new in hook_sites:                           # the modules' sites (checked above)
        region, base = ("boot", V60_BOOT) if b.space == "boot site" else ("program", V60_PROGRAM)
        parts[region][b.start - base:b.start - base + b.size] = new
    out = dataclasses.replace(rs, program=bytes(parts["program"]), boot=bytes(parts["boot"]), data=bytes(parts["data"]),
                              polygons=bytes(parts["polygons"]))
    report = {"layout": lay, "image": (IMAGE[0], len(image)), "stub": (sb.start, pos - sb.start),
              "lists": lists, "common": slay["common"], "copydir": slay["copydir"], "banktab": slay["banktab"],
              "stub_labels": {k: code.addr(k) for k in ("wet", "release", "load", "copy_list")},
              "course_data_end": a, "data_end": lay.carrier["data_end"], "static_data_end": static_end, "rom": rom_used}
    return out, report
