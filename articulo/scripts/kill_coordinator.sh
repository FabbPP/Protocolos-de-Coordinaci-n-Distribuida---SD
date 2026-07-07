#!/usr/bin/env bash
# kill_coordinator.sh — Detiene o reinicia el contenedor del coordinador/aplicación
# Uso: ./kill_coordinator.sh [stop|start|restart]
#
# Ejemplos:
#   ./kill_coordinator.sh stop     → simula caída del coordinador
#   ./kill_coordinator.sh start    → recupera el coordinador
#   ./kill_coordinator.sh restart  → ciclo completo de caída+recuperación

set -euo pipefail

CONTAINER="${COORDINATOR_CONTAINER:-two-pc-app}"
ACTION="${1:-stop}"

echo "=== Coordinador: [$ACTION] $CONTAINER ==="

case "$ACTION" in
    stop|kill)
        echo "→ Deteniendo el contenedor del coordinador ($CONTAINER)..."
        docker stop "$CONTAINER"
        echo "✓ Coordinador detenido — simula caída del proceso coordinador"
        ;;

    start)
        echo "→ Iniciando el contenedor del coordinador ($CONTAINER)..."
        docker start "$CONTAINER"
        echo "✓ Coordinador iniciado — listo para reanudar transacciones"
        ;;

    restart)
        echo "→ Reiniciando el contenedor del coordinador ($CONTAINER)..."
        docker stop "$CONTAINER"
        sleep 2
        docker start "$CONTAINER"
        echo "✓ Coordinador reiniciado — ciclo completo de caída + recuperación"
        ;;

    status)
        echo -n "→ Estado del coordinador: "
        docker inspect -f '{{.State.Status}}' "$CONTAINER" 2>/dev/null || echo "no encontrado"
        ;;

    *)
        echo "ERROR: acción '$ACTION' no reconocida. Use stop, start, restart o status."
        exit 1
        ;;
esac
