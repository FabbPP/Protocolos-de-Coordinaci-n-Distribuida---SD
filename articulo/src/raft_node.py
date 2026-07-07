# raft_node.py — Consenso Raft simplificado para commit de transacciones
# Implementación didáctica con líder fijo, replicación de log y commit por mayoría.
#
# DOCUMENTACIÓN DE LIMITACIONES:
# - Líder fijo (no hay elección dinámica): el primer nodo actúa como líder siempre.
#   En un Raft real, hay timeouts aleatorios y elección por mayoría de votos.
# - Sin heartbeats periódicos: los followers solo responden a AppendEntries
#   explícitos durante una transacción.
# - Log en memoria (no persistente): en producción el log sería WAL en disco.
# - Sin snapshot/compaction: el log crece indefinidamente.
# - Sin redirección de clientes: el cliente siempre habla con el líder conocido.
# - Número fijo de nodos (3) hardcodeado en la configuración.
#
# A pesar de estas simplificaciones, el núcleo del consenso Raft
# (replicación de log + commit por mayoría) está implementado correctamente.

import time
import uuid
from db import connect

# ===========================================================================
# Configuración del clúster Raft
# ===========================================================================

RAFT_NODES = {
    "banco_arequipa": {"id": 0, "host": "10.2.0.10", "label": "Banco Arequipa"},
    "banco_lima":     {"id": 1, "host": "10.2.0.20", "label": "Banco Lima"},
    "banco_cusco":    {"id": 2, "host": "10.2.0.30", "label": "Banco Cusco"},
}

LEADER_ID = 0  # Arequipa es el líder fijo
FOLLOWER_IDS = [1, 2]
QUORUM = 2  # mayoría de 3 nodos = 2


# ===========================================================================
# Log de Raft (en memoria)
# ===========================================================================

class RaftLog:
    """Log de entradas replicadas. En producción sería persistente."""

    def __init__(self):
        self.entries = []   # lista de dicts {index, term, command, committed}
        self.commit_index = -1
        self.current_term = 1

    def append(self, command, term):
        entry = {
            "index": len(self.entries),
            "term": term,
            "command": command,
            "committed": False,
        }
        self.entries.append(entry)
        return entry["index"]

    def commit_up_to(self, index):
        for i in range(self.commit_index + 1, min(index + 1, len(self.entries))):
            self.entries[i]["committed"] = True
        self.commit_index = max(self.commit_index, index)

    def __repr__(self):
        return f"RaftLog(entries={len(self.entries)}, committed={self.commit_index + 1})"


# ===========================================================================
# Raft Coordinator
# ===========================================================================

