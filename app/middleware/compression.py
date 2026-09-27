"""Response compression that leaves media bytes alone.

Starlette's ``GZipMiddleware`` compresses every response over its size floor,
media included. That is wasted work on audio, video and images, which are
already compressed, and it is incorrect for byte ranges: a ``206`` whose
``Content-Range`` counts the file's bytes but whose body is gzip no longer
describes what it carries, and a media player that seeks by byte offset is
handed bytes it cannot use.

``MediaSafeGZipMiddleware`` keeps gzip for text-like responses (JSON, HTML,
JS, CSS, SVG) and passes these through untouched:

- any request that carries a ``Range`` header, and any ``206`` response;
- responses whose ``Content-Type`` is binary media or an archive.
"""

from starlette.datastructures import Headers
from starlette.middleware.gzip import GZipMiddleware, GZipResponder
from starlette.types import Message, Receive, Scope, Send

# Already compressed, or byte-addressed by clients: never gzip these.
_UNCOMPRESSED_PREFIXES = ("audio/", "video/", "image/", "font/")
_UNCOMPRESSED_TYPES = frozenset(
    {
        "application/gzip",
        "application/octet-stream",
        "application/pdf",
        "application/x-gzip",
        "application/zip",
    }
)
# Text-like types under a binary prefix that still compress well.
_COMPRESSIBLE_EXCEPTIONS = frozenset({"image/svg+xml"})


def is_compressible(content_type: str) -> bool:
    """Whether a response of this ``Content-Type`` is worth gzipping."""
    media_type = content_type.split(";", 1)[0].strip().lower()
    if media_type in _COMPRESSIBLE_EXCEPTIONS:
        return True
    if media_type in _UNCOMPRESSED_TYPES:
        return False
    return not media_type.startswith(_UNCOMPRESSED_PREFIXES)


class _MediaSafeGZipResponder(GZipResponder):
    """``GZipResponder`` that forwards partial and media responses verbatim."""

    passthrough = False

    async def send_with_compression(self, message: Message) -> None:
        if message["type"] == "http.response.start":
            headers = Headers(raw=message["headers"])
            self.passthrough = message["status"] == 206 or not is_compressible(
                headers.get("content-type", "")
            )
        if self.passthrough:
            await self.send(message)
            return
        await super().send_with_compression(message)


class MediaSafeGZipMiddleware(GZipMiddleware):
    """``GZipMiddleware`` that never compresses byte ranges or binary media."""

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":  # pragma: no cover
            await self.app(scope, receive, send)
            return

        headers = Headers(scope=scope)
        # A range names bytes of the file itself, so the answer must carry
        # exactly those bytes, never an encoded form of them.
        if "range" in headers:
            await self.app(scope, receive, send)
            return
        if "gzip" not in headers.get("accept-encoding", ""):
            await super().__call__(scope, receive, send)
            return

        responder = _MediaSafeGZipResponder(
            self.app, self.minimum_size, compresslevel=self.compresslevel
        )
        await responder(scope, receive, send)
