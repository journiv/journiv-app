"""
Enums and constants for the application.
"""
from enum import Enum


class MediaType(str, Enum):
    """Media types for journal entries."""
    IMAGE = "image"
    VIDEO = "video"
    AUDIO = "audio"
    UNKNOWN = "unknown"


class UploadStatus(str, Enum):
    """Upload status for media files."""
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


class MoodCategory(str, Enum):
    """Mood categories."""
    POSITIVE = "positive"
    NEGATIVE = "negative"
    NEUTRAL = "neutral"


class PromptCategory(str, Enum):
    """Categories for journaling prompts."""
    # Self-awareness & emotional growth
    GRATITUDE = "gratitude"
    REFLECTION = "reflection"
    EMOTIONS = "emotions"
    MINDFULNESS = "mindfulness"
    SELF_DISCOVERY = "self_discovery"

    # Goals & productivity
    GOALS = "goals"
    PRODUCTIVITY = "productivity"
    GROWTH = "growth"  # personal/professional improvement

    # Relationships & connection
    RELATIONSHIPS = "relationships"
    FAMILY = "family"
    LOVE = "love"
    SOCIAL = "social"

    # Creativity & imagination
    CREATIVITY = "creativity"
    DREAMS = "dreams"
    MEMORIES = "memories"

    # Well-being
    SELF_CARE = "self_care"
    HEALTH = "health"
    SPIRITUALITY = "spirituality"

    # Misc / catch-all
    GENERAL = "general"


class Theme(str, Enum):
    """UI themes."""
    LIGHT = "light"
    DARK = "dark"
    AUTO = "auto"


class TokenType(str, Enum):
    """JWT token types."""
    ACCESS = "access"
    REFRESH = "refresh"


class UserRole(str, Enum):
    """User roles for authorization."""
    ADMIN = "admin"
    USER = "user"


class JournalColor(str, Enum):
    """Preset colors for journals."""
    RED = "#EF4444"
    ORANGE = "#F97316"
    AMBER = "#F59E0B"
    YELLOW = "#EAB308"
    LIME = "#84CC16"
    GREEN = "#22C55E"
    EMERALD = "#10B981"
    TEAL = "#14B8A6"
    CYAN = "#06B6D4"
    SKY = "#0EA5E9"
    BLUE = "#3B82F6"
    INDIGO = "#6366F1"
    VIOLET = "#8B5CF6"
    PURPLE = "#A855F7"
    FUCHSIA = "#D946EF"
    PINK = "#EC4899"
    ROSE = "#F43F5E"
    SLATE = "#64748B"
    GRAY = "#6B7280"
    ZINC = "#71717A"
    NEUTRAL = "#737373"
    STONE = "#78716C"


class GoalType(str, Enum):
    """Goal direction."""
    ACHIEVE = "achieve"
    AVOID = "avoid"


class GoalFrequency(str, Enum):
    """Goal frequency."""
    DAILY = "daily"
    WEEKLY = "weekly"
    MONTHLY = "monthly"


class GoalLogStatus(str, Enum):
    """Goal log status for a period."""
    SUCCESS = "success"
    FAIL = "fail"
    SKIPPED = "skipped"


class GoalLogSource(str, Enum):
    """Goal log origin."""
    AUTO = "auto"
    MANUAL = "manual"


class JobStatus(str, Enum):
    """Status for import/export jobs."""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    PARTIAL = "partial"
    FAILED = "failed"
    CANCELLED = "cancelled"


class ImportSourceType(str, Enum):
    """Source types for imports."""
    JOURNIV = "journiv"
    MARKDOWN = "markdown"
    DAYONE = "dayone"
    IMMICH = "immich"


class ExportType(str, Enum):
    """Types of exports."""
    FULL = "full"  # Full user export
    JOURNAL = "journal"  # Single journal export
