"""Memoria permanente del observador: una base de datos SQLite en diario/vivo/.

Cada decisión (compra imaginaria, rechazo o compra que fallaría) es una fila
con el precio exacto del momento, y luego el precio a 1 hora y a 24 horas.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

_ESQUEMA = """
CREATE TABLE IF NOT EXISTS decisiones (
    id INTEGER PRIMARY KEY,
    momento REAL NOT NULL,        -- segundos desde 1970 (hora exacta de la decisión)
    fecha TEXT NOT NULL,          -- día local, AAAA-MM-DD
    cadena TEXT NOT NULL,
    token TEXT NOT NULL,
    simbolo TEXT, nombre TEXT, par TEXT, dex TEXT, url TEXT,
    accion TEXT NOT NULL,         -- compra · rechazo · fallida
    tipo TEXT,                    -- de rechazo: seguridad · límites · precio
    motivos TEXT,                 -- JSON: lista de motivos
    hype INTEGER, riesgo INTEGER, arquetipo TEXT,
    razones_hype TEXT, banderas TEXT, billeteras TEXT,   -- JSON
    precio REAL, liquidez REAL, fdv REAL,
    monto REAL, nota_monto TEXT, precio_entrada REAL, cantidad REAL,
    comision_red REAL, comision_dex REAL, slippage_pct REAL,
    momento_1h REAL, precio_1h REAL, liquidez_1h REAL, valor_1h REAL,
    momento_24h REAL, precio_24h REAL, liquidez_24h REAL, valor_24h REAL,
    archivo TEXT,
    UNIQUE (cadena, token)
);
CREATE TABLE IF NOT EXISTS vistos (
    fecha TEXT NOT NULL, cadena TEXT NOT NULL, token TEXT NOT NULL,
    UNIQUE (fecha, cadena, token)
);
"""
_JSON = ("motivos", "razones_hype", "banderas", "billeteras")


class Registro:
    def __init__(self, ruta: Path):
        ruta.parent.mkdir(parents=True, exist_ok=True)
        self.con = sqlite3.connect(ruta)
        self.con.row_factory = sqlite3.Row
        self.con.executescript(_ESQUEMA)

    def _fila(self, r: sqlite3.Row | None) -> dict | None:
        if r is None:
            return None
        d = dict(r)
        for k in _JSON:
            d[k] = json.loads(d[k]) if d.get(k) else None
        return d

    def ya_decidido(self, cadena: str, token: str) -> bool:
        return self.con.execute("SELECT 1 FROM decisiones WHERE cadena=? AND token=?", (cadena, token)).fetchone() is not None

    def marcar_visto(self, fecha: str, cadena: str, token: str) -> None:
        self.con.execute("INSERT OR IGNORE INTO vistos VALUES (?,?,?)", (fecha, cadena, token))
        self.con.commit()

    def vistos(self, fecha: str) -> int:
        return self.con.execute("SELECT COUNT(*) FROM vistos WHERE fecha=?", (fecha,)).fetchone()[0]

    def guardar(self, datos: dict) -> int:
        datos = {k: (json.dumps(v, ensure_ascii=False) if k in _JSON and v is not None else v) for k, v in datos.items()}
        columnas = ", ".join(datos)
        cur = self.con.execute(f"INSERT INTO decisiones ({columnas}) VALUES ({', '.join('?' * len(datos))})",
                               list(datos.values()))
        self.con.commit()
        return cur.lastrowid

    def actualizar(self, id_: int, **campos) -> None:
        asignaciones = ", ".join(f"{k}=?" for k in campos)
        self.con.execute(f"UPDATE decisiones SET {asignaciones} WHERE id=?", [*campos.values(), id_])
        self.con.commit()

    def obtener(self, id_: int) -> dict:
        return self._fila(self.con.execute("SELECT * FROM decisiones WHERE id=?", (id_,)).fetchone())

    def pendientes(self, ahora: float) -> list[dict]:
        filas = self.con.execute(
            "SELECT * FROM decisiones WHERE (momento_1h IS NULL AND momento + 3600 <= ?)"
            " OR (momento_24h IS NULL AND momento + 86400 <= ?)", (ahora, ahora)).fetchall()
        return [self._fila(r) for r in filas]

    def del_dia(self, fecha: str) -> list[dict]:
        filas = self.con.execute("SELECT * FROM decisiones WHERE fecha=? ORDER BY momento", (fecha,)).fetchall()
        return [self._fila(r) for r in filas]

    def todas(self) -> list[dict]:
        return [self._fila(r) for r in self.con.execute("SELECT * FROM decisiones ORDER BY momento").fetchall()]

    def gastado(self, fecha: str) -> float:
        return self.con.execute("SELECT COALESCE(SUM(monto),0) FROM decisiones WHERE accion='compra' AND fecha=?",
                                (fecha,)).fetchone()[0]

    def invertido_abierto(self) -> float:
        """Compras imaginarias que aún no llegan a las 24 h (siguen 'en juego')."""
        return self.con.execute("SELECT COALESCE(SUM(monto),0) FROM decisiones"
                                " WHERE accion='compra' AND momento_24h IS NULL").fetchone()[0]
