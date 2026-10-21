"""Tests for the fail-closed uid handling added to enforcer.proc_scan (review)."""

from pathlib import Path

from enforcer import proc_scan


def _mkproc(root: Path, pid: int, exe: str, uid: int) -> None:
    d = root / str(pid)
    d.mkdir(parents=True)
    # Simulate /proc/<pid>/exe as a symlink to the binary path.
    binpath = root / "bin" / Path(exe).name
    binpath.parent.mkdir(parents=True, exist_ok=True)
    binpath.write_text("")
    (d / "exe").symlink_to(binpath)
    (d / "status").write_text(f"Name:\t{Path(exe).name}\nUid:\t{uid}\t{uid}\t{uid}\t{uid}\n")


def test_find_session_uid_returns_non_root_compositor_uid(tmp_path):
    _mkproc(tmp_path, 100, "/usr/bin/Hyprland", uid=1000)
    _mkproc(tmp_path, 101, "/usr/bin/firefox", uid=1000)
    assert proc_scan.find_session_uid(tmp_path, ["Hyprland"]) == 1000


def test_find_session_uid_supports_niri(tmp_path):
    _mkproc(tmp_path, 100, "/usr/bin/niri", uid=1000)
    assert proc_scan.find_session_uid(tmp_path, ["Hyprland", "niri"]) == 1000


def test_find_session_uid_ignores_root_compositor(tmp_path):
    _mkproc(tmp_path, 100, "/usr/bin/Hyprland", uid=0)
    assert proc_scan.find_session_uid(tmp_path, ["Hyprland"]) is None


def test_find_session_uid_none_when_absent(tmp_path):
    _mkproc(tmp_path, 101, "/usr/bin/firefox", uid=1000)
    assert proc_scan.find_session_uid(tmp_path, ["Hyprland"]) is None


def test_find_browser_pids_specific_uid(tmp_path):
    _mkproc(tmp_path, 200, "/usr/bin/firefox", uid=1000)
    _mkproc(tmp_path, 201, "/usr/bin/firefox", uid=1001)
    assert proc_scan.find_browser_pids(tmp_path, ["firefox"], 1000) == [200]


def test_find_browser_pids_none_uid_matches_any_non_root(tmp_path):
    # Fail-closed fallback: uid unknown ⇒ match any non-root browser, but never root.
    _mkproc(tmp_path, 200, "/usr/bin/firefox", uid=1000)
    _mkproc(tmp_path, 201, "/usr/bin/firefox", uid=1001)
    _mkproc(tmp_path, 202, "/usr/bin/firefox", uid=0)  # root browser — not killed
    assert proc_scan.find_browser_pids(tmp_path, ["firefox"], None) == [200, 201]
