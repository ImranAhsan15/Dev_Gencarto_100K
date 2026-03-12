import arcpy
import traceback
import sys
from common_utils import *
import re
import os
import time


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
        feature_count = count_features("transport")
        if feature_count >= 1:
            if recursive == "true":
                delete_dangles("transport", dangles, seg_length, compare_fcs, working_gdb)
                arcpy.management.SelectLayerByAttribute("transport", "NEW_SELECTION", where)
        else:
            delete_dangles("transport", dangles, seg_length, compare_fcs, working_gdb)

        # Delete temp files
        arcpy.management.Delete([dangles, "transport"])

    except Exception as e:
            tb = traceback.format_exc()
            error_message = f"Delete dangles error: {e}\nTraceback details:\n{tb}"
            arcpy.AddMessage(error_message)


# changes for model to script by imran
def thin_road_network(in_features, minimum_length_min, minimum_length_max, invisibility_field, hierarchy_field, ref_scale, carto_high_sql, carto_low_sql, carto_partition, working_gdb):
    arcpy.AddMessage("Starting thin road networking")
    try:
        # Set the workspace
        arcpy.env.overwriteOutput = True
        # Set the reference scale
        arcpy.env.referenceScale = ref_scale
        # Set the cartographic partitions
        arcpy.env.cartographicPartitions = carto_partition

        carto_high_where = carto_high_sql
        carto_low_where  = carto_low_sql

        
        # arcpy.AddMessage(f"Cartographic partition: {carto_partition} \n in_features: {in_features}")
    
        arcpy.SetProgressorLabel(f"Processing thin road networking for {in_features[0]} and {in_features[1]}")
        fc_singlepart_road = arcpy.management.MultipartToSinglepart(in_features[0], f"{working_gdb}\\fc_singlepart_road")
        fc_singlepart_track = arcpy.management.MultipartToSinglepart(in_features[1], f"{working_gdb}\\fc_singlepart_track")
        arcpy.management.MakeFeatureLayer(fc_singlepart_road, "fc_singlepart_road_lyr")
        arcpy.management.MakeFeatureLayer(fc_singlepart_track, "fc_singlepart_track_lyr")

        selected_features_high = arcpy.analysis.Select(carto_partition, f"{working_gdb}\\road_carto_rank_high_fc", carto_high_where)
        selected_fc_singlepart_road_lyr=arcpy.management.SelectLayerByLocation(
            in_layer="fc_singlepart_road_lyr",
            overlap_type="WITHIN",
            select_features=selected_features_high,
            selection_type="NEW_SELECTION"
        )
        selected_fc_singlepart_track_lyr=arcpy.management.SelectLayerByLocation(
            in_layer="fc_singlepart_track_lyr",
            overlap_type="WITHIN",
            select_features=selected_features_high,
            selection_type="NEW_SELECTION"
        )

        if count_features("fc_singlepart_road_lyr") > 0 and count_features("fc_singlepart_track_lyr") > 0 :
            arcpy.cartography.ThinRoadNetwork(
                f"{selected_fc_singlepart_road_lyr};{selected_fc_singlepart_track_lyr}",
                f"{minimum_length_max} Meters",
                invisibility_field,
                hierarchy_field
            )
            arcpy.AddMessage("Applied Thin Road Network function for maximum distance")


        selected_features_low = arcpy.analysis.Select(carto_partition, f"{working_gdb}\\road_carto_rank_low_fc", carto_low_where)
        selected_low_fc_singlepart_road_lyr = arcpy.management.SelectLayerByLocation(
            in_layer="fc_singlepart_road_lyr",
            overlap_type="WITHIN",
            select_features=selected_features_low,
            selection_type="NEW_SELECTION"
        )
        selected_low_fc_singlepart_track_lyr = arcpy.management.SelectLayerByLocation(
            in_layer="fc_singlepart_track_lyr",
            overlap_type="WITHIN",
            select_features=selected_features_low,
            selection_type="NEW_SELECTION"
        )
        if count_features("fc_singlepart_road_lyr") > 0 and count_features("fc_singlepart_track_lyr") > 0:
            arcpy.cartography.ThinRoadNetwork(
                f"{selected_low_fc_singlepart_road_lyr};{selected_low_fc_singlepart_track_lyr}",
                f"{minimum_length_min} Meters",
                invisibility_field,
                hierarchy_field
            )
            arcpy.AddMessage("Applied Thin Road Network function for minimum distance")

        arcpy.management.SelectLayerByAttribute("fc_singlepart_road_lyr", "CLEAR_SELECTION")
        arcpy.management.SelectLayerByAttribute("fc_singlepart_track_lyr", "CLEAR_SELECTION")
        arcpy.SetProgressorLabel(f"Repairing Geometry")
        arcpy.management.RepairGeometry("fc_singlepart_road_lyr")
        arcpy.management.RepairGeometry("fc_singlepart_track_lyr")


        arcpy.SetProgressorLabel(f"Deleting Features in {in_features[0]} and {in_features[1]}")
        arcpy.management.DeleteFeatures(in_features[0])
        arcpy.management.DeleteFeatures(in_features[1])

        arcpy.SetProgressorLabel(f"Adding Generated Features in {in_features[0]} and {in_features[1]}")
        arcpy.management.Append("fc_singlepart_road_lyr", in_features[0], "NO_TEST")
        arcpy.management.Append("fc_singlepart_track_lyr", in_features[1], "NO_TEST")
        # Delete temp files
        # arcpy.management.Delete([f'{working_gdb}\\road_carto_rank_high_fc', f'{working_gdb}\\road_carto_rank_low_fc', f"{working_gdb}\\fc_singlepart_road", f"{working_gdb}\\fc_singlepart_track"])
        arcpy.AddMessage("Thin Road Network function completed")



    except Exception as e:
            tb = traceback.format_exc()
            error_message = f"Thin road network error: {e}\nTraceback details:\n{tb}"
            arcpy.AddMessage(error_message)
 # changes for model to script by imran

