"""The root enforcer loop — privileged wiring around the pure logic modules.

NEVER run this by hand on a dev machine: it is started only by
``hyprblocker-enforcer.service`` (root, ``HYPRBLOCKER_LAYOUT=root``) after
``install-root.sh``. :func:`main` refuses to run unless layout is ``root`` AND
euid is 0, so an accidental invocation under the user layout exits immediately.

Each tick the loop:

1. verifies the previous heartbeat challenge's echo (R4) and issues a new one;
2. runs the fail-closed kill decision (R7) and, when it fires, SIGKILLs the
   user's browsers found by its own /proc scan (R8) — never trusting the daemon;
3. repairs the system unit + native-messaging manifests (service_enforcer);
4. consumes settings/lock requests from ``requests/settings/`` with asymmetric
   semantics (tighten now, loosen after a delay) and applies matured pending
   loosenings, NTP-stamped via the root-tier settings_lock time source (R1);
5. refreshes ``secure/enforcer_state.json`` with a fresh wall/monotonic/boot_id
   snapshot so the user daemon can observe enforcer liveness (R6).

INTEGRATION HOOKS (shared files owned by the integrator — do not wire here):

- daemon/main.py (root layout only): each daemon heartbeat interval, call
  ``nonce = enforcer.heartbeat.read_challenge()`` and, if a nonce is present,
  ``enforcer.heartbeat.write_echo(nonce)``. Both are unprivileged-safe.
- daemon/main.py (R6 mesh gating): spawn the watchdog mesh under root layout
  ONLY if ``paths.enforcer_state_path()`` is absent or its ``monotonic``/
  ``written_at`` is stale beyond ~3x heartbeat_interval; surface that condition
  as ``enforcer_down`` in ``/api/status``.
- daemon/api/routes/settings.py (root layout): instead of writing lock/policy
  fields directly, drop request files into ``paths.requests_dir()/"settings"``
  using the shapes documented in ``enforcer.logic.classify_request``.
- /api/status: read ``paths.enforcer_state_path()`` for ``enforcement_tier``,
  ``dev_mode``, and lock fields.
"""

from __future__ import annotations

import json
import logging
import os
import sys
import time
from dataclasses import asdict
from datetime import UTC, datetime, timedelta
from pathlib import Path

from daemon import paths, service_enforcer, settings_lock
from daemon.enforcement_policy import EnforcementPolicy, load_policy, write_policy
from daemon.grants import policy as grant_policy
from enforcer import heartbeat, logic, proc_scan

logger = logging.getLogger(__name__)

PROC = Path("/proc")

# Loop cadence bounds (seconds). The policy's heartbeat interval drives the
# tick, clamped so a corrupt policy can neither spin nor stall the enforcer.
MIN_TICK_SECONDS = 5.0
MAX_TICK_SECONDS = 120.0

# The compositor process whose presence defines "a user session exists" (R7).
SESSION_PROCESS_NAMES = ["Hyprland", "niri"]


def _pending_changes_path() -> Path:
    return paths.secure_dir() / "pending_changes.json"


def _settings_requests_dir() -> Path:
    return paths.requests_dir() / "settings"


def _target_uid_from_files() -> int | None:
    """Best-effort login uid from ownership of the root-created user state dir.

    Only a *fallback* for the case where no compositor is running (so the /proc
    session scan yields nothing). Never used to gate a kill — a user cannot make
    this suppress enforcement, because the kill path derives its uid from the
    live compositor instead (see :meth:`Enforcer.tick`)."""
    for candidate in (paths.user_dir(), paths.config_path(), paths.database_path()):
        try:
            uid = candidate.stat().st_uid
        except OSError:
            continue
        if uid != 0:
            return uid
    return None


def _atomic_write(target: Path, text: str, mode: int = 0o644) -> None:
    paths.ensure_dir(target.parent)
    tmp = target.with_suffix(target.suffix + ".tmp")
    tmp.write_text(text)
    tmp.chmod(mode)
    tmp.replace(target)


