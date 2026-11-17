"""RetroAchievements: the shared account and options, PCSX2, Dolphin and RetroArch."""

from __future__ import annotations

import io
import json
import urllib.error
from pathlib import Path
from typing import Any

import pytest

from retrobox.configgen.config import SystemConfig
from retrobox.configgen.generators.dolphin import dolphin_config
from retrobox.configgen.generators.libretro import libretro_achievements
from retrobox.configgen.generators.pcsx2 import pcsx2_config
from retrobox.configgen.utils import achievements
from retrobox.configgen.utils.configparser import CaseSensitiveConfigParser

ON = {
    "retroachievements": "1",
    "retroachievements.username": "player",
    "retroachievements.token": "tok123",
}


def _config(**values: str) -> SystemConfig:
    data = {key.replace("__", "."): value for key, value in values.items()}
    return SystemConfig(data)


def _on(**values: str) -> SystemConfig:
    config = SystemConfig(dict(ON))
    config.data.update({key.replace("__", "."): value for key, value in values.items()})
    return config


class _Reply(io.BytesIO):
    """A fake HTTP response for urlopen."""

    def __enter__(self) -> _Reply:
        return self

    def __exit__(self, *args: object) -> None:
        self.close()


@pytest.fixture(name="server")
def fixture_server(monkeypatch: pytest.MonkeyPatch) -> list[Any]:
    """Replace the RetroAchievements server; collects the requests made."""
    requests: list[Any] = []
    reply: dict[str, Any] = {"Success": True, "User": "player", "Token": "fromserver"}

    def urlopen(request: Any, timeout: float) -> _Reply:
        del timeout
        requests.append(request)
        if reply.get("raise"):
            raise urllib.error.URLError("offline")
        return _Reply(json.dumps(reply).encode())

    monkeypatch.setattr(achievements.urllib.request, "urlopen", urlopen)
    requests.append(reply)  # the first item is the reply, for the test to change
    return requests


# --- the shared module -------------------------------------------------------


def test_account_needs_switch_user_and_secret() -> None:
    """No account while off, without a user, or without a token or password."""
    assert achievements.account(_config()) is None
    assert achievements.account(_config(retroachievements="0", **{
        "retroachievements__username": "u", "retroachievements__token": "t"})) is None
    assert achievements.account(_config(retroachievements="1", **{
        "retroachievements__username": "u"})) is None
    assert achievements.account(_on()) == achievements.Account("player", "tok123")


def test_token_wins_over_password() -> None:
    """With a token the password is never carried along."""
    found = achievements.account(_on(retroachievements__password="secret"))
    assert found is not None and found.password == ""
    assert achievements.session_account(_on()) == {"username": "player", "token": "tok123"}
    no_token = _on(retroachievements__token="", retroachievements__password="secret")
    assert achievements.session_account(no_token) == {
        "username": "player", "password": "secret"}


def test_options_hardcore_and_leaderboards() -> None:
    """Leaderboards need hardcore; netplay turns hardcore off."""
    assert not achievements.options(_on(retroachievements__leaderboards="1")).leaderboards
    options = achievements.options(
        _on(retroachievements__hardcore="1", retroachievements__leaderboards="1")
    )
    assert options.hardcore and options.leaderboards
    netplay = achievements.options(_on(retroachievements__hardcore="1", netplay__mode="host"))
    assert not netplay.hardcore and not netplay.leaderboards


@pytest.mark.parametrize(("sound", "expected"), [("", False), ("none", False), ("chime", True)])
def test_sound(sound: str, expected: bool) -> None:
    """``none`` and nothing mean no unlock sound."""
    assert achievements.options(_on(retroachievements__sound=sound)).has_sound is expected


def test_login_token_uses_the_token_first(server: list[Any]) -> None:
    """An account with a token never asks the server."""
    assert achievements.login_token(achievements.Account("player", "tok123")) == "tok123"
    assert len(server) == 1


def test_login_token_swaps_the_password(server: list[Any]) -> None:
    """Without a token, login2 with the password gives one (sent in the body)."""
    token = achievements.login_token(achievements.Account("player", password="p&ss"))
    assert token == "fromserver"
    request = server[1]
    assert request.full_url == achievements.SERVER
    assert request.data == b"r=login2&u=player&p=p%26ss"
    assert request.get_header("User-agent").startswith("Retrobox/")


