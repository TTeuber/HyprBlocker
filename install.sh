#!/bin/bash
# Website Blocker Installation Script

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CONFIG_DIR="$HOME/.config/website-blocker"
DATA_DIR="$HOME/.local/share/website-blocker"
BIN_DIR="$HOME/.local/bin"

# Check for --build flag
if [ "$1" = "--build" ]; then
    echo "=== Building Desktop and Tray Executables ==="
    echo ""

    # Build frontend
    echo "Building frontend..."
    cd "$SCRIPT_DIR/desktop-app/frontend"
    bun run build

    # Sync dependencies
    echo "Installing build dependencies..."
    cd "$SCRIPT_DIR/desktop-app"
    uv sync
    cd "$SCRIPT_DIR/tray"
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
    rm -rf "$DATA_DIR/desktop-app-bin/website-blocker"
    cp -r "$SCRIPT_DIR/dist/website-blocker" "$DATA_DIR/desktop-app-bin/"

    # Create symlink in ~/.local/bin
    echo "Creating symlinks in $BIN_DIR..."
    mkdir -p "$BIN_DIR"
    ln -sf "$DATA_DIR/desktop-app-bin/website-blocker/website-blocker" "$BIN_DIR/website-blocker"
    cp "$SCRIPT_DIR/dist/website-blocker-tray" "$BIN_DIR/"
    chmod +x "$BIN_DIR/website-blocker-tray"

    # Copy icons to installed location
    echo "Installing icons..."
    mkdir -p "$DATA_DIR/icons"
    cp "$SCRIPT_DIR/icons/"* "$DATA_DIR/icons/"

    # Install desktop icon for app launcher
    echo "Installing desktop icon..."
    APPS_DIR="$HOME/.local/share/applications"
    mkdir -p "$APPS_DIR/icons"
    cp "$SCRIPT_DIR/icons/icon-desktop-256.png" "$APPS_DIR/icons/WebsiteBlocker.png"

    # Create desktop entry
    echo "Creating desktop entry..."
    cat > "$APPS_DIR/WebsiteBlocker.desktop" << EOF
[Desktop Entry]
Name=Website Blocker
Comment=Block distracting websites and applications
Exec=$DATA_DIR/desktop-app-bin/website-blocker/website-blocker
Icon=$APPS_DIR/icons/WebsiteBlocker.png
Terminal=false
Type=Application
Categories=Utility;
StartupNotify=true
EOF

    # Create autostart entry for tray app
    echo "Creating autostart entry for tray app..."
    AUTOSTART_DIR="$HOME/.config/autostart"
    mkdir -p "$AUTOSTART_DIR"
    cat > "$AUTOSTART_DIR/website-blocker-tray.desktop" << EOF
[Desktop Entry]
Name=Website Blocker Tray
Comment=Website Blocker System Tray Icon
Exec=$BIN_DIR/website-blocker-tray
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
    echo "  Desktop app: $DATA_DIR/desktop-app-bin/website-blocker/"
    echo "  Tray app: $BIN_DIR/website-blocker-tray"
    echo "  Desktop entry: $APPS_DIR/WebsiteBlocker.desktop"
    echo ""
    echo "Tray app will start automatically on login."
    echo "To start it now: $BIN_DIR/website-blocker-tray &"
    echo ""
    exit 0
fi

echo "=== Website Blocker Installation ==="
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

# Install daemon dependencies
echo "Installing daemon dependencies..."
cd "$SCRIPT_DIR/daemon"
uv sync
DAEMON_PYTHON="$SCRIPT_DIR/daemon/.venv/bin/python"
cd "$SCRIPT_DIR"

# Install desktop-app dependencies
echo "Installing desktop-app dependencies..."
cd "$SCRIPT_DIR/desktop-app"
uv sync
DESKTOP_PYTHON="$SCRIPT_DIR/desktop-app/.venv/bin/python"
cd "$SCRIPT_DIR"

# Install tray dependencies
echo "Installing tray dependencies..."
cd "$SCRIPT_DIR/tray"
uv sync
cd "$SCRIPT_DIR"

# Update native messaging manifests with correct paths
NATIVE_HOST_PATH="$DATA_DIR/native-host/host.py"

# Firefox native messaging manifest
FIREFOX_NATIVE_DIR="$HOME/.mozilla/native-messaging-hosts"
mkdir -p "$FIREFOX_NATIVE_DIR"
cat > "$FIREFOX_NATIVE_DIR/com.websiteblocker.host.json" << EOF
{
  "name": "com.websiteblocker.host",
  "description": "Website Blocker Native Host",
  "path": "$NATIVE_HOST_PATH",
  "type": "stdio",
  "allowed_extensions": ["website-blocker@websiteblocker.local"]
}
EOF
echo "Firefox native messaging manifest installed"

# Chrome/Chromium native messaging manifest
for chrome_dir in \
    "$HOME/.config/google-chrome/NativeMessagingHosts" \
    "$HOME/.config/chromium/NativeMessagingHosts" \
    "$HOME/.config/BraveSoftware/Brave-Browser/NativeMessagingHosts"; do
    mkdir -p "$chrome_dir"
    cat > "$chrome_dir/com.websiteblocker.host.json" << EOF
{
  "name": "com.websiteblocker.host",
  "description": "Website Blocker Native Host",
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
SERVICE_FILE="$HOME/.config/systemd/user/website-blocker.service"
mkdir -p "$(dirname "$SERVICE_FILE")"

cat > "$SERVICE_FILE" << EOF
[Unit]
Description=Website Blocker Daemon
After=wayland-session@hyprland.desktop.target
BindsTo=wayland-session@hyprland.desktop.target
StartLimitIntervalSec=0

[Service]
Type=simple
Environment="PYTHONUNBUFFERED=1"
WorkingDirectory=$CONFIG_DIR
ExecStart=$DAEMON_PYTHON $SCRIPT_DIR/daemon/main.py
Restart=always
RestartSec=5
StandardOutput=journal
StandardError=journal

# Make it harder to kill
KillMode=process
KillSignal=SIGTERM
SendSIGKILL=no

[Install]
WantedBy=wayland-session@hyprland.desktop.target
EOF

# Reload systemd
systemctl --user daemon-reload

echo ""
echo "=== Installation Complete ==="
echo ""
echo "Next steps:"
echo ""
echo "1. Start the daemon:"
echo "   systemctl --user enable website-blocker"
echo "   systemctl --user start website-blocker"
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
echo "   Or if built: ~/.local/bin/website-blocker"
echo ""
echo "5. Check daemon status:"
echo "   systemctl --user status website-blocker"
echo "   journalctl --user -u website-blocker -f"
echo ""
