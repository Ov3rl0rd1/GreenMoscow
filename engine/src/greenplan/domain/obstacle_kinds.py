GAS_PIPELINE = "gas_pipeline"
WATER_SUPPLY = "water_supply"
SEWER = "sewer"
SEWER_PRESSURE = "sewer_pressure"
STORMWATER = "stormwater"
DRAINAGE = "drainage"
HEATING_NETWORK = "heating_network"
POWER_CABLE = "power_cable"
COMMUNICATION_CABLE = "communication_cable"
CABLE_UNKNOWN = "cable_unknown"
LKS_TMK = "lks_tmk"
UTILITY_TUNNEL = "utility_tunnel"
NETWORK_UNKNOWN = "network_unknown"
OVERHEAD_LINE = "overhead_line"

BUILDING_WALL = "building_wall"
CARRIAGEWAY_EDGE = "carriageway_edge"
SIDEWALK_EDGE = "sidewalk_edge"
CURB = "curb"
LIGHTING_POLE = "lighting_pole"
TRAFFIC_LIGHT_POLE = "traffic_light_pole"
BRIDGE_SUPPORT = "bridge_support"
MANHOLE = "manhole"
BUS_SHELTER = "bus_shelter"
SLOPE_TOE = "slope_toe"
RETAINING_WALL = "retaining_wall"

EXISTING_TREE = "existing_tree"
EXISTING_TREE_ROW = "existing_tree_row"
TREE_TO_REMOVE = "tree_to_remove"

SITE_BOUNDARY = "site_boundary"
SURVEY_BOUNDARY = "survey_boundary"
STREET_AXIS = "street_axis"
LAWN_SURFACE = "lawn_surface"
GREEN_AREA = "green_area"

UNDERGROUND_NETWORK_KINDS = frozenset(
    {
        GAS_PIPELINE,
        WATER_SUPPLY,
        SEWER,
        SEWER_PRESSURE,
        STORMWATER,
        DRAINAGE,
        HEATING_NETWORK,
        POWER_CABLE,
        COMMUNICATION_CABLE,
        CABLE_UNKNOWN,
        LKS_TMK,
        UTILITY_TUNNEL,
        NETWORK_UNKNOWN,
    }
)

POINT_SYMBOL_KINDS = frozenset({LIGHTING_POLE, TRAFFIC_LIGHT_POLE, MANHOLE, BRIDGE_SUPPORT, BUS_SHELTER})

EDGE_KINDS = frozenset(
    {BUILDING_WALL, CARRIAGEWAY_EDGE, SIDEWALK_EDGE, SLOPE_TOE, RETAINING_WALL, OVERHEAD_LINE}
)
