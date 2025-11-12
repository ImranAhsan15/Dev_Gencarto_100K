import arcpy
import traceback
import sys
from common_utils import *

def has_features(fc):
    with arcpy.da.SearchCursor(fc, ['OID@']) as cursor:
        return next(cursor, None) is not None

def convert_small_bldg_2_point(fc_list, small_bldg_2_point_a, small_bldg_2_point_p, min_size_bldg, delete_input, one_point, unique_field, working_gdb):
    try:
        small_bldg_2_point_a = list(filter(str.strip, small_bldg_2_point_a))
        small_bldg_2_point_a = [fc for a_lyr in small_bldg_2_point_a for fc in fc_list if str(a_lyr) in fc]
        small_bldg_2_point_p = list(filter(str.strip, small_bldg_2_point_p))
        small_bldg_2_point_p = [fc for p_lyr in small_bldg_2_point_p for fc in fc_list if str(p_lyr) in fc]

        # Small building to point
        for inFc, point_fc in zip(small_bldg_2_point_a, small_bldg_2_point_p):
            if has_features(inFc):
                one_point = True
                feature2point_bldg(inFc, point_fc, min_size_bldg, delete_input, one_point, unique_field, working_gdb)
    
    except Exception as e:
        tb = traceback.format_exc()
        error_message = f"Convert small building to point error: {e}\nTraceback details:\n{tb}"
        arcpy.AddMessage(error_message)

def delete_features_in_poly(features_in_cemetery, poly_fc, poly_size):
    # Set the workspace
    arcpy.env.overwriteOutput = True
    try:
        desc = arcpy.da.Describe(poly_fc)
        shape_delim = desc['areaFieldName']
        sizeQuery = shape_delim + " <= " + str(poly_size)
        arcpy.AddMessage(f'sizeQuery is: {sizeQuery}')
        for pt_fc in features_in_cemetery:
            if not has_features(pt_fc):
                arcpy.AddMessage(f"Skipping {pt_fc} as it has no features") #new continue block added to avoid operation on empty feature classes 
                continue
            # Make Feature Layers for input point and polygon
            if "BA0010_Residential_Building_A" in pt_fc or "BC0010_Industrial_Building_A" in pt_fc or "BE0010_Educational_Building_A" in pt_fc:
                pt_lyr = arcpy.management.MakeFeatureLayer(pt_fc, "point_lyr")
            elif "BA0010_Residential_Building_P" in pt_fc or "BC0010_Industrial_Building_P" in pt_fc or "BE0010_Educational_Building_P" in pt_fc:
                pt_lyr = arcpy.management.MakeFeatureLayer(pt_fc, "point_lyr")
            else:
                pt_lyr = arcpy.management.MakeFeatureLayer(pt_fc, "point_lyr")

            point_count = int(arcpy.management.GetCount("point_lyr").getOutput(0))
            if point_count >= 1:
                poly_lyr = arcpy.management.MakeFeatureLayer(poly_fc, "polygon_lyr")
                arcpy.management.SelectLayerByAttribute(poly_lyr, "", sizeQuery)

                # Find all features that fall within the selected polygons
                arcpy.management.SelectLayerByLocation(pt_lyr, "INTERSECT", poly_lyr)
                point_count = int(arcpy.management.GetCount("point_lyr").getOutput(0))
                arcpy.AddMessage(str(point_count))
                # Determine if pt_fc is a point or polygon feature class
                desc = arcpy.da.Describe(pt_fc)
                if desc['shapeType'] == 'Polygon':
                    # Optional code to fil holes in cemetery if topology exists between the two
                    point_count = int(arcpy.management.GetCount("point_lyr").getOutput(0))
                    if point_count >= 1:
                        # If features still remain, just delete them
                        arcpy.AddMessage(str(point_count) + " features will be deleted")
                        arcpy.management.DeleteFeatures("point_lyr")

                if desc['shapeType'] == 'Point':
                    # If features are selected, delete them
                    point_count = int(arcpy.management.GetCount("point_lyr").getOutput(0))
                    if point_count >= 1:
                        arcpy.AddMessage(str(point_count) + " features will be deleted")
                        arcpy.management.DeleteFeatures("point_lyr")
                    else:
                        arcpy.AddMessage("No features will be deleted")
                # Delete temp files
                delete_list = ["point_lyr", "polygon_lyr"]
                arcpy.management.Delete(delete_list)
                
    except Exception as e:
        tb = traceback.format_exc()
        error_message = f"Delete features in polygon error: {e}\nTraceback details:\n{tb}"
        arcpy.AddMessage(error_message)

