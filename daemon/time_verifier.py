"""NTP time verification to prevent time manipulation bypasses."""

from datetime import datetime, timezone
from typing import Optional
import logging
import ntplib
import socket
import sys
import os

# Add daemon directory to Python path for absolute imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from config import get_config

logger = logging.getLogger(__name__)


class TimeVerifier:
    """Verifies system time against NTP servers to prevent time manipulation."""

    def __init__(self):
        self._ntp_client = ntplib.NTPClient()
        self._last_verified: Optional[datetime] = None
        self._last_ntp_time: Optional[datetime] = None
        self._cached_valid = True

    @property
    def ntp_servers(self) -> list:
        """Get NTP servers from config."""
        return get_config().security.ntp_servers

    @property
    def max_time_diff(self) -> int:
        """Get max allowed time difference in seconds."""
        return get_config().security.max_time_diff_seconds

    def get_ntp_time(self) -> Optional[datetime]:
        """Query NTP servers for accurate time.

        Returns:
            datetime: Current time from NTP server, or None if all servers failed.
        """
        for server in self.ntp_servers:
            try:
                response = self._ntp_client.request(server, timeout=5)
                ntp_time = datetime.fromtimestamp(response.tx_time, tz=timezone.utc)
                logger.debug(f"Got NTP time from {server}: {ntp_time}")
                return ntp_time
            except (ntplib.NTPException, socket.gaierror, socket.timeout, OSError) as e:
                logger.warning(f"Failed to query NTP server {server}: {e}")
                continue

        logger.error("All NTP servers failed")
        return None

    def is_system_time_valid(self) -> bool:
        """Check if system time is reasonable compared to NTP time.

        Returns:
            bool: True if system time is valid or NTP is unreachable (fail-safe).
        """
        ntp_time = self.get_ntp_time()

        if ntp_time is None:
            # Network down - fail safe (trust system time but log)
            logger.warning("Could not verify time with NTP (network down?) - trusting system time")
            return True

        system_time = datetime.now(timezone.utc)
        diff = abs((ntp_time - system_time).total_seconds())

        if diff > self.max_time_diff:
            logger.error(
                f"Time manipulation detected! System: {system_time}, NTP: {ntp_time}, "
                f"Diff: {diff}s (max allowed: {self.max_time_diff}s)"
            )
            return False

        logger.debug(f"Time verification passed. Difference: {diff}s")
        self._last_verified = system_time
        self._last_ntp_time = ntp_time
        self._cached_valid = True
        return True

    def verify_at_lock_transitions(self) -> bool:
        """Verify time specifically at lock start/end.

        This is called when entering or exiting lock mode.
        MUST verify with NTP to prevent time manipulation.
        If network down, use cached verification or fail-safe block.

        Returns:
            bool: True if time is verified valid, False if manipulation detected.
        """
        ntp_time = self.get_ntp_time()

        if ntp_time is None:
            # Network down at transition - this is suspicious
            logger.warning("Network down during lock transition - using fail-safe (block)")

            # If we recently verified successfully, trust that
            if self._last_verified is not None:
                time_since_verify = (datetime.now(timezone.utc) - self._last_verified).total_seconds()
                if time_since_verify < 300:  # Verified within last 5 minutes
                    logger.info("Using cached time verification from recent check")
                    return self._cached_valid

            # No recent verification - fail-safe means block
            return False

        system_time = datetime.now(timezone.utc)
        diff = abs((ntp_time - system_time).total_seconds())

        if diff > self.max_time_diff:
            logger.error(
                f"Time manipulation detected at lock transition! "
                f"System: {system_time}, NTP: {ntp_time}, Diff: {diff}s"
            )
            self._cached_valid = False
            return False

        logger.info(f"Lock transition time verified. Difference: {diff}s")
        self._last_verified = system_time
        self._last_ntp_time = ntp_time
        self._cached_valid = True
        return True

    def get_verified_time(self) -> datetime:
        """Get current time, with periodic NTP verification.

        Returns:
            datetime: Current system time (after verification).
        """
        # Verify time periodically (every 5 minutes)
        if self._last_verified is None or \
           (datetime.now(timezone.utc) - self._last_verified).total_seconds() > 300:
            self.is_system_time_valid()

        return datetime.now()


# Global time verifier instance
_verifier: Optional[TimeVerifier] = None


def get_time_verifier() -> TimeVerifier:
    """Get the global time verifier instance."""
    global _verifier
    if _verifier is None:
        _verifier = TimeVerifier()
    return _verifier
