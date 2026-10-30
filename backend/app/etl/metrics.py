"""CAMS parameter identities and dimensional conversions (never column -> surface)."""
from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class Metric:
    name: str
    source_unit: str
    unit: str
    quantity: str
    scale: float = 1.0
    offset: float = 0.0

    def metadata(self):
        return dict(asdict(self), display_name=DISPLAY_NAMES.get(self.name,self.name))


# ECMWF parameter IDs, validated against every GRIB message, not filenames.
GAS_PARAM_IDS = {210123, 210121, 210122, 210203}
SUPPORT_PARAMETERS = {130: ("t_model", "K"), 133: ("q_model", "kg kg**-1")}

METRICS = {
    210123: Metric("co", "kg kg**-1", "mg/m³", "near_surface_model_mass_concentration", 1e6),
    210121: Metric("no2", "kg kg**-1", "µg/m³", "near_surface_model_mass_concentration", 1e9),
    210122: Metric("so2", "kg kg**-1", "µg/m³", "near_surface_model_mass_concentration", 1e9),
    210203: Metric("o3", "kg kg**-1", "µg/m³", "near_surface_model_mass_concentration", 1e9),
    210072: Metric("pm1", "kg m**-3", "µg/m³", "surface_mass_concentration", 1e9),
    210073: Metric("pm25", "kg m**-3", "µg/m³", "surface_mass_concentration", 1e9),
    210074: Metric("pm10", "kg m**-3", "µg/m³", "surface_mass_concentration", 1e9),
    210207: Metric("aod550", "~", "1", "aerosol_optical_depth"),
    210206: Metric("o3_column", "kg m**-2", "mg/m²", "total_column_mass", 1e6),
    210125: Metric("no2_column", "kg m**-2", "mg/m²", "total_column_mass", 1e6),
    210126: Metric("so2_column", "kg m**-2", "mg/m²", "total_column_mass", 1e6),
    210127: Metric("co_column", "kg m**-2", "mg/m²", "total_column_mass", 1e6),
    167: Metric("t2m", "K", "°C", "air_temperature_2m", offset=-273.15),
    168: Metric("d2m", "K", "°C", "dewpoint_temperature_2m", offset=-273.15),
    134: Metric("sp", "Pa", "hPa", "surface_pressure", 0.01),
    151: Metric("mslp", "Pa", "hPa", "mean_sea_level_pressure", 0.01),
    165: Metric("u10", "m s**-1", "m/s", "eastward_wind_10m"),
    166: Metric("v10", "m s**-1", "m/s", "northward_wind_10m"),
}


def resolve_metric(param_id: int, unit: str) -> Metric:
    if param_id not in METRICS:
        raise ValueError(f"Unsupported GRIB paramId {param_id}")
    metric = METRICS[param_id]
    if unit != metric.source_unit:
        raise ValueError(f"Unexpected unit for {metric.name}: {unit!r}, expected {metric.source_unit!r}")
    return metric


def convert_direct(metric, values):
    """Only dimensional linear conversions; MMR requires a density-aware path."""
    if metric.source_unit == "kg kg**-1":
        raise ValueError("Mixing ratios require aligned model-level density")
    return values * metric.scale + metric.offset


DISPLAY_NAMES = {
    'pm1':'PM1', 'pm25':'PM2.5', 'pm10':'PM10', 'co':'CO', 'no2':'NO₂', 'so2':'SO₂', 'o3':'O₃',
    'aod550':'AOD 550 nm', 'co_column':'CO total column','no2_column':'NO₂ total column',
    'so2_column':'SO₂ total column','o3_column':'O₃ total column', 't2m':'2 m temperature',
    'd2m':'2 m dewpoint','sp':'Surface pressure','mslp':'Mean sea-level pressure',
    'u10':'10 m eastward wind','v10':'10 m northward wind',
}
