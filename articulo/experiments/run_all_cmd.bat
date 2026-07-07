@echo off
REM run_all_experiments.cmd — ejecuta 16 combinaciones desde el host Windows
setlocal enabledelayedexpansion

set ESCENARIOS=A B C D
set PROTOCOLOS=2pc saga tcc raft
set RESET_SQL=UPDATE cuentas SET saldo = 50000 WHERE titular = 'Alvaro Quispe'; UPDATE cuentas SET saldo = 30000 WHERE titular = 'Mathias Barrios'; UPDATE cuentas SET saldo = 20000 WHERE titular = 'Fabiana Pacheco'

for %%p in (%PROTOCOLOS%) do (
  for %%e in (%ESCENARIOS%) do (
    echo ========================================
    echo   %%p / %%e
    echo ========================================

    REM Reset Arequipa
    docker exec pg-arequipa sh -c "psql -U sdhm -d banco_arequipa -c '%RESET_SQL%'" 2>nul
    docker exec pg-arequipa sh -c "psql -U sdhm -d banco_arequipa -c 'DELETE FROM raft_log'" 2>nul

    REM Reset Lima
    docker exec pg-lima sh -c "psql -U sdhm -d banco_lima -c '%RESET_SQL%'" 2>nul
    docker exec pg-lima sh -c "psql -U sdhm -d banco_lima -c 'DELETE FROM raft_log'" 2>nul

    REM Reset Cusco
    docker exec pg-cusco sh -c "psql -U sdhm -d banco_cusco -c '%RESET_SQL%'" 2>nul
    docker exec pg-cusco sh -c "psql -U sdhm -d banco_cusco -c 'DELETE FROM raft_log'" 2>nul

    docker exec two-pc-app sh -c "cd /app/experiments && PROTOCOLO=%%p ESCENARIO=%%e N_ITER=3 REPETICIONES=5 CSV_OUT=results/%%p_%%e.csv python client_load.py"
    echo.
  )
)
echo Done.
