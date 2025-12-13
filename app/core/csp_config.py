"""
CSP Configuration.
Centralized configuration for Content Security Policy and related security headers.
"""

import json
import secrets
from enum import Enum
from typing import Dict, Optional, Any
from app.core.logging_config import log_info


class CSPEnvironment(Enum):
    DEVELOPMENT = "development"
    PRODUCTION = "production"
    TESTING = "testing"


class CSPConfig:
    """Content Security Policy configuration."""

    def __init__(self, environment: CSPEnvironment = CSPEnvironment.DEVELOPMENT):
        self.environment = environment
        self._config = self._build_config()

    # ---------------------------------------------------------------------
    #  Environment-based configuration
    # ---------------------------------------------------------------------
    def _build_config(self) -> Dict[str, Any]:
        if self.environment == CSPEnvironment.DEVELOPMENT:
            config = self._development_config()
            log_info(f"CSP Configuration loaded: DEVELOPMENT environment\n{json.dumps(config, indent=2)}")
            return config

        elif self.environment == CSPEnvironment.PRODUCTION:
            config = self._production_config()
            log_info(f"CSP Configuration loaded: PRODUCTION environment\n{json.dumps(config, indent=2)}")
            return config
        else:
            config = self._testing_config()
            log_info(f"CSP Configuration loaded: TESTING environment\n{json.dumps(config, indent=2)}")
            return config

    # ---------------------------------------------------------------------
    #  DEVELOPMENT
    # ---------------------------------------------------------------------
    def _development_config(self) -> Dict[str, Any]:
        """Permissive CSP suitable for local testing."""
        return {
            "enable_csp": True,
            "enable_hsts": False,
            "enable_csp_reporting": True,
            "csp_report_uri": "/api/v1/security/csp-report",
            "directives": {
                "default-src": ["'self'"],
                "script-src": [
                    "'self'",
                    "'unsafe-inline'",
                    "'unsafe-eval'",
                    "https://www.gstatic.com",
                    "https://cdn.jsdelivr.net",
                    "https://unpkg.com",
                    "https://cdn.jsdelivr.net" # swagger docs
                ],
                "style-src": [
                    "'self'",
                    "'unsafe-inline'",
                    "https://fonts.googleapis.com",
                    "https://cdn.jsdelivr.net" # swagger docs
                ],
                "img-src": [
                    "'self'",
                    "data:",
                    "blob:",
                    "https:",         # permit any https images during dev
                    "https://fastapi.tiangolo.com" # swagger docs image

                ],
                "font-src": [
                    "'self'",
                    "data:",
                    "https://fonts.gstatic.com",
                    "https://www.gstatic.com"
                ],
                "connect-src": [
                    "'self'",
                    "blob:",
                    "data:",
                    "ws:",
                    "wss:",
                    "https://fonts.gstatic.com",
                    "https://www.gstatic.com",
                    "{base_url}",
                    "https://cdn.jsdelivr.net" # swagger docs
                ],
                "media-src": [
                    "'self'",
                    "data:",
                    "blob:",
                    "{base_url}"
                ],
                "object-src": ["'none'"],
                "frame-src": ["'self'"],
                "frame-ancestors": ["'none'"],
                "base-uri": ["'self'"],
                "form-action": ["'self'"],
                "manifest-src": ["'self'"],
                "worker-src": ["'self'", "blob:"],
                # TODO: Add upgrade-insecure-requests if HTTPS is enabled
                # "upgrade-insecure-requests": [],
                # "block-all-mixed-content": [],
                "child-src": ["'self'", "blob:"]
            }
        }

    # ---------------------------------------------------------------------
    #  PRODUCTION
    # ---------------------------------------------------------------------
    def _production_config(self) -> Dict[str, Any]:
        """Stricter CSP for production."""
        return {
            "enable_csp": True,
            "enable_hsts": True,
            "enable_csp_reporting": True,
            "csp_report_uri": "/api/v1/security/csp-report",
            "directives": {
                "default-src": ["'self'"],
                "script-src": [
                    "'self'",
                    "'unsafe-inline'",
                    "'unsafe-eval'",
                    # Breaks <script> tag that does not have a matching nonce="..."
                    # attribute (which your Flutter-generated index.html doesn not) will be blocked.
                    # "'nonce-{nonce}'",
                    "https://www.gstatic.com",
                    "https://cdn.jsdelivr.net" # swagger docs
                ],
                "style-src": [
                    "'self'",
                    "'unsafe-inline'",
                    "https://fonts.googleapis.com",
                    "https://cdn.jsdelivr.net" # swagger docs
                ],
                "img-src": ["'self'", "data:", "blob:", "https:", "https://fastapi.tiangolo.com"],
                "font-src": [
                    "'self'",
                    "data:",
                    "https://fonts.gstatic.com",
                    "https://www.gstatic.com"
                ],
                "connect-src": [
                    "'self'",
                    "blob:",
                    "data:",
                    "https://fonts.gstatic.com",
                    "https://www.gstatic.com",
                    "{base_url}",
                    "https://cdn.jsdelivr.net" # swagger docs
                ],
                "media-src": ["'self'", "data:", "blob:", "{base_url}"],
                "object-src": ["'none'"],
                "frame-src": ["'self'"],
                "frame-ancestors": ["'none'"],
                "base-uri": ["'self'"],
                "form-action": ["'self'"],
                "manifest-src": ["'self'"],
                "worker-src": ["'self'", "blob:"],
                # TODO: Add upgrade-insecure-requests if HTTPS is enabled
                # "upgrade-insecure-requests": [],
                # "block-all-mixed-content": [],
                "child-src": ["'self'", "blob:"]
            }
        }

    # ---------------------------------------------------------------------
    #  TESTING
    # ---------------------------------------------------------------------
    def _testing_config(self) -> Dict[str, Any]:
        """No-CSP config for automated tests."""
        return {
            "enable_csp": False,
            "enable_hsts": False,
            "enable_csp_reporting": False,
            "csp_report_uri": None,
            "directives": {}
        }

    # ---------------------------------------------------------------------
    #  Builders
    # ---------------------------------------------------------------------
    def get_csp_policy(self, base_url: str = "") -> str:
        if not self._config["enable_csp"]:
            return ""
        base_url = (base_url or "").rstrip("/")
        directives = []
        for directive, sources in self._config["directives"].items():
            if sources is not None:
                src = " ".join(sources)
                # Only replace {nonce} if it's actually in the string
                if "{nonce}" in src:
                    nonce = self._generate_nonce()
                    src = src.replace("{nonce}", nonce)
                src = src.replace("{base_url}", base_url)
                directives.append(f"{directive} {src}".strip())
        return "; ".join(directives)

    def _generate_nonce(self) -> str:
        return secrets.token_urlsafe(16)

    def get_security_headers(self, base_url: str = "") -> Dict[str, str]:
        headers = {}
        if self._config["enable_csp"]:
            policy = self.get_csp_policy(base_url)
            if policy:
                headers["Content-Security-Policy"] = policy

        if self._config["enable_hsts"]:
            headers["Strict-Transport-Security"] = (
                "max-age=31536000; includeSubDomains; preload"
            )

        headers.update({
            "X-Content-Type-Options": "nosniff",
            "X-Frame-Options": "DENY",
            "X-XSS-Protection": "1; mode=block",
            "Referrer-Policy": "strict-origin-when-cross-origin",
            "Permissions-Policy": self._get_permissions_policy(),
            "X-Permitted-Cross-Domain-Policies": "none",
            "X-Download-Options": "noopen"
        })
        return headers

    def _get_permissions_policy(self) -> str:
        permissions = [
            "geolocation=()",
            "microphone=()",
            "camera=()",
            "payment=()",
            "usb=()",
            "magnetometer=()",
            "gyroscope=()",
            "accelerometer=()",
            "ambient-light-sensor=()",
            "autoplay=(self)",
            "fullscreen=(self)",
            "picture-in-picture=()"
        ]
        return ", ".join(permissions)

    # ---------------------------------------------------------------------
    #  Accessors
    # ---------------------------------------------------------------------
    def is_csp_enabled(self) -> bool:
        return self._config["enable_csp"]

    def is_hsts_enabled(self) -> bool:
        return self._config["enable_hsts"]

    def is_reporting_enabled(self) -> bool:
        return self._config["enable_csp_reporting"]

    def get_report_uri(self) -> Optional[str]:
        return self._config.get("csp_report_uri")


# ---------------------------------------------------------------------
#  Global helpers
# ---------------------------------------------------------------------
DEVELOPMENT_CSP = CSPConfig(CSPEnvironment.DEVELOPMENT)
PRODUCTION_CSP = CSPConfig(CSPEnvironment.PRODUCTION)
TESTING_CSP = CSPConfig(CSPEnvironment.TESTING)


def get_csp_config(environment: str) -> CSPConfig:
    env_map = {
        "development": DEVELOPMENT_CSP,
        "production": PRODUCTION_CSP,
        "testing": TESTING_CSP,
    }
    return env_map.get(environment.lower(), DEVELOPMENT_CSP)
