# Protocolos-de-Coordinaci-n-Distribuida---SD

Infraestructura reproducible para evaluar el protocolo **Two-Phase Commit (2PC)** en entornos distribuidos con Docker. Soporta los casos de estudio **FarmaAndes** (transferencia de inventario entre almacenes) y **Sistema Nacional de Bancos Cooperativos** (transferencias bancarias con fallos).

## Requisitos previos

| Herramienta | Versión mínima | Verificación |
|---|---|---|
| Docker | 24+ | `docker --version` |
| Docker Compose | v2 | `docker compose version` |
| Python | 3.11+ | `python --version` |
| Bash | 4+ | `bash --version` |
| **Opcional:** Typst | 0.12+ | `typst --version` (para compilar PDF) |

## Estructura del proyecto

```
articulo/
├── articulo.typ                  # Artículo IEEE en Typst (placeholders)
├── ieee_template.typ             # Plantilla IEEE dos columnas + macros
├── README.md                     # Este archivo
├── apendice_code.txt             # Trazabilidad del código reutilizado
│
├── docker/
│   ├── docker-compose.yml        # 3 nodos PostgreSQL + app container
│   ├── app/Dockerfile            # Imagen Python 3.11 + psycopg2
│   └── init/
│       ├── 01-arequipa.sql       # BD: almacen_arequipa + banco_arequipa
│       ├── 02-lima.sql           # BD: almacen_lima     + banco_lima
│       └── 03-cusco.sql          # BD: banco_cusco
│
├── src/
│   ├── db.py                     # Conexión PG con hosts configurables
│   └── coordinator_2pc.py        # Protocolo 2PC unificado (farma + banco)
│
├── experiments/
│   ├── client_load.py            # Generador de carga + CSV
│   └── results/                  # CSVs generados (ignorados por git)
│
└── scripts/
    ├── run_all.sh                # Orquestador de experimentos A–D
    ├── simulate_partition.sh     # Partición de red con iptables/tc
    ├── kill_coordinator.sh       # Caída/recuperación del coordinador
    └── add_latency.sh            # Latencia artificial con tc-netem
```

## Topología de red Docker

```
                    ┌─────────────────────┐
                    │   two-pc-app (app)   │
                    │    10.2.0.100        │
                    │  Python 3.11 slim    │
                    └──────┬──────┬───────┘
                           │      │
          ┌────────────────┼──────┼──────────────────┐
          │                │      │                  │
   ┌──────▼──────┐  ┌──────▼──────┐  ┌──────▼──────┐
   │ pg-arequipa │  │  pg-lima    │  │  pg-cusco   │
   │  10.2.0.10  │  │  10.2.0.20  │  │  10.2.0.30  │
   │  PG 15      │  │  PG 15      │  │  PG 15      │
   │  puerto 5432│  │  puerto 5432│  │  puerto 5432│
   └─────────────┘  └─────────────┘  └─────────────┘
```

**Mapeo de puertos al host:**
- pg-arequipa → `localhost:5432`
- pg-lima → `localhost:5433`
- pg-cusco → `localhost:5434`

## 1. Levantar el entorno

```bash
cd articulo/docker

# Construir e iniciar todos los contenedores
docker compose up -d --build

# Verificar que estén todos saludables
docker compose ps
```

**Esperar ~10 segundos** a que PostgreSQL termine de inicializar las bases de datos.

### Verificar que las BD se crearon correctamente

```bash
# FarmaAndes — inventario en Arequipa
docker exec pg-arequipa psql -U sdhm -d almacen_arequipa -c "SELECT * FROM inventario"

# FarmaAndes — inventario en Lima
docker exec pg-lima psql -U sdhm -d almacen_lima -c "SELECT * FROM inventario"

# Banco — cuentas en cada nodo
docker exec pg-arequipa psql -U sdhm -d banco_arequipa -c "SELECT * FROM cuentas"
docker exec pg-cusco    psql -U sdhm -d banco_cusco    -c "SELECT * FROM cuentas"
docker exec pg-lima     psql -U sdhm -d banco_lima     -c "SELECT * FROM cuentas"
```

## 2. Ejecutar experimentos

### Opción rápida: todos los escenarios

```bash
cd articulo/scripts
chmod +x *.sh
./run_all.sh

```

### Opción granular: escenario por escenario

```bash
# Solo escenario A (transacciones exitosas, 10 iteraciones)
./run_all.sh A

# Escenarios A y B con 20 iteraciones y monto base S/ 1000
N_ITER=20 MONTO_BASE=1000 ./run_all.sh A B

# Escenario C con 5 iteraciones
N_ITER=5 ./run_all.sh C

# Hooks para protocolos futuros (placeholder)
./run_all.sh saga tcc raft
```

### Ejecutar directamente desde el contenedor

```bash
docker exec two-pc-app bash -c \
  "cd /app/experiments && ESCENARIO=A N_ITER=5 python client_load.py"
```

## 3. Escenarios definidos

