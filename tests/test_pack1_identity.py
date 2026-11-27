"""Pack 1's identity, a standing gate (fix round 1, C1): `vrtools build` (the Saturn courses' set, no option) built from this tree
must give, member for member, the released v0.4.1 set's bytes. The digests below are the sha256 of each member of the three zips
of v0.4.1 as built from main (they agree with the released play set's); they are facts about built files, not game data.

A release that changes pack 1 ON PURPOSE re-pins them here, in the same commit, and names the release in RELEASE. Any other
difference is a regression of pack 1 (the PS2 courses' set, pack 2, must never move it). Gated like the other build tests: the
arcade set (VR_ROMDIR) and the Saturn disc (VR_SATURN_CUE)."""
import hashlib
import zipfile

import pytest

RELEASE = "v0.4.1"
PINNED = {
    ("vr.zip", "315-5571.bin"): "2d00f5418f20702c34b7e27ca8d47ac197499e010c0ae1f50e414a3025c34ae5",
    ("vr.zip", "315-5572.bin"): "94d582f2efc095acef8fb038e9abd80784fe8785f68916afd8163aa117e43c52",
    ("vr.zip", "315-5573.bin"): "21ab871d2a5440114bac1e8b90dae32025baddc8c19d1bc77797190edf4f352a",
    ("vr.zip", "93c45.bin"): "6fd5b02f29f0454b4e978d77368d02c1a860aa0d057bdc5408b1a6b7d110a5f2",
    ("vr.zip", "epr-14870a.7"): "d71ea3bce3d1a1b7145ac2727feb620b4cde60af28749d8d208f1b529e8bbea0",
    ("vr.zip", "epr-14878a.4"): "edc691ca530458985a1bc339f07f6487f8dc67fd59226882468e1c5cec546e18",
    ("vr.zip", "epr-14879a.5"): "393998ede78ac6fcc592594919510f1bd13bd4e3faa9137f2e690682345c5ebd",
    ("vr.zip", "epr-14882.14"): "1518e24c6af0cfde7d9ca19aa19f2eb586a43cf50ff464ae77cb3b96225321dc",
    ("vr.zip", "epr-14883.15"): "16517e4b1929cef1f391862388165485fb28c3902cb4be843eeaca3964918041",
    ("vr.zip", "mpr-14873.32"): "f1d256375ee32ec385c736ca016f4ccd7f21ca75ab974ab9bf6829b5caba957f",
    ("vr.zip", "mpr-14876.4"): "c1dc5eadc2db0ca45a458b27c02f0509fcfc248f3a91bdb078872dd8a37a7437",
    ("vr.zip", "mpr-14880.6"): "2c83167747ae15587fdc9d27c834ed4434a4ba0137c2b72e3bf5bb68fdce9e32",
    ("vr.zip", "mpr-14881.7"): "e1ea5d03e736dd5d64f0304576bc98a3110585c9d455d073c28416f1a3b00d2a",
    ("vr.zip", "mpr-14884.8"): "7f24893f495d9cbdf73ecf25cd58cfd41890ee73b81821efca9f8ebf2bf89c3f",
    ("vr.zip", "mpr-14885.9"): "07331d72ff5a2f1ecd82d9925d5b1753ea99e4396cc3866bdc920ad1eeaf797a",
    ("vr.zip", "mpr-14886.10"): "b45e8e6a5303c09dfeca8d5093efad56900a60b64ac6ebb972dc01555151ad13",
    ("vr.zip", "mpr-14887.11"): "a459fe1efd522965e920831094dc2070f210d91b5cef2fefbd2df32a8591282b",
    ("vr.zip", "mpr-14888.12"): "0aabc71b0541c70e136cfd0675e0f2ffd3c37e6cdb36827f8fd7d6c533d19cc0",
    ("vr.zip", "mpr-14889.13"): "e4e9fb9fdafa7bf9725a1f67e9e006befa343f84f63add25d09724cf452beaaa",
    ("vr.zip", "mpr-14890.26"): "ee3c1c3bb32d059544a54f4aecde96b06e71b78450d0aa2c84e57d30c114eb55",
    ("vr.zip", "mpr-14891.27"): "bbfd1ecebf9cc9d97ed27d5e96e7f43126b673fd45b66bdc8f099c4b2530e057",
    ("vr.zip", "mpr-14892.28"): "69ca2ebdcb11a7c47deedb303ef9683d9377392b49bd89d58c8434c3f133e7e3",
    ("vr.zip", "mpr-14893.29"): "42954fad84f06442ff023511805ce880bd340a62e65a23186dcd1ebc70936dad",
    ("vr.zip", "mpr-14894.30"): "ebd7f2a41794ca1c04b3182f1f7b21a3e4f1474921b7c8d2f16453f3891730aa",
    ("vr.zip", "mpr-14895.31"): "13c66d07031a2217329c6b5400be8bf995864f656f109ee0d07a1321740e334b",
    ("vr.zip", "mpr-14896.32"): "abfe73340869145e1240ec00f5699364a44310a815645c7b9c75299c2d344354",
    ("vr.zip", "mpr-14897.33"): "98c983cd7346d5a4a1ee3ace6f27be9e13396af2dcb6eadf83f7ea238c23d0da",
    ("vr.zip", "mpr-14898.39"): "4f0363673cc0c0c53fb6f3360218959787aceb14fe39c476cdd4198b3560d10c",
    ("vr.zip", "mpr-14899.40"): "0ac9910156c440a84d6ff53f11bb9abf9d07c4a5f7b4903abfb605ec5009e5b9",
    ("vr.zip", "mpr-14900.41"): "c26cdedb4bfa01b6053302239dffcf2da40a2934842abf02917a05168afde0e3",
    ("vr.zip", "mpr-14901.42"): "9488a12301e45a40072b171915edb1b0fcb56a9d8c07c0f75afa48e1ca54f817",
    ("vr.zip", "opr-14744.58"): "a59d05e17f98a5bd2b2eecf5126555fad0128b90adf4a880513d6b8b8745302c",
    ("vr.zip", "opr-14745.59"): "34be268b2e6cfd75d36869e5561745ba574626c691e4bc11f03c4ebd604341ba",
    ("vr.zip", "opr-14746.62"): "f25ed5d145e6197909899a06d024570a20a61d7005dc40f1bd3fb414e1187ed8",
    ("vr.zip", "opr-14747.63"): "db7f76d2406c04a5708d775007b120a76a4c9e93c4655c8e54d9aad0a966ded4",
    ("vr.zip", "opr14742.bin"): "1dc67b5b23eb84ef77526e6589b5ecca3f972401d4c1743110273725ce02827c",
    ("vr.zip", "opr14743.bin"): "4504325a7e106cb12330a491885ebb3661e1870c5e953da2f0d30c9d7bef306b",
    ("vr.zip", "opr14748.bin"): "43314d00b5445552489be09969a9b75d4ccb420fe1e8e7e290d542d5fc424c6e",
    ("model1io.zip", "epr-14869.25"): "fe000e0e7fb85e4fac0dc8f7e477af11a698ac5f8971c66bf0c8d230a6e2749e",
    ("model1io.zip", "epr-14869b.25"): "003ed35c120a37b42e689b527afcad3cf8d96f42760fac2aa83f748e4a1a5a95",
    ("model1io.zip", "epr-14869c.25"): "e4bed0465099b513d9830cd3b4d088d7ade9406d774a7c0ead790fb4ad400e52",
    ("m1comm.zip", "epr-15112.17"): "ae5a67c8b187022d632b367058c43cdee3b871fe1fd7ca6f4e1d2099d368faff",
    ("m1comm.zip", "epr-15624.17"): "2db3f8c92ac7126b1992afeb549ca8eb8bf39032e78e98985598857e68452e08",
}


