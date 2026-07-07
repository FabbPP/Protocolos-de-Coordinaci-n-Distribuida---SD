# saga_orchestrator.py — Saga orquestada para transferencias distribuidas
# Cada paso es una transacción local. Si un paso falla, se ejecutan
# compensaciones en orden inverso para deshacer los pasos anteriores.

import time
from db import connect

SEDES_BANCO = {
    "banco_arequipa": "Banco Arequipa",
    "banco_cusco":    "Banco Cusco",
    "banco_lima":     "Banco Lima",
}


def saga_transfer(origen_db, destino_db, monto, simular_fallo=False, paso_fallo=2):
    """Orquesta una saga de 2 pasos con compensaciones.

    Paso 1: Débito en origen. Compensación → crédito en origen.
    Paso 2: Crédito en destino. Compensación → débito en destino.

    Args:
        origen_db: base de datos del nodo origen
        destino_db: base de datos del nodo destino
        monto: cantidad a transferir
        simular_fallo: si True, inyecta fallo en el paso indicado
        paso_fallo: 1 = fallo en débito, 2 = fallo en crédito
    """
    logs = []
    compensaciones_aplicadas = []

    if origen_db == destino_db:
        logs.append("ERROR: origen y destino no pueden ser iguales")
        return logs, 0

    nombre_origen  = SEDES_BANCO[origen_db]
    nombre_destino = SEDES_BANCO[destino_db]

    logs.append("SAGA: Iniciando saga de transferencia")
    logs.append(f"Transferencia de S/ {monto:,.2f}")
    logs.append(f"Origen: {nombre_origen} → Destino: {nombre_destino}")

    # ── Paso 1: Débito en origen ──
    t0 = time.time()
    try:
        conn_o = connect(origen_db)
        cur_o = conn_o.cursor()
        conn_o.autocommit = False

        cur_o.execute("SELECT id, titular, saldo FROM cuentas LIMIT 1")
        cuenta = cur_o.fetchone()
        if cuenta is None or cuenta[2] < monto:
            conn_o.rollback()
            conn_o.close()
            logs.append(f"SAGA ABORT: Saldo insuficiente en {nombre_origen}")
            return logs, 0

        logs.append(f"SAGA Paso 1/2: Débito {nombre_origen} (-S/ {monto:,.2f})")

        if simular_fallo and paso_fallo == 1:
            conn_o.rollback()
            conn_o.close()
            logs.append(f"SAGA FALLO inyectado en Paso 1: {nombre_origen} no pudo debitar")
            logs.append("SAGA: No hay pasos que compensar (fallo en paso 1)")
            return logs, 0

        cur_o.execute(
            "UPDATE cuentas SET saldo = saldo - %s WHERE id = %s",
            (monto, cuenta[0]),
        )
        conn_o.commit()
        conn_o.close()
        logs.append(f"SAGA Paso 1/2 ✓: Débito completado en {nombre_origen}")

    except Exception as e:
        logs.append(f"SAGA ERROR Paso 1: {e}")
        return logs, 0

    # ── Paso 2: Crédito en destino ──
    try:
        conn_d = connect(destino_db)
        cur_d = conn_d.cursor()
        conn_d.autocommit = False

        logs.append(f"SAGA Paso 2/2: Crédito {nombre_destino} (+S/ {monto:,.2f})")

        if simular_fallo and paso_fallo == 2:
            conn_d.rollback()
            conn_d.close()
            raise Exception(f"Fallo inyectado: {nombre_destino} no pudo acreditar")

        cur_d.execute(
            "UPDATE cuentas SET saldo = saldo + %s WHERE id = (SELECT id FROM cuentas LIMIT 1)",
            (monto,),
        )
        conn_d.commit()
        conn_d.close()
        logs.append(f"SAGA Paso 2/2 ✓: Crédito completado en {nombre_destino}")

    except Exception as e:
        logs.append(f"SAGA ERROR Paso 2: {e}")
        logs.append("SAGA: Iniciando compensaciones en orden inverso...")

        # ── Compensación Paso 1: Crédito (revertir débito en origen) ──
        try:
            conn_comp = connect(origen_db)
            cur_comp = conn_comp.cursor()
            conn_comp.autocommit = False

            cur_comp.execute("SELECT id FROM cuentas LIMIT 1")
            cuenta_comp = cur_comp.fetchone()

            cur_comp.execute(
                "UPDATE cuentas SET saldo = saldo + %s WHERE id = %s",
                (monto, cuenta_comp[0]),
            )
            conn_comp.commit()
            conn_comp.close()

            compensaciones_aplicadas.append(f"Compensación 1: Crédito revertido en {nombre_origen} (+S/ {monto:,.2f})")
            logs.append(f"SAGA COMPENSACIÓN ✓: Débito revertido en {nombre_origen}")
        except Exception as comp_e:
            logs.append(f"SAGA COMPENSACIÓN FALLÓ en {nombre_origen}: {comp_e}")

        logs.append(f"SAGA: {len(compensaciones_aplicadas)} compensación(es) aplicada(s)")
        return logs, len(compensaciones_aplicadas)

    elapsed_ms = round((time.time() - t0) * 1000, 2)
    logs.append(f"SAGA COMPLETA: Transferencia exitosa sin fallos")
    return logs, 0


def saga_transfer_fallo_red(origen_db, destino_db, monto):
    """Simula fallo de red: el destino nunca responde → compensación."""
    logs, ncomp = saga_transfer(
        origen_db, destino_db, monto,
        simular_fallo=True, paso_fallo=2,
    )
    return logs, ncomp


def saga_transfer_caida_nodo(origen_db, destino_db, monto):
    """Simula caída del nodo destino → igual que fallo de red desde el coordinador."""
    logs, ncomp = saga_transfer(
        origen_db, destino_db, monto,
        simular_fallo=True, paso_fallo=2,
    )
    return logs, ncomp


def saga_recuperacion(origen_db, destino_db, monto):
    """Reintenta la saga completa tras un fallo (ambos nodos responden)."""
    logs, ncomp = saga_transfer(
        origen_db, destino_db, monto,
        simular_fallo=False, paso_fallo=0,
    )
    return logs, ncomp
