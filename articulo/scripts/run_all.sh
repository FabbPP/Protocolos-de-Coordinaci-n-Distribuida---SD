#!/usr/bin/env bash
# run_all.sh — Orquestador multi-protocolo de experimentos
# Ejecuta 4 protocolos × 4 escenarios × 5 repeticiones y genera CSVs
#
# Uso:
#   ./run_all.sh                     → 2PC A–D (por defecto)
#   PROTOCOLO=saga ./run_all.sh A B  → Saga escenarios A y B
#   ALL=1 ./run_all.sh               → Ejecuta TODOS los protocolos y escenarios
#   DRY_RUN=1 ./run_all.sh           → Vista previa sin ejecutar
#
# Variables de entorno:
#   PROTOCOLO    — protocolo (2pc, saga, tcc, raft)       [default: 2pc]
#   ALL          — si=1, ejecuta los 4 protocolos         [default: 0]
#   N_ITER       — transacciones por repetición           [default: 10]
#   REPETICIONES — repeticiones por escenario             [default: 5]
#   MONTO_BASE   — monto base (S/)                        [default: 500]
#   DRY_RUN      — si=1, solo muestra comandos            [default: 0]

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
DOCKER_DIR="$PROJECT_DIR/docker"
EXPERIMENTS_DIR="$PROJECT_DIR/experiments"
RESULT_DIR="${RESULT_DIR:-$EXPERIMENTS_DIR/results}"
PROTOCOLO="${PROTOCOLO:-2pc}"
ALL="${ALL:-0}"
DRY_RUN="${DRY_RUN:-0}"
N_ITER="${N_ITER:-10}"
REPETICIONES="${REPETICIONES:-5}"
MONTO_BASE="${MONTO_BASE:-500}"

export N_ITER REPETICIONES MONTO_BASE
mkdir -p "$RESULT_DIR"

ALL_PROTOCOLS=(2pc saga tcc raft)
ALL_ESCENARIOS=(A B C D)

# ===========================================================================
banner() {
    echo "================================================================"
    echo "  EXPERIMENTOS: Protocolo $PROTOCOLO"
    echo "  Repeticiones: $REPETICIONES × $N_ITER tx c/u"
    echo "  Monto base:  S/ $MONTO_BASE"
    echo "  Resultados:  $RESULT_DIR"
    echo "================================================================"
    echo ""
}

# ===========================================================================
check_containers() {
    local missing=""
    for c in pg-arequipa pg-lima pg-cusco two-pc-app; do
        if ! docker ps --format '{{.Names}}' | grep -qx "$c"; then
            missing="$missing $c"
        fi
    done
    if [ -n "$missing" ]; then
        echo "ERROR: contenedores no encontrados:$missing"
        echo "  Ejecute primero: cd $DOCKER_DIR && docker compose up -d"
        exit 1
    fi
    echo "✓ Contenedores activos"
}

# ===========================================================================
reset_db() {
    echo "→ Restaurando bases de datos..."
    for node in pg-arequipa pg-lima pg-cusco; do
        docker exec "$node" sh -c "
            psql -U sdhm -d banco_arequipa -c \"UPDATE cuentas SET saldo = 50000 WHERE titular = 'Alvaro Quispe'\" 2>/dev/null || true;
            psql -U sdhm -d banco_cusco    -c \"UPDATE cuentas SET saldo = 30000 WHERE titular = 'Mathias Barrios'\" 2>/dev/null || true;
            psql -U sdhm -d banco_lima     -c \"UPDATE cuentas SET saldo = 20000 WHERE titular = 'Fabiana Pacheco'\" 2>/dev/null || true;
            psql -U sdhm -d banco_arequipa -c \"DELETE FROM reservas\" 2>/dev/null || true;
            psql -U sdhm -d banco_cusco    -c \"DELETE FROM reservas\" 2>/dev/null || true;
            psql -U sdhm -d banco_lima     -c \"DELETE FROM reservas\" 2>/dev/null || true;
            psql -U sdhm -d banco_arequipa -c \"DELETE FROM raft_log\" 2>/dev/null || true;
            psql -U sdhm -d banco_cusco    -c \"DELETE FROM raft_log\" 2>/dev/null || true;
            psql -U sdhm -d banco_lima     -c \"DELETE FROM raft_log\" 2>/dev/null || true
        " 2>/dev/null || true
    done
    echo "✓ BD restaurada"
}

# ===========================================================================
run_scenario() {
    local proto="$1" letra="$2" label="$3"
    local csv="$RESULT_DIR/${proto}_${letra}.csv"

    echo ""
    echo "────────────────────────────────────────────────────────────"
    echo "  [$proto] Escenario $letra: $label"
    echo "────────────────────────────────────────────────────────────"

    if [ "$DRY_RUN" = "1" ]; then
        echo "  [DRY RUN] docker exec two-pc-app python client_load.py"
        echo "    PROTOCOLO=$proto ESCENARIO=$letra CSV_OUT=$csv"
        return
    fi

    docker exec two-pc-app bash -c "
        cd /app/experiments &&
        CSV_OUT=${csv} PROTOCOLO=${proto} ESCENARIO=${letra} \
        N_ITER=${N_ITER} REPETICIONES=${REPETICIONES} MONTO_BASE=${MONTO_BASE} \
        python client_load.py
    "

    local filas=$(wc -l < "$csv" 2>/dev/null || echo 0)
    echo "  → CSV: $csv (${filas} líneas)"
}

# ===========================================================================
# Main
# ===========================================================================

USER_SCENARIOS=("${@:-A B C D}")

if [ "$ALL" = "1" ]; then
    check_containers

    for proto in "${ALL_PROTOCOLS[@]}"; do
        PROTOCOLO="$proto"
        banner
        for esc in "${ALL_ESCENARIOS[@]}"; do
            reset_db
            case "$esc" in
                A) run_scenario "$proto" A "Transacciones exitosas" ;;
                B) run_scenario "$proto" B "Fallo de red" ;;
                C) run_scenario "$proto" C "Caída de nodo" ;;
                D) run_scenario "$proto" D "Recuperación" ;;
            esac
        done
    done
else
    # Modo single-protocol
    banner
    check_containers

    for esc in "${USER_SCENARIOS[@]}"; do
        reset_db
        case "$esc" in
            A) run_scenario "$PROTOCOLO" A "Transacciones exitosas" ;;
            B) run_scenario "$PROTOCOLO" B "Fallo de red" ;;
            C) run_scenario "$PROTOCOLO" C "Caída de nodo" ;;
            D) run_scenario "$PROTOCOLO" D "Recuperación" ;;
            saga|SAGA)
                echo "⚠ HOOK: Saga — usa PROTOCOLO=saga ./run_all.sh A B C D"
                ;;
            tcc|TCC)
                echo "⚠ HOOK: TCC — usa PROTOCOLO=tcc ./run_all.sh A B C D"
                ;;
            raft|RAFT)
                echo "⚠ HOOK: Raft — usa PROTOCOLO=raft ./run_all.sh A B C D"
                ;;
            *)
                echo "ERROR: escenario '$esc' no reconocido. Use: A B C D [saga tcc raft]"
                ;;
        esac
    done
fi

echo ""
echo "================================================================"
echo "  EXPERIMENTOS COMPLETADOS"
echo "  CSVs en: $RESULT_DIR"
ls -lah "$RESULT_DIR/"*.csv 2>/dev/null || echo "  (ninguno)"
echo "================================================================"
