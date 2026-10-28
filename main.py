"""Backend REST del Sistema de Turnos, conforme a spec.md v0.3.0."""

from __future__ import annotations

from collections.abc import AsyncIterator
import json
import os
import re
import sqlite3
import uuid
from contextlib import asynccontextmanager, contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Annotated, Iterator, Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import bcrypt
import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError
from fastapi import Depends, FastAPI, Header, HTTPException, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, ConfigDict, Field, field_validator
from starlette.responses import JSONResponse


DATABASE_PATH = Path(os.environ.get("TURNOS_DB_PATH", "turnos.db"))
TOKEN_SECRET = os.environ.get("TURNOS_TOKEN_SECRET", "")
TOKEN_DURATION = timedelta(minutes=30)
CANCELLATION_WINDOW = timedelta(hours=2)
MINIMUM_LEAD_TIME = timedelta(hours=1)
BOOKING_HORIZON = timedelta(days=60)
GRID_MINUTES = 15
EMAIL_PATTERN = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]{2,}$")
PHONE_PATTERN = re.compile(r"^\+[1-9]\d{7,14}$")
PASSWORD_HASHER = PasswordHasher()

def _database_connection() -> sqlite3.Connection:
    connection = sqlite3.connect(DATABASE_PATH, timeout=30, isolation_level=None)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    connection.execute("PRAGMA busy_timeout = 30000")
    return connection


@contextmanager
def _database() -> Iterator[sqlite3.Connection]:
    connection = _database_connection()
    try:
        yield connection
    finally:
        connection.close()


