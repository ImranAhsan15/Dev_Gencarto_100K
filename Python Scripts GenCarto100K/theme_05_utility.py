import arcpy
import traceback
import sys
from common_utils import *

def lookupSubTypeValue(table, value):
    """
       Given the text description of a subtype value, return
       the code value as an int
    """
    try:
        desc_lu = {key: value['Name'] for (key, value) in arcpy.da.ListSubtypes(table).items()}
        for key in desc_lu.keys():
            if desc_lu[key].lower() == value.lower():
                return key
            del key

    except Exception as e:
        tb = traceback.format_exc()
        error_message = f"Look up subtype field error: {e}\nTraceback details:\n{tb}"
        arcpy.AddMessage(error_message)

def extract_and_replace_by_type(working_gdb, powerlineFC, powerlineBuffer, polygonFCToRemove_, valid, replacePolygonFC):
    """ main driver of program """
    try:
        # Set the workspace
        arcpy.env.workspace = "memory"
        arcpy.env.overwriteOutput = True

        for polygonFCToRemove in polygonFCToRemove_:
            # Delete list
            clean_list = []
            if valid:
                replacePolygonFC = polygonFCToRemove

            #desc = arcpy.Describe(replacePolygonFC)
            #oid_delim = desc['OIDFieldName']

            #   Local Variables
            plBuffer = "plBuffer"
            removeFL = "remove_fl"
            removedGeom = "removed"
            powerLineFL = "powerLineFL"
            polygonFLToRemove = "polygonFLToRemove"

            # Logic
            powerLineFL = arcpy.management.MakeFeatureLayer(powerlineFC, powerLineFL)[0]
            arcpy.management.MakeFeatureLayer(polygonFCToRemove, polygonFLToRemove)[0]
            plBuffer = arcpy.analysis.Buffer(powerLineFL, plBuffer, powerlineBuffer)[0]

            clean_list.append(plBuffer)

            # If the feature under the powerline needs to be replaced
            removeFL = arcpy.management.MakeFeatureLayer(polygonFLToRemove, removeFL)[0]
            arcpy.AddMessage("Determine if features need to be expanded or removed")
            removedGeom2 = arcpy.analysis.Clip(removeFL, plBuffer, removedGeom)[0]

            if has_features(removedGeom2):
                # Add the Clip features to the target feature class
                if valid == "Yes":
                    arcpy.AddMessage("Expanding features")
                    arcpy.management.Append(removedGeom, replacePolygonFC, "NO_TEST")
                else:
                    arcpy.AddMessage("Adding features to " + replacePolygonFC)
                    arcpy.management.Append(removedGeom2, replacePolygonFC, "NO_TEST")
                    arcpy.management.SelectLayerByLocation(removeFL, "INTERSECT", removedGeom2)
                    arcpy.AddMessage("Deleting features from " + polygonFCToRemove)
                    try:
                        with arcpy.da.UpdateCursor(removeFL, ["SHAPE@", "oid@"]) as urows:
                            for urow in urows:
                                geom = urow[0]
                                arcpy.AddMessage("Process " + str(urow[1]))
                                with arcpy.da.SearchCursor(removedGeom, ["SHAPE@"]) as srows:
                                    for srow in srows:
                                        remGeo = srow[0]
                                        geom = geom.difference(remGeo)
                                urow[0] = geom
                                urows.updateRow(urow)
                    finally:
                        del urow
            del plBuffer
            del removeFL
            del removedGeom

            # Delete temp files
            arcpy.management.Delete(clean_list)
            #return replacePolygonFC

    except Exception as e:
        tb = traceback.format_exc()
        error_message = f"Extract and replace by type error: {e}\nTraceback details:\n{tb}"
        arcpy.AddMessage(error_message)

