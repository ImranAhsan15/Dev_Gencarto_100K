import arcpy
import pandas as pd
import os
import traceback
import sys
from common_utils import *

# # Writing Detection of Conflicts
def detect_write_conflicts(in_feature_loc, inputFCs, compareFCs, rev_workspace, partitions, map_name, symbology_file_path, val_dict, logger, working_gdb):
    
    arcpy.AddMessage('Starting conflicts detection.....')
    # values 'NEVER', 'NO_DISTANCE', 'ALL'
    # this value determines when we use symbology with no outline rather than using
    # representation symbology.  This only works for polygon layers.
    # NEVER - will always try to use represenation symbology
    # NO_DISTANCE - will only set symbology with no ouline when the search distance is 0
    # ALL - will always try to use symbology with no ouline.

    # Define environment variables (match original behavior)
    arcpy.env.overwriteOutput = True
    arcpy.env.addOutputsToMap = False
    arcpy.env.parallelProcessingFactor = "100%"
    arcpy.env.workspace = working_gdb

    USE_NO_OUTLINE = 'ALL'
    try:
        inLayers = []
        compareLayers = []
        comparison = {}

        arcpy.CheckOutExtension("datareviewer")

        total_conflict = 0

        # Set the reference scale and partitions
        arcpy.env.referenceScale = val_dict['Detect_reference_scale']
        arcpy.env.cartographicPartitions = partitions

        # Set spatial reference from first input FC
        fc = inputFCs[0]
        desc = arcpy.da.Describe(fc)
        sr = desc['spatialReference']
        arcpy.env.cartographicCoordinateSystem = sr

        # Decide symbology (match original)
        symbology = ""
        if USE_NO_OUTLINE == "ALL":
            symbology = "NO_OUTLINE"
        elif USE_NO_OUTLINE == "NO_DISTANCE":
            dist = val_dict['Detect_conflict_distance']
            if dist == '0':
                symbology = "NO_OUTLINE"

        inLayers = prepFcs(inputFCs, in_feature_loc, map_name, symbology_file_path, val_dict['Detect_expression'], symbology)
        if len(inLayers) >= 1:
            compareLayers = prepFcs(compareFCs, in_feature_loc, map_name, symbology_file_path, val_dict['Detect_expression'], symbology)
            outfcname = "detectconflict"

            for inlyr in inLayers:
                compareTo = []
                in_name = arcpy.da.Describe(inlyr)['name']

                for conflict_lyr_ID in compareLayers:
                    compared = False

                    # Skip if already compared in opposite order (match original logic)
                    compare_name = arcpy.da.Describe(conflict_lyr_ID)['name']
                    if compare_name in comparison:
                        vals = comparison[compare_name]
                        if in_name in vals:
                            arcpy.AddMessage("Already compared " + str(inlyr) + " to " + str(conflict_lyr_ID) + " skipping...")
                            compared = True

                    if not compared:
                        compareTo.append(str(compare_name))
                        arcpy.AddMessage("Comparing " + str(inlyr) + " to " + str(conflict_lyr_ID))

                        # Run DetectGraphicConflict (original: fixed name in current workspace)
                        outfc = arcpy.cartography.DetectGraphicConflict(inlyr, conflict_lyr_ID, outfcname, val_dict['Detect_conflict_distance'])
                        arcpy.AddMessage(arcpy.GetMessages())

                        # Repair and count (match original)
                        arcpy.management.RepairGeometry(outfc)
                        
                        number_conflict = int(arcpy.management.GetCount(outfc)[0])
                        arcpy.AddMessage(str(number_conflict) + " conflicts were found.")

                        if number_conflict >= 1:
                            error_count = write2Rev(outfc, rev_workspace, val_dict['Detect_reviewer_session'], str(val_dict['Detect_severity']))
                            if(error_count):
                                total_conflict = total_conflict + int(error_count)

                comparison[in_name] = compareTo
                inLayers.remove(inlyr)

        # Check extension back in (match original placement)
        arcpy.CheckInExtension("datareviewer")

        # Delete temp layers (match original)
        for lyr in inLayers:
            if arcpy.Exists(lyr):
                arcpy.management.Delete(lyr)
        for lyr in compareLayers:
            if arcpy.Exists(lyr):
                arcpy.management.Delete(lyr)
        return total_conflict
    
    except Exception as e:
        tb = traceback.format_exc()
        error_message = f"Detect conflict error: {e}\nTraceback details:\n{tb}"
        arcpy.AddError(error_message)
        logger.error(error_message)
        simplified_msgs('Detect conflict', f'{e}\n')


