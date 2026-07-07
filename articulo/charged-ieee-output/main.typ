#import "@preview/charged-ieee:0.1.4": ieee

#show: ieee.with(
  title: [
    Implementación y Evaluación de Protocolos de Coordinación Distribuida (2PC, Saga, TCC y Raft) sobre PostgreSQL
  ],
  abstract: [
    Se implementaron y evaluaron cuatro protocolos de coordinación de transacciones distribuidas —2PC, Saga, TCC y Raft— sobre PostgreSQL en contenedores Docker simulando una red bancaria de tres nodos. Se midió latencia, tasa de éxito y compensaciones en cuatro escenarios: transacciones exitosas (A), fallo de red (B), caída de nodo (C) y recuperación (D), con 5 repeticiones de 3 transacciones cada una. 2PC mostró la menor latencia en éxito (30.51 ms) pero bloquea ante fallos (323.77 ms por timeout). Saga logró compensación correcta en escenarios B y C con latencia de 37–39 ms y 100% de recuperación. TCC tuvo la mayor latencia (114 ms en éxito) por el overhead de reservas. Raft alcanzó 100% de éxito en todos los escenarios con ~95 ms de latencia gracias a su replicación por consenso, aunque la implementación simplificada usa líder fijo. Se concluye que 2PC es óptimo para entornos sin fallos, Saga ofrece el mejor balance simplicidad/robustez, y Raft garantiza consistencia al costo de mayor complejidad operacional.
  ],
  authors: (
    (
      name: "Mathias Alonso Barrios Medina",
      department: [Escuela Profesional de Ingeniería de Sistemas],
      organization: [Universidad Nacional de San Agustín de Arequipa],
      location: [Arequipa, Perú],
      email: "mbarriosme@unsa.edu.pe",
    ),
    (
      name: "Sergio Danilo Hancco Mullisaca",
      department: [Escuela Profesional de Ingeniería de Sistemas],
      organization: [Universidad Nacional de San Agustín de Arequipa],
      location: [Arequipa, Perú],
      email: "shanccom@unsa.edu.pe",
    ),
    (
      name: "Denise Andrea Huacani Jara",
      department: [Escuela Profesional de Ingeniería de Sistemas],
      organization: [Universidad Nacional de San Agustín de Arequipa],
      location: [Arequipa, Perú],
      email: "dhuacanij@unsa.edu.pe",
    ),
    (
      name: "Fabiana Francinet Pacheco Palo",
      department: [Escuela Profesional de Ingeniería de Sistemas],
      organization: [Universidad Nacional de San Agustín de Arequipa],
      location: [Arequipa, Perú],
      email: "fpachecop@unsa.edu.pe",
    ),
    (
      name: "Alvaro Raul Quispe Condori",
      department: [Escuela Profesional de Ingeniería de Sistemas],
      organization: [Universidad Nacional de San Agustín de Arequipa],
      location: [Arequipa, Perú],
      email: "aquispeco@unsa.edu.pe",
    ),
  ),
  index-terms: ("Two-Phase Commit", "PostgreSQL", "bases de datos distribuidas", "atomicidad", "recuperación ante fallos", "sistemas transaccionales"),
)

#set text(font: "Times New Roman")

// =============================================================================
// I. INTRODUCCIÓN
// =============================================================================

= Introducción

Los sistemas de bases de datos distribuidas requieren mecanismos que garanticen atomicidad y consistencia cuando múltiples nodos independientes participan en una misma transacción. El protocolo Two-Phase Commit (2PC) es el estándar industrial más utilizado para este propósito, pero introduce bloqueos ante fallos de red o caídas de nodos. Protocolos alternativos como Saga, Try-Confirm/Cancel (TCC) y Raft ofrecen distintos compromisos entre consistencia, disponibilidad y tolerancia a particiones.

Este trabajo implementa y compara experimentalmente los cuatro protocolos sobre PostgreSQL en un entorno Docker de tres nodos simulando transferencias bancarias distribuidas. Las contribuciones principales son: (1) implementación didáctica y funcional de cada protocolo en Python, (2) evaluación sistemática en cuatro escenarios de fallo con recolección automatizada de métricas, y (3) análisis comparativo de latencia, tasa de éxito y compensaciones.

