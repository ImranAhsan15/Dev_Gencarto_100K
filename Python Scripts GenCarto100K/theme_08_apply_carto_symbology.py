import arcpy
import traceback
import sys
from common_utils import *

def timestamp():
    """Return current timestamp as string."""
    return datetime.now()

def has_features(fc):
    with arcpy.da.SearchCursor(fc, ["OID@"]) as cursor:
        return next(cursor, None) is not None  # True if at least one feature

def split_at_intersection(input_line, split_lines, working_gdb):
    arcpy.env.overwriteOutput = True
    try:
        spat_ref = arcpy.da.Describe(input_line)['spatialReference']

        split_points = []
        for split_line in split_lines:
            # Determine intersections
            arcpy.AddMessage("Determining intersections with " + str(split_line))
            near = arcpy.analysis.GenerateNearTable(input_line, split_line, f"{working_gdb}\\near", "0 Meters", closest="ALL")

            arcpy.AddMessage(str(int(arcpy.management.GetCount(near)[0])))
            near_dict = {} 
            split_oids = []
            in_oids = []
            if has_features(near):
                with arcpy.da.SearchCursor(near, ["IN_FID", "NEAR_FID"]) as cursor:
                    for row in cursor:
                        # If this is the first record for that in_fid value
                        if row[0] not in in_oids:
                            #add to the touching_ids list and near dictionary
                            in_oids.append(row[0])
                            near_dict[row[0]] = [row[1]]
                            split_oids.append(row[1])
                        else:
                            # Updated the dictionary to add the new near id
                            cur_list = near_dict[row[0]]
                            cur_list.append(row[1])
                            near_dict[row[0]] = cur_list
                            split_oids.append(row[1])

            split_oids = set(split_oids)
            if len(in_oids) >= 1:
                arcpy.AddMessage("Getting intersection points")
                split_geos = {}
                # Get the geometries for the split features
                if has_features(split_line):
                    with arcpy.da.SearchCursor(split_line, ['OID@', 'SHAPE@']) as cursor:
                        for row in cursor:
                            if row[0] in split_oids:
                                split_geos[row[0]] = row[1]
                if has_features(input_line):
                    with arcpy.da.SearchCursor(input_line, ['OID@', 'SHAPE@']) as cursor:
                        for row in cursor:
                            if row[0] in in_oids:
                                near_oid = near_dict[row[0]]
                                for oid in near_oid:
                                    near_geo = split_geos[oid]
                                    pts = row[1].intersect(near_geo, 1)
                                    for pt in pts:
                                        split_points.append(arcpy.PointGeometry(pt, spat_ref))

        if len(split_points) >= 1:
            arcpy.AddMessage("Splitting at intersections")
            pt_fc = arcpy.management.CopyFeatures(split_points, "intersect_pts_split")
            split_line_result = arcpy.management.SplitLineAtPoint(input_line, pt_fc, "split_at_intersect", "1 Meters")
            arcpy.management.RepairGeometry(split_line_result)
            arcpy.management.DeleteFeatures(input_line)
            arcpy.management.Append(split_line_result, input_line, "NO_TEST")
            split_lines.append(input_line)
            arcpy.management.Integrate(split_lines)

        if arcpy.Exists(f"{working_gdb}\\near"):
            arcpy.management.Delete(f"{working_gdb}\\near")

    except Exception as e:
        tb = traceback.format_exc()
        error_message = f"Split at intersection error: {e}\nTraceback details:\n{tb}"
        arcpy.AddMessage(error_message)

