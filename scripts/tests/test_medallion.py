import json
from pathlib import Path
import sys
import tempfile
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from inventory_landing import discover, run, inspect

class InventoryTests(unittest.TestCase):
    def test_unknown_and_empty_sources_have_no_invented_normalization(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)/'landing';(root/'extra/daily').mkdir(parents=True);(root/'ERA5/single_levels').mkdir(parents=True)
            (root/'extra/daily/source.csv').write_text('date,index\n2026-01-01,20\n')
            data=run(root,Path(folder)/'report')['datasets']
            unknown=next(d for d in data if d['dataset_id']=='extra/daily')
            self.assertEqual(unknown['readiness'],'requires_adapter_review')
            self.assertIsNone(unknown['silver_adapter'])
            self.assertEqual(next(d for d in data if d['dataset_id'].startswith('ERA5'))['status'],'blocked_missing_source')
    def test_corrupt_json_and_csv_are_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'x.json';path.write_text('{')
            with self.assertRaises(ValueError):inspect(path)
            path=Path(folder)/'x.csv';path.write_text('a,b\n1,2,3\n')
            self.assertEqual(inspect(path)['status'],'failed')
    def test_symlinks_are_not_ingested(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);(root/'link').symlink_to('/tmp')
            with self.assertRaises(ValueError):list(discover(root))
    def test_hourly_contract_preserves_legacy(self):
        root=Path(__file__).resolve().parents[2]/'lakehouse/gold/contracts'
        old=json.loads((root/'cams-eac4-v1.json').read_text());new=json.loads((root/'cams-eac4-hourly-v1.json').read_text())
        self.assertEqual((old['source_resolution_minutes'],new['source_resolution_minutes']),(180,60))
        self.assertEqual(new['temporal_support'],'instantaneous')
        self.assertNotEqual(old['contract_version'],new['contract_version'])

class RunnerTests(unittest.TestCase):
    def test_independent_failures_and_empty_sources(self):
        from unittest.mock import patch
        import subprocess
        from run_medallion import execute
        with tempfile.TemporaryDirectory() as folder:
            def dataset(name,adapter):
                return dict(dataset_id=name,file_count=1,files=[dict(path=name+'/x',sha256='a',validation=dict(status='passed_structure'))],source_version='native',silver_adapter=adapter,gold_adapter='native_sources')
            inventory=dict(datasets=[dataset('bad/source','adapter.py'),dataset('good/source','adapter.py'),dict(dataset_id='ERA5/single_levels',file_count=0)])
            with patch('run_medallion.subprocess.run',side_effect=[subprocess.CompletedProcess([],1),subprocess.CompletedProcess([],0),subprocess.CompletedProcess([],0)]):
                result=execute(inventory,Path(folder)/'state.json')
            self.assertEqual([r['status'] for r in result],['failed','normalized','blocked_missing_source'])
            self.assertNotIn('silver',result[0])
            self.assertEqual(result[1]['silver']['exit_code'],0)

class RegistryTests(unittest.TestCase):
    def test_registry_never_guesses_emission_units_or_relabels_waqi(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)/'landing'
            for source in ['waqi/historical','climate_trace/climate_trace_vietnam']:(root/source).mkdir(parents=True)
            (root/'waqi/historical/x.csv').write_text('date,pm25\n2026-01-01,20\n')
            (root/'climate_trace/climate_trace_vietnam/x.csv').write_text('year,gas,value\n2025,co2,3\n')
            output=Path(folder)/'report';run(root,output)
            registry=json.loads((output/'variable-registry.json').read_text())
            self.assertEqual(next(r for r in registry if r['dataset_id']=='waqi/historical')['standard_unit'],'AQI')
            climate=next(r for r in registry if r['dataset_id'].startswith('climate_trace'))
            self.assertIsNone(climate['standard_unit']);self.assertFalse(climate['conversion_verified'])

class PublicationSafetyTests(unittest.TestCase):
    def test_failed_native_source_blocks_shared_native_publication(self):
        from unittest.mock import patch
        import subprocess
        from run_medallion import execute
        with tempfile.TemporaryDirectory() as folder:
            datasets=[dict(dataset_id=n,file_count=1,files=[dict(path=n+'/x',sha256='a',validation=dict(status='passed_structure'))],source_version='native',silver_adapter='adapter.py',gold_adapter='native_sources') for n in ('waqi/historical','climate_trace/climate_trace_vietnam')]
            with patch('run_medallion.subprocess.run',side_effect=[subprocess.CompletedProcess([],0),subprocess.CompletedProcess([],0),subprocess.CompletedProcess([],1)]) as call:
                results=execute(dict(datasets=datasets),Path(folder)/'state.json',gold=dict(schema='gold_test',start_date='2003-01-01',end_date='2003-01-02'))
            self.assertEqual(call.call_count,3)
            self.assertEqual(results[0]['gold']['status'],'blocked')
            self.assertEqual(results[1]['status'],'failed')
