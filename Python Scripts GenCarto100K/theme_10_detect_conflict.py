import arcpy
import traceback
import sys
from common_utils import *

def detect_write_conflicts(in_feature_loc, inputFCs, query, compareFCs,
                           conflictDistance, rev_workspace, rev_session, severity,
                           ref_scale, partitions, map_name, symbology_file_path, logger):
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

    USE_NO_OUTLINE = 'ALL'
    try:
        inLayers = []
        compareLayers = []
        comparison = {}

        arcpy.CheckOutExtension("datareviewer")

        total_conflict = 0

        # Set the reference scale and partitions
        arcpy.env.referenceScale = ref_scale
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
            dist = conflictDistance
            if dist == '0':
                symbology = "NO_OUTLINE"

        inLayers = prepFcs(inputFCs, in_feature_loc, map_name, symbology_file_path, query, symbology)
        if len(inLayers) >= 1:
            compareLayers = prepFcs(compareFCs, in_feature_loc, map_name, symbology_file_path, query, symbology)
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
                        outfc = arcpy.cartography.DetectGraphicConflict(inlyr, conflict_lyr_ID, outfcname, conflictDistance)
                        arcpy.AddMessage(arcpy.GetMessages())

                        # Repair and count (match original)
                        arcpy.management.RepairGeometry(outfc)
                        
                        number_conflict = int(arcpy.management.GetCount(outfc)[0])
                        arcpy.AddMessage(str(number_conflict) + " conflicts were found.")

                        if number_conflict >= 1:
                            error_count = write2Rev(outfc, rev_workspace, rev_session, str(severity))
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
        logger.error(error_message)
        simplified_msgs('Detect conflict', f'{e}\n')