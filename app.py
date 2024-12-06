import sys
import traceback
from datetime import datetime
from http import HTTPStatus

from aiohttp import web
from aiohttp.web import Request, Response, json_response

from botbuilder.core import (
    BotFrameworkAdapterSettings,
    TurnContext,
    BotFrameworkAdapter,
)
from botbuilder.core.integration import aiohttp_error_middleware
from botbuilder.schema import Activity, ActivityTypes

from bots import alfabot

from config import DefaultConfig

CONFIG = DefaultConfig()

# Create adapter.
SETTINGS = BotFrameworkAdapterSettings(CONFIG.APP_ID, CONFIG.APP_PASSWORD)
ADAPTER = BotFrameworkAdapter(SETTINGS)

# Catch-all for errors.
async def on_error(context: TurnContext, error: Exception):
    print(f"\n [on_turn_error] unhandled error: {error}", file=sys.stderr)
    traceback.print_exc()

    await context.send_activity("The bot encountered an error or bug.")
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

# Create the Bot
BOT = alfabot()

# Listen for incoming requests on /api/messages
async def messages(req: Request) -> Response:
    if "application/json" in req.headers["Content-Type"]:
        body = await req.json()
    else:
        return Response(status=HTTPStatus.UNSUPPORTED_MEDIA_TYPE)

    activity = Activity().deserialize(body)
    auth_header = req.headers["Authorization"] if "Authorization" in req.headers else ""

    response = await ADAPTER.process_activity(activity, auth_header, BOT.on_turn)
    if response:
        return json_response(data=response.body, status=response.status)
    return Response(status=HTTPStatus.OK)

# Create the aiohttp application and add routes
app = web.Application(middlewares=[aiohttp_error_middleware])
app.router.add_post("/api/messages", messages)

# Now adapt the aiohttp app for ASGI using the ASGIApp middleware
from aiohttp import web
from aiohttp.web import Application
from uvicorn import Config, Server

# Create ASGI app using aiohttp
asgi_app = web.Application(middlewares=[aiohttp_error_middleware])
asgi_app.router.add_post("/api/messages", messages)

# This wrapper allows running the aiohttp app as an ASGI app for uvicorn
class ASGIApp:
    def __init__(self, app: Application):
        self.app = app

    async def __call__(self, scope, receive, send):
        await self.app(scope, receive, send)

# If you're running this as the main app
if __name__ == "__main__":
    try:
        # Wrap the app into an ASGI app
        app_asgi = ASGIApp(asgi_app)
        
        # Use Uvicorn to serve the ASGI app
        config = Config(app_asgi, host="0.0.0.0", port=3979)
        server = Server(config)
        server.run()
    except Exception as error:
        raise error
