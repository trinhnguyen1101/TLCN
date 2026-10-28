import unittest
from app.repositories.gold.colors import concentration_metadata

class ColorTests(unittest.TestCase):
    def test_six_fixed_unit_specific_scales(self):
        first=concentration_metadata('hourly_native_samples')
        self.assertEqual(len(first),6)
        self.assertNotEqual(first['co'].map_scale.breakpoints,first['pm25'].map_scale.breakpoints)
        for metadata in first.values():
            self.assertEqual(metadata.unit,'µg/m³')
            self.assertEqual(metadata.map_scale.version,'analytical-concentration-colors-v1')
            self.assertEqual(metadata.map_scale.sample_count,0) # fixed domains, not quantile estimates
            self.assertEqual(len(metadata.map_scale.breakpoints),3)
        self.assertEqual(first['pm25'].map_scale.breakpoints,concentration_metadata('daily_available_sample_mean')['pm25'].map_scale.breakpoints)
