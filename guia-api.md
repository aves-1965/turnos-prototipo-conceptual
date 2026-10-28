# Guía rápida de la API

La documentación interactiva está en [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs), mientras el backend está en ejecución. En Swagger, abrí una operación, pulsá **Try it out**, completá los datos y elegí **Execute**. La respuesta y el código HTTP aparecen debajo.

## Cómo probar los endpoints

1. **Obtener un token:** usá `POST /api/auth/login` con un usuario ya existente:

   ```json
   {
     "email": "persona@example.com",
     "password": "tu-contraseña"
   }
   ```

   Copiá el valor `access_token` de la respuesta. El token dura 30 minutos. El backend no incluye una ruta para registrar usuarios ni crea usuarios de ejemplo: si todavía no hay usuarios cargados, no será posible iniciar sesión.

2. **Autorizar las operaciones:** en cada endpoint protegido, completá el encabezado `authorization` escribiendo el esquema `Bearer`, un espacio y, a continuación, el token obtenido. No agregues comillas.

3. **Consultar turnos:** ejecutá `GET /api/turnos`. El backend limita los resultados según el rol autenticado: cliente, turnos propios; profesional, turnos de su agenda; administrador, todos.

4. **Crear una reserva:** ejecutá `POST /api/turnos` con IDs existentes y un inicio futuro que incluya zona horaria. Por ejemplo:

   ```json
   {
     "profesional_id": "UUID-DEL-PROFESIONAL",
     "servicio_id": "UUID-DEL-SERVICIO",
     "inicio": "2026-11-02T10:00:00Z"
   }
   ```

   Un cliente autenticado reserva para sí mismo. Un administrador también debe enviar `cliente_id` para indicar a quién reserva. El backend calcula `fin` y valida disponibilidad, horario laboral, contacto y email verificado.

5. **Cancelar:** ejecutá `POST /api/turnos/{turno_id}/cancelar`, sustituyendo `{turno_id}` por el UUID devuelto al crear el turno. Un cliente no envía cuerpo y solo puede cancelar sus turnos con al menos dos horas de anticipación. Un profesional o administrador debe enviar:

   ```json
   {
     "motivo_cancelacion": "Motivo de la cancelación"
   }
   ```

Los UUID de usuario, profesional y servicio deben corresponder a datos existentes en `turnos.db`. Los errores incluyen un código en `detail`, por ejemplo `SLOT_UNAVAILABLE` (409) o `CANCELLATION_WINDOW_EXPIRED` (409).

## Para iniciar el servidor

Ejecutá estos cuatro pasos en orden, desde el directorio del proyecto. Los pasos 1 y 2 se hacen la primera vez; para inicios posteriores, alcanza con repetir 3 y 4 en la misma terminal.

```bash
# 1. Crear un entorno aislado para las dependencias de Python.
python -m venv .venv

# 2. Instalar FastAPI, Uvicorn y las demás dependencias del backend.
.venv/bin/python -m pip install -r requirements.txt

# 3. Crear un secreto aleatorio para firmar los tokens Bearer.
export TURNOS_TOKEN_SECRET="$(openssl rand -hex 32)"

# 4. Iniciar FastAPI en el puerto 8000 y recargarlo al editar el código.
.venv/bin/uvicorn main:app --reload --host 127.0.0.1 --port 8000
```

El paso 3 configura el secreto solo para la terminal actual; no lo publiques ni lo agregues al repositorio. Al arrancar, el backend crea la base local `turnos.db` y las tablas definidas por el modelo del sistema. Dejá la terminal abierta y entrá a [Swagger UI](http://127.0.0.1:8000/docs); para detener el servidor, usá **Ctrl+C**.
