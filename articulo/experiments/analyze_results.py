#!/usr/bin/env python3
# analyze_results.py — Análisis estadístico y generación de gráficas
# Lee CSVs de experiments/results/, calcula medias/desviaciones,
# y genera gráficas PNG comparativas.

import os
import csv
import sys
import statistics
from collections import defaultdict

# Verificar matplotlib
try:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import matplotlib.ticker as mticker
    HAS_MATPLOTLIB = True
except ImportError:
    HAS_MATPLOTLIB = False
    print("⚠ matplotlib no instalado. Instale con: pip install matplotlib")
    print("   Se generarán solo estadísticas de texto, sin gráficas.")


RESULT_DIR = os.environ.get("RESULT_DIR", "results")
GRAPH_DIR = os.environ.get("GRAPH_DIR", "../experiments/graphs")
DEFAULT_PROTOCOLOS = ["2pc", "saga", "tcc", "raft"]
DEFAULT_ESCENARIOS = ["A", "B", "C", "D"]

ESC_LABELS = {
    "A": "Éxito (sin fallos)",
    "B": "Fallo de red",
    "C": "Caída de nodo",
    "D": "Recuperación",
}

COLORS = {"2pc": "#2196F3", "saga": "#FF9800", "tcc": "#4CAF50", "raft": "#E91E63"}


# ===========================================================================
# Lectura de CSVs
# ===========================================================================

