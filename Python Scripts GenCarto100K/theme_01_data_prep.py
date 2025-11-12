import arcpy
import traceback
import sys
from common_utils import *

def contour_clean_up(aoi, feature_list, working_gdb, buffer_distance, vertex_limit, logger):
    arcpy.AddMessage('Contour cleaning.....')
    # Set environment variables
    arcpy.env.overwriteOutput = True
    try:
        # Get contour feature
        contour_fcs = [contour for contour in feature_list if 'RA0010_Contour_Line_L' in contour][0]
        base_name = arcpy.da.Describe(contour_fcs)['name']
        # Creating buffer fc
        buffer_fc = f'{working_gdb}\\aoi_buffer'
        arcpy.analysis.Buffer(aoi, buffer_fc, f"{buffer_distance} Meters")
        # Clipped features using buffer
        clip_fc = f'{working_gdb}\\{base_name}_clip'
        arcpy.analysis.Clip(contour_fcs, buffer_fc, clip_fc)
        # Dicing features using dice gp tool
        dice_fc = f'{working_gdb}\\{base_name}_dice'
        arcpy.management.Dice(clip_fc, dice_fc, vertex_limit)
        # Delete features before append
        arcpy.management.DeleteFeatures(contour_fcs)
        # Append clipped features with input features
        arcpy.management.Append(dice_fc, contour_fcs, 'NO_TEST')
        # Delete temporary files
        arcpy.management.Delete([buffer_fc, clip_fc, dice_fc])

    except Exception as e:
        exc_type, exc_value, exc_traceback = sys.exc_info()
        tb = traceback.format_exc()
        error_message = f"Contour clean up error: {e}\nTraceback details:\n{tb}"
        logger.error(error_message)
        simplified_msgs('Contour clean up', f'{exc_value}\n') 

def split_fcs(aoi, fc_list, buffer_distance, working_gdb, feature_to_split, logger):
    arcpy.AddMessage('Splitting multiple features based on AOI.....')
    # Set environment variables
    arcpy.env.overwriteOutput = True
    arcpy.env.workspace = "memory"

    try:
        # Remove empty string
        feature_to_split_list = list(filter(str.strip, feature_to_split))
        feature_to_split_list = [fc for a_lyr in feature_to_split_list for fc in fc_list if str(a_lyr) in fc and has_features(fc) and not 'RA0010_Contour_Line_L' in fc]
        if not feature_to_split_list:
            arcpy.AddMessage('.....No features to process.')
            return
        update_list = []
        # Creating buffer fc
        buffer_fc = f'{working_gdb}\\aoi_buffer'
        arcpy.analysis.Buffer(aoi, buffer_fc, f"{buffer_distance} Meters")

        for fc_path in feature_to_split_list:
            fc_name = os.path.basename(fc_path)        
            arcpy.AddMessage(f'Processing {fc_name}')
            update_list.append(fc_name)
            clip_fc = f'{working_gdb}\\{fc_name}_clip'
            # Clip features
            arcpy.AddMessage('  ...Clipping feature class to buffer')
            arcpy.analysis.Clip(fc_path, buffer_fc, clip_fc)
            # Delete features before append
            arcpy.management.DeleteFeatures(fc_path)
            # Append clipped features with input features
            arcpy.management.Append(clip_fc, fc_path, 'NO_TEST')
            # Delete temporary files
            arcpy.management.Delete([clip_fc])

        if len(update_list) >= 1:
            table = arcpy.management.CreateTable(working_gdb, 'split_features')
            arcpy.management.AddField(table, 'feature_classes', 'TEXT', field_length = 100)
            # Insert feature classes
            cursor = arcpy.da.InsertCursor(table, ['feature_classes'])

            for fc_class in update_list:
                cursor.insertRow([fc_class])
            del cursor  

        # Delete temporary files
        arcpy.management.Delete([buffer_fc])
    except Exception as e:
        exc_type, exc_value, exc_traceback = sys.exc_info()
        tb = traceback.format_exc()
        error_message = f'Split feature classes error: {e}\nTraceback details:\n{tb}'
        logger.error(error_message)
        simplified_msgs('Split feature classes', f'{exc_value}\n')

