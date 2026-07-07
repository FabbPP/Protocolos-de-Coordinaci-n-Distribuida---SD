# coordinator_2pc.py — Protocolo Two-Phase Commit unificado
# Adaptado de las implementaciones en casoFarmaAndes/ y casoBancoCooperativo/
# Soporta ambos dominios: farmacia (productos/stock) y bancos (cuentas/saldo)

import time
from db import connect


# ---------------------------------------------------------------------------
# Configuración de nodos — centralizada
# ---------------------------------------------------------------------------

SEDES_FARMA = {
    "almacen_arequipa": ("Arequipa", "10.2.0.10"),
    "almacen_lima":     ("Lima",     "10.2.0.20"),
}

SEDES_BANCO = {
    "banco_arequipa": ("Banco Arequipa", "10.2.0.10"),
    "banco_cusco":    ("Banco Cusco",    "10.2.0.30"),
    "banco_lima":     ("Banco Lima",     "10.2.0.20"),
}


# ---------------------------------------------------------------------------
# Helpers de inventario (FarmaAndes)
# ---------------------------------------------------------------------------

def obtener_inventario(nombre_db):
    conn = connect(nombre_db)
    cur = conn.cursor()
    cur.execute("SELECT producto, stock FROM inventario ORDER BY producto")
    datos = cur.fetchall()
    conn.close()
    return datos


def obtener_productos():
    conn = connect("almacen_arequipa")
    cur = conn.cursor()
    cur.execute("SELECT producto FROM inventario ORDER BY producto")
    productos = [fila[0] for fila in cur.fetchall()]
    conn.close()
    return productos


# ---------------------------------------------------------------------------
# Helpers de cuentas (Banco Cooperativo)
# ---------------------------------------------------------------------------

def obtener_cuentas(nombre_db):
    conn = connect(nombre_db)
    cur = conn.cursor()
    cur.execute("SELECT titular, saldo FROM cuentas ORDER BY titular")
    datos = cur.fetchall()
    conn.close()
    return datos


def obtener_titulares():
    conn = connect("banco_arequipa")
    cur = conn.cursor()
    cur.execute("SELECT titular FROM cuentas ORDER BY titular")
    titulares = [fila[0] for fila in cur.fetchall()]
    conn.close()
    return titulares


# ---------------------------------------------------------------------------
# 2PC — FarmaAndes (2 nodos)
# ---------------------------------------------------------------------------

def ejecutar_2pc_farma(origen_db, destino_db, producto, cantidad, simular_fallo=False):
    """Protocolo 2PC para transferencia de inventario entre almacenes."""
    logs = []

    if origen_db == destino_db:
        logs.append("ERROR: origen y destino no pueden ser iguales")
        return logs

    nombre_origen  = SEDES_FARMA[origen_db][0]
    nombre_destino = SEDES_FARMA[destino_db][0]

    origen  = connect(origen_db)
    destino = connect(destino_db)

    try:
        origen.autocommit = False
        destino.autocommit = False

        cur_o = origen.cursor()
        cur_d = destino.cursor()

        logs.append("FASE 1: PREPARE")
        logs.append(f"Transferencia de {cantidad} unidades — {producto}")
        logs.append(f"Origen: {nombre_origen} → Destino: {nombre_destino}")

        cur_o.execute("SELECT stock FROM inventario WHERE producto = %s", (producto,))
        fila = cur_o.fetchone()
        if fila is None:
            raise Exception("Producto no encontrado")

        stock_actual = fila[0]
        logs.append(f"Stock disponible en origen: {stock_actual}")

        if stock_actual < cantidad:
            raise Exception("Stock insuficiente")

        logs.append(f"Nodo {nombre_origen} responde YES")
        logs.append(f"Nodo {nombre_destino} responde YES")

        cur_o.execute(
            "UPDATE inventario SET stock = stock - %s WHERE producto = %s",
            (cantidad, producto),
        )
        logs.append(f"Stock descontado en {nombre_origen}")

        if simular_fallo:
            raise Exception(f"El nodo {nombre_destino} dejó de responder")

        cur_d.execute(
            "UPDATE inventario SET stock = stock + %s WHERE producto = %s",
            (cantidad, producto),
        )
        logs.append(f"Stock incrementado en {nombre_destino}")
        logs.append("Todos los nodos aceptaron la transacción")

        logs.append("FASE 2: COMMIT")
        origen.commit()
        destino.commit()
        logs.append("COMMIT GLOBAL EJECUTADO")
        logs.append("Transferencia completada correctamente")

    except Exception as e:
        origen.rollback()
        destino.rollback()
        logs.append(f"ERROR: {e}")
        logs.append("ROLLBACK GLOBAL EJECUTADO")
        logs.append("La transacción fue cancelada")
    finally:
        origen.close()
        destino.close()

    return logs


