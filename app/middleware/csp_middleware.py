"""
Content Security Policy (CSP) middleware for FastAPI.
Provides comprehensive security headers for the Journiv web application.
"""
from typing import Optional

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

from app.core.csp_config import get_csp_config


class CSPMiddleware(BaseHTTPMiddleware):
    """
    Content Security Policy middleware for FastAPI.

    Implements comprehensive security headers including:
    - Content Security Policy (CSP)
    - Other security headers (HSTS, X-Frame-Options, etc.)
    - Environment-specific configurations
    """

    def __init__(
        self,
        app,
        environment: str = "development",
        enable_csp: bool = True,
        enable_hsts: bool = True,
        enable_csp_reporting: bool = False,
        csp_report_uri: Optional[str] = None,
    ):
        super().__init__(app)
        self.environment = environment
        self.csp_config = get_csp_config(environment)

        # Override config with explicit parameters if provided
        if enable_csp is not None:
            self.csp_config._config["enable_csp"] = enable_csp
        if enable_hsts is not None:
            self.csp_config._config["enable_hsts"] = enable_hsts
        if enable_csp_reporting is not None:
            self.csp_config._config["enable_csp_reporting"] = enable_csp_reporting
        if csp_report_uri is not None:
            self.csp_config._config["csp_report_uri"] = csp_report_uri

    async def dispatch(self, request: Request, call_next):
        """Process request and add security headers."""
        response = await call_next(request)

        # Add security headers
        self._add_security_headers(request, response)

        return response

    def _add_security_headers(self, request: Request, response: Response):
        """Add comprehensive security headers to the response."""

        # Get base URL for CSP policy
        base_url = f"{request.url.scheme}://{request.url.netloc}"

        # Get security headers from config
        security_headers = self.csp_config.get_security_headers(base_url)

        # Add all security headers
        for header_name, header_value in security_headers.items():
            response.headers[header_name] = header_value

        # Published embed pages must be frameable by third-party sites.
        if request.url.path.startswith("/pub/") and request.query_params.get("embed") == "1":
            csp_value = response.headers.get("Content-Security-Policy")
            if csp_value:
                directives = []
                for directive in csp_value.split(";"):
                    normalized = directive.strip()
                    if not normalized or normalized.startswith("frame-ancestors "):
                        continue
                    directives.append(normalized)
                directives.append("frame-ancestors *")
                response.headers["Content-Security-Policy"] = "; ".join(directives)

            if "X-Frame-Options" in response.headers:
                del response.headers["X-Frame-Options"]


def create_csp_middleware(
    environment: str = "development",
    enable_csp: bool = True,
    enable_hsts: bool = True,
    enable_csp_reporting: bool = False,
    csp_report_uri: Optional[str] = None,
):
    """
    Factory function to create CSP middleware with configuration.

    Args:
        environment: Environment (development/production)
        enable_csp: Enable Content Security Policy
        enable_hsts: Enable HTTP Strict Transport Security
        enable_csp_reporting: Enable CSP violation reporting
        csp_report_uri: URI for CSP violation reports

    Returns:
        CSPMiddleware class configured with parameters
    """
    class ConfiguredCSPMiddleware(CSPMiddleware):
        def __init__(self, app):
            super().__init__(
                app=app,
                environment=environment,
                enable_csp=enable_csp,
                enable_hsts=enable_hsts,
                enable_csp_reporting=enable_csp_reporting,
                csp_report_uri=csp_report_uri,
            )

    return ConfiguredCSPMiddleware
