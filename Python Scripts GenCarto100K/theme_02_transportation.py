import arcpy
import traceback
import sys
from common_utils import *

def collapse_replace(input_line_list, collapse_sql, collapse_size, carto_partition, working_gdb):
    # Set the workspace
    arcpy.env.overwriteOutput = True
    # Set the cartographic partitions
    arcpy.env.cartographicPartitions = carto_partition
    try:
        for input_line, colps_sql in zip(input_line_list, collapse_sql):
            fc_singlepart = arcpy.management.MultipartToSinglepart(input_line, f"{working_gdb}\\fc_singlepart")
            if colps_sql != '' and colps_sql != None:
                in_lyr = arcpy.management.MakeFeatureLayer(fc_singlepart, "in_lyr", colps_sql)
            else:
                in_lyr = arcpy.management.MakeFeatureLayer(fc_singlepart, "in_lyr")

            # Run Collapse Road Detail
            collapse_out = "Collapse"
            arcpy.AddMessage("Collapsing Road Detail")
            arcpy.cartography.CollapseRoadDetail(in_lyr, f'{collapse_size} Meters', collapse_out)
            # Select features and delete features
            arcpy.management.SelectLayerByLocation(input_line, "WITHIN", in_lyr, None, "NEW_SELECTION", "NOT_INVERT")
            # Delete all features in original feature class
            arcpy.AddMessage("Replacing geometry on original features")
            arcpy.management.DeleteFeatures(input_line)
            # Append collups out features with input features
            arcpy.management.Append(collapse_out, input_line, "NO_TEST")
            # Delete temp files
            arcpy.management.Delete([fc_singlepart, "Collapse", "in_lyr"])

    except Exception as e:
        tb = traceback.format_exc()
        error_message = f"Collapse replace error: {e}\nTraceback details:\n{tb}"
        arcpy.AddMessage(error_message)

def trans_delete_dangles(trans_lines, sql, compare_fcs, seg_length, working_gdb, recursive):
    # Define environment variables
    arcpy.env.overwriteOutput = 1
    arcpy.env.workspace = working_gdb

    try:
        # Denote dangles using points using the
        # Feature Vertices to Points GP tool at dangles
        arcpy.AddMessage("Creating points at dangles...")
        dangles = arcpy.management.FeatureVerticesToPoints(trans_lines, "dangles", "DANGLE").getOutput(0)
        # Use Describe function to get SHAPE Length field
        shp_len_fld = arcpy.da.Describe(trans_lines)['lengthFieldName']
        # Create feature layer of hydro lines where
        # length of segment < seg_length and Name field
        # is an empty string or NULL
    
        where = f"{shp_len_fld} < {seg_length}"
        if sql:
            where += " AND "  + "(" + sql + ")"
        arcpy.management.MakeFeatureLayer(trans_lines, "transport", where)
        feature_count = int(arcpy.management.GetCount("transport")[0])
        if feature_count >= 1:
            if recursive == "true":
                count = 1
                while feature_count >= 1:
                    feature_count = delete_dangles("transport", dangles, seg_length, compare_fcs, working_gdb)
                    arcpy.management.SelectLayerByAttribute("transport", "NEW_SELECTION", where)
                    count += 1
        else:
            delete_dangles("transport", dangles, seg_length, compare_fcs, working_gdb)

        # Delete temp files
        arcpy.management.Delete([dangles, "transport"])

    except Exception as e:
            tb = traceback.format_exc()
            error_message = f"Delete dangles ain error: {e}\nTraceback details:\n{tb}"
            arcpy.AddMessage(error_message)

