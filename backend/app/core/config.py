import os
from dataclasses import dataclass
from pathlib import Path

DEFAULT_PARQUET_PATH = Path(__file__).resolve().parents[2] / "data/samples/cams/eac4_provinces"


@dataclass(frozen=True)
class Settings:
    dashboard_data_source: str = "parquet"
    dashboard_parquet_path: Path = DEFAULT_PARQUET_PATH

    @classmethod
    def from_env(cls) -> "Settings":
        return cls(
            dashboard_data_source=os.environ.get("DASHBOARD_DATA_SOURCE", "parquet"),
            dashboard_parquet_path=Path(os.environ.get("DASHBOARD_PARQUET_PATH", str(DEFAULT_PARQUET_PATH))),
        )
