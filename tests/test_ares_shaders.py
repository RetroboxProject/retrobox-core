"""Ares loads its shaders from Retrobox's shaders folder."""

from retrobox.configgen.generators.ares import ares_config


def test_link_shaders_points_ares_at_the_shared_folder(tmp_path):
    """Ares' user data directory gets a link to the shaders folder, once."""
    shaders = tmp_path / "shaders"
    (shaders / "crt").mkdir(parents=True)
    (shaders / "crt" / "crt-hyllian-ntsc-2.slangp").write_text("")
    ares_dir = tmp_path / "ares"
    ares_dir.mkdir()

    ares_config.link_shaders(ares_dir, shaders)
    ares_config.link_shaders(ares_dir, shaders)

    assert (ares_dir / "Shaders" / "crt" / "crt-hyllian-ntsc-2.slangp").is_file()
    assert ares_config.resolve_shader("crt/crt-hyllian-ntsc-2", shaders) == (
        "crt/crt-hyllian-ntsc-2"
    )


def test_link_shaders_keeps_a_real_folder(tmp_path):
    """A folder the user put there is not replaced."""
    ares_dir = tmp_path / "ares"
    (ares_dir / "Shaders").mkdir(parents=True)

    ares_config.link_shaders(ares_dir, tmp_path / "shaders")

    assert not (ares_dir / "Shaders").is_symlink()


def test_sound_server_env(tmp_path, monkeypatch):
    """PulseAudio is forced only when it is the one sound server running."""
    # pylint: disable=import-outside-toplevel
    from retrobox.configgen.generators.ares.ares_generator import sound_server_env

    monkeypatch.setenv("XDG_RUNTIME_DIR", str(tmp_path))
    monkeypatch.delenv("SDL_AUDIODRIVER", raising=False)
    assert not sound_server_env()

    (tmp_path / "pulse").mkdir()
    (tmp_path / "pulse" / "native").write_text("")
    assert sound_server_env() == {"SDL_AUDIODRIVER": "pulseaudio"}

    (tmp_path / "pipewire-0").write_text("")
    assert not sound_server_env()

    (tmp_path / "pipewire-0").unlink()
    monkeypatch.setenv("SDL_AUDIODRIVER", "alsa")
    assert not sound_server_env()
