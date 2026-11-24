"""Stand-in storm modules for the weather tests (weather Task 6J: the join moved them out of `vrtools`; the normal set registers the
real owners, cover, lightning, rain, handling and sound).

`strike_standin` (stage 6's, from weather/sound.py): a module named `lightning` that strikes on chosen race passes, so that the sound's
MAME tests hear thunders at known moments (the real lightning's strikes come at random every 20-40 s). It owns the real lightning's two
interface cells (`STANDIN_CELLS`, as lightning.cells() names them) and three of its own."""
from vrtools.arcade.v60asm import Block
from vrtools.arcade.weather import carrier

STANDIN_CELLS = (("strike_seq", 4), ("strike_band", 4))


def strike_standin(schedule: tuple[tuple[int, int], ...], after: tuple[tuple[int, int], ...] = (),
                   late_at: tuple[int, ...] = ()) -> carrier.Module:
    """A module named `lightning` (tests only) that raises a strike of band `band` on the `n`-th SHOW pass of the race (mode 0x14) for
    each (n, band) of `schedule`, and on the `n`-th SHOW pass after it (the goal and results' rain modes, where the real lightning,
    as the prototype's, starts none) for each of `after`: strike_band := band and strike_seq + 1 on that pass, as lightning's
    contract says; it holds strike_band until its next strike. Its cell `late` is 1 on the race passes `late_at` and 0 on every other
    pass (the planted late guard of `module(planted_late=True)`)."""
    def code(lay):
        seq, band = lay.cell("lightning", "strike_seq"), lay.cell("lightning", "strike_band")
        n, m = lay.cell("lightning", "passes"), lay.cell("lightning", "after")
        b = Block(lay.code("lightning"))

        def strikes(counter, sched, tag):
            for k, (at, bd) in enumerate(sched):
                b.emit("cmp.w imm,abs", at, counter)
                b.branch("bne", f"{tag}{k}")
                b.emit("mov.w imm,abs", bd, band)
                b.emit("add.w imm,abs", 1, seq)
                b.label(f"{tag}{k}")
        late = lay.cell("lightning", "late")
        b.label("frame")
        b.emit("mov.b imm,abs", 0, late)
        b.emit("cmp.b imm,abs", 0x14, carrier.MODE)
        b.branch("bne", "not_race")
        b.emit("add.w imm,abs", 1, n)
        strikes(n, schedule, "s")
        for k, at in enumerate(late_at):
            b.emit("cmp.w imm,abs", at, n)
            b.branch("bne", f"l{k}")
            b.emit("mov.b imm,abs", 1, late)
            b.label(f"l{k}")
        b.emit("rsr")
        b.label("not_race")
        b.emit("cmp.w imm,abs", 0, n)                   # after the race only (the countdown has passes 0)
        b.branch("be", "out")
        b.emit("add.w imm,abs", 1, m)
        strikes(m, after, "a")
        b.label("out")
        b.emit("rsr")
        return b
    return carrier.Module(name="lightning", code=code, cells=STANDIN_CELLS + (("passes", 4), ("after", 4), ("late", 4)), frame="frame")
