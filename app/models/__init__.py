# Import all models for easy access
from .analytics import WritingStreak
from .base import BaseModel
from .entry import Entry, EntryMedia
from .entry_tag_link import EntryTagLink
from .external_identity import ExternalIdentity
from .journal import Journal
from .mood import Mood, MoodLog
from .prompt import Prompt
from .tag import Tag
from .user import User, UserSettings

__all__ = [
    "BaseModel",
    "User",
    "UserSettings",
    "Journal",
    "Entry",
    "EntryMedia",
    "Mood",
    "MoodLog",
    "Prompt",
    "Tag",
    "EntryTagLink",
    "WritingStreak",
    "ExternalIdentity",
]
