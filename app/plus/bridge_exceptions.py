"""
Exception hierarchy for bridge operations.

These exceptions are raised by the host bridge implementation when
operations fail. Plus features should handle these gracefully.

The exception hierarchy allows for granular error handling:
- BridgeError: Base class for all bridge-related errors
- BridgeDataError: Data query/fetch failures
- BridgeAuthError: Authorization/authentication failures
"""


class BridgeError(Exception):
    """
    Base exception for all bridge-related errors.

    All bridge-specific exceptions inherit from this class,
    allowing for catch-all error handling when needed.
    """
    pass


class BridgeDataError(BridgeError):
    """
    Raised when a bridge data query fails.

    This could be due to:
    - Database query errors
    - Invalid query parameters
    - Data not found
    - SQL execution failures

    Example:
        try:
            tags = bridge.fetch_tags_with_usage()
        except BridgeDataError as e:
            logger.error(f"Failed to fetch tags: {e}")
            # Handle gracefully
    """
    pass


class BridgeAuthError(BridgeError):
    """
    Raised when a bridge operation lacks proper authorization.

    This should rarely happen if the bridge is properly scoped
    to a user_id during initialization, but serves as defense in depth.

    Example scenarios:
    - User session expired
    - Invalid user_id
    - Insufficient permissions
    """
    pass


__all__ = ["BridgeError", "BridgeDataError", "BridgeAuthError"]