def grouping(input_line_list, group_sql_rd1, group_sql_rd2, group_sql_track):
    arcpy.AddMessage(f"Processing grouping for {len(input_line_list)} feature classes")
    try:
        for fc in input_line_list:
            if dynamic_fc_names.Road_L in fc:
                # Add Field
                if len(arcpy.ListFields(fc, "Road_Group")) == 0:
                    arcpy.management.AddField(in_table=fc, field_name="Road_Group", field_type="TEXT")
                arcpy.management.SelectLayerByAttribute(fc, "NEW_SELECTION", group_sql_rd1)
                arcpy.management.CalculateField(in_table=fc, field="Road_Group", expression='"Highway"', expression_type="PYTHON3")
                arcpy.management.SelectLayerByAttribute(fc, "NEW_SELECTION", group_sql_rd2)
                arcpy.management.CalculateField(in_table=fc, field="Road_Group", expression='"Road"', expression_type="PYTHON3")

            elif dynamic_fc_names.Track_L in fc:
                # Add Field
                if len(arcpy.ListFields(fc, "Track_Group")) == 0:
                    arcpy.management.AddField(in_table=fc, field_name="Track_Group", field_type="TEXT")
                arcpy.management.SelectLayerByAttribute(fc, "NEW_SELECTION", group_sql_track)
                arcpy.management.CalculateField(in_table=fc, field="Track_Group", expression='"Track"', expression_type="PYTHON3")

    except Exception as e:
        tb = traceback.format_exc()
        error_message = f"Transportation grouping error: {e}\nTraceback details:\n{tb}"
        arcpy.AddMessage(error_message)   