def _initialize_database() -> None:
    DATABASE_PATH.parent.mkdir(parents=True, exist_ok=True)
    with _database() as connection:
        connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS usuarios (
                id TEXT PRIMARY KEY,
                email TEXT NOT NULL UNIQUE,
                email_verificado INTEGER NOT NULL DEFAULT 0 CHECK (email_verificado IN (0, 1)),
                password_hash TEXT NOT NULL,
                nombre_completo TEXT NOT NULL CHECK (length(nombre_completo) BETWEEN 2 AND 100),
                telefono TEXT NOT NULL,
                rol TEXT NOT NULL CHECK (rol IN ('CLIENTE', 'PROFESIONAL', 'ADMIN')),
                activo INTEGER NOT NULL DEFAULT 1 CHECK (activo IN (0, 1)),
                creado_en TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS servicios (
                id TEXT PRIMARY KEY,
                profesional_id TEXT NOT NULL REFERENCES usuarios(id) ON DELETE RESTRICT,
                nombre TEXT NOT NULL,
                descripcion TEXT,
                duracion_min INTEGER NOT NULL CHECK (
                    duracion_min BETWEEN 15 AND 480 AND duracion_min % 15 = 0
                ),
                precio_referencia NUMERIC NOT NULL CHECK (precio_referencia >= 0),
                activo INTEGER NOT NULL CHECK (activo IN (0, 1))
            );
            CREATE TABLE IF NOT EXISTS turnos (
                id TEXT PRIMARY KEY,
                cliente_id TEXT NOT NULL REFERENCES usuarios(id) ON DELETE RESTRICT,
                profesional_id TEXT NOT NULL REFERENCES usuarios(id) ON DELETE RESTRICT,
                servicio_id TEXT NOT NULL REFERENCES servicios(id) ON DELETE RESTRICT,
                inicio TEXT NOT NULL,
                fin TEXT NOT NULL,
                estado TEXT NOT NULL CHECK (
                    estado IN ('CONFIRMADO', 'CANCELADO', 'COMPLETADO', 'AUSENTE')
                ),
                motivo_cancelacion TEXT,
                cancelado_por_id TEXT REFERENCES usuarios(id) ON DELETE RESTRICT,
                creado_en TEXT NOT NULL,
                actualizado_en TEXT NOT NULL,
                CHECK (inicio < fin)
            );
            CREATE TABLE IF NOT EXISTS horario_laboral (
                id TEXT PRIMARY KEY,
                profesional_id TEXT NOT NULL REFERENCES usuarios(id) ON DELETE RESTRICT,
                dia_semana INTEGER NOT NULL CHECK (dia_semana BETWEEN 0 AND 6),
                hora_inicio TEXT NOT NULL,
                hora_fin TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS bloqueos (
                id TEXT PRIMARY KEY,
                profesional_id TEXT NOT NULL REFERENCES usuarios(id) ON DELETE RESTRICT,
                inicio TEXT NOT NULL,
                fin TEXT NOT NULL,
                motivo TEXT NOT NULL,
                CHECK (inicio < fin)
            );
            CREATE TABLE IF NOT EXISTS auditoria_evento (
                id TEXT PRIMARY KEY,
                entidad TEXT NOT NULL,
                entidad_id TEXT NOT NULL,
                accion TEXT NOT NULL,
                actor_id TEXT NOT NULL REFERENCES usuarios(id) ON DELETE RESTRICT,
                rol TEXT NOT NULL CHECK (rol IN ('CLIENTE', 'PROFESIONAL', 'ADMIN')),
                ocurrido_en TEXT NOT NULL,
                detalle TEXT
            );
            CREATE INDEX IF NOT EXISTS ix_turnos_profesional_intervalo
                ON turnos(profesional_id, estado, inicio, fin);
            CREATE INDEX IF NOT EXISTS ix_turnos_cliente_intervalo
                ON turnos(cliente_id, estado, inicio, fin);
            CREATE INDEX IF NOT EXISTS ix_horario_profesional_dia
                ON horario_laboral(profesional_id, dia_semana);
            CREATE TRIGGER IF NOT EXISTS auditoria_evento_inmutable_update
            BEFORE UPDATE ON auditoria_evento
            BEGIN
                SELECT RAISE(ABORT, 'auditoria_evento es inmutable');
            END;
            CREATE TRIGGER IF NOT EXISTS auditoria_evento_inmutable_delete
            BEFORE DELETE ON auditoria_evento
            BEGIN
                SELECT RAISE(ABORT, 'auditoria_evento es inmutable');
            END;
            """
        )


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    if not TOKEN_SECRET or len(TOKEN_SECRET.encode("utf-8")) < 32:
        raise RuntimeError(
            "TURNOS_TOKEN_SECRET es obligatorio y debe tener al menos 32 bytes."
        )
    try:
        ZoneInfo(os.environ.get("TURNOS_TIMEZONE", "UTC"))
    except ZoneInfoNotFoundError as error:
        raise RuntimeError("TURNOS_TIMEZONE no es una zona horaria IANA válida.") from error
    _initialize_database()
    yield


app = FastAPI(
    title="Sistema de Turnos API",
    description="API REST conforme a spec.md v0.3.0.",
    version="0.3.0",
    lifespan=lifespan,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(RequestValidationError)
async def invalid_request_handler(
    _: Request,
    error: RequestValidationError,
) -> JSONResponse:
    return JSONResponse(
        status_code=422,
        content={
            "detail": {
                "code": "INVALID_REQUEST",
                "message": "La solicitud no cumple el contrato del endpoint.",
                "errors": [
                    {
                        "field": ".".join(str(part) for part in item["loc"]),
                        "message": item["msg"],
                    }
                    for item in error.errors()
                ],
            }
        },
    )


class LoginRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    email: str
    password: str

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: str) -> str:
        normalized = value.strip().lower()
        if not EMAIL_PATTERN.fullmatch(normalized):
            raise ValueError("email inválido")
        return normalized


class LoginResponse(BaseModel):
    access_token: str
    token_type: Literal["Bearer"] = "Bearer"
    expires_in: int


class BookingRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    profesional_id: uuid.UUID
    servicio_id: uuid.UUID
    inicio: datetime
    cliente_id: uuid.UUID | None = None


class CancellationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    motivo_cancelacion: Annotated[str, Field(min_length=1, max_length=2000)] | None = None


class TurnoResponse(BaseModel):
    id: uuid.UUID
    cliente_id: uuid.UUID
    profesional_id: uuid.UUID
    servicio_id: uuid.UUID
    inicio: datetime
    fin: datetime
    estado: Literal["CONFIRMADO", "CANCELADO", "COMPLETADO", "AUSENTE"]
    motivo_cancelacion: str | None
    cancelado_por_id: uuid.UUID | None
    creado_en: datetime
    actualizado_en: datetime


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _to_utc_text(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat(timespec="microseconds")


def _from_db_datetime(value: str) -> datetime:
    return datetime.fromisoformat(value).astimezone(timezone.utc)


def _raise_domain_error(
    code: str,
    http_status: int,
    message: str,
) -> None:
    raise HTTPException(
        status_code=http_status,
        detail={"code": code, "message": message},
    )


def _create_access_token(user_id: str) -> str:
    issued_at = _utc_now()
    return jwt.encode(
        {"sub": user_id, "exp": issued_at + TOKEN_DURATION},
        TOKEN_SECRET,
        algorithm="HS256",
    )


def _decode_access_token(token: str) -> str:
    try:
        payload = jwt.decode(
            token,
            TOKEN_SECRET,
            algorithms=["HS256"],
            options={"require": ["sub", "exp"]},
        )
        subject = payload["sub"]
        uuid.UUID(subject)
        return subject
    except (jwt.InvalidTokenError, ValueError, KeyError, TypeError) as error:
        raise ValueError("token inválido") from error


def _verify_password(plain_password: str, password_hash: str) -> bool:
    encoded_hash = password_hash.encode("utf-8")
    if password_hash.startswith("$argon2"):
        try:
            return PASSWORD_HASHER.verify(password_hash, plain_password)
        except (VerificationError, VerifyMismatchError, InvalidHashError, ValueError):
            return False
    if password_hash.startswith(("$2a$", "$2b$", "$2y$")):
        try:
            return bcrypt.checkpw(plain_password.encode("utf-8"), encoded_hash)
        except ValueError:
            return False
    return False


def _authenticated_user(
    authorization: Annotated[str | None, Header()] = None,
) -> dict[str, str]:
    if authorization is None or not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=401,
            detail={"code": "UNAUTHORIZED", "message": "Se requiere un token Bearer válido."},
            headers={"WWW-Authenticate": "Bearer"},
        )
    try:
        user_id = _decode_access_token(authorization[7:])
    except ValueError:
        raise HTTPException(
            status_code=401,
            detail={"code": "UNAUTHORIZED", "message": "El token no es válido o expiró."},
            headers={"WWW-Authenticate": "Bearer"},
        ) from None

    with _database() as connection:
        user = connection.execute(
            "SELECT id, rol, activo FROM usuarios WHERE id = ?",
            (user_id,),
        ).fetchone()
    if user is None or not user["activo"]:
        raise HTTPException(
            status_code=401,
            detail={"code": "UNAUTHORIZED", "message": "El usuario no está activo."},
            headers={"WWW-Authenticate": "Bearer"},
        )
    return {"id": user["id"], "rol": user["rol"]}


AuthenticatedUser = Annotated[dict[str, str], Depends(_authenticated_user)]


def _audit(
    connection: sqlite3.Connection,
    *,
    entity: str,
    entity_id: str,
    action: str,
    actor: dict[str, str],
    occurred_at: datetime,
    detail: str | None,
) -> None:
    connection.execute(
        """
        INSERT INTO auditoria_evento
            (id, entidad, entidad_id, accion, actor_id, rol, ocurrido_en, detalle)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            str(uuid.uuid4()),
            entity,
            entity_id,
            action,
            actor["id"],
            actor["rol"],
            _to_utc_text(occurred_at),
            detail,
        ),
    )


