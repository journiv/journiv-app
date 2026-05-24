# Import all models for easy access
from .activity import Activity
from .activity_group import ActivityGroup
from .analytics import WritingStreak
from .base import BaseModel
from .entry import Entry
from .export_job import ExportJob
from .external_identity import ExternalIdentity
from .goal import Goal, GoalLog
from .goal_category import GoalCategory
from .immich_asset_face import ImmichAssetFace
from .import_job import ImportJob
from .instance_detail import InstanceDetail
from .integration import Integration
from .journal import Journal
from .moment import Moment, MomentMedia, MomentMoodActivity
from .moment_person_link import MomentPersonLink
from .moment_tag_link import MomentTagLink
from .mood import Mood
from .mood_group import MoodGroup, MoodGroupLink
from .person import Person
from .person_external_identity import PersonExternalIdentity
from .person_group import PersonGroup
from .person_group_link import PersonGroupLink
from .prompt import Prompt
from .tag import Tag
from .user import User, UserSettings

__all__ = [
    "BaseModel",
    "User",
    "UserSettings",
    "Journal",
    "Entry",
    "MomentMedia",
    "Mood",
    "Prompt",
    "Tag",
    "Person",
    "PersonExternalIdentity",
    "ImmichAssetFace",
    "PersonGroup",
    "PersonGroupLink",
    "MomentTagLink",
    "MomentPersonLink",
    "WritingStreak",
    "ExternalIdentity",
    "ImportJob",
    "ExportJob",
    "InstanceDetail",
    "Integration",
    "Activity",
    "ActivityGroup",
    "Goal",
    "GoalLog",
    "GoalCategory",
    "Moment",
    "MomentMoodActivity",
    "MoodGroup",
    "MoodGroupLink",
]
