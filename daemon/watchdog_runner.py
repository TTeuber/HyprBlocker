#!/usr/bin/env python3
"""Watchdog process entry point.

This script runs as an independent process, monitoring the daemon and sibling
watchdogs. It's spawned by WatchdogManager and can also respawn itself.
"""

import argparse
import logging
import os
import sys

# Add daemon directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from watchdog import Watchdog

# Set up logging to file
log_dir = os.path.expanduser("~/.config/website-blocker")
os.makedirs(log_dir, exist_ok=True)
log_file = os.path.join(log_dir, "watchdog.log")

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(log_file),
    ]
)

logger = logging.getLogger(__name__)


def main():
    parser = argparse.ArgumentParser(description="Watchdog process for website blocker daemon")
    parser.add_argument("--name", required=True, help="Obfuscated process name")
    parser.add_argument("--port", type=int, default=8765, help="Daemon port")
    args = parser.parse_args()

    logger.info(f"Starting watchdog: name={args.name}, port={args.port}, pid={os.getpid()}")

    try:
        watchdog = Watchdog(name=args.name, daemon_port=args.port)
        watchdog.run()
    except Exception as e:
        logger.error(f"Watchdog crashed: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
