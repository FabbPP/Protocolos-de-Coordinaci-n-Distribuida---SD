#!/usr/bin/env bash
# add_latency.sh — Agrega/remueve latencia artificial entre nodos con tc-netem
# Útil para simular entornos geográficamente distribuidos
#
# Uso: ./add_latency.sh [on|off] [contenedor] [latencia_ms] [jitter_ms]
#
# Ejemplos:
#   ./add_latency.sh on  pg-arequipa 80 10    → 80ms ± 10ms jitter
#   ./add_latency.sh on  pg-cusco    120 20   → 120ms ± 20ms
#   ./add_latency.sh off pg-arequipa           → eliminar latencia
#   ./add_latency.sh off                        → eliminar latencia de todos

set -euo pipefail

ACTION="${1:-on}"
TARGET="${2:-}"
LATENCY_MS="${3:-80}"
JITTER_MS="${4:-10}"

apply_latency() {
    local c="$1" ms="$2" jit="$3"
    echo "→ Configurando latencia en $c: ${ms}ms ± ${jit}ms"
    docker exec "$c" sh -c "
        tc qdisc del dev eth0 root 2>/dev/null || true;
        tc qdisc add dev eth0 root netem delay ${ms}ms ${jit}ms distribution normal
    " 2>/dev/null || echo "  ⚠ tc no disponible en $c — no se aplicó latencia (solo Linux)"
}

remove_latency() {
    local c="$1"
    echo "→ Eliminando latencia en $c..."
    docker exec "$c" sh -c "
        tc qdisc del dev eth0 root 2>/dev/null || true
    " 2>/dev/null || true
}

echo "=== Latencia de red: [$ACTION] ==="

case "$ACTION" in
    on|apply|add)
        if [ -z "$TARGET" ]; then
            echo "ERROR: especifique el contenedor destino."
            echo "  uso: ./add_latency.sh on <contenedor> [latencia_ms] [jitter_ms]"
            exit 1
        fi
        apply_latency "$TARGET" "$LATENCY_MS" "$JITTER_MS"
        echo "✓ Latencia aplicada en $TARGET"
        ;;

    off|remove|del)
        if [ -n "$TARGET" ]; then
            remove_latency "$TARGET"
        else
            echo "→ Eliminando latencia en todos los nodos..."
            for c in pg-arequipa pg-lima pg-cusco; do
                remove_latency "$c"
            done
        fi
        echo "✓ Latencia eliminada"
        ;;

    show|status)
        echo "→ Estado de tc-netem:"
        for c in pg-arequipa pg-lima pg-cusco; do
            echo -n "  $c: "
            docker exec "$c" sh -c "tc qdisc show dev eth0 2>/dev/null | grep netem || echo 'sin latencia'" 2>/dev/null || echo "no disponible"
        done
        ;;

    *)
        echo "ERROR: acción '$ACTION' no reconocida. Use on, off o show."
        exit 1
        ;;
esac
