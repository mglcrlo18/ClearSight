#!/bin/bash
# -------------------------------------------------------------------
# ClearSight - Native macOS Desktop Launcher
# Launches the zero-cloud statistical core on localhost:8540 and opens Cocoa window.
# -------------------------------------------------------------------

DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" >/dev/null 2>&1 && pwd )"
cd "$DIR"

# 1. Terminate any previous instance running on port 8540
lsof -ti:8540 | xargs kill -9 2>/dev/null

# 2. Select Python 3.14 interpreter
PYTHON_BIN="/Library/Frameworks/Python.framework/Versions/3.14/bin/python3"
if [ ! -f "$PYTHON_BIN" ]; then
    PYTHON_BIN="python3"
fi

# 3. Ensure native window binary is compiled
if [ ! -f "$DIR/ClearSight_Window" ]; then
    echo "[*] Compiling native Swift desktop window..."
    bash "$DIR/build_native.sh"
fi

# 4. Start local headless statistical server in background
echo "[*] Starting ClearSight zero-cloud analytical core..."
"$PYTHON_BIN" "$DIR/server.py" > /dev/null 2>&1 &
SERVER_PID=$!

# 5. Wait for localhost:8540 to become responsive
for i in {1..20}; do
    if curl -s http://127.0.0.1:8540 >/dev/null 2>&1; then
        break
    fi
    sleep 0.25
done

# 6. Launch Native macOS Window
echo "[✓] Opening ClearSight native desktop window..."
"$DIR/ClearSight_Window"

# 7. Cleanup server upon window close
kill -9 $SERVER_PID 2>/dev/null
echo "[*] ClearSight session closed cleanly."
