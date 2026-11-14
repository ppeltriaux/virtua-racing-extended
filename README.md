# Virtua Racing Extended v0.2

Virtua Racing Extended is the 1992 Sega Model 1 arcade Virtua Racing with ten courses: its own three
(Big Forest, Bay Bridge, Acropolis) and the seven the 1995 Saturn port added (Alpine, Amazon Falls,
Diablo Canyon, Metropolis, Pacific Coast, Surfers Oval, Surfers Road). The seven are converted from
the Saturn disc into the arcade game's own data formats and race on the arcade's engine in MAME: its
fifteen opponents, its time limits and checkpoints, its render rate. The three original courses are
untouched, byte for byte. The project page, with videos and screenshots:
https://continuearcade.com/virtua-racing-extended/

This repository is a patch: one command builds the game on your machine from your own copies of the
arcade game and of the Saturn port. It holds none of either (see "What is in the patch").

> **v0.2 is an early release, not a finished one.** All ten courses load and race, with opponents,
> pit lanes, walls, checkpoints, the in-race map and a best-time table per course, and the seven
> converted courses can be raced in reverse, but the tuning and the finish are still being worked on:
> see "Known issues in v0.2" and "Planned".

## What you need

- **Your own copy of the arcade game:** MAME 0.289's `vr` ROM set, `vr.zip` with all 38 files (the
  25 the build reads are checked by size and CRC against MAME 0.289's list; the other 13 must be
  present), with `model1io.zip` and `m1comm.zip` beside it. MAME has one Virtua Racing arcade set for
  every region: the region is an operator setting in the game's test menu (COUNTRY), so there is no
  regional arcade version to choose.
- **Your own copy of the Saturn port:** *Virtua Racing* for the Saturn, **the European release**, as
  a `.cue` with its `.bin` beside it. The US and Japanese discs are not supported yet (see "Planned");
  the build refuses them and names the file it could not find.
