"""A minimal NEC V60 encoder for the code patches: the handful of instruction forms the new routines use,
each verified against MAME's unidasm (tests/test_v60asm.py). Absolute addressing only, so emitted code is
position-independent apart from branches, which `Block` resolves.

Encoding (from MAME's v60d.cpp): opcode byte, then for two-operand forms a code byte — bit 7 set: two
addressing-mode (AM) operands (bit 6 / bit 5 = the "m" family of the first / second); bit 7 clear: one AM
operand and one register in the low five bits, bit 5 set when the AM operand comes first (source), bit 6 the
AM's m family. AM bytes: m=0 — `disp[reg]` (size class << 5 | reg, then the displacement), `[reg]` (0x60 | reg),
`#imm` (0xe0 | v for 0..15, else 0xf4 + the value in the operand's size), absolute (0xf3 + u32); m=1 —
register direct (0x60 | reg), direct address indexed `abs(reg)` (0xc0 | index, 0xf3, u32)."""
from __future__ import annotations

import struct
from dataclasses import dataclass, field


class AsmError(Exception):
    pass


def _reg(name: str) -> int:
    if not (isinstance(name, str) and name[0] in "rR" and name[1:].isdigit() and 0 <= int(name[1:]) < 32):
        raise AsmError(f"not a register: {name!r}")
    return int(name[1:])


def _u32(v: int) -> bytes:
    return struct.pack("<I", v & 0xFFFFFFFF)


# ---- addressing modes: (m, bytes)
def am_reg(r: str) -> tuple[int, bytes]:
    return 1, bytes([0x60 | _reg(r)])


def am_ind(r: str) -> tuple[int, bytes]:
    return 0, bytes([0x60 | _reg(r)])


def am_disp(disp: int, r: str) -> tuple[int, bytes]:
    reg = _reg(r)
    if -128 <= disp < 128:
        return 0, bytes([reg]) + struct.pack("<b", disp)
    if -32768 <= disp < 32768:
        return 0, bytes([0x20 | reg]) + struct.pack("<h", disp)
    return 0, bytes([0x40 | reg]) + struct.pack("<i", disp)


def am_abs(addr: int) -> tuple[int, bytes]:
    if not (0 <= addr < 1 << 32):
        raise AsmError(f"address out of range: {addr:#x}")
    return 0, b"\xf3" + _u32(addr)


def am_imm(v: int, size: int) -> tuple[int, bytes]:
    if 0 <= v < 16:
        return 0, bytes([0xE0 | v])
    mask = (1 << (8 * size)) - 1
    if not (-(1 << (8 * size - 1)) <= v <= mask):
        raise AsmError(f"immediate {v:#x} does not fit {size} bytes")
    return 0, b"\xf4" + (v & mask).to_bytes(size, "little")


def am_abs_indexed(addr: int, idx: str) -> tuple[int, bytes]:
    return 1, bytes([0xC0 | _reg(idx), 0xF3]) + _u32(addr)


def am_ind_indexed(base: str, idx: str) -> tuple[int, bytes]:
    """`[base](idx)`: the operand at base + idx × operand size."""
    return 1, bytes([0xC0 | _reg(idx), 0x60 | _reg(base)])


# ---- instruction formats
def _f1(op: int, am: tuple[int, bytes], r: str, am_is_source: bool) -> bytes:
    m, b = am
    return bytes([op, (0x20 if am_is_source else 0) | (0x40 if m else 0) | _reg(r)]) + b


def _f2(op: int, src: tuple[int, bytes], dst: tuple[int, bytes]) -> bytes:
    (m1, b1), (m2, b2) = src, dst
    return bytes([op, 0x80 | (0x40 if m1 else 0) | (0x20 if m2 else 0)]) + b1 + b2


def _f3(op: int, am: tuple[int, bytes]) -> bytes:
    m, b = am
    return bytes([op | m]) + b


OPS = {"mov.w": (0x2D, 4), "mov.h": (0x1B, 2), "mov.b": (0x09, 1), "movz.bw": (0x0D, 1), "movz.hw": (0x1D, 2),
       "add.w": (0x84, 4), "sub.w": (0xAC, 4), "mul.w": (0x85, 4), "and.w": (0xA4, 4), "or.w": (0x8C, 4),
       "shl.w": (0xAD, 1), "sha.w": (0xBD, 1), "cmp.w": (0xBC, 4), "cmp.h": (0xBA, 2), "cmp.b": (0xB8, 1)}
