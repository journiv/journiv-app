"""
Journiv Plus placeholder module.

This is a stub implementation for the non Plus build.
In Plus-enabled Docker builds, the compiled .so module will provide
the actual implementations.
"""
from typing import Any


class _PlaceholderError(ImportError):
    """Raised when Plus features are accessed in non Plus build."""
    pass

class PlusFeatureFactory:
    """
    Placeholder factory for non Plus builds.

    This will always raise an error when instantiated in non Plus builds.
    In Plus builds, the real factory from plus_features.so (compiled) is used.
    """
    def __init__(self, signed_license: str, bridge: Any):
        """
        Placeholder constructor that always denies access.

        Args:
            signed_license: Signed license blob (unused in non Plus build)
            bridge: Host bridge instance (unused in non Plus build)

        Raises:
            _PlaceholderError: Always raised in non Plus builds
        """
        raise _PlaceholderError(
            "PlusFeatureFactory requires Journiv Plus build. "
            "This feature is not available in the non Plus build."
        )

    @property
    def tier(self) -> str:
        """Placeholder property that always raises."""
        raise _PlaceholderError(
            "License tier access requires Journiv Plus build"
        )

    @property
    def license_type(self) -> str:
        """Placeholder property that always raises."""
        raise _PlaceholderError(
            "License type access requires Journiv Plus build"
        )

    @property
    def subscription_expires_at(self) -> str | None:
        """Placeholder property that always raises."""
        raise _PlaceholderError(
            "License subscription expiration access requires Journiv Plus build"
        )

    @property
    def issued_at(self) -> str:
        """Placeholder property that always raises."""
        raise _PlaceholderError(
            "License issued_at access requires Journiv Plus build"
        )

    @property
    def verdict(self) -> dict[str, Any]:
        """Placeholder property that always raises."""
        raise _PlaceholderError(
            "License verdict access requires Journiv Plus build"
        )


# Minimal exports to prevent import errors
__all__ = [
    "PlusFeatureFactory",
]
