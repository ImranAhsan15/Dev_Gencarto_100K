import arcpy
import traceback
import sys
from common_utils import *

def resolve_building_point_road_track_conflict(building_fcs, logger, road_fc="TA0060_Road_L", track_fc="TA0110_Track_L"):
    arcpy.env.overwriteOutput = True
    aprx = arcpy.mp.ArcGISProject("CURRENT")
    active_map = aprx.activeMap
    active_layers = active_map.listLayers()
    building_layers = [lyr for bfc in building_fcs for lyr in active_layers if lyr.name in bfc]
    road_layer = [lyr for lyr in active_layers if os.path.basename(road_fc) in lyr.name][0]
    track_layer = [lyr for lyr in active_layers if os.path.basename(track_fc) in lyr.name][0]
    
    resolve_rules = [
        (track_layer, "TCS = 1", "42.5 Meters"),
        (track_layer, "TCS = 2", "37.5 Meters"),
        (road_layer, "RCS = 1", "57.5 Meters"),
        (road_layer, "RCS = 2", "47.5 Meters"),
        (road_layer, "RCS = 3", "57.5 Meters"),
        (road_layer, "RCS = 4", "47.5 Meters"),
        (road_layer, "RCS = 5", "42.5 Meters"),
        (road_layer, "RCS = 6", "45 Meters")
        ]

    for src, query, buffer_dist in resolve_rules:
        # logger.info(f"Processing: {layer} | {query} | Buffer={buffer_dist}")
        # 1. Create filtered layer
        # arcpy.management.MakeFeatureLayer(src, layer, query)
        selected_features = arcpy.management.SelectLayerByAttribute(src, "NEW_SELECTION", query)
        logger.info(f"Resolving building conflict for {src} where {query}")
        ##  2. Resolve building conflicts
        arcpy.cartography.ResolveBuildingConflicts(
            in_buildings=building_layers,
            invisibility_field="INVISIBILITY",
            # in_barriers=f"{layer} TRUE '{buffer_dist}'",
            in_barriers=[[f"{selected_features}", "true", buffer_dist]],
            building_gap="12.5 Meters",
            minimum_size="10 Meters",
            hierarchy_field=""
        )
        arcpy.management.SelectLayerByAttribute(src, "CLEAR_SELECTION")

def resolve_building_polygon_road_track_conflict(building_fcs, logger, road_fc="TA0060_Road_L", track_fc="TA0110_Track_L"):
    arcpy.env.overwriteOutput = True
    aprx = arcpy.mp.ArcGISProject("CURRENT")
    active_map = aprx.activeMap
    active_layers = active_map.listLayers()
    building_layers = [lyr for bfc in building_fcs for lyr in active_layers if lyr.name in bfc]
    road_layer = [lyr for lyr in active_layers if os.path.basename(road_fc) in lyr.name][0]
    track_layer = [lyr for lyr in active_layers if os.path.basename(track_fc) in lyr.name][0]
    
    resolve_rules = [
            (track_layer, "TCS = 1", "12.5 Meters"),
            (track_layer, "TCS = 2", "12.5 Meters"),
            (road_layer, "RCS = 1",  "12.5 Meters"),
            (road_layer, "RCS = 2",  "12.5 Meters"),
            (road_layer, "RCS = 3",  "12.5 Meters"),
            (road_layer, "RCS = 4",  "12.5 Meters"),
            (road_layer, "RCS = 5",  "12.5 Meters"),
            (road_layer, "RCS = 6",  "12.5 Meters")
        ]

    for src, query, buffer_dist in resolve_rules:
        # logger.info(f"Processing: {layer} | {query} | Buffer={buffer_dist}")
        # 1. Create filtered layer
        # arcpy.management.MakeFeatureLayer(src, layer, query)
        selected_features = arcpy.management.SelectLayerByAttribute(src, "NEW_SELECTION", query)
        logger.info(f"Resolving building conflict for {src} where {query}")
        ##  2. Resolve building conflicts
        arcpy.cartography.ResolveBuildingConflicts(
            in_buildings=building_layers,
            invisibility_field="INVISIBILITY",
            # in_barriers=f"{layer} TRUE '{buffer_dist}'",
            in_barriers=[[f"{selected_features}", "true", buffer_dist]],
            building_gap="12.5 Meters",
            minimum_size="10 Meters",
            hierarchy_field=""
        )
        arcpy.management.SelectLayerByAttribute(src, "CLEAR_SELECTION")

