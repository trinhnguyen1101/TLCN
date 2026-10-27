"""Contract tests for the private Storage manifest and immutable raw bytes."""

import hashlib
import json
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))
import supabase_to_bronze as bronze


class SupabaseBronzeContract(unittest.TestCase):
    def fixture(self):
        hour = "2026-10-26T04:00:00.000Z"
        run_id = "00000000-0000-4000-8000-000000000001"
        prefix = "waqi/2026/10/26/04/" + run_id
        raw = b'{"status":"ok","data":{"idx":123}}'
        record = {"requested_source_uid": "123", "outcome": "valid", "raw_stored": True,
                  "raw_object_path": prefix + "/123.raw.json",
                  "payload_sha256": hashlib.sha256(raw).hexdigest()}
        manifest = {"source": "waqi", "collection_run_id": run_id, "scheduled_hour_utc": hour,
                    "attempt_number": 1, "status": "succeeded", "expected_records": 1,
                    "successful_records": 1, "failed_records": 0, "records": [record]}
        raw_manifest = json.dumps(manifest).encode()
        run = {"run_id": run_id, "scheduled_hour_utc": hour, "attempt_number": 1,
               "status": "succeeded", "expected_records": 1, "successful_records": 1, "failed_records": 0,
               "manifest_object_path": prefix + "/manifest.json",
               "manifest_sha256": hashlib.sha256(raw_manifest).hexdigest()}
        return run, {run["manifest_object_path"]: raw_manifest, record["raw_object_path"]: raw}

    def test_verified_inventory_and_stable_fingerprint(self):
        run, blobs = self.fixture()
        with patch.object(bronze, "storage_get", side_effect=lambda _, __, path: blobs[path]):
            objects, fingerprint = bronze.inventory([run], "waqi", "unused", "unused")
            second, repeat = bronze.inventory([run], "waqi", "unused", "unused")
        self.assertEqual(len(objects), 2)
        self.assertEqual(fingerprint, repeat)
        self.assertEqual(objects, second)

    def test_changed_raw_or_manifest_is_rejected(self):
        run, blobs = self.fixture()
        raw_path = next(path for path in blobs if path.endswith("raw.json"))
        blobs[raw_path] = b"changed"
        with patch.object(bronze, "storage_get", side_effect=lambda _, __, path: blobs[path]):
            with self.assertRaisesRegex(ValueError, "SHA-256"):
                bronze.inventory([run], "waqi", "unused", "unused")
        run["manifest_sha256"] = "0" * 64
        with patch.object(bronze, "storage_get", side_effect=lambda _, __, path: blobs[path]):
            with self.assertRaisesRegex(ValueError, "manifest SHA-256"):
                bronze.inventory([run], "waqi", "unused", "unused")

    def test_cross_run_path_is_rejected(self):
        run, blobs = self.fixture()
        manifest = json.loads(blobs[run["manifest_object_path"]])
        manifest["records"][0]["raw_object_path"] = manifest["records"][0]["raw_object_path"].replace(
            "00000000-0000-4000-8000-000000000001", "00000000-0000-4000-8000-000000000002")
        blobs[run["manifest_object_path"]] = json.dumps(manifest).encode()
        run["manifest_sha256"] = hashlib.sha256(blobs[run["manifest_object_path"]]).hexdigest()
        with patch.object(bronze, "storage_get", side_effect=lambda _, __, path: blobs[path]):
            with self.assertRaisesRegex(ValueError, "outside"):
                bronze.inventory([run], "waqi", "unused", "unused")


if __name__ == "__main__":
    unittest.main()
