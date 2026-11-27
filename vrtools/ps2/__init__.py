"""Readers for the PS2 disc Sega Ages 2500 Vol. 8, Virtua Racing FlatOut (Japan), SLPM 624.43.

Formats: docs/spike/2026-11-phase90-ps2-disc-recon.md. Modules: `disc` (the MODE2 ISO), `pac` (LZSS archives),
`model` (triangle-list models), `vcp` (collision triangles), `pat` (point lists), `picture` (the headerless
CLUT pictures), `course` (one course's files, gathered).
"""


class Ps2ReadError(Exception):
    """The base of the readers' errors (PacError, ModelError, VcpError, PatError, PictureError): what the build reports as a
    problem with the PS2 disc's files."""
