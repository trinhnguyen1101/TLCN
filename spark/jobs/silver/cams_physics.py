"""EAC4 L60 pressure and SI conversions; all calculations use float64.

Coefficient reference (retrieved 2026-10-26), half-level indices 0..60:
https://confluence.ecmwf.int/spaces/UDOC/pages/108117131/L60+model+level+definitions
The published table rounds A [Pa] and B [1] to six decimal places. GRIB pv
retains more precision and takes precedence after comparison with this table.
"""

import hashlib
import json

import numpy as np


L60_SOURCE = "https://confluence.ecmwf.int/spaces/UDOC/pages/108117131/L60+model+level+definitions"
L60_A_ATOL_PA = 2e-3  # Archived 2013-2016 GRIB pv values are quantized to this precision.
RD = 287.05  # J kg-1 K-1
EPSILON = 0.621981
GASES = {"co", "no2", "so2", "o3"}
MODEL_FIELDS = GASES | {"t_model", "q_model"}
L60_A = (
    0, 20, 38.425343, 63.647804, 95.636963, 134.483307, 180.584351,
    234.779053, 298.495789, 373.971924, 464.618134, 575.651001,
    713.218079, 883.660522, 1094.834717, 1356.474609, 1680.640259,
    2082.273926, 2579.888672, 3196.421631, 3960.291504, 4906.708496,
    6018.019531, 7306.631348, 8765.053711, 10376.126953, 12077.446289,
    13775.325195, 15379.805664, 16819.474609, 18045.183594, 19027.695313,
    19755.109375, 20222.205078, 20429.863281, 20384.480469, 20097.402344,
    19584.330078, 18864.750000, 17961.357422, 16899.468750, 15706.447266,
    14411.124023, 13043.218750, 11632.758789, 10209.500977, 8802.356445,
    7438.803223, 6144.314941, 4941.778320, 3850.913330, 2887.696533,
    2063.779785, 1385.912598, 855.361755, 467.333588, 210.393890,
    65.889244, 7.367743, 0, 0,
)
L60_B = (
    *(0.0 for _ in range(24)),
    .000076, .000461, .001815, .005081, .011143, .020678, .034121,
    .051690, .073534, .099675, .130023, .164384, .202476, .243933,
    .288323, .335155, .383892, .433963, .484772, .535710, .586168,
    .635547, .683269, .728786, .771597, .811253, .847375, .879657,
    .907884, .931940, .951822, .967645, .979663, .988270, .994019,
    .997630, 1.0,
)

# Native unit is checked before applying any conversion. Gas scales cannot be
# represented by a constant: rho varies with both grid point and valid time.
# column: native unit, quantity kind, standard unit, scale, offset
CONTRACTS = {
    **{c: ("kg m**-3", "mass_concentration", "ug/m3", 1e9, 0.)
       for c in ("pm1", "pm2p5", "pm10")},
    **{c: ("kg kg**-1", "mass_concentration", "ug/m3", None, None) for c in GASES},
    **{c: ("kg m**-2", "column_mass", "mg/m2", 1e6, 0.)
       for c in ("co_column", "no2_column", "so2_column", "o3_column")},
    **{c: ("K", "temperature", "degC", 1., -273.15) for c in ("t2m", "d2m", "t_model")},
    **{c: ("Pa", "pressure", "hPa", .01, 0.) for c in ("sp", "mslp")},
    **{c: ("m s**-1", "wind_component", "m/s", 1., 0.) for c in ("u10", "v10")},
    "q_model": ("kg kg**-1", "specific_humidity", "kg/kg", 1., 0.),
    "aod550": ("~", "optical_depth", "1", 1., 0.),
}


def finite(values, name):
    result = np.asarray(values, dtype=np.float64)
    if not np.all(np.isfinite(result)):
        raise ValueError(f"{name}: null/NaN/Infinity")
    return result


def positive(values, name):
    result = finite(values, name)
    if np.any(result <= 0):
        raise ValueError(f"{name}: must be positive")
    return result


def hybrid_coefficients(metadata):
    """Return validated A/B, preferring pv=[A0..A60,B0..B60].

    A present but invalid pv is an error, never grounds for silent fallback.
    Only absence (NV=0 or no NV/pv) permits the published L60 table.
    """
    pv = metadata.get("pv")
    nv = metadata.get("NV")
    if pv is None:
        if nv not in (None, 0):
            raise ValueError("L60: NV declares coefficients but pv is missing")
        return np.array(L60_A), np.array(L60_B), "ecmwf_l60_table_6dp"
    pv = finite(pv, "L60 pv")
    if pv.shape != (122,) or (nv is not None and int(nv) != 122):
        raise ValueError("L60 requires 122 pv coefficients (61 A followed by 61 B), not L137")
    a, b = pv[:61], pv[61:]
    if (not np.allclose(a, L60_A, rtol=0, atol=L60_A_ATOL_PA)
            or not np.allclose(b, L60_B, rtol=0, atol=5.1e-7)):
        raise ValueError("GRIB pv does not match the official ECMWF L60 coefficients in Pa")
    return a, b, "grib_pv_l60"


