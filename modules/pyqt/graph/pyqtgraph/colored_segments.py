import numpy as np


def _as_array(values):
    if values is None or np.isscalar(values) or isinstance(values, np.ndarray):
        return values
    return np.asarray(values)


def _segment_color(brushes, index):
    if brushes is None:
        return None

    brush = brushes[index]
    if np.isscalar(brush):
        return None if not np.isfinite(brush) else brush

    brush_array = np.asarray(brush)
    if brush_array.size == 0:
        return None
    if (
        np.issubdtype(brush_array.dtype, np.number)
        and not np.isfinite(brush_array).all()
    ):
        return None

    return tuple(brush_array.tolist())


def _build_segment_points(x, y, brushes):
    if x is None or y is None or np.isscalar(x) or np.isscalar(y):
        return []
    if brushes is not None and np.isscalar(brushes):
        brushes = None
    n = min(len(x), len(y), len(brushes) if brushes is not None else len(x))
    if n < 2:
        return []

    x, y = np.asarray(x[:n], dtype=float), np.asarray(y[:n], dtype=float)
    finite = np.isfinite(x) & np.isfinite(y)
    valid = finite[:-1] & finite[1:]
    if brushes is None:
        same = np.ones(n - 2, dtype=bool)
    elif (
        isinstance(brushes, np.ndarray)
        and brushes.ndim == 2
        and brushes.shape[1]
        and np.issubdtype(brushes.dtype, np.number)
    ):
        rows = brushes[1:n]
        colored = np.isfinite(rows).all(axis=1)
        same = (colored[1:] == colored[:-1]) & (
            ~colored[1:] | np.all(rows[1:] == rows[:-1], axis=1)
        )
    else:
        colors = [_segment_color(brushes, i) for i in range(1, n)]
        same = np.array([a == b for a, b in zip(colors[1:], colors[:-1])], dtype=bool)

    # Segment i uses the color of its endpoint i + 1.
    continues = valid & np.r_[False, valid[:-1]] & np.r_[False, same]
    starts = np.flatnonzero(valid & ~continues)
    stops = np.r_[np.flatnonzero(~continues), n - 1]
    ends = stops[np.searchsorted(stops, starts, side="right")]
    xs, ys = x.tolist(), y.tolist()
    return [
        (
            list(zip(xs[start : stop + 1], ys[start : stop + 1])),  # noqa: E203
            _segment_color(brushes, start + 1),
        )
        for start, stop in zip(starts, ends)
    ]
