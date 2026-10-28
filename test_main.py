from __future__ import annotations

import uuid
import sqlite3
from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from datetime import datetime, timedelta, timezone
from threading import Barrier
from typing import TypedDict

import pytest
from fastapi.testclient import TestClient

import main


class ApiContext(TypedDict):
    client: TestClient
    tokens: dict[str, str]
    users: dict[str, tuple[str, str, str]]
    service_id: str
    database_path: Path


@pytest.fixture
def api(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> Iterator[ApiContext]:
    database_path = tmp_path / "turnos-test.db"
    monkeypatch.setattr(main, "DATABASE_PATH", database_path)
    monkeypatch.setattr(main, "TOKEN_SECRET", "test-secret-with-more-than-thirty-two-bytes")
    monkeypatch.setenv("TURNOS_TIMEZONE", "UTC")

    users = {
        "cliente": (str(uuid.uuid4()), "cliente@example.com", "CLIENTE"),
        "cliente2": (str(uuid.uuid4()), "cliente2@example.com", "CLIENTE"),
        "profesional": (str(uuid.uuid4()), "profesional@example.com", "PROFESIONAL"),
        "admin": (str(uuid.uuid4()), "admin@example.com", "ADMIN"),
    }
    service_id = str(uuid.uuid4())
    with TestClient(main.app) as client:
        now = main._to_utc_text(datetime.now(timezone.utc))
        with main._database() as connection:
            for name, (user_id, email, role) in users.items():
                connection.execute(
                    """
                    INSERT INTO usuarios (
                        id, email, email_verificado, password_hash, nombre_completo,
                        telefono, rol, activo, creado_en
                    ) VALUES (?, ?, 1, ?, ?, ?, ?, 1, ?)
                    """,
                    (
                        user_id,
                        email,
                        main.PASSWORD_HASHER.hash("correct-horse-battery"),
                        f"Nombre {name}",
                        "+5491155550101",
                        role,
                        now,
                    ),
                )
            connection.execute(
                """
                INSERT INTO servicios (
                    id, profesional_id, nombre, descripcion, duracion_min,
                    precio_referencia, activo
                ) VALUES (?, ?, 'Consulta', NULL, 30, 0, 1)
                """,
                (service_id, users["profesional"][0]),
            )
            for weekday in range(7):
                connection.execute(
                    """
                    INSERT INTO horario_laboral
                        (id, profesional_id, dia_semana, hora_inicio, hora_fin)
                    VALUES (?, ?, ?, '00:00', '23:59')
                    """,
                    (str(uuid.uuid4()), users["profesional"][0], weekday),
                )

        tokens: dict[str, str] = {}
        for name, (_, email, _) in users.items():
            result = client.post(
                "/api/auth/login",
                json={"email": email.upper(), "password": "correct-horse-battery"},
            )
            assert result.status_code == 200
            tokens[name] = result.json()["access_token"]
        yield ApiContext(
            client=client,
            tokens=tokens,
            users=users,
            service_id=service_id,
            database_path=database_path,
        )


def _booking_start() -> datetime:
    current = datetime.now(timezone.utc)
    return current.replace(hour=10, minute=0, second=0, microsecond=0) + timedelta(days=2)


def _booking_payload(api: ApiContext, start: datetime) -> dict[str, str]:
    users = api["users"]
    service_id = api["service_id"]
    return {
        "profesional_id": users["profesional"][0],
        "servicio_id": service_id,
        "inicio": start.isoformat(),
    }


def _headers(api: ApiContext, role: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {api['tokens'][role]}"}


def test_login_docs_and_protected_listing(api: ApiContext) -> None:
    client = api["client"]
    assert client.get("/docs").status_code == 200

    unauthenticated = client.get("/api/turnos")
    assert unauthenticated.status_code == 401
    assert unauthenticated.json()["detail"]["code"] == "UNAUTHORIZED"

    login = client.post(
        "/api/auth/login",
        json={"email": "cliente@example.com", "password": "wrong-password"},
    )
    assert login.status_code == 401
    assert login.json()["detail"]["code"] == "INVALID_CREDENTIALS"

    payload = _booking_payload(api, _booking_start())
    extra_field = client.post(
        "/api/turnos",
        json={**payload, "unexpected": "field"},
        headers=_headers(api, "cliente"),
    )
    assert extra_field.status_code == 422
    assert extra_field.json()["detail"]["code"] == "INVALID_REQUEST"

    professional_forbidden = client.post(
        "/api/turnos", json=payload, headers=_headers(api, "profesional")
    )
    assert professional_forbidden.status_code == 403
    assert professional_forbidden.json()["detail"]["code"] == "FORBIDDEN"

    admin_missing_client = client.post(
        "/api/turnos", json=payload, headers=_headers(api, "admin")
    )
    assert admin_missing_client.status_code == 422
    assert admin_missing_client.json()["detail"]["code"] == "INVALID_REQUEST"


def test_booking_overlap_is_rejected_and_contiguous_slot_is_allowed(
    api: ApiContext,
) -> None:
    client = api["client"]
    start = _booking_start()
    payload = _booking_payload(api, start)
    first = client.post(
        "/api/turnos", json=payload, headers=_headers(api, "cliente")
    )
    assert first.status_code == 201

    overlap = client.post(
        "/api/turnos",
        json=_booking_payload(api, start),
        headers=_headers(api, "cliente2"),
    )
    assert overlap.status_code == 409
    assert overlap.json()["detail"]["code"] == "SLOT_UNAVAILABLE"

    adjacent = client.post(
        "/api/turnos",
        json=_booking_payload(api, start + timedelta(minutes=30)),
        headers=_headers(api, "cliente"),
    )
    assert adjacent.status_code == 201

    own_turnos = client.get("/api/turnos", headers=_headers(api, "cliente"))
    all_turnos = client.get("/api/turnos", headers=_headers(api, "admin"))
    assert len(own_turnos.json()) == 2
    assert len(all_turnos.json()) == 2


def test_concurrent_reservations_confirm_exactly_one(api: ApiContext) -> None:
    client = api["client"]
    start = _booking_start()
    barrier = Barrier(2)
    payloads = [
        _booking_payload(api, start),
        _booking_payload(api, start),
    ]

    def reserve(payload: dict[str, str], role: str) -> int:
        barrier.wait()
        return client.post(
            "/api/turnos", json=payload, headers=_headers(api, role)
        ).status_code

    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = [
            executor.submit(reserve, payloads[0], "cliente"),
            executor.submit(reserve, payloads[1], "cliente2"),
        ]
    assert sorted(future.result() for future in futures) == [201, 409]


def test_booking_validation_and_wildcard_cors(api: ApiContext) -> None:
    client = api["client"]
    start = _booking_start()
    payload = _booking_payload(api, start)
    cliente_id = api["users"]["cliente"][0]

    with main._database() as connection:
        connection.execute(
            "UPDATE usuarios SET email_verificado = 0 WHERE id = ?",
            (cliente_id,),
        )
    unverified = client.post(
        "/api/turnos", json=payload, headers=_headers(api, "cliente")
    )
    assert unverified.status_code == 403
    assert unverified.json()["detail"]["code"] == "EMAIL_NOT_VERIFIED"

    with main._database() as connection:
        connection.execute(
            "UPDATE usuarios SET email_verificado = 1, telefono = 'invalid' WHERE id = ?",
            (cliente_id,),
        )
    invalid_contact = client.post(
        "/api/turnos", json=payload, headers=_headers(api, "cliente")
    )
    assert invalid_contact.status_code == 422
    assert invalid_contact.json()["detail"]["code"] == "INVALID_CONTACT"

    with main._database() as connection:
        connection.execute(
            "UPDATE usuarios SET telefono = '+5491155550101' WHERE id = ?",
            (cliente_id,),
        )
    naive_datetime = dict(payload)
    naive_datetime["inicio"] = start.replace(tzinfo=None).isoformat()
    invalid_time = client.post(
        "/api/turnos", json=naive_datetime, headers=_headers(api, "cliente")
    )
    assert invalid_time.status_code == 422
    assert invalid_time.json()["detail"]["code"] == "INVALID_TIME_RANGE"

    preflight = client.options(
        "/api/turnos",
        headers={
            "Origin": "http://localhost:5173",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "authorization,content-type",
        },
    )
    assert preflight.status_code == 200
    assert preflight.headers["access-control-allow-origin"] == "*"


def test_professional_cancellation_requires_reason_and_is_audited(
    api: ApiContext,
) -> None:
    client = api["client"]
    booked = client.post(
        "/api/turnos",
        json=_booking_payload(api, _booking_start()),
        headers=_headers(api, "cliente"),
    )
    turno_id = booked.json()["id"]
    soon = datetime.now(timezone.utc) + timedelta(minutes=90)
    with main._database() as connection:
        connection.execute(
            "UPDATE turnos SET inicio = ?, fin = ? WHERE id = ?",
            (
                main._to_utc_text(soon),
                main._to_utc_text(soon + timedelta(minutes=30)),
                turno_id,
            ),
        )

    no_reason = client.post(
        f"/api/turnos/{turno_id}/cancelar",
        headers=_headers(api, "profesional"),
    )
    assert no_reason.status_code == 422
    assert no_reason.json()["detail"]["code"] == "REASON_REQUIRED"

    cancelled = client.post(
        f"/api/turnos/{turno_id}/cancelar",
        json={"motivo_cancelacion": "Cierre del consultorio"},
        headers=_headers(api, "profesional"),
    )
    assert cancelled.status_code == 200
    assert cancelled.json()["estado"] == "CANCELADO"
    assert cancelled.json()["motivo_cancelacion"] == "Cierre del consultorio"

    repeated = client.post(
        f"/api/turnos/{turno_id}/cancelar",
        headers=_headers(api, "cliente"),
    )
    assert repeated.status_code == 409
    assert repeated.json()["detail"]["code"] == "INVALID_STATE_TRANSITION"

    with main._database() as connection:
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                "UPDATE auditoria_evento SET detalle = 'alterado' WHERE entidad_id = ?",
                (turno_id,),
            )


def test_cancel_window_audit_and_persistence(api: ApiContext) -> None:
    client = api["client"]
    start = _booking_start()
    booked = client.post(
        "/api/turnos",
        json=_booking_payload(api, start),
        headers=_headers(api, "cliente"),
    )
    assert booked.status_code == 201
    turno_id = booked.json()["id"]

    soon = datetime.now(timezone.utc) + timedelta(minutes=90)
    with main._database() as connection:
        connection.execute(
            """
            UPDATE turnos SET inicio = ?, fin = ?
            WHERE id = ?
            """,
            (
                main._to_utc_text(soon),
                main._to_utc_text(soon + timedelta(minutes=30)),
                turno_id,
            ),
        )
    refused = client.post(
        f"/api/turnos/{turno_id}/cancelar",
        headers=_headers(api, "cliente"),
    )
    assert refused.status_code == 409
    assert refused.json()["detail"]["code"] == "CANCELLATION_WINDOW_EXPIRED"

    with main._database() as connection:
        connection.execute(
            "UPDATE turnos SET inicio = ?, fin = ? WHERE id = ?",
            (
                main._to_utc_text(start),
                main._to_utc_text(start + timedelta(minutes=30)),
                turno_id,
            ),
        )
    cancelled = client.post(
        f"/api/turnos/{turno_id}/cancelar",
        headers=_headers(api, "cliente"),
    )
    assert cancelled.status_code == 200
    assert cancelled.json()["estado"] == "CANCELADO"
    with main._database() as connection:
        assert connection.execute(
            "SELECT count(*) FROM auditoria_evento WHERE entidad_id = ?",
            (turno_id,),
        ).fetchone()[0] == 2
        columns = {
            row["name"]
            for row in connection.execute("PRAGMA table_info(turnos)").fetchall()
        }
    assert columns == {
        "id",
        "cliente_id",
        "profesional_id",
        "servicio_id",
        "inicio",
        "fin",
        "estado",
        "motivo_cancelacion",
        "cancelado_por_id",
        "creado_en",
        "actualizado_en",
    }

    with TestClient(main.app) as restarted_client:
        listed = restarted_client.get(
            "/api/turnos", headers=_headers(api, "cliente")
        )
    assert listed.status_code == 200
    assert listed.json()[0]["estado"] == "CANCELADO"


def test_client_cannot_cancel_another_clients_appointment(api: ApiContext) -> None:
    client = api["client"]
    booked = client.post(
        "/api/turnos",
        json=_booking_payload(api, _booking_start()),
        headers=_headers(api, "cliente"),
    )
    result = client.post(
        f"/api/turnos/{booked.json()['id']}/cancelar",
        headers=_headers(api, "cliente2"),
    )
    assert result.status_code == 404
    assert result.json()["detail"]["code"] == "NOT_FOUND"
