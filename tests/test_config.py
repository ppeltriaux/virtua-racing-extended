from pathlib import Path

from vrtools import config


def test_rom_dir_none_when_unset(monkeypatch):
    monkeypatch.delenv("VR_ROMDIR", raising=False)
    assert config.rom_dir() is None


def test_rom_dir_from_env(monkeypatch, tmp_path):
    monkeypatch.setenv("VR_ROMDIR", str(tmp_path))
    assert config.rom_dir() == tmp_path


def test_saturn_cue_from_env(monkeypatch, tmp_path):
    cue = tmp_path / "vr.cue"
    monkeypatch.setenv("VR_SATURN_CUE", str(cue))
    assert config.saturn_cue() == cue


def test_out_dir_is_created(tmp_path, monkeypatch):
    monkeypatch.setenv("VR_OUT", str(tmp_path / "o"))
    assert config.out_dir().is_dir()
    assert config.out_dir() == tmp_path / "o"