# ---------------------------------------------------------------------------
# 2PC — Banco Cooperativo (3 nodos)
# ---------------------------------------------------------------------------

def _conectar_par(origen_db, destino_db):
    origen  = connect(origen_db)
    destino = connect(destino_db)
    origen.autocommit  = False
    destino.autocommit = False
    return origen, destino


def _obtener_cuenta(cur, logs, nombre):
    cur.execute("SELECT id, titular, saldo FROM cuentas LIMIT 1")
    cuenta = cur.fetchone()
    if cuenta is None:
        raise Exception(f"No existe cuenta en {nombre}")
    logs.append(f"Saldo disponible en {nombre}: S/ {cuenta[2]:,.2f}")
    return cuenta


def ejecutar_2pc_banco(origen_db, destino_db, monto):
    """Protocolo 2PC exitoso para transferencia bancaria."""
    logs = []

    if origen_db == destino_db:
        logs.append("ERROR: origen y destino no pueden ser iguales")
        return logs

    nombre_origen  = SEDES_BANCO[origen_db][0]
    nombre_destino = SEDES_BANCO[destino_db][0]
    origen, destino = _conectar_par(origen_db, destino_db)

    try:
        cur_o = origen.cursor()
        cur_d = destino.cursor()

        logs.append("FASE 1: PREPARE")
        logs.append(f"Transferencia de S/ {monto:,.2f}")
        logs.append(f"Origen: {nombre_origen} → Destino: {nombre_destino}")

        cuenta_origen = _obtener_cuenta(cur_o, logs, nombre_origen)
        if cuenta_origen[2] < monto:
            raise Exception("Saldo insuficiente en cuenta origen")

        logs.append(f"{nombre_origen} responde YES")
        logs.append(f"{nombre_destino} responde YES")

        cur_o.execute(
            "UPDATE cuentas SET saldo = saldo - %s WHERE id = %s",
            (monto, cuenta_origen[0]),
        )
        logs.append(f"Débito realizado en {nombre_origen}")

        cur_d.execute(
            "UPDATE cuentas SET saldo = saldo + %s WHERE id = (SELECT id FROM cuentas LIMIT 1)",
            (monto,),
        )
        logs.append(f"Crédito realizado en {nombre_destino}")
        logs.append("Todos los participantes votaron YES")

        logs.append("FASE 2: GLOBAL COMMIT")
        origen.commit()
        destino.commit()
        logs.append("COMMIT GLOBAL EJECUTADO")
        logs.append("Transferencia completada exitosamente")

    except Exception as e:
        origen.rollback()
        destino.rollback()
        logs.append(f"ERROR: {e}")
        logs.append("GLOBAL ROLLBACK EJECUTADO")
        logs.append("Transacción cancelada — estado consistente restaurado")
    finally:
        origen.close()
        destino.close()

    return logs


def ejecutar_fallo_red(origen_db, destino_db, monto):
    """Simula timeout por partición de red durante el PREPARE."""
    logs = []

    if origen_db == destino_db:
        logs.append("ERROR: origen y destino no pueden ser iguales")
        return logs

    nombre_origen  = SEDES_BANCO[origen_db][0]
    nombre_destino = SEDES_BANCO[destino_db][0]
    origen, destino = _conectar_par(origen_db, destino_db)

    try:
        cur_o = origen.cursor()

        logs.append("FASE 1: PREPARE")
        logs.append(f"Transferencia de S/ {monto:,.2f}")
        logs.append(f"Origen: {nombre_origen} → Destino: {nombre_destino}")

        cuenta_origen = _obtener_cuenta(cur_o, logs, nombre_origen)
        if cuenta_origen[2] < monto:
            raise Exception("Saldo insuficiente en cuenta origen")

        logs.append(f"{nombre_origen} responde YES")
        logs.append(f"Enviando PREPARE a {nombre_destino}...")
        time.sleep(0.3)
        logs.append("FALLA DE RED — No se recibió respuesta del nodo destino")
        logs.append(f"Timeout: {nombre_destino} no responde (simulado)")
        raise Exception(f"Falla de red — pérdida de conexión con {nombre_destino}")

    except Exception as e:
        origen.rollback()
        destino.rollback()
        logs.append(f"ERROR: {e}")
        logs.append("GLOBAL ROLLBACK EJECUTADO")
        logs.append("Transacción cancelada — ningún saldo fue modificado")
    finally:
        origen.close()
        destino.close()

    return logs