def _turno_response(row: sqlite3.Row) -> TurnoResponse:
    return TurnoResponse(
        id=uuid.UUID(row["id"]),
        cliente_id=uuid.UUID(row["cliente_id"]),
        profesional_id=uuid.UUID(row["profesional_id"]),
        servicio_id=uuid.UUID(row["servicio_id"]),
        inicio=_from_db_datetime(row["inicio"]),
        fin=_from_db_datetime(row["fin"]),
        estado=row["estado"],
        motivo_cancelacion=row["motivo_cancelacion"],
        cancelado_por_id=(
            uuid.UUID(row["cancelado_por_id"]) if row["cancelado_por_id"] else None
        ),
        creado_en=_from_db_datetime(row["creado_en"]),
        actualizado_en=_from_db_datetime(row["actualizado_en"]),
    )


def _check_booking_time(
    start_utc: datetime,
    duration_minutes: int,
    professional_id: str,
    connection: sqlite3.Connection,
) -> datetime:
    now = _utc_now()
    if start_utc < now + MINIMUM_LEAD_TIME or start_utc > now + BOOKING_HORIZON:
        _raise_domain_error(
            "INVALID_TIME_RANGE",
            422,
            "El inicio debe respetar la antelación mínima y el horizonte de 60 días.",
        )

    operation_zone = ZoneInfo(os.environ.get("TURNOS_TIMEZONE", "UTC"))
    local_start = start_utc.astimezone(operation_zone)
    if (
        local_start.second
        or local_start.microsecond
        or local_start.minute % GRID_MINUTES
    ):
        _raise_domain_error(
            "INVALID_TIME_RANGE",
            422,
            "El inicio debe estar alineado a la grilla de 15 minutos.",
        )

    end_utc = start_utc + timedelta(minutes=duration_minutes)
    schedules = connection.execute(
        """
        SELECT hora_inicio, hora_fin
        FROM horario_laboral
        WHERE profesional_id = ? AND dia_semana = ?
        """,
        (professional_id, local_start.weekday()),
    ).fetchall()
    local_end = end_utc.astimezone(operation_zone)
    starts_at = local_start.hour * 60 + local_start.minute
    ends_at = local_end.hour * 60 + local_end.minute
    is_scheduled = any(
        starts_at >= _clock_minutes(schedule["hora_inicio"])
        and ends_at <= _clock_minutes(schedule["hora_fin"])
        and local_start.date() == local_end.date()
        for schedule in schedules
    )
    if not is_scheduled:
        _raise_domain_error(
            "SLOT_UNAVAILABLE",
            409,
            "El horario está fuera de la jornada laboral del profesional.",
        )

    blocks = connection.execute(
        """
        SELECT 1 FROM bloqueos
        WHERE profesional_id = ? AND inicio < ? AND fin > ?
        LIMIT 1
        """,
        (professional_id, _to_utc_text(end_utc), _to_utc_text(start_utc)),
    ).fetchone()
    if blocks is not None:
        _raise_domain_error(
            "SLOT_UNAVAILABLE",
            409,
            "El horario se solapa con un bloqueo.",
        )
    return end_utc


