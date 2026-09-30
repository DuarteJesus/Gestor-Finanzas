import os
import re
import sqlite3
from contextlib import closing
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import bcrypt
import jwt
from fastapi import Depends, FastAPI, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel


DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./gestor_finanzas_server.db")
if not DATABASE_URL.startswith("sqlite:///"):
    raise RuntimeError("DATABASE_URL debe apuntar a una base SQLite persistente.")
DATABASE_PATH = Path(DATABASE_URL.removeprefix("sqlite:///"))
if not DATABASE_PATH.is_absolute():
    DATABASE_PATH = (Path.cwd() / DATABASE_PATH).resolve()
DATABASE_PATH.parent.mkdir(parents=True, exist_ok=True)
JWT_SECRET = os.getenv("JWT_SECRET", "")
JWT_ALGORITHM = "HS256"


def conectar():
    connection = sqlite3.connect(DATABASE_PATH, timeout=20)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys=ON")
    connection.execute("PRAGMA busy_timeout=20000")
    return connection


with closing(conectar()) as connection:
    connection.executescript("""
        CREATE TABLE IF NOT EXISTS usuarios (
            id INTEGER PRIMARY KEY,
            correo TEXT UNIQUE NOT NULL,
            contrasena_hash BLOB NOT NULL
        );
        CREATE TABLE IF NOT EXISTS preferencias_financieras (
            usuario_id INTEGER PRIMARY KEY,
            moneda TEXT NOT NULL,
            FOREIGN KEY (usuario_id) REFERENCES usuarios (id) ON DELETE CASCADE
        );
        CREATE TABLE IF NOT EXISTS movimientos (
            id INTEGER PRIMARY KEY,
            usuario_id INTEGER NOT NULL,
            tipo TEXT NOT NULL CHECK (tipo IN ('ingreso', 'gasto')),
            descripcion TEXT NOT NULL,
            monto_centavos INTEGER NOT NULL CHECK (monto_centavos > 0),
            fecha TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            categoria TEXT NOT NULL DEFAULT 'Otros',
            metodo TEXT NOT NULL DEFAULT 'Efectivo',
            notas TEXT NOT NULL DEFAULT '',
            FOREIGN KEY (usuario_id) REFERENCES usuarios (id) ON DELETE CASCADE
        );
        CREATE INDEX IF NOT EXISTS idx_movimientos_usuario
            ON movimientos (usuario_id, id DESC);
    """)
    movement_columns = {
        row["name"] for row in connection.execute("PRAGMA table_info(movimientos)")
    }
    for name, definition in (
        ("categoria", "TEXT NOT NULL DEFAULT 'Otros'"),
        ("metodo", "TEXT NOT NULL DEFAULT 'Efectivo'"),
        ("notas", "TEXT NOT NULL DEFAULT ''"),
    ):
        if name not in movement_columns:
            connection.execute(f"ALTER TABLE movimientos ADD COLUMN {name} {definition}")
    connection.commit()


class Credentials(BaseModel):
    email: str
    password: str


class Registration(Credentials):
    currency: str = "EUR"


class NewMovement(BaseModel):
    kind: str
    description: str
    amount_cents: int
    movement_date: str
    category: str = "Otros"
    method: str = "Efectivo"
    notes: str = ""


app = FastAPI(title="Gestor Finanzas API", version="1.0.0")
bearer = HTTPBearer(auto_error=False)


def crear_token(user_id: int) -> str:
    if not JWT_SECRET:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="El servidor aun no esta configurado: falta JWT_SECRET.",
        )
    ahora = datetime.now(timezone.utc)
    return jwt.encode(
        {"sub": str(user_id), "iat": ahora, "exp": ahora + timedelta(days=7)},
        JWT_SECRET,
        algorithm=JWT_ALGORITHM,
    )


def obtener_conexion():
    connection = conectar()
    try:
        yield connection
    finally:
        connection.close()


def usuario_actual(
    credenciales: HTTPAuthorizationCredentials | None = Depends(bearer),
    connection: sqlite3.Connection = Depends(obtener_conexion),
) -> dict:
    if not credenciales:
        raise HTTPException(status_code=401, detail="Inicia sesion para continuar.")
    try:
        payload = jwt.decode(
            credenciales.credentials, JWT_SECRET, algorithms=[JWT_ALGORITHM]
        )
        user_id = int(payload["sub"])
    except (jwt.InvalidTokenError, KeyError, ValueError):
        raise HTTPException(status_code=401, detail="La sesion no es valida.") from None
    user = connection.execute(
        "SELECT id, correo FROM usuarios WHERE id = ?", (user_id,)
    ).fetchone()
    if not user:
        raise HTTPException(status_code=401, detail="La cuenta ya no existe.")
    return dict(user)


def validar_correo_y_contrasena(email: str, password: str):
    email = email.strip().lower()
    if not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", email):
        raise HTTPException(status_code=422, detail="Escribe un correo valido.")
    if len(password) < 8:
        raise HTTPException(
            status_code=422, detail="La contrasena debe tener al menos 8 caracteres."
        )
    return email


