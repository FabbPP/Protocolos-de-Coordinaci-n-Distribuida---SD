-- Nodo Arequipa: FarmaAndes (almacen) + Banco Cooperativo
CREATE DATABASE almacen_arequipa;
CREATE DATABASE banco_arequipa;

\c almacen_arequipa;
CREATE TABLE inventario (
    id SERIAL PRIMARY KEY,
    producto VARCHAR(100) NOT NULL,
    stock INTEGER NOT NULL CHECK (stock >= 0)
);
INSERT INTO inventario (producto, stock) VALUES
    ('Paracetamol', 50),
    ('Ibuprofeno',  30),
    ('Amoxicilina', 20);

\c banco_arequipa;
CREATE TABLE cuentas (
    id SERIAL PRIMARY KEY,
    titular VARCHAR(200) NOT NULL,
    saldo NUMERIC(12,2) NOT NULL CHECK (saldo >= 0)
);
INSERT INTO cuentas (titular, saldo) VALUES ('Alvaro Quispe', 50000.00);

-- Tabla de reservas para TCC
CREATE TABLE IF NOT EXISTS reservas (
    id_tx     TEXT PRIMARY KEY,
    cuenta_id INTEGER NOT NULL,
    monto     NUMERIC(12,2) NOT NULL,
    tipo      TEXT NOT NULL CHECK (tipo IN ('debito', 'credito')),
    estado    TEXT NOT NULL DEFAULT 'try' CHECK (estado IN ('try', 'confirmed', 'cancelled')),
    created_at TIMESTAMP DEFAULT NOW()
);

-- Log de replicación para Raft
CREATE TABLE IF NOT EXISTS raft_log (
    log_index     INTEGER NOT NULL,
    term          INTEGER NOT NULL,
    command_json  TEXT NOT NULL,
    committed     BOOLEAN NOT NULL DEFAULT false,
    created_at    TIMESTAMP DEFAULT NOW(),
    PRIMARY KEY (log_index, term)
);
