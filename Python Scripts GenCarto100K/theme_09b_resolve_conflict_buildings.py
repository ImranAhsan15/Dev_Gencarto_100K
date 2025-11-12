import arcpy
import traceback
import sys
from common_utils import *

def resolve_conflict_buildings(fc_list, build_up_area_fcs, express_val_mx, express_val_mn, field_name, search_distance, query, input_building_layers, input_barrier_layers, bb_lyr_ex, 
                               bb_lyr_ex_his, hierarchy_field, invisibility_field, symbology_file_path, ref_scale, minimum_size, bld_gap, ap_src_dis_mn, ap_src_dis_mx, orient_dir, g1_align_features, 
                               g4_align_features, g5_input_points, g5_align_features, g6_align_features, g7_input_points, g7_align_features, input_primary, input_secondary, in_prim_sql, 
                               max_gap_area, fill_option, working_gdb, map_name, log_dir, logger):
    arcpy.AddMessage('Starting resolve conflicts for buildings.....')
    try:
        # Hide buildings under built up area
        hide_blgs_under_built_up_area(fc_list, build_up_area_fcs, express_val_mx, express_val_mn, field_name, search_distance, query)

        # Resolve conflicts for point and polygon
        resolve_conflicts_points_polygon(fc_list, input_building_layers, input_barrier_layers, bb_lyr_ex, bb_lyr_ex_his, hierarchy_field, invisibility_field, symbology_file_path, ref_scale, 
                                        minimum_size, bld_gap, working_gdb, map_name)
        # Align points-G1
        g1_input_points = [fc for fc in fc_list if 'TA0240_Bridge_P' in fc]
        g1_align_features = list(filter(str.strip, g1_align_features))
        g1_align_features = [fc for align_fc in g1_align_features for fc in fc_list if str(align_fc) in fc]
        align_points(g1_input_points, g1_align_features, ap_src_dis_mn, orient_dir, ref_scale, hierarchy_field, symbology_file_path, map_name)
        # Align points-G2
        g2_input_points = [fc for fc in fc_list if 'BJ0030_Rail_Terminal_Railway_Station_P' in fc]
        g2_align_features = [fc for fc in fc_list if 'TA0010_Rail_Line_L' in fc]
        align_points(g2_input_points, g2_align_features, ap_src_dis_mx, orient_dir, ref_scale, hierarchy_field, symbology_file_path, map_name)
        # Align points-G3
        g3_input_points = [fc for fc in fc_list if 'TA0150_Toll_Plaza_P' in fc]
        g3_align_features = [fc for fc in fc_list if 'TA0060_Road_L' in fc]
        align_points(g3_input_points, g3_align_features, ap_src_dis_mx, orient_dir, ref_scale, hierarchy_field, symbology_file_path, map_name)
        # Align points-G4
        g4_input_points = [fc for fc in fc_list for build_p in ['BA0010_Residential_Building_P','BC0010_Industrial_Building_P','BE0010_Educational_Building_P','BF0010_Building_Of_Worship_P'] if build_p in fc]
        g4_align_features = list(filter(str.strip, g4_align_features))
        g4_align_features = [fc for align_fc in g4_align_features for fc in fc_list if str(align_fc) in fc]
        align_points(g4_input_points, g4_align_features, ap_src_dis_mn, orient_dir, ref_scale, hierarchy_field, symbology_file_path, map_name)
        # Align points-G5
        g5_input_points = list(filter(str.strip, g5_input_points))
        g5_input_points = [fc for input_fc in g5_input_points for fc in fc_list if str(input_fc) in fc]
        g5_align_features = list(filter(str.strip, g5_align_features))
        g5_align_features = [fc for align_fc in g5_align_features for fc in fc_list if str(align_fc) in fc]
        align_points(g5_input_points, g5_align_features, ap_src_dis_mn, orient_dir, ref_scale, hierarchy_field, symbology_file_path, map_name)
        # Align points-G6
        g6_input_points = [fc for fc in fc_list if 'HD0040_Jetty_Pier_P' in fc]
        g6_align_features = list(filter(str.strip, g6_align_features))
        g6_align_features = [fc for align_fc in g6_align_features for fc in fc_list if str(align_fc) in fc]
        align_points(g6_input_points, g6_align_features, ap_src_dis_mn, orient_dir, ref_scale, hierarchy_field, symbology_file_path, map_name)
        # Align points-G7
        g7_input_points = list(filter(str.strip, g7_input_points))
        g7_input_points = [fc for input_fc in g7_input_points for fc in fc_list if str(input_fc) in fc]
        g7_align_features = list(filter(str.strip, g7_align_features))
        g7_align_features = [fc for align_fc in g7_align_features for fc in fc_list if str(align_fc) in fc]
        align_points(g7_input_points, g7_align_features, ap_src_dis_mn, orient_dir, ref_scale, hierarchy_field, symbology_file_path, map_name)

        # Fix Vegetation after Resolve Conflicts
        fix_veg_after_resolve_conflict(fc_list, input_primary, input_secondary, in_prim_sql, max_gap_area, fill_option, invisibility_field, working_gdb)

    except Exception as e:
        exc_type, exc_value, exc_traceback = sys.exc_info()
        tb = traceback.format_exc()
        error_message = f"Resolve conflicts for buildings error: {e}\nTraceback details:\n{tb}"
        logger.error(error_message)
        simplified_msgs('Resolve conflicts for buildings', f'{exc_value}\n')