def test_login_token_failures(server: list[Any], caplog: pytest.LogCaptureFixture) -> None:
    """A refused login or an unreachable server gives no token, and says why."""
    reply = server[0]
    reply.clear()
    reply.update({"Success": False, "Error": "Invalid User/Password combination."})
    assert achievements.login_token(achievements.Account("player", password="bad")) is None
    assert "Invalid User/Password" in caplog.text
    reply["raise"] = True
    assert achievements.login_token(achievements.Account("player", password="x")) is None
    assert "offline" in caplog.text


# --- PCSX2 -----------------------------------------------------------------------


def _pcsx2(config: SystemConfig) -> dict[str, str]:
    settings = CaseSensitiveConfigParser(interpolation=None)
    settings.add_section("Achievements")
    settings.set("Achievements", "Username", "kept")
    pcsx2_config._configure_achievements(settings, config)  # pylint: disable=protected-access
    return dict(settings.items("Achievements"))


def test_pcsx2_off_keeps_the_account() -> None:
    """Off, PCSX2 only gets Enabled = false."""
    assert _pcsx2(_config()) == {"Username": "kept", "Enabled": "false"}


def test_pcsx2_on() -> None:
    """On, the account and every switch of the menu."""
    values = _pcsx2(_on(
        retroachievements__hardcore="1",
        retroachievements__leaderboards="1",
        retroachievements__challenge_indicators="1",
        retroachievements__sound="chime",
    ))
    assert values["Enabled"] == "true"
    assert values["Username"] == "player"
    assert values["Token"] == "tok123"
    assert int(values["LoginTimestamp"]) > 0
    assert values["ChallengeMode"] == "true"
    assert values["LeaderboardNotifications"] == "true"
    assert values["Overlays"] == "true"
    assert values["SoundEffects"] == "true"
    assert values["EncoreMode"] == values["UnofficialTestMode"] == "false"


def test_pcsx2_password_only(server: list[Any]) -> None:
    """With a password and no token, the server's token goes to PCSX2."""
    values = _pcsx2(_on(retroachievements__token="", retroachievements__password="pw"))
    assert values["Token"] == "fromserver"
    assert "pw" not in values.values()
    del server


def test_pcsx2_failed_login_turns_it_off(server: list[Any]) -> None:
    """No token to be had: off for this game, rather than a broken login."""
    server[0]["raise"] = True
    values = _pcsx2(_on(retroachievements__token="", retroachievements__password="pw"))
    assert values["Enabled"] == "false"


# --- Dolphin --------------------------------------------------------------------


@pytest.fixture(name="dolphin_ini")
def fixture_dolphin_ini(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """RetroAchievements.ini in a temporary folder."""
    path = tmp_path / "dolphin-emu" / "RetroAchievements.ini"
    monkeypatch.setattr(dolphin_config, "DOLPHIN_ACHIEVEMENTS_INI", path)
    return path


def _read(path: Path) -> dict[str, str]:
    settings = CaseSensitiveConfigParser(interpolation=None)
    settings.read(path)
    return dict(settings.items("Achievements"))


def test_dolphin_on(dolphin_ini: Path) -> None:
    """On: the account, and hardcore written even when off (Dolphin's default is on)."""
    dolphin_config.write_achievements_ini(_on(retroachievements__verbose="1"))
    values = _read(dolphin_ini)
    assert values["Enabled"] == "True"
    assert values["Username"] == "player"
    assert values["ApiToken"] == "tok123"
    assert values["HardcoreEnabled"] == "False"
    assert values["ProgressEnabled"] == "True"


def test_dolphin_off_keeps_the_rest(dolphin_ini: Path) -> None:
    """Off, only Enabled changes; Dolphin's own settings stay."""
    dolphin_ini.parent.mkdir(parents=True)
    dolphin_ini.write_text(
        "[Achievements]\nEnabled = True\nUsername = someone\nHostUrl = custom\n", encoding="utf-8"
    )
    dolphin_config.write_achievements_ini(_config())
    assert _read(dolphin_ini) == {"Enabled": "False", "Username": "someone", "HostUrl": "custom"}


# --- RetroArch keeps its behaviour --------------------------------------------------


def test_retroarch_settings() -> None:
    """RetroArch still gets the token, hardcore and leaderboards from the shared options."""
    settings = libretro_achievements.settings(
        _on(retroachievements__hardcore="1", retroachievements__leaderboards="1")
    )
    assert settings["cheevos_enable"] == "true"
    assert settings["cheevos_token"] == '"tok123"'
    assert settings[libretro_achievements.HARDCORE_SETTING] == "true"
    assert settings["cheevos_leaderboards_enable"] == "true"
    assert libretro_achievements.settings(_config())["cheevos_enable"] == "false"
