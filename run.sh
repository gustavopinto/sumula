#!/usr/bin/env bash
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# ── cores ──────────────────────────────────────────────────────────────────────
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; CYAN='\033[0;36m'; NC='\033[0m'
info()  { echo -e "${CYAN}[sumula]${NC} $*"; }
ok()    { echo -e "${GREEN}[ok]${NC} $*"; }
warn()  { echo -e "${YELLOW}[warn]${NC} $*"; }
die()   { echo -e "${RED}[erro]${NC} $*" >&2; exit 1; }

# ── 1. matar processos antigos ─────────────────────────────────────────────────
info "Procurando processos antigos..."

kill_pattern() {
    local pattern="$1"
    local pids
    pids=$(pgrep -f "$pattern" 2>/dev/null || true)
    if [[ -n "$pids" ]]; then
        echo "$pids" | xargs kill 2>/dev/null || true
        sleep 1
        # SIGKILL se ainda estiver vivo
        local remaining
        remaining=$(pgrep -f "$pattern" 2>/dev/null || true)
        if [[ -n "$remaining" ]]; then
            echo "$remaining" | xargs kill -9 2>/dev/null || true
        fi
        warn "Encerrado: $pattern (PIDs: $pids)"
    fi
}

kill_pattern "uvicorn app.main:app"
kill_pattern "arq app.worker.WorkerSettings"

ok "Processos antigos encerrados"

# ── 2. verificar venv ──────────────────────────────────────────────────────────
[[ -f ".venv/bin/activate" ]] || die "Virtualenv não encontrado. Crie com: python3 -m venv .venv && source .venv/bin/activate && pip install -e ."
source .venv/bin/activate
ok "Virtualenv ativado: $(python --version)"

# ── 3. docker compose (postgres + redis) ──────────────────────────────────────
info "Verificando Docker..."
if ! docker info >/dev/null 2>&1; then
    warn "Docker daemon não está rodando. Tentando abrir Docker Desktop..."
    open -a Docker 2>/dev/null || die "Docker não encontrado"
    for i in $(seq 1 30); do
        docker info >/dev/null 2>&1 && break
        sleep 2
    done
    docker info >/dev/null 2>&1 || die "Docker não iniciou"
fi

info "Subindo Postgres e Redis..."
docker compose up -d 2>&1 | grep -E "(Started|Running|healthy|error)" || true

# aguardar postgres pronto
info "Aguardando Postgres..."
for i in $(seq 1 20); do
    docker compose exec -T postgres pg_isready -U sumula >/dev/null 2>&1 && break
    sleep 2
done
docker compose exec -T postgres pg_isready -U sumula >/dev/null 2>&1 || die "Postgres não ficou pronto"
ok "Postgres pronto"

# ── 4. migrations ─────────────────────────────────────────────────────────────
info "Rodando migrations..."
python -m alembic upgrade head
ok "Migrations aplicadas"

# ── 5. criar workdir ──────────────────────────────────────────────────────────
WORKDIR="${WORKDIR_PATH:-/tmp/sumula_workdir}"
mkdir -p "$WORKDIR"

# ── 6. iniciar web server ─────────────────────────────────────────────────────
LOG_DIR="$SCRIPT_DIR/logs"
mkdir -p "$LOG_DIR"

info "Iniciando web server na porta 8000..."
nohup python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 \
    > "$LOG_DIR/web.log" 2>&1 &
WEB_PID=$!
echo $WEB_PID > "$LOG_DIR/web.pid"

# aguardar web pronto
for i in $(seq 1 15); do
    curl -s -o /dev/null -w "%{http_code}" http://localhost:8000/ 2>/dev/null | grep -q "200" && break
    sleep 1
done
curl -s -o /dev/null -w "%{http_code}" http://localhost:8000/ 2>/dev/null | grep -q "200" \
    || die "Web server não respondeu. Veja logs/web.log"
ok "Web server rodando (PID $WEB_PID) → http://localhost:8000"

# ── 7. iniciar worker ─────────────────────────────────────────────────────────
info "Iniciando worker ARQ..."
nohup python -m arq app.worker.WorkerSettings \
    > "$LOG_DIR/worker.log" 2>&1 &
WORKER_PID=$!
echo $WORKER_PID > "$LOG_DIR/worker.pid"
sleep 2

if kill -0 "$WORKER_PID" 2>/dev/null; then
    ok "Worker rodando (PID $WORKER_PID)"
else
    die "Worker falhou ao iniciar. Veja logs/worker.log"
fi

# ── 8. resumo ─────────────────────────────────────────────────────────────────
echo ""
echo -e "${GREEN}═══════════════════════════════════════════${NC}"
echo -e "${GREEN}  Sumula Curricular FAPESP — rodando       ${NC}"
echo -e "${GREEN}═══════════════════════════════════════════${NC}"
echo -e "  Web:    ${CYAN}http://localhost:8000${NC}"
echo -e "  Logs:   ${CYAN}logs/web.log${NC} · ${CYAN}logs/worker.log${NC}"
echo -e "  Parar:  ${YELLOW}./stop.sh${NC}"
echo -e "${GREEN}═══════════════════════════════════════════${NC}"
