from typing import List, Optional

from pydantic import BaseModel


class PlusCapability(BaseModel):
    """
    Public, non-sensitive summary of this instance's Journiv Plus capability.

    Lets the frontend gate Plus-only surfaces (e.g. tag analytics) without
    probing a protected endpoint and interpreting its error codes. Contains
    only capability flags — never install_id, registered email, expiry or the
    signed license blob (those stay on the admin-only /instance/license/info).
    """

    available: bool  # Plus code is deployable here (binary loaded, or proxy configured)
    tier: str  # "member" (unlicensed / invalid), "supporter" or "believer"
    upgrade_url: str  # Where to learn about / buy Journiv Plus


class InstanceConfigResponse(BaseModel):
    """Public instance configuration safe for frontend consumption."""

    import_export_max_file_size_mb: int
    max_file_size_mb: int
    allowed_media_types: Optional[List[str]] = None
    allowed_file_extensions: Optional[List[str]] = None
    disable_signup: bool
    immich_base_url: Optional[str] = None
    oidc_enabled: bool  # Whether OIDC authentication is available
    oidc_only: bool  # Whether OIDC is the only allowed authentication method
    plus: PlusCapability