class Enforcer:
    """Per-boot enforcer state machine. One instance lives for the service's life."""

    def __init__(self) -> None:
        self._boot_id = heartbeat.read_boot_id()
        self._expected_exes = heartbeat.resolve_expected_exes()
        self._issued_nonce: str | None = None
        self._last_verified: logic.HeartbeatObservation | None = None
        self._session_started_monotonic: float | None = None
        self._session_was_present = False
        self._ntp_cache: datetime | None = None  # per-tick cache

    # -- heartbeat ---------------------------------------------------------

    def _check_heartbeat(self, now_monotonic: float, policy: EnforcementPolicy) -> heartbeat.AttestationVerdict:
        echo = heartbeat.read_echo()
        pid_info = heartbeat.read_pid_info(PROC, echo.pid) if echo else None
        verdict = heartbeat.verify_attestation(
            self._issued_nonce,
            echo,
            self._boot_id,
            now_monotonic,
            pid_info,
            expected_exes=self._expected_exes,
            max_age_seconds=max(3.0 * policy.heartbeat_interval_seconds, 90.0),
        )
        if verdict.ok and echo is not None:
            self._last_verified = logic.HeartbeatObservation(
                monotonic=echo.monotonic, boot_id=echo.boot_id
            )
        else:
            logger.debug("Heartbeat not verified: %s", verdict.reason)
        return verdict

    def _issue_challenge(self) -> None:
        self._issued_nonce = heartbeat.new_challenge()
        try:
            heartbeat.write_challenge(self._issued_nonce, self._boot_id)
        except OSError as e:
            logger.error("Cannot publish heartbeat challenge: %s", e)

    # -- settings/lock requests (asymmetric) -------------------------------

    def _ntp_now(self) -> datetime | None:
        if self._ntp_cache is None:
            # Root-tier time source (R1): hardcoded server list inside
            # settings_lock, never user-writable config. Private by design —
            # settings_lock is the single owner of root NTP.
            self._ntp_cache = settings_lock._root_ntp_now()
        return self._ntp_cache

    def _write_lock(self, locked_until: datetime | None) -> None:
        stamp = self._ntp_now()
        _atomic_write(
            paths.lock_path(),
            json.dumps(
                {
                    "locked_until": locked_until.isoformat() if locked_until else None,
                    "ntp_stamp": stamp.isoformat() if stamp else None,
                },
                indent=2,
            ),
        )

    def _apply_request(self, request: dict) -> None:
        if request.get("type") == "lock":
            raw = request.get("locked_until")
            self._write_lock(datetime.fromisoformat(raw) if raw else None)
        elif request.get("type") == "policy":
            # Merge onto the CURRENT policy — a request that names only the fields
            # it changes must not silently reset every omitted field to its
            # dataclass default (which could, e.g., re-enable a disabled toggle).
            known = EnforcementPolicy().__dict__.keys()
            body = {k: v for k, v in request.get("policy", {}).items() if k in known}
            current = asdict(load_policy())
            current.update(body)
            write_policy(EnforcementPolicy(**current))
        elif request.get("type") == "judge_policy":
            # Re-validate at apply time — a matured pending entry must not land
            # an invalid document (the judge would silently fall back to strict,
            # but the file would misrepresent the active policy).
            text = request.get("text")
            if isinstance(text, str) and not grant_policy.validate_policy_text(text):
                _atomic_write(paths.policy_path(), text)

    def _process_settings_requests(self, policy: EnforcementPolicy) -> None:
        req_dir = _settings_requests_dir()
        try:
            files = sorted(req_dir.glob("*.json"))
        except OSError:
            return
        if not files:
            return
        current_lock = settings_lock.read_lock_until()
        current_judge_policy = grant_policy.load_policy_text()
        dev_mode = paths.is_dev_mode()
        for f in files:
            try:
                request = json.loads(f.read_text())
            except (OSError, json.JSONDecodeError):
                logger.error("Dropping unreadable request %s", f)
                f.unlink(missing_ok=True)
                continue
            verdict = logic.classify_request(
                request,
                current_lock,
                policy,
                current_judge_policy=current_judge_policy,
                dev_mode=dev_mode,
            )
            if verdict.error:
                logger.warning("Rejecting request %s: %s", f.name, verdict.error)
            elif verdict.action is logic.ChangeAction.APPLY_NOW:
                logger.info("Applying tightening %s request %s", verdict.kind, f.name)
                self._apply_request(request)
            else:
                ntp = self._ntp_now()
                if ntp is None:
                    # Fail closed: a loosening cannot even be *scheduled*
                    # without verified time. Leave the request for next tick.
                    logger.warning("NTP down — deferring loosening request %s", f.name)
                    continue
                apply_at = ntp + timedelta(hours=logic.DEFAULT_LOOSEN_DELAY_HOURS)
                self._schedule_pending(request, apply_at)
                logger.warning(
                    "Loosening %s request %s scheduled for %s (fields: %s)",
                    verdict.kind, f.name, apply_at.isoformat(), verdict.loosened_fields,
                )
            f.unlink(missing_ok=True)

    def _schedule_pending(self, request: dict, apply_at: datetime) -> None:
        pending = self._load_pending()
        pending.append({"request": request, "apply_at": apply_at.isoformat()})
        _atomic_write(_pending_changes_path(), json.dumps({"pending": pending}, indent=2))

    def _load_pending(self) -> list[dict]:
        try:
            data = json.loads(_pending_changes_path().read_text())
            return list(data.get("pending", []))
        except (OSError, json.JSONDecodeError, TypeError):
            return []

    def _apply_matured_pending(self) -> None:
        pending = self._load_pending()
        if not pending:
            return
        ntp = self._ntp_now()
        if ntp is None:
            return  # fail closed: no verified time, nothing loosens
        keep: list[dict] = []
        for entry in pending:
            try:
                apply_at = datetime.fromisoformat(entry["apply_at"])
            except (KeyError, TypeError, ValueError):
                logger.error("Dropping malformed pending entry: %r", entry)
                continue
            if apply_at.tzinfo is None:
                apply_at = apply_at.replace(tzinfo=UTC)
            if ntp >= apply_at:
                logger.warning("Applying matured loosening: %r", entry.get("request"))
                self._apply_request(entry.get("request") or {})
            else:
                keep.append(entry)
        if keep != pending:
            _atomic_write(_pending_changes_path(), json.dumps({"pending": keep}, indent=2))

    # -- liveness snapshot (R6) --------------------------------------------

    def _write_state(
        self,
        now_monotonic: float,
        hb_verdict: heartbeat.AttestationVerdict,
        decision: logic.KillDecision,
        killed: int,
        policy: EnforcementPolicy,
    ) -> None:
        lock_until = settings_lock.read_lock_until()
        snapshot = {
            "written_at": datetime.now(UTC).isoformat(),
            "monotonic": now_monotonic,
            "boot_id": self._boot_id,
            "heartbeat_ok": hb_verdict.ok,
            "heartbeat_reason": hb_verdict.reason,
            "kill_fired": decision.kill,
            "kill_reason": decision.reason,
            "killed_count": killed,
            "locked_until": lock_until.isoformat() if lock_until else None,
            "dev_mode": paths.is_dev_mode(),
            "enforcement_tier": "root",
            "policy": asdict(policy),
        }
        try:
            _atomic_write(paths.enforcer_state_path(), json.dumps(snapshot, indent=2))
        except OSError as e:
            logger.error("Cannot write enforcer state: %s", e)

    # -- one tick ----------------------------------------------------------

    def tick(self) -> None:
        self._ntp_cache = None
        now_monotonic = time.monotonic()
        policy = load_policy()

        # Session presence AND the target uid both come from the live compositor
        # in /proc — a source the user cannot delete while the session runs — so a
        # missing/altered state file can never suppress a kill (review: fail-open
        # uid). Fall back to file ownership only for the no-session case.
        session_uid = proc_scan.find_session_uid(PROC, SESSION_PROCESS_NAMES)
        session = session_uid is not None
        uid = session_uid if session_uid is not None else _target_uid_from_files()
        if session and not self._session_was_present:
            self._session_started_monotonic = now_monotonic
        self._session_was_present = session

        hb_verdict = self._check_heartbeat(now_monotonic, policy)
        self._issue_challenge()

        decision = logic.kill_decision(
            now_monotonic=now_monotonic,
            boot_id=self._boot_id,
            last_heartbeat=self._last_verified,
            session_present=session,
            session_started_monotonic=self._session_started_monotonic,
            intended_enforcement_on=policy.browser_enforcement_enabled,
            grace=logic.GraceWindows(),
            stale_after_seconds=max(3.0 * policy.heartbeat_interval_seconds, 90.0),
        )
        killed = 0
        if decision.kill:
            # decision.kill only fires when a session is present, so uid is the
            # compositor's uid here. If it somehow could not be pinned, pass None
            # to match any non-root browser rather than let the kill no-op.
            pids = proc_scan.find_browser_pids(PROC, policy.browsers, uid)
            if pids:
                logger.warning("Fail-closed kill (%s): pids %s", decision.reason, pids)
            killed = proc_scan.kill_pids(pids)

        if policy.shutdown_prevention_enabled:
            service_enforcer.ensure_service_intact()
            service_enforcer.repair_native_manifests()

        self._process_settings_requests(policy)
        self._apply_matured_pending()
        self._write_state(now_monotonic, hb_verdict, decision, killed, policy)

    def tick_interval(self) -> float:
        try:
            interval = float(load_policy().heartbeat_interval_seconds)
        except Exception:
            interval = 30.0
        return min(max(interval, MIN_TICK_SECONDS), MAX_TICK_SECONDS)


def main() -> int:
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s"
    )
    if paths.layout() != "root":
        logger.error(
            "Refusing to run: layout is %r, not 'root'. The enforcer only runs "
            "from the /opt install via hyprblocker-enforcer.service.",
            paths.layout(),
        )
        return 2
    if os.geteuid() != 0:
        logger.error("Refusing to run: euid=%d, root required.", os.geteuid())
        return 2

    logger.info("Root enforcer starting (boot_id=%s)", heartbeat.read_boot_id())
    enforcer = Enforcer()
    while True:
        try:
            enforcer.tick()
        except Exception:
            logger.exception("Enforcer tick failed; continuing")
        time.sleep(enforcer.tick_interval())


if __name__ == "__main__":
    sys.exit(main())
