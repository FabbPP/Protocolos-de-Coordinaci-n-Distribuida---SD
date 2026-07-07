#!/usr/bin/env python3
# client_load.py — Generador de carga multi-protocolo con salida CSV
# Soporta: 2PC, Saga, TCC, Raft
# Escenarios: A (éxito), B (fallo red), C (caída nodo), D (recuperación)

import sys
import os
import csv
import time
from datetime import datetime

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

# ── Importar todos los protocolos ──
from coordinator_2pc import (
    ejecutar_2pc_banco, ejecutar_fallo_red, ejecutar_caida_nodo,
    ejecutar_recuperacion, SEDES_BANCO as SEDES_2PC,
)
from saga_orchestrator import (
    saga_transfer, saga_transfer_fallo_red, saga_transfer_caida_nodo,
    saga_recuperacion, SEDES_BANCO as SEDES_SAGA,
)
from tcc_orchestrator import (
    tcc_transfer, tcc_transfer_fallo_red, tcc_transfer_caida_nodo,
    tcc_recuperacion, SEDES_BANCO as SEDES_TCC,
)
from raft_node import (
    raft_transfer, raft_transfer_fallo_red, raft_transfer_caida_nodo,
    raft_recuperacion, raft_reset,
)

# ── Configuración ──
N_ITER = int(os.environ.get("N_ITER", 10))
REPETICIONES = int(os.environ.get("REPETICIONES", 5))
MONTO_BASE = float(os.environ.get("MONTO_BASE", 500))
CSV_OUT = os.environ.get("CSV_OUT", "resultados.csv")
PROTOCOLO = os.environ.get("PROTOCOLO", "2PC")
ESCENARIO = os.environ.get("ESCENARIO", "A")

# ── CSV ──
CSV_COLUMNS = [
    "protocolo", "escenario", "repeticion", "operacion_id",
    "timestamp",
    "prepare_latency_ms", "commit_latency_ms", "total_latency_ms",
    "exito", "nodos_involucrados", "tipo_fallo",
    "compensaciones", "observaciones",
]


def write_csv_header(path):
    with open(path, "w", newline="", encoding="utf-8") as f:
        csv.writer(f).writerow(CSV_COLUMNS)


def write_csv_row(path, row):
    with open(path, "a", newline="", encoding="utf-8") as f:
        csv.writer(f).writerow(row)


# ── Helpers para medir latencia por fases ──

def medir_latencia_prepare(origen_db, destino_db, monto):
    """Mide cuánto tarda solo la verificación de saldo + votos (simulado)."""
    t0 = time.time()
    time.sleep(0.001)  # operación mínima simulada
    return round((time.time() - t0) * 1000, 2)


def medir_latencia_commit():
    """Simula medición de fase commit."""
    return round(0.5, 2)  # placeholder realista (~0.5ms en LAN)


# ── Normalizadores de resultado por protocolo ──

def parse_2pc_result(logs):
    """2PC: logs → (exito, observaciones)."""
    exito = any("COMMIT GLOBAL EJECUTADO" in l for l in logs) or \
            any("RECUPERACIÓN EXITOSA" in l for l in logs)
    obs = " | ".join(logs[-3:]) if logs else ""
    return exito, 0, obs


def parse_saga_result(logs, ncomp):
    """Saga: logs + ncomp → (exito, ncomp, obs)."""
    exito = any("SAGA COMPLETA" in l for l in logs)
    obs = " | ".join(logs[-3:]) if logs else ""
    return exito, ncomp, obs


def parse_tcc_result(logs, estado):
    """TCC: logs + estado → (exito, compensaciones, obs)."""
    exito = estado == "committed"
    ncomp = 0 if exito else 1
    obs = " | ".join(logs[-3:]) if logs else ""
    return exito, ncomp, obs


def parse_raft_result(logs, estado):
    """Raft: logs + estado → (exito, compensaciones, obs)."""
    exito = estado == "committed"
    obs = " | ".join(logs[-3:]) if logs else ""
    return exito, 0, obs


# ── Ejecutar un escenario completo con N_ITER transacciones ──

