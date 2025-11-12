# Import required modules from the respective theme, helper, and common utility files
import arcpy
import time
import os
import sys
import traceback
import logging
import importlib
import DetermineTouching as touch
import RemoveByConverting as convert
import SplitByBox
from get_param_vals import ParamValues
from datetime import datetime
import LayerGrouping as LG

import common_utils as common_utils

# Import theme files
import theme_01_data_prep as theme_01_data_prep
import theme_02_transportation as theme_02_transportation
import theme_03_hydrography as theme_03_hydrography
import theme_04_buildup as theme_04_buildup
import theme_05_utility as theme_05_utility
import theme_06_hypsography as theme_06_hypsography
import theme_07_vegetation as theme_07_vegetation
import theme_08_apply_carto_symbology as theme_08_apply_carto_symbology
import theme_09a_resolve_conflict_lines as theme_09a_resolve_conflict_lines
import theme_09b_resolve_conflict_buildings as theme_09b_resolve_conflict_buildings
import theme_10_detect_conflict as theme_10_detect_conflict
import theme_11_load_data as theme_11_load_data

# Set development mode
DEV_MODE = True
if(DEV_MODE):
    importlib.reload(common_utils)
    importlib.reload(touch)
    importlib.reload(convert)
    importlib.reload(SplitByBox)
    importlib.reload(theme_01_data_prep)
    importlib.reload(theme_02_transportation)
    importlib.reload(theme_03_hydrography)
    importlib.reload(theme_04_buildup)
    importlib.reload(theme_05_utility)
    importlib.reload(theme_06_hypsography)
    importlib.reload(theme_07_vegetation)
    importlib.reload(theme_08_apply_carto_symbology)
    importlib.reload(theme_09a_resolve_conflict_lines)
    importlib.reload(theme_09b_resolve_conflict_buildings)
    importlib.reload(theme_10_detect_conflict)
    importlib.reload(theme_11_load_data)
    importlib.reload(LG)

