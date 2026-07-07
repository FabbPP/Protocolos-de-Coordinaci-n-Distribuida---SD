#!/usr/bin/env python3
# analyze_results.py — Análisis estadístico y generación de gráficas
# Lee CSVs de experiments/results/, calcula medias/desviaciones,
# y genera gráficas PNG comparativas.

import os
import csv
import sys
import statistics
from collections import defaultdict

# Forzar UTF-8 para compatibilidad con caracteres Unicode en Windows
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# Verificar matplotlib
try:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import matplotlib.ticker as mticker
    HAS_MATPLOTLIB = True
except ImportError:
    HAS_MATPLOTLIB = False
    print("[!] matplotlib no instalado. Instale con: pip install matplotlib")
    print("    Se generaran solo estadisticas de texto, sin graficas.")


_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
RESULT_DIR = os.environ.get("RESULT_DIR", os.path.join(_SCRIPT_DIR, "results"))
GRAPH_DIR = os.environ.get("GRAPH_DIR", os.path.join(_SCRIPT_DIR, "graphs"))
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
# Dashboard interactivo (Streamlit + Plotly)
# ===========================================================================

def run_dashboard():
    """Lanza el dashboard dinámico con Streamlit."""
    import streamlit as st
    import plotly.express as px
    import plotly.graph_objects as go
    import pandas as pd

    st.set_page_config(
        page_title="Protocolos de Coordinacion Distribuida - Dashboard",
        layout="wide",
        initial_sidebar_state="expanded",
    )

    # ── Sidebar ──────────────────────────────────────────────────────────
    st.sidebar.title("Controles")
    st.sidebar.markdown("---")

    selected_protocols = st.sidebar.multiselect(
        "Protocolos",
        DEFAULT_PROTOCOLOS,
        default=DEFAULT_PROTOCOLOS,
        format_func=lambda x: x.upper(),
    )
    selected_scenarios = st.sidebar.multiselect(
        "Escenarios",
        DEFAULT_ESCENARIOS,
        default=DEFAULT_ESCENARIOS,
        format_func=lambda x: f"{x} – {ESC_LABELS[x]}",
    )
    st.sidebar.markdown("---")
    st.sidebar.markdown(
        "**Que es esto?**\n\n"
        "Dashboard interactivo que compara 4 protocolos de coordinacion "
        "distribuida (2PC, Saga, TCC, Raft) en 4 escenarios de fallo."
    )

    st.sidebar.markdown("---")
    if st.sidebar.button("Recargar datos", width="stretch"):
        st.rerun()

    # ── Carga de datos ───────────────────────────────────────────────────
    @st.cache_resource
    def load_data_cached():
        return dict(load_data(
            RESULT_DIR,
            protocolos=DEFAULT_PROTOCOLOS,
            escenarios=DEFAULT_ESCENARIOS,
        ))

    @st.cache_resource
    def compute_stats_cached(data_dict):
        return compute_stats(data_dict)

    @st.cache_data
    def to_dataframe(data_dict):
        rows = []
        for proto, escs in data_dict.items():
            for esc, filas in escs.items():
                for f in filas:
                    f["protocolo"] = proto
                    f["escenario"] = esc
                    rows.append(f)
        return pd.DataFrame(rows)

    raw_data = load_data_cached()
    if not raw_data:
        st.error("No se encontraron CSVs. Ejecute primero los experimentos.")
        st.stop()

    stats = compute_stats_cached(raw_data)
    df = to_dataframe(raw_data)

    # Convertir columnas numéricas
    for col in ["total_latency_ms", "prepare_latency_ms", "commit_latency_ms",
                 "repeticion", "operacion_id", "compensaciones"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    # Filtrar por selección
    df_filtered = df[
        df["protocolo"].isin(selected_protocols) &
        df["escenario"].isin(selected_scenarios)
    ]

    # ── Header ───────────────────────────────────────────────────────────
    st.title("Protocolos de Coordinacion Distribuida")
    st.markdown(
        "### Análisis experimental de 2PC, Saga, TCC y Raft bajo fallos "
        "en sistemas de bases de datos distribuidas"
    )
    st.markdown("---")

    # ── Métricas globales ────────────────────────────────────────────────
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        total_ops = len(df_filtered)
        st.metric("Operaciones totales", total_ops)
    with col2:
        avg_lat = df_filtered["total_latency_ms"].mean()
        st.metric("Latencia media (ms)", f"{avg_lat:.2f}" if pd.notna(avg_lat) else "N/A")
    with col3:
        success_count = df_filtered["exito"].value_counts().get("true", 0)
        success_pct = (success_count / total_ops * 100) if total_ops else 0
        st.metric("Tasa de exito", f"{success_pct:.1f}%")
    with col4:
        avg_comp = df_filtered["compensaciones"].mean()
        st.metric("Compensaciones promedio", f"{avg_comp:.2f}" if pd.notna(avg_comp) else "N/A")

    st.markdown("---")

    # ── Tabs ─────────────────────────────────────────────────────────────
    tab_overview, tab_latency, tab_success, tab_comp, tab_recovery, tab_raw = \
        st.tabs([
            "Vision General",
            "Latencia",
            "Tasa de Exito",
            "Compensaciones",
            "Recuperacion",
            "Datos Crudos",
        ])

    # =====================================================================
    # TAB 1: Visión General
    # =====================================================================
    with tab_overview:
        st.subheader("Vision General del Experimento")

        st.markdown("""
        Este experimento evalúa **4 protocolos de coordinación distribuida**
        simulando un sistema de transferencias bancarias entre 2 nodos
        (*Banco Arequipa* y *Banco Cusco*).

        | Protocolo | Filosofía |
        |---|---|
        | **2PC (Two-Phase Commit)** | Coordinador central con votación + decisión global |
        | **Saga** | Transacciones secuenciales con compensaciones por paso |
        | **TCC (Try-Confirm/Cancel)** | Reserva tentativa → confirmación o cancelación |
        | **Raft** | Consenso distribuido basado en líder y réplicas |
        """)

        st.markdown("#### Escenarios de fallo simulados")
        esc_df = pd.DataFrame({
            "Escenario": list(ESC_LABELS.keys()),
            "Descripción": list(ESC_LABELS.values()),
            "Tipo de fallo": ["Ninguno", "Red", "Nodo", "Recuperación"],
        })
        st.table(esc_df)

        st.markdown("#### Distribución de datos cargados")
        proto_counts = df_filtered.groupby(["protocolo", "escenario"]).size().unstack(fill_value=0)
        st.dataframe(proto_counts, width="stretch")

        st.markdown("#### Estadísticas consolidadas")
        stats_rows = []
        for proto in selected_protocols:
            for esc in selected_scenarios:
                s = stats.get(proto, {}).get(esc)
                if s:
                    stats_rows.append({
                        "Protocolo": proto.upper(), "Escenario": esc,
                        "N": s["n"], "Latencia μ (ms)": s["latency_mean"],
                        "Latencia σ": s["latency_std"],
                        "Éxito %": f"{s['success_rate']*100:.1f}",
                        "Comp. μ": s["compensations_mean"],
                    })
        if stats_rows:
            st.dataframe(pd.DataFrame(stats_rows), width="stretch", hide_index=True)

    # =====================================================================
    # TAB 2: Latencia
    # =====================================================================
    with tab_latency:
        st.subheader("Analisis de Latencia")
        st.markdown("""
        La **latencia total** mide el tiempo (en milisegundos) que toma completar
        una transacción desde que inicia hasta que finaliza (commit o rollback).

        - **Menor latencia** = mejor rendimiento
        - La desviación estándar (σ) indica **variabilidad**: valores altos
          implican comportamiento impredecible
        - En escenarios con fallos, la latencia incluye *timeouts*, *retries*
          y *compensaciones*
        """)

        # Gráfico de barras agrupadas
        fig = go.Figure()
        x = list(range(len(selected_scenarios)))
        width = 0.2

        for i, proto in enumerate(selected_protocols):
            means = []
            stds = []
            for esc in selected_scenarios:
                s = stats.get(proto, {}).get(esc, {})
                means.append(s.get("latency_mean", 0))
                stds.append(s.get("latency_std", 0))

            fig.add_trace(go.Bar(
                name=proto.upper(),
                x=[f"{esc}<br><sub>{ESC_LABELS[esc]}</sub>" for esc in selected_scenarios],
                y=means,
                error_y=dict(type="data", array=stds, visible=True),
                marker_color=COLORS[proto],
                width=0.18,
                text=[f"{m:.1f}" for m in means],
                textposition="outside",
            ))

        fig.update_layout(
            title="Latencia media por protocolo y escenario",
            xaxis_title="Escenario",
            yaxis_title="Latencia total (ms)",
            barmode="group",
            height=500,
            hovermode="x unified",
            template="plotly_white",
            legend=dict(orientation="h", y=1.12),
        )
        st.plotly_chart(fig, width="stretch")

        st.markdown("#### Conclusiones de latencia")
        conclusions = []
        for esc in selected_scenarios:
            vals = [(p, stats.get(p, {}).get(esc, {}).get("latency_mean", 0))
                    for p in selected_protocols]
            vals = [(p, v) for p, v in vals if v > 0]
            if vals:
                best = min(vals, key=lambda x: x[1])
                worst = max(vals, key=lambda x: x[1])
                conclusions.append(
                    f"- **{ESC_LABELS[esc]}**: "
                    f"más rápido → **{best[0].upper()}** ({best[1]:.1f} ms), "
                    f"más lento → **{worst[0].upper()}** ({worst[1]:.1f} ms)"
                )
        for c in conclusions:
            st.markdown(c)

        # Distribución de latencias (box plot)
        st.markdown("---")
        st.markdown("#### Distribucion de latencias por protocolo")
        fig_box = px.box(
            df_filtered,
            x="protocolo", y="total_latency_ms", color="protocolo",
            facet_col="escenario", facet_row=None,
            color_discrete_map=COLORS,
            labels={"protocolo": "Protocolo", "total_latency_ms": "Latencia (ms)"},
            category_orders={"protocolo": DEFAULT_PROTOCOLOS},
            points="outliers",
            title="Distribución de latencias (agrupado por escenario)",
        )
        fig_box.update_layout(
            height=500, template="plotly_white", showlegend=False,
        )
        fig_box.for_each_annotation(lambda a: a.update(
            text=f"{a.text.split('=')[1]} – {ESC_LABELS.get(a.text.split('=')[1], '')}"
        ))
        st.plotly_chart(fig_box, width="stretch")

    # =====================================================================
    # TAB 3: Tasa de Éxito
    # =====================================================================
    with tab_success:
        st.subheader("Analisis de Tasa de Exito")
        st.markdown("""
        La **tasa de éxito** mide qué porcentaje de transacciones se completaron
        satisfactoriamente en cada escenario.

        - **100%** = todas las transacciones llegaron a *commit* / finalizaron correctamente
        - **0%** = todas fueron abortadas / compensadas
        - Ideal: mantener alta tasa de éxito incluso bajo fallos
        """)

        fig = go.Figure()
        for i, proto in enumerate(selected_protocols):
            rates = []
            for esc in selected_scenarios:
                s = stats.get(proto, {}).get(esc, {})
                rates.append(s.get("success_rate", 0) * 100)

            fig.add_trace(go.Bar(
                name=proto.upper(),
                x=[f"{esc}<br><sub>{ESC_LABELS[esc]}</sub>" for esc in selected_scenarios],
                y=rates,
                marker_color=COLORS[proto],
                width=0.18,
                text=[f"{r:.1f}%" for r in rates],
                textposition="outside",
            ))

        fig.update_layout(
            title="Tasa de éxito por protocolo y escenario",
            xaxis_title="Escenario",
            yaxis_title="Tasa de éxito (%)",
            barmode="group",
            height=500,
            yaxis=dict(range=[0, 110]),
            template="plotly_white",
            hovermode="x unified",
            legend=dict(orientation="h", y=1.12),
        )
        st.plotly_chart(fig, width="stretch")

        st.markdown("#### Analisis por escenario")
        for esc in selected_scenarios:
            vals = [(p, stats.get(p, {}).get(esc, {}).get("success_rate", 0) * 100)
                    for p in selected_protocols]
            vals = [(p, v) for p, v in vals if v >= 0]
            if vals:
                st.markdown(f"**{esc} – {ESC_LABELS[esc]}**:")
                for p, v in vals:
                    tag = "[OK]" if v == 100 else "[!]" if v > 0 else "[X]"
                    st.markdown(f"  - {tag} **{p.upper()}**: {v:.1f}%")

        # Heatmap de éxito
        st.markdown("---")
        st.markdown("#### Mapa de calor: Tasa de exito")
        heat_data = []
        for proto in selected_protocols:
            row = []
            for esc in selected_scenarios:
                s = stats.get(proto, {}).get(esc, {})
                row.append(s.get("success_rate", 0) * 100)
            heat_data.append(row)

        fig_heat = go.Figure(data=go.Heatmap(
            z=heat_data,
            x=[f"{esc}" for esc in selected_scenarios],
            y=[p.upper() for p in selected_protocols],
            colorscale="RdYlGn",
            text=[[f"{v:.1f}%" for v in row] for row in heat_data],
            texttemplate="%{text}",
            textfont={"size": 14},
            hovertemplate="Protocolo: %{y}<br>Escenario: %{x}<br>Éxito: %{text}<extra></extra>",
        ))
        fig_heat.update_layout(
            title="Tasa de éxito (%) - Mapa de calor",
            height=350,
            template="plotly_white",
            xaxis_title="Escenario",
            yaxis_title="Protocolo",
        )
        st.plotly_chart(fig_heat, width="stretch")

    # =====================================================================
    # TAB 4: Compensaciones
    # =====================================================================
    with tab_comp:
        st.subheader("Analisis de Compensaciones")
        st.markdown("""
        Las **compensaciones** son operaciones que *deshacen* los efectos parciales
        de una transacción cuando algo falla. Son el mecanismo de *rollback* distribuido.

        - **2PC**: Rollback global — todas las operaciones se revierten juntas
        - **Saga**: Contratransacción por paso — cada acción tiene su compensación
        - **TCC**: Cancel — se liberan los recursos reservados en la fase *Try*
        - **Raft**: No usa compensaciones — el consenso previene estados inconsistentes
        """)

        col_left, col_right = st.columns([3, 2])

        with col_left:
            fig = go.Figure()
            x = list(range(len(selected_scenarios)))
            for i, proto in enumerate(selected_protocols):
                comps = []
                for esc in selected_scenarios:
                    s = stats.get(proto, {}).get(esc, {})
                    comps.append(s.get("compensations_mean", 0))

                fig.add_trace(go.Bar(
                    name=proto.upper(),
                    x=[f"{esc}<br><sub>{ESC_LABELS[esc]}</sub>" for esc in selected_scenarios],
                    y=comps, marker_color=COLORS[proto], width=0.18,
                    text=[f"{c:.2f}" for c in comps], textposition="outside",
                ))

            fig.update_layout(
                title="Compensaciones promedio por protocolo y escenario",
                xaxis_title="Escenario",
                yaxis_title="Compensaciones promedio",
                barmode="group", height=450,
                template="plotly_white",
                legend=dict(orientation="h", y=1.12),
            )
            st.plotly_chart(fig, width="stretch")

        with col_right:
            st.markdown("#### Promedio global")
            for proto in selected_protocols:
                vals = [stats.get(proto, {}).get(esc, {}).get("compensations_mean", 0)
                        for esc in selected_scenarios]
                avg = statistics.mean(vals) if vals else 0
                st.metric(proto.upper(), f"{avg:.2f}")

        st.markdown("---")
        st.markdown("#### Interpretacion")
        st.info(
            "**Saga** suele tener más compensaciones porque cada paso fallido "
            "dispara una contratransacción específica. **2PC** y **TCC** "
            "compensan todo en bloque. **Raft** evita compensaciones mediante "
            "consenso, pero paga el costo en latencia y mensajería extra."
        )

    # =====================================================================
    # TAB 5: Recuperación
    # =====================================================================
    with tab_recovery:
        st.subheader("Analisis de Recuperacion (Escenario D)")
        st.markdown("""
        El **Escenario D** simula caída de un nodo y su posterior recuperación.
        Mide cuánto tiempo toma al protocolo restablecer el servicio después
        de una falla.

        - **Latencia**: tiempo total incluyendo detección de fallo + recuperación
        - **Tasa de éxito**: si las transacciones se completan tras la recuperación
        - Clave para evaluar **resiliencia** del sistema
        """)

        if "D" in selected_scenarios:
            col_a, col_b, col_c = st.columns(3)
            with col_a:
                d_lats = [(p, stats.get(p, {}).get("D", {}).get("latency_mean", 0))
                          for p in selected_protocols]
                st.metric(
                    "Menor latencia en recuperacion",
                    f"{min(d_lats, key=lambda x: x[1])[0].upper()} "
                    f"({min(d_lats, key=lambda x: x[1])[1]:.1f} ms)",
                )
            with col_b:
                d_success = [(p, stats.get(p, {}).get("D", {}).get("success_rate", 0) * 100)
                             for p in selected_protocols]
                best_s = max(d_success, key=lambda x: x[1])
                st.metric(
                    "Mejor tasa de exito en recuperacion",
                    f"{best_s[0].upper()} ({best_s[1]:.1f}%)",
                )
            with col_c:
                d_comp = [(p, stats.get(p, {}).get("D", {}).get("compensations_mean", 0))
                          for p in selected_protocols]
                st.metric(
                    "Promedio compensaciones en recuperacion",
                    f"{statistics.mean([c for _, c in d_comp]):.2f}",
                )

            fig_rec = go.Figure()
            protos_rec = []
            means_rec = []
            stds_rec = []
            for proto in selected_protocols:
                s = stats.get(proto, {}).get("D", {})
                if s:
                    protos_rec.append(proto.upper())
                    means_rec.append(s.get("latency_mean", 0))
                    stds_rec.append(s.get("latency_std", 0))

            fig_rec.add_trace(go.Bar(
                x=protos_rec, y=means_rec,
                error_y=dict(type="data", array=stds_rec, visible=True),
                marker_color=[COLORS[p] for p in selected_protocols if p.upper() in protos_rec],
                text=[f"{m:.1f}" for m in means_rec],
                textposition="outside",
                width=0.5,
            ))
            fig_rec.update_layout(
                title="Tiempo de recuperación por protocolo (Escenario D)",
                xaxis_title="Protocolo",
                yaxis_title="Latencia de recuperación (ms)",
                height=450, template="plotly_white",
            )
            st.plotly_chart(fig_rec, width="stretch")
        else:
            st.warning("Seleccione el Escenario D en la barra lateral para ver este análisis.")

    # =====================================================================
    # TAB 6: Datos Crudos
    # =====================================================================
    with tab_raw:
        st.subheader("Datos crudos del experimento")
        st.markdown("""
        A continuación se muestran las filas completas de los CSVs cargados,
        filtradas según la selección de la barra lateral.
        """)
        st.dataframe(df_filtered, width="stretch", hide_index=True)

        csv_download = df_filtered.to_csv(index=False).encode("utf-8")
        st.download_button(
            label="Descargar CSV filtrado",
            data=csv_download,
            file_name="experiment_results_filtered.csv",
            mime="text/csv",
        )


# ===========================================================================
# Entry point extendido
# ===========================================================================

if __name__ == "__main__":
    # Auto-detectar ejecucion via `streamlit run` (streamlit ya esta en sys.modules)
    _in_streamlit = "streamlit" in sys.modules
    if _in_streamlit or any(arg in sys.argv for arg in ("--dashboard", "-d")):
        run_dashboard()
        sys.exit(0)

    # Modo CLI normal
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

    print("\n✓ Analisis completado")
    print("💡 Dashboard interactivo: streamlit run analyze_results.py")
