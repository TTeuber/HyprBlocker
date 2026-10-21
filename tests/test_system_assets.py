"""Tests for the canonical system-asset renderers (daemon.system_assets)."""

import json

import pytest

from daemon import system_assets as sa


def test_render_unknown_asset_raises():
    with pytest.raises(KeyError):
        sa.render("nope")


def test_all_named_assets_render_nonempty():
    for name in [
        "user-unit",
        "enforcer-unit",
        "breakglass-unit",
        "breakglass-timer",
        "chrome-manifest",
        "firefox-manifest",
        "pacman-sudoers",
    ]:
        assert sa.render(name).strip()


def test_user_unit_uses_isolated_interpreter_and_root_layout():
    unit = sa.user_unit()
    assert "-I -m daemon.main" in unit  # isolated mode closes PYTHONPATH injection
    assert "HYPRBLOCKER_LAYOUT=root" in unit
    assert sa.VENV_PYTHON in unit
    assert "PYTHONPATH=" in unit  # explicitly cleared
    assert "After=graphical-session.target" in unit
    assert "BindsTo=graphical-session.target" in unit
    assert "WantedBy=graphical-session.target" in unit


def test_enforcer_unit_runs_as_root_isolated():
    unit = sa.enforcer_unit()
    assert "User=root" in unit
    assert "-I -m enforcer.main" in unit
    assert "Restart=always" in unit


def test_breakglass_is_independent_of_enforcer():
    # The break-glass runner must be its own entry point, not enforcer.main.
    unit = sa.breakglass_unit()
    assert "enforcer.breakglass_runner" in unit
    assert "enforcer.main" not in unit


def test_chrome_manifest_is_valid_json_with_pinned_id():
    data = json.loads(sa.chrome_manifest())
    assert data["name"] == "com.hyprblocker.host"
    assert data["path"] == sa.NATIVE_HOST_PATH
    assert data["allowed_origins"] == [f"chrome-extension://{sa.EXTENSION_ID}/"]


def test_firefox_manifest_is_valid_json_with_pinned_id():
    data = json.loads(sa.firefox_manifest())
    assert data["allowed_extensions"] == [sa.FIREFOX_EXTENSION_ID]
    assert data["path"] == sa.NATIVE_HOST_PATH


def test_pinned_extension_id_is_frozen():
    # This ID is baked into every browser's native-messaging manifest. If it ever
    # changes, native messaging silently fails and the daemon kills every browser.
    assert sa.EXTENSION_ID == "djngojgikpdalhbiimclpdcfehcphcim"


def test_pacman_sudoers_is_pinned_to_syu_only():
    line = sa.pacman_sudoers()
    assert "/usr/bin/pacman -Syu" in line
    # No arbitrary package files or extra args that could widen the carve-out.
    assert " -U" not in line
    assert "%hyprblocker" in line


def test_cli_render(capsys):
    rc = sa.main(["prog", "user-unit"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "ExecStart" in out


def test_cli_bad_args():
    assert sa.main(["prog"]) == 2
    assert sa.main(["prog", "bogus"]) == 2
