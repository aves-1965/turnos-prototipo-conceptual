"""Crea datos de demostración locales para probar la API."""

from __future__ import annotations

import argparse
import secrets
import uuid
from datetime import datetime, timezone

import main


INITIAL_DEMO_USERS = (
    ("cliente.demo@example.test", "Cliente de demostración", "CLIENTE"),
    ("cliente2.demo@example.test", "Segundo cliente de demostración", "CLIENTE"),
    ("profesional.demo@example.test", "Profesional de demostración", "PROFESIONAL"),
    ("admin.demo@example.test", "Administrador de demostración", "ADMIN"),
)


def seed_demo_data() -> None:
    main._initialize_database()
    now = main._to_utc_text(datetime.now(timezone.utc))
    password = secrets.token_urlsafe(24)
    user_ids = {
        role + str(index): str(uuid.uuid4())
        for index, (_, _, role) in enumerate(INITIAL_DEMO_USERS)
    }
    service_id = str(uuid.uuid4())

    with main._database() as connection:
        connection.execute("BEGIN IMMEDIATE")
        for table in (
            "usuarios",
            "servicios",
            "turnos",
            "horario_laboral",
            "bloqueos",
            "auditoria_evento",
        ):
            count = connection.execute(f"SELECT count(*) FROM {table}").fetchone()[0]
            if count:
                connection.rollback()
                raise RuntimeError(
                    f"La base de datos ya contiene registros en {table}; "
                    "no se cargaron datos demo para evitar mezclar o reemplazar datos."
                )

        for index, (email, name, role) in enumerate(INITIAL_DEMO_USERS):
            user_id = user_ids[role + str(index)]
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
                    main.PASSWORD_HASHER.hash(password),
                    name,
                    "+5491100000000",
                    role,
                    now,
                ),
            )

        professional_id = user_ids["PROFESIONAL2"]
        connection.execute(
            """
            INSERT INTO servicios (
                id, profesional_id, nombre, descripcion, duracion_min,
                precio_referencia, activo
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                service_id,
                professional_id,
                "Consulta de demostración",
                "Servicio de prueba para las reservas de la API.",
                30,
                0,
                1,
            ),
        )

        for weekday in range(5):
            connection.execute(
                """
                INSERT INTO horario_laboral (
                    id, profesional_id, dia_semana, hora_inicio, hora_fin
                ) VALUES (?, ?, ?, ?, ?)
                """,
                (str(uuid.uuid4()), professional_id, weekday, "09:00", "17:00"),
            )
        connection.commit()

    print("Datos demo creados. La misma contraseña aleatoria sirve para estas cuentas:")
    print(f"Contraseña: {password}")
    for email, _, role in INITIAL_DEMO_USERS:
        print(f"{role}: {email}")
    print(f"profesional_id: {professional_id}")
    print(f"servicio_id: {service_id}")
    print(f"cliente_id: {user_ids['CLIENTE0']}")
    print(f"cliente2_id: {user_ids['CLIENTE1']}")
    print("\nGuardá la contraseña en un lugar seguro: no se volverá a mostrar.")


def add_demo_clients(amount: int) -> None:
    if amount < 1:
        raise ValueError("La cantidad de clientes adicionales debe ser mayor que cero.")

    password = secrets.token_urlsafe(24)
    now = main._to_utc_text(datetime.now(timezone.utc))
    added: list[tuple[str, str]] = []
    with main._database() as connection:
        connection.execute("BEGIN IMMEDIATE")
        for index in range(amount):
            suffix = 3 + index
            email = f"cliente{suffix}.demo@example.test"
            while connection.execute(
                "SELECT 1 FROM usuarios WHERE email = ?", (email,)
            ).fetchone():
                suffix += amount
                email = f"cliente{suffix}.demo@example.test"
            user_id = str(uuid.uuid4())
            connection.execute(
                """
                INSERT INTO usuarios (
                    id, email, email_verificado, password_hash, nombre_completo,
                    telefono, rol, activo, creado_en
                ) VALUES (?, ?, 1, ?, ?, ?, 'CLIENTE', 1, ?)
                """,
                (
                    user_id,
                    email,
                    main.PASSWORD_HASHER.hash(password),
                    f"Cliente demo {suffix}",
                    "+5491100000000",
                    now,
                ),
            )
            added.append((email, user_id))
        connection.commit()

    print(f"Se agregaron {len(added)} cliente(s) demo. Contraseña para este lote:")
    print(f"Contraseña: {password}")
    for email, user_id in added:
        print(f"CLIENTE: {email} (cliente_id: {user_id})")
    print("\nGuardá la contraseña en un lugar seguro: no se volverá a mostrar.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--more-clients",
        type=int,
        metavar="CANTIDAD",
        help="agrega clientes a la base existente sin modificar los demás datos",
    )
    arguments = parser.parse_args()
    if arguments.more_clients is None:
        seed_demo_data()
    else:
        add_demo_clients(arguments.more_clients)