// =============================================================================
// II. TRABAJOS RELACIONADOS
// =============================================================================

= Trabajos Relacionados

El estándar X/Open DTP define el modelo de referencia para 2PC con un coordinador centralizado que recolecta votos de todos los participantes antes de decidir commit o abort global @xopen1991. Bernstein et al. formalizaron las propiedades de atomicidad y recuperación en sistemas distribuidos @bernstein1987. Mohan et al. propusieron las optimizaciones Presumed Abort y Presumed Commit que reducen el número de mensajes en el camino común @mohan1986.

Como alternativas a 2PC, Garcia-Molina y Salem introdujeron Sagas como secuencias de transacciones locales con compensaciones explícitas @garciamolina1987. El patrón Try-Confirm/Cancel extiende este modelo añadiendo una fase de reserva que reduce la ventana de inconsistencia @helland2007. En el extremo de consistencia fuerte, Raft ofrece un protocolo de consenso donde cada decisión requiere mayoría de votos de un clúster de réplicas @ongaro2014, eliminando el punto único de fallo del coordinador.

Trabajos previos han evaluado el rendimiento de 2PC en PostgreSQL @ozsu2020, pero no existe una comparación experimental directa de los cuatro protocolos sobre la misma infraestructura, que es precisamente la contribución de este artículo.

// =============================================================================
// III. METODOLOGÍA
// =============================================================================

= Metodología

== Arquitectura del Sistema

La infraestructura experimental consiste en tres contenedores PostgreSQL (pg-arequipa, pg-lima, pg-cusco) conectados mediante una red Docker bridge (10.2.0.0/24) y un contenedor de aplicación Python que actúa como orquestador de transacciones. Cada nodo aloja una base de datos del dominio bancario con una cuenta única. La @fig:topology ilustra la topología.

#figure(
  placement: top,
  caption: [Topología de red experimental con tres contenedores PostgreSQL y un orquestador Python.],
  image("figures/fig1_topologia.png", width: 100%),
) <fig:topology>

== Protocolos Implementados

- _2PC:_ Coordinador centralizado que ejecuta PREPARE (verificación de saldo y débito en origen) seguido de COMMIT (crédito en destino) sobre ambos nodos en una misma transacción distribuida con two-phase locking.
- _Saga:_ Secuencia de dos transacciones locales independientes (débito, crédito). Si el paso 2 falla, se ejecuta una compensación que revierte el débito del paso 1.
- _TCC:_ Tres fases: TRY (INSERT en tabla _reservas_ con verificación de saldo), CONFIRM (UPDATE en _cuentas_ y marca _confirmed_ en reservas) y CANCEL (marca _cancelled_ sin modificar saldos).
- _Raft simplificado:_ Líder fijo (Arequipa, ID=0) con dos followers. Cada comando se replica a los tres nodos y requiere quorum de 2/3 para commit. El log se almacena en la tabla _raft_log_ de cada nodo.

== Entorno Experimental



#table(
  columns: (auto, auto),
  align: (left, left),
  inset: (x: 5pt, y: 4pt),
  stroke: (x, y) => if y == 0 { (bottom: 0.5pt) },
  fill: (x, y) => if y > 0 and calc.rem(y, 2) == 0 { rgb("#efefef") },

  table.header[*Componente*, *Versión / Detalle *],
  [PostgreSQL], [15-alpine (Docker)],
  [Python], [3.11-slim + psycopg2-binary 2.9.12],
  [Docker Engine], [29.5.2],
  [Red], [Bridge 10.2.0.0/24, sin latencia artificial],
  [Host], [Windows 11, SSD NVMe],
)
*Tabla I. Entorno experimental. Sin latencia de red simulada.*

== Escenarios de Evaluación

Cada protocolo se evaluó en cuatro escenarios, con 5 repeticiones de 3 transacciones cada una (15 observaciones por celda, 240 total).

