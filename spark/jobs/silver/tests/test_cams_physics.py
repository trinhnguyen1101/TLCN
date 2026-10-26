"""Numerical tests independent of Spark/ecCodes, using documented SI inputs."""

import copy
import sys
import unittest
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from cams_physics import (
    CONTRACTS, GASES, L60_A, L60_B, air_density, gas_concentration,
    half_level_pressure, hybrid_coefficients, model_level_pressure,
    normalize_fields, virtual_temperature,
)
from test_cams_cube import messages


class CamsPhysicsTests(unittest.TestCase):
    def test_linear_conversions(self):
        for column, value, expected in (
            ("pm1", 1e-9, 1.), ("pm2p5", 1e-9, 1.), ("pm10", 1e-9, 1.),
            ("co_column", 1e-6, 1.), ("t_model", 300., 26.85), ("sp", 101325., 1013.25),
        ):
            with self.subTest(column=column):
                _, _, _, scale, offset = CONTRACTS[column]
                self.assertAlmostEqual(value * scale + offset, expected, places=10)

    def test_independent_half_and_full_pressure(self):
        self.assertAlmostEqual(float(half_level_pressure(100., .9, 100000.)), 90100.)
        a, b = np.array(L60_A), np.array(L60_B)
        full = model_level_pressure(np.array([100000., 80000.]), a, b)
        np.testing.assert_allclose(full, [99881.5, 79905.2], rtol=0, atol=1e-8)
        self.assertGreater(full[0], .997630 * 100000.)
        self.assertLess(full[0], 100000.)
        # Official pf uses unrounded B; the fallback table publishes B at 6dp.
        self.assertLess(abs(float(model_level_pressure(101325., a, b)) / 100. - 1012.0494), .0003)
        b[59] = .9976301193237305
        self.assertAlmostEqual(float(model_level_pressure(101325., a, b)) / 100., 1012.0494, places=4)
        b[59] = 1.1
        with self.assertRaisesRegex(ValueError, "between ordered"):
            model_level_pressure(100000., a, b)

    def test_virtual_temperature_and_density(self):
        # Independent arithmetic using epsilon=0.621981, not rounded 0.6078.
        self.assertAlmostEqual(float(virtual_temperature(300., .01)), 301.82329846088546, places=9)
        self.assertAlmostEqual(float(air_density(101325., 300., 0.)), 1.176624281484062, places=12)
        self.assertLess(float(air_density(101325., 300., .01)), float(air_density(101325., 300., 0.)))
        self.assertAlmostEqual(float(gas_concentration(2e-8, 1.2)), 24., places=12)

    def test_each_gas_uses_local_density_kelvin_and_no_column_conversion(self):
        source = messages()
        before = copy.deepcopy(source)
        result = normalize_fields(source)
        # Hand-computed with p=0.998815*sp and exact epsilon, per cell.
        expected = [23.362609600454148, 32.007083840848056]
        for column in GASES:
            np.testing.assert_allclose(result[column], expected, rtol=2e-7)
            np.testing.assert_allclose(result[column + "_column"], [1., 2.], rtol=1e-7)
        np.testing.assert_allclose(result["t_model"], [26.85, 16.85], rtol=1e-7)
        self.assertEqual(result["q_model"], np.array([.01, .02], dtype=np.float32).tolist())
        self.assertEqual(source, before)

    def test_zero_pm_is_a_valid_concentration(self):
        source = messages()
        for column in ("pm1", "pm2p5", "pm10"):
            source[column][3][0] = 0.
        result = normalize_fields(source)
        for column in ("pm1", "pm2p5", "pm10"):
            self.assertEqual(result[column][0], 0.)
            self.assertTrue(np.isfinite(result[column][0]))

    def test_grib_coefficients_take_precedence_when_another_model_field_has_no_pv(self):
        source = messages()
        for column in GASES | {"q_model"}:
            source[column][0]["pv"][120] = .9976301193237305
        source["t_model"][0].pop("pv")
        source["t_model"][0]["NV"] = 0
        result = normalize_fields(source)
        expected = 2e-8 * (101325. * (1 + .9976301193237305) / 2) / (
            287.05 * 300. * (1 + (1 - .621981) / .621981 * .01)) * 1e9
        self.assertAlmostEqual(result["co"][0], expected, places=5)

    def test_prefers_grib_and_rejects_wrong_or_malformed_coefficients(self):
        pv = list(L60_A) + list(L60_B)
        pv[120] = .9976301193237305
        a, b, method = hybrid_coefficients({"NV": 122, "pv": pv})
        self.assertEqual(method, "grib_pv_l60")
        self.assertEqual(b[59], pv[120])
        self.assertEqual(len(a), 61)
        self.assertEqual(hybrid_coefficients({})[2], "ecmwf_l60_table_6dp")
        invalid = [
            {"NV": 122}, {"NV": 276, "pv": [0.] * 276}, {"pv": list(reversed(pv))},
            {"pv": pv[:59] + [float("nan")] + pv[60:]},
            {"pv": [x / 100 for x in L60_A] + list(L60_B)},
            {"NV": 0, "pv": pv},
        ]
        for metadata in invalid:
            with self.subTest(metadata=str(metadata)[:50]), self.assertRaises(ValueError):
                hybrid_coefficients(metadata)

    def test_invalid_meteorology_and_missing_values(self):
        for column, invalid in {
            "sp": [None, float("nan"), float("inf"), 0., -1.],
            "t_model": [None, float("nan"), float("inf"), 0., -1.],
            "q_model": [None, float("nan"), float("inf"), -.001, 1., 2.],
            "co": [None, float("nan"), float("inf"), -1., 1.1],
            "pm10": [-1., float("inf")],
        }.items():
            for value in invalid:
                with self.subTest(column=column, value=value), self.assertRaises(ValueError):
                    source = messages()
                    source[column][3][0] = value
                    normalize_fields(source)

    def test_missing_fields_shapes_coefficients_and_units_fail_closed(self):
        source = messages()
        del source["sp"]
        with self.assertRaises(ValueError):
            normalize_fields(source)
        source = messages()
        source["co"][3].append(1.)
        with self.assertRaises(ValueError):
            normalize_fields(source)
        source = messages()
        source["co"][0]["pv"][120] += .0000001
        with self.assertRaisesRegex(ValueError, "conflicting L60"):
            normalize_fields(source)
        for column in ("co", "pm10", "t_model", "sp", "aod550"):
            with self.subTest(column=column), self.assertRaises(ValueError):
                source = messages()
                source[column][0]["units"] = "already_converted"
                normalize_fields(source)


if __name__ == "__main__":
    unittest.main()
