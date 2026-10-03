#!/bin/bash
# -------------------------------------------------------------------
# Native Swift Compiler for Sukat by Lunsad macOS Desktop Window
# -------------------------------------------------------------------

DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" >/dev/null 2>&1 && pwd )"
cd "$DIR"

echo "[*] Compiling native Swift Cocoa wrapper..."
swiftc window.swift -o ClearSight_Window -framework Cocoa -framework WebKit

if [ -f "$DIR/ClearSight_Window" ]; then
    chmod +x "$DIR/ClearSight_Window"
    echo "[✓] ClearSight_Window binary successfully compiled!"
else
    echo "[!] Error compiling ClearSight_Window."
    exit 1
fi
