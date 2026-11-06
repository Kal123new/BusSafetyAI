import os
import tempfile
from dataclasses import dataclass
from pathlib import Path
from .storage import data_directory


@dataclass(frozen=True)
class Settings:
    database_url: str
    mode: str = "production"
    model_path: str = ""
    confidence: float = 0.45
    osrm_url: str = ""
    ntfy_url: str = ""
    ntfy_token: str = ""
    tile_url: str = ""
    tile_attribution: str = ""
    public_demo_services: bool = False
    public_live_locations: bool = False
    max_upload_bytes: int = 5 * 1024 * 1024
    require_model: bool = False

    @classmethod
    def from_env(cls):
        path = data_directory()
        return cls(
            database_url=os.getenv("DATABASE_URL", f"sqlite:///{path.as_posix()}/safesense.db"),
            mode=os.getenv("SAFESENSE_MODE", "production"),
            model_path=os.getenv("YOLO_MODEL_PATH", ""),
            confidence=float(os.getenv("YOLO_CONFIDENCE", "0.45")),
            osrm_url=os.getenv("OSRM_URL", "").rstrip("/"),
            ntfy_url=os.getenv("NTFY_URL", "").rstrip("/"),
            ntfy_token=os.getenv("NTFY_TOKEN", ""),
            tile_url=os.getenv("MAP_TILE_URL", ""),
            tile_attribution=os.getenv("MAP_TILE_ATTRIBUTION", ""),
            require_model=os.getenv('SAFESENSE_REQUIRE_MODEL', 'false').lower() == 'true',
        )

    def __post_init__(self):
        if self.mode not in {"demo", "production"}:
            raise ValueError("SAFESENSE_MODE must be demo or production")
        if not 0 < self.confidence <= 1:
            raise ValueError("YOLO_CONFIDENCE must be between 0 and 1")
