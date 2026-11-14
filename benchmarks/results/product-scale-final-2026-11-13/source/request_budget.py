"""Bounded JSON bodies before framework parsing; capsule uploads stream separately."""

from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send


class RequestBodyBudget:
    def __init__(self, app: ASGIApp, limit: int = 65536) -> None:
        self.app, self.limit = app, limit

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if (
            scope["type"] != "http"
            or scope["method"] not in {"POST", "PUT", "PATCH"}
            or scope["path"] == "/v1/runs/import"
        ):
            await self.app(scope, receive, send)
            return
        body = bytearray()
        while True:
            message = await receive()
            if message["type"] != "http.request":
                return
            body.extend(message.get("body", b""))
            if len(body) > self.limit:
                await JSONResponse({"detail": "JSON body exceeds byte budget"}, status_code=413)(
                    scope, receive, send
                )
                return
            if not message.get("more_body", False):
                break
        consumed = False

        async def bounded_receive() -> Message:
            nonlocal consumed
            if consumed:
                return await receive()
            consumed = True
            return {"type": "http.request", "body": bytes(body), "more_body": False}

        await self.app(scope, bounded_receive, send)