def multipart_to_singlepart(working_gdb, FC, sql):
    # Define environment variables
    arcpy.env.overwriteOutput = 1
    arcpy.env.workspace = "memory"
    try:
        fcName = os.path.basename(FC)
        outFC = f"{working_gdb}" + "\\" + fcName + "_Explode"
        arcpy.management.MakeFeatureLayer(FC, "layer", sql)

        arcpy.AddMessage("Processing " + fcName)

        if has_features(FC):
            # Run feature to Line on feature class
            arcpy.AddMessage ("   ...Running Multipart to Singlepart")
            arcpy.management.MultipartToSinglepart(FC, outFC)
            # Delete features from the input feature class
            arcpy.AddMessage ("   ...Running Delete Features")
            arcpy.management.DeleteFeatures(FC)
            # Add the output of Feature To Line back into the original feature class
            arcpy.AddMessage ("   ...Running Append")
            arcpy.management.Append(outFC, FC, "NO_TEST")
            # Delete temporary output feature class
            if arcpy.Exists(outFC):
                arcpy.management.Delete(outFC)
        else:
            arcpy.AddMessage("Feature class has no features.")
    except Exception as e:
        tb = traceback.format_exc()
        error_message = f"Multipart to singlepart error: {e}\nTraceback details:\n{tb}"
        arcpy.AddMessage(error_message)

def multipart_to_singlepart_(working_gdb, FC, sql):
    # Define environment variables
    arcpy.env.overwriteOutput = 1
    arcpy.env.workspace = working_gdb
    try: 
        desc = arcpy.da.Describe(FC)
        fcName = desc['name']
        outFC = f"{working_gdb}" + "\\" + fcName + "_Explode"
        arcpy.management.MakeFeatureLayer(FC, "layer", sql)
        arcpy.AddMessage("Processing " + fcName)
        # Check for feature classes with no features
        result = arcpy.management.GetCount(FC)
        count = int(result.getOutput(0))

        if count >= 1:
            # Run feature to Line on feature class
            arcpy.AddMessage ("   ...Running Multipart to Singlepart")
            arcpy.management.MultipartToSinglepart(FC, outFC)
            # Delete features from the input feature class
            arcpy.AddMessage ("   ...Running Delete Features")
            arcpy.management.DeleteFeatures(FC)
            # Add the output of Feature To Line back into the original feature class
            arcpy.AddMessage ("   ...Running Append")
            arcpy.management.Append(outFC, FC, "NO_TEST")
            # Delete temporary output feature class
            if arcpy.Exists(outFC):
                arcpy.management.Delete(outFC)
        else:
            arcpy.AddMessage("Feature class has no features.")
    except Exception as e:
        tb = traceback.format_exc()
        error_message = f"Multipart to singlepart error: {e}\nTraceback details:\n{tb}"
        arcpy.AddMessage(error_message)

