from lima_cloud import config


def test_build_grid_has_rows_times_cols_quadrants():
    quads = config.build_grid()
    assert len(quads) == config.GRID_ROWS * config.GRID_COLS


def test_grid_covers_the_full_basin_bbox_without_gaps_or_overlaps():
    quads = config.build_grid()
    lat_mins = sorted({round(q.lat_min, 9) for q in quads})
    lat_maxs = sorted({round(q.lat_max, 9) for q in quads})
    assert lat_mins[0] == round(config.BASIN_LAT_MIN, 9)
    assert lat_maxs[-1] == round(config.BASIN_LAT_MAX, 9)
    # cada limite superior de una fila debe ser el limite inferior de la siguiente
    for i in range(len(lat_mins) - 1):
        assert lat_mins[i + 1] == lat_maxs[i]


def test_quadrant_ids_are_unique():
    quads = config.build_grid()
    ids = [q.id for q in quads]
    assert len(ids) == len(set(ids))