def clean_data(aoi_fc, fcs, working_gdb, not_include_fields, clean_fc_name, extend_val, trim_val, logger):
    arcpy.AddMessage("Data cleaning started.....")
    try:
        # Set environment and variables
        arcpy.env.overwriteOutput = True
        arcpy.env.workspace = "memory"
        aoi_name = os.path.basename(aoi_fc)
        clean_list = []
        # Select only line or polygon feature classes (ending with _L or _A, not AOI AND at least one feature)
        fcs = [fc for fc in fcs if  (fc.endswith('_L') or fc.endswith('_A')) and 'AOI' not in os.path.basename(fc) and has_features(fc)]
        # Get AOI feature class name 
        if not has_features(aoi_fc):
            arcpy.AddError(aoi_name + " should contain one and only one feature")
        else:
            arcpy.management.MakeFeatureLayer(aoi_fc, "aoi_layer")
        #  Processing with Line and Polygon Feature Classes
        for fc_path in fcs:
                fc_name = os.path.basename(fc_path)
                proc_fc = fc_path
                # Integrating line features
                arcpy.management.Integrate([[proc_fc, 1]])
                # Reparing geometry
                has_issues, issues = is_repair_needed(proc_fc)
                if has_issues:
                    arcpy.AddMessage(f"{proc_fc} has {len(issues)} geometry problems:")
                    for fid, problem in issues:
                        arcpy.AddMessage(f"  - FID {fid}: {problem}")
                    arcpy.management.RepairGeometry(proc_fc)

                if fc_path.endswith('_L'):
                    if fc_name in clean_fc_name:
                        # Data trimming and extending
                        arcpy.edit.ExtendLine(proc_fc, f'{extend_val} Meters', 'EXTENSION')
                        arcpy.edit.TrimLine(proc_fc, f'{trim_val} Meters', 'DELETE_SHORT')
                        # Create unsplit lines
                        fields = get_fields(proc_fc, not_include_fields, logger)
                        proc_fc = arcpy.management.UnsplitLine(proc_fc, f'temp_unsplit_{fc_name}', fields)
                        # Data append for next deleting
                        clean_list.append(f'temp_unsplit_{fc_name}')
                        # Reparing geometry
                        arcpy.management.RepairGeometry(proc_fc)

                    out_fc = f'{working_gdb}\\{fc_name}_temp'
                    # Feature to line conversion
                    proc_fc = arcpy.management.FeatureToLine(proc_fc, out_fc)
                    # Data append for next deleting
                    clean_list.append(out_fc)

                    # Split features at the boundary of the AOI
                    arcpy.management.MakeFeatureLayer(proc_fc, 'fc_layer')
                    arcpy.management.SelectLayerByLocation('fc_layer', 'CROSSED_BY_THE_OUTLINE_OF', 'aoi_layer', None, 'NEW_SELECTION')
                    if has_features('fc_layer'):
                        out_fc = f'{working_gdb}\\{fc_name}_temp1'
                        # Identity features
                        arcpy.analysis.Identity('fc_layer', 'aoi_layer', out_fc, 'ONLY_FID')
                        # Data append for next deleting
                        clean_list.append(out_fc)
                        # Delete existing features
                        arcpy.management.DeleteFeatures('fc_layer')
                        # Append features with base fc
                        arcpy.management.Append(out_fc, proc_fc, 'NO_TEST')
                        # Reparing geometry
                        arcpy.management.RepairGeometry(proc_fc)

                if fc_path.endswith('_A') or fc_path.endswith('_L'):
                    out_fc = f'{working_gdb}\\{fc_name}_ms'
                    # Multipart to single part
                    proc_fc = arcpy.management.MultipartToSinglepart(proc_fc, out_fc)
                    # Data append for next deleting
                    clean_list.append(out_fc)

                if proc_fc != fc_path:
                    # Delete features and append features
                    arcpy.management.DeleteFeatures(fc_path)
                    arcpy.management.Append(proc_fc, fc_path, 'NO_TEST')
                has_fcpth_issues, fcpathissues = is_repair_needed(fc_path)
                if has_fcpth_issues:
                    arcpy.AddMessage(f"{fc_path} has {len(fcpathissues)} geometry problems:")
                    for fid, problem in fcpathissues:
                        arcpy.AddMessage(f"  - FID {fid}: {problem}")
                    arcpy.management.RepairGeometry(fc_path, 'DELETE_NULL')
                # Delete temp files
                arcpy.management.Delete(clean_list)
    except Exception as e:
        exc_type, exc_value, exc_traceback = sys.exc_info()
        tb = traceback.format_exc()
        error_message = f"Clean data lines error: {e}\nTraceback details:\n{tb}"
        logger.error(error_message)
        simplified_msgs('Clean data lines', f'{exc_value}\n')