COND = {"be": 4, "bne": 5, "bnh": 6, "bh": 7, "br": 0xA, "blt": 0xC, "bge": 0xD, "ble": 0xE, "bgt": 0xF}   # bnh / bh: unsigned


# Weather stage 2: the float group (opcode 0x5c, short floats; cvt in 0x5f), always two AM operands: the code byte is 0x80, the m
# families in bits 6 / 5 and the operation in the low five bits. `cmpf.s src, dst` sets the flags of dst - src, as `cmp`.
FOPS = {"cmpf.s": (0x5C, 0x00), "movf.s": (0x5C, 0x08), "negf.s": (0x5C, 0x09), "addf.s": (0x5C, 0x18), "subf.s": (0x5C, 0x19),
        "mulf.s": (0x5C, 0x1A), "divf.s": (0x5C, 0x1B), "cvt.ws": (0x5F, 0x00), "cvt.sw": (0x5F, 0x01)}
# The string moves (opcode 0x5a, format 7a: two `[reg]` operands each followed by its length, a register (0x80 | reg) or an
# immediate 0..127): movcu.h copies min(length 1, length 2) halfwords upward; movcfu.h copies length 1 and fills the rest of length
# 2 with R26's low half. Both leave R27 / R28 at the ends (MAME's opMOVSTRUH): a routine using them saves those two.
STRING_OPS = {"movcu.h": 0x08, "movcfu.h": 0x0A}


def float_bits(x: float) -> int:
    """The single-precision bit pattern of `x` (a float immediate's operand)."""
    return struct.unpack("<I", struct.pack("<f", x))[0]


def _string_len(v) -> int:
    if isinstance(v, str):
        return 0x80 | _reg(v)
    if not 0 <= v < 0x80:
        raise AsmError(f"string length immediate {v} not in 0..127")
    return v


def branch(cond: str, own: int, target: int) -> bytes:
    """A conditional/unconditional branch at V60 address `own` to `target` (8-bit when it fits, else 16-bit)."""
    d = target - own
    if -128 <= d < 128:
        return bytes([0x60 | COND[cond]]) + struct.pack("<b", d)
    if -32768 <= d < 32768:
        return bytes([0x70 | COND[cond]]) + struct.pack("<h", d)
    raise AsmError(f"branch from {own:#x} to {target:#x} too far")


def _float_op(form: str, mnem: str, operands: str, args) -> bytes:
    """A FOPS instruction: operand kinds reg, abs, imm (a Python float is taken as its bit pattern), [reg], disp[reg], abs(reg)."""
    op, sub = FOPS[mnem]
    fargs = [float_bits(a) if isinstance(a, float) else a for a in args]
    kinds = operands.split(",")
    if len(kinds) != 2:
        raise AsmError(f"unknown form {form!r}")

    def take(kind: str) -> tuple[int, bytes]:
        if kind == "reg":
            return am_reg(fargs.pop(0))
        if kind == "abs":
            return am_abs(fargs.pop(0))
        if kind == "imm":
            return am_imm(fargs.pop(0), 4)
        if kind == "[reg]":
            return am_ind(fargs.pop(0))
        if kind == "disp[reg]":
            d, r = fargs.pop(0), fargs.pop(0)
            return am_disp(d, r)
        if kind == "abs(reg)":
            a, r = fargs.pop(0), fargs.pop(0)
            return am_abs_indexed(a, r)
        raise AsmError(f"unknown operand kind {kind!r} in {form!r}")
    (m1, b1), (m2, b2) = take(kinds[0]), take(kinds[1])
    if fargs:
        raise AsmError(f"too many operands for {form!r}")
    return bytes([op, 0x80 | (m1 << 6) | (m2 << 5) | sub]) + b1 + b2


