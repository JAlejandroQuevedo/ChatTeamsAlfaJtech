import sys
import traceback
from datetime import datetime
from http import HTTPStatus
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from botbuilder.core import BotFrameworkAdapterSettings, TurnContext, BotFrameworkAdapter
from botbuilder.core.integration import aiohttp_error_middleware
from botbuilder.schema import Activity, ActivityTypes

from bots import alfabot
from config import DefaultConfig

# Configuración
CONFIG = DefaultConfig()

# Crear adaptador
SETTINGS = BotFrameworkAdapterSettings(CONFIG.APP_ID, CONFIG.APP_PASSWORD)
ADAPTER = BotFrameworkAdapter(SETTINGS)

# Manejo de errores global
async def on_error(context: TurnContext, error: Exception):
    """Manejamos errores durante el procesamiento de la actividad"""
    print(f"\n[on_turn_error] error no manejado: {error}", file=sys.stderr)
    traceback.print_exc()

    # Enviamos un mensaje al usuario
    await context.send_activity("El bot ha encontrado un error o bug.")
    
    # Si estamos en el emulador, agregamos trazabilidad adicional
    if context.activity.channel_id == "emulator":
        trace_activity = Activity(
            label="TurnError",
            name="on_turn_error Trace",
            timestamp=datetime.utcnow(),
            type=ActivityTypes.trace,
            value=f"{error}",
            value_type="https://www.botframework.com/schemas/error",
        )
        await context.send_activity(trace_activity)

ADAPTER.on_turn_error = on_error

# Crear la instancia del bot
BOT = alfabot()

# Endpoint de mensajes
async def messages(req: Request):

    body = await req.json()


    activity = Activity().deserialize(body)
    auth_header = req.headers.get("Authorization", "")

    # Procesamos la actividad
    response = await ADAPTER.process_activity(activity, auth_header, BOT.on_turn)

    if response:
        return JSONResponse(content=response.body, status_code=response.status)
    
    # Asegurarse de enviar una respuesta vacía con código OK (200)
    return JSONResponse(content={}, status_code=HTTPStatus.OK)

# Configuración de la aplicación FastAPI
app = FastAPI()

# Aseguramos que los endpoints están configurados correctamente
app.post("/api/messages")(messages)

# Ejecutar la app usando uvicorn
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=CONFIG.PORT or 3979)
