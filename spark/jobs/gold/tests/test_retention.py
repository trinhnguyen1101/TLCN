from datetime import datetime,timezone
import json
from pathlib import Path
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from retention import references,dry_run

class RetentionTests(unittest.TestCase):
    def test_input_rollback_registry_head_and_tags_are_never_candidates(self):
        prefix='nessie.gold_test.'
        releases=[dict(release_id='r1',input_snapshots_json=json.dumps({'nessie.silver.input':1}),output_snapshots_json=json.dumps({'fact':10}))]
        timeline=dict(timeline_id='old-view',manifest_json=json.dumps(dict(version=2,series_catalog={},segments=[dict(release_id='r1',snapshots={'fact':11})])))
        refs=references(prefix,iter(releases),iter([timeline]))
        records=[dict(table=t,snapshot_id=s,committed_at='2020-01-01T00:00:00Z',is_head=head,named_refs=tag) for t,s,head,tag in [
            ('nessie.silver.input',1,False,[]),('nessie.silver.input',2,False,[]),
            (prefix+'fact',10,False,[]),(prefix+'fact',11,False,[]),
            (prefix+'fact',12,True,[]),(prefix+'fact',13,False,['rollback_tag']),(prefix+'fact',14,False,[])]]
        report=dry_run(refs,records,now=datetime(2026,1,1,tzinfo=timezone.utc))
        self.assertTrue(report['inventory_complete'])
        self.assertEqual([r['snapshot_id'] for r in report['unreferenced_snapshot_review_candidates']],[14])
        self.assertEqual(report['delete_candidates'],[])
        self.assertFalse(report['cleanup_enabled'])
    def test_incomplete_inventory_and_unknown_release_fail_closed(self):
        refs=references('nessie.gold_test.',[dict(release_id='r',input_snapshots_json='{}',output_snapshots_json='{"fact":1}')],[])
        report=dry_run(refs,[dict(table='nessie.gold_test.fact',snapshot_id=2,committed_at='2020-01-01T00:00:00Z')])
        self.assertFalse(report['inventory_complete']);self.assertEqual(report['unreferenced_snapshot_review_candidates'],[])
    def test_recent_stage_is_held_for_review_not_deleted(self):
        refs=references('nessie.gold_test.',[],[])
        row=dict(table='nessie.gold_test.fact',snapshot_id=1,committed_at='2026-01-01T00:00:00Z')
        report=dry_run(refs,[row],now=datetime(2026,1,2,tzinfo=timezone.utc))
        self.assertEqual(len(report['recent_unreferenced']),1)
        self.assertEqual(report['delete_candidates'],[])