def coefficient_provenance(metadata):
    a, b, source = hybrid_coefficients(metadata)
    payload = dict(source=source, reference=L60_SOURCE, half_level_indices=[59, 60],
                   a_pa=a.tolist(), b=b.tolist())
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    # Identify the validated physical coefficient family, not the exact binary
    # representation found in one GRIB message. ECMWF archive messages from
    # 2013-2016 quantize some A coefficients slightly differently while still
    # representing the same official L60 definition.
    identity = json.dumps(
        dict(family="ecmwf_l60", reference=L60_SOURCE,
             a_pa=list(L60_A), b=list(L60_B)),
        sort_keys=True,
        separators=(",", ":"),
    )
    return encoded, hashlib.sha256(identity.encode()).hexdigest()


def aligned_coefficient_metadata(messages):
    """Use a validated GRIB pv from any model field, or the official fallback."""
    selected = messages["t_model"][0]
    present = []
    for column in sorted(MODEL_FIELDS):
        metadata = messages[column][0]
        a, b, _ = hybrid_coefficients(metadata)
        if metadata.get("pv") is not None:
            present.append((metadata, a, b))
    if present:
        selected, a, b = present[0]
        if any(not np.array_equal(a, ca) or not np.array_equal(b, cb) for _, ca, cb in present):
            raise ValueError("Model-level fields have conflicting L60 coefficients")
    return selected


def half_level_pressure(a_pa, b, sp_pa):
    return finite(a_pa, "A [Pa]") + finite(b, "B [1]") * positive(sp_pa, "sp [Pa]")


def model_level_pressure(sp_pa, a, b):
    upper = positive(half_level_pressure(a[59], b[59], sp_pa), "p59 [Pa]")
    lower = positive(half_level_pressure(a[60], b[60], sp_pa), "p60 [Pa]")
    full = (upper + lower) / 2.
    if np.any((upper >= full) | (full >= lower)):
        raise ValueError("L60 pressure must lie strictly between ordered half-levels 59 and 60")
    return positive(full, "p60 full [Pa]")


def virtual_temperature(t_kelvin, q_specific):
    t = positive(t_kelvin, "t_model [K]")
    q = finite(q_specific, "q_model [kg/kg]")
    if np.any((q < 0) | (q >= 1)):
        raise ValueError("q_model: specific humidity must be in [0, 1)")
    return positive(t * (1. + (1. - EPSILON) / EPSILON * q), "Tv [K]")


def air_density(p_pa, t_kelvin, q_specific):
    return positive(positive(p_pa, "p [Pa]") / (RD * virtual_temperature(t_kelvin, q_specific)),
                    "rho [kg/m3]")


def gas_concentration(mixing_ratio, density):
    w = finite(mixing_ratio, "gas [kg/kg]")
    if np.any((w < 0) | (w > 1)):
        raise ValueError("gas mass mixing ratio outside [0, 1]")
    return finite(w * positive(density, "rho [kg/m3]") * 1e9, "gas [ug/m3]")


def normalize_fields(messages):
    """Convert a fully aligned time/grid message group; never mutate Bronze arrays."""
    if set(messages) != set(CONTRACTS):
        raise ValueError("Normalization requires all 20 EAC4 fields")
    arrays = {c: finite(m[3], c) for c, m in messages.items()}
    shapes = {a.shape for a in arrays.values()}
    if len(shapes) != 1 or any(a.ndim != 1 or a.size == 0 for a in arrays.values()):
        raise ValueError("Normalization requires equal, nonempty 1D grid arrays")
    for column, message in messages.items():
        native = CONTRACTS[column][0]
        if message[0]["units"] != native and not (column == "aod550" and message[0]["units"] == "1"):
            raise ValueError(f"{column}: unexpected source unit {message[0]['units']!r}; expected {native!r}")
    a, b, _ = hybrid_coefficients(aligned_coefficient_metadata(messages))
    p = model_level_pressure(arrays["sp"], a, b)
    rho = air_density(p, arrays["t_model"], arrays["q_model"])
    result = {}
    for column, values in arrays.items():
        native, _, _, scale, offset = CONTRACTS[column]
        if column not in {"u10", "v10"} and np.any(values < 0):
            raise ValueError(f"{column}: negative native value")
        if native in {"K", "Pa"}:
            positive(values, column)
        converted = gas_concentration(values, rho) if column in GASES else values * scale + offset
        # ARRAY<FLOAT> storage only after the entire physical computation.
        if np.any(np.abs(converted) > np.finfo(np.float32).max):
            raise ValueError(f"{column}: normalized value overflows float32")
        result[column] = converted.astype(np.float32).tolist()
    return result