- **Python 3.12 or later.**
- **MAME 0.289** to play (and, optionally, to run the build's smoke test).
- Tested on macOS (Apple silicon) with Homebrew's MAME 0.289. Linux should work the same; Windows is
  untried (WSL2 is the safe bet).

None of the game is included here, linked to, or sent on request.

## How to use it

```sh
git clone https://github.com/ppeltriaux/virtua-racing-extended.git
cd virtua-racing-extended
python3 -m venv .venv && .venv/bin/pip install -e .
.venv/bin/vrtools check --roms ~/roms/vr --saturn ~/saturn/"Virtua Racing (Europe).cue" --out ~/vr-extended
.venv/bin/vrtools build --roms ~/roms/vr --saturn ~/saturn/"Virtua Racing (Europe).cue" --out ~/vr-extended --smoke
mame vr -rompath ~/vr-extended
```

- `--roms` is the folder holding `vr.zip`, `model1io.zip` and `m1comm.zip`; `--saturn` the disc's
  `.cue`; `--out` a new folder (it must not be the ROM folder: your files are only read, never
  overwritten). The three default to `$VR_ROMDIR`, `$VR_SATURN_CUE` and `$VR_OUT`.
- `check` names anything wrong with the inputs (a missing file, a file with another CRC than MAME
  0.289's, a disc of another region) and `build` will not start until it passes.
- `build` takes about nine minutes on an Apple silicon Mac. It writes `vr.zip` (the patched set), copies `model1io.zip` and `m1comm.zip` beside it, and
  writes `build-report.txt` (one line per course). `--smoke` then runs MAME headless for 60 emulated
  seconds on a converted course and checks that it loads and renders at the arcade's rate; without
  `mame` on your `PATH` it says so and the build still succeeds.
- MAME warns that some ROMs have the wrong checksums: they are the patched ones, that is expected.
- Exit codes: 0 done, 1 an input is wrong, 2 a patch site did not match, 3 the smoke test failed.

**In the game:** choose Practice; the course row scrolls through ten entries as you turn the wheel
(steering left/right): BIG FOREST, BAY BRIDGE, ACROPOLIS, then ALPINE, AMAZON FALLS, DIABLO CANYON,
METROPOLIS, PACIFIC COAST, SURFERS OVAL, SURFERS ROAD. Grand Prix is untouched.

**Reverse (new in v0.2):** after you pick one of the seven converted courses, a COURSE DIRECTION screen shows
the course twice, NORMAL on the left and REVERSE on the right. It starts on NORMAL; turn the wheel right for
REVERSE (bring it to the centre or left first if it is already to the right), and press the gas to start. Doing
nothing races the normal way. The three original courses have no reverse and go straight to the race.

**Best times:** each course keeps its own ranking table in the game's battery-backed RAM. On the first
boot of the patched set the game finds its RAM laid out for three tables and initialises it for ten,
so best times saved by the original set are reset once. Keep a copy of MAME's `nvram/vr` folder if
you want them.

**Tuning (optional):** `--tune "AMAZON FALLS:pace=0.9,laps=4"` scales a course's opponents' pace
(`pace`), its checkpoint time extensions (`time_factor`) and sets its race length (`laps`, 1 to 7);
repeat `--tune` per course. The defaults are 5 laps and the values the build was tested with.

## What's new in v0.2

- **Every converted course in reverse:** the seven Saturn courses can be raced the other way round, chosen
  on a new COURSE DIRECTION screen after the course select (see "In the game"). The opponents, the
  checkpoints and time extensions, the in-race map, the start grid and the pit stop all run in reverse;
  the pit lane is entered where a normal race leaves it. A reverse race records no best time. The attract
  mode and linked play stay in the normal direction.
- **The course's name in the race:** on a converted course the bottom-right label of the race screen reads
  the course's name (ALPINE, AMAZON FALLS, ...) where it showed its host's BEGINNER / MEDIUM / EXPERT.
- **The road's look:** dark wedges on the road are gone (about a sixth to nearly half of the road faces of a
  course were lit as if facing away), and the road's greys are matched to the arcade courses'.
- **Driving feel:** the car no longer leans when one side runs onto the grass or snow beside the road; a hump
  just after Metropolis's start line and a lean on the grass at one of Alpine's bends are gone.
- **The opponents stay on the road more:** the point each opponent steers at sat too far ahead on the
  converted courses; counted over a 150-second race, their off-road moments fell on every course
  (Pacific Coast 100 to 89, Diablo Canyon 90 to 74, Metropolis 76 to 57, Surfers Road 56 to 40, Surfers Oval
  30 to 19, Amazon Falls 20 to 14, Alpine 148 to 78).
- **The in-race map:** the cars' markers no longer vanish on the lower parts of a course.
- **The sky:** the hard line where a cloudy backdrop met the flat sky colour above it is faded out.
- **Diablo Canyon's pit lane:** a wall that stood in the lane's west side is trimmed off it (this changes the
  normal race there too).

## What's new in v0.1.5

- **The rankings name their course:** after a race on a converted course, its best-time table is titled with its
  name ("AMAZON FALLS COURSE RANKING"); before, it showed its host course's BEGINNER / MEDIUM / EXPERT. In the
  attract mode, each original course's ranking page now shows the converted courses in its slot by name on later
  loops, one per loop.
- **Fixed:** since v0.1, the attract mode's three ranking pages all showed the table of the last course chosen
  (Bay Bridge's on a fresh boot): each original's page shows its own table again (EXPERT: Acropolis's 5'00 times).
  Best times already saved are kept.

## What's new in v0.1.4

- **The title says so:** the attract mode's V.R. / Virtua Racing logo now reads "Extended" under "Racing",
  in the logo's own red with its black shadow, in bold italic. Nothing else in the game changes.

## What's new in v0.1.3

- **The opponents stay on the road:** on the converted courses they ran off into the scenery far more often
  than on the originals, about half as often now. The game tracks each car's progress by the road piece under it
  and steers it at a point just ahead; our long road pieces made that point jump far ahead. Long pieces are now cut
  (measured over a 150-second race per course: off-road moments 98 -> 43 over the seven courses).

## What's new in v0.1.2

- **Surfers Road's pit stop** now always triggers: the lane shares open tarmac with the race road for its
  first 140 units, and a car coming in from the race side could cross into the lane past the trigger.
- **Amazon Falls' pit exit:** the wall now stands at the drawn rock on the right; a car leaving the pit
  could drive into the rock and out of the course.
- **Pacific Coast:** the Saturn's first C.P. flag, which stood 400 units after the start line and was
  not a checkpoint, is no longer drawn.
- **Metropolis:** the pit stop parks the car inside the tunnel, not just past its exit.

The game the patch builds changes on those four courses only. v0.1.1 changed the tests only.

## Known issues in v0.2

- **Reverse:** the reverse pit stops and Diablo Canyon's trimmed pit lane were measured with the test
  autopilot on all seven courses, not yet driven through by hand on each. On Alpine, Diablo Canyon and
  Metropolis some cars stand turned on the reverse start grid. On Amazon Falls, Pacific Coast, Surfers Oval
  and Surfers Road the opponents share three racing lines in reverse (eight in the normal direction). On
  Alpine a reverse car that runs along the very edge of the road on the pit side, just past the pit exit,
  is taken for a pit stop. The three original courses have no reverse.

- **Music:** races on the seven converted courses play the select screen's track, not the Saturn
  course's music.
- **Walls:** the collision wall follows the drawn scenery closely on most of each course, but not
  everywhere: on a few corners (Amazon Falls' second corner, Diablo Canyon's rocks at its middle and
  end sections) the wall stands a little off the drawn rock, and at Diablo Canyon's end the car can
  slip under a rock.
- **Opponents:** they still leave the road now and then, most on Diablo Canyon.
- **Difficulty:** the opponents' pace and the time limits on the converted courses are first values,
  not yet balanced by play.
- **Diablo Canyon:** its colours are not yet the Saturn's, the cars start the race slightly slanted,
  and the camera can bounce on some sections.
- **Original program bytes:** the patch finds and checks its sites in the arcade program by short
  instruction patterns (the instructions being replaced or next to them: 15 patterns, 286 bytes in all, up to
  v0.1.5; v0.2's reverse direction adds more, not recounted for this release). A later
  release will check them by checksum instead, so the patch holds no bytes of the program.
- How the converted courses differ from the Saturn's, measured: `docs/deviations.md`.

## Planned

- **The Saturn port's other releases:** the **US** and **Japanese** discs (they lay their files out
  differently from the European one). The arcade side needs nothing: its one ROM set covers every region.
- The Saturn's music on each converted course.
- The remaining wall spots, and the difficulty per course from playtesting.
- Diablo Canyon's colours.
- The patch-site checks by checksum (see above).

## What is in the patch

- the converter (`vrtools/`, Python): it reads the Saturn course files from your disc and writes the
  arcade's road, collision, scenery, opponents' lines, race tables, select panels, map and backdrop
  for each new course into free space of your ROM set, then patches the program to offer ten courses and
  adds "Extended" to the attract logo;
- the MAME Lua scripts the tests drive the game with (`vrtools/mame/lua/`);
- the tests (`tests/`): most need your ROM set and disc (`VR_ROMDIR`, `VR_SATURN_CUE`, see
  `local.env.example`) and skip without them; the race tests need MAME 0.289;
- the notes on the arcade's and the Saturn's data formats (`docs/formats/`), the research notes
  behind each step (`docs/spike/`), and the measured differences (`docs/deviations.md`);
- facts about the original program: addresses, sizes, CRCs, and the patch-site patterns above.

None of the game: every course's road, collision, scenery and race tables are computed from your own
disc when the build runs, and every picture and letter the select screen shows is drawn from your own
ROM set or by the converter.

## Development

```sh
.venv/bin/pip install -e '.[dev]'
cp local.env.example local.env   # set the two paths, then: source local.env
.venv/bin/pytest
```

The tests that disassemble the game's code need MAME's `unidasm`, which `tools/build-mame.sh` builds into
`build/mame/` (macOS with Homebrew; it compiles MAME's Model 1 driver, which takes a while); without it they
skip and say so. Ten tests written for earlier rounds are known to fail against the current geometry and
are being restated: five collision tests, the thinning test, two profile tests, and two of the first
autopilot drives (Alpine in Big Forest's slot, Diablo Canyon), whose old autopilot now meets the walls.
`tools/pre-commit` refuses binaries and large files (link it into `.git/hooks/`).

## Legal

This is a personal, non-commercial technical study; nothing is sold.

- Virtua Racing, its code, art, sound and courses belong to Sega; the Saturn port and its courses to
  Sega and Time Warner Interactive. This project is not affiliated with or endorsed by either; the
  names are used only to say which games it concerns.
- No ROM set, disc image, patched set or extracted game data is offered here or anywhere else, none
  is linked to, and nothing will be sent on request. Build it from your own lawfully obtained copies.
- The code and documents in this repository are under the MIT licence (`LICENSE`), which covers them
  only.
- If you hold rights in the games and object to anything here, open an issue and it will be taken
  down promptly.