- _A — Éxito:_ Transferencia sin fallos entre banco_arequipa y banco_cusco por montos de S/ 500--640.
- _B — Fallo de red:_ El destino simula timeout de 300 ms durante PREPARE (2PC/Saga/TCC) o pierde conectividad (Raft).
- _C — Caída de nodo:_ El destino lanza excepción durante la fase COMMIT, forzando abort o compensación.
- _D — Recuperación:_ Se reintenta la transferencia tras restaurar el estado de todos los nodos.

// =============================================================================
// IV. RESULTADOS EXPERIMENTALES
// =============================================================================

= Resultados Experimentales

== Escenario A: Transacciones Exitosas

La @tab:A presenta las latencias medias sin fallos. 2PC y Saga obtuvieron rendimiento similar (~30 ms), mientras TCC fue 3.8× más lento por el overhead de las reservas.

#figure(
  placement: top,
  caption: [Escenario A: transferencias exitosas sin fallos (n=15).],
  table(
    columns: (auto, auto, auto, auto, auto),
    align: center,
    inset: (x: 4pt, y: 4pt),
    stroke: (x, y) => if y <= 1 { (top: 0.5pt) },
    fill: (x, y) => if y > 0 and calc.rem(y, 2) == 0 { rgb("#efefef") },

    table.header[*Protocolo*, *Latencia (ms)*, *Desv. Est.*, *Éxito*, *Comp.*],
    [2PC],  [30.51], [6.65],  [100%], [0.00],
    [Saga], [29.27], [5.38],  [100%], [0.00],
    [TCC],  [114.02], [11.65], [100%], [0.00],
    [Raft], [94.30], [5.82],  [100%], [0.00],
  ),
) <tab:A>

== Escenario B: Fallo de Red

2PC registró 323.77 ms por el timeout fijo de 300 ms. Saga y TCC fallaron correctamente con 1 compensación promedio. Raft mantuvo 100% de éxito gracias al quorum: 2 de 3 nodos bastan para commit.

#figure(
  placement: top,
  caption: [Escenario B: fallo de red durante PREPARE (n=15).],
  table(
    columns: (auto, auto, auto, auto, auto),
    align: center,
    inset: (x: 4pt, y: 4pt),
    stroke: (x, y) => if y <= 1 { (top: 0.5pt) },
    fill: (x, y) => if y > 0 and calc.rem(y, 2) == 0 { rgb("#efefef") },

    table.header[*Protocolo*, *Latencia (ms)*, *Desv. Est.*, *Éxito*, *Comp.*],
    [2PC],  [323.77], [2.25],   [0%],  [0.00],
    [Saga], [39.05],  [6.20],   [0%],  [1.00],
    [TCC],  [109.32], [10.59],  [0%],  [1.00],
    [Raft], [178.24], [220.96], [100%], [0.00],
  ),
)

== Escenario C: Caída de Nodo

La @tab:C muestra resultados similares al escenario B, con la diferencia de que 2PC detecta la caída más rápido (24.99 ms) porque la excepción se lanza en la fase COMMIT, sin esperar el timeout.

#figure(
  placement: top,
  caption: [Escenario C: caída de nodo durante COMMIT (n=15).],
  table(
    columns: (auto, auto, auto, auto, auto),
    align: center,
    inset: (x: 4pt, y: 4pt),
    stroke: (x, y) => if y <= 1 { (top: 0.5pt) },
    fill: (x, y) => if y > 0 and calc.rem(y, 2) == 0 { rgb("#efefef") },

    table.header[*Protocolo*, *Latencia (ms)*, *Desv. Est.*, *Éxito*, *Comp.*],
    [2PC],  [24.99], [3.09],  [0%],  [0.00],
    [Saga], [37.24], [6.70],  [0%],  [1.00],
    [TCC],  [109.94], [7.56], [0%],  [1.00],
    [Raft], [97.05], [5.83],  [100%], [0.00],
  ),
) <tab:C>

== Escenario D: Recuperación

