"""Tests for compositor window discovery and close commands."""

import asyncio
import json

from daemon.hyprland_monitor import CompositorMonitor


class _Process:
    def __init__(
        self,
        payload: list[dict] | None = None,
        returncode: int = 0,
        stderr: bytes = b"",
        stdout: bytes | None = None,
    ):
        self.returncode = returncode
        self._stdout = stdout if stdout is not None else json.dumps(payload).encode()
        self._stderr = stderr

    async def communicate(self):
        return self._stdout, self._stderr


def test_normalizes_niri_windows(monkeypatch):
    commands = []

    async def fake_create_subprocess_exec(*command, **kwargs):
        commands.append(command)
        return _Process([{"id": 42, "app_id": "firefox", "pid": 1234, "title": "Browser"}])

    monkeypatch.setenv("NIRI_SOCKET", "/run/user/1000/niri.sock")
    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_create_subprocess_exec)

    windows = asyncio.run(CompositorMonitor(None).get_all_windows())

    assert commands == [("niri", "msg", "-j", "windows")]
    assert windows[0]["class"] == "firefox"
    assert windows[0]["address"] == 42
    assert windows[0]["_compositor"] == "niri"


def test_falls_back_to_niri_without_socket_hint(monkeypatch):
    commands = []

    async def fake_create_subprocess_exec(*command, **kwargs):
        commands.append(command)
        if command[0] == "hyprctl":
            return _Process([], returncode=1, stderr=b"not running")
        return _Process([{"id": 7, "app_id": None, "pid": 1234}])

    monkeypatch.delenv("NIRI_SOCKET", raising=False)
    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_create_subprocess_exec)

    windows = asyncio.run(CompositorMonitor(None).get_all_windows())

    assert commands == [
        ("hyprctl", "clients", "-j"),
        ("niri", "msg", "-j", "windows"),
    ]
    assert windows[0]["class"] == ""


def test_preserves_hyprland_window_shape_and_close_command(monkeypatch):
    commands = []

    async def fake_create_subprocess_exec(*command, **kwargs):
        commands.append(command)
        if command[:2] == ("hyprctl", "clients"):
            return _Process([{"address": "0x1", "class": "discord", "pid": 99}])
        return _Process([])

    monkeypatch.delenv("NIRI_SOCKET", raising=False)
    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_create_subprocess_exec)
    monitor = CompositorMonitor(None)

    windows = asyncio.run(monitor.get_all_windows())
    closed = asyncio.run(monitor.close_window(windows[0]))

    assert windows[0]["class"] == "discord"
    assert windows[0]["address"] == "0x1"
    assert commands[-1] == ("hyprctl", "dispatch", "closewindow", "address:0x1")
    assert closed is True


def test_closes_niri_window_by_id(monkeypatch):
    commands = []

    async def fake_create_subprocess_exec(*command, **kwargs):
        commands.append(command)
        return _Process([])

    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_create_subprocess_exec)

    closed = asyncio.run(
        CompositorMonitor(None).close_window(
            {"id": 42, "address": 42, "class": "firefox", "_compositor": "niri"}
        )
    )

    assert closed is True
    assert commands == [("niri", "msg", "action", "close-window", "--id", "42")]


def test_raises_when_both_compositors_are_unavailable(monkeypatch):
    async def fake_create_subprocess_exec(*command, **kwargs):
        raise FileNotFoundError(command[0])

    monkeypatch.delenv("NIRI_SOCKET", raising=False)
    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_create_subprocess_exec)

    monitor = CompositorMonitor(None)
    try:
        asyncio.run(monitor.get_all_windows())
    except RuntimeError as error:
        assert "command not found" in str(error)
    else:
        raise AssertionError("expected compositor IPC failure")


def test_raises_on_malformed_compositor_output(monkeypatch):
    async def fake_create_subprocess_exec(*command, **kwargs):
        return _Process(stdout=b"{not-json")

    monkeypatch.setenv("NIRI_SOCKET", "/run/user/1000/niri.sock")
    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_create_subprocess_exec)

    monitor = CompositorMonitor(None)
    try:
        asyncio.run(monitor.get_all_windows())
    except RuntimeError as error:
        assert "Invalid niri window data" in str(error)
    else:
        raise AssertionError("expected malformed compositor output failure")


def test_ignores_niri_windows_without_id(monkeypatch):
    async def fake_create_subprocess_exec(*command, **kwargs):
        return _Process([{"app_id": "firefox", "pid": 1234}])

    monkeypatch.setenv("NIRI_SOCKET", "/run/user/1000/niri.sock")
    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_create_subprocess_exec)

    assert asyncio.run(CompositorMonitor(None).get_all_windows()) == []