def delete_small_building(fc_list, delete_small_bldgs, del_min_area):
    try:
        delete_small_bldgs = list(filter(str.strip, delete_small_bldgs))
        delete_small_bldgs = [fc for a_lyr in delete_small_bldgs for fc in fc_list if str(a_lyr) in fc]

        for polygon_fc in delete_small_bldgs:
            if has_features(polygon_fc):
                # Create query
                desc = arcpy.da.Describe(polygon_fc)
                fc_name = desc['name']
                shape_area = desc['areaFieldName']
                query = f"{shape_area} <= {del_min_area}"
                features_lyr = arcpy.management.MakeFeatureLayer(polygon_fc, f"{fc_name}_layer", query)
                # Delete features
                arcpy.management.DeleteFeatures(features_lyr)

    except Exception as e:
        tb = traceback.format_exc()
        error_message = f"Delete small building error: {e}\nTraceback details:\n{tb}"
        arcpy.AddMessage(error_message)


def simplify_buildings(polygon_fc, distance, working_gdb):
    # Define environment variables
    arcpy.env.overwriteOutput = 1
    try:
        field = "BLD_STATUS"

        desc = arcpy.da.Describe(polygon_fc)
        fc_name = desc['name']
        oid_field = desc['OIDFieldName']
        simple_fc = working_gdb + "\\"+ fc_name + "_Simple"
        if arcpy.Exists(simple_fc):
            arcpy.management.Delete(simple_fc)

        smooth_fc = working_gdb + "\\"+ fc_name + "_Smooth"
        if arcpy.Exists(smooth_fc):
            arcpy.management.Delete(smooth_fc)

        arcpy.AddMessage("running simplify")
        arcpy.management.AddField(polygon_fc, "BLD_STATUS", "LONG")
        simplify_features = arcpy.management.MakeFeatureLayer(polygon_fc, "simplify_features")

    # Check for feature classes with no features
        # result = arcpy.management.GetCount(simplify_features)
        # count = int(result.getOutput(0))

        if has_features(simplify_features):   #added has_features check instead of count check
            # Run simplify buildings
            arcpy.cartography.SimplifyBuilding(simplify_features, simple_fc, distance)
            field_delimited = arcpy.AddFieldDelimiters(simple_fc, field)
            query = field_delimited + " <> 5"
            simple_lyr = arcpy.management.MakeFeatureLayer(simple_fc, "simple_lyr")
            arcpy.management.SelectLayerByAttribute(simple_lyr, "", query)

            # Replace the original features with simplified geometries
            with arcpy.da.SearchCursor(simple_lyr, ['SHAPE@', 'InBld_FID']) as cursor:
                arcpy.AddMessage("replacing geometries")
                for row in cursor:
                    update_sql = oid_field + " = " + str(row[1])

                    with arcpy.da.UpdateCursor(polygon_fc, ['SHAPE@', 'oid@'], update_sql) as uCursor:
                        for uRow in uCursor:
                            #replace the shape if it is not identical
                            if not uRow[0].equals(row[0]):
                                uRow[0] = row[0]
                                uCursor.updateRow(uRow)
            # Delete temp files 
            arcpy.management.DeleteField(polygon_fc, field)

    except Exception as e:
        tb = traceback.format_exc()
        error_message = f"Simplify buildings error: {e}\nTraceback details:\n{tb}"
        arcpy.AddMessage(error_message)

def delineate_built_up_area(fc_list, in_buildings_list, edge_features_list, grouping_distance, minimum_detail_size, minimum_building_count, in_feature_loc, delineate_ref_scale):
    # Define environment variables
    arcpy.env.overwriteOutput = 1
    arcpy.env.referenceScale = delineate_ref_scale
    try:
        in_buildings_list = list(filter(str.strip, in_buildings_list))
        in_buildings = [fc for a_lyr in in_buildings_list for fc in fc_list if str(a_lyr) in fc]
        edge_features_list = list(filter(str.strip, edge_features_list))
        edge_features = [fc for a_lyr in edge_features_list for fc in fc_list if str(a_lyr) in fc]
        # Town Built Up Fc Layer
        town_buil_up = [fc for fc in fc_list if 'BJ0073_Town_Built_up_A' in fc][0]

        out_feature_class = f"{in_feature_loc}\\town_built_up"
        arcpy.cartography.DelineateBuiltUpAreas(in_buildings, None, edge_features, grouping_distance, minimum_detail_size, out_feature_class, minimum_building_count)
        # Append with town buil up layer
        arcpy.management.Append(out_feature_class, town_buil_up, 'NO_TEST')
    except Exception as e:
        tb = traceback.format_exc()
        error_message = f"Delineate built-up area error: {e}\nTraceback details:\n{tb}"
        arcpy.AddMessage(error_message)