Saga, TCC y Raft lograron 100% de recuperación exitosa. 2PC muestra 0% porque su función de recuperación requiere el parámetro _tipo_fallo_, no utilizado en las pruebas automatizadas. En el caso original del Banco Cooperativo, la recuperación 2PC funciona correctamente.

#figure(
  placement: top,
  caption: [Escenario D: recuperación post-fallo (n=15).],
  table(
    columns: (auto, auto, auto, auto, auto),
    align: center,
    inset: (x: 4pt, y: 4pt),
    stroke: (x, y) => if y <= 1 { (top: 0.5pt) },
    fill: (x, y) => if y > 0 and calc.rem(y, 2) == 0 { rgb("#efefef") },

    table.header[*Protocolo*, *Latencia (ms)*, *Desv. Est.*, *Éxito*, *Comp.*],
    [2PC],  [24.41], [1.72],  [0%],  [0.00],
    [Saga], [28.00], [4.25],  [100%], [0.00],
    [TCC],  [117.04], [10.05], [100%], [0.00],
    [Raft], [95.70], [7.13],  [100%], [0.00],
  ),
)

== Análisis Comparativo Global

Las Figuras 2 y 3 presentan las gráficas comparativas generadas con PlantUML a partir de los datos experimentales: latencia por protocolo y escenario, y tasa de éxito.

#figure(
  placement: top,
  caption: [Latencia comparativa por protocolo y escenario (ms).],
  image("figures/fig2a_latencia.png", width: 100%),
) <fig:latencia>

#figure(
  placement: top,
  caption: [Tasa de éxito por protocolo y escenario (%).],
  image("figures/fig2b_exito.png", width: 100%),
) <fig:exito>

== Código Relevante

El siguiente fragmento muestra el núcleo del protocolo Saga con compensación automática:

#rect(
  width: 100%,
  fill: rgb("#f0f0f0"),
  inset: 5pt,
)[
  ```py
  # Paso 1: Débito en origen
  cur_o.execute("UPDATE cuentas
    SET saldo = saldo - %s", (monto,))
  conn_o.commit()

  # Paso 2: Crédito en destino
  cur_d.execute("UPDATE cuentas
    SET saldo = saldo + %s", (monto,))
  # Si falla -> compensación:
  cur_comp.execute("UPDATE cuentas
    SET saldo = saldo + %s", (monto,))
  ```
]

// =============================================================================
// V. DISCUSIÓN
// =============================================================================

= Discusión

Los resultados confirman que ningún protocolo es universalmente superior: la elección depende del perfil de fallos esperado y los requisitos de latencia.

2PC es el más eficiente en régimen normal (30.51 ms) pero introduce un bloqueo determinista ante fallos: el timeout de 300 ms domina la latencia total, y el coordinador centralizado constituye un punto único de fallo. En entornos LAN con baja tasa de fallos, 2PC sigue siendo la opción más simple y rápida.

Saga ofrece el mejor balance simplicidad/robustez: su latencia en éxito (29.27 ms) es comparable a 2PC, y en escenarios de fallo la compensación añade solo ~8 ms. Para sagas de más de 2 pasos, el número de compensaciones crecería linealmente con la longitud de la saga.

TCC mostró el mayor overhead (114 ms) debido a 4 operaciones adicionales por transacción. Sin embargo, su modelo de reservas ofrece una garantía más fuerte que Saga: los fondos están bloqueados desde TRY, eliminando condiciones de carrera en escenarios de alta contención.

Raft fue el único protocolo con 100% de éxito en todos los escenarios. La latencia de ~95 ms refleja el costo de replicar cada comando a 3 nodos. Las limitaciones de la implementación —líder fijo, log en memoria, sin heartbeats— implican que estos resultados representan una cota inferior del rendimiento real. En producción, Raft añadiría 150–300 ms por elección de líder en caso de fallo del nodo líder.

Las amenazas a la validez incluyen: (1) todas las pruebas se ejecutaron en un solo host Docker sin latencia de red real, subestimando tiempos absolutos pero preservando diferencias relativas; (2) el tamaño de muestra (n=15) es adecuado para tendencias pero insuficiente para significancia estadística formal; (3) la simulación de fallos es determinista y no captura la estocasticidad de fallos reales.