def hide_near_lines_by_count(hide_line, vis_field, distance, test_value, comp_lines, working_gdb):
    # Set environment
    arcpy.env.overwriteOutput = True
    try:
        max_val = 0
        rank_dict = {}
        higher_list = []
        hide_cnt = 0
        near_dict = {}

        close_lines = f"{working_gdb}\\close_lines"

        near = arcpy.analysis.GenerateNearTable(hide_line, comp_lines, close_lines, distance, closest="ALL")

        with arcpy.da.SearchCursor(near, ("IN_FID", "NEAR_RANK")) as cursor:
            for row in cursor:
                id_val = row[0]
                rank = row[1]
                if id_val not in near_dict:
                    near_dict[id_val] = rank
                else:
                    cur_rank = near_dict[id_val]
                    if rank > cur_rank:
                        near_dict[id_val] = rank

        for key, value in near_dict.items():
            if value > max_val:
                max_val = value

            if value in rank_dict:
                cur_cnt = rank_dict[value]
                rank_dict[value] = cur_cnt + 1
            else:
                rank_dict[value] = 1

            if value > test_value:
                higher_list.append(key)
                hide_cnt += 1

        arcpy.AddMessage("Maximum near line count is " + str(max_val))
        arcpy.AddMessage("Features to hide count is " + str(hide_cnt))
        arcpy.AddMessage(str(rank_dict))

        with arcpy.da.UpdateCursor(hide_line, ('OID@', vis_field)) as cursor:
            for row in cursor:
                if row[0] in higher_list:
                    row[1] = 1
                    cursor.updateRow(row)

        if arcpy.Exists(close_lines):
            arcpy.management.Delete(close_lines)

    except Exception as e:
        tb = traceback.format_exc()
        error_message = f"Hide near lines by count error: {e}\nTraceback details:\n{tb}"
        arcpy.AddMessage(error_message)

def add_layers(fc_list, map_name):
    try:
        aprx = arcpy.mp.ArcGISProject('CURRENT')
        maps = aprx.listMaps(map_name)[0]
        for fc in fc_list:
            if has_features(fc):
                maps.addDataFromPath(fc)
        aprx.save()
        del aprx
    except Exception as e:
        tb = traceback.format_exc()
        error_message = f"Add layers error: {e}\nTraceback details:\n{tb}"
        arcpy.AddMessage(error_message)

def apply_attribution(fc_list, attribution_fc_list, express_list, query_list, field_list):
    try:
        # Get feature list
        attribution_fc_list = list(filter(str.strip, attribution_fc_list))
        attribution_fc_list = [fc for attr_lyr in attribution_fc_list for fc in fc_list if str(attr_lyr) in fc]
        # Remove unneccesary character
        query_list = list(filter(str.strip, query_list))
        field_list = list(filter(str.strip, field_list))
        for attr_fc, express, query, field in zip(attribution_fc_list, express_list, query_list, field_list):
            fc_name = arcpy.da.Describe(attr_fc)['name']
            if(query):
                fcfields = [f.name for f in arcpy.ListFields(attr_fc)]
                if ' ' in field.strip():
                    multiple_fields = field.strip().split(' ')
                    if len(multiple_fields) > 1:
                        for fld in multiple_fields:
                            if fld not in fcfields:
                                arcpy.AddField_management(
                                    in_table=attr_fc,
                                    field_name=fld,
                                    field_type='SHORT'
                                )
                else:
                    if field not in fcfields:
                        arcpy.AddField_management(
                            in_table=attr_fc,
                            field_name=field,
                            field_type='SHORT'
                        )       
            feature_layer = arcpy.management.MakeFeatureLayer(attr_fc, f"{fc_name}_layer")
            selected_road_fc = arcpy.management.SelectLayerByAttribute(feature_layer, "NEW_SELECTION", query)
            if ' ' in field.strip():
                multiple_fields = field.strip().split(' ')
                if len(multiple_fields) > 1:
                    for fld in multiple_fields:
                        arcpy.management.CalculateField(in_table=selected_road_fc, field=fld, expression=express, expression_type='PYTHON3')

    except Exception as e:
        tb = traceback.format_exc()
        error_message = f"Apply attribution error: {e}\nTraceback details:\n{tb}"
        arcpy.AddMessage(error_message)

