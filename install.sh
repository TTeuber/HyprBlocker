#!/bin/bash
# HyprBlocker Installation Script

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CONFIG_DIR="$HOME/.config/hyprblocker"
DATA_DIR="$HOME/.local/share/hyprblocker"
BIN_DIR="$HOME/.local/bin"

# Check for --build flag
if [ "$1" = "--build" ]; then
    echo "=== Building Desktop and Tray Executables ==="
    echo ""

    # Build frontend
    echo "Building frontend..."
    cd "$SCRIPT_DIR/desktop-app/frontend"
    bun run build

    # Sync dependencies (single project venv at the repo root)
    echo "Installing build dependencies..."
    cd "$SCRIPT_DIR"
    uv sync

    # Build executables
    echo "Building desktop app executable..."
    cd "$SCRIPT_DIR/desktop-app"
    uv run pyinstaller desktop-app.spec --distpath "$SCRIPT_DIR/dist/" --workpath "$SCRIPT_DIR/build/desktop-app" --noconfirm

    echo "Building tray app executable..."
    cd "$SCRIPT_DIR/tray"
    uv run pyinstaller tray-app.spec --distpath "$SCRIPT_DIR/dist/" --workpath "$SCRIPT_DIR/build/tray" --noconfirm

    # Install desktop app (onedir mode - copy directory)
    echo "Installing desktop app..."
    mkdir -p "$DATA_DIR/desktop-app-bin"
    rm -rf "$DATA_DIR/desktop-app-bin/hyprblocker"
    cp -r "$SCRIPT_DIR/dist/hyprblocker" "$DATA_DIR/desktop-app-bin/"

    # Create symlink in ~/.local/bin
    echo "Creating symlinks in $BIN_DIR..."
    mkdir -p "$BIN_DIR"
    ln -sf "$DATA_DIR/desktop-app-bin/hyprblocker/hyprblocker" "$BIN_DIR/hyprblocker"
    cp "$SCRIPT_DIR/dist/hyprblocker-tray" "$BIN_DIR/"
    chmod +x "$BIN_DIR/hyprblocker-tray"

    # Copy icons to installed location
    echo "Installing icons..."
    mkdir -p "$DATA_DIR/icons"
    cp "$SCRIPT_DIR/icons/"* "$DATA_DIR/icons/"

    # Install desktop icon for app launcher
    echo "Installing desktop icon..."
    APPS_DIR="$HOME/.local/share/applications"
    mkdir -p "$APPS_DIR/icons"
    cp "$SCRIPT_DIR/icons/icon-desktop-256.png" "$APPS_DIR/icons/HyprBlocker.png"

    # Create desktop entry
    echo "Creating desktop entry..."
    cat > "$APPS_DIR/HyprBlocker.desktop" << EOF
[Desktop Entry]
Name=HyprBlocker
Comment=Block distracting websites and applications
Exec=$DATA_DIR/desktop-app-bin/hyprblocker/hyprblocker
Icon=$APPS_DIR/icons/HyprBlocker.png
Terminal=false
Type=Application
Categories=Utility;
StartupNotify=true
EOF

    # Create autostart entry for tray app
    echo "Creating autostart entry for tray app..."
    AUTOSTART_DIR="$HOME/.config/autostart"
    mkdir -p "$AUTOSTART_DIR"
    cat > "$AUTOSTART_DIR/hyprblocker-tray.desktop" << EOF
[Desktop Entry]
Name=HyprBlocker Tray
Comment=HyprBlocker System Tray Icon
Exec=$BIN_DIR/hyprblocker-tray
StartupNotify=false
Terminal=false
Type=Application
Categories=Utility;
X-GNOME-Autostart-enabled=true
EOF

    echo ""
    echo "=== Build Complete ==="
    echo ""
    echo "Installed:"
    echo "  Desktop app: $DATA_DIR/desktop-app-bin/hyprblocker/"
    echo "  Tray app: $BIN_DIR/hyprblocker-tray"
    echo "  Desktop entry: $APPS_DIR/HyprBlocker.desktop"
    echo ""
    echo "Tray app will start automatically on login."
    echo "To start it now: $BIN_DIR/hyprblocker-tray &"
    echo ""
    exit 0
fi

echo "=== HyprBlocker Installation ==="
echo ""

# Create directories
echo "Creating directories..."
mkdir -p "$CONFIG_DIR"
mkdir -p "$DATA_DIR"
mkdir -p "$DATA_DIR/extension"
mkdir -p "$DATA_DIR/desktop-app"
mkdir -p "$DATA_DIR/native-host"

# Copy extension files
echo "Installing browser extension..."
cp -r "$SCRIPT_DIR/extension/"* "$DATA_DIR/extension/"