def run_gdb_audit_and_validation(input_gdb, output_gdb_name, excel_file_name):
    """
    Strictly follows ArcPy documentation to audit requirements, evaluate rules,
    and log results to a new GDB and Excel file.
    """
    # Set environment and derived paths
    current_dir = os.getcwd()
    output_gdb_path = os.path.join(current_dir, output_gdb_name)
    excel_full_path = os.path.join(current_dir, excel_file_name)
    
    arcpy.env.workspace = input_gdb
    arcpy.env.overwriteOutput = True

    # 1. Audit and Enable Requirements (GlobalID & Editor Tracking)
    # Using arcpy.da.Walk to find all Feature Classes as per ESRI best practice
    walk = arcpy.da.Walk(input_gdb, datatype="FeatureClass")
    for dirpath, dirnames, filenames in walk:
        for filename in filenames:
            fc_path = os.path.join(dirpath, filename)
            desc = arcpy.Describe(fc_path)
            
            # Check GlobalID
            if not desc.hasGlobalID:
                arcpy.AddWarning(f"Requirement Missing: Adding Global IDs to {filename}")
                arcpy.management.AddGlobalIDs(fc_path)

            # if not desc.attributeRules.isEnabled:
            #     arcpy.AddWarning(f"Requirement Missing: Enabling Attribute Rules to {filename}")
            #     arcpy.management.EnableAttributeRules(fc_path)
            
            # Check Editor Tracking
            if not desc.editorTrackingEnabled:
                arcpy.AddWarning(f"Requirement Missing: Enabling Editor Tracking for {filename}")
                arcpy.management.EnableEditorTracking(
                    fc_path, "created_user", "created_date", 
                    "last_edited_user", "last_edited_date", "ADD_FIELDS", "UTC"
                )

    # 2. Evaluate Validation Rules
    # This tool populates the GDB system error tables
    arcpy.AddMessage("Executing EvaluateRules_management...")
    arcpy.management.EvaluateRules(input_gdb, "VALIDATION_RULES", None, "ASYNC")

    # 3. Create Output Geodatabase
    if not arcpy.Exists(output_gdb_path):
        arcpy.AddMessage(f"Creating output GDB: {output_gdb_name}")
        arcpy.management.CreateFileGDB(current_dir, output_gdb_name)

    # 4. Process System Error Tables
    # Standard naming convention for Validation Error layers in a GDB
    error_tables = [
        "GDB_ValidationPointErrors", 
        "GDB_ValidationLineErrors", 
        "GDB_ValidationPolyErrors", 
        "GDB_ValidationObjectErrors"
    ]

    # Initialize Excel Writer using Pandas
    with pd.ExcelWriter(excel_full_path, engine='openpyxl') as writer:
        found_any_errors = False
        
        for table_name in error_tables:
            source_table = os.path.join(input_gdb, table_name)
            
            if arcpy.Exists(source_table):
                # A. Copy Feature Class/Table to new GDB
                target_table = os.path.join(output_gdb_path, table_name)
                arcpy.management.Copy(source_table, target_table)
                
                # B. Read data for Excel using SearchCursor
                fields = [f.name for f in arcpy.ListFields(source_table) if f.type != 'Geometry']
                data = []
                with arcpy.da.SearchCursor(source_table, fields) as cursor:
                    for row in cursor:
                        data.append(row)
                
                if data:
                    df = pd.DataFrame(data, columns=fields)
                    df.to_excel(writer, sheet_name=table_name[:31], index=False)
                    found_any_errors = True
                else:
                    # Create empty sheet with headers if no rows exist
                    pd.DataFrame(columns=fields).to_excel(writer, sheet_name=table_name[:31], index=False)
            else:
                arcpy.AddMessage(f"System table {table_name} not found. Ensure validation is enabled.")

    arcpy.AddMessage(f"Process Complete.\nGeodatabase: {output_gdb_path}\nExcel Log: {excel_full_path}")

