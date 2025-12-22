#!/usr/bin/env python3
"""
Native messaging host for Website Blocker browser extension.
This script provides the browser process ID to the extension.
"""

import json
import os
import struct
import sys


def send_message(message: dict) -> None:
    """Send a message to the browser extension.

    Args:
        message: Dictionary to send as JSON
    """
    encoded = json.dumps(message).encode('utf-8')
    sys.stdout.buffer.write(struct.pack('I', len(encoded)))
    sys.stdout.buffer.write(encoded)
    sys.stdout.buffer.flush()


def read_message() -> dict | None:
    """Read a message from the browser extension.

    Returns:
        Parsed JSON message or None if no message available
    """
    # Read message length (4 bytes)
    raw_length = sys.stdin.buffer.read(4)
    if not raw_length:
        return None

    # Unpack message length
    length = struct.unpack('I', raw_length)[0]

    # Read message content
    message = sys.stdin.buffer.read(length).decode('utf-8')
    return json.loads(message)


def get_parent_pid() -> int:
    """Get the parent process ID (the browser).

    Returns:
        Parent process ID
    """
    return os.getppid()


def main() -> None:
    """Main loop for the native messaging host."""
    while True:
        try:
            message = read_message()
            if message is None:
                break

            if message.get('action') == 'get_pid':
                pid = get_parent_pid()
                send_message({'pid': pid})

            elif message.get('action') == 'ping':
                send_message({'status': 'pong'})

            else:
                send_message({'error': f"Unknown action: {message.get('action')}"})

        except Exception as e:
            send_message({'error': str(e)})
            break


if __name__ == '__main__':
    main()