def feature_to_point(working_db, inFc, sql, min_size, outputFc, deleteInput, onePoint, uniqueField):
    # Set the workspace
    scratch = "memory"
    arcpy.env.overwriteOutput = True
    try:
        # Use Describe object and get Shape Area field
        desc = arcpy.da.Describe(inFc)
        if desc['shapeType'] == 'Polygon':
            size_field  = desc['areaFieldName']
        if desc['shapeType'] == 'Polyline':
            size_field  = desc['lengthFieldName']

        oid_field = desc['OIDFieldName']
        selection_criteria = ''
        if min_size:
            selection_criteria = f"{size_field} < {min_size}"
        if sql:
            if selection_criteria != '':
                selection_criteria = f"{selection_criteria} AND {sql})"
            else:
                selection_criteria = sql
        arcpy.management.MakeFeatureLayer(inFc, "SmallFeatures", selection_criteria)
        
        if has_features("SmallFeatures"):
            if not onePoint:
                # Convert polygon to point
                arcpy.AddMessage( "converting  to point")
                arcpy.management.FeatureToPoint("SmallFeatures", f"{scratch}\\points")
                # Append point with output feature
                arcpy.AddMessage("Adding point to output feature class")
                arcpy.management.Append(f"{scratch}\\points", outputFc, "NO_TEST")
                if arcpy.Exists(f"{scratch}\\points"):
                    arcpy.management.Delete(f"{scratch}\\points")
                # Delete the features in the polygon feature class
                if deleteInput:
                    arcpy.AddMessage( "Deleting features from " + inFc)
                    arcpy.management.DeleteFeatures("SmallFeatures")
                    arcpy.management.Delete("SmallFeatures")
            else:
                convertOIDs = []
                deleteOIDs = []
                arcpy.AddMessage("Determining which feature to convert")
                values = [row[0] for row in arcpy.da.SearchCursor("SmallFeatures", (uniqueField))]
                uniqueValues = set(values)
                uniqueValues.discard("")
                uniqueValues.discard(" ")
                uniqueValues.discard(None)
                for val in uniqueValues:
                    arcpy.AddMessage(val)
                    val = val.replace("'", "''")
                    postfix  = f"ORDER BY {size_field} DESC"
                    whereClause = f"{uniqueField} = '{val}'"
                    arcpy.management.SelectLayerByAttribute("SmallFeatures", "NEW_SELECTION", whereClause)
                    oids = [row[0] for row in arcpy.da.SearchCursor("SmallFeatures", ['OID@', size_field, uniqueField], sql_clause = (None, postfix ) ) ]
                    arcpy.AddMessage("Convert feature oid " + str(oids[0]))
                    convertOIDs.append(oids[0])
                    deleteOIDs.append(oids)
                arcpy.AddMessage("Converting largest features to points")
                convert_layer = arcpy.management.MakeFeatureLayer(inFc, "convert_lyr")
                for oid in convertOIDs:
                    where = oid_field + " = " + str(oid)
                    arcpy.management.SelectLayerByAttribute(convert_layer, "ADD_TO_SELECTION", where)
               
                if has_features(convert_layer):
                    arcpy.management.FeatureToPoint(convert_layer, f"{scratch}\\points")
                    arcpy.AddMessage("Adding point to output feature class")
                    arcpy.management.Append(f"{scratch}\\points", outputFc, "NO_TEST")
                    if arcpy.Exists(f"{scratch}\\points"):
                        arcpy.management.Delete(f"{scratch}\\points")

                arcpy.AddMessage(f"Converting features with no value in {uniqueField}")
                where = f"{uniqueField} IS NULL OR {uniqueField} = ''"
                if sql:
                    where = f"{where} AND ({sql})"
                arcpy.AddMessage(where)
                arcpy.management.SelectLayerByAttribute(convert_layer, "NEW_SELECTION", where)
                if has_features(convert_layer):
                    arcpy.management.FeatureToPoint(convert_layer, f"{scratch}\\points")
                    arcpy.AddMessage("Adding point to output feature class")
                    arcpy.management.Append(f"{scratch}\\points", outputFc, "NO_TEST") #, outputSubtype)
                    if arcpy.Exists(f"{scratch}\\points"):
                        arcpy.management.Delete(f"{scratch}\\points")
                if deleteInput:
                    arcpy.management.SelectLayerByAttribute("SmallFeatures", "CLEAR_SELECTION")
                    arcpy.AddMessage( "deleting features from " + inFc)
                    arcpy.management.DeleteFeatures("SmallFeatures")
                    arcpy.management.Delete("SmallFeatures")
        else:
            arcpy.AddMessage("No features meet criteria to be converted to point.")

        clean_list = ["convert_lyr", f"{scratch}\\points", "SmallFeatures"]
        # Delete temp files
        arcpy.management.Delete(clean_list)

    except Exception as e:
        tb = traceback.format_exc()
        error_message = f"Feature to point error: {e}\nTraceback details:\n{tb}"
        arcpy.AddMessage(error_message)

