import math
import numpy as np
import pytest
from steering.geometry import circle_intersections, rotate, unwrap


def test_rotation_and_unwrapping():
    np.testing.assert_allclose(rotate((0, -1), math.pi/2), [1, 0], atol=1e-14)
    assert unwrap(math.radians(-179), math.radians(179)) == pytest.approx(math.radians(181))


@pytest.mark.parametrize("other,radius,status,count", [
    ((1, 0), 1, "valid", 2), ((2, 0), 1, "tangent", 1),
    ((3, 0), 1, "impossible", 0), ((0, 0), 1, "coincident", 0),
    ((0, 0), 2, "concentric", 0), ((1, 0), 0, "degenerate", 0),
    ((1, 0), 2, "tangent", 1),
])
def test_circle_cases(other, radius, status, count):
    result = circle_intersections(np.zeros(2), 1, np.array(other), radius, 1e-10)
    assert result.status == status
    assert len(result.points) == count
    for _, point in result.points:
        assert np.linalg.norm(point) == pytest.approx(1)
        assert np.linalg.norm(point-np.array(other)) == pytest.approx(radius)


def test_tolerance_near_tangency():
    assert circle_intersections(np.zeros(2), 1, np.array([2+1e-12, 0]), 1, 1e-10).status == "tangent"
    assert circle_intersections(np.zeros(2), 1, np.array([2+1e-7, 0]), 1, 1e-10).status == "impossible"