def asm(form: str, *args) -> bytes:
    """Encode one instruction. `form` = "<mnemonic> <src>,<dst>" with operand kinds abs, reg, imm, [reg],
    disp[reg], abs(reg); plus "jsr abs", "jmp abs", "push reg", "pop reg", "pushm imm", "popm imm" (a register mask: bit n
    is Rn), "rsr", "nop" and the branches ("be"… with (own, target)); weather stage 2: the FOPS float forms ("mulf.s abs,reg"…),
    "movcu.h [reg],reg,[reg],reg" and "movcfu.h [reg],imm,[reg],reg"."""
    if form in COND:
        return branch(form, *args)
    if form == "rsr":
        return b"\xca"
    if form == "nop":
        return b"\xcd"
    if form == "jsr abs":
        return _f3(0xE8, am_abs(args[0]))
    if form == "jmp abs":
        return _f3(0xD6, am_abs(args[0]))
    if form == "push reg":
        return _f3(0xEE, am_reg(args[0]))
    if form == "pop reg":
        return _f3(0xE6, am_reg(args[0]))
    if form == "pushm imm":
        return _f3(0xEC, am_imm(args[0], 4))
    if form == "popm imm":
        return _f3(0xE4, am_imm(args[0], 4))
    mnem, operands = form.split(" ", 1)
    if mnem in STRING_OPS:
        if operands not in ("[reg],reg,[reg],reg", "[reg],imm,[reg],reg"):
            raise AsmError(f"unknown form {form!r}")
        src, len1, dst, len2 = args
        return bytes([0x5A, 0x80 | STRING_OPS[mnem], 0x60 | _reg(src), _string_len(len1), 0x60 | _reg(dst), _string_len(len2)])
    if mnem in FOPS:
        return _float_op(form, mnem, operands, args)
    if mnem not in OPS:
        raise AsmError(f"unknown form {form!r}")
    op, size1 = OPS[mnem]
    src_kind, dst_kind = operands.split(",")
    args = list(args)

    def take(kind: str) -> tuple[int, bytes] | str:
        if kind == "reg":
            return args.pop(0)
        if kind == "abs":
            return am_abs(args.pop(0))
        if kind == "imm":
            return am_imm(args.pop(0), size1)
        if kind == "[reg]":
            return am_ind(args.pop(0))
        if kind == "disp[reg]":
            d, r = args.pop(0), args.pop(0)
            return am_disp(d, r)
        if kind == "abs(reg)":
            a, r = args.pop(0), args.pop(0)
            return am_abs_indexed(a, r)
        if kind == "[reg](reg)":
            b, r = args.pop(0), args.pop(0)
            return am_ind_indexed(b, r)
        raise AsmError(f"unknown operand kind {kind!r} in {form!r}")

    src, dst = take(src_kind), take(dst_kind)
    if args:
        raise AsmError(f"too many operands for {form!r}")
    if isinstance(src, str) and isinstance(dst, str):                  # reg,reg: register source, register-direct AM destination
        return _f1(op, am_reg(dst), src, am_is_source=False)
    if isinstance(dst, str):
        return _f1(op, src, dst, am_is_source=True)
    if isinstance(src, str):
        return _f1(op, dst, src, am_is_source=False)
    return _f2(op, src, dst)


@dataclass
class Block:
    """A code block at `base`: emit instructions and labels; branches to labels are sized in a second pass."""
    base: int
    items: list = field(default_factory=list)          # bytes | (cond, label) | ("label", name)

    def emit(self, form: str, *args) -> None:
        self.items.append(asm(form, *args))

    def branch(self, cond: str, label: str) -> None:
        self.items.append((cond, label))

    def raw(self, data: bytes) -> None:
        """Bytes as they are (instructions `asm` has no form for, or an original sequence copied whole: its relative
        branches must stay inside it)."""
        self.items.append(bytes(data))

    def label(self, name: str) -> None:
        self.items.append(("label", name))

    def _layout(self) -> tuple[bytes, dict[str, int]]:
        sizes = [2 if isinstance(it, tuple) and it[0] != "label" else 0 for it in self.items]
        for _ in range(20):
            addrs: dict[str, int] = {}
            pos = self.base
            for it, sz in zip(self.items, sizes):
                if isinstance(it, bytes):
                    pos += len(it)
                elif it[0] == "label":
                    addrs[it[1]] = pos
                else:
                    pos += sz
            out = bytearray()
            pos = self.base
            changed = False
            for k, (it, sz) in enumerate(zip(self.items, sizes)):
                if isinstance(it, bytes):
                    out += it
                    pos += len(it)
                elif it[0] == "label":
                    continue
                else:
                    cond, name = it
                    if name not in addrs:
                        raise AsmError(f"undefined label {name!r}")
                    b = branch(cond, pos, addrs[name])
                    if len(b) != sz:
                        sizes[k] = len(b)
                        changed = True
                    out += b
                    pos += len(b)
            if not changed:
                return bytes(out), addrs
        raise AsmError("branch sizing did not converge")

    def bytes(self) -> bytes:
        return self._layout()[0]

    def addr(self, name: str) -> int:
        return self._layout()[1][name]