def remove_short_road_in_terrace_house(road_fc, bldg_fc, search_tolerance, working_gdb, length_tolerance, road_class_field, road_class_type, name_field, invisibility_field, invisibility_field_2, hierarchy_field, logger):
    # Set environment variables
    arcpy.env.overwriteOutput = True
    arcpy.env.workspace = working_gdb
    try:
        arcpy.AddMessage("Applying remove back lane function") 
        if length_tolerance != 0:
            # Get length field
            length_field = arcpy.da.Describe(road_fc)['lengthFieldName']
            name_query = f"({name_field} = '' or {name_field} = ' ' or {name_field} IS NULL)"
            # Create make feature layer for road and building
            copy_road_lyr = arcpy.management.CopyFeatures(road_fc, f"{working_gdb}\\copy_road_lyr")
            arcpy.management.MakeFeatureLayer(road_fc, "road_layer")
            # Select building features with RET <= 3 (Terrace houses)
            arcpy.management.SelectLayerByAttribute(in_layer_or_view=bldg_fc, selection_type="NEW_SELECTION", where_clause="RET <= 3")
            # Dissolve selected building features
            dissolved_terrace_bldg_lyr = arcpy.management.Dissolve(in_features=bldg_fc, out_feature_class=f"{working_gdb}\\dissolved_terrace_bldg_lyr")
            arcpy.management.MakeFeatureLayer(dissolved_terrace_bldg_lyr, "dissolved_terrace_bldg_lyr")
            # Select features within a distance
            arcpy.management.SelectLayerByLocation(in_layer="road_layer", overlap_type="WITHIN_A_DISTANCE", select_features="dissolved_terrace_bldg_lyr", search_distance=f"{search_tolerance} Meters",
                selection_type="NEW_SELECTION")
            # Select feature by attribute
            if count_features("road_layer")>0:
                arcpy.cartography.ThinRoadNetwork(in_features=road_fc, minimum_length=length_tolerance, invisibility_field=invisibility_field_2, hierarchy_field=hierarchy_field)
                warnings = arcpy.GetMessages(1)
                # Extract all txt paths from the warning text
                txt_files = re.findall(r'[A-Za-z]:\\[^\n]*\.txt', warnings)
                sharedgeom_file = None
                for file in txt_files:
                    if "SharedGeom" in file:
                        sharedgeom_file = file
                        break
                arcpy.AddMessage(f"SharedGeom file: {sharedgeom_file}")
                if sharedgeom_file != None:
                    # Wait until ArcGIS finishes writing the file
                    while not os.path.exists(sharedgeom_file):
                        time.sleep(1)
                    # Read ObjectIDs
                    object_ids = []
                    with open(sharedgeom_file, "r") as f:
                        text = f.read()
                        ids = re.findall(r'OBJECTID\s*=\s*(\d+)', text)
                        object_ids = [int(i) for i in ids]
                    # convert list → SQL string
                    oid_string = ",".join(map(str, object_ids))
                    query = f"OBJECTID NOT IN ({oid_string})"
                    if len(object_ids)>0: 
                        where_clause=f"{length_field} < {length_tolerance} And {road_class_field} = {road_class_type} And {name_query} And {invisibility_field_2} = 1 And {query}"
                        arcpy.AddMessage(f"{where_clause}")
                        arcpy.management.SelectLayerByAttribute(in_layer_or_view="road_layer", selection_type="SUBSET_SELECTION", where_clause=f"{length_field} < {length_tolerance} And {road_class_field} = {road_class_type} And {name_query} And {invisibility_field_2} = 1 And {query}")
                        arcpy.AddMessage(f"deleting {count_features("road_layer")} features")
                        arcpy.management.DeleteFeatures("road_layer")
                        arcpy.AddMessage("Remove backlane function completed successfully with sharedgeom file")
                else:
                    arcpy.management.SelectLayerByAttribute(in_layer_or_view="road_layer", selection_type="SUBSET_SELECTION", where_clause=f"{length_field} < {length_tolerance} And {road_class_field} = {road_class_type} And {name_query} And {invisibility_field} = 1")
                    # Delete features
                    arcpy.AddMessage(f"deleting {count_features("road_layer")} features")
                    arcpy.management.DeleteFeatures("road_layer")
                    arcpy.AddMessage("Remove backlane function completed successfully")
        else:
            arcpy.AddMessage("Leangth value with 0 meter cannot be processed, change the the value in config file")
            arcpy.AddMessage("Skipping Remove backlane function")

    except Exception as e:
        exc_type, exc_value, exc_traceback = sys.exc_info()
        tb = traceback.format_exc()
        error_message = f"Road feature remove in terrace area error: {e}\nTraceback details:\n{tb}"
        logger.error(error_message)
        simplified_msgs('Road feature remove in terrace area', f'{exc_value}\n')

