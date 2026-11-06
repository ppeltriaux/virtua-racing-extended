# Phase 11 recon: lanes, the ranking and the parked pairs (31 Oct 2026)

Follows `docs/spike/2026-11-opponents.md` (Phase 10): the field moves on every converted course, but 4–8 cars per
race park for good, often in pairs sharing a road point, and the single-file packs of the Bay Bridge / Acropolis
templates queue behind the slowest car. Formats: `docs/formats/model1-course-tables.md` §15–16.

## What the code does with the car ahead (`0xfec7ab..0xfeca85`)

1. The cars are ranked by road point every frame (`0xfea597`; ties keep the previous rank). Each car knows its
   ranking neighbours (`+0x19c` ahead, `+0x198` behind).
2. For the car ranked ahead, the TGP gives the distance; beyond **7 units nothing happens**.
3. Within 7 units the code looks for a **lane group** at the target line point's segment: the originals pack
   eight narrow collision quads side by side across the road on some stretches (Big Forest road points 79–118
   and 231–293, Acropolis 350–395; Bay Bridge two or three per point on 91 points), consecutive in the segment
   array, and a car's lane is its lap-position quad's index within the group. In a lane group the two cars'
   lanes decide the pass (a lane change read from the lane quad's geometry, command `0x0c00`); outside one, a
   fallback compares speeds.

## Why our fields park

A per-frame trace of a Metropolis race (`fieldtrace.lua` now logs each car's rank and ranking neighbours)
looked at the two parked pairs, and the ranking is **not** what stops the first car of each pair:

- **Car 7** stops at (−195, 228), road point 43–47, 17 s into the race, with a valid target two points ahead,
  full performance and no car within 7 units. Under it there is **no tarmac quad at all**, only verges: its AI
  line runs 7 units off the centreline, and for road points 45–47 the tarmac quads (one per slice, merged) do
  not reach that far — a coverage gap the Phase 8 test never saw (it checks the centreline only). An AI car on
  grass stops dead and never recovers; car 8 then parks behind it.
- **Car 11** stops at (366, −363), road point 267, having crossed a stretch where only verge quads cover its
  line (point 266) and arriving on tarmac that two verge quads overlap **at the same height**. The TGP keeps
  the containing quad nearest the car's height and breaks exact ties for the later list entry — the verge —
  so the car counts as off the road: its lap-position quad stops updating (road point frozen at 264), its
  target (cursor + 2 = 267) is where it stands, and it stops. Car 12 runs into it twenty frames later.

So the parked pairs are tarmac coverage off the centreline and verge-over-tarmac ties, both converter data
(Phase 11's write-up, `2026-11-field-coverage.md`, corrects the second: it is the overlap itself that holds the
car on the verge, not the tie — the originals' verges never overlap their tarmac);
the ranking-and-brake logic (which needs two cars within 7 units) is secondary, and a car with distinct road
points per 10 units is not what the originals rely on here. The single-file queue behind the slowest car and
the field's pace remain the AI-lines item.

## Levers

- **Tarmac coverage across the road**: every point of every AI line (and the width ±10) inside a tarmac quad;
  where a slice's quad falls short (triangles, slivers, bends), grow the quad's side or add a filler quad.
- **Verges below the tarmac plane** by a hair (say 0.3 units): a car on tarmac is then nearer the tarmac's
  height and wins the tie; a car that has driven onto the verge is at the verge's height and keeps it. Phase 8
  reverted a *drop-by-height* rule, not an offset; this is an A/B on the parked-car count.
- **Lane strips** where cars bunch: split the tarmac quads of a stretch into lateral lanes (two or three like
  Bay Bridge, eight like Big Forest's overtaking zones), consecutive in the segment array, so cars side by side
  get distinct lap-position quads and the pass logic has lanes to work with. Budget: a lane strip costs one quad
  (16 words) per lane per merged quad; the start straight's first 300 units at eight lanes is ~5 quads × 8 ×
  16 = 640 words per course; the whole lap at three lanes ~3× today's tarmac. The Phase 10 build leaves 27 084 words (106 KB) of the TGP data ROM free, so lanes on the start straights of all seven courses fit (~4 500 words) and whole-lap lanes do not.
- **Shorter merge runs** where cars bunch (the first 300 units) so cars 10 units apart report distinct points.
- **AI lines** with lateral spread at the start and apex lines in bends (the originals' hand-made lines).