def _clock_minutes(value: str) -> int:
    hour, minute = (int(part) for part in value.split(":"))
    return hour * 60 + minute


@app.post(
    "/api/auth/login",
    response_model=LoginResponse,
    tags=["Autenticación"],
)
def login(request: LoginRequest) -> LoginResponse:
    with _database() as connection:
        user = connection.execute(
            """
            SELECT id, password_hash, activo
            FROM usuarios
            WHERE email = ?
            """,
            (request.email,),
        ).fetchone()
    if user is None or not user["activo"] or not _verify_password(
        request.password, user["password_hash"]
    ):
        _raise_domain_error(
            "INVALID_CREDENTIALS",
            401,
            "Email o contraseña incorrectos.",
        )
    return LoginResponse(
        access_token=_create_access_token(user["id"]),
        expires_in=int(TOKEN_DURATION.total_seconds()),
    )


@app.get(
    "/api/turnos",
    response_model=list[TurnoResponse],
    tags=["Turnos"],
)
def list_turnos(actor: AuthenticatedUser) -> list[TurnoResponse]:
    query = "SELECT * FROM turnos"
    parameters: tuple[str, ...] = ()
    if actor["rol"] == "CLIENTE":
        query += " WHERE cliente_id = ?"
        parameters = (actor["id"],)
    elif actor["rol"] == "PROFESIONAL":
        query += " WHERE profesional_id = ?"
        parameters = (actor["id"],)
    query += " ORDER BY inicio, id"
    with _database() as connection:
        rows = connection.execute(query, parameters).fetchall()
    return [_turno_response(row) for row in rows]


