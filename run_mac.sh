#!/bin/bash
# -------------------------------------------------------------------
# ClearSight - Native macOS Desktop Launcher
# Zero-cloud survey analytics platform on localhost:8540
# -------------------------------------------------------------------

set -eo pipefail

DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" >/dev/null 2>&1 && pwd )"
cd "$DIR"

PID_FILE="$DIR/.clearsight_server.pid"

cleanup() {
    if [ -f "$PID_FILE" ]; then
        PID=$(cat "$PID_FILE" 2>/dev/null || true)
        if [ -n "$PID" ] && kill -0 "$PID" 2>/dev/null; then
            kill -TERM "$PID" 2>/dev/null || true
        fi
        rm -f "$PID_FILE"
    fi
    rm -f "$DIR/.clearsight_port" 2>/dev/null || true
    echo "[*] ClearSight session terminated cleanly."
}
trap cleanup EXIT INT TERM

# 1. Gracefully terminate previously recorded ClearSight server
if [ -f "$PID_FILE" ]; then
    OLD_PID=$(cat "$PID_FILE" 2>/dev/null || true)
    if [ -n "$OLD_PID" ] && kill -0 "$OLD_PID" 2>/dev/null; then
        echo "[*] Terminating previous ClearSight instance (PID: $OLD_PID)..."
        kill -TERM "$OLD_PID" 2>/dev/null || true
        sleep 0.5
    fi
    rm -f "$PID_FILE"
fi

# 2. Select Python 3.10+ interpreter
if [ -x "/usr/local/bin/python3.14" ]; then
    PYTHON_BIN="/usr/local/bin/python3.14"
elif [ -x "/Library/Frameworks/Python.framework/Versions/3.14/bin/python3" ]; then
    PYTHON_BIN="/Library/Frameworks/Python.framework/Versions/3.14/bin/python3"
elif command -v python3.14 >/dev/null 2>&1; then
    PYTHON_BIN="$(command -v python3.14)"
elif command -v python3.12 >/dev/null 2>&1; then
    PYTHON_BIN="$(command -v python3.12)"
elif command -v python3.11 >/dev/null 2>&1; then
    PYTHON_BIN="$(command -v python3.11)"
elif command -v python3.10 >/dev/null 2>&1; then
    PYTHON_BIN="$(command -v python3.10)"
elif command -v python3 >/dev/null 2>&1; then
    PYTHON_BIN="$(command -v python3)"
else
    PYTHON_BIN="python3"
fi

# Validate Python version
if ! "$PYTHON_BIN" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)' 2>/dev/null; then
    echo "[-] Error: ClearSight requires Python 3.10 or newer."
    exit 1
fi

# 3. Ensure native window binary is compiled
if [ ! -f "$DIR/ClearSight_Window" ]; then
    echo "[*] Compiling native Swift desktop window..."
    bash "$DIR/build_native.sh"
fi

# 4. Start local analytical server in background
echo "[*] Starting ClearSight zero-cloud analytical core..."
"$PYTHON_BIN" "$DIR/server.py" > /tmp/clearsight_server.log 2>&1 &
SERVER_PID=$!
echo "$SERVER_PID" > "$PID_FILE"
export CLEARSIGHT_SERVER_PID="$SERVER_PID"

# 5. Readiness probe (Wait for server port discovery with timeout)
READY=0
ACTIVE_PORT=8540
for i in {1..24}; do
    if [ -f "$DIR/.clearsight_port" ]; then
        ACTIVE_PORT=$(cat "$DIR/.clearsight_port" 2>/dev/null || echo "8540")
    fi
    if curl -s "http://127.0.0.1:${ACTIVE_PORT}/api/dataset-status" >/dev/null 2>&1; then
        READY=1
        break
    fi
    sleep 0.25
done

if [ "$READY" -ne 1 ]; then
    echo "[-] Error: ClearSight server failed to respond on port ${ACTIVE_PORT} within timeout."
    echo "    Check logs at /tmp/clearsight_server.log"
    exit 1
fi

export CLEARSIGHT_PORT="$ACTIVE_PORT"

# 6. Launch Native macOS Window
echo "[✓] Opening ClearSight native desktop window (port ${ACTIVE_PORT})..."
"$DIR/ClearSight_Window"