def embankment_cutting(fc_list, intersecting_fc_list, working_gdb):
    try:
        intersecting_fc_list = list(filter(str.strip, intersecting_fc_list))
        intersecting_fc_list = [fc for intersect_fc in intersecting_fc_list for fc in fc_list if str(intersect_fc) in fc]
        cutting = [fc for fc in fc_list if 'RA0070_Cutting_L' in fc][0]
        embankment = [fc for fc in fc_list if 'RA0080_Embankment_L' in fc][0]
        split_at_intersection(cutting, intersecting_fc_list, working_gdb)
        split_at_intersection(embankment, intersecting_fc_list, working_gdb)

    except Exception as e:
        tb = traceback.format_exc()
        error_message = f"Embankment Cutting error: {e}\nTraceback details:\n{tb}"
        arcpy.AddMessage(error_message)

def prep_4_line_resolve(fc_list, query, visible_field, distance, mx_no_close_fcs_l, mx_no_close_fcs_m, mx_no_close_fcs_u, prep_line_resolve_fcs_list, working_gdb):
    try:
        prep_line_resolve_fcs_list = list(filter(str.strip, prep_line_resolve_fcs_list))
        prep_line_resolve_fcs_list = [fc for prep_line in prep_line_resolve_fcs_list for fc in fc_list if str(prep_line) in fc]
        # Required feature class
        generalised_bldg = [fc for fc in fc_list if 'BJ0500_Generalised_Buildings_A' in fc][0]
        town_built_up = [fc for fc in fc_list if 'BJ0073_Town_Built_up_A' in fc][0]
        cutting = [fc for fc in fc_list if 'RA0070_Cutting_L' in fc][0]
        feature_layer_cutting = arcpy.management.MakeFeatureLayer(cutting, "cutting_layer")
        embankment = [fc for fc in fc_list if 'RA0080_Embankment_L' in fc][0]

        feature_layer_embankment = arcpy.management.MakeFeatureLayer(embankment, "embankment_layer")
        sel_generalised_bldg_em = arcpy.management.SelectLayerByLocation(feature_layer_embankment, "WITHIN", generalised_bldg, "", "NEW_SELECTION")
        sel_town_built_em = arcpy.management.SelectLayerByLocation(feature_layer_embankment, "WITHIN", town_built_up, "", "NEW_SELECTION")
        sel_generalised_bldg_cut = arcpy.management.SelectLayerByLocation(feature_layer_cutting, "WITHIN", generalised_bldg, "", "NEW_SELECTION")
        sel_town_built_cut = arcpy.management.SelectLayerByLocation(feature_layer_cutting, "WITHIN", town_built_up, "", "NEW_SELECTION")
        # Delete features
        arcpy.management.DeleteFeatures(sel_generalised_bldg_em)
        arcpy.management.DeleteFeatures(sel_town_built_em)
        arcpy.management.DeleteFeatures(sel_generalised_bldg_cut)
        arcpy.management.DeleteFeatures(sel_town_built_cut)

        compare_layers = []
        for in_features in prep_line_resolve_fcs_list:
            if has_features(in_features):
                fc_name = arcpy.da.Describe(in_features)['name']
                if "TA0060_Road_L" in in_features:
                    desc = arcpy.da.Describe(in_features)
                    oid_fld_name = desc["OIDFieldName"]
                    feature_layer = arcpy.management.MakeFeatureLayer(in_features, f"feature_layer_{fc_name}", query)
                    compare_layers.append(feature_layer)
                    # Unsplit line
                    road_unsplit = arcpy.management.UnsplitLine(in_features, f"memory\\road_unsplit", ['RCS', 'NAM'], [['OBJECTID', 'FIRST']])
                    # Join field
                    fields_list_selected_fcs = [field.name for field in desc['fields'] if field.name not in ['not_required_flds']]
                    joined_layer = arcpy.management.JoinField(road_unsplit, 'FIRST_OBJECTID', in_features, oid_fld_name, fields_list_selected_fcs)
                    # Delete features
                    arcpy.management.DeleteFeatures(feature_layer)
                    append_layer = arcpy.management.Append(joined_layer, feature_layer, 'NO_TEST')
                    arcpy.management.RepairGeometry(append_layer)

                elif "TA0110_Track_L" in in_features:
                    desc = arcpy.da.Describe(in_features)
                    oid_fld_name = desc["OIDFieldName"]
                    feature_layer = arcpy.management.MakeFeatureLayer(in_features, f"feature_layer_{fc_name}", query)
                    compare_layers.append(feature_layer)
                    # Unsplit line
                    track_unsplit = arcpy.management.UnsplitLine(in_features, f"memory\\track_unsplit", ['NAM'], [['OBJECTID', 'FIRST']])
                    # Join field
                    fields_list_selected_fcs = [field.name for field in (arcpy.da.Describe(in_features))['fields'] if field.name not in ['not_required_flds']]
                    joined_layer = arcpy.management.JoinField(track_unsplit, 'FIRST_OBJECTID', in_features, oid_fld_name, fields_list_selected_fcs)
                    # Delete features
                    arcpy.management.DeleteFeatures(feature_layer)
                    append_layer = arcpy.management.Append(joined_layer, feature_layer, 'NO_TEST')
                    arcpy.management.RepairGeometry(append_layer)

                elif "HH0190_Irrigation_Canal_L" in in_features:
                    desc = arcpy.da.Describe(in_features)
                    oid_fld_name = desc["OIDFieldName"]
                    feature_layer = arcpy.management.MakeFeatureLayer(in_features, f"feature_layer_{fc_name}", query)
                    compare_layers.append(feature_layer)
                    # Unsplit line
                    irrigation_unsplit = arcpy.management.UnsplitLine(in_features, f"memory\\irrigation_unsplit", ['NAM'], [['OBJECTID', 'FIRST']])
                    # Join field
                    fields_list_selected_fcs = [field.name for field in (arcpy.da.Describe(in_features))['fields'] if field.name not in ['not_required_flds']]
                    joined_layer = arcpy.management.JoinField(irrigation_unsplit, 'FIRST_OBJECTID', in_features, oid_fld_name, fields_list_selected_fcs)
                    # Delete features
                    arcpy.management.DeleteFeatures(feature_layer)
                    append_layer = arcpy.management.Append(joined_layer, feature_layer, 'NO_TEST')
                    arcpy.management.RepairGeometry(append_layer)
                else:
                    try: 
                        feature_layer = arcpy.management.MakeFeatureLayer(in_features, f"feature_layer_{fc_name}", query)
                        compare_layers.append(feature_layer)
                    except Exception as e:
                        tb = traceback.format_exc()
                        error_message = f"Make feature layer error for {fc_name}: {e}\nTraceback details:\n{tb}"
                        arcpy.AddMessage(error_message)
                        return False
        # Hide close feature by count
        if "feature_layer_RA0080_Embankment_L" in compare_layers:
            ind = compare_layers.index("feature_layer_RA0080_Embankment_L")
            compare_layers.pop(ind)
            hide_near_lines_by_count("feature_layer_RA00_Embankment_L", visible_field, distance, mx_no_close_fcs_m, compare_layers, working_gdb)
        if "feature_layer_RA0070_Cutting_L" in compare_layers:
            ind = compare_layers.index("feature_layer_RA0070_Cutting_L")
            compare_layers.pop(ind)
            hide_near_lines_by_count("feature_layer_RA0070_Cutting_L", visible_field, distance, mx_no_close_fcs_m, compare_layers, working_gdb)
        if "feature_layer_HH0190_Irrigation_Canal_L" in compare_layers:
            ind = compare_layers.index("feature_layer_HH0190_Irrigation_Canal_L")
            compare_layers.pop(ind)
            hide_near_lines_by_count("feature_layer_HH0190_Irrigation_Canal_L", visible_field, distance, mx_no_close_fcs_u, compare_layers, working_gdb)
        if "feature_layer_BJ0400_Fence_L" in compare_layers:
            ind = compare_layers.index("feature_layer_BJ0400_Fence_L")
            compare_layers.pop(ind)
            hide_near_lines_by_count("feature_layer_BJ0400_Fence_L", visible_field, distance, mx_no_close_fcs_l, compare_layers, working_gdb)
        if "feature_layer_BJ0390_Wall_L" in compare_layers:
            ind = compare_layers.index("feature_layer_BJ0390_Wall_L")
            compare_layers.pop(ind)
            hide_near_lines_by_count("feature_layer_BJ0390_Wall_L", visible_field, distance, mx_no_close_fcs_l, compare_layers, working_gdb)

    except Exception as e:
        tb = traceback.format_exc()
        error_message = f"Preparation for line resolving error: {e}\nTraceback details:\n{tb}"
        arcpy.AddMessage(error_message)

