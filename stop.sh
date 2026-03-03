#!/usr/bin/env bash
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

stop_pid() {
    local pidfile="$1" name="$2"
    if [[ -f "$pidfile" ]]; then
        local pid
        pid=$(cat "$pidfile")
        if kill -0 "$pid" 2>/dev/null; then
            kill "$pid" && echo "[ok] $name encerrado (PID $pid)"
        else
            echo "[warn] $name já estava parado"
        fi
        rm -f "$pidfile"
    else
        # fallback: procurar pelo padrão
        pgrep -f "$2" | xargs kill 2>/dev/null && echo "[ok] $name encerrado (por padrão)" || true
    fi
}

stop_pid logs/web.pid    "uvicorn app.main:app"
stop_pid logs/worker.pid "arq app.worker.WorkerSettings"
echo "Parado."