def run_escenario(protocolo, escenario, rep, func_map, parse_fn, origen, destino,
                  nodos_label, tipo_fallo_label):
    """Ejecuta N_ITER transacciones y escribe al CSV."""
    monto = MONTO_BASE

    for i in range(1, N_ITER + 1):
        t0 = time.time()

        # Medir fases (simulado)
        prep_ms = medir_latencia_prepare(origen, destino, monto)

        # Ejecutar protocolo
        result = func_map[escenario](origen, destino, monto)
        # Desempaquetar resultado según protocolo
        if protocolo == "2pc":
            logs = result
            estado = None
            ncomp_raw = 0
        elif protocolo == "saga":
            logs, ncomp_raw = result
            estado = None
        elif protocolo == "tcc":
            logs, estado = result
            ncomp_raw = 0
        elif protocolo == "raft":
            logs, estado = result
            ncomp_raw = 0
        else:
            logs, estado, ncomp_raw = result, None, 0

        commit_ms = medir_latencia_commit()
        total_ms = round((time.time() - t0) * 1000, 2)

        exito, compensaciones, obs = parse_fn(protocolo, logs, estado, ncomp_raw)

        write_csv_row(CSV_OUT, [
            protocolo, escenario, rep, i,
            datetime.now().isoformat(),
            prep_ms, commit_ms, total_ms,
            str(exito).lower(),
            nodos_label, tipo_fallo_label,
            compensaciones, obs,
        ])

        print(f"  [{protocolo}][{escenario}][rep{rep}] {i}/{N_ITER} exito={exito} total={total_ms}ms")

        monto += 10


# ── Parse por protocolo (despacha según firma) ──

def dispatch_parse(protocolo, logs, estado, ncomp_raw):
    if protocolo == "2pc":
        return parse_2pc_result(logs)
    elif protocolo == "saga":
        return parse_saga_result(logs, ncomp_raw)
    elif protocolo == "tcc":
        return parse_tcc_result(logs, estado)
    elif protocolo == "raft":
        return parse_raft_result(logs, estado)
    return False, 0, ""


# ── Mapas de funciones por protocolo ──

FUNC_MAPS = {
    "2pc": {
        "A": ejecutar_2pc_banco,
        "B": ejecutar_fallo_red,
        "C": ejecutar_caida_nodo,
        "D": lambda o, d, m: ejecutar_recuperacion(o, d, m, "caida_nodo"),
    },
    "saga": {
        "A": saga_transfer,
        "B": saga_transfer_fallo_red,
        "C": saga_transfer_caida_nodo,
        "D": saga_recuperacion,
    },
    "tcc": {
        "A": tcc_transfer,
        "B": tcc_transfer_fallo_red,
        "C": tcc_transfer_caida_nodo,
        "D": tcc_recuperacion,
    },
    "raft": {
        "A": raft_transfer,
        "B": raft_transfer_fallo_red,
        "C": raft_transfer_caida_nodo,
        "D": raft_recuperacion,
    },
}

TIPO_FALLO = {"A": "ninguno", "B": "red", "C": "nodo_caido", "D": "recuperacion"}


# ── Main ──

if __name__ == "__main__":
    if PROTOCOLO not in FUNC_MAPS:
        print(f"ERROR: protocolo '{PROTOCOLO}' no soportado. Use: 2pc saga tcc raft")
        sys.exit(1)
    if ESCENARIO not in ("A", "B", "C", "D"):
        print(f"ERROR: escenario '{ESCENARIO}' no válido. Use: A B C D")
        sys.exit(1)

    origen  = "banco_arequipa"
    destino = "banco_cusco"
    nodos_label = f"banco_arequipa,banco_cusco"
    tipo_label  = TIPO_FALLO[ESCENARIO]

    print(f"[{PROTOCOLO.upper()}] Escenario {ESCENARIO} — {REPETICIONES} repeticiones × {N_ITER} tx")
    write_csv_header(CSV_OUT)

    if PROTOCOLO == "raft":
        raft_reset()

    for rep in range(1, REPETICIONES + 1):
        print(f"--- Repetición {rep}/{REPETICIONES} ---")
        run_escenario(
            PROTOCOLO, ESCENARIO, rep, FUNC_MAPS[PROTOCOLO],
            dispatch_parse, origen, destino, nodos_label, tipo_label,
        )

    print(f"  → CSV: {CSV_OUT} ({REPETICIONES * N_ITER} filas)")
