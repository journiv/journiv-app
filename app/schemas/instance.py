from typing import List, Optional

from pydantic import BaseModel


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