# Copy desktop app files
echo "Installing desktop app..."
cp -r "$SCRIPT_DIR/desktop-app/"* "$DATA_DIR/desktop-app/"

# Copy native host
echo "Installing native messaging host..."
cp "$SCRIPT_DIR/extension/native-host/host.py" "$DATA_DIR/native-host/"
chmod +x "$DATA_DIR/native-host/host.py"

# Install all Python dependencies into the single project venv
echo "Installing Python dependencies..."
cd "$SCRIPT_DIR"
uv sync
PROJECT_PYTHON="$SCRIPT_DIR/.venv/bin/python"
DAEMON_PYTHON="$PROJECT_PYTHON"
DESKTOP_PYTHON="$PROJECT_PYTHON"

# Update native messaging manifests with correct paths
NATIVE_HOST_PATH="$DATA_DIR/native-host/host.py"

# Firefox native messaging manifest
FIREFOX_NATIVE_DIR="$HOME/.mozilla/native-messaging-hosts"
mkdir -p "$FIREFOX_NATIVE_DIR"
cat > "$FIREFOX_NATIVE_DIR/com.hyprblocker.host.json" << EOF
{
  "name": "com.hyprblocker.host",
  "description": "HyprBlocker Native Host",
  "path": "$NATIVE_HOST_PATH",
  "type": "stdio",
  "allowed_extensions": ["hyprblocker@hyprblocker.local"]
}
EOF
echo "Firefox native messaging manifest installed"

# Chrome/Chromium native messaging manifest
for chrome_dir in \
    "$HOME/.config/google-chrome/NativeMessagingHosts" \
    "$HOME/.config/chromium/NativeMessagingHosts" \
    "$HOME/.config/BraveSoftware/Brave-Browser/NativeMessagingHosts"; do
    mkdir -p "$chrome_dir"
    cat > "$chrome_dir/com.hyprblocker.host.json" << EOF
{
  "name": "com.hyprblocker.host",
  "description": "HyprBlocker Native Host",
  "path": "$NATIVE_HOST_PATH",
  "type": "stdio",
  "allowed_origins": [
    "chrome-extension://djngojgikpdalhbiimclpdcfehcphcim/"
  ]
}
EOF
done
echo "Chrome/Chromium native messaging manifests installed"

# Install systemd service
echo "Installing systemd service..."
SERVICE_FILE="$HOME/.config/systemd/user/hyprblocker.service"
mkdir -p "$(dirname "$SERVICE_FILE")"

cat > "$SERVICE_FILE" << EOF
[Unit]
Description=HyprBlocker Daemon
After=graphical-session.target
BindsTo=graphical-session.target
StartLimitIntervalSec=0

[Service]
Type=simple
Environment="PYTHONUNBUFFERED=1"
# %h (home) rather than the config dir: on the first boot after the rename
# the config dir may not exist yet (the daemon migrates the legacy one).
WorkingDirectory=%h
ExecStart=$DAEMON_PYTHON -m daemon.main
Restart=always
RestartSec=5
StandardOutput=journal
StandardError=journal

# Make it harder to kill
KillMode=process
KillSignal=SIGTERM
SendSIGKILL=no

[Install]
WantedBy=graphical-session.target
EOF

# Reload systemd
systemctl --user daemon-reload

echo ""
echo "=== Installation Complete ==="
echo ""
echo "Next steps:"
echo ""
echo "1. Start the daemon:"
echo "   systemctl --user enable hyprblocker"
echo "   systemctl --user start hyprblocker"
echo ""
echo "2. Install the browser extension:"
echo "   Firefox:"
echo "     - Go to about:debugging#/runtime/this-firefox"
echo "     - Click 'Load Temporary Add-on'"
echo "     - Select $DATA_DIR/extension/manifest.json"
echo "     - Enable in incognito mode in extension settings"
echo ""
echo "   Chrome/Chromium:"
echo "     - Go to chrome://extensions/"
echo "     - Enable 'Developer mode'"
echo "     - Click 'Load unpacked'"
echo "     - Select $DATA_DIR/extension/"
echo "     - Enable in incognito mode in extension settings"
echo ""
echo "3. Build and install desktop/tray executables (optional):"
echo "   ./install.sh --build"
echo ""
echo "4. Launch the desktop app:"
echo "   $DESKTOP_PYTHON $SCRIPT_DIR/desktop-app/main.py"
echo "   Or if built: ~/.local/bin/hyprblocker"
echo ""
echo "5. Check daemon status:"
echo "   systemctl --user status hyprblocker"
echo "   journalctl --user -u hyprblocker -f"
echo ""
