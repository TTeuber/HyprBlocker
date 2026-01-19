#!/bin/bash
# Development reinstall script - quick reinstalls without full dependency setup

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CONFIG_DIR="$HOME/.config/website-blocker"
DATA_DIR="$HOME/.local/share/website-blocker"
BIN_DIR="$HOME/.local/bin"

usage() {
    echo "Usage: $0 <component> [component...]"
    echo ""
    echo "Components:"
    echo "  daemon       Restart the daemon systemd service"
    echo "  extension    Copy extension files to installed location"
    echo "  native-host  Copy native messaging host"
    echo "  desktop      Rebuild and install desktop app executable"
    echo "  tray         Rebuild and install tray app executable"
    echo "  frontend     Build frontend only (for dev mode testing)"
    echo "  all          Reinstall all components"
    exit 1
}

reinstall_daemon() {
    echo "=== Reinstalling Daemon ==="
    systemctl --user restart website-blocker
    echo "Daemon restarted. Check status: systemctl --user status website-blocker"
}

reinstall_extension() {
    echo "=== Reinstalling Extension ==="
    cp -r "$SCRIPT_DIR/extension/"* "$DATA_DIR/extension/"
    echo "Extension files copied to $DATA_DIR/extension/"
    echo "Reload the extension in your browser to apply changes."
}

reinstall_native_host() {
    echo "=== Reinstalling Native Host ==="
    cp "$SCRIPT_DIR/extension/native-host/host.py" "$DATA_DIR/native-host/"
    chmod +x "$DATA_DIR/native-host/host.py"
    echo "Native host reinstalled."
}

reinstall_frontend() {
    echo "=== Building Frontend ==="
    cd "$SCRIPT_DIR/desktop-app/frontend"
    bun run build
    echo "Frontend built to desktop-app/web/"
}

reinstall_desktop() {
    echo "=== Reinstalling Desktop App ==="

    # Build frontend first
    reinstall_frontend

    # Build executable
    echo "Building desktop app executable..."
    cd "$SCRIPT_DIR/desktop-app"
    uv run pyinstaller desktop-app.spec \
        --distpath "$SCRIPT_DIR/dist/" \
        --workpath "$SCRIPT_DIR/build/desktop-app" \
        --noconfirm

    # Install
    echo "Installing desktop app..."
    mkdir -p "$DATA_DIR/desktop-app-bin"
    rm -rf "$DATA_DIR/desktop-app-bin/website-blocker"
    cp -r "$SCRIPT_DIR/dist/website-blocker" "$DATA_DIR/desktop-app-bin/"

    # Ensure symlink exists
    mkdir -p "$BIN_DIR"
    ln -sf "$DATA_DIR/desktop-app-bin/website-blocker/website-blocker" "$BIN_DIR/website-blocker"

    echo "Desktop app reinstalled at $BIN_DIR/website-blocker"
}

reinstall_tray() {
    echo "=== Reinstalling Tray App ==="

    # Build executable
    echo "Building tray app executable..."
    cd "$SCRIPT_DIR/tray"
    uv run pyinstaller tray-app.spec \
        --distpath "$SCRIPT_DIR/dist/" \
        --workpath "$SCRIPT_DIR/build/tray" \
        --noconfirm

    # Install
    cp "$SCRIPT_DIR/dist/website-blocker-tray" "$BIN_DIR/"
    chmod +x "$BIN_DIR/website-blocker-tray"

    echo "Tray app reinstalled at $BIN_DIR/website-blocker-tray"
    echo "Restart the tray app or log out/in to apply changes."
}

# Main
if [ $# -eq 0 ]; then
    usage
fi

for component in "$@"; do
    case "$component" in
        daemon)
            reinstall_daemon
            ;;
        extension)
            reinstall_extension
            ;;
        native-host)
            reinstall_native_host
            ;;
        desktop)
            reinstall_desktop
            ;;
        tray)
            reinstall_tray
            ;;
        frontend)
            reinstall_frontend
            ;;
        all)
            reinstall_daemon
            reinstall_extension
            reinstall_native_host
            reinstall_desktop
            reinstall_tray
            ;;
        *)
            echo "Unknown component: $component"
            usage
            ;;
    esac
    echo ""
done

echo "Done!"
