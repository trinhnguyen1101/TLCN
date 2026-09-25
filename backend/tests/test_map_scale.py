from datetime import date

from app.services.map_scale import monthly_concentration_scale


def test_absolute_thresholds_and_reference_metadata():
    samples = [(date(2024, month, 1), value) for month, value in enumerate([0, 10, 20, 30, 1000], 1)]
    scale = monthly_concentration_scale(samples)
    assert scale.breakpoints == [25, 50, 100]
    assert scale.sample_count == 5
    assert scale.reference_start == date(2024, 1, 1)
    assert scale.reference_end == date(2024, 5, 1)
    assert scale.method == 'absolute_concentration'


def test_missing_and_nonfinite_samples_are_excluded_but_zero_is_valid():
    samples = [(date(2024, 1, 1), value) for value in [None, float('nan'), float('inf'), 0]]
    scale = monthly_concentration_scale(samples)
    assert scale.breakpoints == [25, 50, 100]
    assert scale.sample_count == 1
    assert monthly_concentration_scale(samples[:3]) is None
    assert monthly_concentration_scale([]) is None


def test_distribution_changes_do_not_rebalance_colors_or_collapse_four_bands():
    for values in [[10] * 20, [50] * 20, [200] * 20, [0, 1, 2, 3], [1, 1000]]:
        samples = [(date(2024, 1, 1), value) for value in values]
        assert monthly_concentration_scale(samples).breakpoints == [25, 50, 100]