def cal_orient_degree(point_fc_list, fc_4_orient_deg, logger):
    arcpy.AddMessage('New field Orientation degree adding.....')
    # Set environment
    arcpy.env.overwriteOutput = True
    try:
        # Selected point featureclass to create orient degree
        fc_4_orient_deg = list(filter(str.strip, fc_4_orient_deg))
        point_fcs = [fc for item in fc_4_orient_deg for fc in point_fc_list if str(item) in fc]

        for fc in point_fcs:
            if 'HD0040_Jetty_Pier_P' in fc:
                # Add Field
                arcpy.management.AddField(in_table=fc, field_name='orientation_degree', field_type='DOUBLE')
                # Calculate Field
                arcpy.management.CalculateField(in_table=fc, field='orientation_degree', expression='!orientation_degree!*180 /3.141592654', expression_type='PYTHON3')
            elif 'TA0180_Kilometer_Post_P' in fc or 'ZA0050_Height_Point_P' in fc:
                # Add Field
                arcpy.management.AddField(in_table=fc, field_name='orientation_degree', field_type='DOUBLE')
                arcpy.management.AddField(in_table=fc, field_name='OFFSETX', field_type='DOUBLE')
                arcpy.management.AddField(in_table=fc, field_name='OFFSETY', field_type='DOUBLE')
                # Calculate Field
                arcpy.management.CalculateField(in_table=fc, field='orientation_degree', expression='!orientation!*180 /3.141592654', expression_type='PYTHON3')

            else:
                # Add Field
                arcpy.management.AddField(in_table=fc, field_name='orientation_degree', field_type='DOUBLE')
                # Calculate Field
                arcpy.management.CalculateField(in_table=fc, field='orientation_degree', expression='!orientation!*180 /3.141592654', expression_type='PYTHON3')

    except Exception as e:
        exc_type, exc_value, exc_traceback = sys.exc_info()
        tb = traceback.format_exc()
        error_message = f"Cal orient degree error: {e}\nTraceback details:\n{tb}"
        logger.error(error_message)
        simplified_msgs('Cal orient degree', f'{exc_value}\n')

def create_buffer_25k(working_gdb, buffer_distance_point, fc_list, buffer_points_25k, logger):
    arcpy.AddMessage('Buffer zone creation from given point fc input.....')
    # Set environment
    arcpy.env.overwriteOutput = True
    try:
        # Remove empty string
        buffer_points_25k = list(filter(str.strip, buffer_points_25k))
        new_point_fc_list = [fc for item in buffer_points_25k for fc in fc_list if str(item) in fc]
        # Buffer // Create buffer for each point feature class // modified by Perver.N
        for buffer_fc in new_point_fc_list:
            fc_name = os.path.basename(buffer_fc)
            out_fc = f"{working_gdb}\\{fc_name}_buffer"
            arcpy.analysis.PairwiseBuffer(in_features=buffer_fc, out_feature_class=out_fc, buffer_distance_or_field=f"{buffer_distance_point} Meters")
                    
    except Exception as e:
        exc_type, exc_value, exc_traceback = sys.exc_info()
        arcpy.AddMessage(f'Buffer points for 25k error: \n{exc_value}')
        tb = traceback.format_exc()
        error_message = f"Buffer points for 25k error: {e}\nTraceback details:\n{tb}"
        logger.error(error_message)
        simplified_msgs('Buffer points for 25k', f'{exc_value}\n')


