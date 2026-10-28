# Guía práctica: probar la API en Swagger

Esta guía acompaña la API local del Sistema de Turnos. Swagger permite enviar solicitudes al backend desde el navegador y ver la respuesta sin instalar una herramienta adicional.

## 1. Iniciar el servidor

Abrí una terminal en la carpeta del proyecto. Ejecutá los comandos en orden:

```bash
# Paso 1: crea .venv, un entorno aislado para las herramientas de este proyecto.
python -m venv .venv

# Paso 2: instala FastAPI, Uvicorn y las demás dependencias dentro de .venv.
.venv/bin/python -m pip install -r requirements.txt

# Paso 3: prepara la variable que el backend necesita para firmar los tokens de sesión.
export TURNOS_TOKEN_SECRET="$(openssl rand -hex 32)"

# Paso 4: inicia el servidor local en el puerto 8000 y recarga el código cuando lo editás.
.venv/bin/uvicorn main:app --reload --host 127.0.0.1 --port 8000
```

### Qué hace cada paso

1. **Crear el entorno virtual:** separa las dependencias de este proyecto de las de otros proyectos o de Python del sistema. Se hace una sola vez. Si `.venv` ya existe, no hace falta volver a crearla.
2. **Instalar las dependencias:** descarga los paquetes declarados en `requirements.txt` dentro del entorno. Se hace la primera vez y se repite cuando cambian esas dependencias.
3. **Preparar la variable:** genera un valor aleatorio que el backend utiliza para firmar los tokens Bearer del login. La variable queda disponible en esta terminal, por eso, si abrís otra, tenés que definirla de nuevo.
4. **Iniciar Uvicorn:** levanta FastAPI en `127.0.0.1:8000`. La opción `--reload` reinicia el servidor cuando se modifica el código. Dejá esta terminal abierta mientras probás.

Para una sesión posterior en la misma máquina, normalmente basta con abrir una terminal, volver a definir `TURNOS_TOKEN_SECRET` (paso 3) y ejecutar Uvicorn (paso 4). Como el secreto nuevo es distinto, volvé a iniciar sesión en Swagger para obtener un token válido. Para detener el servidor, volvé a la terminal de Uvicorn y presioná **Ctrl+C**.

## 2. Cargar usuarios y datos de prueba

El backend crea las tablas de SQLite al iniciarse, pero no crea usuarios. Swagger no puede iniciar sesión mientras no existan usuarios en la base.

### Primera carga demo

Antes de arrancar Uvicorn por primera vez, ejecutá este comando en la carpeta del proyecto, después de los pasos 1–3:

```bash
./.venv/bin/python seed_demo.py
```

El script carga cuatro usuarios (dos clientes, un profesional y un administrador), un servicio de 30 minutos y un horario laboral de lunes a viernes de 09:00 a 17:00. Al final imprime una contraseña aleatoria compartida por las cuatro cuentas, sus emails y los identificadores del profesional, el servicio y los clientes. **Guardá esa salida**: la contraseña solo se muestra en ese momento.

Si la primera carga todavía no se hizo, corré el script y luego el paso 4 para iniciar el servidor. Si el servidor ya está en ejecución, podés cargar la base desde una segunda terminal en la misma carpeta; Uvicorn detectará el cambio en `turnos.db`.

El script inicial se ejecuta solamente sobre una base vacía: si detecta registros existentes, se detiene sin borrarlos ni mezclarlos. Para añadir clientes a una base demo existente, ejecutá:

```bash
./.venv/bin/python seed_demo.py --more-clients 2
```

El número indica cuántas cuentas nuevas crear. El script elige emails demo disponibles, conserva los datos actuales y muestra una contraseña nueva compartida solo por ese lote, junto con los IDs de los nuevos clientes. No repitas el comando esperando que muestre la misma contraseña: cada ejecución genera una diferente.

Si configuraste `TURNOS_DB_PATH` para usar una ubicación distinta de `turnos.db`, mantené esa misma variable y ruta tanto al ejecutar `seed_demo.py` como al iniciar Uvicorn; así ambos procesos usan la misma base.

### Cuentas demo iniciales

Las cuentas iniciales se llaman:

- `cliente.demo@example.test`
- `cliente2.demo@example.test`
- `profesional.demo@example.test`
- `admin.demo@example.test`

Usá la contraseña que imprimió `seed_demo.py` para iniciar sesión. No hay contraseñas fijas incluidas en el repositorio. Los IDs no son constantes: copiá `profesional_id`, `servicio_id` y `cliente_id` de la salida de la carga demo para las solicitudes de reserva.