def generalised_buildings(fc_list):
    try:
        # Set the workspace
        arcpy.env.overwriteOutput = True
        local_authoruty_cover = [fc for fc in fc_list if 'DA0220_Local_Authority_Area_A' in fc][0]
        town_buil_up = [fc for fc in fc_list if 'BJ0073_Town_Built_up_A' in fc][0]
        generalised_building = [fc for fc in fc_list if 'BJ0500_Generalised_Buildings_A' in fc][0]
        # Make feature layers
        local_authoruty_cover = arcpy.management.MakeFeatureLayer(local_authoruty_cover, "local_authoruty_cover")
        town_buil_up = arcpy.management.MakeFeatureLayer(town_buil_up, "town_buil_up")
        # Town buil up selection by Local Authority Cover Layer
        arcpy.management.SelectLayerByLocation(town_buil_up, 'INTERSECT', local_authoruty_cover, None, 'NEW_SELECTION')
        arcpy.management.SelectLayerByAttribute(town_buil_up, "SWITCH_SELECTION")
        # Delete features from town built up areas
        arcpy.management.DeleteFeatures(town_buil_up)
        # Append town built up areas with generalised building
        arcpy.management.Append(town_buil_up, generalised_building, 'NO_TEST')

    except Exception as e:
        tb = traceback.format_exc()
        error_message = f"Generalised building error: {e}\nTraceback details:\n{tb}"
        arcpy.AddMessage(error_message)


def gen_buildup(fc_list, small_bldg_2_point_a, small_bldg_2_point_p, min_size_bldg, sql_bldg, delete_input, one_point, unique_field, working_gdb, min_size_bldg2, features_in_cemetery, 
                enlarge_min_size, enlarge_val, enlarge_barrier_fcs, delete_small_bldgs, del_min_area, enlarge_building_features, enlarge_bldg_min_width, enlarge_bldg_min_length, 
                enlarge_bldg_additional_criteria, simpl_bldg_distance, in_buildings_list, edge_features_list, grouping_distance, minimum_detail_size, minimum_building_count, 
                in_feature_loc, delineate_ref_scale, del_small_recreation_fc_min_size, delete_small_features, erase_sql, simplification_tolerance, logger):
    arcpy.AddMessage('Starting buildup features generalization.....')
    # Set the workspace
    arcpy.env.overwriteOutput = True
    try:
        # Convert small building to point
        convert_small_bldg_2_point(fc_list, small_bldg_2_point_a, small_bldg_2_point_p, min_size_bldg, delete_input, one_point, unique_field, working_gdb)
        # Delete buildings in Cemetery
        features_in_cemetery = list(filter(str.strip, features_in_cemetery))
        features_in_cemetery = [fc for a_lyr in features_in_cemetery for fc in fc_list if str(a_lyr) in fc]
        cemetery = [fc for fc in fc_list if 'BH0010_Cemetery_A' in fc][0]
        delete_features_in_poly(features_in_cemetery, cemetery, min_size_bldg2)
        # Enlarge builtup Features (Cemetery)
        enlarge_barrier_fcs = list(filter(str.strip, enlarge_barrier_fcs))
        enlarge_barrier_fcs = [fc for a_lyr in enlarge_barrier_fcs for fc in fc_list if str(a_lyr) in fc]
        enlarge_polygon_barrier(cemetery, None, None, enlarge_min_size, enlarge_val, enlarge_barrier_fcs, working_gdb)
        # Delete small buildings
        delete_small_building(fc_list, delete_small_bldgs, del_min_area)
        # Enlarge small buildings
        enlarge_building_features = list(filter(str.strip, enlarge_building_features))
        enlarge_building_features = [fc for a_lyr in enlarge_building_features for fc in fc_list if str(a_lyr) in fc]
        #extend_polygon_sides(enlarge_building_features, working_gdb, enlarge_bldg_min_width, enlarge_bldg_min_length, enlarge_bldg_additional_criteria, simplification_tolerance)
        # Simplify buildings
        for polygon_fc in enlarge_building_features:
            if has_features(polygon_fc):
                simplify_buildings(polygon_fc, simpl_bldg_distance, working_gdb)
        # Delineaate town built-Up Areas
        delineate_built_up_area(fc_list, in_buildings_list, edge_features_list, grouping_distance, minimum_detail_size, minimum_building_count, in_feature_loc, delineate_ref_scale)
        # Generalised Buildings
        generalised_buildings(fc_list)
        # Delete small features (Swimming)
        recreation = [fc for fc in fc_list if 'BG0040_Swimming_Pool_A' in fc][0] ## edited
        delete_small_features = list(filter(str.strip, delete_small_features))
        delete_small_features = [fc for a_lyr in delete_small_features for fc in fc_list if str(a_lyr) in fc]
        remove_by_converting(recreation, delete_small_features, del_small_recreation_fc_min_size, None, working_gdb)
        # Erase vagetaton
        erase_polygons_by_replace(cemetery, delete_small_features, erase_sql, working_gdb)

    except Exception as e:
        exc_type, exc_value, exc_traceback = sys.exc_info()
        tb = traceback.format_exc()
        error_message = f"Built-Up Area Generalisation error: {e}\nTraceback details:\n{tb}"
        logger.error(error_message)
        simplified_msgs('Built-Up Area Generalisation', f'{exc_value}\n')