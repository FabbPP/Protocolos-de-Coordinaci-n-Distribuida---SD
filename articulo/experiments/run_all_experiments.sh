#!/bin/sh
# run_all_experiments.sh — Ejecuta 16 combinaciones con reset de BD entre cada una
cd /app/experiments
mkdir -p results

reset_dbs() {
  for node in pg-arequipa pg-cusco pg-lima; do
    psql -U sdhm -h $node -d banco_arequipa -c "UPDATE cuentas SET saldo = 50000 WHERE titular = 'Alvaro Quispe'" 2>/dev/null || true
    psql -U sdhm -h $node -d banco_cusco    -c "UPDATE cuentas SET saldo = 30000 WHERE titular = 'Mathias Barrios'" 2>/dev/null || true
    psql -U sdhm -h $node -d banco_lima     -c "UPDATE cuentas SET saldo = 20000 WHERE titular = 'Fabiana Pacheco'" 2>/dev/null || true
  done
  for db in banco_arequipa banco_cusco banco_lima; do
    psql -U sdhm -h pg-arequipa -d $db -c "DELETE FROM raft_log" 2>/dev/null || true
    psql -U sdhm -h pg-cusco    -d $db -c "DELETE FROM raft_log" 2>/dev/null || true
    psql -U sdhm -h pg-lima     -d $db -c "DELETE FROM raft_log" 2>/dev/null || true
    psql -U sdhm -h pg-arequipa -d $db -c "DELETE FROM reservas" 2>/dev/null || true
    psql -U sdhm -h pg-cusco    -d $db -c "DELETE FROM reservas" 2>/dev/null || true
    psql -U sdhm -h pg-lima     -d $db -c "DELETE FROM reservas" 2>/dev/null || true
  done
}

for proto in 2pc saga tcc raft; do
  for esc in A B C D; do
    echo "============================================"
    echo "  $proto / $esc"
    echo "============================================"
    reset_dbs
    PROTOCOLO=$proto ESCENARIO=$esc N_ITER=3 REPETICIONES=5 CSV_OUT=results/${proto}_${esc}.csv python client_load.py
    echo ""
  done
done

echo "✓ Todos los experimentos completados"
ls -la results/*.csv