# changes for model to script by imran
def resolve_segmented_symbology_fortransport(transport_layer, transport_symbology_field, transport_symbology_RCS, working_gdb, logger):
    arcpy.env.overwriteOutput = True
    arcpy.env.workspace = working_gdb
    try:
        rcs_values = []
        with arcpy.da.SearchCursor(transport_layer, [transport_symbology_RCS]) as cursor:
            for row in cursor:
                if row[0] is not None:
                    rcs_values.append(row[0])
        rcs_values = list(set(rcs_values))
        for indv_rcs in rcs_values:
            if indv_rcs == 4:
                arcpy.management.CalculateField(in_table=transport_layer, field=transport_symbology_field , expression="2",
                                                expression_type="PYTHON3",
                                                code_block="", field_type="TEXT", enforce_domains="NO_ENFORCE_DOMAINS")
                transport_layer=arcpy.management.SelectLayerByAttribute(in_layer_or_view=transport_layer, selection_type="NEW_SELECTION",
                                                        where_clause=f"{transport_symbology_RCS} = {indv_rcs}", invert_where_clause=None)
                dangle_points = arcpy.management.FeatureVerticesToPoints(in_features=transport_layer,
                                                                        out_feature_class=f"{working_gdb}\\dangle_points",
                                                                        point_location="DANGLE")
                transport_layer=arcpy.management.SelectLayerByLocation(in_layer=transport_layer, overlap_type="INTERSECT",
                                                    select_features=dangle_points,
                                                    search_distance=None, selection_type="SUBSET_SELECTION",
                                                    invert_spatial_relationship="NOT_INVERT")
                arcpy.management.CalculateField(in_table=transport_layer, field=transport_symbology_field, expression="0",
                                                expression_type="PYTHON3",
                                                code_block="", field_type="TEXT", enforce_domains="NO_ENFORCE_DOMAINS")
                transport_layer=arcpy.management.SelectLayerByAttribute(in_layer_or_view=transport_layer, selection_type="NEW_SELECTION",
                                                        where_clause=f"{transport_symbology_RCS} = {indv_rcs} And {transport_symbology_field} = 2",
                                                        invert_where_clause=None)
                arcpy.management.CalculateField(in_table=transport_layer, field=transport_symbology_field, expression="1",
                                                expression_type="PYTHON3",code_block="", field_type="TEXT", enforce_domains="NO_ENFORCE_DOMAINS")
                
        arcpy.AddMessage("Applied Resolve Segmented Symbology for Transport function")
    except Exception as e:
        exc_type, exc_value, exc_traceback = sys.exc_info()
        tb = traceback.format_exc()
        error_message = f"Resolve segmented symbology for Transport error: {e}\nTraceback details:\n{tb}"
        logger.error(error_message)
        simplified_msgs('Resolve segmented symbology for Transport', f'{exc_value}\n')
# changes for model to script by imran