def add_identifier_BUA(fc_list, bau_field_fc, logger):
    arcpy.AddMessage('New field Identifier_BUA adding.....') 
    # Set environment
    arcpy.env.overwriteOutput = True
    try:
        # Get feature class list for BAU field creation
        bau_field_fc_list = list(filter(str.strip, bau_field_fc))
        bau_field_fc_list = [fc for a_lyr in bau_field_fc_list for fc in fc_list if str(a_lyr) in fc]

        for fc_item in bau_field_fc_list:
            # Add Identifier BUA Field
            arcpy.management.AddField(in_table=fc_item, field_name='Identifier_BUA', field_type='SHORT')

    except Exception as e:
        exc_type, exc_value, exc_traceback = sys.exc_info()
        tb = traceback.format_exc()
        error_message = f"Add identifier BUA field error: {e}\nTraceback details:\n{tb}"
        logger.error(error_message)
        simplified_msgs('Add identifier BUA field', f'{exc_value}\n')

def add_invisibility_hierarchy_field(fc_list, logger):
    arcpy.AddMessage('New fields INVISIBILITY and HIERARCHY adding.....')   
    arcpy.env.overwriteOutput = True
    try:
        for fc_item in fc_list:
            # Add Invisibility and Hierarchy Field
            arcpy.management.AddField(in_table=fc_item, field_name='INVISIBILITY', field_type='SHORT')
            arcpy.management.AddField(in_table=fc_item, field_name='HIERARCHY', field_type='SHORT')
    except Exception as e:
        exc_type, exc_value, exc_traceback = sys.exc_info()
        tb = traceback.format_exc()
        error_message = f"Add invisibility hierarchy field error: {e}\nTraceback details:\n{tb}"
        logger.error(error_message)
        simplified_msgs('Add invisibility hierarchy field', f'{exc_value}\n')

def create_partition(in_feature_loc, feature_count, fc_list, logger):
    arcpy.AddMessage('Creating partition layer.....')   
    # Set environment
    arcpy.env.overwriteOutput = True
    arcpy.env.parallelProcessingFactor = "100%"
    
    try:
        out_features = f'{in_feature_loc}\\CartoPartitionA'
        if arcpy.Exists(out_features):
            arcpy.management.Delete([out_features])
        # Create Carto Partition
        arcpy.cartography.CreateCartographicPartitions(fc_list, out_features, feature_count, "FEATURES")

    except Exception as e:
        exc_type, exc_value, exc_traceback = sys.exc_info()
        tb = traceback.format_exc()
        error_message = f"Create partition error: {e}\nTraceback details:\n{tb}"
        logger.error(error_message)
        simplified_msgs('Create partition', f'{exc_value}\n')

def data_cleaning_all_funcs(aoi, fc_list, in_feature_loc, working_gdb, buffer_distance, vertex_limit, buffer_distance_point, feature_count, not_include_fields, 
                            fcs_trim_extend, extend_val, trim_val, buffer_points_25K, feature_to_split, bau_field_fc,logger):
    arcpy.AddMessage('Starting Data cleaning process.....')
    # Set environment variables
    arcpy.env.overwriteOutput = True
    try:
        # Split contour features
        contour_clean_up(aoi, fc_list, working_gdb, buffer_distance, vertex_limit, logger)
        # Split feature classes
        split_fcs(aoi, fc_list, buffer_distance, working_gdb, feature_to_split, logger)
        # Clean data
        clean_data(aoi, fc_list, working_gdb, not_include_fields, fcs_trim_extend, extend_val, trim_val, logger)
        # Create buffer
        create_buffer_25k(working_gdb, buffer_distance_point, fc_list, buffer_points_25K, logger)
        # # Add Identifier BUA Field
        # add_identifier_BUA(fc_list, bau_field_fc, logger)
        # # Add Invisibility and Hierarchy Field
        # add_invisibility_hierarchy_field(fc_list, logger)
        # Create Carto Partition
        create_partition(in_feature_loc, feature_count, fc_list, logger)
        # Polygon to line conversion for boundary
        aoi = f"{in_feature_loc}\\AOI"
        arcpy.management.PolygonToLine(aoi, f"{in_feature_loc}\\AOI_L", "IDENTIFY_NEIGHBORS")

    except Exception as e:
        exc_type, exc_value, exc_traceback = sys.exc_info()
        tb = traceback.format_exc()
        error_message = f"Data cleaning for all funcs error: {e}\nTraceback details:\n{tb}"
        logger.error(error_message)
        simplified_msgs('Data cleaning for all funcs', f'{exc_value}\n')