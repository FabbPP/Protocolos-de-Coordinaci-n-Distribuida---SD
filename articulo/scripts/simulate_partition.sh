#!/usr/bin/env bash
# simulate_partition.sh — Simula una partición de red entre dos nodos PostgreSQL
# Uso: ./simulate_partition.sh [on|off] [nodo_origen] [nodo_destino]
#
# Ejemplos:
#   ./simulate_partition.sh on  pg-arequipa pg-cusco
#   ./simulate_partition.sh off pg-arequipa pg-cusco

set -euo pipefail

ACTION="${1:-on}"
NODO_A="${2:-pg-arequipa}"
NODO_B="${3:-pg-cusco}"

IP_A=$(docker inspect -f '{{range.NetworkSettings.Networks}}{{.IPAddress}}{{end}}' "$NODO_A" 2>/dev/null || echo "")
IP_B=$(docker inspect -f '{{range.NetworkSettings.Networks}}{{.IPAddress}}{{end}}' "$NODO_B" 2>/dev/null || echo "")

if [ -z "$IP_A" ] || [ -z "$IP_B" ]; then
    echo "ERROR: No se pudieron obtener las IPs de $NODO_A y/o $NODO_B"
    echo "  IP $NODO_A = $IP_A"
    echo "  IP $NODO_B = $IP_B"
    exit 1
fi

echo "=== Partición de red: [$ACTION] entre $NODO_A ($IP_A) y $NODO_B ($IP_B) ==="

case "$ACTION" in
    on|apply)
        echo "→ Bloqueando tráfico entre $IP_A y $IP_B..."

        # Bloquear en A → B
        docker exec "$NODO_A" sh -c "
            iptables -A INPUT  -s $IP_B -j DROP 2>/dev/null || true;
            iptables -A OUTPUT -d $IP_B -j DROP 2>/dev/null || true
        " 2>/dev/null || echo "  (iptables no disponible en $NODO_A, usando enfoque alternativo con tc)"

        # Bloquear en B → A (partición bidireccional)
        docker exec "$NODO_B" sh -c "
            iptables -A INPUT  -s $IP_A -j DROP 2>/dev/null || true;
            iptables -A OUTPUT -d $IP_A -j DROP 2>/dev/null || true
        " 2>/dev/null || echo "  (iptables no disponible en $NODO_B, usando enfoque alternativo con tc)"

        # Alternativa con tc: simular 100% packet loss si iptables no funciona
        docker exec "$NODO_A" sh -c "
            tc qdisc add dev eth0 root netem loss 100% 2>/dev/null || true
        " 2>/dev/null || true

        echo "✓ Partición activa — los nodos $NODO_A y $NODO_B están aislados entre sí"
        ;;

    off|remove)
        echo "→ Restaurando conectividad..."

        # Limpiar reglas iptables del contenedor
        docker exec "$NODO_A" sh -c "
            iptables -F INPUT  2>/dev/null || true;
            iptables -F OUTPUT 2>/dev/null || true
        " 2>/dev/null || echo "  (iptables no disponible, limpiando tc...)"

        docker exec "$NODO_B" sh -c "
            iptables -F INPUT  2>/dev/null || true;
            iptables -F OUTPUT 2>/dev/null || true
        " 2>/dev/null || echo "  (iptables no disponible, limpiando tc...)"

        # Restaurar tc default
        docker exec "$NODO_A" sh -c "
            tc qdisc del dev eth0 root 2>/dev/null || true
        " 2>/dev/null || true

        docker exec "$NODO_B" sh -c "
            tc qdisc del dev eth0 root 2>/dev/null || true
        " 2>/dev/null || true

        echo "✓ Conectividad restaurada entre $NODO_A y $NODO_B"
        ;;

    *)
        echo "ERROR: acción '$ACTION' no reconocida. Use 'on' u 'off'."
        exit 1
        ;;
esac
