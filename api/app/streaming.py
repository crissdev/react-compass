import asyncio
from collections.abc import AsyncGenerator

from starlette.requests import ClientDisconnect
from starlette.responses import StreamingResponse
from starlette.types import Receive, Scope, Send


class CancellableStreamingResponse(StreamingResponse):
    """Cancel active work on disconnect, including between writes on ASGI 2.4+."""

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        tasks = (
            asyncio.create_task(self.stream_response(send)),
            asyncio.create_task(self.listen_for_disconnect(receive)),
        )
        try:
            completed, _ = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
            for task in completed:
                task.result()
        except OSError as error:
            raise ClientDisconnect() from error
        finally:
            for task in tasks:
                task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
            if isinstance(self.body_iterator, AsyncGenerator):
                await self.body_iterator.aclose()

        if self.background is not None:
            await self.background()