def move_building_near_adjacent_points(fc_list, map_name, logger, working_gdb, building_features = None, stated_point_features_dict_with_distance = None):
    arcpy.AddMessage(f"Starting moving buildings in respect to stated points...")
    valid_barriers = []
    point_buffered_features = {}
    arcpy.env.workspace = working_gdb
    aprx = arcpy.mp.ArcGISProject("CURRENT")
    map = aprx.listMaps(map_name)[0]
    active_layers = map.listLayers()
    active_layers = [lyr for lyr in active_layers if not lyr.isGroupLayer]
    # arcpy.AddMessage(f"fc_list:  {fc_list}")
    building_layers = []
    
    if(not building_features):
        building_features = ["BA0010_Residential_Building_A", "BA0010_Residential_Building_P"]
        for bfc in building_features:
            for lyr in active_layers:
               # arcpy.AddMessage(f"active_layer : {lyr.name}")
               if bfc == lyr.name:
                   building_layers.append(lyr)
    if(not stated_point_features_dict_with_distance):
        stated_point_features_dict_with_distance = {
            "HH0130_Natural_Spring_A": '12.5 Meters',
            "HH0130_Natural_Spring_P": '12.5 Meters',
            "BF0010_Building_Of_Worship_A": '12.5 Meters',
            "BF0010_Building_Of_Worship_P": '12.5 Meters',
            "ZA0010_Global_Navigation_Satellite_System_Station_P": '12.5 Meters',
            "ZA0040_Trigonometry_Station_P": '12.5 Meters',
            "ZA0050_Height_Point_P": '0 Meters',
            "ZA0070_Base_Point_P": '0 Meters',
            "ZA0080_International_Boundary_Marker_P": '12.5 Meters',
            "ZA0090_State_Boundary_Marker_P": '12.5 Meters'
        }

    for feature, distance in stated_point_features_dict_with_distance.items():
        if feature in [lyr.name for lyr in active_layers ]:
            if feature in [ os.path.basename(fc) for fc in fc_list]:
                feature_class = [fc for fc in fc_list if feature == os.path.basename(fc)][0]
                feature_path = os.path.join(arcpy.env.workspace, feature)
                # arcpy.AddMessage(f"feature_class:  {feature_class}")
                if feature.endswith('_P'):
                    if has_features(feature_class):
                        arcpy.management.MakeFeatureLayer(feature_class, feature)
                        buffered_feature = os.path.join(arcpy.env.workspace, f"{feature}_Buffer")
                        arcpy.analysis.Buffer(
                            in_features=feature_class,
                            out_feature_class=buffered_feature,
                            buffer_distance_or_field="0.5 Meters",
                            line_side="FULL",
                            line_end_type="ROUND",
                            dissolve_option="NONE",
                            dissolve_field=None,
                            method="PLANAR"
                        )
                        point_buffered_features[feature] = buffered_feature
                        arcpy.management.MakeFeatureLayer(buffered_feature, f"{feature}_Buffer")
                        valid_barriers.append(f"{feature}_Buffer TRUE '{distance}'")
                else:
                    if has_features(feature_class):
                        for lyr in active_layers:
                            if feature == lyr.name:
                                # arcpy.management.MakeFeatureLayer(feature_class, feature)
                                valid_barriers.append(f"{lyr.name} TRUE '{distance}'")
                    else:
                        logger.warning(f"Polygon feature '{feature}' has no records and will be skipped.")

    if valid_barriers:
        in_barriers = ";".join(valid_barriers)
        arcpy.cartography.ResolveBuildingConflicts(
            in_buildings=building_layers, 
            invisibility_field="INVISIBILITY",
            in_barriers=in_barriers,
            building_gap="12.5 Meters",
            minimum_size="10 Meters",
            hierarchy_field="HIERARCHY"
        )
        
    else:
        logger.warning("No valid barriers were found to resolve conflicts.")

    return None

