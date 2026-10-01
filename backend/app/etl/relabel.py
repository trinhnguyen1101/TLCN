"""Publish corrected region labels without recalculating unchanged observations."""
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import shutil
import uuid

import pyarrow as pa
import pyarrow.parquet as pq

from app.core.config import DEFAULT_PARQUET_PATH
from app.etl.eac4 import DEFAULT_BOUNDARIES
from app.etl.spatial import load_provinces


def publish_labels(output: Path = DEFAULT_PARQUET_PATH, boundaries: Path = DEFAULT_BOUNDARIES):
    output = Path(output)
    old_id = (output / "CURRENT").read_text(encoding="ascii").strip()
    old = output / "runs" / old_id
    manifest = json.loads((old / "manifest.json").read_text(encoding="utf-8"))
    provinces, _ = load_provinces(Path(boundaries))
    names = {province.code: province.name for province in provinces}
    stored = {item["code"]: item for item in manifest["provinces"]}
    if names.keys() != stored.keys() or any(
        abs(province.area_m2 - stored[code]["area_m2"]) > 1
        for code, province in ((p.code, p) for p in provinces)
    ):
        raise ValueError("Region geometry or identifiers changed; run the full EAC4 ETL")
    changed = {code: name for code, name in names.items() if name != stored[code]["name"]}
    if not changed:
        return old_id

    generation = uuid.uuid4().hex
    staging = output / f".staging-{generation}"
    staging.mkdir()
    for folder in ("weights", "observations"):
        source = old / folder
        if source.exists():
            shutil.copytree(source, staging / folder, copy_function=os.link)
    monthly = staging / "monthly"
    monthly.mkdir()
    for file in sorted((old / "monthly").glob("*.parquet")):
        table = pq.read_table(file)
        rows = table.to_pylist()
        for row in rows:
            if row["province_code"] in changed:
                row["province_name"] = changed[row["province_code"]]
        pq.write_table(pa.Table.from_pylist(rows, schema=table.schema), monthly / file.name,
                       compression="zstd")
    for code, name in changed.items():
        stored[code]["name"] = name
    manifest.update(generation=generation, created_at=datetime.now(timezone.utc).isoformat(),
                    parent_generation=old_id, label_changes=changed)
    (staging / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2),
                                           encoding="utf-8")
    staged_run = output / "runs" / generation
    staging.rename(staged_run)
    pointer = output / f".CURRENT-{generation}"
    pointer.write_text(generation + "\n", encoding="ascii")
    pointer.replace(output / "CURRENT")
    return generation


if __name__ == "__main__":
    print(publish_labels())
