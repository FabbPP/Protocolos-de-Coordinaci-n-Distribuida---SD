# tcc_orchestrator.py — Try-Confirm/Cancel para transferencias distribuidas
# Fase TRY:   reserva fondos en ambos nodos (no se debita aún)
# Fase CONFIRM: confirma débito y crédito
# Fase CANCEL: libera reservas si TRY falla o hay timeout

import time
from db import connect

SEDES_BANCO = {
    "banco_arequipa": "Banco Arequipa",
    "banco_cusco":    "Banco Cusco",
    "banco_lima":     "Banco Lima",
}


def _ensure_reservas_table(conn, dbname):
    """Crea la tabla de reservas si no existe (idempotente)."""
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS reservas (
            id_tx     TEXT PRIMARY KEY,
            cuenta_id INTEGER NOT NULL,
            monto     NUMERIC(12,2) NOT NULL,
            tipo      TEXT NOT NULL CHECK (tipo IN ('debito', 'credito')),
            estado    TEXT NOT NULL DEFAULT 'try' CHECK (estado IN ('try', 'confirmed', 'cancelled')),
            created_at TIMESTAMP DEFAULT NOW()
        )
    """)
    conn.commit()


def _try_reserve(conn, cuenta_id, monto, tipo, tx_id, logs, nombre):
    """Fase TRY: crea una reserva. Débito verifica saldo suficiente."""
    cur = conn.cursor()
    conn.autocommit = False

    if tipo == "debito":
        cur.execute("SELECT saldo FROM cuentas WHERE id = %s", (cuenta_id,))
        fila = cur.fetchone()
        if fila is None:
            conn.rollback()
            raise Exception(f"Cuenta no encontrada en {nombre}")
        if fila[0] < monto:
            conn.rollback()
            raise Exception(f"Saldo insuficiente en {nombre}: S/ {fila[0]:,.2f} < S/ {monto:,.2f}")

    cur.execute(
        "INSERT INTO reservas (id_tx, cuenta_id, monto, tipo, estado) VALUES (%s, %s, %s, %s, 'try')",
        (tx_id, cuenta_id, monto, tipo),
    )
    conn.commit()
    logs.append(f"TCC TRY ✓: Reserva {tipo} por S/ {monto:,.2f} en {nombre} (tx={tx_id[:8]}...)")


def _confirm_one(conn, cuenta_id, monto, tipo, tx_id, logs, nombre):
    """Fase CONFIRM: aplica la reserva (UPDATE real) y marca confirmed."""
    cur = conn.cursor()
    conn.autocommit = False

    cur.execute(
        "SELECT estado FROM reservas WHERE id_tx = %s AND cuenta_id = %s AND tipo = %s FOR UPDATE",
        (tx_id, cuenta_id, tipo),
    )
    reserva = cur.fetchone()
    if reserva is None or reserva[0] != "try":
        conn.rollback()
        raise Exception(f"Reserva no encontrada o ya procesada en {nombre}")

    signo = "-" if tipo == "debito" else "+"
    cur.execute(
        f"UPDATE cuentas SET saldo = saldo {'-' if tipo == 'debito' else '+'} %s WHERE id = %s",
        (monto, cuenta_id),
    )
    cur.execute(
        "UPDATE reservas SET estado = 'confirmed' WHERE id_tx = %s AND tipo = %s",
        (tx_id, tipo),
    )
    conn.commit()
    logs.append(f"TCC CONFIRM ✓: {tipo.capitalize()} confirmado en {nombre} ({signo}S/ {monto:,.2f})")


def _cancel_one(conn, cuenta_id, monto, tipo, tx_id, logs, nombre):
    """Fase CANCEL: libera la reserva sin modificar saldo."""
    cur = conn.cursor()
    conn.autocommit = False
    cur.execute(
        "UPDATE reservas SET estado = 'cancelled' WHERE id_tx = %s AND tipo = %s",
        (tx_id, tipo),
    )
    conn.commit()
    logs.append(f"TCC CANCEL → Reserva {tipo} liberada en {nombre} (tx={tx_id[:8]}...)")


def tcc_transfer(origen_db, destino_db, monto, simular_fallo=False):
    """Ejecuta transferencia con TCC: TRY → CONFIRM (o CANCEL si falla).

    Returns:
        (logs, estado) donde estado es 'committed' o 'cancelled'
    """
    logs = []
    tx_id = f"tcc_{time.time_ns()}"

    if origen_db == destino_db:
        logs.append("ERROR: origen y destino no pueden ser iguales")
        return logs, "cancelled"

    nombre_origen  = SEDES_BANCO[origen_db]
    nombre_destino = SEDES_BANCO[destino_db]

    logs.append("TCC: Iniciando transacción Try-Confirm/Cancel")
    logs.append(f"Transferencia de S/ {monto:,.2f}")
    logs.append(f"Origen: {nombre_origen} → Destino: {nombre_destino}")
    logs.append(f"ID transacción: {tx_id[:16]}...")

    # Obtener IDs de cuenta
    conn_o = connect(origen_db)
    conn_d = connect(destino_db)
    _ensure_reservas_table(conn_o, origen_db)
    _ensure_reservas_table(conn_d, destino_db)
    conn_o.close()
    conn_d.close()

    cuenta_origen_id = None
    cuenta_destino_id = None

    # ── TRY ──
    logs.append("TCC Fase TRY: Creando reservas...")
    try:
        # Try débito (origen)
        conn_o = connect(origen_db)
        cur_o = conn_o.cursor()
        cur_o.execute("SELECT id FROM cuentas LIMIT 1")
        cuenta = cur_o.fetchone()
        conn_o.close()
        cuenta_origen_id = cuenta[0]

        conn_o2 = connect(origen_db)
        _try_reserve(conn_o2, cuenta_origen_id, monto, "debito", tx_id, logs, nombre_origen)
        conn_o2.close()

        # Try crédito (destino)
        conn_d2 = connect(destino_db)
        cur_d = conn_d2.cursor()
        cur_d.execute("SELECT id FROM cuentas LIMIT 1")
        cuenta_d = cur_d.fetchone()
        conn_d2.close()
        cuenta_destino_id = cuenta_d[0]

        conn_d3 = connect(destino_db)
        _try_reserve(conn_d3, cuenta_destino_id, monto, "credito", tx_id, logs, nombre_destino)
        conn_d3.close()

        if simular_fallo:
            raise Exception("Fallo de red durante TRY — destino no confirmó reserva")

        logs.append("TCC TRY ✓: Todas las reservas creadas exitosamente")

    except Exception as e:
        logs.append(f"TCC TRY FALLÓ: {e}")
        logs.append("TCC: Ejecutando CANCEL para liberar reservas...")

        # Cancelar ambas reservas (las que existan)
        for db_name, cuenta_id, tipo in [
            (origen_db, cuenta_origen_id, "debito"),
            (destino_db, cuenta_destino_id, "credito"),
        ]:
            if cuenta_id is None:
                continue
            try:
                conn = connect(db_name)
                _cancel_one(conn, cuenta_id, monto, tipo, tx_id, logs, SEDES_BANCO[db_name])
                conn.close()
            except Exception as ce:
                logs.append(f"TCC CANCEL error en {db_name}: {ce}")

        logs.append("TCC: Transacción cancelada — fondos no afectados")
        return logs, "cancelled"

    # ── CONFIRM ──
    logs.append("TCC Fase CONFIRM: Aplicando cambios...")
    try:
        conn_oc = connect(origen_db)
        _confirm_one(conn_oc, cuenta_origen_id, monto, "debito", tx_id, logs, nombre_origen)
        conn_oc.close()

        conn_dc = connect(destino_db)
        _confirm_one(conn_dc, cuenta_destino_id, monto, "credito", tx_id, logs, nombre_destino)
        conn_dc.close()

        logs.append("TCC CONFIRM ✓: Transacción completada exitosamente")
        return logs, "committed"

    except Exception as e:
        logs.append(f"TCC CONFIRM FALLÓ: {e}")
        logs.append("TCC: Datos inconsistentes — se requiere intervención manual o retry")
        return logs, "cancelled"


def tcc_transfer_fallo_red(origen_db, destino_db, monto):
    """Simula fallo de red: TRY falla → CANCEL."""
    return tcc_transfer(origen_db, destino_db, monto, simular_fallo=True)


def tcc_transfer_caida_nodo(origen_db, destino_db, monto):
    """Simula caída de nodo: igual comportamiento desde el coordinador."""
    return tcc_transfer(origen_db, destino_db, monto, simular_fallo=True)


def tcc_recuperacion(origen_db, destino_db, monto):
    """Reintenta TCC sin fallo tras recuperación."""
    return tcc_transfer(origen_db, destino_db, monto, simular_fallo=False)