def resolve_conflict_polygons(fc_list, build_up_area_fcs, express_val_mx, express_val_mn, field_name, search_distance, query, input_building_layers, input_barrier_layers, bb_lyr_ex, 
                               bb_lyr_ex_his, hierarchy_field, invisibility_field, symbology_file_path, ref_scale, minimum_size, bld_gap, ap_src_dis_mn, ap_src_dis_mx, orient_dir, g1_align_features, 
                               g4_align_features, g5_input_points, g5_align_features, g6_align_features, g7_input_points, g7_align_features, input_primary, input_secondary, in_prim_sql, 
                               max_gap_area, fill_option, working_gdb, map_name, orient_f, log_dir, logger):
    arcpy.AddMessage('Starting resolve conflicts for polygons.....')
    try:
        # # Hide buildings under built up area
        hide_blgs_under_built_up_area(fc_list, build_up_area_fcs, express_val_mx, express_val_mn, field_name, search_distance, query, map_name)

        # Resolve conflicts for point and polygon
        resolve_conflicts_points_polygon(fc_list, input_building_layers, input_barrier_layers, bb_lyr_ex, bb_lyr_ex_his, hierarchy_field, invisibility_field, symbology_file_path, ref_scale, 
                                        minimum_size, bld_gap, working_gdb, map_name)
        # Align points-G1
        g1_input_points = [fc for fc in fc_list if 'TA0240_Bridge_P' in fc]
        g1_align_features = list(filter(str.strip, g1_align_features))
        g1_align_features = [fc for align_fc in g1_align_features for fc in fc_list if str(align_fc) in fc]
        align_points(g1_input_points, g1_align_features, ap_src_dis_mn, orient_dir, ref_scale, hierarchy_field, symbology_file_path, orient_f, working_gdb, map_name)
        #Align points-G2
        g2_input_points = [fc for fc in fc_list if 'BJ0030_Rail_Terminal_Railway_Station_P' in fc]
        g2_align_features = [fc for fc in fc_list if 'TA0010_Rail_Line_L' in fc]
        align_points(g2_input_points, g2_align_features, ap_src_dis_mx, orient_dir, ref_scale, hierarchy_field, symbology_file_path, orient_f, working_gdb, map_name)
        # Align points-G3
        g3_input_points = [fc for fc in fc_list if 'TA0150_Toll_Plaza_P' in fc]
        g3_align_features = [fc for fc in fc_list if 'TA0060_Road_L' in fc]
        align_points(g3_input_points, g3_align_features, ap_src_dis_mx, orient_dir, ref_scale, hierarchy_field, symbology_file_path, orient_f, working_gdb, map_name)
        # Align points-G4
        g4_input_points = [fc for fc in fc_list for build_p in ['BA0010_Residential_Building_P','BC0010_Industrial_Building_P','BE0010_Educational_Building_P'] if build_p in fc]
        g4_align_features = list(filter(str.strip, g4_align_features))
        g4_align_features = [fc for align_fc in g4_align_features for fc in fc_list if str(align_fc) in fc]
        align_points(g4_input_points, g4_align_features, ap_src_dis_mx, orient_dir, ref_scale, hierarchy_field, symbology_file_path, orient_f, working_gdb, map_name)
        #Align points-G5
        g5_input_points = list(filter(str.strip, g5_input_points))
        g5_input_points = [fc for input_fc in g5_input_points for fc in fc_list if str(input_fc) in fc]
        g5_align_features = list(filter(str.strip, g5_align_features))
        g5_align_features = [fc for align_fc in g5_align_features for fc in fc_list if str(align_fc) in fc]
        align_points(g5_input_points, g5_align_features, ap_src_dis_mn, orient_dir, ref_scale, hierarchy_field, symbology_file_path, orient_f, working_gdb, map_name)
        # Align points-G6
        g6_input_points = [fc for fc in fc_list if 'HD0040_Jetty_Pier_P' in fc]
        g6_align_features = list(filter(str.strip, g6_align_features))
        g6_align_features = [fc for align_fc in g6_align_features for fc in fc_list if str(align_fc) in fc]
        align_points(g6_input_points, g6_align_features, ap_src_dis_mn, orient_dir, ref_scale, hierarchy_field, symbology_file_path, orient_f, working_gdb, map_name)
        # Align points-G7
        g7_input_points = list(filter(str.strip, g7_input_points))
        g7_input_points = [fc for input_fc in g7_input_points for fc in fc_list if str(input_fc) in fc]
        g7_align_features = list(filter(str.strip, g7_align_features))
        g7_align_features = [fc for align_fc in g7_align_features for fc in fc_list if str(align_fc) in fc]
        align_points(g7_input_points, g7_align_features, ap_src_dis_mn, orient_dir, ref_scale, hierarchy_field, symbology_file_path, orient_f, working_gdb, map_name)

        # Fix Vegetation after Resolve Conflicts
        fix_veg_after_resolve_conflict(fc_list, input_primary, input_secondary, in_prim_sql, max_gap_area, fill_option, invisibility_field, working_gdb)
        # Apply Layer Definition on Building Feature Classes
        apply_layer_definition(input_building_layers, "INVISIBILITY = 0 OR INVISIBILITY IS NULL", map_name)

        # # Move Buildings According to Adjacent stated Points
        move_building_near_adjacent_points(fc_list, map_name, logger, working_gdb)

        # # # resolve_building_point_road_track_conflict(building_point_fcs, logger, road_fc, track_fc)
        # # # resolve_building_polygon_road_track_conflict(building_polygon_fcs, logger, road_fc, track_fc)

    except Exception as e:
        exc_type, exc_value, exc_traceback = sys.exc_info()
        tb = traceback.format_exc()
        error_message = f"Resolve conflicts for buildings error: {e}\nTraceback details:\n{tb}"
        logger.error(error_message)
        simplified_msgs('Resolve conflicts for buildings', f'{exc_value}\n')