import os
from dataclasses import dataclass
from pathlib import Path

DEFAULT_PARQUET_PATH = Path(__file__).resolve().parents[2] / "data/samples/cams/eac4_provinces"


@dataclass(frozen=True)
class Settings:
    dashboard_data_source: str = "parquet"
    dashboard_parquet_path: Path = DEFAULT_PARQUET_PATH

    gold_trino_uri: str = "http://127.0.0.1:8083"
    gold_trino_user: str = "gold_api"
    gold_schema: str = "gold"
    gold_channel: str = "air_quality"

    @classmethod
    def from_env(cls) -> "Settings":
        return cls(
            gold_trino_uri=os.environ.get("GOLD_TRINO_URI", "http://127.0.0.1:8083"),
            gold_trino_user=os.environ.get("GOLD_TRINO_USER", "gold_api"),
            gold_schema=os.environ.get("GOLD_SCHEMA", "gold"),
            gold_channel=os.environ.get("GOLD_CHANNEL", "air_quality"),
            dashboard_data_source=os.environ.get("DASHBOARD_DATA_SOURCE", "parquet"),
            dashboard_parquet_path=Path(os.environ.get("DASHBOARD_PARQUET_PATH", str(DEFAULT_PARQUET_PATH))),
        )
