"""Phase 28: the frame's draw budget, raised to 10 500 in the ten-course build (`install_directory` calls `patch_budget`).

The game counts the polygon records it sends to the display list in a frame (the long word 0x5011a0, reset every frame) against a
budget, the long word 0x5011b0. The object-list walker (0xff848a for lists drawn above the HUD's layer, 0xff84a2 for the others)
compares the count with the budget before each list and returns without drawing it when the count is already above it: the list
that crosses the budget is drawn whole and every later list of that frame is skipped. The scenery cells come last in the frame
(0xff8450, in the 0x501cc0 order: own cell, the 8 around, the 16 outer), so a frame over the budget loses its far cells for that
frame. Sega's own courses pass 5 500 on 3-22 % of race frames; the converted Diablo Canyon, Metropolis and Pacific Coast near their
starts (docs/spike/2026-11-phase28-polygons-recon.md §2-3).

Who reads 0x5011b0 (the original boot listing, and a byte search of the boot and program ROMs for the absolute address, which finds
these five readers and the two writers below and nothing else; docs/spike/2026-11-phase28-draw-budget-findings.md §4):
- 0xff848a / 0xff84a2: the walker's compare above;
- 0xff5e33: the character path draws an object with flag bit 0x1a only while the count is at most the budget less 150;
- 0xff8571 / 0xff862c: every 0x01 (or 0x10, 0x11) display-list command carries the budget as its size word. The size is a cap on
  the records drawn from that object: MAME's `push_object` stops at the object's own end record (type 0) or after `size`
  records, whichever comes first, and refuses a size of 0x1000000 or more. No object reaches 5 500 records (the converter caps a
  cell there: polyrom.MAX_RECORDS), so a larger size draws the same records.
Nothing sizes a buffer or a loop by the budget: the display list grows by a fixed number of entries an object, whatever its
records.

The two writers (0xfe1100..0xfe11df, boot, once):
- 0xfe10e5: with the link setting 0x40dc8c at 0 (a standalone cabinet) the boot sets the flag 0x501a35 to 1 and goes straight to
  BUDGET_SITE: the budget is 5 500;
- otherwise (a linked cabinet) 0xfe6c5f initialises the comm board (writing the link mode to its byte 0xb00001), the flag is 1
  when that byte still reads non-zero, then BUDGET_SITE sets 5 500 and, with the flag 0, LINK_SITE overwrites it with 5 000.
LINK_SITE is linked play only; it is raised by the same amount (5 000 + 5 000 = 10 000) so that a linked cabinet keeps its 500
records less. Linked play was not run.

The value (docs/spike/2026-11-phase28-draw-budget-findings.md §3): with the budget out of the way the originals' busiest frames ask
for up to 9 771 records before their last list (Big Forest, the highest of five runs; the converted courses at most 6 948, a pit
stop on Metropolis); 10 500 leaves every measured frame drawing every list with a margin of 729 records (7.5 %). The session lead
recommended 10 500 and Pascal answered "Ok". The originals then draw far scenery that the arcade dropped on busy frames
(docs/deviations.md).
"""
from __future__ import annotations

from vrtools.arcade.codepatch import patch_span
from vrtools.arcade.patch import PatchError
from vrtools.arcade.romset import V60_BOOT, RomSet

ORIGINAL_BUDGET = 5500                 # 0xfe11bd: mov.w #157C, 5011B0 (the standalone cabinet's)
ORIGINAL_LINK_BUDGET = 5000            # 0xfe11d3: mov.w #1388, 5011B0 (a linked cabinet whose comm board reads 0 at 0xb00001)
LINK_OFFSET = ORIGINAL_BUDGET - ORIGINAL_LINK_BUDGET      # a linked cabinet's budget stays 500 records below
FRAME_BUDGET = 10_500                  # Phase 28: Pascal's "Ok" to the lead's recommendation (findings §3)
LINK_FRAME_BUDGET = FRAME_BUDGET - LINK_OFFSET            # 10 000: the game's 5 000 raised by the same 5 000 (linked play not run)
MAX_BUDGET = 0xFFFFFF                  # MAME's push_object ignores an object whose size word is 0x1000000 or more
BUDGET_CELL = 0x5011B0
BUDGET_SITE, LINK_SITE = 0xFE11BD, 0xFE11D3
SITE_LEN = 12                          # 2d 80 f4 <imm32> f3 <abs32>: mov.w #imm, abs
IMM_OFFSET = 3                         # the immediate's four bytes; the only bytes patched
BUDGET_SITES = ((BUDGET_SITE, ORIGINAL_BUDGET), (LINK_SITE, ORIGINAL_LINK_BUDGET))


def site_pattern(value: int) -> bytes:
    """`mov.w #value, 5011B0` as the boot ROM encodes it at both sites."""
    return bytes.fromhex("2d80f4") + value.to_bytes(4, "little") + b"\xf3" + BUDGET_CELL.to_bytes(4, "little")


def patch_budget(rs: RomSet, budget: int = FRAME_BUDGET) -> None:
    """Both sites' immediates in place: `budget` at BUDGET_SITE, `budget` less LINK_OFFSET at LINK_SITE. PatchError when a site's
    twelve bytes are not the original instruction (naming the site), or when `budget` is outside ORIGINAL_BUDGET..MAX_BUDGET."""
    if not ORIGINAL_BUDGET <= budget <= MAX_BUDGET:
        raise PatchError(f"draw budget {budget} is outside {ORIGINAL_BUDGET}..{MAX_BUDGET}")
    for site, original in BUDGET_SITES:                    # both checked before either is written
        have = rs.boot[site - V60_BOOT:site - V60_BOOT + SITE_LEN]
        if have != site_pattern(original):
            raise PatchError(f"draw budget site at {site:#x} is not the expected sequence: {have.hex()} "
                             f"(expected {site_pattern(original).hex()})")
    for site, original in BUDGET_SITES:
        patch_span(rs, site + IMM_OFFSET, (budget - (ORIGINAL_BUDGET - original)).to_bytes(4, "little"), 4)