def thin_road_network(in_features, minimum_length_min, minimum_length_max, invisibility_field, hierarchy_field, ref_scale, carto_partition, working_gdb):
    arcpy.AddMessage("Starting thin road networking")
    try:
        # Set the workspace
        arcpy.env.overwriteOutput = True
        # Set the reference scale
        arcpy.env.referenceScale = ref_scale
        # Set the cartographic partitions
        arcpy.env.cartographicPartitions = carto_partition

        carto_high_where = "RANK >= 3 AND RANK IS NOT NULL"
        carto_low_where  = "RANK < 3 AND RANK IS NOT NULL"
        
        # arcpy.AddMessage(f"Cartographic partition: {carto_partition} \n in_features: {in_features}")
        for in_feature in in_features:
            arcpy.SetProgressorLabel(f"Processing thin road networking for {in_feature}")
            fc_singlepart = arcpy.management.MultipartToSinglepart(in_feature, f"{working_gdb}\\fc_singlepart")
            arcpy.management.MakeFeatureLayer(fc_singlepart, "fc_singlepart_lyr")
            selected_features_high = arcpy.analysis.Select(carto_partition, f"{working_gdb}\\road_carto_rank_high_fc", carto_high_where)
            arcpy.management.SelectLayerByLocation(
                in_layer="fc_singlepart_lyr",
                overlap_type="WITHIN",
                select_features=selected_features_high,
                selection_type="NEW_SELECTION"
            )

            if has_features("fc_singlepart_lyr") > 0:
                arcpy.cartography.ThinRoadNetwork(
                    "fc_singlepart_lyr",
                    f"{minimum_length_max} Meters",
                    invisibility_field,
                    hierarchy_field
                )
            selected_features_low = arcpy.analysis.Select(carto_partition, f"{working_gdb}\\road_carto_rank_low_fc", carto_low_where)
            arcpy.management.SelectLayerByLocation(
                in_layer="fc_singlepart_lyr",
                overlap_type="WITHIN",
                select_features=selected_features_low,
                selection_type="NEW_SELECTION"
            )
            if has_features("fc_singlepart_lyr") > 0:
                arcpy.cartography.ThinRoadNetwork(
                    "fc_singlepart_lyr",
                    f"{minimum_length_min} Meters",
                    invisibility_field,
                    hierarchy_field
                )
            arcpy.management.SelectLayerByAttribute("fc_singlepart_lyr", "CLEAR_SELECTION")
            arcpy.SetProgressorLabel(f"Repairing Geometry")
            arcpy.management.RepairGeometry("fc_singlepart_lyr")
            arcpy.SetProgressorLabel(f"Deleting Features in {in_feature}")
            arcpy.management.DeleteFeatures(in_feature)
            arcpy.SetProgressorLabel(f"Adding Generated Features in {in_feature}")
            arcpy.management.Append("fc_singlepart_lyr", in_feature, "NO_TEST")
            # Delete temp files
            arcpy.management.Delete([f'{working_gdb}\\road_carto_rank_high_fc', f'{working_gdb}\\road_carto_rank_low_fc', f"{working_gdb}\\fc_singlepart"])
  
    except Exception as e:
            tb = traceback.format_exc()
            error_message = f"Thin road network error: {e}\nTraceback details:\n{tb}"
            arcpy.AddMessage(error_message)

def grouping(input_line_list, group_sql_rd1, group_sql_rd2, group_sql_track):
    arcpy.AddMessage(f"Processing grouping for {len(input_line_list)} feature classes")
    try:
        for fc in input_line_list:
            if 'TA0060_Road_L' in fc:
                # Add Field
                if len(arcpy.ListFields(fc, "Road_Group")) == 0:
                    arcpy.management.AddField(in_table=fc, field_name="Road_Group", field_type="TEXT")
                arcpy.management.SelectLayerByAttribute(fc, "NEW_SELECTION", group_sql_rd1)
                arcpy.management.CalculateField(in_table=fc, field="Road_Group", expression='"Highway"', expression_type="PYTHON3")
                arcpy.management.SelectLayerByAttribute(fc, "NEW_SELECTION", group_sql_rd2)
                arcpy.management.CalculateField(in_table=fc, field="Road_Group", expression='"Road"', expression_type="PYTHON3")

            elif 'TA0110_Track_L' in fc:
                # Add Field
                if len(arcpy.ListFields(fc, "Track_Group")) == 0:
                    arcpy.management.AddField(in_table=fc, field_name="Track_Group", field_type="TEXT")
                arcpy.management.SelectLayerByAttribute(fc, "NEW_SELECTION", group_sql_track)
                arcpy.management.CalculateField(in_table=fc, field="Track_Group", expression='"Track"', expression_type="PYTHON3")

    except Exception as e:
        tb = traceback.format_exc()
        error_message = f"Transportation grouping error: {e}\nTraceback details:\n{tb}"
        arcpy.AddMessage(error_message)   