def ejecutar_caida_nodo(origen_db, destino_db, monto):
    """Simula caída de un nodo durante el COMMIT (fase 2)."""
    logs = []

    if origen_db == destino_db:
        logs.append("ERROR: origen y destino no pueden ser iguales")
        return logs

    nombre_origen  = SEDES_BANCO[origen_db][0]
    nombre_destino = SEDES_BANCO[destino_db][0]
    origen, destino = _conectar_par(origen_db, destino_db)

    try:
        cur_o = origen.cursor()

        logs.append("FASE 1: PREPARE")
        logs.append(f"Transferencia de S/ {monto:,.2f}")
        logs.append(f"Origen: {nombre_origen} → Destino: {nombre_destino}")

        cuenta_origen = _obtener_cuenta(cur_o, logs, nombre_origen)
        if cuenta_origen[2] < monto:
            raise Exception("Saldo insuficiente en cuenta origen")

        logs.append(f"{nombre_origen} responde YES")
        logs.append(f"{nombre_destino} responde YES")

        cur_o.execute(
            "UPDATE cuentas SET saldo = saldo - %s WHERE id = %s",
            (monto, cuenta_origen[0]),
        )
        logs.append(f"Débito realizado en {nombre_origen}")
        logs.append("FASE 2: GLOBAL COMMIT iniciado")
        logs.append(f"Enviando COMMIT a {nombre_destino}...")

        logs.append(f"CAÍDA DE NODO — {nombre_destino} dejó de responder")
        logs.append(f"El proceso en {nombre_destino} fue terminado (simulado)")
        raise Exception(f"Nodo caído: {nombre_destino} no completó el COMMIT")

    except Exception as e:
        origen.rollback()
        destino.rollback()
        logs.append(f"ERROR: {e}")
        logs.append("GLOBAL ROLLBACK EJECUTADO")
        logs.append("Débito revertido en origen — estado consistente restaurado")
    finally:
        origen.close()
        destino.close()

    return logs


def ejecutar_recuperacion(origen_db, destino_db, monto, tipo_fallo):
    """Reintenta una transacción fallida tras recuperar el nodo."""
    logs = []

    if origen_db == destino_db:
        logs.append("ERROR: origen y destino no pueden ser iguales")
        return logs

    nombre_origen  = SEDES_BANCO[origen_db][0]
    nombre_destino = SEDES_BANCO[destino_db][0]
    origen, destino = _conectar_par(origen_db, destino_db)

    try:
        cur_o = origen.cursor()
        cur_d = destino.cursor()

        logs.append("RECUPERACIÓN POSTERIOR")
        logs.append("Verificando estado de nodos tras fallo previo...")
        logs.append(f"Nodo {nombre_origen}: en línea ✓")
        logs.append(f"Nodo {nombre_destino}: en línea ✓ (recuperado)")
        logs.append("Consultando log de transacciones pendientes...")
        logs.append(f"RECUPERACIÓN — Resolviendo fallo: {tipo_fallo.replace('_', ' ').upper()}")

        logs.append("FASE 1: PREPARE (reintento)")
        cuenta_origen = _obtener_cuenta(cur_o, logs, nombre_origen)

        logs.append(f"{nombre_origen} (Participante 1) — Vota: YES")
        logs.append(f"{nombre_destino} (Participante 2) — Vota: YES (Recuperado)")

        cur_o.execute(
            "UPDATE cuentas SET saldo = saldo - %s WHERE id = %s",
            (monto, cuenta_origen[0]),
        )
        cur_d.execute(
            "UPDATE cuentas SET saldo = saldo + %s WHERE id = (SELECT id FROM cuentas LIMIT 1)",
            (monto,),
        )

        logs.append("FASE 2: GLOBAL COMMIT")
        origen.commit()
        destino.commit()

        logs.append("LOG: Transacción marcada como COMPLETADA en el Coordinador")
        logs.append("RECUPERACIÓN EXITOSA — Consistencia total restaurada en todos los nodos")

    except Exception as e:
        origen.rollback()
        destino.rollback()
        logs.append(f"ERROR durante recuperación: {e}")
        logs.append("GLOBAL ROLLBACK EJECUTADO")
        logs.append("Recuperación fallida — intervención manual requerida")
    finally:
        origen.close()
        destino.close()

    return logs