# start here of additional lines for 100k from below 100k_ACP
def split_explode_lines_100k(fc_list,apply_symbology_layers_list,working_gdb):
    try:
        
        apply_symbology_fc_name = list(filter(str.strip, apply_symbology_layers_list))
        apply_symbology_fc_list = [fc for sym_app_lyr in apply_symbology_fc_name for fc in fc_list if str(sym_app_lyr) in fc]
        # Set environment variables
        arcpy.env.overwriteOutput = True
        scratch = working_gdb

        polyline_fc_list = []
        clean_list = []
        update_list = []

        # Loop through each feature class path
        for fc in apply_symbology_fc_list:
            # Get the shape type
            shape_type = arcpy.Describe(fc).shapeType
            if shape_type == "Polyline":
                polyline_fc_list.append(fc)

        vis_field = "INVISIBILITY"
        delete = "DELETE_INVISIBLE"

        try:
            fc_list_line = polyline_fc_list

            where = vis_field + " = 0 OR " + vis_field + " IS NULL"

            for fc_path in fc_list_line:

                fc_name = arcpy.Describe(fc_path).name
                arcpy.AddMessage("Processing " + fc_name)

                # Check for feature classes with no features

                split_fc = scratch + "\\" + fc_name + "_split"
                explode_fc = scratch + "\\" + fc_name + "_explode"
                layer = fc_name + "_layer"

                clean_list.append(explode_fc)
                clean_list.append(split_fc)
                clean_list.append(layer)

                arcpy.management.MakeFeatureLayer(fc_path, layer, where)

                if int(arcpy.management.GetCount(layer)[0]) >= 1:

                    arcpy.AddMessage("  ...Splitting the lines")
                    arcpy.management.FeatureToLine(layer, split_fc)
                    arcpy.AddMessage("  ...Exploding the lines")
                    arcpy.management.MultipartToSinglepart(split_fc, explode_fc)

                    if delete == "DELETE_INVISIBLE":
                        arcpy.management.DeleteFeatures(fc_path)
                    else:
                        arcpy.management.DeleteFeatures(layer)
                    arcpy.management.Append(explode_fc, fc_path, "NO_TEST")

        finally:
            for item in clean_list:
                if arcpy.Exists(item):
                    arcpy.management.Delete(item)

    except Exception as e:
        tb = traceback.format_exc()
        error_message = f"Split and Explode error: {e}\nTraceback details:\n{tb}"
        arcpy.AddMessage(error_message)

    # end here of additional lines for 100k_ACP

