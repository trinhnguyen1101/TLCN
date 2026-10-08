"""Publish a portable sample with native rows from the last two source years.

Run after EAC4 conversion. Monthly history and native scientific values are
copied unchanged; no interpolation of monthly averages is performed.
"""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import shutil
import uuid

import pyarrow.parquet as pq

from app.core.config import DEFAULT_PARQUET_PATH


def publish_sample(output: Path = DEFAULT_PARQUET_PATH, years: int = 2, source_generation: str | None = None):
    if years < 0:
        raise ValueError("years must be nonnegative (0 keeps the full native history)")
    output = Path(output)
    parent = source_generation or (output / "CURRENT").read_text(encoding="ascii").strip()
    if not re.fullmatch(r"[a-f0-9]{32}", parent):
        raise ValueError("Invalid source generation")
    old = output / "runs" / parent
    manifest = json.loads((old / "manifest.json").read_text(encoding="utf-8"))
    last_year = max(datetime.fromisoformat(s["end"]).year for s in manifest["sources"])
    first_year = min(datetime.fromisoformat(s["start"]).year for s in manifest["sources"]) if years == 0 else last_year - years + 1
    generation = uuid.uuid4().hex
    staging = output / f".staging-{generation}"
    staging.mkdir()
    shutil.copytree(old / "monthly", staging / "monthly")
    total = 0
    for source in manifest["sources"]:
        for year in range(first_year, last_year + 1):
            partition = old / "observations" / source["name"] / str(year)
            if not partition.exists():
                raise ValueError(f"Missing {partition}; run the EAC4 conversion first")
            destination = staging / "observations" / source["name"] / str(year)
            shutil.copytree(partition, destination)
            total += sum(pq.ParquetFile(p).metadata.num_rows for p in destination.glob("*.parquet"))
    manifest.update(generation=generation, parent_generation=parent,
                    created_at=datetime.now(timezone.utc).isoformat(),
                    observation_start=f"{first_year}-01-01T00:00:00+00:00",
                    observation_end=max(s["end"] for s in manifest["sources"]),
                    observation_rows=total,
                    sample_policy=f"Unchanged native observations from {first_year}–{last_year}; full monthly history")
    (staging / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    staging.rename(output / "runs" / generation)
    pointer = output / f".CURRENT-{generation}"
    pointer.write_text(generation + "\n", encoding="ascii")
    pointer.replace(output / "CURRENT")
    return manifest


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_PARQUET_PATH)
    parser.add_argument("--years", type=int, default=2)
    parser.add_argument("--source-generation", help="Read an existing full ETL generation instead of CURRENT")
    args = parser.parse_args()
    print(json.dumps(publish_sample(args.output_dir, args.years, args.source_generation), ensure_ascii=False, indent=2))
