import sys
from pathlib import Path
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from timeline import overlay,gaps


def item(lo,hi,release='a',lane='v1',withdrawn=False):
    return dict(start=lo+'T17:00:00+00:00',end=hi+'T17:00:00+00:00',release_id=release,compatibility_id=lane,withdrawn=withdrawn)

class TimelineTests(unittest.TestCase):
    def test_three_chunks_cross_year_correction_and_missing(self):
        m={}
        for lo,hi,r in [('2025-12-29','2025-12-30','a'),('2025-12-30','2025-12-31','b'),('2025-12-31','2026-01-01','c')]:m=overlay(m,item(lo,hi,r))
        old=m
        m=overlay(m,item('2025-12-29','2025-12-31','corrected'))
        self.assertEqual([s['release_id'] for s in m['segments']],['corrected','c'])
        self.assertEqual(len(old['segments']),3)
        m=overlay(m,item('2025-12-30','2025-12-31',withdrawn=True))
        missing=gaps(m['segments'],'2025-12-29T17:00:00Z','2026-01-02T17:00:00Z')
        self.assertEqual([s['reason'] for s in missing],['withdrawn_scope','unpublished_scope'])
    def test_incompatible_lane_never_overwrites(self):
        m=overlay({},item('2025-12-29','2026-01-01'))
        m=overlay(m,item('2025-12-30','2025-12-31',lane='geometry2'))
        self.assertEqual(len(m['segments']),2)
    def test_overlap_splits_preserves_deletion_scope(self):
        m=overlay({},item('2025-12-29','2026-01-01'))
        m=overlay(m,item('2025-12-30','2025-12-31','empty-correction'))
        self.assertEqual([s['release_id'] for s in m['segments']],['a','empty-correction','a'])
        for left,right in zip(m['segments'],m['segments'][1:]):self.assertLessEqual(left['end'],right['start'])
if __name__=='__main__':unittest.main()

class ManifestCodecTests(unittest.TestCase):
    def test_dictionary_encoding_preserves_scopes_snapshots_and_v1(self):
        from timeline import pack_manifest,unpack_manifest
        import json
        entries=[]
        for i in range(20):
            entry=item('2025-12-29','2026-01-01',str(i))
            entry['snapshots']={'mart_air_quality_hourly':100+i}
            entry['series']=[dict(series_id='b',source_system='test'),dict(series_id='a',source_system='test')]
            entries.append(entry)
        original=dict(version=1,segments=entries,activated_releases=['a'])
        packed=pack_manifest(original);decoded=unpack_manifest(packed)
        self.assertEqual(packed['version'],2)
        self.assertEqual(len(packed['series_catalog']),1)
        self.assertLess(len(json.dumps(packed)),len(json.dumps(original)))
        for a,b in zip(original['segments'],decoded['segments']):
            self.assertEqual(a['snapshots'],b['snapshots']);self.assertEqual(a['start'],b['start'])
            self.assertEqual(sorted(a['series'],key=lambda s:s['series_id']),b['series'])
        self.assertEqual(original['version'],1)
        self.assertIs(unpack_manifest(original),original)
    def test_missing_catalog_reference_rejected(self):
        from timeline import unpack_manifest
        with self.assertRaises(ValueError):unpack_manifest(dict(version=2,series_catalog={},segments=[dict(series_ref='bad')]))
