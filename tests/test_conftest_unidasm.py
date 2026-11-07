"""v0.1.1: a fresh clone has no build/mame/unidasm; the tests that disassemble skip with the command to build it,
instead of failing (77 failures in the public v0.1 copy were this)."""
from pathlib import Path

pytest_plugins = "pytester"

CONFTEST = (Path(__file__).parent / "conftest.py").read_text()


def test_a_missing_unidasm_skips_with_the_build_command(pytester):
    pytester.makeconftest(CONFTEST)
    pytester.makepyfile(test_x="""
        from vrtools.arcade.disasm import DisasmError
        from vrtools.saturn.sh2 import Sh2Error
        def test_v60():
            raise DisasmError("unidasm not found at /x/build/mame/unidasm; run tools/build-mame.sh")
        def test_sh2():
            raise Sh2Error("unidasm not found at /x/build/mame/unidasm; run tools/build-mame.sh")
        def test_other_disasm_error_still_fails():
            raise DisasmError("address 0x10 is not in program or boot ROM")
    """)
    res = pytester.runpytest("-rs")
    res.assert_outcomes(skipped=2, failed=1)
    res.stdout.fnmatch_lines(["*tools/build-mame.sh*"])