@app.post(
    "/api/turnos",
    response_model=TurnoResponse,
    status_code=status.HTTP_201_CREATED,
    tags=["Turnos"],
)
def create_turno(
    request: BookingRequest,
    actor: AuthenticatedUser,
) -> TurnoResponse:
    if actor["rol"] not in ("CLIENTE", "ADMIN"):
        _raise_domain_error("FORBIDDEN", 403, "El rol no puede crear reservas.")
    if actor["rol"] == "CLIENTE" and request.cliente_id is not None:
        _raise_domain_error(
            "FORBIDDEN",
            403,
            "El cliente autenticado no puede indicar otro cliente_id.",
        )
    if actor["rol"] == "ADMIN" and request.cliente_id is None:
        _raise_domain_error(
            "INVALID_REQUEST",
            422,
            "Un Administrador debe indicar cliente_id.",
        )

    if request.inicio.tzinfo is None or request.inicio.utcoffset() is None:
        _raise_domain_error(
            "INVALID_TIME_RANGE",
            422,
            "inicio debe incluir una zona horaria.",
        )
    start_utc = request.inicio.astimezone(timezone.utc)
    client_id = str(request.cliente_id or uuid.UUID(actor["id"]))
    professional_id = str(request.profesional_id)
    service_id = str(request.servicio_id)
    now = _utc_now()

    connection = _database_connection()
    try:
        connection.execute("BEGIN IMMEDIATE")
        client = connection.execute(
            """
            SELECT id, email, email_verificado, nombre_completo, telefono, rol, activo
            FROM usuarios WHERE id = ?
            """,
            (client_id,),
        ).fetchone()
        professional = connection.execute(
            "SELECT id, rol, activo FROM usuarios WHERE id = ?",
            (professional_id,),
        ).fetchone()
        service = connection.execute(
            """
            SELECT id, profesional_id, duracion_min, activo
            FROM servicios WHERE id = ?
            """,
            (service_id,),
        ).fetchone()
        if (
            client is None
            or client["rol"] != "CLIENTE"
            or not client["activo"]
            or professional is None
            or professional["rol"] != "PROFESIONAL"
            or not professional["activo"]
            or service is None
            or not service["activo"]
            or service["profesional_id"] != professional_id
        ):
            _raise_domain_error("NOT_FOUND", 404, "El cliente, profesional o servicio no existe.")

        normalized_email = client["email"].strip().lower()
        normalized_phone = re.sub(r"[\s().-]", "", client["telefono"])
        if (
            len(client["nombre_completo"].strip()) < 2
            or len(client["nombre_completo"].strip()) > 100
            or not EMAIL_PATTERN.fullmatch(normalized_email)
            or not PHONE_PATTERN.fullmatch(normalized_phone)
        ):
            _raise_domain_error(
                "INVALID_CONTACT",
                422,
                "El perfil del cliente tiene datos de contacto inválidos.",
            )
        if not client["email_verificado"]:
            _raise_domain_error(
                "EMAIL_NOT_VERIFIED",
                403,
                "El email del cliente debe estar verificado.",
            )

        end_utc = _check_booking_time(
            start_utc,
            service["duracion_min"],
            professional_id,
            connection,
        )
        overlap = connection.execute(
            """
            SELECT 1 FROM turnos
            WHERE estado = 'CONFIRMADO'
              AND inicio < ?
              AND fin > ?
              AND (profesional_id = ? OR cliente_id = ?)
            LIMIT 1
            """,
            (
                _to_utc_text(end_utc),
                _to_utc_text(start_utc),
                professional_id,
                client_id,
            ),
        ).fetchone()
        if overlap is not None:
            _raise_domain_error(
                "SLOT_UNAVAILABLE",
                409,
                "El horario solicitado no está disponible.",
            )

        turno_id = str(uuid.uuid4())
        connection.execute(
            """
            INSERT INTO turnos (
                id, cliente_id, profesional_id, servicio_id, inicio, fin, estado,
                motivo_cancelacion, cancelado_por_id, creado_en, actualizado_en
            ) VALUES (?, ?, ?, ?, ?, ?, 'CONFIRMADO', NULL, NULL, ?, ?)
            """,
            (
                turno_id,
                client_id,
                professional_id,
                service_id,
                _to_utc_text(start_utc),
                _to_utc_text(end_utc),
                _to_utc_text(now),
                _to_utc_text(now),
            ),
        )
        _audit(
            connection,
            entity="Turno",
            entity_id=turno_id,
            action="CREADO",
            actor=actor,
            occurred_at=now,
            detail=json.dumps(
                {"cliente_id": client_id, "servicio_id": service_id},
                separators=(",", ":"),
            ),
        )
        row = connection.execute(
            "SELECT * FROM turnos WHERE id = ?", (turno_id,)
        ).fetchone()
        connection.commit()
        return _turno_response(row)
    finally:
        if connection.in_transaction:
            connection.rollback()
        connection.close()