def detect_small_util(working_gdb, primaryFC, secondaryFCs, minimumArea, additionalCriteria):
    try:
        # Set the workspace
        arcpy.AddMessage(minimumArea)
        arcpy.env.overwriteOutput = True
        arcpy.env.workspace = "memory"
        arcpy.AddMessage("Scratch : " + str(working_gdb))

        # Use Describe object and get Shape Area field
        desc = arcpy.da.Describe(primaryFC)
        area_field  = desc["areaFieldName"]
        
        selectionCriteria = area_field + " < " + str(minimumArea)
        # Add additional optional SQL query
        if additionalCriteria:
            selectionCriteria = selectionCriteria + " AND (" + additionalCriteria + ")"
        arcpy.AddMessage("additionalCriteria: "+selectionCriteria)
        # Make a layer from the feature class
        primaryFCLyr = "primaryFCLyr"
        arcpy.management.MakeFeatureLayer(primaryFC, primaryFCLyr)
        # Now get info for secondary FC
        secondaryFCNames = []
        secondaryFCLyrs = []
        for fc in secondaryFCs:
            # get just the secondary fc name without path
            indx = str(fc).rfind("\\")
            fcName = str(fc)[indx+1:]
            secondaryFCNames.append(fcName)
            # Create layer
            lyrName = fcName + "Lyr"
            arcpy.management.MakeFeatureLayer(fc, lyrName)
            arcpy.management.SelectLayerByLocation(lyrName, "INTERSECT", primaryFCLyr)
            secondaryFCLyrs.append(lyrName)
        # Convert overlapping features
        selectedFeatures = arcpy.management.SelectLayerByAttribute(primaryFCLyr, "NEW_SELECTION", selectionCriteria)
        if  has_features(primaryFCLyr):
            arcpy.AddMessage(str(int(arcpy.management.GetCount(primaryFCLyr)[0])) + " features to be processed by overlap")
             # Select only those secondary features that intersect the primary
            for clearFCLyr in secondaryFCLyrs:
                arcpy.management.SelectLayerByLocation(clearFCLyr, "Intersect", selectedFeatures)
            arcpy.AddMessage(f"Converting overlapping selected features: {arcpy.Describe(selectedFeatures).baseName}")
            ConvertOverlapping(selectedFeatures, secondaryFCLyrs, working_gdb)
        # Convert enclosed features
        # Get features from primary FC that meet Attribyte criteria - new selection
        selectedFeatures = arcpy.management.SelectLayerByAttribute(primaryFCLyr, "NEW_SELECTION", selectionCriteria)
        if  has_features(primaryFCLyr):
            arcpy.AddMessage(str(int(arcpy.management.GetCount(primaryFCLyr)[0])) + " features to be processed by enclosed")
            # Select only those secondary features that intersect the primary
            for clearFCLyr in secondaryFCLyrs:
                arcpy.management.SelectLayerByLocation(clearFCLyr, "Intersect", selectedFeatures)
            ConvertEnclosed(selectedFeatures, secondaryFCLyrs, working_gdb)
        selectedFeatures = arcpy.management.SelectLayerByAttribute(primaryFCLyr, "NEW_SELECTION", selectionCriteria)
        if  has_features(primaryFCLyr):
            arcpy.AddMessage(str(int(arcpy.management.GetCount(primaryFCLyr)[0])) + " features to be processed")
            arcpy.AddMessage("Deleting Features without replacing")
            arcpy.management.DeleteFeatures(primaryFCLyr)
        # Delete temp files
        clean_list = [primaryFCLyr, secondaryFCNames, secondaryFCLyrs]
        arcpy.management.Delete(clean_list)

    except Exception as e:
        tb = traceback.format_exc()
        error_message = f"Remove by converting error: {e}\nTraceback details:\n{tb}"
        arcpy.AddMessage(error_message)

def merge_parallel_powerlines(fc_list, Distance, Distance_shorter, merge_fields, update, working_gdb):
    try:
        powerlineFC = [fc for fc in fc_list if 'UA0010_Powerline_L' in fc][0]
       
        # Add and calculate field
        arcpy.management.AddField(powerlineFC, merge_fields, "SHORT", "", "", 10, "", "NULLABLE", "NON_REQUIRED", "")

        code_block = """def CalcMerge(PLT):
        if PLT is None or PLT == 0:
            return 100
        else:
            return None
    """
        arcpy.management.CalculateField(powerlineFC, merge_fields, "CalcMerge(!PLT!)", "PYTHON3", code_block)
        
        # Merge parallel powerlines
        merge_parallel_roads(powerlineFC, None, merge_fields, Distance_shorter, update, None, working_gdb)
        merge_parallel_roads(powerlineFC, None, merge_fields, Distance,  update, None, working_gdb)
        merge_parallel_roads(powerlineFC, None, merge_fields, Distance, update, None, working_gdb)

    except Exception as e:
        tb = traceback.format_exc()
        error_message = f"Merge parallel powerlines error: {e}\nTraceback details:\n{tb}"
        arcpy.AddMessage(error_message)