def split_explode_lines(fc_list, working_gdb):
    arcpy.AddMessage('Splitting and exploding lines ....')
    try:
        for fc in fc_list:
            fc_name = os.path.basename(fc)
            if fc_name.endswith("_L") and has_features(fc):
                # Process
                feature2line = arcpy.management.FeatureToLine(fc, f"{working_gdb}\\{fc_name}_feature2line")
                single_part = arcpy.management.MultipartToSinglepart(feature2line, f"{working_gdb}\\{fc_name}_single")

                # Replace features safely
                arcpy.management.TruncateTable(fc)
                arcpy.management.Append(single_part, fc, 'NO_TEST')

        # Cleanup temp layers
        for lyr in [f"{working_gdb}\\{fc_name}_feature2line", f"{working_gdb}\\{fc_name}_single"]:
                if arcpy.Exists(lyr):
                    arcpy.management.Delete(lyr)

    except Exception as e:
        tb = traceback.format_exc()
        error_message = f"Split explode line error: {e}\nTraceback details:\n{tb}"
        arcpy.AddError(error_message)


def create_carto_partition(fc_list, feature_loc, feature_count):
    try:
        if arcpy.Exists(f"{feature_loc}\\CartoPartitionA"):
            arcpy.management.Delete(f"{feature_loc}\\CartoPartitionA")
        arcpy.cartography.CreateCartographicPartitions(fc_list, f"{feature_loc}\\CartoPartitionA", feature_count, 'Features')

    except Exception as e:
        tb = traceback.format_exc()
        error_message = f"Create carto partition error: {e}\nTraceback details:\n{tb}"
        arcpy.AddMessage(error_message)

