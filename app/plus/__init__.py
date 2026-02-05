"""
Journiv Plus integration module.

This module provides integration with Journiv Plus licensing features.
It's designed to gracefully fall back when Plus features are not available or licensed.

In Plus builds, the compiled .so module is imported.
In non-Plus builds, placeholder stubs are used.

"""

import logging
from typing import TYPE_CHECKING, Any, Type, cast

from app.core.logging_config import LogCategory

logger = logging.getLogger(LogCategory.PLUS)

PlusFeatureFactory: Type[Any]

if TYPE_CHECKING:
    from app.plus.placeholder import PlusFeatureFactory as PlusFeatureFactory


def _create_error_stub(plus_err: str, placeholder_err: str, error_type: str = "also failed") -> type:
    """Create a no-op PlusFeatureFactory stub that raises ImportError."""
    class PlusFeatureFactory:
        def __init__(self, signed_license: str):
            raise ImportError(
                f"PlusFeatureFactory is unavailable. "
                f"Plus features import failed: {plus_err}. "
                f"Placeholder import {error_type}: {placeholder_err}. "
                "This indicates a configuration error."
            )
    return PlusFeatureFactory


# Try to import Plus feature factory from compiled module
# Falls back to placeholders if not available
PLUS_FEATURES_AVAILABLE = False

try:
    # Try to import from compiled extension module (Plus build)
    from app.plus.plus_features import (  # type: ignore[unresolved-import]
        PlusFeatureFactory as _PlusFeatureFactory,
    )
    PlusFeatureFactory = cast(Type[Any], _PlusFeatureFactory)
    PLUS_FEATURES_AVAILABLE = True
except ImportError as e:
    # Log the import error for debugging
    logger.warning(
        f"Plus features module not available (falling back to placeholders): {e}",
        exc_info=True
    )
    # Fall back to placeholder implementations
    try:
        from app.plus.placeholder import (
            PlusFeatureFactory as _PlusFeatureFactory,
        )
        PlusFeatureFactory = cast(Type[Any], _PlusFeatureFactory)
        PLUS_FEATURES_AVAILABLE = False
    except ImportError as placeholder_error:
        logger.error(
            f"Failed to import placeholder module: {placeholder_error}. "
            f"Original Plus features import error: {e}. "
            "Using no-op stub as fallback.",
            exc_info=True
        )
        PlusFeatureFactory = cast(Type[Any], _create_error_stub(
            str(e),
            str(placeholder_error),
            "also failed"
        ))
        PLUS_FEATURES_AVAILABLE = False
    except Exception as placeholder_error:
        logger.error(
            f"Unexpected error importing placeholder module: {placeholder_error}. "
            f"Original Plus features import error: {e}. "
            "Using no-op stub as fallback.",
            exc_info=True
        )
        PlusFeatureFactory = cast(Type[Any], _create_error_stub(
            str(e),
            str(placeholder_error),
            "failed with unexpected error"
        ))
        PLUS_FEATURES_AVAILABLE = False
except Exception as e:
    # Catch any other errors during import (e.g., missing dependencies, wrong architecture)
    logger.error(
        f"Unexpected error importing Plus features module: {e}",
        exc_info=True
    )
    # Fall back to placeholder implementations
    try:
        from app.plus.placeholder import (
            PlusFeatureFactory as _PlusFeatureFactory,
        )
        PlusFeatureFactory = cast(Type[Any], _PlusFeatureFactory)
        PLUS_FEATURES_AVAILABLE = False
    except ImportError as placeholder_error:
        logger.error(
            f"Failed to import placeholder module: {placeholder_error}. "
            f"Original Plus features import error: {e}. "
            "Using no-op stub as fallback.",
            exc_info=True
        )
        PlusFeatureFactory = cast(Type[Any], _create_error_stub(
            str(e),
            str(placeholder_error),
            "also failed"
        ))
        PLUS_FEATURES_AVAILABLE = False
    except Exception as placeholder_error:
        logger.error(
            f"Unexpected error importing placeholder module: {placeholder_error}. "
            f"Original Plus features import error: {e}. "
            "Using no-op stub as fallback.",
            exc_info=True
        )
        PlusFeatureFactory = cast(Type[Any], _create_error_stub(
            str(e),
            str(placeholder_error),
            "failed with unexpected error"
        ))
        PLUS_FEATURES_AVAILABLE = False

__all__ = [
    "PLUS_FEATURES_AVAILABLE",
    "PlusFeatureFactory",
]