def gen_transportation(feature_list, working_gdb, hierarchy_file, in_feature_loc, collapse_sql, carto_partition, generalize_operations, railway_sql, 
                                                       change_road_type, trans_build_up_buildings, trans_topology_features, val_dict, logger):
    
    arcpy.AddMessage('Starting transportation features generalization.....')
    # Set environment
    arcpy.env.overwriteOutput = True
    global dynamic_fc_names
    dynamic_fc_names = resolve_lyr()
    try:
        total_steps = 9
        # Remove empty string  
        input_line_list = [fc for in_line in [ dynamic_fc_names.Road_L, dynamic_fc_names.Track_L] for fc in feature_list if str(in_line) in fc]
        compare_fcs_list = list(filter(str.strip, trans_build_up_buildings))
        compare_fcs_list = sorted([fc for a_lyr in trans_build_up_buildings for fc in feature_list if str(a_lyr) in fc])
        aoi_l = f"{in_feature_loc}\\AOI_L"

        # # changes for model to script by imran
        # # compare_fcs_list.append(aoi_l)
        # # changes for model to script by imran
     

        # Integrate features
        arcpy.management.Integrate(input_line_list)
        # Repair Geometry
        for  fc in input_line_list:
            if has_features(fc):
                arcpy.management.RepairGeometry(fc, 'DELETE_NULL', 'ESRI')
        # Populate hierarchy
        populate_hierarchy(hierarchy_file, in_feature_loc, val_dict['Resolve_conflict_build_hierarchy_field'], working_gdb)

        # Flag looping
        for input_line in input_line_list:
            flag_loops(input_line, working_gdb, val_dict['Resolve_conflict_build_hierarchy_field'])
        # Road collapse and Replace
        collapse_replace(input_line_list, collapse_sql, val_dict['Transport_collapse_size'], carto_partition, working_gdb)


        # Delete dangles
        delete_dngl_sql = val_dict["Transport_delete_dangle_sql"]
        recursive = "true"
        # changes for model to script by imran
        selected_compare_fcs = []
        for comp_fcs in compare_fcs_list:
            out_comp_fcs = "make_ft_"+os.path.basename(comp_fcs)+"_layer"
            arcpy.AddMessage(f"{out_comp_fcs} and {val_dict["Transport_short_delete_dangles_sql"]}")
            out_comp_fcs_list = arcpy.management.MakeFeatureLayer(comp_fcs, out_comp_fcs, val_dict["Transport_short_delete_dangles_sql"])
            selected_compare_fcs.append(out_comp_fcs_list)
        selected_compare_fcs.append(aoi_l)  
        for trans_lines in input_line_list:
            if os.path.basename(trans_lines) == dynamic_fc_names.Road_L:
                if(os.path.basename(str(selected_compare_fcs[0]))==dynamic_fc_names.Road_L):
                    selected_compare_fcs.remove(selected_compare_fcs[0])
                selected_compare_fcs.insert(0, input_line_list[1])
            elif os.path.basename(trans_lines) == dynamic_fc_names.Track_L:
                if(os.path.basename(str(selected_compare_fcs[0]))==dynamic_fc_names.Track_L):
                    selected_compare_fcs.remove(selected_compare_fcs[0])
                selected_compare_fcs.insert(0, input_line_list[0])

            arcpy.AddMessage(f"{trans_lines} and {selected_compare_fcs}")
            
            trans_delete_dangles(trans_lines, delete_dngl_sql, selected_compare_fcs, val_dict['Transport_min_seg_length'], working_gdb, recursive)
        # end changes for model to script by imran
        
        
        
        
        
        # Thin road network reducing
        thin_road_network(input_line_list, val_dict['Transport_minimum_length_min'], val_dict['Transport_minimum_length_max'], val_dict['Transportation_invisible_field'], 
                          val_dict['Transportation_hierarchy_field'], val_dict['Resolve_conflict_build_ref_scale'], 
                          val_dict["Transport_ThinRoad_Carto_High_sql"], val_dict["Transport_ThinRoad_Carto_low_sql"], carto_partition, working_gdb)
       
       
        # Smooth road
        # Insert main feature into topology fcs list
        topology_fcs = list(filter(str.strip, trans_topology_features))
        topology_fcs = [fc for topo in topology_fcs for fc in feature_list if str(topo) in fc]
        for input_fc in input_line_list:
            if has_features(input_fc):
                arcpy.SetProgressorLabel(f"Generalizing Shared Feature: {arcpy.da.Describe(input_fc)['baseName']}")
                if os.path.basename(input_fc) == dynamic_fc_names.Road_L:
                    main_fc = arcpy.management.MakeFeatureLayer(input_fc, "main_fc", val_dict['Transport_common_express'])
                    topology_fcs.insert(0, main_fc)
                    # selected_fc = arcpy.management.SelectLayerByAttribute(main_fc, "NEW_SELECTION", "RCS <> 5")
                    # if has_features(selected_fc):
                    track_fc = input_line_list[1]
                    gen_shared_features(main_fc, generalize_operations, val_dict['Transport_simplify_tolerance'], val_dict['Transport_smooth_tolerance'], working_gdb, topology_fcs, track_fc)
                    # arcpy.management.SelectLayerByAttribute(main_fc, "SWITCH_SELECTION", "RCS <> 5")
                    # if has_features(main_fc):
                    #     gen_shared_features(main_fc, generalize_operations, simple_tolerance, smooth_tolerance, working_gdb, topology_fcs)
                    topology_fcs.remove(main_fc)

                else:
                    main_fc = arcpy.management.MakeFeatureLayer(input_fc, "main_fc", val_dict['Transport_common_express'])
                    road_fc = input_line_list[0]
                    topology_fcs.insert(0, main_fc)
                    if has_features(main_fc):
                        gen_shared_features(main_fc, generalize_operations, val_dict['Transport_simplify_tolerance'], val_dict['Transport_smooth_tolerance'], working_gdb, topology_fcs, road_fc)
                    topology_fcs.remove(main_fc)

        # Grouping
        grouping(input_line_list, val_dict['Transport_group_sql_rd1'], val_dict['Transport_group_sql_rd2'], val_dict['Transport_group_sql_track'])
        # Polygon to point
        polygon_point_features = [fc for com_fc in [ dynamic_fc_names.Toll_Plaza_A, dynamic_fc_names.Rail_Terminal_Railway_Station_A] for fc in feature_list if str(com_fc) in fc]
        toll_plaza_p = [fc for fc in feature_list if dynamic_fc_names.Toll_Plaza_P in fc][0]
        rail_station_p = [fc for fc in feature_list if dynamic_fc_names.Rail_Terminal_Railway_Station_P in fc][0]
        temp_list = [toll_plaza_p, rail_station_p]
        for poly_fc, point_fc in zip(polygon_point_features, temp_list):
            feature2point(working_gdb, poly_fc, point_fc, val_dict['Transport_min_size'], val_dict['Transport_delete_input'], val_dict['Transport_create_one_point'], val_dict['Transport_unique_field'], None)
        # Extend polygon sides
        building_fc = [fc for fc in feature_list if dynamic_fc_names.Toll_Plaza_A in fc]
        extend_polygon_sides(building_fc, working_gdb, val_dict['Transport_minimum_length'], val_dict['Transport_minimum_width'], val_dict['Transport_additional_criteria'], None)
        # Merge parallel roads
        # RTR = 3
        railway_sql_3 = railway_sql[0]
        # RTR = 1
        railway_sql_1 = railway_sql[1]
        # Get feature class
        rail = [fc for fc in feature_list if dynamic_fc_names.Rail_Line_L in fc][0]
        merge_parallel_roads(rail, railway_sql_3, val_dict['Transport_merge_field'], val_dict['Transport_merge_distance'], val_dict['Transport_update_val'], change_road_type[0], working_gdb)
        merge_parallel_roads(rail, railway_sql_1, val_dict['Transport_merge_field'], val_dict['Transport_merge_distance'], val_dict['Transport_update_val'], change_road_type[1], working_gdb)
        
        # Applying remove back lane function
        road_fc=[fc for fc in feature_list if dynamic_fc_names.Road_L in fc][0]
        bldg_fc=[fc for fc in feature_list if dynamic_fc_names.Residential_Building_A in fc][0]
        road_class_field = val_dict['Transport_Terrace_road_class_field']
        road_class_type = val_dict.get('Transport_Terrace_road_class_type') or 4
        name_field=val_dict['Transport_unique_field']
        invisibility_field_2="RoadCasing"
        invisibility_field =  "INVISIBILITY"
        remove_short_road_in_terrace_house(road_fc, bldg_fc, val_dict['Transport_remove_backlane_distance'], working_gdb, val_dict['Transport_remove_backlane_length'], road_class_field, road_class_type, name_field, val_dict["Transportation_invisible_field"], val_dict["Transportation_backlane_invisible_field"], val_dict['Transportation_hierarchy_field'], logger)
        # calculate orientation degree field for attribute driven symbology based on connected road and dangle road
        road_fc=[fc for fc in feature_list if dynamic_fc_names.Road_L in fc][0]
        # changes for model to script by imran
        resolve_segmented_symbology_fortransport(road_fc,val_dict["Transport_Symbology_Field"], val_dict["Transport_Symbology_Road_Class"], working_gdb, logger)
        # changes for model to script by imran
    
    except Exception as e:
        exc_type, exc_value, exc_traceback = sys.exc_info()
        tb = traceback.format_exc()
        error_message = f"Transportation generalisation error: {e}\nTraceback details:\n{tb}"
        logger.error(error_message)
        simplified_msgs('Transportation generalisation', f'{exc_value}\n')

