"""Weather stage 6: the storm's sound (spec 5.6). Two halves: the SOUND BOARD (generated samples in the two sample ROMs, five new
sound numbers and four small patches in the 68000 sound program; `install_board`) and the V60's TRIGGERS (a storm module on the
carrier that sends the board one word at each edge of the rain and one word a lightning strike; `module`). The stage's plan:
docs/superpowers/plans/2026-11-18-weather-stage-6-sound.md. Ported from the joined prototype (branch `spike70-storm` at 91ad73f:
`spike/p66_sound.py` with spike 75's thunder level, `spike/p70_storm.py`'s `sound_code`, spike 72's trigger), rewritten; the samples
come from weather/thunder_gen.py. With SoundTune() the two sample ROMs equal out/p75storm's byte for byte and the program equals it
but for four ranges (fix round 2's timing patch, patch 4 and the reset in place: the board's ticks are v0.3's; the session lead's
ruling replacing ruling A; tests/test_weather_sound.py P75_PROGRAM_DIFF lists them).

THE CONTRACT (the words the V60 sends; the game's own sound queue, entry 0xffa246 with R0 the word)
  B074  thunder, close     after a 0.3 s wait: the crack (chip 2 voice 0x14, sample 110, note 0x30) and the rumble with its boom
                           (chip 1 voice 0x15, sample 113, note 0x1c), both at full level less SoundTune.thunder_db
  B075  thunder, medium    after 0.6 s: the same two samples 2 semitones lower and 0.75 dB quieter
  B076  thunder, distant   after 0.9 s: the rumble from 0.6 s in (sample 114, past its boom), 3 semitones lower, swelling in over
                           ~0.7 s to full level less thunder_db; no crack
  B077  rain on            the 2 s rain loop (chip 2 voice 0x19, sample 115, note 0x2c) fading in (~0.4 s) to SoundTune.rain_db,
                           held for good (its track ties the note for 10 minutes, then re-keys it once)
  B078  rain off           fades the rain out (~0.5 s) and keys it off; a thunder already sounding finishes its sample (its track
                           keys the rumble off 363 ticks after its note, the distant one 392: 6.52 s and 7.04 s at the measured
                           tick of 17.957 ms), as the prototype the owner approved
  C201 / C200 (the game's own tunnel words) also fade the rain out (~0.45 s) / back to its level (~0.9 s) when it plays
  8100 (the game's own sound reset) also keys off our three voices and clears the duck: nothing of ours survives it
  Under a thunder every other sample voice (engine, music, effects, rain) is pulled down by SoundTune.duck_db (the FM parts are not)
  for about 1.2 s, from 4 ticks before the crack, back up 0.375 dB a tick.
Voices: chip 2 voices 0x14 and 0x19 (no track of the game names them), chip 1 voice 0x15 (command B021's, never seen sent in a race).
Work areas 0xf00f80, 0xf01000, 0xf01080 (named by no header or instruction of the game); the duck's state at 0xf01400. A tick of
the sound program is 17.9 ms. A thunder word sent again while one plays restarts it.

THE TRIGGERS (V60; the storm module `sound`, the last in the frame order: after the rain, and after lightning at the join)
  The carrier calls its `frame` on every SHOW pass (SWITCH 1: a RAIN race's modes, inside the scenery call). THE TRIGGER IS EXEMPT
  FROM THE GUARD (the join's round 2, J1, the session lead's ruling: it is the storm's cheapest unit and the only one whose lateness
  is heard): on a pass the guard finds late (the vblank count moved) it counts the pass in its `late` cell ("sent on a late pass")
  and does its work all the same, so every word goes on the pass it is due; the carrier's contract names it as an allowed unguarded
  unit with its measured cost (carrier.SOUND_TRIGGER_US). Then:
  the rain is wanted in the countdown and the race (SOUND_MODES 0x12-0x14): RAIN ON when wanted and not sent, RAIN OFF when not
  wanted and RAIN ON was the last sent (the finish, 0x19, and the time over's next mode); the thunder: lightning's `strike_seq` (its
  low byte) differing from the last seen is taken as seen and, while the rain is wanted, sends one word by `strike_band` (1 close,
  2 medium, 3 distant; another value nothing). It relies on `strike_seq` changing only, and reads `strike_band` on the pass where it
  sees that change (since J1 the strike's first pass itself; the rule below stays, harmless): LIGHTNING MUST HOLD `strike_band`
  UNCHANGED FROM A STRIKE'S FIRST PASS UNTIL ITS NEXT STRIKE'S FIRST PASS (the interface as amended, fix round 1). A strike begun
  under cover counts like any other (the sky's flash is kept and the thunder heard the same, spec 5.4): `strike_seq` + 1 and its
  band; only an attempt aborted for want of a valid place for the bolt leaves both cells untouched, and sends nothing. Nothing of it runs outside the scenery call: in mode 0x1d and in the test menu entered
  from a RAIN race, where SWITCH stays 1, it does not run at all; nothing on the sound board reads SWITCH. It has no `release`: the
  board's state ends at RAIN OFF or at the game's reset 8100 (time over, the test switch, a reset, the attract), on every path.
  Its cells (zeroed at each load): rain (byte: 1 while RAIN ON is the last rain word sent), seen (byte), nrain, nthunder, late
  (words: rain words sent, thunder words sent, passes it ran on late: sent on a late pass)."""
from __future__ import annotations