def usuario_y_moneda(connection: sqlite3.Connection, user: dict):
    preference = connection.execute(
        "SELECT moneda FROM preferencias_financieras WHERE usuario_id = ?",
        (user["id"],),
    ).fetchone()
    return {"id": user["id"], "email": user["correo"],
            "currency": preference["moneda"] if preference else "EUR"}


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/auth/register")
def registrar(data: Registration, connection: sqlite3.Connection = Depends(obtener_conexion)):
    if not JWT_SECRET:
        raise HTTPException(
            status_code=503, detail="Configura JWT_SECRET antes de iniciar el servidor."
        )
    email = validar_correo_y_contrasena(data.email, data.password)
    currency = data.currency.strip().upper()
    if len(currency) != 3 or not currency.isalpha() or not currency.isascii():
        raise HTTPException(status_code=422, detail="Usa un codigo de moneda de 3 letras.")
    password_hash = bcrypt.hashpw(data.password.encode("utf-8"), bcrypt.gensalt())
    try:
        cursor = connection.execute(
            "INSERT INTO usuarios (correo, contrasena_hash) VALUES (?, ?)",
            (email, password_hash),
        )
        user = {"id": cursor.lastrowid, "correo": email}
        connection.execute(
            "INSERT INTO preferencias_financieras (usuario_id, moneda) VALUES (?, ?)",
            (user["id"], currency),
        )
        connection.commit()
    except sqlite3.IntegrityError:
        connection.rollback()
        raise HTTPException(status_code=409, detail="Ese correo ya tiene una cuenta.") from None
    return {"token": crear_token(user["id"]), "user": usuario_y_moneda(connection, user)}


@app.post("/auth/login")
def iniciar_sesion(data: Credentials, connection: sqlite3.Connection = Depends(obtener_conexion)):
    email = data.email.strip().lower()
    user = connection.execute(
        "SELECT id, correo, contrasena_hash FROM usuarios WHERE correo = ?", (email,)
    ).fetchone()
    if not user or not bcrypt.checkpw(data.password.encode("utf-8"), user["contrasena_hash"]):
        raise HTTPException(status_code=401, detail="Correo o contrasena incorrectos.")
    user_data = dict(user)
    return {"token": crear_token(user_data["id"]),
            "user": usuario_y_moneda(connection, user_data)}


@app.get("/me")
def mi_cuenta(
    user: dict = Depends(usuario_actual),
    connection: sqlite3.Connection = Depends(obtener_conexion),
):
    return usuario_y_moneda(connection, user)


@app.get("/summary")
def resumen(
    user: dict = Depends(usuario_actual),
    connection: sqlite3.Connection = Depends(obtener_conexion),
):
    beginning = date.today().replace(day=1).isoformat()
    totals = connection.execute("""
        SELECT tipo, COALESCE(SUM(monto_centavos), 0) AS total
        FROM movimientos WHERE usuario_id = ? GROUP BY tipo
    """, (user["id"],)).fetchall()
    month_totals = connection.execute("""
        SELECT tipo, COALESCE(SUM(monto_centavos), 0) AS total
        FROM movimientos WHERE usuario_id = ? AND fecha >= ? GROUP BY tipo
    """, (user["id"], beginning)).fetchall()
    totals = {row["tipo"]: row["total"] for row in totals}
    month_totals = {row["tipo"]: row["total"] for row in month_totals}
    income = int(totals.get("ingreso", 0))
    expenses = int(totals.get("gasto", 0))
    return {
        "balance_cents": income - expenses,
        "income_month_cents": int(month_totals.get("ingreso", 0)),
        "expenses_month_cents": int(month_totals.get("gasto", 0)),
    }


@app.get("/movements")
def listar_movimientos(
    user: dict = Depends(usuario_actual),
    connection: sqlite3.Connection = Depends(obtener_conexion),
):
    movements = connection.execute("""
        SELECT id, tipo, descripcion, monto_centavos, fecha, categoria, metodo, notas
        FROM movimientos WHERE usuario_id = ? ORDER BY id DESC LIMIT 200
    """, (user["id"],)).fetchall()
    return [
        {
            "id": row["id"], "kind": row["tipo"], "description": row["descripcion"],
            "amount_cents": row["monto_centavos"], "movement_date": row["fecha"],
            "category": row["categoria"], "method": row["metodo"], "notes": row["notas"],
        }
        for row in movements
    ]


@app.post("/movements", status_code=201)
def crear_movimiento(
    data: NewMovement, user: dict = Depends(usuario_actual),
    connection: sqlite3.Connection = Depends(obtener_conexion),
):
    if data.kind not in ("ingreso", "gasto"):
        raise HTTPException(status_code=422, detail="El tipo debe ser ingreso o gasto.")
    if not data.description.strip() or len(data.description) > 300:
        raise HTTPException(status_code=422, detail="Escribe una descripcion de hasta 300 caracteres.")
    if data.amount_cents <= 0:
        raise HTTPException(status_code=422, detail="El importe debe ser mayor que cero.")
    try:
        movement_date = date.fromisoformat(data.movement_date).isoformat()
    except ValueError:
        raise HTTPException(status_code=422, detail="La fecha debe usar formato AAAA-MM-DD.") from None
    cursor = connection.execute("""
        INSERT INTO movimientos
            (usuario_id, tipo, descripcion, monto_centavos, fecha, categoria, metodo, notas)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        user["id"], data.kind, data.description.strip(), data.amount_cents,
        movement_date, data.category.strip()[:80] or "Otros",
        data.method.strip()[:80] or "Efectivo", data.notes.strip()[:2000],
    ))
    connection.commit()
    return {"id": cursor.lastrowid}