// =============================================================================
// VI. CONCLUSIONES
// =============================================================================

= Conclusiones

Se implementaron y compararon experimentalmente cuatro protocolos de coordinación distribuida sobre PostgreSQL en un entorno Docker de 3 nodos (240 transacciones en total). Los hallazgos principales son:

- 2PC ofrece la menor latencia sin fallos (~30 ms) pero su coordinador centralizado es un punto único de fallo y el timeout penaliza severamente los escenarios con pérdida de conectividad.
- Saga logra el mejor compromiso simplicidad/robustez: compensación correcta en 100% de los casos con solo ~8 ms de overhead adicional.
- TCC proporciona garantías más fuertes mediante reservas explícitas, al costo de 3.8× más latencia. Es adecuado para escenarios con alta probabilidad de condiciones de carrera.
- Raft fue el único protocolo con 100% de tasa de éxito en todos los escenarios, demostrando empíricamente la tolerancia a fallos que el consenso mayoritario proporciona.

// =============================================================================
// VII. TRABAJO FUTURO
// =============================================================================

= Trabajo Futuro

- Implementar la optimización Presumed Abort en 2PC para reducir mensajes en el caso de rollback.
- Replicar el coordinador 2PC con Paxos o Raft para eliminar el punto único de fallo.
- Evaluar los protocolos con latencias de red reales (>50 ms entre continentes) usando _tc-netem_ en los contenedores Docker.
- Extender la implementación de Raft con elección dinámica de líder, heartbeats periódicos y persistencia del log en disco.
- Aumentar el tamaño de muestra a 100+ repeticiones para obtener significancia estadística en las diferencias de latencia.
- Integrar middleware de mensajería (RabbitMQ/Kafka) para desacoplar la comunicación entre nodos en Saga y TCC.

// =============================================================================
// REFERENCIAS
// =============================================================================

#bibliography("refs.bib")

// =============================================================================
// APÉNDICE
// =============================================================================

= Apéndice

== Codigo Fuente
#link("https://github.com/unsa-semester-2026-A/sis_dis_lab/tree/main/Proyecto_final", "Repositorio del Proyecto")

== Reproducibilidad
Todos los experimentos son reproducibles mediante:
1. `cd docker && docker compose up -d --build`
2. `cd experiments && sh run_experiments.sh`
3. `python analyze_results.py results graphs`

El código fuente completo está disponible en el repositorio del laboratorio.

===  Requisitos previos

#table(
  columns: (auto, auto, auto),
  align: (left, left, left),
  table.header[*Herramienta*, *Versión mínima*, *Verificación*],
  [Docker], [24+], [`docker --version`],
  [Docker Compose], [v2], [`docker compose version`],
  [Python], [3.11+], [`python --version`],
  [Bash], [4+], [`bash --version`],
  [Typst (opcional)], [0.12+], [`typst --version`],
)
Mapeo de puertos al host:
- pg-arequipa → `localhost:5432`
- pg-lima → `localhost:5433`
- pg-cusco → `localhost:5434`

=== Ejecución de experimentos 

Opción rápida: script con todos los escenarios
```bash
cd articulo/scripts
chmod +x *.sh
./run_all.sh
```

== Configuración de PostgreSQL

Parámetros relevantes de _postgresql.conf_: `wal_level = replica`, `max_wal_senders = 10`, `synchronous_commit = on`. Las cadenas de conexión usan el usuario _sdhm_ sin contraseña y los hostnames de Docker: pg-arequipa, pg-lima, pg-cusco en puerto 5432.

== Datos de Prueba

Cuentas iniciales: Alvaro Quispe (Arequipa, S/ 50,000), Fabiana Pacheco (Lima, S/ 20,000), Mathias Barrios (Cusco, S/ 30,000). Las transferencias son por montos crecientes de S/ 500 a S/ 640 en incrementos de S/ 10.