import dataclasses
import struct

from vrtools.arcade.patch import PatchError
from vrtools.arcade.romset import RomSet
from vrtools.arcade.v60asm import Block
from vrtools.arcade.weather import carrier, thunder_gen
from vrtools.arcade.weather.tune import SoundTune

# ---- the contract -----------------------------------------------------------------------------------------------------------------
WORDS = {"close": 0xB074, "medium": 0xB075, "distant": 0xB076, "rain_on": 0xB077, "rain_off": 0xB078}
BAND_WORDS = ("close", "medium", "distant")             # strike_band 1, 2, 3
NOOP_WORD = 0xB062                                      # a sound number whose handler does nothing (the tests' control: the same
                                                        # queue turns without the thunder)
SOUND_MODES = (0x12, 0x13, 0x14)                        # the countdown and the race: the rain bed's modes
QUEUE = 0xFFA246                                        # the game's sound queue without the race gate: R0 the word; keeps R1

# ---- the sound board (MAME's segam1audio: a 68000 at 10 MHz, two MultiPCM chips, a YM3438) -----------------------------------------
CRACK_V, RAIN_V, RUMBLE_V = 0x34, 0x39, 0x15            # voice bytes: bit 5 chip 2, bits 0-4 the chip's voice selector
CRACK_WA, RUMBLE_WA, RAIN_WA = 0xF00F80, 0xF01000, 0xF01080
DUCK = 0xF01400                                         # delay.w, hold.w, current.b, target.b, pending.b
DUCK_HOLD_TICKS, DUCK_ATTACK, DUCK_LEAD = 67, 4, 4      # hold ~1.2 s at depth; 4 steps (1.5 dB) a tick down; from 4 ticks before
CRACK_ENTRY, RAIN_ENTRY = 110, 115                      # chip 2's sample table (free entries)
RUMBLE_ENTRY, DISTANT_ENTRY = 113, 114                  # chip 1's
DISTANT_FROM_S = 0.6                                    # the distant rumble starts this far into the rumble's data
FREE_PROG, FREE_SAMPLES = 0xAC00, 0x600                 # the program's erased run (from 0xabfc), each sample ROM's (to 0x1ffff)
# the program's own routines and cells the patches call or read (the original's addresses)
TABLE, MULTI, NOOP = 0x58A, 0x0A5E, 0x0588              # the sound-number table (8 bytes: header, handler), the multi-voice
                                                        # handler, the handler that does nothing
RESET_A, RESET_B, RESET_TAIL = 0x117E, 0x19D4, 0x1AEC   # the reset 8100's two calls and its tail
KEY_OFF = 0x16E6                                        # keys off the voice in D7
TRACK_LEVEL = 0x1670                                    # writes the track's (A5) level to its voice
ENGINE, FM_TRACKS = 0x1C42, 0x0C9E                      # the main loop's engine and FM calls (at 0x26e)
LEVEL_CHIP1, LEVEL_CHIP2 = 0x17FA, 0x182A               # the register write's two paths (D5 register, D6 value, D7 voice byte)
TUNNEL_BIT, TUNNEL_TAIL = 0xF00012, 0x0562              # the tunnel word's bit (bit 1) and its original "off" path
WORK_AREAS = 0xF00400                                   # 56 sample track work areas of 0x40 bytes
# work area fields (the program's track interpreter): +0 bit 7 active, +8 level byte, +0x19 bit 7 fading out / bit 2 fading in,
# +0x2d the fade's rate, +0x2e its counter
WA_LEVEL, WA_FLAGS, WA_RATE, WA_COUNT = 0x08, 0x19, 0x2D, 0x2E


