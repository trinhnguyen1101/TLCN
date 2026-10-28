"""Versioned analytical display domains, independent from AQI risk categories."""
import json
from pathlib import Path
from app.schemas.dashboard import MetricMetadata,ConcentrationScale


def concentration_metadata(statistic):
    path=Path(__file__).resolve().parents[4]/'lakehouse/gold/contracts/concentration-colors-v1.json'
    policy=json.loads(path.read_text())
    if statistic not in policy['statistic_policies']:raise ValueError('Unsupported concentration statistic')
    return {p:MetricMetadata(unit='µg/m³',quantity='concentration',map_scale=ConcentrationScale(
        breakpoints=cuts,method='absolute_concentration',sample_count=0,
        reference_start=policy['effective_date'],reference_end=policy['effective_date'],
        version=policy['version'],statistic=statistic,reference_kind='fixed_display_domains',
        note='Thang nồng độ phân tích cố định; không phải phân loại nguy cơ sức khỏe. So sánh cùng chất, đơn vị và basis.'))
        for p,cuts in policy['breakpoints'].items()}
