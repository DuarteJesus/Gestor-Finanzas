import argparse
import sqlite3
from pathlib import Path

from api import DATABASE_PATH, conectar


def migrar(origen: Path):
    if not origen.is_file():
        raise FileNotFoundError(f"No existe la base de datos: {origen}")
    if origen.resolve() == DATABASE_PATH.resolve():
        raise ValueError("El origen y destino no pueden ser la misma base de datos.")

    source = sqlite3.connect(origen)
    source.row_factory = sqlite3.Row
    try:
        source_users = source.execute(
            "SELECT id, correo, contrasena_hash FROM usuarios ORDER BY id"
        ).fetchall()
        source_preferences = source.execute(
            "SELECT usuario_id, moneda FROM preferencias_financieras"
        ).fetchall()
        movement_columns = {
            row[1] for row in source.execute("PRAGMA table_info(movimientos)")
        }
        optional_columns = ("categoria", "metodo", "notas")
        movement_select = ["id", "usuario_id", "tipo", "descripcion", "monto_centavos", "fecha"]
        movement_select.extend(column for column in optional_columns if column in movement_columns)
        source_movements = source.execute(
            f"SELECT {', '.join(movement_select)} FROM movimientos ORDER BY id"
        ).fetchall()
    finally:
        source.close()

    destination = conectar()
    try:
        destination.execute("BEGIN IMMEDIATE")
        if destination.execute("SELECT COUNT(*) FROM usuarios").fetchone()[0]:
            raise RuntimeError(
                "La base de destino ya contiene cuentas. La migracion se cancelo "
                "para evitar mezclar o duplicar datos."
            )

        user_ids = {}
        for row in source_users:
            cursor = destination.execute(
                "INSERT INTO usuarios (correo, contrasena_hash) VALUES (?, ?)",
                (row["correo"], bytes(row["contrasena_hash"])),
            )
            user_ids[row["id"]] = cursor.lastrowid

        for row in source_preferences:
            if row["usuario_id"] in user_ids:
                destination.execute(
                    "INSERT INTO preferencias_financieras (usuario_id, moneda) "
                    "VALUES (?, ?)",
                    (user_ids[row["usuario_id"]], row["moneda"]),
                )

        for row in source_movements:
            if row["usuario_id"] not in user_ids:
                continue
            destination.execute("""
                INSERT INTO movimientos
                    (usuario_id, tipo, descripcion, monto_centavos, fecha,
                     categoria, metodo, notas)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                user_ids[row["usuario_id"]], row["tipo"], row["descripcion"],
                row["monto_centavos"], row["fecha"],
                row["categoria"] if "categoria" in movement_columns else "Otros",
                row["metodo"] if "metodo" in movement_columns else "Efectivo",
                row["notas"] if "notas" in movement_columns else "",
            ))
        destination.commit()
    except Exception:
        destination.rollback()
        raise
    finally:
        destination.close()

    print(
        f"Migracion completada: {len(source_users)} cuentas, "
        f"{len(source_preferences)} preferencias y {len(source_movements)} movimientos."
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Copia cuentas y movimientos SQLite al destino configurado por DATABASE_URL."
    )
    parser.add_argument("origen", nargs="?", default="cuentas.db", type=Path)
    args = parser.parse_args()
    migrar(args.origen)