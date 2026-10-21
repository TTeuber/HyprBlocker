"""Tests for compositor window discovery and close commands."""

import asyncio
import json

from daemon.hyprland_monitor import CompositorMonitor


class _Process:
    def __init__(self, payload: list[dict], returncode: int = 0):
        self.returncode = returncode
        self._payload = payload

    async def communicate(self):
        return json.dumps(self._payload).encode(), b""


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