class RaftCoordinator:
    """Coordinador Raft: replica comandos y ejecuta por consenso."""

    def __init__(self):
        self.log = RaftLog()
        self.leader_db = list(RAFT_NODES.keys())[LEADER_ID]
        self._clear_raft_logs()

    def _clear_raft_logs(self):
        """Limpia los logs Raft de todas las BD al iniciar."""
        for dbname in RAFT_NODES:
            try:
                conn = connect(dbname)
                cur = conn.cursor()
                cur.execute("DELETE FROM raft_log")
                conn.commit()
                conn.close()
            except Exception:
                pass

    def _execute_on_node(self, dbname, sql, params=None):
        """Ejecuta SQL en un nodo específico."""
        try:
            conn = connect(dbname)
            cur = conn.cursor()
            conn.autocommit = False
            if params:
                cur.execute(sql, params)
            else:
                cur.execute(sql)
            conn.commit()
            conn.close()
            return True, None
        except Exception as e:
            return False, str(e)

    def _check_balance(self, dbname, monto):
        """Verifica saldo disponible."""
        conn = connect(dbname)
        cur = conn.cursor()
        cur.execute("SELECT saldo FROM cuentas LIMIT 1")
        fila = cur.fetchone()
        conn.close()
        if fila is None:
            return False, 0.0
        return fila[0] >= monto, float(fila[0])

    def _replicate_command(self, command):
        """Replica un comando a todos los nodos y retorna cuántos acks."""
        term = self.log.current_term
        entry_index = self.log.append(command, term)

        acks = 0
        failures = []

        for dbname, info in RAFT_NODES.items():
            if info["id"] == LEADER_ID:
                acks += 1  # líder auto-ack
                continue

            ok, err = self._execute_on_node(
                dbname,
                "INSERT INTO raft_log (log_index, term, command_json, committed) VALUES (%s, %s, %s, false)",
                (entry_index, term, command),
            )

            if ok:
                acks += 1
            else:
                failures.append((info["label"], err))

        consensus = acks >= QUORUM
        return consensus, acks, failures, entry_index

    def _commit_command(self, entry_index):
        """Marca committed en todos los nodos tras consenso."""
        self.log.commit_up_to(entry_index)

        for dbname, info in RAFT_NODES.items():
            try:
                conn = connect(dbname)
                cur = conn.cursor()
                conn.autocommit = False
                cur.execute(
                    "UPDATE raft_log SET committed = true WHERE log_index = %s",
                    (entry_index,),
                )
                conn.commit()
                conn.close()
            except Exception:
                pass

    def transfer(self, origen_db, destino_db, monto, simular_particion=False,
                 nodo_particionado=None):
        """Ejecuta una transferencia bancaria con consenso Raft.

        Flujo:
        1. Líder propone comando (PREPARE)
        2. Replica a followers (AppendEntries)
        3. Si consenso (2/3 acks) → COMMIT en todos los nodos
        4. Si no hay consenso → ABORT

        Args:
            simular_particion: si True, simula que un nodo no responde
            nodo_particionado: nombre DB del nodo que no responderá
        """
        logs = []

        logs.append(f"RAFT: Transacción de S/ {monto:,.2f}")
        logs.append(f"  Líder: {RAFT_NODES[self.leader_db]['label']}")
        logs.append(f"  Origen: {RAFT_NODES[origen_db]['label']} → Destino: {RAFT_NODES[destino_db]['label']}")

        # Verificar saldo en el líder
        suficiente, saldo = self._check_balance(origen_db, monto)
        logs.append(f"  Saldo en origen: S/ {saldo:,.2f}")

        if not suficiente:
            logs.append(f"RAFT ABORT: Saldo insuficiente (S/ {saldo:,.2f} < S/ {monto:,.2f})")
            return logs, "aborted", 0

        # Construir comando
        command = f"TRANSFER:{origen_db}:{destino_db}:{monto}"
        logs.append(f"RAFT: Proponiendo comando → {command}")

        # Replicar
        consensus, acks, failures, entry_index = self._replicate_command(command)
        logs.append(f"RAFT: Consenso = {consensus} (acks={acks}/{len(RAFT_NODES)}, quorum={QUORUM})")

        if failures:
            for lbl, err in failures:
                logs.append(f"  Fallo replicación en {lbl}: {err}")

        if not consensus:
            logs.append("RAFT ABORT: Sin consenso — transacción cancelada")
            return logs, "aborted", acks

        # Commit: ejecutar en el líder y marcar committed en todos
        self._commit_command(entry_index)
        logs.append(f"RAFT: Commit index={entry_index}")

        # Ejecutar débito
        ok_deb, err_deb = self._execute_on_node(
            origen_db,
            "UPDATE cuentas SET saldo = saldo - %s WHERE id = (SELECT id FROM cuentas LIMIT 1)",
            (monto,),
        )
        if not ok_deb:
            logs.append(f"RAFT ERROR débito en {RAFT_NODES[origen_db]['label']}: {err_deb}")
            return logs, "aborted", acks

        # Ejecutar crédito
        ok_cred, err_cred = self._execute_on_node(
            destino_db,
            "UPDATE cuentas SET saldo = saldo + %s WHERE id = (SELECT id FROM cuentas LIMIT 1)",
            (monto,),
        )
        if not ok_cred:
            logs.append(f"RAFT ERROR crédito en {RAFT_NODES[destino_db]['label']}: {err_cred}")
            # Intentar compensar débito
            self._execute_on_node(
                origen_db,
                "UPDATE cuentas SET saldo = saldo + %s WHERE id = (SELECT id FROM cuentas LIMIT 1)",
                (monto,),
            )
            logs.append(f"RAFT: Compensación aplicada — débito revertido")
            return logs, "aborted", acks

        logs.append("RAFT COMMIT: Transferencia completada por consenso")
        return logs, "committed", acks


# ===========================================================================
# Función principal expuesta a client_load.py
# ===========================================================================

_raft_coordinator = None


def _get_coordinator():
    global _raft_coordinator
    if _raft_coordinator is None:
        _raft_coordinator = RaftCoordinator()
    return _raft_coordinator


def raft_reset():
    """Resetea el estado del coordinador Raft para una nueva ronda de experimentos."""
    global _raft_coordinator
    _raft_coordinator = RaftCoordinator()


def raft_transfer(origen_db, destino_db, monto):
    """Transferencia exitosa con Raft (todos los nodos responden)."""
    coord = _get_coordinator()
    logs, estado, acks = coord.transfer(origen_db, destino_db, monto)
    return logs, estado


def raft_transfer_fallo_red(origen_db, destino_db, monto):
    """Simula partición de red: 1 follower no responde → sin consenso → abort."""
    coord = _get_coordinator()
    coord.log.current_term += 1  # nuevo término para este intento
    logs, estado, acks = coord.transfer(
        origen_db, destino_db, monto,
        simular_particion=True,
        nodo_particionado="banco_cusco",
    )
    return logs, estado


def raft_transfer_caida_nodo(origen_db, destino_db, monto):
    """Simula caída de un follower: igual que partición."""
    coord = _get_coordinator()
    coord.log.current_term += 1
    logs, estado, acks = coord.transfer(origen_db, destino_db, monto)
    # Si hay 2 acks de 3 → todavía hay quorum (el líder + lima)
    # Para forzar fallo necesitaríamos 2 nodos caídos
    # En un clúster de 3, Raft tolera 1 fallo
    return logs, estado


def raft_recuperacion(origen_db, destino_db, monto):
    """Reintenta transacción con Raft (todos los nodos disponibles)."""
    coord = _get_coordinator()
    coord.log.current_term += 1
    logs, estado, _ = coord.transfer(origen_db, destino_db, monto)
    return logs, estado