def load_data(result_dir, protocolos=None, escenarios=None):
    """Carga todos los CSVs en un dict: data[protocolo][escenario] = [filas]."""
    if protocolos is None:
        protocolos = DEFAULT_PROTOCOLOS
    if escenarios is None:
        escenarios = DEFAULT_ESCENARIOS

    data = defaultdict(lambda: defaultdict(list))

    for proto in protocolos:
        for esc in escenarios:
            path = os.path.join(result_dir, f"{proto}_{esc}.csv")
            if not os.path.exists(path):
                print(f"  ⚠ No encontrado: {path} — saltando")
                continue

            with open(path, "r", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    data[proto][esc].append(row)

            if data[proto][esc]:
                print(f"  ✓ {proto}_{esc}: {len(data[proto][esc])} filas")

    return data


# ===========================================================================
# Cómputo de estadísticas
# ===========================================================================

def compute_stats(data):
    """Calcula medias, desv.std, tasa de éxito, compensaciones.

    Returns:
        stats[protocolo][escenario] = {
            "latency_mean": float, "latency_std": float,
            "success_rate": float (0-1),
            "compensations_mean": float,
            "n": int,
        }
    """
    stats = defaultdict(dict)

    for proto, escenarios in data.items():
        for esc, filas in escenarios.items():
            if not filas:
                continue

            latencies = []
            compensaciones_list = []
            exitos = 0

            for f in filas:
                try:
                    lat = float(f.get("total_latency_ms", 0))
                    latencies.append(lat)
                except (ValueError, TypeError):
                    pass

                try:
                    comp = int(f.get("compensaciones", 0))
                    compensaciones_list.append(comp)
                except (ValueError, TypeError):
                    compensaciones_list.append(0)

                if f.get("exito", "").lower() == "true":
                    exitos += 1
                elif f.get("exito", "").lower() == "false":
                    pass  # ya contado
                else:
                    # intentar interpretar desde observaciones
                    obs = f.get("observaciones", "")
                    if any(kw in obs for kw in ["COMMIT", "COMPLETA", "EXITOSA", "committed"]):
                        exitos += 1

            n = len(latencies)
            stats[proto][esc] = {
                "latency_mean": round(statistics.mean(latencies), 2) if latencies else 0,
                "latency_std": round(statistics.stdev(latencies), 2) if len(latencies) > 1 else 0,
                "success_rate": round(exitos / n, 3) if n > 0 else 0,
                "compensations_mean": round(statistics.mean(compensaciones_list), 2) if compensaciones_list else 0,
                "n": n,
            }

    return stats


# ===========================================================================
# Tabla comparativa (texto)
# ===========================================================================

def print_table(stats, title="Resultados"):
    print(f"\n{'=' * 100}")
    print(f"  {title}")
    print(f"{'=' * 100}")
    header = f"{'Protocolo':<10} {'Esc':<4} {'N':<6} {'Latencia μ (ms)':<16} {'Latencia σ':<12} {'Éxito %':<10} {'Comp. μ':<10}"
    print(header)
    print("-" * 100)

    for proto in DEFAULT_PROTOCOLOS:
        for esc in DEFAULT_ESCENARIOS:
            if esc not in stats.get(proto, {}):
                continue
            s = stats[proto][esc]
            print(f"{proto:<10} {esc:<4} {s['n']:<6} {s['latency_mean']:<16.2f} {s['latency_std']:<12.2f} {s['success_rate']*100:<10.1f} {s['compensations_mean']:<10.2f}")

    print("-" * 100)


# ===========================================================================
# Gráficas
# ===========================================================================

def plot_latency_comparison(stats, graph_dir):
    """Gráfico de barras: latencia media por protocolo y escenario."""
    if not HAS_MATPLOTLIB:
        return

    fig, ax = plt.subplots(figsize=(12, 6))
    x = range(len(DEFAULT_ESCENARIOS))
    width = 0.2

    for i, proto in enumerate(DEFAULT_PROTOCOLOS):
        means = []
        stds = []
        for esc in DEFAULT_ESCENARIOS:
            s = stats.get(proto, {}).get(esc, {})
            means.append(s.get("latency_mean", 0))
            stds.append(s.get("latency_std", 0))

        bars = ax.bar(
            [xi + i * width for xi in x], means, width,
            label=proto.upper(), color=COLORS[proto], yerr=stds, capsize=3,
        )

    ax.set_xlabel("Escenario", fontweight="bold")
    ax.set_ylabel("Latencia total (ms)", fontweight="bold")
    ax.set_title("Latencia media por protocolo y escenario", fontweight="bold", fontsize=13)
    ax.set_xticks([xi + 1.5 * width for xi in x])
    ax.set_xticklabels([f"{esc}\n{ESC_LABELS[esc]}" for esc in DEFAULT_ESCENARIOS], fontsize=9)
    ax.legend(fontsize=9)
    ax.grid(axis="y", alpha=0.3)
    plt.tight_layout()
    path = os.path.join(graph_dir, "latencia_comparativa.png")
    plt.savefig(path, dpi=150)
    plt.close()
    print(f"  → Gráfica guardada: {path}")


def plot_success_rate(stats, graph_dir):
    """Gráfico de barras: tasa de éxito por protocolo y escenario."""
    if not HAS_MATPLOTLIB:
        return

    fig, ax = plt.subplots(figsize=(12, 6))
    x = range(len(DEFAULT_ESCENARIOS))
    width = 0.2

    for i, proto in enumerate(DEFAULT_PROTOCOLOS):
        rates = []
        for esc in DEFAULT_ESCENARIOS:
            s = stats.get(proto, {}).get(esc, {})
            rates.append(s.get("success_rate", 0) * 100)

        ax.bar(
            [xi + i * width for xi in x], rates, width,
            label=proto.upper(), color=COLORS[proto],
        )

    ax.set_xlabel("Escenario", fontweight="bold")
    ax.set_ylabel("Tasa de éxito (%)", fontweight="bold")
    ax.set_title("Tasa de éxito por protocolo y escenario", fontweight="bold", fontsize=13)
    ax.set_xticks([xi + 1.5 * width for xi in x])
    ax.set_xticklabels([f"{esc}\n{ESC_LABELS[esc]}" for esc in DEFAULT_ESCENARIOS], fontsize=9)
    ax.set_ylim(0, 110)
    ax.legend(fontsize=9)
    ax.grid(axis="y", alpha=0.3)
    plt.tight_layout()
    path = os.path.join(graph_dir, "tasa_exito.png")
    plt.savefig(path, dpi=150)
    plt.close()
    print(f"  → Gráfica guardada: {path}")


def plot_compensations(stats, graph_dir):
    """Gráfico de compensaciones promedio por protocolo."""
    if not HAS_MATPLOTLIB:
        return

    fig, ax = plt.subplots(figsize=(10, 5))
    x = range(len(DEFAULT_PROTOCOLOS))
    means = []
    for proto in DEFAULT_PROTOCOLOS:
        vals = [stats.get(proto, {}).get(esc, {}).get("compensations_mean", 0)
                for esc in DEFAULT_ESCENARIOS]
        means.append(statistics.mean(vals) if vals else 0)

    bars = ax.bar(x, means, color=[COLORS[p] for p in DEFAULT_PROTOCOLOS])
    ax.set_xticks(x)
    ax.set_xticklabels([p.upper() for p in DEFAULT_PROTOCOLOS])
    ax.set_ylabel("Compensaciones promedio", fontweight="bold")
    ax.set_title("Compensaciones promedio por protocolo", fontweight="bold", fontsize=13)

    for bar, val in zip(bars, means):
        ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 0.02,
                f"{val:.2f}", ha="center", fontsize=9)

    ax.grid(axis="y", alpha=0.3)
    plt.tight_layout()
    path = os.path.join(graph_dir, "compensaciones.png")
    plt.savefig(path, dpi=150)
    plt.close()
    print(f"  → Gráfica guardada: {path}")