# ---- a small 68000 encoder (only the instructions the patches use; big-endian words) ---------------------------------------------
class M68k:
    """Instructions at `base`; labels and branches resolved by `bytes()`."""
    CC = {"ra": 0x0, "sr": 0x1, "ls": 0x3, "cc": 0x4, "cs": 0x5, "ne": 0x6, "eq": 0x7}

    def __init__(self, base: int):
        self.base, self.out, self.labels, self.fix = base, bytearray(), {}, []

    def here(self) -> int:
        return self.base + len(self.out)

    def label(self, name: str) -> None:
        self.labels[name] = self.here()

    def _w(self, *words: int) -> None:
        for x in words:
            self.out += struct.pack(">H", x & 0xFFFF)

    def _l(self, x: int) -> None:
        self.out += struct.pack(">I", x & 0xFFFFFFFF)

    def raw(self, data: bytes) -> None:
        self.out += data

    # flow
    def b(self, cc: str, target) -> None:
        """Bcc.w (cc "ra": BRA, "sr": BSR) to a label or an address."""
        self.fix.append((len(self.out), target, 16))
        self._w(0x6000 | self.CC[cc] << 8, 0)

    def bs(self, cc: str, target) -> None:
        """Bcc.s (an 8-bit displacement)."""
        self.fix.append((len(self.out), target, 8))
        self._w(0x6000 | self.CC[cc] << 8)

    def dbra(self, d: int, target) -> None:
        self.fix.append((len(self.out), target, 16))
        self._w(0x51C8 | d, 0)

    def jsr(self, a: int) -> None:
        self._w(0x4EB9); self._l(a)

    def jmp(self, a: int) -> None:
        self._w(0x4EF9); self._l(a)

    def rts(self) -> None:
        self._w(0x4E75)

    def nop(self) -> None:
        self._w(0x4E71)

    # moves
    def move_b_imm_d(self, v: int, d: int) -> None:
        self._w(0x103C | d << 9, v & 0xFF)

    def move_w_imm_d(self, v: int, d: int) -> None:
        self._w(0x303C | d << 9, v)

    def move_b_imm_abs(self, v: int, a: int) -> None:
        self._w(0x13FC, v & 0xFF); self._l(a)

    def move_w_imm_abs(self, v: int, a: int) -> None:
        self._w(0x33FC, v); self._l(a)

    def move_b_abs_abs(self, src: int, dst: int) -> None:
        self._w(0x13F9); self._l(src); self._l(dst)

    def move_b_abs_d(self, a: int, d: int) -> None:
        self._w(0x1039 | d << 9); self._l(a)

    def move_b_d_abs(self, d: int, a: int) -> None:
        self._w(0x13C0 | d); self._l(a)

    def move_b_disp_d(self, disp: int, an: int, d: int) -> None:
        self._w(0x1028 | d << 9 | an, disp)

    def push_w(self, d: int) -> None:
        self._w(0x3F00 | d)                             # move.w Dn, -(A7)

    def pop_w(self, d: int) -> None:
        self._w(0x301F | d << 9)                        # move.w (A7)+, Dn

    def lea_abs(self, a: int, an: int) -> None:
        self._w(0x41F9 | an << 9); self._l(a)

    # arithmetic and tests
    def clr_l_abs(self, a: int) -> None:
        self._w(0x42B9); self._l(a)

    def clr_b_abs(self, a: int) -> None:
        self._w(0x4239); self._l(a)

    def tst_b_abs(self, a: int) -> None:
        self._w(0x4A39); self._l(a)

    def tst_w_abs(self, a: int) -> None:
        self._w(0x4A79); self._l(a)

    def subq_w_abs(self, q: int, a: int) -> None:
        self._w(0x5179 | (q & 7) << 9); self._l(a)

    def subq_b_d(self, q: int, d: int) -> None:
        self._w(0x5100 | (q & 7) << 9 | d)

    def addq_b_d(self, q: int, d: int) -> None:
        self._w(0x5000 | (q & 7) << 9 | d)

    def add_b_dd(self, src: int, dst: int) -> None:
        self._w(0xD000 | dst << 9 | src)

    def adda_w_imm(self, v: int, an: int) -> None:
        self._w(0xD0FC | an << 9, v)

    def cmp_b_abs_d(self, a: int, d: int) -> None:
        self._w(0xB039 | d << 9); self._l(a)

    def cmpi_b_d(self, v: int, d: int) -> None:
        self._w(0x0C00 | d, v & 0xFF)

    def andi_b_d(self, v: int, d: int) -> None:
        self._w(0x0200 | d, v & 0xFF)

    def btst_d(self, n: int, d: int) -> None:
        self._w(0x0800 | d, n)

    def btst_ind(self, n: int, an: int) -> None:
        self._w(0x0810 | an, n)

    def btst_abs(self, n: int, a: int) -> None:
        self._w(0x0839, n); self._l(a)

    def bset_abs(self, n: int, a: int) -> None:
        self._w(0x08F9, n); self._l(a)

    def bclr_abs(self, n: int, a: int) -> None:
        self._w(0x08B9, n); self._l(a)

    def bytes(self) -> bytes:
        out = bytearray(self.out)
        for at, target, bits in self.fix:
            to = self.labels[target] if isinstance(target, str) else target
            d = to - (self.base + at + 2)
            if bits == 8:
                if not (-128 <= d < 128) or d in (0, -1):
                    raise PatchError(f"68000 short branch at {self.base + at:#x} to {to:#x} out of reach")
                out[at + 1] = d & 0xFF
            else:
                if not -32768 <= d < 32768:
                    raise PatchError(f"68000 branch at {self.base + at:#x} to {to:#x} out of reach")
                out[at + 2:at + 4] = struct.pack(">h", d)
        return bytes(out)


D0, D4, D5, D6, D7, A5 = 0, 4, 5, 6, 7, 5


def _code(base: int, fill) -> bytes:
    m = M68k(base)
    fill(m)
    return m.bytes()


# ---- the program's pieces ------------------------------------------------------------------------------------------------------------
def reset_routine(m: M68k) -> None:
    """Patch 1: the reset 8100 (its `bsr 117e; bsr 19d4; bra 1aec` at 0x544: the first call stays in place, so the YM3438's timer A,
    which 0x117e reloads, restarts at v0.3's moment (fix round 2); the `bsr 19d4; bra 1aec` at 0x548 become a jump here): the second
    call, our three voices keyed off (the game's reset keys off only chip voices 0-6 and 8-14, so a looped rain would sound on), the
    duck cleared, the tail. Three nops after the tail's jump (dead) keep the routine its former length, so every other piece and
    every address in the sound-number table stay where out/p75storm has them."""
    m.jsr(RESET_B)
    for v in (RUMBLE_V, CRACK_V, RAIN_V):
        m.move_b_imm_d(v, D7)
        m.jsr(KEY_OFF)
    m.clr_l_abs(DUCK)
    m.clr_l_abs(DUCK + 4)
    m.jmp(RESET_TAIL)
    for _ in range(3):
        m.nop()