@app.post(
    "/api/turnos/{turno_id}/cancelar",
    response_model=TurnoResponse,
    tags=["Turnos"],
)
def cancel_turno(
    turno_id: uuid.UUID,
    actor: AuthenticatedUser,
    request: CancellationRequest | None = None,
) -> TurnoResponse:
    now = _utc_now()
    reason = (request.motivo_cancelacion or "").strip() if request else ""
    connection = _database_connection()
    try:
        connection.execute("BEGIN IMMEDIATE")
        row = connection.execute(
            "SELECT * FROM turnos WHERE id = ?", (str(turno_id),)
        ).fetchone()
        if row is None:
            _raise_domain_error("NOT_FOUND", 404, "El turno no existe.")
        if actor["rol"] == "CLIENTE" and row["cliente_id"] != actor["id"]:
            _raise_domain_error("NOT_FOUND", 404, "El turno no existe.")
        if actor["rol"] == "PROFESIONAL" and row["profesional_id"] != actor["id"]:
            _raise_domain_error("NOT_FOUND", 404, "El turno no existe.")
        if row["estado"] != "CONFIRMADO":
            _raise_domain_error(
                "INVALID_STATE_TRANSITION",
                409,
                "El turno no está en estado CONFIRMADO.",
            )
        if actor["rol"] == "CLIENTE":
            if _from_db_datetime(row["inicio"]) - now < CANCELLATION_WINDOW:
                _raise_domain_error(
                    "CANCELLATION_WINDOW_EXPIRED",
                    409,
                    "No se puede cancelar con menos de 2 horas de antelación.",
                )
            reason_value = None
        elif actor["rol"] in ("PROFESIONAL", "ADMIN"):
            if not reason:
                _raise_domain_error(
                    "REASON_REQUIRED",
                    422,
                    "El motivo de cancelación es obligatorio.",
                )
            reason_value = reason
        else:
            _raise_domain_error("FORBIDDEN", 403, "El rol no puede cancelar turnos.")

        connection.execute(
            """
            UPDATE turnos
            SET estado = 'CANCELADO', motivo_cancelacion = ?,
                cancelado_por_id = ?, actualizado_en = ?
            WHERE id = ? AND estado = 'CONFIRMADO'
            """,
            (reason_value, actor["id"], _to_utc_text(now), str(turno_id)),
        )
        detail = reason_value or "Cancelación solicitada por el Cliente."
        _audit(
            connection,
            entity="Turno",
            entity_id=str(turno_id),
            action="CANCELADO",
            actor=actor,
            occurred_at=now,
            detail=detail,
        )
        updated = connection.execute(
            "SELECT * FROM turnos WHERE id = ?", (str(turno_id),)
        ).fetchone()
        connection.commit()
        return _turno_response(updated)
    finally:
        if connection.in_transaction:
            connection.rollback()
        connection.close()