def test_the_pins_cover_the_three_zips():
    assert len(PINNED) == 43 and sum(z == "vr.zip" for z, _ in PINNED) == 38
    assert {z for z, _ in PINNED} == {"vr.zip", "model1io.zip", "m1comm.zip"}


def test_pack_one_built_from_the_tree_is_the_released_set_byte_for_byte(tmp_path_factory):
    """Its inputs (the original set, the Saturn disc) missing: skips, or FAILS under VR_REQUIRE_REFERENCE_SETS=1
    (tests/reference_sets.py's `missing_input`: a release run cannot pass this gate by skipping it)."""
    from tests.pack_sets import built
    from tests.reference_sets import required_romset_zip, required_saturn_cue
    romset_zip, saturn_cue = required_romset_zip(), required_saturn_cue()
    out = built("saturn", romset_zip, tmp_path_factory, saturn_cue=saturn_cue)      # the session's pack 1 (shared)
    got = {}
    for z in ("vr.zip", "model1io.zip", "m1comm.zip"):
        with zipfile.ZipFile(out / z) as zf:
            got.update({(z, m): hashlib.sha256(zf.read(m)).hexdigest() for m in zf.namelist()})
    assert set(got) == set(PINNED), f"members differ from {RELEASE}'s: {sorted(set(got) ^ set(PINNED))}"
    moved = sorted(f"{z}/{m}" for (z, m), d in got.items() if d != PINNED[z, m])
    assert not moved, f"pack 1 differs from the released {RELEASE} in {moved}"
