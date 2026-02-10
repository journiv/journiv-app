"""
Custom application exceptions.
"""

class JournivAppException(Exception):
    """Base exception for the journal app."""
    pass


class UserNotFoundError(JournivAppException):
    """Raised when a user is not found."""
    pass


class UserAlreadyExistsError(JournivAppException):
    """Raised when a user already exists."""
    pass


class InvalidCredentialsError(JournivAppException):
    """Raised when credentials are invalid."""
    pass


class JournalNotFoundError(JournivAppException):
    """Raised when a journal is not found."""
    pass


class EntryNotFoundError(JournivAppException):
    """Raised when an entry is not found."""
    pass


class MoodNotFoundError(JournivAppException):
    """Raised when a mood is not found."""
    pass


class MoodAlreadyExistsError(JournivAppException):
    """Raised when a mood already exists."""
    pass


class PromptNotFoundError(JournivAppException):
    """Raised when a prompt is not found."""
    pass


class MediaNotFoundError(JournivAppException):
    """Raised when a media file is not found."""
    pass


class FileTooLargeError(JournivAppException):
    """Raised when uploaded file exceeds size limit."""
    pass


class InvalidFileTypeError(JournivAppException):
    """Raised when file type is not supported."""
    pass


class InvalidMediaTypeError(JournivAppException):
    """Raised when media type is invalid or unrecognized."""
    pass


class FileValidationError(JournivAppException):
    """Raised when file validation fails."""
    pass


class TagNotFoundError(JournivAppException):
    """Raised when a tag is not found."""
    pass


class UnauthorizedError(JournivAppException):
    """Raised when user is not authorized."""
    pass


class UserSettingsNotFoundError(JournivAppException):
    """Raised when user settings are not found."""
    pass


class FileProcessingError(JournivAppException):
    """Raised when file processing fails."""
    pass


class TokenNotFoundError(JournivAppException):
    """Raised when a token is not found."""
    pass


class TokenAlreadyRevokedError(JournivAppException):
    """Raised when a token is already revoked."""
    pass


class ValidationError(JournivAppException):
    """Raised when validation fails."""
    pass


class LicenseResetInstallIdMismatchError(JournivAppException):
    """Raised when license reset install_id does not match this instance."""
    pass


class LicenseResetEmailMismatchError(JournivAppException):
    """Raised when license reset email verification fails."""
    pass


class LicenseResetRateLimitedError(JournivAppException):
    """Raised when license reset is rate limited by upstream."""

    def __init__(self, retry_after: int):
        super().__init__("Rate limit exceeded")
        self.retry_after = retry_after
