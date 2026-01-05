# Technical Concepts: Daemon Startup and Native Messaging

This document explains the technical concepts behind two critical fixes made to the Website Blocker application.

## Table of Contents
1. [Issue 1: Daemon Startup Ordering](#issue-1-daemon-startup-ordering)
2. [Issue 2: Native Messaging and Extension IDs](#issue-2-native-messaging-and-extension-ids)

---

## Issue 1: Daemon Startup Ordering

### The Problem

After a system reboot, the daemon started but didn't enforce browser blocking until after running `systemctl --user restart website-blocker.service`.

### Root Cause: Systemd Targets and Dependencies

#### What is systemd?

**systemd** is the init system used by most Linux distributions. It manages system services (daemons) and controls when they start, stop, and in what order.

Services are defined by **unit files** (ending in `.service`) that contain:
- **Dependencies**: What must start before this service
- **Triggers**: When this service should start
- **Execution details**: How to run the service

#### Systemd Targets

A **target** is a systemd unit that groups related services together. Think of it as a milestone in the boot process.

Common targets:
- `network.target` - Basic networking is available
- `default.target` - System has reached the default runlevel
- `graphical.target` - GUI is available

For Wayland compositors like Hyprland, systemd creates session-specific targets:
- `wayland-session@hyprland.desktop.target` - Hyprland session is fully initialized

#### The Original Configuration

The daemon's systemd service originally had:

```ini
[Unit]
After=network.target

[Install]
WantedBy=default.target
```

This means:
- **After=network.target**: Start after network is available
- **WantedBy=default.target**: Auto-start with the user session

#### Why This Failed

The daemon depends on **Hyprland** being fully initialized because it uses `hyprctl` (Hyprland's control utility) to:
1. List all open windows
2. Find browser windows by their window class
3. Get the process ID (PID) of each browser window

**Timeline of what happened:**
```
1. User logs in
2. systemd starts default.target services
3. Daemon starts (network.target is ready)
4. Daemon calls hyprctl clients -j
5. ERROR: Hyprland isn't running yet!
6. hyprctl returns empty result
7. Daemon thinks: "No browsers open"
8. Meanwhile... Hyprland starts
9. User opens browser
10. Daemon still can't detect it (hyprctl now works, but daemon already initialized)
```

The daemon started **too early** - before Hyprland was ready.

#### The Fix

Change the systemd dependencies to wait for Hyprland:

```ini
[Unit]
After=wayland-session@hyprland.desktop.target
BindsTo=wayland-session@hyprland.desktop.target

[Install]
WantedBy=wayland-session@hyprland.desktop.target
```

**What each directive does:**

- **After=wayland-session@hyprland.desktop.target**
  - "Don't start until Hyprland session is fully initialized"
  - Ensures hyprctl will work when daemon starts

- **BindsTo=wayland-session@hyprland.desktop.target**
  - "My lifecycle is bound to Hyprland's session"
  - If Hyprland stops (logout), daemon stops too
  - Prevents daemon from running without Hyprland

- **WantedBy=wayland-session@hyprland.desktop.target**
  - "Auto-start when Hyprland session starts"
  - Creates a symlink in `~/.config/systemd/user/wayland-session@hyprland.desktop.target.wants/`

#### Key Concepts

**Service Ordering**
- `After=` only controls *when* a service starts, not *if* it starts
- Without `After=`, services can start in parallel
- Race conditions occur when services start in the wrong order

**Service Binding**
- `BindsTo=` creates a tight coupling between services
- Useful for services that are useless without their dependency
- Example: A Hyprland-specific daemon is useless if Hyprland isn't running

**Target Selection**
- Generic targets like `default.target` start very early
- Specific targets like `wayland-session@hyprland.desktop.target` start later
- Always use the most specific target that matches your dependency

#### Verification

Check where your service is linked:
```bash
ls -l ~/.config/systemd/user/*.target.wants/website-blocker.service
```

After the fix, you should see:
```
wayland-session@hyprland.desktop.target.wants/website-blocker.service
```

---

## Issue 2: Native Messaging and Extension IDs

### The Problem

Browsers with the extension installed were still being killed. The extension showed a 10-digit PID instead of a normal 5-digit PID.

### Root Cause: Native Messaging Configuration

#### What is Native Messaging?

**Native messaging** allows browser extensions to communicate with native applications (programs running outside the browser).

The flow:
```
Browser Extension → Native Messaging → Native Host (Python script) → OS
```

For Website Blocker, we use native messaging to get the **real browser process ID**.

#### Why Do We Need the Browser PID?

The daemon needs to match PIDs between two sources:

1. **Extension heartbeat**: PID reported by the extension
2. **Hyprland windows**: PID of actual browser window

If these PIDs match → browser is compliant (has extension)
If they don't match → browser killed (no extension)

#### The Challenge: Getting the Right PID

Browser extensions run in a sandboxed environment. When you call `process.pid` in JavaScript, you get the PID of the extension process, **not** the browser window process.

**Why this matters:**
- Hyprland reports the main browser window's PID
- The extension's sandbox PID is different
- These PIDs won't match!

**Solution:** Use native messaging to run a Python script that calls `os.getppid()` to get its parent process PID (the actual browser).

#### The Native Messaging Setup

Native messaging requires two components:

**1. Manifest File** (JSON)
Located at: `~/.config/chromium/NativeMessagingHosts/com.websiteblocker.host.json`

```json
{
  "name": "com.websiteblocker.host",
  "description": "Website Blocker Native Host",
  "path": "/path/to/host.py",
  "type": "stdio",
  "allowed_origins": [
    "chrome-extension://EXTENSION_ID_HERE/"
  ]
}
```

**2. Host Script** (Python)
The script that runs when the extension connects:

```python
#!/usr/bin/env python3
import os

# Get parent process ID (the browser)
pid = os.getppid()

# Send back to extension
send_message({'pid': pid})
```

#### The Critical Field: `allowed_origins`

This field controls **which extensions** can connect to the native host.

**Security model:**
- Native hosts have full system access (run arbitrary code)
- Browser must verify the extension is authorized
- Only extensions listed in `allowed_origins` can connect

#### The Bug: Wildcard Patterns

Our original manifest used:
```json
"allowed_origins": ["chrome-extension://*/"]
```

This looks reasonable - "allow any extension" - but **Chromium does not support wildcards** in `allowed_origins`.

From Chrome's documentation:
> "allowed_origins values can't contain wildcards. Each extension must be explicitly listed."

**What happened:**
1. Extension tried to connect to native host
2. Browser checked: "Is this extension ID in allowed_origins?"
3. Found: `chrome-extension://*/`
4. Extension's actual ID: `chrome-extension://abcd1234efgh5678/`
5. Browser: ❌ "No match - connection denied"
6. Extension never received the real PID

#### The Fallback PID Problem

When native messaging fails, the extension uses a fallback:

```javascript
browserPID = hashCode(chrome.runtime.id + Date.now());
```

This generates a **hash-based PID** like `1497655261` (10 digits).

**Why 10 digits?**
- Real Linux PIDs: 5-7 digits (typically max PID is 32768 or 4194304)
- Hash output: Can be much larger (JavaScript integer)
- This immediately tells us native messaging failed

**The mismatch:**
```
Extension reports: PID 1497655261 (hash)
Hyprland reports: PID 14468 (real browser)
Daemon: ❌ "PIDs don't match - kill browser!"
```

#### Extension IDs in Chrome

When you load an unpacked extension in Chrome:
- Chrome generates a **random extension ID**
- Example: `abcdefghijklmnop` (16 characters, a-p)
- This ID changes if you remove and re-add the extension
- Makes it impossible to pre-configure in native messaging manifest

#### The Solution: Stable Extension IDs

Add a `"key"` field to the extension's `manifest.json`:

```json
{
  "manifest_version": 3,
  "key": "MIIBIjANBgkqhkiG9w0BAQEFAAOCAQ8AMIIBCgKCAQEA...",
  "name": "Website Blocker",
  ...
}
```

**How it works:**

1. **Key Generation**
   - Generate an RSA keypair
   - Extract the public key
   - Base64-encode it
   - Put it in manifest.json

2. **Extension ID Derivation**
   - Chrome takes the public key
   - Computes SHA256 hash
   - Takes first 128 bits (16 bytes)
   - Encodes as a-p (not a-z, to avoid offensive words)
   - Result: stable, deterministic extension ID

3. **Benefits**
   - Same key → same extension ID, always
   - Can pre-configure native messaging manifest
   - Extension ID survives remove/re-add cycles

#### How We Generated the Key

```bash
# Generate RSA private key, extract public key, encode as base64
openssl genrsa 2048 | openssl rsa -pubout -outform DER | base64 -w0
```

This gives us the base64 string for the `"key"` field.

#### Calculating the Extension ID

Chrome's algorithm:
```python
import hashlib
import base64

# Decode the base64 key
key_bytes = base64.b64decode(key_b64)

# SHA256 hash
hash_bytes = hashlib.sha256(key_bytes).digest()

# Take first 16 bytes
hash_hex = hash_bytes[:16].hex()

# Convert to a-p encoding
# 0→a, 1→b, ..., 9→j, a→k, ..., f→p
extension_id = hex_to_extension_id(hash_hex)
```

For our generated key, this produces:
**`djngojgikpdalhbiimclpdcfehcphcim`**

#### Final Configuration

**manifest.json:**
```json
{
  "key": "MIIBIjANBgkqhkiG9w0BAQEFAAOCAQ8AMIIBCgKCAQEA6e2iRfjdXt...",
  ...
}
```

**Native messaging manifest:**
```json
{
  "allowed_origins": [
    "chrome-extension://djngojgikpdalhbiimclpdcfehcphcim/"
  ]
}
```

Now the IDs match → native messaging works → real PID retrieved → browser not killed! ✅

#### Key Concepts

**Sandboxing**
- Browser extensions run in isolated processes for security
- Can't directly access system resources like process IDs
- Need explicit bridges (like native messaging) to escape sandbox

**Process IDs (PIDs)**
- Unique identifier for each running process
- Assigned by the kernel (Linux)
- Used to send signals, track resources, kill processes
- Critical for our daemon to identify which browser to kill

**Cryptographic Hashing**
- One-way function: key → hash (can't reverse)
- Deterministic: same input → same output, always
- Used for content addressing, IDs, checksums
- Chrome uses SHA256 for extension ID generation

**Base64 Encoding**
- Binary data → ASCII text (safe for JSON/URLs)
- 64 characters: A-Z, a-z, 0-9, +, /
- Used for embedding binary keys in text files

**Extension ID Encoding (a-p)**
- Chrome's custom alphabet: a-p (16 chars, maps to hex 0-f)
- Avoids full alphabet to prevent offensive words
- Deterministic mapping preserves hash properties

---

## Summary

### Systemd Startup (Issue 1)

**Problem**: Daemon started before Hyprland was ready
**Fix**: Use `wayland-session@hyprland.desktop.target` instead of `network.target`
**Lesson**: Always use the most specific dependency target that matches your actual requirement

### Native Messaging (Issue 2)

**Problem**: Wildcard extension ID prevented native messaging connection
**Fix**: Add a `"key"` field to get a stable extension ID, configure native messaging with that specific ID
**Lesson**: Chrome security model requires explicit authorization - no wildcards allowed

Both issues demonstrate a common theme in systems programming: **assumptions about initialization order and identity management can silently fail**, leading to mysterious bugs that only manifest under specific conditions (like a fresh boot).

---

## Further Reading

- [systemd for Administrators](https://www.freedesktop.org/wiki/Software/systemd/)
- [Chrome Native Messaging Documentation](https://developer.chrome.com/docs/extensions/develop/concepts/native-messaging)
- [Understanding Linux Process IDs](https://man7.org/linux/man-pages/man5/proc.5.html)
- [Chrome Extension IDs and Keys](https://developer.chrome.com/docs/extensions/mv3/manifest/key/)