def vegetation_under_powerlines(fc_list, utility_compare_features, utility_beffer_dist, working_gdb):
    # Set environment
    arcpy.env.workspace = working_gdb
    arcpy.env.overwriteOutput = True
    #arcpy.AddMessage("Vegetation under powerlines tool started")

    compare_features = list(filter(str.strip, utility_compare_features))
    compare_features = sorted([fc for a_lyr in compare_features for fc in fc_list if str(a_lyr) in fc])
    powerlineFC = [fc for fc in fc_list if 'UA0010_Powerline_L' in fc][0]
    Grass_A = [fc for fc in fc_list if 'VC1110_Grass_A' in fc][0]
    miscFC = [fc for fc in compare_features if os.path.basename(fc).startswith(("VC"))]
    agricultureFC = [fc for fc in compare_features if os.path.basename(fc).startswith(("VA"))]
    forestFC = [fc for fc in compare_features if os.path.basename(fc).startswith(("VB"))]
    argri_selected_fc = [
            "VA1010_Mix_Traditional_Farming_A",
            "VA1020_Cocoa_A",
            "VA1030_Coconut_A",
            "VA1050_Coffee_A",
            "VA1060_Oil_Palm_A",
            "VA1070_Tea_A",
            "VA1290_Rumbia_A",
            "VA9010_Sundry_Tree_A",
            "VA1310_Mixed_Fruit_Crops_A"
            ]  
    misc_selected_fc = [ "VC1010_Bamboo_A","VC1100_Riung_A"]
    misc_selected_incl_fc = [fc for fc in miscFC if os.path.basename(fc) in misc_selected_fc]
    misc_selected_excl_fc = [fc for fc in miscFC if os.path.basename(fc) not in misc_selected_fc]
    agriculture_selected_incl = [fc for fc in agricultureFC if os.path.basename(fc) in argri_selected_fc]
    argri_selected_excl = [fc for fc in agricultureFC if os.path.basename(fc) not in argri_selected_fc]

    try:
        # Replace all forest with grass
        extract_and_replace_by_type(working_gdb, powerlineFC, utility_beffer_dist, forestFC, False, Grass_A)
        # Misc types to replace with grass
        extract_and_replace_by_type(working_gdb, powerlineFC, utility_beffer_dist, misc_selected_incl_fc, False, Grass_A)
        # Misc types to expand
        extract_and_replace_by_type(working_gdb, powerlineFC, utility_beffer_dist, misc_selected_excl_fc, True, None)
        # Agriculture types to replace with grass
        extract_and_replace_by_type(working_gdb, powerlineFC, utility_beffer_dist, agriculture_selected_incl, False, Grass_A)
        # Agriculture types to expand
        extract_and_replace_by_type(working_gdb, powerlineFC, utility_beffer_dist, argri_selected_excl, True, Grass_A)
        # Multipart to singlepart for all feature classes

        for fc in forestFC:
            multipart_to_singlepart(working_gdb, fc, None)
        for fc in miscFC:
            multipart_to_singlepart(working_gdb, fc, None)
        for fc in agricultureFC:
            multipart_to_singlepart(working_gdb, fc, None)

    except Exception as e:
        tb = traceback.format_exc()
        error_message = f"Vegetation under powerlines error: {e}\nTraceback details:\n{tb}"
        arcpy.AddMessage(error_message)