# The power-on initialisation (fix round 2, the session lead's ruling replacing ruling A): 0x191a writes 168 registers of both chips
# through the register write at 0x17f2 before 0x117e starts the YM3438's timer A, which sets the phase of every tick for good (a reset
# 8100 reloads it a fixed time after a tick). Through the level hook (patch 3a) those writes cost 8 288 cycles more (each non-level
# write 38 on chip 1, 42 on chip 2; each level write 66 / 70; 112 + 56 writes), so the whole timeline ran 828.8 us behind v0.3's and
# commands near a tick boundary were read a tick apart (effects on other voices, cut short or run longer). Patch 4 gives the time
# back before the hook is reached: the boot's RAM clear (0x982..0x993, 180 050 cycles: lea; move.w #$1ff6, d4; 8 183 x move.w #0,
# (a0)+; dbra) becomes a jump to `clear_routine`, which clears the same 0x3fee bytes by longs and then waits exactly the rest.
INIT_SURPLUS_CYCLES = 8288              # the hook's cost on the 168 writes before the timer starts (measured as 828.8 us at 10 MHz)
CLEAR_ORIGINAL_CYCLES = 12 + 8 + 8183 * 12 + 8182 * 10 + 14          # lea abs.l; move.w #imm,d4; the loop (dbra taken 10, out 14)
CLEAR_FIXED_CYCLES = 12 + 12 + 4 + 8 + (4091 * 12 + 4090 * 10 + 14) + 8 + 10     # jmp at the site; lea; moveq; move.w; the long loop;
                                                                                    # move.w d0,(a0)+; jmp $994.w
INIT_CLEAR, INIT_CLEAR_END, INIT_CLEAR_BYTES = 0x982, 0x994, 0x3FEE


def clear_pad() -> tuple[int, int]:
    """(n, k) of the clear routine's wait, `move.w #n, d4; dbra d4, *` (8 + 10 n + 14 cycles) and k nops (4 each): together the
    original clear's cycles less the long loop's and INIT_SURPLUS_CYCLES."""
    rest = CLEAR_ORIGINAL_CYCLES - CLEAR_FIXED_CYCLES - INIT_SURPLUS_CYCLES - 22
    for k in range(5):
        if (rest - 4 * k) % 10 == 0 and rest - 4 * k >= 0:
            return (rest - 4 * k) // 10, k
    raise ValueError(f"the clear routine's wait cannot make {rest} cycles")


