"""
Request logging middleware with request ID tracking, context propagation, and structured logging.
"""
import json
import logging
import time
import uuid
from contextvars import ContextVar
from typing import Optional

from app.core.logging_config import _sanitize_data

logger = logging.getLogger(__name__)

# Context variable for request ID propagation
request_id_ctx: ContextVar[str] = ContextVar('request_id', default='unknown')
request_path_ctx: ContextVar[str] = ContextVar('request_path', default='unknown')

# Default status code when response is not captured
DEFAULT_STATUS_CODE = 500


def _sanitize_response_body(response_body: str) -> str:
    """
    Sanitize response body to mask sensitive fields.

    Handles both JSON and plain text response bodies.
    For JSON responses, parses, sanitizes, and re-stringifies.
    For plain text, applies string sanitization.

    Args:
        response_body: The response body string to sanitize

    Returns:
        Sanitized response body string
    """
    if not response_body:
        return response_body

    try:
        parsed = json.loads(response_body)
        sanitized = _sanitize_data(parsed)
        return json.dumps(sanitized)
    except (json.JSONDecodeError, TypeError):
        sanitized = _sanitize_data(response_body)
        return str(sanitized) if sanitized is not None else ""


class RequestLoggingMiddleware:
    """
    Request logging middleware with request ID tracking, context propagation, and structured logging.

    Features:
    - Generates unique request ID for each request
    - Propagates request ID via context variables (accessible throughout the request lifecycle)
    - Structured logging with JSON-compatible extra fields
    - Exception handling with proper error logging
    - Response header injection (x-request-id)
    - Performance timing
    """

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] == "http":
            # Generate unique request ID
            request_id = str(uuid.uuid4())

            # Set request ID in context for automatic propagation
            request_id_ctx.set(request_id)

            # Start timing
            start_time = time.time()

            # Extract request information
            method = scope.get("method", "UNKNOWN")
            path = scope.get("path", "/")
            client_host = scope.get("client", ["unknown", 0])[0] if scope.get("client") else "unknown"
            request_path_ctx.set(path)

            # Structured logging for request start
            logger.info(
                "Request started",
                extra={
                    "request_id": request_id,
                    "method": method,
                    "path": path,
                    "client_ip": client_host,
                    "event": "request_start"
                }
            )

            # Process request and capture response
            response_captured = None
            error_occurred = False
            error_message = None
            response_body = None

            async def send_wrapper(message):
                nonlocal response_captured, response_body
                if message["type"] == "http.response.start":
                    # Capture status code
                    status_code = message.get("status", DEFAULT_STATUS_CODE)
                    response_captured = {"status_code": status_code}

                    # Add request ID to response headers
                    headers = list(message.get("headers", []))
                    headers.append([b"x-request-id", request_id.encode()])
                    message["headers"] = headers
                elif message["type"] == "http.response.body":
                    # Capture response body for 4xx errors to help with debugging
                    body = message.get("body", b"")
                    if body and response_captured and 400 <= response_captured.get("status_code", 0) < 500:
                        try:
                            response_body = body.decode("utf-8")[:1000]  # Limit to 1KB
                        except (UnicodeDecodeError, AttributeError):
                            pass

                await send(message)

            # Process the request with exception handling
            try:
                await self.app(scope, receive, send_wrapper)
            except Exception as e:
                error_occurred = True
                error_message = str(e)

                # Structured logging for exceptions
                logger.error(
                    "Request failed with exception",
                    extra={
                        "request_id": request_id,
                        "method": method,
                        "path": path,
                        "client_ip": client_host,
                        "error": error_message,
                        "event": "request_exception"
                    },
                    exc_info=True
                )

                # Re-raise the exception to let FastAPI handle it
                raise
            finally:
                # Calculate duration
                duration = time.time() - start_time
                duration_ms = round(duration * 1000, 2)
                if duration_ms >= 10000:
                    logger.warning(
                        "Slow request",
                        extra={
                            "request_id": request_id,
                            "method": method,
                            "path": path,
                            "client_ip": client_host,
                            "duration_ms": duration_ms,
                            "event": "request_slow",
                        },
                    )

                # Determine final status code
                if response_captured:
                    status_code = response_captured.get("status_code", DEFAULT_STATUS_CODE)
                else:
                    # No response was captured, likely due to an exception
                    status_code = DEFAULT_STATUS_CODE

                # Structured logging for request completion
                log_extra = {
                    "request_id": request_id,
                    "method": method,
                    "path": path,
                    "client_ip": client_host,
                    "status_code": status_code,
                    "duration_ms": duration_ms,
                    "event": "request_complete"
                }

                if error_occurred:
                    log_extra["error"] = error_message
                    logger.error("Request completed with error", extra=log_extra)
                else:
                    # Log at different levels based on status code
                    if status_code >= 500:
                        logger.error("Request completed with server error", extra=log_extra)
                    elif status_code >= 400:
                        # Include response body for 4xx errors to help with debugging
                        if response_body:
                            sanitized_body = _sanitize_response_body(response_body)
                            log_extra["response_body"] = sanitized_body
                        logger.warning("Request completed with client error", extra=log_extra)
                    else:
                        logger.info("Request completed successfully", extra=log_extra)
        else:
            # Non-HTTP scope (e.g., WebSocket, lifespan)
            await self.app(scope, receive, send)



class RequestContextLogger:
    """
    Context-aware logger that automatically includes request ID in all log messages.

    This logger uses the request_id_ctx context variable to automatically include
    the request ID in structured logging. No need to manually pass request_id.

    Usage:
        logger = RequestContextLogger(__name__)
        logger.info("User logged in", user_id=123)  # Automatically includes request_id

    The request ID is added to the 'extra' dict for structured logging compatibility.
    """

    def __init__(self, name: str):
        self.logger = logging.getLogger(name)

    def _add_request_context(self, extra: Optional[dict] = None) -> dict:
        """Add request ID from context to extra dict."""
        if extra is None:
            extra = {}
        extra["request_id"] = request_id_ctx.get()
        return extra

    def info(self, message: str, **kwargs):
        """Log info message with automatic request ID."""
        kwargs["extra"] = self._add_request_context(kwargs.get("extra"))
        self.logger.info(message, **kwargs)

    def warning(self, message: str, **kwargs):
        """Log warning message with automatic request ID."""
        kwargs["extra"] = self._add_request_context(kwargs.get("extra"))
        self.logger.warning(message, **kwargs)

    def error(self, message: str, **kwargs):
        """Log error message with automatic request ID."""
        kwargs["extra"] = self._add_request_context(kwargs.get("extra"))
        self.logger.error(message, **kwargs)

    def debug(self, message: str, **kwargs):
        """Log debug message with automatic request ID."""
        kwargs["extra"] = self._add_request_context(kwargs.get("extra"))
        self.logger.debug(message, **kwargs)


class RequestContextFilter(logging.Filter):
    """
    Logging filter that automatically adds request ID to all log records.

    This filter can be added to any logger to automatically include the request_id
    field in all log records, making it available for formatters.

    Usage in logging configuration:
        handler.addFilter(RequestContextFilter())

    Formatter example:
        formatter = logging.Formatter(
            '%(asctime)s - [%(request_id)s] - %(name)s - %(levelname)s - %(message)s'
        )
    """

    def filter(self, record):
        """Add request_id to the log record."""
        record.request_id = request_id_ctx.get()
        return True


# Global request context logger
request_logger = RequestContextLogger("app.request")
