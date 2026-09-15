from shapely.geometry import LineString, Point, Polygon

from greenplan.domain.drawing import BlockReference, DrawingContent, LayerGeometry, TextAnnotation

from fixtures.drawing_factory import rectangle

STREET_LENGTH_M = 100.0
CARRIAGEWAY = rectangle(0, 0, STREET_LENGTH_M, 8)
LAWN = rectangle(0, 10, STREET_LENGTH_M, 20)
SIDEWALK = rectangle(0, 20, STREET_LENGTH_M, 23)
BOUNDARY = rectangle(0, -2, STREET_LENGTH_M, 30)
GAS_PIPELINE_Y = 15.0


def closed_ring(coordinates) -> LineString:
    return LineString(list(coordinates) + [coordinates[0]])


def synthetic_street_content(gas_pipeline_y: float = GAS_PIPELINE_Y) -> DrawingContent:
    geometries = (
        LayerGeometry("ДВ_ГП_П_Граница работ", "LWPOLYLINE", closed_ring(BOUNDARY), "boundary", "1"),
        LayerGeometry("_АБ ПЧ-АБ ПЧ", "HATCH", Polygon(CARRIAGEWAY), "surfaces", "2"),
        LayerGeometry("_ГЗН-ГЗН", "HATCH", Polygon(LAWN), "surfaces", "3"),
        LayerGeometry("_АБ ТР-АБ ТР", "HATCH", Polygon(SIDEWALK), "surfaces", "4"),
        LayerGeometry(
            "Газопровод", "LINE", LineString([(0, gas_pipeline_y), (50, gas_pipeline_y)]), "tile_up", "5"
        ),
        LayerGeometry(
            "Газопровод", "LINE", LineString([(50, gas_pipeline_y), (100, gas_pipeline_y)]), "tile_up", "6"
        ),
        LayerGeometry("Фонари", "CIRCLE", Point(30, 9).buffer(0.2).exterior, "tile_tp", "7"),
        LayerGeometry("Бортовой камень", "LINE", LineString([(0, 8), (100, 8)]), "tile_tp", "8"),
    )
    annotations = (
        TextAnnotation("Газопровод", "d=110н.д.п/э", Point(25, gas_pipeline_y + 0.4), 0.0, "tile_up"),
    )
    trees = (BlockReference("!!!_1. Дендра_сохранить", "*U135", Point(10, 18), 1.0, 0.0, (), "dendro"),)
    return DrawingContent(geometries, annotations, trees)
