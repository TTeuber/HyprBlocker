"""Pure decision logic for the root enforcer — no I/O, no privilege, no clocks.

Everything here is a deterministic function of its inputs so the fail-closed
semantics (hardening R7) and the lock/settings asymmetry (spec phase 2) are
fully unit-testable without root, sockets, or a real ``/proc``.

The privileged wrappers in :mod:`enforcer.main` gather the inputs (monotonic
clock, boot_id, /proc scans, request files) and act on the verdicts returned
here (SIGKILL, file writes).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum

from daemon.enforcement_policy import EnforcementPolicy
from daemon.grants import policy as grant_policy

# Loosening changes (shorter lock, weaker policy) are delayed by this many hours
# before they apply (spec: 24-48h). Tightening changes always apply immediately.
DEFAULT_LOOSEN_DELAY_HOURS = 36.0


# ---------------------------------------------------------------------------
# R7 — fail-closed kill decision
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class GraceWindows:
    """Grace periods during which a stale heartbeat must NOT trigger kills.

    ``boot_grace_seconds`` is measured directly on CLOCK_MONOTONIC (which counts
    from boot), covering the window before the user daemon has had any chance to
    start. ``login_grace_seconds`` starts when a supported compositor session first
    appears.
    """

    boot_grace_seconds: float = 300.0
    login_grace_seconds: float = 120.0


@dataclass(frozen=True)
class HeartbeatObservation:
    """The last successfully *verified* attestation, as recorded by the enforcer.

    ``monotonic`` is the attester's CLOCK_MONOTONIC stamp; ``boot_id`` is the
    boot it was taken in. Both are compared against the enforcer's own current
    values — staleness is never measured on the wall clock (R7).
    """

    monotonic: float
    boot_id: str


@dataclass(frozen=True)
class KillDecision:
    kill: bool
    reason: str


def kill_decision(
    *,
    now_monotonic: float,
    boot_id: str,
    last_heartbeat: HeartbeatObservation | None,
    session_present: bool,
    session_started_monotonic: float | None,
    intended_enforcement_on: bool,
    grace: GraceWindows,
    stale_after_seconds: float,
) -> KillDecision:
    """Decide whether the fail-closed browser kill should fire this tick (R7).

    Kill **only** when the heartbeat is stale AND a user session is present AND
    enforcement is intentionally on AND no grace window applies. Every other
    combination suppresses the kill — a legally-off blocker or an idle machine
    must never produce false-positive kills.

    A heartbeat that was never seen, carries a foreign ``boot_id``, or claims a
    monotonic time in the enforcer's future all count as stale (fail closed on
    absence and on nonsense alike).
    """
    if not intended_enforcement_on:
        return KillDecision(False, "enforcement intentionally off")
    if not session_present:
        return KillDecision(False, "no user session present")
    if now_monotonic < grace.boot_grace_seconds:
        return KillDecision(False, "within post-boot grace window")
    if (
        session_started_monotonic is not None
        and now_monotonic - session_started_monotonic < grace.login_grace_seconds
    ):
        return KillDecision(False, "within post-login grace window")

    if last_heartbeat is None:
        return KillDecision(True, "no verified heartbeat ever observed")
    if last_heartbeat.boot_id != boot_id:
        return KillDecision(True, "last verified heartbeat is from a different boot")
    delta = now_monotonic - last_heartbeat.monotonic
    if delta < 0:
        return KillDecision(True, "heartbeat monotonic stamp is in the future (bogus)")
    if delta > stale_after_seconds:
        return KillDecision(True, f"heartbeat stale ({delta:.0f}s > {stale_after_seconds:.0f}s)")
    return KillDecision(False, "heartbeat fresh")


def should_kill_browsers(
    now_monotonic: float,
    boot_id: str,
    last_heartbeat: HeartbeatObservation | None,
    session_present: bool,
    intended_enforcement_on: bool,
    grace: GraceWindows,
    *,
    session_started_monotonic: float | None = None,
    stale_after_seconds: float = 90.0,
) -> bool:
    """Boolean convenience wrapper around :func:`kill_decision`."""
    return kill_decision(
        now_monotonic=now_monotonic,
        boot_id=boot_id,
        last_heartbeat=last_heartbeat,
        session_present=session_present,
        session_started_monotonic=session_started_monotonic,
        intended_enforcement_on=intended_enforcement_on,
        grace=grace,
        stale_after_seconds=stale_after_seconds,
    ).kill


# ---------------------------------------------------------------------------
# Lock / settings asymmetry (tighten now, loosen later)
# ---------------------------------------------------------------------------

class ChangeAction(StrEnum):
    """What to do with a settings/lock change request."""

    APPLY_NOW = "apply_now"  # tightening (or no-op): applied immediately
    DELAY = "delay"          # loosening: becomes a pending change after the delay


def _as_utc(dt: datetime | None) -> datetime | None:
    if dt is not None and dt.tzinfo is None:
        return dt.replace(tzinfo=UTC)
    return dt


def classify_lock_change(
    current_until: datetime | None, requested_until: datetime | None
) -> ChangeAction:
    """Classify a settings-lock change request (asymmetric semantics).

    Extending the lock (or creating one where none exists) is *tightening* and
    applies immediately. Shortening or clearing an existing lock is *loosening*
    and must go through the delayed pending path. Re-asserting the identical
    expiry is a no-op tighten. Naive datetimes are treated as UTC.
    """
    current = _as_utc(current_until)
    requested = _as_utc(requested_until)
    if requested is None:
        return ChangeAction.APPLY_NOW if current is None else ChangeAction.DELAY
    if current is None or requested >= current:
        return ChangeAction.APPLY_NOW
    return ChangeAction.DELAY


# Per-field loosening predicates for the enforcement policy. A change loosens if
# ANY field loosens; only an all-tightening (or no-op) request applies now.
def _policy_loosening_fields(
    current: EnforcementPolicy, requested: EnforcementPolicy
) -> list[str]:
    loosened: list[str] = []
    for toggle in (
        "browser_enforcement_enabled",
        "shutdown_prevention_enabled",
        "watchdog_enabled",
    ):
        if getattr(current, toggle) and not getattr(requested, toggle):
            loosened.append(toggle)
    if not set(requested.browsers) >= set(current.browsers):
        loosened.append("browsers")  # removing a binary from the kill-list
    if requested.heartbeat_interval_seconds > current.heartbeat_interval_seconds:
        loosened.append("heartbeat_interval_seconds")  # slower detection
    if requested.watchdog_count < current.watchdog_count:
        loosened.append("watchdog_count")
    return loosened


def classify_policy_change(
    current: EnforcementPolicy, requested: EnforcementPolicy
) -> ChangeAction:
    """Classify an enforcement-policy change request (asymmetric semantics).

    Tightening (enabling toggles, adding browsers to the kill-list, faster
    heartbeat, more watchdogs) applies immediately. If *any* field loosens, the
    whole request is delayed — a mixed request must not smuggle a loosening
    field in alongside a tightening one.
    """
    if _policy_loosening_fields(current, requested):
        return ChangeAction.DELAY
    return ChangeAction.APPLY_NOW


@dataclass(frozen=True)
class RequestVerdict:
    """Classification of a raw request dict from ``requests/settings/``."""

    action: ChangeAction
    kind: str  # "lock" | "policy"
    error: str | None = None
    loosened_fields: list[str] = field(default_factory=list)


def classify_request(
    request: dict,
    current_lock_until: datetime | None,
    current_policy: EnforcementPolicy,
    current_judge_policy: str | None = None,
    dev_mode: bool = False,
) -> RequestVerdict:
    """Classify a parsed request file. Malformed requests are rejected (error set).

    Request shapes (written by the user daemon into ``requests/settings/``):

    - ``{"type": "lock", "locked_until": "<ISO datetime>" | null}``
    - ``{"type": "policy", "policy": {<EnforcementPolicy fields>}}``
    - ``{"type": "judge_policy", "text": "<policy.md contents>"}``

    ``current_judge_policy`` is the active grant-judge policy text; ``None``
    means no custom policy file exists, i.e. the strict preset is in effect.
    ``dev_mode`` (pre-graduation) applies any *valid* judge-policy edit
    immediately — the delay exists to bind future-you, not to slow development.
    It does not touch lock or enforcement-policy requests.
    """
    kind = request.get("type")
    if kind == "lock":
        raw = request.get("locked_until")
        if raw is None:
            requested = None
        else:
            try:
                requested = datetime.fromisoformat(raw)
            except (TypeError, ValueError):
                return RequestVerdict(ChangeAction.DELAY, "lock", error=f"bad locked_until: {raw!r}")
        return RequestVerdict(classify_lock_change(current_lock_until, requested), "lock")

    if kind == "policy":
        body = request.get("policy")
        if not isinstance(body, dict):
            return RequestVerdict(ChangeAction.DELAY, "policy", error="missing policy body")
        known = EnforcementPolicy().__dict__.keys()
        try:
            requested_policy = EnforcementPolicy(
                **{k: v for k, v in body.items() if k in known}
            )
        except TypeError as e:
            return RequestVerdict(ChangeAction.DELAY, "policy", error=str(e))
        loosened = _policy_loosening_fields(current_policy, requested_policy)
        action = ChangeAction.DELAY if loosened else ChangeAction.APPLY_NOW
        return RequestVerdict(action, "policy", loosened_fields=loosened)

    if kind == "judge_policy":
        text = request.get("text")
        if not isinstance(text, str):
            return RequestVerdict(ChangeAction.DELAY, "judge_policy", error="missing policy text")
        errors = grant_policy.validate_policy_text(text)
        if errors:
            return RequestVerdict(ChangeAction.DELAY, "judge_policy", error="; ".join(errors))
        if dev_mode:
            return RequestVerdict(ChangeAction.APPLY_NOW, "judge_policy")
        current = (
            current_judge_policy
            if current_judge_policy is not None
            else grant_policy.default_policy_text()
        )
        decision = grant_policy.classify_policy_edit(current, text)
        action = ChangeAction.APPLY_NOW if decision.apply_immediately else ChangeAction.DELAY
        return RequestVerdict(action, "judge_policy")

    return RequestVerdict(ChangeAction.DELAY, str(kind), error=f"unknown request type: {kind!r}")