## 3. Abrir Swagger

Con el servidor en ejecución, abrí [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs). Verás las operaciones agrupadas por categoría.

Para probar una operación:

1. Abrí su fila para desplegarla.
2. Pulsá **Try it out**.
3. Completá los encabezados y el cuerpo JSON que se indiquen abajo.
4. Pulsá **Execute**.
5. Revisá **Responses**: ahí aparecen el código HTTP y la respuesta del servidor.

## 4. Iniciar sesión y usar el token

1. Abrí `POST /api/auth/login` y pulsá **Try it out**.
2. En el cuerpo, ingresá uno de los emails demo y la contraseña que imprimió el script:

   ```json
   {
     "email": "cliente.demo@example.test",
     "password": "PEGAR_LA_CONTRASENA_DE_LA_TERMINAL"
   }
   ```

3. Pulsá **Execute**. Una respuesta `200` incluye `access_token`.
4. Copiá el valor completo de `access_token`.
5. En cada operación protegida (`GET /api/turnos` y las dos operaciones `POST`), pulsá **Try it out** y completá el campo del encabezado `authorization` así: `Bearer ` seguido del token, por ejemplo `Bearer eyJ...`.

El token dura 30 minutos. Si venció, repetí el login para obtener otro.

## 5. Recorrido de prueba recomendado

### Consultar turnos — `GET /api/turnos`

Completá el encabezado `authorization` y pulsá **Execute**. Si la base demo todavía no tiene reservas, la respuesta correcta es `200` con una lista vacía. El rol limita qué turnos devuelve: Cliente ve los propios, Profesional los de su agenda y Admin todos.

### Crear una reserva — `POST /api/turnos`

Iniciá sesión como `cliente.demo@example.test` y enviá este JSON, reemplazando los IDs por los que imprimió el script:

```json
{
  "profesional_id": "PEGAR_PROFESIONAL_ID",
  "servicio_id": "PEGAR_SERVICIO_ID",
  "inicio": "AAAA-MM-DDT10:00:00Z"
}
```

Reemplazá `AAAA-MM-DD` por una fecha futura que caiga de lunes a viernes (por ejemplo, `2026-10-30`, si todavía está dentro de los próximos 60 días). El turno dura 30 minutos: elegí un inicio entre las 09:00 y las 16:30 UTC, alineado a intervalos de 15 minutos, al menos una hora después del momento actual. Usá el formato ISO 8601 con `Z` al final para indicar UTC. El servidor calcula `fin`; no lo incluyas.

Una reserva exitosa responde `201` e incluye el `id` del turno creado. Guardalo para probar la cancelación. Si una regla no se cumple, la respuesta explica el motivo; por ejemplo, `SLOT_UNAVAILABLE` indica que el horario no está disponible y `INVALID_TIME_RANGE` que la fecha u hora no cumple las condiciones.

Para reservar como Admin, agregá también `cliente_id` al cuerpo, usando el ID de uno de los clientes demo. Un Profesional no puede crear reservas.

### Cancelar una reserva — `POST /api/turnos/{turno_id}/cancelar`

Reemplazá `{turno_id}` por el `id` de la reserva creada y usá el token de su propietario. El Cliente no necesita enviar cuerpo; puede cancelar si faltan dos horas o más para el inicio. Si faltan menos de dos horas, se devuelve `CANCELLATION_WINDOW_EXPIRED`.

Profesional y Admin pueden cancelar sin respetar la ventana, pero deben enviar un motivo:

```json
{
  "motivo_cancelacion": "Prueba de cancelación desde Swagger"
}
```

Si ya fue cancelado o no está confirmado, el servidor rechaza la operación porque los estados finales no pueden volver a modificarse.

## 6. Códigos de respuesta frecuentes

| Código HTTP | Significado |
|---|---|
| `200` | Consulta, login o cancelación completados |
| `201` | Reserva creada |
| `401` | Falta token válido o las credenciales de login no coinciden |
| `403` | El rol no puede hacer la operación o el email del cliente no está verificado |
| `404` | No se encontró el recurso, o no pertenece al cliente que lo solicita |
| `409` | Conflicto de horario, ventana de cancelación vencida o estado incompatible |
| `422` | El cuerpo no cumple el formato o faltan datos requeridos |

El detalle de error incluye un `code` útil para reconocer la regla que lo produjo, como `SLOT_UNAVAILABLE`, `CANCELLATION_WINDOW_EXPIRED` o `INVALID_REQUEST`.