| Escenario | Descripción | ¿Qué mide? | ¿Qué protocolo falla? |
|---|---|---|---|
| **A** | Transacciones exitosas sin fallos | Latencia total, throughput | Ninguno |
| **B** | Fallo de red (timeout en PREPARE) | Tiempo de detección de timeout, consistencia post-rollback | PREPARE → timeout |
| **C** | Caída de nodo (durante COMMIT) | Correctitud del rollback, restauración del débito | COMMIT → abort |
| **D** | Recuperación post-fallo | Latencia de reintento, tasa de recuperación exitosa | Cualquiera → replay |

## 4. Formato del CSV de resultados

Cada escenario genera un archivo `experiments/results/<PROTOCOLO>_<ESCENARIO>.csv` con las columnas:

| Columna | Tipo | Descripción |
|---|---|---|
| `escenario` | char | Letra del escenario (A/B/C/D) |
| `protocolo` | string | Protocolo evaluado (2PC, saga, tcc, raft) |
| `operacion_id` | int | Número de operación (1..N_ITER) |
| `timestamp` | ISO-8601 | Momento de ejecución |
| `prepare_latency_ms` | float | Latencia de fase PREPARE (placeholder, medir dentro de coordinator) |
| `commit_latency_ms` | float | Latencia de fase COMMIT (placeholder, medir dentro de coordinator) |
| `total_latency_ms` | float | Latencia total de la transacción (wall-clock) |
| `exito` | bool | `true` si COMMIT, `false` si ROLLBACK |
| `nodos_involucrados` | string | Pares de nodos (ej: `banco_arequipa,banco_cusco`) |
| `tipo_fallo` | string | `ninguno`, `red`, `nodo_caido`, `caida_nodo`, `fallo_red` |
| `observaciones` | string | Últimos logs de la transacción |

## 5. Scripts de inyección de fallos

### Partición de red

```bash
# Activar partición entre Arequipa y Cusco
./simulate_partition.sh on pg-arequipa pg-cusco

# Desactivar partición
./simulate_partition.sh off pg-arequipa pg-cusco
```

### Caída del coordinador

```bash
# Detener (simula caída del proceso)
./kill_coordinator.sh stop

# Recuperar (reinicia el contenedor)
./kill_coordinator.sh start

# Ver estado
./kill_coordinator.sh status
```

### Latencia geográfica

```bash
# Agregar 80ms ± 10ms jitter a todos los paquetes del nodo Arequipa
./add_latency.sh on pg-arequipa 80 10

# Agregar 120ms a Cusco
./add_latency.sh on pg-cusco 120 20

# Ver estado actual de latencias
./add_latency.sh show

# Eliminar toda latencia artificial
./add_latency.sh off
```

> **Nota sobre Windows/macOS:** `tc-netem` solo funciona en Linux. Los scripts incluyen manejo de errores para entornos donde `tc` no está disponible (los comandos fallan silenciosamente sin detener la ejecución).

## 6. Compilar el artículo (Typst)

```bash
cd articulo
typst compile articulo.typ articulo.pdf
```

## 7. Detener el entorno

```bash
cd articulo/docker
docker compose down -v    # -v elimina volúmenes (datos)
docker compose down       # sin -v: preserva datos entre sesiones
```

## 8. Extender con nuevos protocolos (hooks)

El sistema está preparado para evaluar comparativamente **múltiples protocolos**:

### Saga

```bash
# 1. Crear src/saga_coordinator.py con orquestador + compensaciones
# 2. Agregar saga_transfer() al module
# 3. Registrar en experiments/client_load.py despachando según PROTOCOLO=saga
# 4. Ejecutar:
PROTOCOLO=saga ./run_all.sh A B C D
```

### TCC (Try-Confirm/Cancel)

```bash
# 1. Crear src/tcc_coordinator.py con fases Try/Confirm/Cancel + timeouts
# 2. Agregar TCC al dispatcher de client_load.py
# 3. Ejecutar:
PROTOCOLO=tcc ./run_all.sh A B C D
```

### Raft

```bash
# 1. Agregar +2 contenedores PostgreSQL en docker-compose.yml (total 5 nodos)
# 2. Crear src/raft_coordinator.py con elección de líder + log replication
# 3. Modificar client_load.py para soportar operaciones Raft
# 4. Ejecutar:
PROTOCOLO=raft ./run_all.sh A B C D
```

## Solución de problemas

| Problema | Causa probable | Solución |
|---|---|---|
| `ERROR: contenedores no encontrados` | Docker no está corriendo o `docker compose up` no se ejecutó | `cd docker && docker compose up -d` |
| `psql: could not connect to server` | PostgreSQL aún está inicializando | Esperar 10s y reintentar |
| Puertos 5432-5434 ocupados | PostgreSQL local corriendo | `systemctl stop postgresql` o cambiar puertos en docker-compose.yml |
| `tc: command not found` en add_latency | macOS/Windows sin netem | Normal en no-Linux; usar solo en Linux para latencia real |
| CSV vacío o sin filas | BD no inicializada correctamente | Verificar con `docker compose logs pg-arequipa` |


# Realizamiento de graficas del articulo con matplotlib
pip install virtualenv
virtualenv -p python env
./env/Scripts/activate
pip install -r requirements.txt 

python articulo/experiments/analyze_results.py articulo/experiments/results articulo/experiments/graphs