def main():
    try:
        # Calling logger
        log_dir = os.path.dirname(arcpy.env.scratchGDB)
        logger = common_utils.error_msgs(log_dir)

        # Create scratch GDB if not exists
        scratch_gdb = os.path.join(log_dir, "scratch.gdb")
        if not arcpy.Exists(scratch_gdb):
            arcpy.management.CreateFileGDB(log_dir, "scratch.gdb", "CURRENT")

        # Current time
        current_time = time.time()
        arcpy.AddMessage('Starting cartographic generalisation processing.....')
        logger.info('Starting cartographic generalisation processing.....')

        start_time = current_time
        logger.info(f"Starting time: {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(start_time))}")
        

        # User Input
        theme_type = arcpy.GetParameter(0)
        in_feature_loc = arcpy.GetParameterAsText(1)
        hierarchy_file = arcpy.GetParameterAsText(2)
        out_workspace = arcpy.GetParameterAsText(3)
        rev_workspace = arcpy.GetParameterAsText(4)
        excel_file = arcpy.GetParameterAsText(5)
        symbology_file_path = arcpy.GetParameterAsText(6)
        vst_workspace = arcpy.GetParameterAsText(7)
        working_gdb = scratch_gdb

        # Get params values from excel file
        if os.path.exists(excel_file):

            # Initialize object
            val_obj = ParamValues(excel_file)
            fc_dict = val_obj.get_param_list()
            val_dict = val_obj.get_param_vals()
            arcpy.AddMessage('Fetching parameter values from configuration file.....')
            # Get param values
            dataset_name = val_dict['dataset_name']
            not_include_fields = fc_dict['not_include_fields']
            bau_field_fc = fc_dict['bau_field_fc']
            buffer_points_25K = fc_dict['buffer_points_25K']
            buffer_distance_point = val_dict['buffer_distance_point']
            feature_to_split = fc_dict['feature_to_split']
            extend_val = val_dict['extend_val']
            trim_val = val_dict['trim_val']
            buffer_distance = val_dict['buffer_distance']
            feature_count = val_dict['feature_count']
            vertex_limit = val_dict['vertex_limit']
            map_name_apply_carto = val_dict['map_name_apply_carto']
            map_name_resolve_lines = val_dict['map_name_resolve_lines']
            map_name_resolve_polygons = val_dict['map_name_resolve_polygons']
            map_name_detect = val_dict['map_name_detect']

            railway_sql = fc_dict['railway_sql']
            fcs_trim_extent_trans = fc_dict['fcs_trim_extent_trans']
            fcs_trim_extent_hyd = fc_dict['fcs_trim_extent_hyd']
            fcs_trim_extend = fcs_trim_extent_hyd + fcs_trim_extent_trans
            Structure2Structure = fc_dict['Structure2Structure']
            Structure2Lines = fc_dict['Structure2Lines']
            Lines2Lines = fc_dict['Lines2Lines']
            G1_Poly2Poly = fc_dict['G1_Poly2Poly']
            G2_Poly2Poly = fc_dict['G2_Poly2Poly']
            G3_Poly2Poly = fc_dict['G3_Poly2Poly']
            build_up_area_fcs = fc_dict['build_up_area_fcs']
            input_building_layers = fc_dict['input_building_layers'] 
            input_barrier_layers = fc_dict['input_barrier_layers']
            g5_input_points = fc_dict['g5_input_points']
            g7_input_points = fc_dict['g7_input_points']
            g1_align_features = fc_dict['g1_align_features']
            g4_align_features = fc_dict['g4_align_features']
            g5_align_features = fc_dict['g5_align_features']
            g6_align_features = fc_dict['g6_align_features']
            g7_align_features = fc_dict['g7_align_features']
            input_primary = fc_dict['input_primary']
            input_secondary = fc_dict['input_secondary']
            input_line_layers = fc_dict['input_line_layers']
            edge_features = fc_dict['edge_features']
            embank_list = fc_dict['embank_list']
            compare_fcs_embank = fc_dict['compare_fcs_embank']
            road_query = fc_dict['road_query']
            bridge_query = fc_dict['bridge_query']
            attribution_fc_list = fc_dict['attribution_fc_list']
            apply_symbology_layers_list = fc_dict['apply_symbology_layers_list']
            express_list = fc_dict['express_list']
            query_list = fc_dict['query_list']
            field_list = fc_dict['field_list']
            intersecting_fc_list = fc_dict['intersecting_fc_list']
            collapse_sql = fc_dict['collapse_sql']
            collapse_size = val_dict['collapse_size']
            seg_length = val_dict['seg_length']
            group_sql_rd1 = val_dict['group_sql_rd1']
            group_sql_rd2 = val_dict['group_sql_rd2']
            group_sql_track = val_dict['group_sql_track']
            trans_common_express = val_dict['trans_common_express']
            trans_generalized_operation = val_dict['trans_generalized_operation']
            trans_delete_input = val_dict['trans_delete_input']
            trans_create_one_point = val_dict['trans_create_one_point']
            trans_update_val = val_dict['trans_update_val']
            trans_changed_road_type = val_dict['trans_changed_road_type']
            trans_build_up_buildings = fc_dict['trans_build_up_buildings']
            trans_topology_features = fc_dict['topology_features']
            trans_unique_field = val_dict['trans_unique_field']
            minimum_length_min = val_dict['minimum_length_min']
            minimum_length_max = val_dict['minimum_length_max']
            simple_tolerance = val_dict['simple_tolerance']
            smooth_tolerance = val_dict['smooth_tolerance']
            merge_field = val_dict['Merge_Field']
            min_size = val_dict['min_size']
            additional_criteria_trans = val_dict['additional_criteria_trans']
            minimum_length = val_dict['minimum_length']
            minimum_width = val_dict['minimum_width']
            merge_distance = val_dict['merge_distance']
            dc_express = val_dict['dc_express']
            dc_ref_scale = val_dict['dc_ref_scale']
            dc_severity = val_dict['dc_severity']
            dc_reviewer_session = val_dict['dc_reviewer_session']
            dc_distance = val_dict['dc_distance']
            express_val_mx = val_dict['express_val_mx']
            express_val_mn = val_dict['express_val_mn']
            visible_field = val_dict['visible_field']
            hierarchy_field = val_dict['hierarchy_field']
            search_distance = val_dict['search_distance']
            query = val_dict['query']
            bb_lyr_ex = val_dict['bb_lyr_ex']
            bb_lyr_ex_his = val_dict['bb_lyr_ex_his']
            ref_scale = val_dict['ref_scale']
            minimum_size = val_dict['minimum_size']
            bld_gap = val_dict['bld_gap']
            ap_src_dis_mx = val_dict['ap_src_dis_mx']
            ap_src_dis_mn = val_dict['ap_src_dis_mn']
            orient_dir = val_dict['orient_dir']
            in_prim_sql = val_dict['in_prim_sql']
            max_gap_area = val_dict['max_gap_area']
            fill_option = val_dict['fill_option']
            ln_lyr_ex = val_dict['ln_lyr_ex']
            res_con_line_delete = val_dict['res_con_line_delete']
            river_ex = val_dict['river_ex']
            road_query_rlc = val_dict['road_query_rlc']
            name_fld = val_dict['name_fld']
            distance_b = val_dict['distance_b']
            distance_s = val_dict['distance_s']
            min_area = val_dict['min_area']
            additional_criteria = val_dict['additional_criteria']
            distance_rcl = val_dict['distance_rcl']
            min_length = val_dict['min_length']
            orient_fld = val_dict['orient_fld']
            offset_dist_l = val_dict['offset_dist_l']
            offset_dist_u = val_dict['offset_dist_u']
            offset_dist_benc_l = val_dict['offset_dist_benc_l']
            offset_dist_benc_u = val_dict['offset_dist_benc_u']
            perpendicular_k = val_dict['perpendicular_k']
            perpendicular_b = val_dict['perpendicular_b']
            bench_query = val_dict['bench_query']
            res_con_line_erase_input_fcs = val_dict['res_con_line_erase_input_fcs']
            query_acs = val_dict['query_acs']
            distance_acs = val_dict['distance_acs']
            mx_no_close_fcs_l = val_dict['mx_no_close_fcs_l']
            mx_no_close_fcs_m = val_dict['mx_no_close_fcs_m']
            mx_no_close_fcs_u = val_dict['mx_no_close_fcs_u']
            feature_count_acs = val_dict['feature_count_acs']
            specification = val_dict['specification']
            versions = val_dict['versions']
            small_bldg_2_point_a = fc_dict['small_bldg_2_point_a']
            small_bldg_2_point_p = fc_dict['small_bldg_2_point_p']
            min_size_bldg1 = val_dict['min_size_bldg1']
            sql_bldg = val_dict['sql_bldg']
            min_size_bldg2 = val_dict['min_size_bldg2']
            features_in_cemetery = fc_dict['features_in_cemetery']
            enlarge_min_size = val_dict['enlarge_min_size']
            enlarge_val = val_dict['enlarge_val']
            enlarge_barrier_features = fc_dict['enlarge_barrier_features']
            del_min_area = val_dict['del_min_area']
            delete_small_bldgs = fc_dict['delete_small_bldgs']
            enlarge_bldg_min_width = val_dict['enlarge_bldg_min_width']
            enlarge_bldg_min_length = val_dict['enlarge_bldg_min_length']
            enlarge_building_features = fc_dict['enlarge_building_features']
            enlarge_bldg_additional_criteria = val_dict['additional_criteria']
            simpl_bldg_distance = val_dict['simpl_bldg_distance']
            simplification_tolerance = val_dict['simplification_tolerance']
            delineate_ref_scale = val_dict['delineate_ref_scale']
            delineate_min_bldg_count = val_dict['delineate_min_bldg_count']
            delineate_min_detail_size = val_dict['delineate_min_detail_size']
            delineate_grp_dist = val_dict['delineate_grp_dist']
            delineate_building_layers = fc_dict['delineate_building_layers']
            delineate_edge_features = fc_dict['delineate_edge_features']
            del_small_recreation_fc_min_size = val_dict['del_small_recreation_fc_min_size']
            delete_small_features = fc_dict['delete_small_features']
            erase_sql = val_dict['erase_sql']
            build_delete_input = val_dict['build_delete_input']
            build_create_one_point = val_dict['build_create_one_point']
            build_unique_field = val_dict['build_unique_field']
            
            hydro_prep_fc_list = fc_dict['hydro_prep_fc_list']
            remove_short_line_line_length = val_dict['remove_short_line_line_length']
            hydro_input_polygon_fc = fc_dict['hydro_input_polygon_fc']
            hydro_center_line_fc = fc_dict['hydro_center_line_fc']
            hydro_replace_fc = fc_dict['hydro_replace_fc']
            hydro_np_polygon_width = val_dict['hydro_np_polygon_width']
            hydro_np_polygon_percentage = val_dict['hydro_np_polygon_percentage']
            hydro_simple_tolerance = val_dict['hydro_simple_tolerance']
            hydro_smooth_tolerance = val_dict['hydro_smooth_tolerance']
            hydro_remove_small_poly_exp = val_dict['hydro_remove_small_poly_exp']
            hydro_remove_small_poly_mim_area = val_dict['hydro_remove_small_poly_mim_area']
            hydro_enlarge_poly_mim_size = val_dict['hydro_enlarge_poly_mim_size']
            hydro_enlarge_poly_buffer_dist = val_dict['hydro_enlarge_poly_buffer_dist']
            hydro_remove_near_poly_list = fc_dict['hydro_remove_near_poly_list']
            hydro_remove_near_poly_delete_size = val_dict['hydro_remove_near_poly_delete_size']
            hydro_remove_near_poly_min_size = val_dict['hydro_remove_near_poly_min_size']
            hydro_remove_near_poly_dist = val_dict['hydro_remove_near_poly_dist']
            hydro_remove_near_poly_sql = val_dict['hydro_remove_near_poly_sql']
            hydro_enlarge_poly_sql = val_dict['hydro_enlarge_poly_sql']
            hydro_enlarge_untouch_poly_buffer_dist = val_dict['hydro_enlarge_untouch_poly_buffer_dist']
            hydro_enlarge_poly_list = fc_dict['hydro_enlarge_poly_list']
            hydro_trim_between_polygon_min_area = val_dict['hydro_trim_between_polygon_min_area']
            hydro_trim_between_polygon_distance = val_dict['hydro_trim_between_polygon_distance']
            hydro_remove_small_poly_list = fc_dict['hydro_remove_small_poly_list']
            hydro_remove_small_sql = val_dict['hydro_remove_small_sql']
            hydro_remove_small_min_size = val_dict['hydro_remove_small_min_size']
            hydro_erase_poly_list = fc_dict['hydro_erase_poly_list']
            hydro_erase_poly_max_gap_area = val_dict['hydro_erase_poly_max_gap_area']
            hydro_convert_ungr_river_min_length = val_dict['hydro_convert_ungr_river_min_length']
            hydro_generalized_operation = val_dict['hydro_generalized_operation']
            hydro_delete_input = val_dict['hydro_delete_input']
            hydro_create_one_point = val_dict['hydro_create_one_point']
            hydro_trim_update_val = val_dict['hydro_trim_update_val']
            hydro_unique_field = val_dict['hydro_unique_field']
            remove_close_parallel_per_min = val_dict['remove_close_parallel_per_min']
            remove_close_parallel_per_max = val_dict['remove_close_parallel_per_max']
            remove_close_dist = val_dict['remove_close_dist']
            remove_close_tolerance = val_dict['remove_close_tolerance']
            hydro_line_dangle_min_length = val_dict['hydro_line_dangle_min_length']
            hydro_small_line_fc_list = fc_dict['hydro_small_line_fc_list']
            hydro_small_point_fc_list = fc_dict['hydro_small_point_fc_list']
            hydro_small_fc_min_length = val_dict['hydro_small_fc_min_length']

            vegetation_min_area = val_dict['vegetation_min_area']
            vegetation_eliminate_area = val_dict['vegetation_eliminate_area']
            veg_lyrs_list = fc_dict['veg_lyrs_list']
            veg_field_values = fc_dict['veg_field_values']

            utility_area_features = fc_dict['utility_area_features']
            utility_point_features = fc_dict['utility_point_features']
            utility_compare_features = fc_dict['utility_compare_features']
            utility_min_size_sewerage = val_dict['utility_min_size_sewerage'] 
            utility_min_size_building = val_dict['utility_min_size_building']
            utility_min_size = val_dict['utility_min_size']
            utility_beffer_dist = val_dict['utility_beffer_dist']
            utility_dist = val_dict['utility_dist']
            utility_dist_shorter = val_dict['utility_dist_shorter']
            utility_addi_criteria_sewerage = val_dict['utility_addi_criteria_sewerage']
            utility_addi_criteria = val_dict['utility_addi_criteria']
            utility_merge_field = val_dict['utility_merge_field']
            utility_delete_input = val_dict['utility_delete_input']
            utility_create_one_point = val_dict['utility_create_one_point']
            utility_update_val = val_dict['utility_update_val']
            utility_unique_field = val_dict['utility_unique_field']
            increase_hydro_line_min_length = val_dict['increase_hydro_line_min_length']
            
            hypso_compare_features = fc_dict['hypso_compare_features']
            hypso_dissolved_field = val_dict['hypso_dissolved_field']
            hypso_dist = val_dict['hypso_dist']
            hypso_parallel_per = val_dict['hypso_parallel_per']
            hypso_min_length = val_dict['hypso_min_length']
            hypso_smoothing_tolerance = val_dict['hypso_smoothing_tolerance']
            hypso_increase_factor = val_dict['hypso_increase_factor']
            hypso_size_max = val_dict['hypso_size_max']
            hypso_size_min = val_dict['hypso_size_min']

            prep_line_resolve_fcs_list = fc_dict['prep_line_resolve_fcs_list']

            footprint_fcs = fc_dict['footprint_fcs']
            resolve_line_compare = fc_dict['resolve_line_compare']
            
        logger.info(f'...Completed Data Preparation Theme. Dataset name from config: {dataset_name}')

        # Checking configuration file data inputs
        arcpy.env.workspace = in_feature_loc
        datasets = arcpy.ListDatasets("*", "Feature")
        dataset_list = [dataset for dataset in datasets]
        if len(dataset_list) == 0 and dataset_name != '':
            arcpy.AddWarning('Since geodatabase has no dataset. Please remove dataset name from configuration file and Again run.....')
            sys.exit()
        elif len(dataset_list) > 0 and dataset_name == '':
            arcpy.AddWarning('Since geodatabase has dataset. Please add dataset name in configuration file and Again run.....')
            sys.exit()

        # Starting process based on theme type
        if theme_type == '1-Data Preparation':
            logger.info('Starting Data Preparation Theme.....')
            # Get feature classes
            fc_list = sorted(common_utils.get_fcs(in_feature_loc, dataset_name, logger))

            # Get map sheet from input workspace
            aoi = f'{in_feature_loc}\\AOI'
            # Data cleaning
            theme_01_data_prep.data_cleaning_all_funcs(aoi, fc_list, in_feature_loc, working_gdb, buffer_distance, vertex_limit, buffer_distance_point, feature_count,
                                    not_include_fields, fcs_trim_extend, extend_val, trim_val, buffer_points_25K, feature_to_split, bau_field_fc,logger)
            logger.info(f'Data Prep Theme ran successfully. Starting Backup.....')
            # Backup features data
            backup_path_ext = os.path.join(log_dir, "Backup", "00_AFTExt", "Auto")
            os.makedirs(backup_path_ext, exist_ok=True)
            backup_path_edit_ext = os.path.join(log_dir, "Backup", "00_AFTExt", "Edit")
            os.makedirs(backup_path_edit_ext, exist_ok=True)
            # Backup features data
            backup_path = os.path.join(log_dir, "Backup", "01_AFTDP", "Auto")
            os.makedirs(backup_path, exist_ok=True)
            backup_path_edit = os.path.join(log_dir, "Backup", "01_AFTDP", "Edit")
            os.makedirs(backup_path_edit, exist_ok=True)

            backup_gdb_loc = os.path.join(backup_path, os.path.basename(in_feature_loc))
            if not os.path.exists(backup_gdb_loc) and os.path.isdir(in_feature_loc):
                os.makedirs(backup_gdb_loc)         
            common_utils.backup_data(in_feature_loc, backup_gdb_loc, logger)

        elif theme_type == '2-Transportation Generalization':
            logger.info('Starting Transport Generalization Theme.....')
            # Get feature classes
            fc_list = sorted(common_utils.get_fcs(in_feature_loc, dataset_name, logger))
            # Get CartoPartition from input workspace
            carto_partition = f'{in_feature_loc}\\CartoPartitionA'
            # Get Generalize operation
            generalize_operations = trans_generalized_operation.split(" ")
            # Get changed road type
            change_road_type = trans_changed_road_type.split(",")
            # Transportation Feature to point
            theme_02_transportation.gen_transportation(fc_list, working_gdb, hierarchy_file, in_feature_loc, hierarchy_field, collapse_sql, collapse_size, carto_partition, seg_length, group_sql_rd1, group_sql_rd2,
                       minimum_length_min, minimum_length_max, visible_field, ref_scale, generalize_operations, simple_tolerance, smooth_tolerance, trans_common_express, min_size, trans_delete_input,
                       trans_create_one_point, trans_unique_field, group_sql_track, minimum_length, minimum_width, additional_criteria_trans, railway_sql, merge_field, 
                       merge_distance, trans_update_val, change_road_type, trans_build_up_buildings, trans_topology_features,logger)
            logger.info(f'Transportation Theme ran successfully. Starting Backup.....')
            # Backup features data
            backup_path = os.path.join(log_dir, "Backup", "02_AFTTrans", "Auto")
            os.makedirs(backup_path, exist_ok=True)
            backup_path_edit = os.path.join(log_dir, "Backup", "02_AFTTrans", "Edit")
            os.makedirs(backup_path_edit, exist_ok=True)

            backup_gdb_loc = os.path.join(backup_path, os.path.basename(in_feature_loc))
            if ((not os.path.exists(backup_gdb_loc)) and os.path.isdir(in_feature_loc)):
                os.makedirs(backup_gdb_loc)         
            common_utils.backup_data(in_feature_loc, backup_gdb_loc, logger)

        elif theme_type == '3-Hydrography Generalization':
            logger.info('Starting Hydrography Generalization Theme.....')
            # Get feature classes
            fc_list = sorted(common_utils.get_fcs(in_feature_loc, dataset_name, logger))
            # Get Generalize operation
            generalize_operations = hydro_generalized_operation.split(" ")
            # Hydrography Feature Generalisation
            theme_03_hydrography.gen_hydrography(fc_list, hydro_prep_fc_list, name_fld, remove_short_line_line_length, working_gdb, hydro_input_polygon_fc, hydro_center_line_fc, hydro_np_polygon_width, 
                            hydro_np_polygon_percentage, visible_field, hydro_replace_fc, generalize_operations, hydro_simple_tolerance, hydro_smooth_tolerance, hydro_trim_update_val, in_feature_loc, hydro_remove_small_poly_exp,
                            hydro_remove_small_poly_mim_area, hydro_enlarge_poly_mim_size, hydro_enlarge_poly_buffer_dist, hydro_remove_near_poly_list, hydro_remove_near_poly_delete_size, 
                            hydro_remove_near_poly_min_size, hydro_remove_near_poly_dist, hydro_remove_near_poly_sql, hydro_enlarge_poly_sql, hydro_enlarge_untouch_poly_buffer_dist, 
                            hydro_enlarge_poly_list, hydro_trim_between_polygon_min_area, hydro_trim_between_polygon_distance, hydro_remove_small_poly_list, hydro_remove_small_sql, 
                            hydro_remove_small_min_size, hydro_erase_poly_list, hydro_erase_poly_max_gap_area, hydro_convert_ungr_river_min_length, increase_hydro_line_min_length, 
                            remove_close_parallel_per_min, remove_close_parallel_per_max, remove_close_dist, remove_close_tolerance, hydro_line_dangle_min_length, hydro_small_line_fc_list, hydro_small_point_fc_list, 
                            hydro_small_fc_min_length, hydro_delete_input, hydro_create_one_point, hydro_unique_field, logger)
            logger.info(f'Hydrography Theme ran successfully. Starting Backup.....')
            # Backup features data
            backup_path = os.path.join(log_dir, "Backup", "03_AFTHydro", "Auto")
            os.makedirs(backup_path, exist_ok=True)
            backup_path_edit = os.path.join(log_dir, "Backup", "03_AFTHydro", "Edit")
            os.makedirs(backup_path_edit, exist_ok=True)

            backup_gdb_loc = os.path.join(backup_path, os.path.basename(in_feature_loc))
            if not os.path.exists(backup_gdb_loc) and os.path.isdir(in_feature_loc):
                os.makedirs(backup_gdb_loc)         
            common_utils.backup_data(in_feature_loc, backup_gdb_loc, logger)

        elif theme_type == '4-Built-up Generalization':
            logger.info('Starting Built-up Generalization Theme.....')
            # Get feature classes
            fc_list = sorted(common_utils.get_fcs(in_feature_loc, dataset_name, logger))
            # Built-Up Feature Generalisation
            theme_04_buildup.gen_buildup(fc_list, small_bldg_2_point_a, small_bldg_2_point_p, min_size_bldg1, sql_bldg, build_delete_input, build_create_one_point, build_unique_field, 
                        working_gdb, min_size_bldg2, features_in_cemetery, enlarge_min_size, enlarge_val, enlarge_barrier_features, delete_small_bldgs, del_min_area, 
                        enlarge_building_features, enlarge_bldg_min_width, enlarge_bldg_min_length, enlarge_bldg_additional_criteria, simpl_bldg_distance, delineate_building_layers, 
                        delineate_edge_features, delineate_grp_dist, delineate_min_detail_size, delineate_min_bldg_count, in_feature_loc, delineate_ref_scale, del_small_recreation_fc_min_size, 
                        delete_small_features, erase_sql, simplification_tolerance, logger)
            logger.info(f'Built-up Theme ran successfully. Starting Backup.....')
            # Backup features data
            backup_path = os.path.join(log_dir, "Backup", "04_AFTBuiltUp", "Auto")
            os.makedirs(backup_path, exist_ok=True)
            backup_path_edit = os.path.join(log_dir, "Backup", "04_AFTBuiltUp", "Edit")
            os.makedirs(backup_path_edit, exist_ok=True)

            backup_gdb_loc = os.path.join(backup_path, os.path.basename(in_feature_loc))
            if not os.path.exists(backup_gdb_loc) and os.path.isdir(in_feature_loc):
                os.makedirs(backup_gdb_loc)         
            common_utils.backup_data(in_feature_loc, backup_gdb_loc, logger)


        elif theme_type == '5-Utilities Generalization':
            logger.info('Starting Utilities Generalization Theme.....')
            # Get feature classes
            fc_list = sorted(common_utils.get_fcs(in_feature_loc, dataset_name, logger))
            # Utility Feature Generalisation  
            theme_05_utility.gen_utility(fc_list, utility_area_features, utility_point_features, utility_compare_features, utility_min_size_sewerage, utility_min_size_building, utility_min_size, utility_beffer_dist, 
                        utility_dist, utility_dist_shorter, utility_addi_criteria_sewerage, utility_addi_criteria, utility_merge_field, working_gdb, utility_unique_field, utility_update_val,
                        utility_delete_input, utility_create_one_point, logger)
            logger.info(f'Utilities Theme ran successfully. Starting Backup.....')
            # Backup features data
            backup_path = os.path.join(log_dir, "Backup", "05_AFTUtil", "Auto")
            os.makedirs(backup_path, exist_ok=True)
            backup_path_edit = os.path.join(log_dir, "Backup", "05_AFTUtil", "Edit")
            os.makedirs(backup_path_edit, exist_ok=True)

            backup_gdb_loc = os.path.join(backup_path, os.path.basename(in_feature_loc))
            if not os.path.exists(backup_gdb_loc) and os.path.isdir(in_feature_loc):
                os.makedirs(backup_gdb_loc)         
            common_utils.backup_data(in_feature_loc, backup_gdb_loc, logger)


        elif theme_type == '6-Hypsography Generalization':
            logger.info('Starting Hypsography Generalization Theme.....')
            # Get feature classes
            fc_list = sorted(common_utils.get_fcs(in_feature_loc, dataset_name, logger))
            # Hypsography Feature Generalisation 
            theme_06_hypsography.gen_hypsography(fc_list, hypso_compare_features, hypso_dissolved_field, hypso_dist, hypso_parallel_per, hypso_min_length, hypso_smoothing_tolerance, hypso_increase_factor, hypso_size_max, 
                            hypso_size_min, working_gdb, logger)
            logger.info(f'Hypsography Theme ran successfully. Starting Backup.....')
            # Backup features data
            backup_path = os.path.join(log_dir, "Backup", "06_AFTHypso", "Auto")
            os.makedirs(backup_path, exist_ok=True)
            backup_path_edit = os.path.join(log_dir, "Backup", "06_AFTHypso", "Edit")
            os.makedirs(backup_path_edit, exist_ok=True)

            backup_gdb_loc = os.path.join(backup_path, os.path.basename(in_feature_loc))
            if not os.path.exists(backup_gdb_loc) and os.path.isdir(in_feature_loc):
                os.makedirs(backup_gdb_loc)         
            common_utils.backup_data(in_feature_loc, backup_gdb_loc, logger)


        elif theme_type == '7-Vegetation Generalization':
            logger.info('Starting Vegetation Generalization Theme.....')
            # Get feature classes
            fc_list = sorted(common_utils.get_fcs(in_feature_loc, dataset_name, logger))
            # Vegetation Feature Generalisation  
            theme_07_vegetation.gen_vegetation(fc_list, vegetation_min_area, vegetation_eliminate_area, veg_lyrs_list, veg_field_values, working_gdb, logger)
            logger.info(f'Vegetation Theme ran successfully. Starting Backup.....')
            # Backup features data
            backup_path = os.path.join(log_dir, "Backup", "07_AFTVeg", "Auto")
            os.makedirs(backup_path, exist_ok=True)
            backup_path_edit = os.path.join(log_dir, "Backup", "07_AFTVeg", "Edit")
            os.makedirs(backup_path_edit, exist_ok=True)

            backup_gdb_loc = os.path.join(backup_path, os.path.basename(in_feature_loc))
            if not os.path.exists(backup_gdb_loc) and os.path.isdir(in_feature_loc):
                os.makedirs(backup_gdb_loc)         
            common_utils.backup_data(in_feature_loc, backup_gdb_loc, logger)


        elif theme_type == '8-Apply Carto Symbology':
            logger.info('Starting Theme Apply Carto Symbology.....')
            # Get feature classes
            fc_list = sorted(common_utils.get_fcs(in_feature_loc, dataset_name, logger))
            carto_partition = f'{in_feature_loc}\\CartoPartitionA'
            # Clear map contents
            map_name1 = common_utils.create_map_add_layers(map_name_apply_carto)
            LG.clear_map_contents(map_name1)
            # Apply Carto Symbology
            theme_08_apply_carto_symbology.apply_carto_symbology(fc_list, attribution_fc_list, express_list, query_list, field_list, intersecting_fc_list, working_gdb, query_acs, visible_field, 
                    distance_acs, mx_no_close_fcs_l, mx_no_close_fcs_m, mx_no_close_fcs_u, in_feature_loc, feature_count_acs, vst_workspace, specification, hierarchy_file, hierarchy_field, 
                    prep_line_resolve_fcs_list, carto_partition, symbology_file_path, map_name1, apply_symbology_layers_list,logger)
            # Layer grouping and reordering
            sheet_name = "group_layer_mapping"
            LG.layer_grouping(map_name1, excel_file, sheet_name, logger)
            LG.reorder_group_layers(map_name1, excel_file, sheet_name, logger)
            logger.info(f'Apply Carto Symbology Theme ran successfully. Starting Backup.....')
            # Backup features data
            backup_path = os.path.join(log_dir, "Backup", "08_AFTAS", "Auto")
            os.makedirs(backup_path, exist_ok=True)
            backup_path_edit = os.path.join(log_dir, "Backup", "08_AFTAS", "Edit")
            os.makedirs(backup_path_edit, exist_ok=True)

            backup_gdb_loc = os.path.join(backup_path, os.path.basename(in_feature_loc))
            if not os.path.exists(backup_gdb_loc) and os.path.isdir(in_feature_loc):
                os.makedirs(backup_gdb_loc)         
            common_utils.backup_data(in_feature_loc, backup_gdb_loc, logger)

        
        elif theme_type == '9a-Resolve Conflict for Lines':
            logger.info('Starting Resolve Conflicts for Lines Theme.....')
            # Get feature classes
            fc_list = sorted(common_utils.get_fcs(in_feature_loc, dataset_name, logger))
            # Clear map contents
            map_name1 = common_utils.create_map_add_layers(map_name_resolve_lines)
            LG.clear_map_contents(map_name1)
            # Get CartoPartition from input workspace
            carto_partition = f'{in_feature_loc}\\CartoPartitionA'
            theme_09a_resolve_conflict_lines.resolve_conflict_lines(fc_list, in_feature_loc, input_line_layers, ln_lyr_ex, symbology_file_path, ref_scale, hierarchy_field, working_gdb, res_con_line_delete, carto_partition,
                        edge_features, river_ex, road_query_rlc, name_fld, distance_b, distance_s, min_area, additional_criteria, visible_field, distance_rcl, min_length, res_con_line_erase_input_fcs,
                        embank_list, compare_fcs_embank, orient_fld, offset_dist_l, offset_dist_u, offset_dist_benc_l, offset_dist_benc_u, perpendicular_k, perpendicular_b, bench_query,
                        bridge_query, footprint_fcs, resolve_line_compare, road_query, log_dir, map_name1, logger)
            # Apply symbology for all layers in the map
            theme_08_apply_carto_symbology.calc_vst_on_workspace(fc_list, symbology_file_path, apply_symbology_layers_list, map_name1, in_feature_loc)
            # Layer grouping and reordering
            sheet_name = "group_layer_mapping_9"
            LG.layer_grouping(map_name1, excel_file, sheet_name, logger)
            LG.reorder_group_layers(map_name1, excel_file, sheet_name, logger)
            logger.info(f'Resolve Conflict for Lines Theme ran successfully. Starting Backup.....')
            # Backup features data
            backup_path = os.path.join(log_dir, "Backup", "09a_AFTRCL", "Auto")
            os.makedirs(backup_path, exist_ok=True)
            backup_path_edit = os.path.join(log_dir, "Backup", "09a_AFTRCL", "Edit")
            os.makedirs(backup_path_edit, exist_ok=True)

            backup_gdb_loc = os.path.join(backup_path, os.path.basename(in_feature_loc))
            if not os.path.exists(backup_gdb_loc) and os.path.isdir(in_feature_loc):
                os.makedirs(backup_gdb_loc)         
            common_utils.backup_data(in_feature_loc, backup_gdb_loc, logger)


        elif theme_type == '9b-Resolve Conflict for Buildings':
            logger.info('Starting Resolve Conflict for Buildings Theme.....')
            # Get feature classes
            fc_list = sorted(common_utils.get_fcs(in_feature_loc, dataset_name, logger))
            map_name1 = common_utils.create_map_add_layers(map_name_resolve_polygons)
            # Clear map contents
            LG.clear_map_contents(map_name1)
            theme_09b_resolve_conflict_buildings.resolve_conflict_buildings(fc_list, build_up_area_fcs, express_val_mx, express_val_mn, hierarchy_field, search_distance, query, input_building_layers, input_barrier_layers, bb_lyr_ex, 
                            bb_lyr_ex_his, hierarchy_field, visible_field, symbology_file_path, ref_scale, minimum_size, bld_gap, ap_src_dis_mn, ap_src_dis_mx, orient_dir, g1_align_features, 
                            g4_align_features, g5_input_points, g5_align_features, g6_align_features, g7_input_points, g7_align_features, input_primary, input_secondary, in_prim_sql, 
                            max_gap_area, fill_option, working_gdb, map_name1, log_dir, logger)
            # Apply symbology for all layers in the map
            theme_08_apply_carto_symbology.calc_vst_on_workspace(fc_list, symbology_file_path, apply_symbology_layers_list, map_name1, in_feature_loc)
            # Layer grouping and reordering
            sheet_name = "group_layer_mapping_9"
            LG.layer_grouping(map_name1, excel_file, sheet_name, logger)
            LG.reorder_group_layers(map_name1, excel_file, sheet_name, logger)
            logger.info(f'Resolve Conflict for Buildings Theme ran successfully. Starting Backup.....')
            # Backup features data
            backup_path = os.path.join(log_dir, "Backup", "09b_AFTRCB", "Auto")
            os.makedirs(backup_path, exist_ok=True)
            backup_path_edit = os.path.join(log_dir, "Backup", "09b_AFTRCB", "Edit")
            os.makedirs(backup_path_edit, exist_ok=True)

            backup_gdb_loc = os.path.join(backup_path, os.path.basename(in_feature_loc))
            if not os.path.exists(backup_gdb_loc) and os.path.isdir(in_feature_loc):
                os.makedirs(backup_gdb_loc)         
            common_utils.backup_data(in_feature_loc, backup_gdb_loc, logger)

        
        elif theme_type == '10-Detect Conflict':
            logger.info('Starting Detect Conflict Theme.....')
            # Get feature classes
            fc_list = sorted(common_utils.get_fcs(in_feature_loc, dataset_name, logger))
            # Clear map contents
            map_name1 = common_utils.create_map_add_layers(map_name_detect)
            LG.clear_map_contents(map_name1)
            # Get CartoPartition from input workspace
            carto_partition = f'{in_feature_loc}\\CartoPartitionA'
            # Detect and write conflicts: Structure to Structure
            Structure2Structure = list(filter(str.strip, Structure2Structure))
            Structure2Structure = [fc for struct in Structure2Structure for fc in fc_list if str(struct) in fc]
            theme_10_detect_conflict.detect_write_conflicts(in_feature_loc, Structure2Structure, dc_express, Structure2Structure, dc_distance, rev_workspace, dc_reviewer_session, dc_severity, dc_ref_scale, 
                                carto_partition, map_name1, symbology_file_path, logger)
            
            # Detect and write conflicts: Structure to Lines
            Structure2Lines = list(filter(str.strip, Structure2Lines))
            Structure2Lines = [fc for s2l in Structure2Lines for fc in fc_list if str(s2l) in fc]
            theme_10_detect_conflict.detect_write_conflicts(in_feature_loc, Structure2Structure, dc_express, Structure2Lines, dc_distance, rev_workspace, dc_reviewer_session, dc_severity, dc_ref_scale, 
                                carto_partition, map_name1, symbology_file_path, logger)
            
            # Detect and write conflicts: Lines to Lines
            Lines2Lines = list(filter(str.strip, Lines2Lines))
            Lines2Lines = [fc for struct in Lines2Lines for fc in fc_list if str(struct) in fc]
            theme_10_detect_conflict.detect_write_conflicts(in_feature_loc, Lines2Lines, dc_express, Lines2Lines, dc_distance, rev_workspace, dc_reviewer_session, dc_severity, dc_ref_scale, 
                                carto_partition, map_name1, symbology_file_path, logger)
            
            # # Detect and write conflicts: Polygon to Polygon G1
            G1_Poly2Poly = list(filter(str.strip, G1_Poly2Poly))
            G1_Poly2Poly = [fc for struct in G1_Poly2Poly for fc in fc_list if str(struct) in fc]
            theme_10_detect_conflict.detect_write_conflicts(in_feature_loc, G1_Poly2Poly, dc_express, G1_Poly2Poly, dc_distance, rev_workspace, dc_reviewer_session, dc_severity, dc_ref_scale, 
                                carto_partition, map_name1, symbology_file_path, logger)
            
            # Detect and write conflicts: Polygon to Polygon G2
            G2_Poly2Poly = list(filter(str.strip, G2_Poly2Poly))
            G2_Poly2Poly = [fc for struct in G2_Poly2Poly for fc in fc_list if str(struct) in fc]
            theme_10_detect_conflict.detect_write_conflicts(in_feature_loc, G2_Poly2Poly, dc_express, G2_Poly2Poly, dc_distance, rev_workspace, dc_reviewer_session, dc_severity, dc_ref_scale, 
                                carto_partition, map_name1, symbology_file_path, logger)
            
            # Detect and write conflicts: Polygon to Polygon G3
            G3_Poly2Poly = list(filter(str.strip, G3_Poly2Poly))
            G3_Poly2Poly = [fc for struct in G3_Poly2Poly for fc in fc_list if str(struct) in fc]
            theme_10_detect_conflict.detect_write_conflicts(in_feature_loc, G3_Poly2Poly, dc_express, G3_Poly2Poly, dc_distance, rev_workspace, dc_reviewer_session, dc_severity, dc_ref_scale, 
                                carto_partition, map_name1, symbology_file_path, logger)
            
            # Apply symbology for all layers in the map
            theme_08_apply_carto_symbology.calc_vst_on_workspace(fc_list, symbology_file_path, apply_symbology_layers_list, map_name1, in_feature_loc)
            # Layer grouping and reordering
            sheet_name = "group_layer_mapping_10"
            LG.layer_grouping(map_name1, excel_file, sheet_name, logger)
            LG.reorder_group_layers(map_name1, excel_file, sheet_name, logger)
            logger.info(f'Detect Conflict Theme ran successfully. Starting Backup.....')
            # Backup features data
            backup_path = os.path.join(log_dir, "Backup", "10_AFTDC", "Auto")
            os.makedirs(backup_path, exist_ok=True)
            backup_path_edit = os.path.join(log_dir, "Backup", "10_AFTDC", "Edit")
            os.makedirs(backup_path_edit, exist_ok=True)

            backup_gdb_loc = os.path.join(backup_path, os.path.basename(in_feature_loc))
            if not os.path.exists(backup_gdb_loc) and os.path.isdir(in_feature_loc):
                os.makedirs(backup_gdb_loc)         
            common_utils.backup_data(in_feature_loc, backup_gdb_loc, logger)


        elif theme_type == '11-Load Data into CARTO100K':
            logger.info('Starting Load Data into CARTO100K Theme.....')
            # Get map sheet from input workspace
            aoi = f'{in_feature_loc}\\AOI'
            # Load data into gdb or ent db
            theme_11_load_data.load_data_into_edb(in_feature_loc, aoi, out_workspace, versions, working_gdb, logger)
            logger.info(f'Load Data into CARTO100K Theme ran successfully. Starting Backup.....')
            # Backup features data
            backup_path = os.path.join(log_dir, "Backup", "11_Final", "Auto")
            os.makedirs(backup_path, exist_ok=True)
            backup_path_edit = os.path.join(log_dir, "Backup", "11_Final", "Edit")
            os.makedirs(backup_path_edit, exist_ok=True)

            backup_gdb_loc = os.path.join(backup_path, os.path.basename(in_feature_loc))
            if not os.path.exists(backup_gdb_loc) and os.path.isdir(in_feature_loc):
                os.makedirs(backup_gdb_loc)         
            common_utils.backup_data(in_feature_loc, backup_gdb_loc, logger)


        # Delete temp file from working gdb
        arcpy.env.workspace = working_gdb
        temp_file = arcpy.ListFeatureClasses() + arcpy.ListTables()
        if temp_file:
            arcpy.management.Delete(temp_file)
        
        end_time = time.time()
        logger.info(f"Ending time: {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(end_time))}")
        total_time = end_time - start_time
        logger.info(f"The cartographic generalisation process is successfully completed with {total_time} s")
        arcpy.AddMessage(f"The cartographic generalisation process is successfully completed.....")

    except Exception as e:
        exc_type, exc_value, exc_traceback = sys.exc_info()
        tb = traceback.format_exc()
        error_message = f'Gen carto 100k error: {e}\nTraceback details:\n{tb}'
        logger.error(error_message)
        common_utils.simplified_msgs('Gen carto 100k', f'{exc_value}\n')
    except arcpy.ExecuteError:
        logger.error(arcpy.GetMessages(2))

if __name__ == '__main__':
    main()
