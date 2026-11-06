"""Bounded upload admission and private-response headers."""

import asyncio
import tempfile

from fastapi.responses import JSONResponse
from starlette.concurrency import run_in_threadpool

from app.auth.origins import trusted_origin
from app.errors import ServiceError


class AdmissionMiddleware:
    """Bound actual bytes even with chunked encoding, before multipart parsing."""

    def __init__(self, app, settings, db):
        self.app, self.s, self.db = app, settings, db

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        headers = {k.lower(): v for k, v in scope["headers"]}

        async def secure_send(message):
            if message["type"] == "http.response.start" and not scope.get(
                "security_headers_applied"
            ):
                message["headers"] += [
                    (b"cache-control", b"no-store"),
                    (b"referrer-policy", b"no-referrer"),
                    (b"x-robots-tag", b"noindex, nofollow"),
                    (b"x-content-type-options", b"nosniff"),
                    (
                        b"content-security-policy",
                        b"default-src 'self'; script-src 'self'; style-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'",
                    ),
                ]
            await send(message)

        if (
            scope["method"] != "POST"
            or scope["path"].removeprefix(self.s.app_prefix) != "/api/jobs"
        ):
            return await self.app(scope, receive, secure_send)
        lease = None
        spool = None
        try:
            origin = headers.get(b"origin")
            if (
                origin
                and not scope.get("csrf_verified")
                and not trusted_origin(origin.decode("latin-1"), self.s)
            ):
                raise ServiceError("Untrusted request origin.", 403)
            maximum = self.s.upload_bytes + 1024**2  # bounded multipart overhead
            try:
                length = int(headers.get(b"content-length", b"0"))
            except ValueError:
                raise ServiceError("Invalid Content-Length.", 400) from None
            if length > maximum:
                raise ServiceError("Upload exceeds the configured limit.", 413)
            lease = await run_in_threadpool(self.db.reserve_upload)
            scope["admission_lease"] = lease
            spool = tempfile.TemporaryFile(dir=self.s.storage_root / "staging")
            size = 0
            async with asyncio.timeout(300):
                while True:
                    message = await receive()
                    if message["type"] == "http.disconnect":
                        return
                    size += len(message.get("body", b""))
                    if size > maximum:
                        raise ServiceError("Upload exceeds the configured limit.", 413)
                    await run_in_threadpool(spool.write, message.get("body", b""))
                    if not message.get("more_body", False):
                        break
            spool.seek(0)
            delivered = False

            async def replay():
                nonlocal delivered
                if not delivered:
                    chunk = await run_in_threadpool(spool.read, 65536)
                    if chunk:
                        return {"type": "http.request", "body": chunk, "more_body": True}
                    delivered = True
                    return {"type": "http.request", "body": b"", "more_body": False}
                return await receive()

            await self.app(scope, replay, secure_send)
        except (ServiceError, TimeoutError) as exc:
            status = exc.status if isinstance(exc, ServiceError) else 408
            message = exc.message if isinstance(exc, ServiceError) else "Upload timed out."
            await JSONResponse({"detail": message}, status_code=status)(scope, receive, secure_send)
        finally:
            if spool is not None:
                spool.close()
            if lease:
                await run_in_threadpool(self.db.release_upload, lease)
