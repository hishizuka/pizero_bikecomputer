"""
Vendored RDP wrapper for pizero_bikecomputer.

This module vendors the Cython implementation from:
https://github.com/hishizuka/crdp (commit 9359b0ba5a89efca4d30f306dfb250d972d301d8)

That fork is based on the original crdp project by Ran Bi:
https://github.com/biran0079/crdp

Both the vendored implementation and this fallback wrapper are provided
under the MIT License. See NOTICE and third_party/mit/LICENSE.MIT.
"""

from math import sqrt

MODE = "Python"
_cython_rdp = None

try:
    from ._crdp import rdp as _cython_rdp

    MODE = "Cython"
except Exception:
    try:
        import pyximport

        pyximport.install(inplace=True, language_level=3)
        from ._crdp import rdp as _cython_rdp

        MODE = "Cython"
    except Exception:
        _cython_rdp = None


def _point_xy(point):
    return float(point[0]), float(point[1])


def _rdp_mask_python(points, epsilon):
    mask = [True] * len(points)
    stack = [(0, len(points) - 1)]

    while stack:
        start, end = stack.pop()
        x_start, y_start = _point_xy(points[start])
        x_end, y_end = _point_xy(points[end])
        distance = sqrt((y_start - y_end) ** 2 + (x_start - x_end) ** 2)
        p0 = y_start - y_end
        p1 = x_start - x_end
        p2 = x_start * y_end - y_start * x_end
        max_distance = 0.0
        index = start

        for i in range(start + 1, end):
            x_value, y_value = _point_xy(points[i])
            if distance:
                perpendicular_distance = (
                    abs(p0 * x_value - p1 * y_value + p2) / distance
                )
            else:
                perpendicular_distance = sqrt(
                    (y_start - y_value) ** 2 + (x_start - x_value) ** 2
                )

            if perpendicular_distance > max_distance:
                index = i
                max_distance = perpendicular_distance

        if max_distance > epsilon:
            stack.append((start, index))
            stack.append((index, end))
            continue

        for i in range(start + 1, end):
            mask[i] = False

    return mask


def rdp(points, epsilon=0, return_mask=False):
    point_count = len(points)
    if point_count == 0:
        return []
    if point_count == 1:
        return [True] if return_mask else [points[0]]
    if point_count == 2:
        return [True, True] if return_mask else [points[0], points[1]]

    epsilon = float(epsilon)

    if _cython_rdp is not None:
        return _cython_rdp(points, epsilon=epsilon, return_mask=return_mask)

    mask = _rdp_mask_python(points, epsilon)
    if return_mask:
        return mask
    return [point for point, keep in zip(points, mask) if keep]


__all__ = ["MODE", "rdp"]
