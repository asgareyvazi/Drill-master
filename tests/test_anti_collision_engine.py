"""Ground-truth tests for the anti-collision screening engine."""

import pytest

from core.engineering.engines.anti_collision import AntiCollisionEngine


def _vertical_pair(offset_north=3.0, offset_east=4.0, with_uncertainty=False, with_radius=False):
    reference = [
        {"md": 0.0, "tvd": 0.0, "north": 0.0, "east": 0.0},
        {"md": 100.0, "tvd": 100.0, "north": 0.0, "east": 0.0},
    ]
    offset = [
        {"md": 0.0, "tvd": 0.0, "north": offset_north, "east": offset_east},
        {"md": 100.0, "tvd": 100.0, "north": offset_north, "east": offset_east},
    ]
    if with_uncertainty:
        for points in (reference, offset):
            for point in points:
                point.update({"sigma_north": 0.5, "sigma_east": 0.5, "sigma_tvd": 0.5})
    if with_radius:
        for points in (reference, offset):
            for point in points:
                point["wellbore_radius"] = 1.0
    return reference, offset


def test_common_md_separation_and_continuous_closest_approach():
    reference, offset = _vertical_pair()
    result = AntiCollisionEngine.screen_clearance(
        reference, offset, coordinates_unit="m", collision_threshold=4.0
    )

    assert result.success, result.error
    assert result.scope == "PARTIAL / SCREENING"
    assert result.value == pytest.approx(5.0)
    assert result.values["min_distance"] == pytest.approx(5.0)
    assert [row["distance"] for row in result.values["separation_vs_md"]] == [5.0, 5.0]
    assert result.values["collision_scan"]["status"] == "clear"
    assert result.values["collision_scan"]["events"] == []


def test_convergence_scan_and_clearance_threshold():
    reference = [
        {"md": 0.0, "tvd": 0.0, "north": 0.0, "east": 0.0, "wellbore_radius": 1.0},
        {"md": 100.0, "tvd": 100.0, "north": 0.0, "east": 0.0, "wellbore_radius": 1.0},
    ]
    offset = [
        {"md": 0.0, "tvd": 0.0, "north": 10.0, "east": 0.0, "wellbore_radius": 1.0},
        {"md": 100.0, "tvd": 100.0, "north": 0.0, "east": 0.0, "wellbore_radius": 1.0},
    ]
    result = AntiCollisionEngine.screen_clearance(
        reference, offset, coordinates_unit="m", collision_threshold=2.0
    )

    assert result.success, result.error
    assert result.values["closest_approach"]["md"] == pytest.approx(100.0)
    assert result.values["closest_approach"]["distance"] == pytest.approx(0.0)
    assert result.values["closest_approach"]["clearance"] == pytest.approx(-2.0)
    assert result.values["separation_vs_md"][1]["convergence"] == "converging"
    assert result.values["collision_scan"]["status"] == "alert"
    assert result.values["collision_scan"]["events"][-1]["margin"] == pytest.approx(-4.0)


def test_supplied_uncertainty_produces_transparent_screening_factor():
    reference, offset = _vertical_pair(with_uncertainty=True)
    result = AntiCollisionEngine.screen_clearance(reference, offset, coordinates_unit="m")

    assert result.success, result.error
    expected_sigma = (3.0 * (0.5**2 + 0.5**2)) ** 0.5
    assert result.values["closest_approach"]["combined_sigma"] == pytest.approx(expected_sigma)
    assert result.values["closest_approach"]["separation_factor"] == pytest.approx(5.0 / expected_sigma)
    assert result.values["uncertainty"]["iscwsa_applied"] is False
    assert result.metadata["iscwsa_compliant"] is False


def test_missing_uncertainty_and_radii_are_explicit_not_fabricated():
    reference, offset = _vertical_pair()
    result = AntiCollisionEngine.screen_clearance(reference, offset, coordinates_unit="m")

    assert result.success, result.error
    assert result.values["closest_approach"]["separation_factor"] is None
    assert result.values["closest_approach"]["clearance"] is None
    assert any("uncertainty" in warning.lower() for warning in result.warnings)
    assert any("radii" in warning.lower() for warning in result.warnings)
    assert any("collision scan" in warning.lower() for warning in result.warnings)


def test_coordinate_units_are_validated():
    reference, offset = _vertical_pair()
    result = AntiCollisionEngine.screen_clearance(
        reference, offset, coordinates_unit="not-a-length"
    )
    assert not result.success
    assert "coordinates_unit" in result.error


def test_invalid_trajectory_is_a_result_error_and_legacy_facade_is_compatible():
    invalid = [{"md": 0.0, "tvd": 0.0, "north": 0.0}]
    result = AntiCollisionEngine.screen_clearance(invalid, invalid, coordinates_unit="m")
    assert not result.success
    assert "MISSING_INPUT" in result.error

    legacy = AntiCollisionEngine.calculate_clearance(invalid, invalid)
    assert "error" in legacy