def clear_routine(m: M68k) -> None:
    """Patch 4: the boot's RAM clear (0xf00000..0xf03fed, as 0x982's loop) by longs, then the wait (`clear_pad`), then 0x994. D0 is 0
    (the reset clears it; moveq keeps it so), D4 ends 0xffff and A0 at 0xf03fee as the original's loop leaves them."""
    n, k = clear_pad()
    m.lea_abs(0xF00000, 0)
    m.raw(bytes.fromhex("7000"))                        # moveq #0, d0
    m.move_w_imm_d(INIT_CLEAR_BYTES // 4 - 1, D4)
    m.label("clr")
    m.raw(bytes.fromhex("20c0"))                        # move.l d0, (a0)+
    m.dbra(D4, "clr")
    m.raw(bytes.fromhex("30c0"))                        # move.w d0, (a0)+
    m.move_w_imm_d(n, D4)
    m.label("wait")
    m.dbra(D4, "wait")
    for _ in range(k):
        m.nop()
    m.raw(bytes.fromhex("4ef8") + INIT_CLEAR_END.to_bytes(2, "big"))     # jmp $994.w


def tunnel_routine(m: M68k) -> None:
    """Patch 2: the tunnel word C2xx (its handler's `andi.b #1, d0; beq` at 0x550 becomes a jump here) does what it did (the tunnel
    bit, which the engine's voices read) and, while the rain's track is active, C201 starts the program's own fade-out on it (rate 0:
    +8 a tick) and C200 its fade-in back to the level it was started at (rate 1: -8 every second tick)."""
    m.andi_b_d(1, D0)
    m.b("eq", "off")
    m.bset_abs(1, TUNNEL_BIT)
    m.btst_abs(7, RAIN_WA)
    m.b("eq", "on_done")
    m.move_b_imm_abs(0, RAIN_WA + WA_RATE)
    m.move_b_imm_abs(0, RAIN_WA + WA_COUNT)
    m.bclr_abs(2, RAIN_WA + WA_FLAGS)
    m.bset_abs(7, RAIN_WA + WA_FLAGS)
    m.label("on_done")
    m.rts()
    m.label("off")
    m.bclr_abs(1, TUNNEL_BIT)
    m.btst_abs(7, RAIN_WA)
    m.b("eq", "off_done")
    m.move_b_imm_abs(1, RAIN_WA + WA_RATE)
    m.move_b_imm_abs(0, RAIN_WA + WA_COUNT)
    m.bclr_abs(7, RAIN_WA + WA_FLAGS)
    m.bset_abs(2, RAIN_WA + WA_FLAGS)
    m.label("off_done")
    m.rts()


def level_hook(m: M68k) -> None:
    """Patch 3a: the register write (its `btst #5, d7; bne` at 0x17f2 becomes a jump here): a level write (register 5) of any voice
    but the crack's and the rumble's, while the duck is down, gets the duck added (twice its steps on the register byte, bit 0 kept;
    0xfe at most); then the original two paths by the chip bit."""
    m.cmpi_b_d(5, D5)
    m.b("ne", "orig")
    m.tst_b_abs(DUCK + 4)
    m.b("eq", "orig")
    m.cmpi_b_d(CRACK_V, D7)
    m.b("eq", "orig")
    m.cmpi_b_d(RUMBLE_V, D7)
    m.b("eq", "orig")
    m.push_w(D0)
    m.move_b_abs_d(DUCK + 4, D0)
    m.add_b_dd(D0, D0)
    m.add_b_dd(D0, D6)
    m.bs("cc", "fits")
    m.move_b_imm_d(0xFE, D6)
    m.label("fits")
    m.pop_w(D0)
    m.label("orig")
    m.btst_d(5, D7)
    m.bs("ne", "chip2")
    m.jmp(LEVEL_CHIP1)
    m.label("chip2")
    m.jmp(LEVEL_CHIP2)


def duck_routine(m: M68k) -> None:
    """Patch 3b, once a tick (the main loop's `bsr 1c42; bsr c9e` at 0x26e becomes `jsr` here and a nop): the duck's delay runs out
    -> its target is the armed depth and the hold starts; the hold runs out -> the target is 0; the current depth moves toward the
    target (DUCK_ATTACK steps a tick down, one step a tick back up) and, when it moved, every active sample track but the crack's and
    the rumble's has its level written again; then the two calls."""
    m.tst_w_abs(DUCK)
    m.b("eq", "l1")
    m.subq_w_abs(1, DUCK)
    m.b("ne", "l1")
    m.move_b_abs_abs(DUCK + 6, DUCK + 5)
    m.move_w_imm_abs(DUCK_HOLD_TICKS, DUCK + 2)
    m.label("l1")
    m.tst_w_abs(DUCK + 2)
    m.b("eq", "l2")
    m.subq_w_abs(1, DUCK + 2)
    m.b("ne", "l2")
    m.clr_b_abs(DUCK + 5)
    m.label("l2")
    m.move_b_abs_d(DUCK + 4, D0)
    m.cmp_b_abs_d(DUCK + 5, D0)
    m.b("eq", "done")
    m.b("cs", "up")
    m.subq_b_d(1, D0)
    m.b("ra", "set")
    m.label("up")
    m.addq_b_d(DUCK_ATTACK, D0)
    m.cmp_b_abs_d(DUCK + 5, D0)
    m.bs("ls", "set")
    m.move_b_abs_d(DUCK + 5, D0)
    m.label("set")
    m.move_b_d_abs(D0, DUCK + 4)
    m.lea_abs(WORK_AREAS, A5)
    m.move_w_imm_d(0x37, D4)
    m.label("rl")
    m.btst_ind(7, A5)
    m.b("eq", "next")
    m.move_b_disp_d(1, A5, D7)
    m.cmpi_b_d(CRACK_V, D7)
    m.b("eq", "next")
    m.cmpi_b_d(RUMBLE_V, D7)
    m.b("eq", "next")
    m.btst_d(7, D7)
    m.b("ne", "next")
    m.jsr(TRACK_LEVEL)
    m.label("next")
    m.adda_w_imm(0x40, A5)
    m.dbra(D4, "rl")
    m.label("done")
    m.jsr(ENGINE)
    m.jsr(FM_TRACKS)
    m.rts()


def thunder_handler(m: M68k, delay_ticks: int, steps: int) -> None:
    """Patch 3c: a thunder number's handler arms the duck (its delay, DUCK_LEAD ticks before the crack, and its depth), then plays
    the number's tracks with the multi-voice handler."""
    m.move_w_imm_abs(max(1, delay_ticks - DUCK_LEAD), DUCK)
    m.move_b_imm_abs(steps, DUCK + 6)
    m.jmp(MULTI)


def command(at: int, tracks: list[tuple[int, int, int, bytes | int]]) -> bytes:
    """A sound number's header and track bodies at `at`: the track count, a byte the program copies and never reads (0xef), then per
    track its work area, 0x80 (active), the voice byte, the body's address, 0x40 (call stack), 0 (transpose), the level byte, 1 (the
    first tick); then the bodies. A track whose body is an int points at that address (a body shared or placed elsewhere)."""
    hdr, body = bytearray([len(tracks), 0xEF]), bytearray()
    tp = at + 2 + 14 * len(tracks)
    for wa, voice, level, tb in tracks:
        ptr = tb if isinstance(tb, int) else tp + len(body)
        hdr += struct.pack(">I", wa) + bytes([0x80, voice]) + struct.pack(">I", ptr) + bytes([0x40, 0, level, 1])
        if not isinstance(tb, int):
            body += tb
    return bytes(hdr + body)


# track bytes: a note is a byte below 0xe0 then its length in ticks; e3 n waits n ticks (a tie after a note); f1 s sample; e2 v level;
# fc from to rate fade-in; f2 rate fade-out; ea hi lo jump; e4 end (key off). (Never ed / f4: their handlers leave the reader a byte
# behind.)
def _wait(n: int) -> bytes:
    return bytes([0xE3, n])


def crack_track(note: int, level: int, wait: int) -> bytes:
    return _wait(wait) + bytes([0xF1, CRACK_ENTRY, 0xE2, level, note, 0x18, 0xE4])


def rumble_track(note: int, level: int, wait: int) -> bytes:
    return _wait(wait) + bytes([0xF1, RUMBLE_ENTRY, 0xE2, level, note, 0xFF, 0xE3, 0x6C, 0xE4])


def distant_track(level: int, wait: int) -> bytes:
    return _wait(wait) + bytes([0xF1, DISTANT_ENTRY, 0xFC, 0x50 + level, level, 0x03, 0x19, 0xFF, 0xE3, 0x89, 0xE4])


FADE_OUT = bytes([0xF2, 0x00, 0xE3, 0x24, 0xE4])        # +8 a tick to silence, 36 ticks more, key off


def sample_entry(start: int, points: int, loop: int) -> bytes:
    """A 12-byte MultiPCM sample header: 12-bit (bit 22 of the start), start, loop point, minus the length; the envelope attack 15,
    release 15 (immediate), no LFO."""
    return (bytes([0x40 | (start >> 16 & 0x3F), start >> 8 & 0xFF, start & 0xFF]) + struct.pack(">HH", loop, 0x10000 - points)
            + bytes([0, 0xF0, 0, 0x0F, 0]))


# ---- the board's install ----------------------------------------------------------------------------------------------------------------
def _original_sites() -> dict[str, bytes]:
    """The original instructions at the code sites, as instructions (checked in the set before anything is written)."""
    def at(base, fill):
        return _code(base, fill)
    return {"sound main loop": at(0x26E, lambda m: (m.b("sr", ENGINE), m.b("sr", FM_TRACKS))),
            "sound reset": at(0x548, lambda m: (m.b("sr", RESET_B), m.b("ra", RESET_TAIL))),
            "sound init clear": at(INIT_CLEAR, lambda m: (m.lea_abs(0xF00000, 0), m.move_w_imm_d(0x1FF6, D4))),
            "sound tunnel word": at(0x550, lambda m: (m.andi_b_d(1, D0), m.b("eq", TUNNEL_TAIL))),
            "sound level write": at(0x17F2, lambda m: (m.btst_d(5, D7), m.b("ne", LEVEL_CHIP2)))}


def _original_fallthrough() -> tuple[int, bytes]:
    """The tunnel word's handler after the replaced bytes (0x558..0x56b: `bset #1, 0xf00012; rts` and, at 0x562, `bclr #1, 0xf00012;
    rts`): not written, but `tunnel_routine` re-implements it, so it is checked as the original."""
    return 0x558, _code(0x558, lambda m: (m.bset_abs(1, TUNNEL_BIT), m.rts(), m.bclr_abs(1, TUNNEL_BIT), m.rts()))


def _original_reset_call() -> tuple[int, bytes]:
    """The reset 8100's first call (0x544: `bsr 117e`): not written, but the jump at 0x548 depends on it running first (it reloads
    the YM3438's timer A), so it is checked as the original."""
    return 0x544, _code(0x544, lambda m: m.b("sr", RESET_A))


def _original_clear_loop() -> tuple[int, bytes]:
    """The RAM clear's loop after the replaced bytes (0x98c..0x993: `move.w #0, (a0)+; dbra d4, 0x98c`): not written, but
    `clear_routine` re-implements it (and its cycle count), so it is checked as the original."""
    return 0x98C, bytes.fromhex("30fc0000") + _code(0x990, lambda m: (m.label("top"), m.dbra(D4, 0x98C)))


def board(rs: RomSet, tune: SoundTune) -> tuple[dict, dict]:
    """The three members with the storm's sound, from `rs`'s ({"sound_program", "sound_pcm1", "sound_pcm2"}: bytes), and a report
    (where each piece went, the bytes used). PatchError, before anything is changed, when the set has no sound members, a block of the
    layout is not erased, or a site holds other than its original."""
    from vrtools.arcade.weather import layout
    if rs.sound_program is None or rs.sound_pcm1 is None or rs.sound_pcm2 is None:
        raise PatchError("the set carries no sound members (epr-14870a.7, mpr-14873.32, mpr-14876.4): it was not read from a vr.zip")
    blk = {b.name: b for b in layout.blocks() if b.owner == "sound"}
    for b in blk.values():
        if b.space in layout.ERASED and not layout.erased(rs, b):
            raise PatchError(f"the sound block {b.name!r} ({b.space} {b.start:#x}, {b.size} bytes) is not erased")
    for name, old in _original_sites().items():
        if layout.rom_bytes(rs, blk[name])[:len(old)] != old:
            raise PatchError(f"the sound program's site {name!r} at {blk[name].start:#x}: {layout.rom_bytes(rs, blk[name]).hex()}, "
                             f"expected {old.hex()}")
    for what, (at, old) in (("tunnel handler", _original_fallthrough()), ("RAM clear loop", _original_clear_loop()),
                            ("reset's first call", _original_reset_call())):
        if rs.sound_program[at:at + len(old)] != old:
            raise PatchError(f"the sound program's {what} at {at:#x}: {rs.sound_program[at:at + len(old)].hex()}, expected {old.hex()}")
    numbers = blk["sound numbers"]
    for k, w in enumerate(WORDS.values()):
        ent = TABLE + 8 * ((w & 0x7F) - 1)
        if ent != numbers.start + 8 * k or struct.unpack(">I", rs.sound_program[ent + 4:ent + 8])[0] != NOOP:
            raise PatchError(f"the sound number {w:04X} is in use in this set (its handler is not the no-op {NOOP:#x})")
    for name in ("chip 1 sample table", "chip 2 crack entry", "chip 2 rain entry"):
        b = blk[name]
        data = layout.rom_bytes(rs, b)
        if any(data[k:k + 3] != b"\0\0\0" for k in range(0, b.size, 12)):
            raise PatchError(f"the sample table's {name!r} at {b.start:#x} is in use in this set")
    prog, pcm1, pcm2 = bytearray(rs.sound_program), bytearray(rs.sound_pcm1), bytearray(rs.sound_pcm2)
    s = thunder_gen.samples()
    need2 = ((len(s["crack"].data) + 0xF) & ~0xF) + len(s["rain"].data)
    for name, need in (("chip 2 samples", need2), ("chip 1 samples", len(s["rumble"].data))):
        if need > blk[name].size:
            raise PatchError(f"the sound block {name!r} holds {blk[name].size} bytes, the samples need {need}")
    rep: dict = {}
    # the samples (each 16-aligned after the one before) and their table entries
    crack, rumble, rain = s["crack"], s["rumble"], s["rain"]
    at2 = blk["chip 2 samples"].start
    pcm2[at2:at2 + len(crack.data)] = crack.data
    pcm2[12 * CRACK_ENTRY:12 * CRACK_ENTRY + 12] = sample_entry(at2, crack.points, crack.points - 1)
    rain_at = (at2 + len(crack.data) + 0xF) & ~0xF
    pcm2[rain_at:rain_at + len(rain.data)] = rain.data
    pcm2[12 * RAIN_ENTRY:12 * RAIN_ENTRY + 12] = sample_entry(rain_at, rain.points, 0)
    at1 = blk["chip 1 samples"].start
    pcm1[at1:at1 + len(rumble.data)] = rumble.data
    pcm1[12 * RUMBLE_ENTRY:12 * RUMBLE_ENTRY + 12] = sample_entry(at1, rumble.points, rumble.points - 1)
    off = int(DISTANT_FROM_S * rumble.rate) & ~1                     # an even point: two points in three bytes
    pcm1[12 * DISTANT_ENTRY:12 * DISTANT_ENTRY + 12] = sample_entry(at1 + off // 2 * 3, rumble.points - off, rumble.points - off - 1)
    rep["pcm2"] = {"crack": at2, "rain": rain_at, "used": ((rain_at + len(rain.data) + 0xF) & ~0xF) - at2}
    rep["pcm1"] = {"rumble": at1, "distant": at1 + off // 2 * 3, "used": ((at1 + len(rumble.data) + 0xF) & ~0xF) - at1}
    # the program's pieces, one after the other (even addresses) in the erased run
    code = blk["sound code"]
    p = code.start
    where = {}

    def put(name: str, make) -> int:
        nonlocal p
        blob = make(p) if callable(make) else make
        if p + len(blob) > code.start + code.size:
            raise PatchError(f"the sound program's pieces ({p + len(blob) - code.start} bytes) do not fit their block ({code.size})")
        prog[p:p + len(blob)] = blob
        where[name], p = p, (p + len(blob) + 1) & ~1
        return where[name]
    put("reset", lambda a: _code(a, reset_routine))
    put("tunnel", lambda a: _code(a, tunnel_routine))
    put("level", lambda a: _code(a, level_hook))
    put("duck", lambda a: _code(a, duck_routine))
    handlers = {}
    for k, band in enumerate(BAND_WORDS):
        handlers[band] = put(f"handler {band}", lambda a, k=k: _code(a, lambda m: thunder_handler(m, tune.delay_ticks[k],
                                                                                                      tune.duck_steps[k])))
    if p >= 0x10000:
        raise PatchError("the rain loop's body must lie below 0x10000 (a track's jump takes 16 bits)")
    chain = put("rain loop", lambda a: bytes([rain.note, 0xFF]) + _wait(0xFF) * 132 + bytes([0xEA, a >> 8, a & 0xFF]))
    tk, lv, d = tune.thunder_steps, tune.rain_level, tune.delay_ticks
    if (0xFE - lv) % 8 or (0x7E - lv) % 8:
        raise PatchError(f"the rain level byte {lv:#x}: the program's fades would overshoot and wrap")
    tables = {}

    def cmd(word: str, tracks, handler: int = MULTI) -> None:
        tables[word] = (put(f"number {word}", lambda a: command(a, tracks)), handler)
    cmd("close", [(CRACK_WA, CRACK_V, 1, crack_track(crack.note, tk, d[0])),
                  (RUMBLE_WA, RUMBLE_V, 1, rumble_track(rumble.note, tk, d[0]))], handlers["close"])
    cmd("medium", [(CRACK_WA, CRACK_V, 1, crack_track(crack.note - 2, 0x04 + tk, d[1])),
                   (RUMBLE_WA, RUMBLE_V, 1, rumble_track(rumble.note - 2, 0x04 + tk, d[1]))], handlers["medium"])
    cmd("distant", [(RUMBLE_WA, RUMBLE_V, 1, distant_track(tk, d[2]))], handlers["distant"])
    cmd("rain_on", [(RAIN_WA, RAIN_V, 0x7E, bytes([0xF1, RAIN_ENTRY, 0xFC, 0x7E, lv, 0x01, 0xEA, chain >> 8, chain & 0xFF]))])
    cmd("rain_off", [(RAIN_WA, RAIN_V, lv, FADE_OUT)])
    put("clear", lambda a: _code(a, clear_routine))          # last: the prototype's pieces keep their addresses (fix round 2)
    for k, w in enumerate(WORDS):
        a, handler = tables[w]
        ent = numbers.start + 8 * k
        prog[ent:ent + 8] = struct.pack(">II", a, handler)
    # the code sites (a jump over the first instructions; a displacement word left as it was is dead code)
    def site(name: str, fill) -> None:
        b = blk[name]
        new = _code(b.start, fill)
        prog[b.start:b.start + len(new)] = new
    site("sound main loop", lambda m: (m.jsr(where["duck"]), m.nop()))
    site("sound reset", lambda m: (m.jmp(where["reset"]), m.nop()))
    site("sound init clear", lambda m: (m.jmp(where["clear"]), m.nop(), m.nop()))
    site("sound tunnel word", lambda m: m.jmp(where["tunnel"]))
    site("sound level write", lambda m: m.jmp(where["level"]))
    rep["program"] = {**where, "used": p - code.start}
    return {"sound_program": bytes(prog), "sound_pcm1": bytes(pcm1), "sound_pcm2": bytes(pcm2)}, rep


def install_board(rs: RomSet, tune: SoundTune | None = None) -> RomSet:
    """`rs` with the storm's sound on its sound board (`board`), as a new set."""
    members, _ = board(rs, tune or SoundTune())
    return dataclasses.replace(rs, **members)


# ---- the V60's triggers ---------------------------------------------------------------------------------------------------------------
CELLS = (("rain", 1), ("seen", 1), ("nrain", 4), ("nthunder", 4), ("late", 4))


def trigger_code(lay: carrier.Layout, words: dict | None = None, planted_late: bool = False) -> Block:
    """The module's `frame` (see THE TRIGGERS above). `words`: the words sent (WORDS; a test's control maps the thunder's to
    NOOP_WORD). `planted_late` (tests only): the pass is also counted late when the striking stand-in's cell `late` is 1
    (tests/weather_standins.py), so a test can make a strike's first pass late. A late pass is counted and the work done all the same
    (J1). It changes R0-R2 (the carrier saves them)."""
    w = {**WORDS, **(words or {})}
    c = {n: lay.cell("sound", n) for n, _ in CELLS}
    seq, band = lay.cell("lightning", "strike_seq"), lay.cell("lightning", "strike_band")
    b = Block(lay.code("sound"))
    b.label("frame")
    carrier.emit_guard_time(b, "late")                  # exempt (J1): a late pass is only counted
    if planted_late:
        b.emit("cmp.b imm,abs", 0, lay.cell("lightning", "late"))
        b.branch("bne", "late")
    b.label("work")
    b.emit("mov.w imm,reg", 0, "r1")                    # R1 := the rain wanted (the countdown or the race)
    for md in SOUND_MODES:
        b.emit("cmp.b imm,abs", md, carrier.MODE)
        b.branch("be", "want")
    b.branch("br", "decided")
    b.label("want")
    b.emit("mov.w imm,reg", 1, "r1")
    b.label("decided")
    b.emit("movz.bw abs,reg", c["rain"], "r2")
    b.emit("cmp.w reg,reg", "r1", "r2")
    b.branch("be", "thunder")                           # as sent: nothing to say
    b.emit("mov.b reg,abs", "r1", c["rain"])
    b.emit("mov.w imm,reg", w["rain_off"], "r0")
    b.emit("cmp.w imm,reg", 0, "r1")
    b.branch("be", "rain_send")
    b.emit("mov.w imm,reg", w["rain_on"], "r0")
    b.label("rain_send")
    b.emit("jsr abs", QUEUE)                            # keeps R1
    b.emit("add.w imm,abs", 1, c["nrain"])
    b.label("thunder")
    b.emit("movz.bw abs,reg", seq, "r0")                # lightning's counter, its low byte (any width counting by one)
    b.emit("movz.bw abs,reg", c["seen"], "r2")
    b.emit("cmp.w reg,reg", "r0", "r2")
    b.branch("be", "done")
    b.emit("mov.b reg,abs", "r0", c["seen"])            # a new strike: seen, and heard only while the rain is wanted
    b.emit("cmp.w imm,reg", 0, "r1")
    b.branch("be", "done")
    b.emit("movz.bw abs,reg", band, "r2")
    for k, name in enumerate(BAND_WORDS):
        b.emit("mov.w imm,reg", w[name], "r0")
        b.emit("cmp.w imm,reg", k + 1, "r2")
        b.branch("be", "thunder_send")
    b.branch("br", "done")                              # another band: nothing
    b.label("thunder_send")
    b.emit("jsr abs", QUEUE)
    b.emit("add.w imm,abs", 1, c["nthunder"])
    b.label("done")
    b.emit("rsr")
    b.label("late")
    b.emit("add.w imm,abs", 1, c["late"])               # sent on a late pass: counted, and on with the work
    b.branch("br", "work")
    return b


def module(rs: RomSet | None = None, converted=None, tune=None, words: dict | None = None, planted_late: bool = False) -> carrier.Module:
    """The triggers as a carrier module (carrier._sound_factory hands it `tune`, tune.Tunes' `sound`: the triggers read none of it, the
    bands are the lightning's cell; `rs` and `converted` are not read either). `words`,
    `planted_late`: see trigger_code (tests only)."""
    return carrier.Module(name="sound", code=lambda lay: trigger_code(lay, words, planted_late), cells=CELLS, frame="frame")