def vegetation_under_powerlines_(fc_list, utility_compare_features, utility_beffer_dist, working_gdb):
    # Set environment
    arcpy.env.workspace = working_gdb
    arcpy.env.overwriteOutput = True
    #arcpy.AddMessage("Vegetation under powerlines tool started")

    compare_features = list(filter(str.strip, utility_compare_features))
    compare_features = sorted([fc for a_lyr in compare_features for fc in fc_list if str(a_lyr) in fc])
    powerlineFC = [fc for fc in fc_list if 'UA0010_Powerline_L' in fc][0]
    Grass_A = [fc for fc in fc_list if 'VC1110_Grass_A' in fc][0]
    miscFC = [fc for fc in compare_features if os.path.basename(fc).startswith(("VC"))]
    agricultureFC = [fc for fc in compare_features if os.path.basename(fc).startswith(("VA"))]
    forestFC = [fc for fc in compare_features if os.path.basename(fc).startswith(("VB"))]
    argri_selected_fc = [
            "VA1010_Mix_Traditional_Farming_A",
            "VA1020_Cocoa_A",
            "VA1030_Coconut_A",
            "VA1050_Coffee_A",
            "VA1060_Oil_Palm_A",
            "VA1070_Tea_A",
            "VA1290_Rumbia_A",
            "VA9010_Sundry_Tree_A",
            "VA1310_Mixed_Fruit_Crops_A"
            ]  
    misc_selected_fc = [ "VC1010_Bamboo_A","VC1100_Riung_A"]
    misc_selected_incl_fc = [fc for fc in miscFC if os.path.basename(fc) in misc_selected_fc]
    misc_selected_excl_fc = [fc for fc in miscFC if os.path.basename(fc) not in misc_selected_fc]
    agriculture_selected_incl = [fc for fc in agricultureFC if os.path.basename(fc) in argri_selected_fc]
    argri_selected_excl = [fc for fc in agricultureFC if os.path.basename(fc) not in argri_selected_fc]

    try:
        # start here of additional lines for 100k from below 100k_VUP
        comp_fc = miscFC+agricultureFC+forestFC
        for fc in comp_fc:
            if has_features(fc):
                arcpy.management.RepairGeometry(in_features=fc, delete_null=True,
                                                           validation_method="ESRI")
        # end here of additional lines for 100k_VUP
        # Replace all forest with grass
        extract_and_replace_by_type(working_gdb, powerlineFC, utility_beffer_dist, forestFC, False, Grass_A)
        # Misc types to replace with grass
        extract_and_replace_by_type(working_gdb, powerlineFC, utility_beffer_dist, misc_selected_incl_fc, False, Grass_A)
        # Misc types to expand
        extract_and_replace_by_type(working_gdb, powerlineFC, utility_beffer_dist, misc_selected_excl_fc, True, None)
        # Agriculture types to replace with grass
        extract_and_replace_by_type(working_gdb, powerlineFC, utility_beffer_dist, agriculture_selected_incl, False, Grass_A)
        # Agriculture types to expand
        extract_and_replace_by_type(working_gdb, powerlineFC, utility_beffer_dist, argri_selected_excl, True, Grass_A)
        # Multipart to singlepart for all feature classes

        for fc in forestFC:
            multipart_to_singlepart(working_gdb, fc, None)
        for fc in miscFC:
            multipart_to_singlepart(working_gdb, fc, None)
        for fc in agricultureFC:
            multipart_to_singlepart(working_gdb, fc, None)
    except Exception as e:
        tb = traceback.format_exc()
        error_message = f"Vegetation under powerlines error: {e}\nTraceback details:\n{tb}"
        arcpy.AddMessage(error_message)

