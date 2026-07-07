# db.py — Conexión a PostgreSQL con hosts configurables por variable de entorno
# Adaptado de casoFarmaAndes/python/db.py y casoBancoCooperativo/python/db.py

import os
import psycopg2


def connect(dbname, host=None, port=None):
    """Conecta a un nodo PostgreSQL.

    Si host/port no se especifican, se leen de variables de entorno:
      PG_HOST_<dbname>  —  ej: PG_HOST_almacen_arequipa=10.2.0.10
      PG_PORT_<dbname>  —  ej: PG_PORT_almacen_arequipa=5432

    Valores por defecto: localhost / 5432
    """
    if host is None:
        host = os.environ.get(f"PG_HOST_{dbname}", "localhost")
    if port is None:
        port = int(os.environ.get(f"PG_PORT_{dbname}", 5432))

    return psycopg2.connect(
        dbname=dbname,
        user="sdhm",
        password="",
        host=host,
        port=port,
    )