def plot_recovery_time(stats, graph_dir):
    """Gráfico: latencia en escenario D (recuperación) por protocolo."""
    if not HAS_MATPLOTLIB:
        return

    fig, ax = plt.subplots(figsize=(8, 5))
    protos = []
    means = []
    stds = []

    for proto in DEFAULT_PROTOCOLOS:
        s = stats.get(proto, {}).get("D", {})
        if s:
            protos.append(proto.upper())
            means.append(s.get("latency_mean", 0))
            stds.append(s.get("latency_std", 0))

    bars = ax.bar(protos, means, color=[COLORS[p] for p in DEFAULT_PROTOCOLOS if p.upper() in protos],
                  yerr=stds, capsize=5)
    ax.set_ylabel("Latencia de recuperación (ms)", fontweight="bold")
    ax.set_title("Tiempo de recuperación por protocolo (Escenario D)", fontweight="bold", fontsize=13)
    ax.grid(axis="y", alpha=0.3)

    for bar, val in zip(bars, means):
        ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 0.5,
                f"{val:.1f}", ha="center", fontsize=10)

    plt.tight_layout()
    path = os.path.join(graph_dir, "recovery_time.png")
    plt.savefig(path, dpi=150)
    plt.close()
    print(f"  → Gráfica guardada: {path}")


# ===========================================================================
# Main
# ===========================================================================

if __name__ == "__main__":
    result_dir = sys.argv[1] if len(sys.argv) > 1 else RESULT_DIR
    graph_dir = sys.argv[2] if len(sys.argv) > 2 else GRAPH_DIR

    os.makedirs(graph_dir, exist_ok=True)

    print("=== Análisis de resultados experimentales ===\n")

    print("Cargando CSVs...")
    data = load_data(result_dir)

    if not data:
        print("ERROR: No se encontraron CSVs. Ejecute primero los experimentos.")
        sys.exit(1)

    print("\nCalculando estadísticas...")
    stats = compute_stats(data)

    # Tabla
    print_table(stats, "Comparativa 4 protocolos × 4 escenarios")

    # Gráficas
    print("\nGenerando gráficas...")
    plot_latency_comparison(stats, graph_dir)
    plot_success_rate(stats, graph_dir)
    plot_compensations(stats, graph_dir)
    plot_recovery_time(stats, graph_dir)

    print("\n✓ Análisis completado")
