#!/bin/sh
# run_experiments.sh — ejecuta todos los experimentos desde dentro del contenedor
cd /app/experiments
mkdir -p results

for proto in 2pc saga tcc raft; do
  for esc in A B C D; do
    echo "=== $proto / $esc ==="
    PROTOCOLO=$proto ESCENARIO=$esc N_ITER=3 REPETICIONES=5 CSV_OUT=results/${proto}_${esc}.csv python client_load.py
    echo ""
  done
done

echo "✓ Todos los experimentos completados"
ls -la results/*.csv