def building_to_point(fc_list, utility_area_features, utility_point_features, working_gdb, utility_min_size, utility_min_size_building, utility_addi_criteria, unique_field, 
                      utility_compare_features, utility_delete_input, utility_create_one_point):
    try:
        # Create fc list
        arcpy.env.workspace = working_gdb
        area_features = list(filter(str.strip, utility_area_features))
        area_features = [fc for a_lyr in area_features for fc in fc_list if str(a_lyr) in fc]
        point_features = list(filter(str.strip, utility_point_features))
        point_features = [fc for a_lyr in point_features for fc in fc_list if str(a_lyr) in fc]
        compare_features = list(filter(str.strip, utility_compare_features))
        compare_features = [fc for a_lyr in compare_features for fc in fc_list if str(a_lyr) in fc]

        for in_fc, output_fc in zip(area_features, point_features):
            if "UA0030_Power_Station_A" in in_fc:
                feature_to_point(working_gdb, in_fc, None, utility_min_size_building, output_fc, utility_delete_input, utility_create_one_point, unique_field)
            else:
                feature_to_point(working_gdb, in_fc, None, utility_min_size, output_fc, utility_delete_input, utility_create_one_point, unique_field)

        # Loop through utility features and delete small ones
        for feature_name in area_features:
            desc = arcpy.da.Describe(feature_name)
            fc_name = desc["name"]
            area_field = desc['areaFieldName']
            detect_small_util(working_gdb, feature_name, compare_features, utility_min_size, utility_addi_criteria)
            if "U_Electrical_Station_A" in area_features:
                fc_lyr = arcpy.management.MakeFeatureLayer(feature_name, f"fc_lyr_{fc_name}", f"{area_field} < {utility_min_size_building}")
            else:
                fc_lyr = arcpy.management.MakeFeatureLayer(feature_name, f"fc_lyr_{fc_name}", f"{area_field} < {utility_min_size}")
            # Delete features    
            arcpy.management.DeleteFeatures(fc_lyr)

    except Exception as e:
        tb = traceback.format_exc()
        error_message = f"Building to point error: {e}\nTraceback details:\n{tb}"
        arcpy.AddMessage(error_message)

def delete_small_util_sewerage(fc_list, working_gdb, utility_compare_features, utility_min_size_sewerage, utility_addi_criteria_sewerage):
    try:
        # Get feature classes
        compare_features = list(filter(str.strip, utility_compare_features))
        secondaryFCs = [fc for a_lyr in compare_features for fc in fc_list if str(a_lyr) in fc]
        primaryFC = [fc for fc in fc_list if 'UF0010_Sewage_Treatment_Plant_A' in fc][0]
        #arcpy.AddMessage(secondaryFCs)
        # Delete small utility
        detect_small_util(working_gdb, primaryFC, secondaryFCs, utility_min_size_sewerage, utility_addi_criteria_sewerage)

    except Exception as e:
        tb = traceback.format_exc()
        error_message = f"Delete small utility sewerage error: {e}\nTraceback details:\n{tb}"
        arcpy.AddMessage(error_message)

def gen_utility(fc_list, utility_area_features, utility_point_features, utility_compare_features, utility_min_size_sewerage, utility_min_size_building, utility_min_size, utility_beffer_dist, 
                utility_dist, utility_dist_shorter, utility_addi_criteria_sewerage, utility_addi_criteria, utility_merge_field, working_gdb, unique_field, update,
                utility_delete_input, utility_create_one_point,logger):
    arcpy.AddMessage('Starting utility features generalization.....')
    arcpy.env.overwriteOutput = True
    try:
        
        # # Merge parallel powerlines
        merge_parallel_powerlines(fc_list, utility_dist, utility_dist_shorter, utility_merge_field, update, working_gdb)
        # # Vegetation under powerlines
        vegetation_under_powerlines(fc_list, utility_compare_features, utility_beffer_dist, working_gdb)
        # # Convert utility buildings to point
        building_to_point(fc_list, utility_area_features, utility_point_features, working_gdb, utility_min_size, utility_min_size_building, utility_addi_criteria, unique_field, utility_compare_features, utility_delete_input, utility_create_one_point)
        # # Delete small utility features
        delete_small_util_sewerage(fc_list, working_gdb, utility_compare_features, utility_min_size_sewerage, utility_addi_criteria_sewerage)

    except Exception as e:
        exc_type, exc_value, exc_traceback = sys.exc_info()
        tb = traceback.format_exc()
        error_message = f"Utility generalisation error: {e}\nTraceback details:\n{tb}"
        logger.error(error_message)
        simplified_msgs('Utility generalisation', f'{exc_value}\n')