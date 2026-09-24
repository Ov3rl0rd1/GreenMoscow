from greenplan.export.shrub_groups import shrub_group_areas

HEDGE = [(float(x), 0.0) for x in range(6)]
LONE = [(40.0, 40.0), (41.0, 40.0)]


def test_neighbouring_shrubs_merge_into_one_group_outline() -> None:
    areas = shrub_group_areas(HEDGE + LONE, radius_m=0.9, min_size=3, simplify_m=0.1)
    assert len(areas) == 1
    assert areas[0].bounds[0] < 0.0 < 5.0 < areas[0].bounds[2]


def test_pairs_and_single_shrubs_stay_without_a_group() -> None:
    assert shrub_group_areas(LONE, radius_m=0.9, min_size=3, simplify_m=0.1) == []


def test_far_apart_shrubs_do_not_merge() -> None:
    scattered = [(float(x) * 5.0, 0.0) for x in range(6)]
    assert shrub_group_areas(scattered, radius_m=0.9, min_size=3, simplify_m=0.1) == []