def calc_vst_on_workspace(fc_list, symbology_file_path, apply_symbology_layers_list, map_name, feature_loc):
    try:
        # Define environment variables
        arcpy.env.overwriteOutput = 1
        # add_layers(fc_list, map_name)
        # Get feature list
        apply_symbology_fc_name = list(filter(str.strip, apply_symbology_layers_list))
        apply_symbology_fc_list = [fc for sym_app_lyr in apply_symbology_fc_name for fc in fc_list if str(sym_app_lyr) in fc]
        apply_symbology_fc_list.append(f"{feature_loc}\\AOI")
        # Calculate VST
        aprx = arcpy.mp.ArcGISProject('CURRENT')
        maps = aprx.listMaps(map_name)[0]
        lyrx = [os.path.basename(k)[:-5] for k in glob.glob(os.path.join(symbology_file_path + "\*.lyrx"))]

        for fc in apply_symbology_fc_list:
            fc_name = os.path.basename(fc)
            if fc_name in lyrx:
                layer = maps.addDataFromPath(fc)
                # Run Calc Visual Specification
                symbology_layerx = maps.addDataFromPath(f"{symbology_file_path}\\{fc_name}.lyrx")
                in_symbology = symbology_layerx.symbology
                layer.symbology = in_symbology
                maps.removeLayer(symbology_layerx)

    except Exception as e:
        tb = traceback.format_exc()
        error_message = f"Apply visual specification error: {e}\nTraceback details:\n{tb}"
        arcpy.AddMessage(error_message)

def apply_carto_symbology(fc_list, attribution_fc_list, express_list, query_list, field_list, intersecting_fc_list, working_gdb, query, visible_field, distance, mx_no_close_fcs_l, 
                          mx_no_close_fcs_m, mx_no_close_fcs_u, feature_loc, feature_count, vst_workspace, specification, hierarchy_file, hierarchy_fld_name, prep_line_resolve_fcs_list, 
                          carto_partition, symbology_file_path, map_name, apply_symbology_layers_list, logger):
    arcpy.AddMessage('Starting carto symbolisation application .....')
    # Set the workspace
    arcpy.env.overwriteOutput = True
    try:
        # Apply attribution
        apply_attribution(fc_list, attribution_fc_list, express_list, query_list, field_list)
        # Skip embankments and cuttings
        embankment_cutting(fc_list, intersecting_fc_list, working_gdb)
        # Prep for line resolve
        prep_4_line_resolve(fc_list, query, visible_field, distance, mx_no_close_fcs_l, mx_no_close_fcs_m, mx_no_close_fcs_u, prep_line_resolve_fcs_list, working_gdb)
        # Start Additional 100k
        # Split and Explode lines
        split_explode_lines_100k(fc_list, apply_symbology_layers_list, working_gdb)
        # End additional 100k
        # Create carto partition
        create_carto_partition(fc_list, feature_loc, feature_count)
        # Calculate VST on workspace
        calc_vst_on_workspace(fc_list, symbology_file_path, apply_symbology_layers_list, map_name, feature_loc)
        # Populate hierarchy
        populate_hierarchy(hierarchy_file, feature_loc, hierarchy_fld_name, working_gdb)
    except Exception as e:
        exc_type, exc_value, exc_traceback = sys.exc_info()
        tb = traceback.format_exc()
        error_message = f"Apply carto symbology error: {e}\nTraceback details:\n{tb}"
        logger.error(error_message)
        simplified_msgs('Apply carto symbology', f'{exc_value}\n')