def gen_transportation(feature_list, working_gdb, hierarchy_file, in_feature_loc, hierarchy_field, collapse_sql, collapse_size, carto_partition, seg_length, group_sql_rd1, group_sql_rd2, 
                       minimum_length_min, minimum_length_max, invisibility_field, ref_scale, generalize_operations, simple_tolerance, smooth_tolerance, trans_common_express, min_size, delete_input, 
                       one_point, unique_field, group_sql_track, minimum_length, minimum_width, additional_criteria, railway_sql, merge_field, merge_distance, update, change_road_type, 
                       trans_build_up_buildings, trans_topology_features, logger):
    
    arcpy.AddMessage('Starting transportation features generalization.....')
    # Set environment
    arcpy.env.overwriteOutput = True
    try:
        total_steps = 9
        # Remove empty string  
        input_line_list = [fc for in_line in ['TA0060_Road_L', 'TA0110_Track_L'] for fc in feature_list if str(in_line) in fc]
        compare_fcs_list = list(filter(str.strip, trans_build_up_buildings))
        compare_fcs_list = sorted([fc for a_lyr in trans_build_up_buildings for fc in feature_list if str(a_lyr) in fc])
        aoi_l = f"{in_feature_loc}\\AOI_L"
        compare_fcs_list.append(aoi_l)

        # Integrate features
        arcpy.management.Integrate(input_line_list)
        # Repair Geometry
        for  fc in input_line_list:
            if has_features(fc):
                arcpy.management.RepairGeometry(fc, 'DELETE_NULL', 'ESRI')
        # Populate hierarchy
        populate_hierarchy(hierarchy_file, in_feature_loc, hierarchy_field, working_gdb)
        # Flag looping
        for input_line in input_line_list:
            flag_loops(input_line, working_gdb, hierarchy_field)
        # Road collapse and Replace
        collapse_replace(input_line_list, collapse_sql, collapse_size, carto_partition, working_gdb)
        # Delete dangles
        delete_dngl_sql = "NAM IS NOT NULL AND NAM <> ''"
        recursive = "true"
        for trans_lines in input_line_list:
            if arcpy.da.Describe(trans_lines)['baseName'] == 'TA0060_Road_L':
                compare_fcs_list.insert(0, input_line_list[1])
            elif arcpy.da.Describe(trans_lines)['baseName'] == 'TA0110_Track_L':
                compare_fcs_list.insert(0, input_line_list[0])
            trans_delete_dangles(trans_lines, delete_dngl_sql, compare_fcs_list, seg_length, working_gdb, recursive)
        # Thin road network reducing
        thin_road_network(input_line_list, minimum_length_min, minimum_length_max, invisibility_field, hierarchy_field, ref_scale, carto_partition, working_gdb)
        # Smooth road
        # Insert main feature into topology fcs list
        # Insert main feature into topology fcs list
        topology_fcs = list(filter(str.strip, trans_topology_features))
        topology_fcs = [fc for topo in topology_fcs for fc in feature_list if str(topo) in fc]
        for input_fc in input_line_list:
            if has_features(input_fc):
                arcpy.SetProgressorLabel(f"Generalizing Shared Feature: {arcpy.da.Describe(input_fc)['baseName']}")
                if arcpy.da.Describe(input_fc)['name'] == 'TA0060_Road_L':
                    main_fc = arcpy.management.MakeFeatureLayer(input_fc, "main_fc", trans_common_express)
                    topology_fcs.insert(0, main_fc)
                    selected_fc = arcpy.management.SelectLayerByAttribute(main_fc, "NEW_SELECTION", "RCS <> 5")
                    if has_features(selected_fc):
                        gen_shared_features(main_fc, generalize_operations, simple_tolerance, smooth_tolerance, working_gdb, topology_fcs)
                    arcpy.management.SelectLayerByAttribute(main_fc, "SWITCH_SELECTION", "RCS <> 5")
                    if has_features(main_fc):
                        gen_shared_features(main_fc, generalize_operations, simple_tolerance, smooth_tolerance, working_gdb, topology_fcs)
                    topology_fcs.remove(main_fc)

                else:
                    main_fc = arcpy.management.MakeFeatureLayer(input_fc, "main_fc", trans_common_express)
                    topology_fcs.insert(0, main_fc)
                    if has_features(main_fc):
                        gen_shared_features(main_fc, generalize_operations, simple_tolerance, smooth_tolerance, working_gdb, topology_fcs)
                    topology_fcs.remove(main_fc)

        # Grouping
        grouping(input_line_list, group_sql_rd1, group_sql_rd2, group_sql_track)
        # Polygon to point
        polygon_point_features = [fc for com_fc in ['TA0150_Toll_Plaza_A', 'BJ0030_Rail_Terminal_Railway_Station_A'] for fc in feature_list if str(com_fc) in fc]
        toll_plaza_p = [fc for fc in feature_list if 'TA0150_Toll_Plaza_P' in fc][0]
        rail_station_p = [fc for fc in feature_list if 'BJ0030_Rail_Terminal_Railway_Station_P' in fc][0]
        temp_list = [toll_plaza_p, rail_station_p]
        for poly_fc, point_fc in zip(polygon_point_features, temp_list):
            feature2point(working_gdb, poly_fc, point_fc, min_size, delete_input, one_point, unique_field, None)
        # Extend polygon sides
        building_fc = [fc for fc in feature_list if 'TA0150_Toll_Plaza_A' in fc]
        extend_polygon_sides(building_fc, working_gdb, minimum_length, minimum_width, additional_criteria, None)
        # Merge parallel roads
        # RTR = 3
        railway_sql_3 = railway_sql[0]
        # RTR = 1
        railway_sql_1 = railway_sql[1]
        # Get feature class
        rail = [fc for fc in feature_list if 'TA0010_Rail_Line_L' in fc][0]
        merge_parallel_roads(rail, railway_sql_3, merge_field, merge_distance, update, change_road_type[0], working_gdb)
        merge_parallel_roads(rail, railway_sql_1, merge_field, merge_distance, update, change_road_type[1], working_gdb)

    except Exception as e:
        exc_type, exc_value, exc_traceback = sys.exc_info()
        tb = traceback.format_exc()
        error_message = f"Transportation generalisation error: {e}\nTraceback details:\n{tb}"
        logger.error(error_message)
        simplified_msgs('Transportation generalisation', f'{exc_value}\n')

