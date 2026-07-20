import arcpy
import traceback
import sys
import os
import datetime as _dt
from common_utils import *

def area_based_delete(path, townbuiltup_min_area):
    sql_query = f"Shape_Area < {townbuiltup_min_area}"
    arcpy.AddMessage(f"{sql_query}") 
    selected_temp_dis_layer = arcpy.management.SelectLayerByAttribute(path,"NEW_SELECTION",sql_query)
    arcpy.AddMessage(f"Features count before processing: {count_features(path)}")
    if int(arcpy.management.GetCount(selected_temp_dis_layer)[0]) > 0:
        arcpy.management.DeleteFeatures(selected_temp_dis_layer)
        arcpy.AddMessage(f"Features count after processing: {count_features(path)}")

def delete_if_exists(path):
    if arcpy.Exists(path):
        arcpy.management.Delete(path)
# =========================================================
# STEP 3 — FEATURE ENGINEERING
# =========================================================
def run_feature_engineering(
        input_polygons,
        input_points,
        output_polygons,
        temp_polygons,
        temp_point_join,
        temp_poly_neighbor,
        temp_point_hull,
        poly_id_field,
        cluster_type_field,
        pt_density_field,
        pt_hull_ratio_field,
        pt_dispersion_field,
        pt_centroid_dist_field,
        vertex_count_field,
        hole_count_field,
        regularity_field,
        elongation_field,
        convexity_field,
        nbr_avg_area_field,
        nbr_avg_elongation_field,
        nbr_avg_convexity_field,
        nbr_avg_vertices_field,
        nbr_area_ratio_field,
        nbr_dominant_shape_field,
        cluster_type_no_points,
        cluster_type_single_point,
        cluster_type_two_points,
        cluster_type_all_noise,
        cluster_type_single_cluster,
        cluster_type_multi_cluster,
        shape_label_encoding
):
    
    # =========================================================
    # Feature Engineering Block Starts
    # =========================================================

    # =========================================================
    # Helper Functions
    # =========================================================


    def ensure_field(fc, field_name, field_type="LONG"):
        existing = [f.name.upper() for f in arcpy.ListFields(fc)]
        if field_name.upper() not in existing:
            arcpy.management.AddField(fc, field_name, field_type)


    def field_exists(fc, field_name):
        return field_name.lower() in [f.name.lower() for f in arcpy.ListFields(fc)]


    def safe_mean(values):
        vals = [v for v in values if v is not None]
        return round(sum(vals) / len(vals), 6) if vals else None


    def fmt(val, width):
        s = str(val) if val is not None else "None"
        return s.ljust(width)


    # =========================================================
    # GEOMETRY METRIC FUNCTIONS
    # =========================================================
    def count_vertices(geometry):
        if geometry is None:
            return 0
        count = 0
        for part in geometry:
            for pt in part:
                if pt is not None:
                    count += 1
        return count


    def count_holes(geometry):
        if geometry is None:
            return 0
        holes = 0
        for part in geometry:
            in_hole = False
            for pt in part:
                if pt is None:
                    in_hole = True
            if in_hole:
                holes += 1
        return holes


    def polsby_popper(area, perimeter):
        if not perimeter:
            return 0.0
        return round((4 * math.pi * area) / (perimeter ** 2), 6)


    def elongation_ratio(geometry):
        if geometry is None:
            return None
        ext = geometry.extent
        if not ext.width or not ext.height:
            return None
        return round(max(ext.width, ext.height) / min(ext.width, ext.height), 6)


    def convexity_index(area, hull_area):
        if not hull_area:
            return None
        return round(area / hull_area, 6)


    def classify_shape(pp_score):
        if pp_score is None:
            return "none"
        if pp_score >= 0.70:
            return "circular"
        if pp_score >= 0.40:
            return "compact"
        if pp_score >= 0.20:
            return "elongated"
        return "irregular"


    def compute_geometry_metrics(geom, area, perimeter,
                                vertex_count_field,
                                hole_count_field,
                                regularity_field,
                                elongation_field,
                                convexity_field):
        pp = polsby_popper(area, perimeter)
        hull_area = None

        if geom is not None:
            try:
                hull = geom.convexHull()
                hull_area = hull.area if hull else None
            except Exception:
                hull_area = None

        return {
            vertex_count_field: count_vertices(geom),
            hole_count_field: count_holes(geom),
            regularity_field: pp,
            elongation_field: elongation_ratio(geom),
            convexity_field: convexity_index(area, hull_area),
            "area": area,
            "perimeter": perimeter,
            "shape_class": classify_shape(pp),
        }


    # =========================================================
    # DBSCAN
    # =========================================================
    def dbscan_points(points_xy, eps=None, min_samples=2):
        n = len(points_xy)
        if n == 0:
            return []
        if n == 1:
            return [-1]

        if eps is None:
            nn_dists = []
            for i in range(n):
                best = float("inf")
                for j in range(n):
                    if i == j:
                        continue
                    dx = points_xy[i][0] - points_xy[j][0]
                    dy = points_xy[i][1] - points_xy[j][1]
                    d = math.sqrt(dx * dx + dy * dy)
                    if d < best:
                        best = d
                nn_dists.append(best)
            nn_dists.sort()
            eps = nn_dists[len(nn_dists) // 2] * 2.0

        def region_query(idx):
            xi, yi = points_xy[idx]
            return [
                j for j in range(n)
                if math.sqrt(
                    (xi - points_xy[j][0]) ** 2 +
                    (yi - points_xy[j][1]) ** 2
                ) <= eps
            ]

        labels = [-1] * n
        cluster_id = 0

        for i in range(n):
            if labels[i] != -1:
                continue

            neighbours = region_query(i)
            if len(neighbours) < min_samples:
                continue

            labels[i] = cluster_id
            seed_set = set(neighbours) - {i}

            while seed_set:
                j = seed_set.pop()
                if labels[j] == -1:
                    labels[j] = cluster_id
                if labels[j] != -1 and labels[j] != cluster_id:
                    continue
                if labels[j] == cluster_id:
                    continue
                labels[j] = cluster_id
                j_neighbours = region_query(j)
                if len(j_neighbours) >= min_samples:
                    seed_set.update(j_neighbours)

            cluster_id += 1

        return labels


    def encode_cluster_type(point_count, points_xy,
                            cluster_type_no_points,
                            cluster_type_single_point,
                            cluster_type_two_points,
                            cluster_type_all_noise,
                            cluster_type_single_cluster,
                            cluster_type_multi_cluster):
        if point_count == 0 or not points_xy:
            return cluster_type_no_points
        if point_count == 1:
            return cluster_type_single_point
        if point_count == 2:
            return cluster_type_two_points

        labels = dbscan_points(points_xy)
        cluster_ids = {lb for lb in labels if lb >= 0}

        if len(cluster_ids) == 0:
            return cluster_type_all_noise
        if len(cluster_ids) == 1:
            return cluster_type_single_cluster
        return cluster_type_multi_cluster


    # =========================================================
    # POINT DISTRIBUTION METRICS
    # =========================================================
    def compute_point_distribution(points_xy, poly_area, poly_geom, temp_polygons,
                                pt_density_field,
                                pt_hull_ratio_field,
                                pt_dispersion_field,
                                pt_centroid_dist_field):
        n = len(points_xy)

        if n == 0:
            return {
                pt_density_field: 0.0,
                pt_hull_ratio_field: 0.0,
                pt_dispersion_field: None,
                pt_centroid_dist_field: None,
            }

        density = round((n / poly_area) * 1_000_000, 6) if poly_area else None

        pt_array = arcpy.Array([arcpy.Point(x, y) for x, y in points_xy])
        multipoint = arcpy.Multipoint(
            pt_array,
            arcpy.Describe(temp_polygons).spatialReference
        )

        hull_ratio = None

        if n >= 3:
            try:
                pt_hull = multipoint.convexHull()
                hull_area = pt_hull.area if pt_hull else None
                if hull_area is not None and poly_area:
                    hull_ratio = round(min(hull_area / poly_area, 1.0), 6)
            except Exception:
                pass
        elif n == 2:
            hull_ratio = 0.0

        dispersion = None
        if n >= 2:
            nn_dists = []
            for i, (xi, yi) in enumerate(points_xy):
                best = float("inf")
                for j, (xj, yj) in enumerate(points_xy):
                    if i == j:
                        continue
                    d = math.sqrt((xi - xj) ** 2 + (yi - yj) ** 2)
                    if d < best:
                        best = d
                nn_dists.append(best)
            dispersion = round(sum(nn_dists) / len(nn_dists), 4)

        centroid_dist = None
        if poly_geom is not None:
            try:
                poly_cx = poly_geom.centroid.X
                poly_cy = poly_geom.centroid.Y
                cloud_cx = sum(x for x, y in points_xy) / n
                cloud_cy = sum(y for x, y in points_xy) / n
                centroid_dist = round(
                    math.sqrt((poly_cx - cloud_cx) ** 2 + (poly_cy - cloud_cy) ** 2), 4
                )
            except Exception:
                pass

        return {
            pt_density_field: density,
            pt_hull_ratio_field: hull_ratio if hull_ratio is not None else 0.0,
            pt_dispersion_field: dispersion,
            pt_centroid_dist_field: centroid_dist,
        }


    # =========================================================
    # NEIGHBOUR TOPOLOGY
    # =========================================================
    def build_neighbor_lookup(poly_fc, poly_id_field, temp_poly_neighbor):
        print("  Running PolygonNeighbors...")
        delete_if_exists(temp_poly_neighbor)

        arcpy.analysis.PolygonNeighbors(
            in_features=poly_fc,
            out_table=temp_poly_neighbor,
            in_fields=poly_id_field,
            area_overlap="NO_AREA_OVERLAP",
            both_sides="BOTH_SIDES",
            cluster_tolerance="",
            out_linear_units="",
            out_area_units=""
        )

        src_field = "src_{}".format(poly_id_field)
        nbr_field = "nbr_{}".format(poly_id_field)
        length_field = "LENGTH"

        neighbors = defaultdict(set)
        shared_len = defaultdict(float)

        with arcpy.da.SearchCursor(temp_poly_neighbor, [src_field, nbr_field, length_field]) as cur:
            for src_id, nbr_id, length in cur:
                if src_id is None or nbr_id is None:
                    continue
                neighbors[src_id].add(nbr_id)
                shared_len[src_id] += (length or 0.0)

        return neighbors, shared_len


    def aggregate_neighbor_features(poly_id, neighbors, shared_len, geo_features,
                                    nbr_avg_area_field,
                                    nbr_avg_elongation_field,
                                    nbr_avg_convexity_field,
                                    nbr_avg_vertices_field,
                                    nbr_area_ratio_field,
                                    nbr_dominant_shape_field,
                                    elongation_field,
                                    convexity_field,
                                    vertex_count_field,
                                    shape_label_encoding):
        nbr_ids = list(neighbors.get(poly_id, set()))
        nbr_count = len(nbr_ids)

        if nbr_count == 0:
            return {
                nbr_avg_area_field: None,
                nbr_avg_elongation_field: None,
                nbr_avg_convexity_field: None,
                nbr_avg_vertices_field: None,
                nbr_area_ratio_field: None,
                nbr_dominant_shape_field: -1,
            }

        nbr_metrics = [geo_features[nid] for nid in nbr_ids if nid in geo_features]

        avg_area = safe_mean([m["area"] for m in nbr_metrics])
        avg_elongation = safe_mean([m[elongation_field] for m in nbr_metrics])
        avg_convexity = safe_mean([m[convexity_field] for m in nbr_metrics])
        avg_vertices = safe_mean([m[vertex_count_field] for m in nbr_metrics])

        self_area = geo_features.get(poly_id, {}).get("area")
        area_ratio = round(self_area / avg_area, 6) if (self_area and avg_area) else None

        shape_votes = defaultdict(int)
        for m in nbr_metrics:
            shape_votes[m["shape_class"]] += 1
        dominant_label = max(shape_votes, key=shape_votes.get) if shape_votes else "none"
        dominant_code = shape_label_encoding.get(dominant_label, -1)

        return {
            nbr_avg_area_field: avg_area,
            nbr_avg_elongation_field: avg_elongation,
            nbr_avg_convexity_field: avg_convexity,
            nbr_avg_vertices_field: avg_vertices,
            nbr_area_ratio_field: area_ratio,
            nbr_dominant_shape_field: dominant_code,
        }


    print("\n[3/5] Feature Engineering...")

    if not arcpy.Exists(input_polygons):
        raise ValueError("Polygon FC not found: {}".format(input_polygons))
    if not arcpy.Exists(input_points):
        raise ValueError("Point FC not found: {}".format(input_points))
    if arcpy.Describe(input_polygons).shapeType.upper() != "POLYGON":
        raise ValueError("input_polygons must be a polygon layer.")
    if arcpy.Describe(input_points).shapeType.upper() != "POINT":
        raise ValueError("input_points must be a point layer.")

    for path in [temp_polygons, temp_point_join, temp_poly_neighbor, temp_point_hull, output_polygons]:
        delete_if_exists(path)

    arcpy.management.CopyFeatures(input_polygons, temp_polygons)
    ensure_field(temp_polygons, poly_id_field, "LONG")
    poly_oid = arcpy.Describe(temp_polygons).OIDFieldName

    with arcpy.da.UpdateCursor(temp_polygons, [poly_oid, poly_id_field]) as cur:
        for row in cur:
            row[1] = row[0]
            cur.updateRow(row)

    arcpy.analysis.SpatialJoin(
        target_features=input_points,
        join_features=temp_polygons,
        out_feature_class=temp_point_join,
        join_operation="JOIN_ONE_TO_ONE",
        join_type="KEEP_COMMON",
        match_option="INTERSECT"
    )

    if not field_exists(temp_point_join, poly_id_field):
        raise ValueError("'{}' missing from joined point layer.".format(poly_id_field))

    poly_point_count = defaultdict(int)
    poly_points_xy = defaultdict(list)

    with arcpy.da.SearchCursor(temp_point_join, [poly_id_field, "SHAPE@XY"]) as cur:
        for row in cur:
            poly_id, xy = row[0], row[1]
            if poly_id is None or xy is None:
                continue
            poly_point_count[poly_id] += 1
            poly_points_xy[poly_id].append((xy[0], xy[1]))

    geo_features = {}
    poly_geom_map = {}

    with arcpy.da.SearchCursor(temp_polygons, [poly_id_field, "SHAPE@", "SHAPE@AREA", "SHAPE@LENGTH"]) as cur:
        for poly_id, geom, area, perimeter in cur:
            geo_features[poly_id] = compute_geometry_metrics(
                geom, area, perimeter,
                vertex_count_field,
                hole_count_field,
                regularity_field,
                elongation_field,
                convexity_field
            )
            poly_geom_map[poly_id] = geom

    pt_dist_features = {}
    for poly_id, gf in geo_features.items():
        pts = poly_points_xy.get(poly_id, [])
        p_area = gf["area"]
        p_geom = poly_geom_map.get(poly_id)
        pt_dist_features[poly_id] = compute_point_distribution(
            pts, p_area, p_geom, temp_polygons,
            pt_density_field,
            pt_hull_ratio_field,
            pt_dispersion_field,
            pt_centroid_dist_field
        )

    neighbors, shared_len = build_neighbor_lookup(temp_polygons, poly_id_field, temp_poly_neighbor)

    nbr_features = {
        pid: aggregate_neighbor_features(
            pid, neighbors, shared_len, geo_features,
            nbr_avg_area_field,
            nbr_avg_elongation_field,
            nbr_avg_convexity_field,
            nbr_avg_vertices_field,
            nbr_area_ratio_field,
            nbr_dominant_shape_field,
            elongation_field,
            convexity_field,
            vertex_count_field,
            shape_label_encoding
        )
        for pid in geo_features
    }

    arcpy.management.CopyFeatures(temp_polygons, output_polygons)

    field_defs = [
        (cluster_type_field, "LONG"),
        (pt_density_field, "DOUBLE"),
        (pt_hull_ratio_field, "DOUBLE"),
        (pt_dispersion_field, "DOUBLE"),
        (pt_centroid_dist_field, "DOUBLE"),
        (vertex_count_field, "LONG"),
        (hole_count_field, "LONG"),
        (regularity_field, "DOUBLE"),
        (elongation_field, "DOUBLE"),
        (convexity_field, "DOUBLE"),
        (nbr_avg_area_field, "DOUBLE"),
        (nbr_avg_elongation_field, "DOUBLE"),
        (nbr_avg_convexity_field, "DOUBLE"),
        (nbr_avg_vertices_field, "DOUBLE"),
        (nbr_area_ratio_field, "DOUBLE"),
        (nbr_dominant_shape_field, "LONG"),
    ]

    for fname, ftype in field_defs:
        ensure_field(output_polygons, fname, ftype)

    update_fields = [poly_id_field] + [f for f, _ in field_defs]

    with arcpy.da.UpdateCursor(output_polygons, update_fields) as cur:
        for row in cur:
            pid = row[0]
            gf = geo_features.get(pid, {})
            nf = nbr_features.get(pid, {})
            pdf = pt_dist_features.get(pid, {})
            pc = poly_point_count.get(pid, 0)
            pts = poly_points_xy.get(pid, [])

            row[1] = encode_cluster_type(
                pc, pts,
                cluster_type_no_points,
                cluster_type_single_point,
                cluster_type_two_points,
                cluster_type_all_noise,
                cluster_type_single_cluster,
                cluster_type_multi_cluster
            )
            row[2] = pdf.get(pt_density_field, None)
            row[3] = pdf.get(pt_hull_ratio_field, 0.0)
            row[4] = pdf.get(pt_dispersion_field, None)
            row[5] = pdf.get(pt_centroid_dist_field, None)
            row[6] = gf.get(vertex_count_field, 0)
            row[7] = gf.get(hole_count_field, 0)
            row[8] = gf.get(regularity_field, None)
            row[9] = gf.get(elongation_field, None)
            row[10] = gf.get(convexity_field, None)
            row[11] = nf.get(nbr_avg_area_field, None)
            row[12] = nf.get(nbr_avg_elongation_field, None)
            row[13] = nf.get(nbr_avg_convexity_field, None)
            row[14] = nf.get(nbr_avg_vertices_field, None)
            row[15] = nf.get(nbr_area_ratio_field, None)
            row[16] = nf.get(nbr_dominant_shape_field, -1)
            cur.updateRow(row)

    print("      Feature engineering complete → {}".format(output_polygons))
    print("      Total polygons processed: {}".format(len(geo_features)))
    return output_polygons

# =========================================================
# End of Feature Engineering Block
# =========================================================


def terrace_buildings_to_builtup_area(build_point_layer,raw_line_layer,raw_source_layer,append_target,my_gdb,dlpk_path, townbuiltup_min_area):
    # --------------------------------------------------
    # FIELD NAMES
    # --------------------------------------------------
    poly_id_field = "POLY_UID"

    cluster_type_field = "cluster_type"
    pt_density_field = "pt_density"
    pt_hull_ratio_field = "pt_hull_ratio"
    pt_dispersion_field = "pt_dispersion"
    pt_centroid_dist_field = "pt_centroid_dist"

    vertex_count_field = "vertex_count"
    hole_count_field = "hole_count"
    regularity_field = "poly_regularity"
    elongation_field = "elongation"
    convexity_field = "convexity"

    nbr_avg_area_field = "nbr_avg_area"
    nbr_avg_elongation_field = "nbr_avg_elongation"
    nbr_avg_convexity_field = "nbr_avg_convexity"
    nbr_avg_vertices_field = "nbr_avg_vertices"
    nbr_area_ratio_field = "nbr_area_ratio"
    nbr_dominant_shape_field = "nbr_dominant_shape"
    # --------------------------------------------------
    # CLUSTER-TYPE ENCODING
    # --------------------------------------------------
    cluster_type_no_points = 0
    cluster_type_single_point = 1
    cluster_type_two_points = 2
    cluster_type_all_noise = 3
    cluster_type_single_cluster = 4
    cluster_type_multi_cluster = 5
    # --------------------------------------------------
    # SHAPE-CLASS ENCODING
    # --------------------------------------------------
    shape_label_encoding = {"circular": 3,"compact": 2,"elongated": 1,"irregular": 0,"none": -1,}
    # --------------------------------------------------
    # DERIVED PATHS
    # --------------------------------------------------
    step1_polygons = os.path.join(my_gdb, "step1_feature_to_polygon")
    step2_points = os.path.join(my_gdb, "step2_feature_to_point")
    output_polygons = os.path.join(my_gdb, "step3_engineered_polygons")
    temp_polygons = os.path.join(my_gdb, "temp_polygons_uid")
    temp_point_join = os.path.join(my_gdb, "temp_points_with_polyid")
    temp_poly_neighbor = os.path.join(my_gdb, "temp_poly_neighbors")
    temp_point_hull = os.path.join(my_gdb, "temp_point_hull")
    predicted_polygons = os.path.join(my_gdb, "step4_predicted_polygons")
    temp_select_pnt_layer = os.path.join(my_gdb, "temp_select_pnt_layer")
    temp_dis_layer = os.path.join(my_gdb, "temp_dis_layer")
    temp_elim_layer = os.path.join(my_gdb, "temp_elim_layer")
    temp_aggr_layer = os.path.join(my_gdb, "temp_aggr_layer")
    temp_aggr_tbl = os.path.join(my_gdb, "temp_aggr_tbl")
    temp_select_layer = "temp_class1_lyr"


    arcpy.AddMessage("=" * 60)
    arcpy.AddMessage("FULL BUILTUP DETECTION PIPELINE")
    arcpy.AddMessage("=" * 60)

    # --------------------------------------------------
    # STEP 1 — Feature To Polygon
    # --------------------------------------------------
    arcpy.AddMessage("\n[1/5] Feature To Polygon...")
    delete_if_exists(step1_polygons)

    arcpy.management.FeatureToPolygon(in_features=raw_line_layer,out_feature_class=step1_polygons,cluster_tolerance="",attributes="ATTRIBUTES",label_features="")
    print("Polygons created → {}".format(step1_polygons))

    # --------------------------------------------------
    # STEP 2 — Feature To Point
    # --------------------------------------------------
    arcpy.AddMessage("\n[2/5] Feature To Point...")
    delete_if_exists(step2_points)

    selected_building_type = arcpy.management.SelectLayerByAttribute(in_layer_or_view=raw_source_layer,selection_type="NEW_SELECTION",where_clause="RET = 3")
    temp_select_pnt_layer = arcpy.management.FeatureToPoint(in_features=selected_building_type,out_feature_class=temp_select_pnt_layer,point_location="INSIDE")
    arcpy.AddMessage(f"Points created → {step2_points}")
    step2_points=arcpy.management.Merge(inputs=f"{build_point_layer};{temp_select_pnt_layer}",output=step2_points,field_mappings=None,add_source="NO_SOURCE_INFO",
                                        field_match_mode="AUTOMATIC")
    # --------------------------------------------------
    # STEP 3 — Feature Engineering
    # --------------------------------------------------
    engineered_fc = run_feature_engineering(input_polygons=step1_polygons,input_points=step2_points,output_polygons=output_polygons,temp_polygons=temp_polygons,
                                            temp_point_join=temp_point_join,temp_poly_neighbor=temp_poly_neighbor,temp_point_hull=temp_point_hull,poly_id_field=poly_id_field,
                                            cluster_type_field=cluster_type_field,pt_density_field=pt_density_field,pt_hull_ratio_field=pt_hull_ratio_field,
                                            pt_dispersion_field=pt_dispersion_field,pt_centroid_dist_field=pt_centroid_dist_field,vertex_count_field=vertex_count_field,
                                            hole_count_field=hole_count_field,regularity_field=regularity_field,elongation_field=elongation_field,
                                            convexity_field=convexity_field,nbr_avg_area_field=nbr_avg_area_field,nbr_avg_elongation_field=nbr_avg_elongation_field,
                                            nbr_avg_convexity_field=nbr_avg_convexity_field,nbr_avg_vertices_field=nbr_avg_vertices_field,
                                            nbr_area_ratio_field=nbr_area_ratio_field,nbr_dominant_shape_field=nbr_dominant_shape_field,
                                            cluster_type_no_points=cluster_type_no_points,cluster_type_single_point=cluster_type_single_point,
                                            cluster_type_two_points=cluster_type_two_points,cluster_type_all_noise=cluster_type_all_noise,
                                            cluster_type_single_cluster=cluster_type_single_cluster,cluster_type_multi_cluster=cluster_type_multi_cluster,
                                            shape_label_encoding=shape_label_encoding)
    arcpy.AddMessage("\n[3/5] Feature Engineering Completed...")

    # --------------------------------------------------
    # STEP 4 — Predict With AutoML
    # --------------------------------------------------
    arcpy.AddMessage("\n[4/5] Predict With AutoML...")
    arcpy.AddMessage(f"Model path : {dlpk_path}")

    delete_if_exists(predicted_polygons)

    arcpy.geoai.PredictUsingAutoML(in_model_definition=dlpk_path,prediction_type="PREDICT_FEATURE",in_features=engineered_fc,explanatory_rasters=None,
                                   distance_features=None,out_prediction_features=predicted_polygons,out_prediction_surface=None,
                                   match_explanatory_variables="pt_hull_ratio pt_hull_ratio;elongation elongation;poly_regularity poly_regularity;nbr_avg_vertices nbr_avg_vertices;pt_centroid_dist pt_centroid_dist;vertex_count vertex_count;hole_count hole_count;nbr_avg_elongation nbr_avg_elongation;nbr_area_ratio nbr_area_ratio;convexity convexity;nbr_avg_convexity nbr_avg_convexity;nbr_avg_area nbr_avg_area;pt_dispersion pt_dispersion;nbr_dominant_shape nbr_dominant_shape;pt_density pt_density;cluster_type cluster_type",
                                   match_distance_variables=None,match_explanatory_rasters=None,get_prediction_explanations="FALSE")

    arcpy.AddMessage(f"Prediction complete → {predicted_polygons}")

    # --------------------------------------------------
    # STEP 5 — Select Class 1 → Append to target layer
    # --------------------------------------------------
    arcpy.AddMessage("\n[5/5] Selecting class 1 features and appending...")

    pred_field = "prediction_results"

    arcpy.AddMessage(f"Using prediction field: {pred_field}")

    if arcpy.Exists(temp_select_layer):
        arcpy.management.Delete(temp_select_layer)

    arcpy.management.MakeFeatureLayer(in_features=predicted_polygons,out_layer=temp_select_layer,where_clause=f"{pred_field} = 1")

    count = int(arcpy.management.GetCount(temp_select_layer)[0])
    arcpy.AddMessage(f"Class-1 features found: {count}")
    if count > 0:
        if not arcpy.Exists(append_target):
            raise ValueError(
                "Append target not found: {}\n"
                "Create or set APPEND_TARGET correctly.".format(append_target)
            )
        append_sr = arcpy.Describe(append_target).spatialReference

        # Set output coordinate system same as append_layer
        arcpy.env.outputCoordinateSystem = append_sr
        arcpy.management.Dissolve(in_features=temp_select_layer,out_feature_class=temp_dis_layer,dissolve_field=None,statistics_fields=None,
                                                   multi_part="SINGLE_PART",unsplit_lines="DISSOLVE_LINES",concatenation_separator="")
        
        arcpy.management.EliminatePolygonPart(in_features=temp_dis_layer,out_feature_class=temp_elim_layer,condition="AREA",part_area="150000 SquareMeters",part_area_percent=0,
                                              part_option="CONTAINED_ONLY")
        
        arcpy.cartography.AggregatePolygons(in_features=temp_elim_layer,out_feature_class=temp_aggr_layer,aggregation_distance="100 Meters",minimum_area=None,minimum_hole_size=None,
                                            orthogonality_option="ORTHOGONAL",barrier_features=None,out_table=temp_aggr_tbl,aggregate_field=None)

        arcpy.AddMessage(f"Features count before processing: {count_features(temp_aggr_layer)}")
        arcpy.management.Append(inputs=temp_aggr_layer, target=append_target, schema_type="NO_TEST")
        
    else:
        arcpy.AddMessage("No class-1 features found. Append skipped.")


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
        arcpy.AddError(error_message)

def delete_features_in_poly(features_in_cemetery, poly_fc, poly_size):
    # Set the workspace
    arcpy.env.overwriteOutput = True
    dynamic_fc_names = resolve_lyr()
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
            if dynamic_fc_names.Residential_Building_A in pt_fc or dynamic_fc_names.Industrial_Building_A in pt_fc or dynamic_fc_names.Educational_Building_A in pt_fc:
                pt_lyr = arcpy.management.MakeFeatureLayer(pt_fc, "point_lyr")
            elif dynamic_fc_names.Residential_Building_P in pt_fc or dynamic_fc_names.Industrial_Building_P in pt_fc or dynamic_fc_names.Educational_Building_P in pt_fc:
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
        arcpy.AddError(error_message)

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
        arcpy.AddError(error_message)


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
        arcpy.AddError(error_message)

def delineate_built_up_area(fc_list, in_buildings_list, edge_features_list, grouping_distance, minimum_detail_size, minimum_building_count, working_gdb, delineate_ref_scale, townbuiltup_min_area):
    # Define environment variables
    arcpy.env.overwriteOutput = True
    arcpy.env.referenceScale = delineate_ref_scale
    dynamic_fc_names = resolve_lyr()
    try:
        
        in_buildings_list = list(filter(str.strip, in_buildings_list))
        in_buildings = [fc for a_lyr in in_buildings_list for fc in fc_list if str(a_lyr) in fc]
        edge_features_list = list(filter(str.strip, edge_features_list))
        edge_features = [fc for a_lyr in edge_features_list for fc in fc_list if str(a_lyr) in fc]
        # Town Built Up Fc Layer
        town_buil_up = [fc for fc in fc_list if dynamic_fc_names.Town_Built_up_A in fc][0]
        out_feature_class = f"{working_gdb}\\temp_built_up"
        temp_elim_layer = f"{working_gdb}\\temp_elm_fc"
        append_sr = arcpy.Describe(town_buil_up).spatialReference
        # Set output coordinate system same as append_layer
        arcpy.env.outputCoordinateSystem = append_sr
        arcpy.cartography.DelineateBuiltUpAreas(in_buildings, "", edge_features, f"{grouping_distance} Meters", f"{minimum_detail_size} Millimeters", out_feature_class, minimum_building_count)
        
        
        # Append with town build-up layer
        arcpy.management.Append(inputs=out_feature_class, target=town_buil_up, schema_type="NO_TEST")
        arcpy.management.Dissolve(in_features=town_buil_up, out_feature_class=f"{working_gdb}\\temp_dissolve_town", dissolve_field=None, statistics_fields=None, multi_part="SINGLE_PART")
        arcpy.management.EliminatePolygonPart(in_features=f"{working_gdb}\\temp_dissolve_town",out_feature_class=temp_elim_layer,condition="AREA",part_area="150000 SquareMeters",part_area_percent=0,
                                              part_option="CONTAINED_ONLY")
        arcpy.management.TruncateTable(town_buil_up)
        arcpy.management.Append(inputs=temp_elim_layer, target=town_buil_up, schema_type="NO_TEST")
    except Exception as e:
        tb = traceback.format_exc()
        error_message = f"Delineate built-up area error: {e}\nTraceback details:\n{tb}"
        arcpy.AddError(error_message)




def generalised_buildings(fc_list, general_builtup_min_area):
    dynamic_fc_names = resolve_lyr()
    try:
        # Set the workspace
        arcpy.env.overwriteOutput = True
        local_authoruty_cover = [fc for fc in fc_list if dynamic_fc_names.Local_Authority_Area_A in fc][0]
        if count_features(local_authoruty_cover)>0:
            town_buil_up = [fc for fc in fc_list if dynamic_fc_names.Town_Built_up_A in fc][0]
            generalised_building = [fc for fc in fc_list if dynamic_fc_names.Generalised_Buildings_A in fc][0]
            # Make feature layers
            local_authoruty_cover = arcpy.management.MakeFeatureLayer(local_authoruty_cover, "local_authoruty_cover")
            town_buil_up = arcpy.management.MakeFeatureLayer(town_buil_up, "town_buil_up")
            # Town buil up selection by Local Authority Cover Layer
            selected_townbuildup = arcpy.management.SelectLayerByLocation(town_buil_up, 'INTERSECT', local_authoruty_cover, None, 'NEW_SELECTION')
            if count_features(selected_townbuildup)>0:
                arcpy.management.SelectLayerByAttribute(selected_townbuildup, "SWITCH_SELECTION")
                # Append town built up areas with generalised building
                arcpy.management.Append(selected_townbuildup, generalised_building, 'NO_TEST')
                # Delete features from town built up areas
                arcpy.management.DeleteFeatures(selected_townbuildup)
                gen_sql_query = F"Shape_Area < {general_builtup_min_area}"
                selected_gen_temp_dis_layer=arcpy.management.SelectLayerByAttribute(generalised_building,"NEW_SELECTION",gen_sql_query)
                if count_features(selected_gen_temp_dis_layer)>0:
                    arcpy.management.DeleteFeatures(selected_gen_temp_dis_layer)
                arcpy.AddMessage("Successfull to append features from Town Builtup to Generalised Buildings layer")
            else:
                arcpy.AddMessage("no features are selected within local authority boundary")
        else:arcpy.AddMessage("no features are found within local authority boundary, skipping the generalised building function")

    except Exception as e:
        tb = traceback.format_exc()
        error_message = f"Generalised building error: {e}\nTraceback details:\n{tb}"
        arcpy.AddError(error_message)

def resolve_fence(pond, fence, scratch_gdb, distance="17 Meters", map_name = "04 Built-Up Generalization"):
    arcpy.env.overwriteOutput = 1
    arcpy.AddMessage("Starting Resolving Fence")
    try:
        pond_base_name = os.path.basename(pond)
        fence_base_name = os.path.basename(fence)
        pond_layer = get_feature_layer_by_feature_class(os.path.basename(pond), map_name)[0]
        fence_layer = get_feature_layer_by_feature_class(os.path.basename(fence), map_name)[0]
        if has_features(pond) and has_features(fence):
            fence_line_to_move = arcpy.management.SelectLayerByLocation(
                in_layer=fence_layer,
                overlap_type="INTERSECT",
                select_features=pond_layer,
                search_distance=distance,
                selection_type="NEW_SELECTION",
                invert_spatial_relationship="NOT_INVERT"
            )

            pond_buffer = arcpy.analysis.Buffer(
                in_features=pond_layer,
                out_feature_class=f"{scratch_gdb}\\{pond_base_name}_Buffer",
                buffer_distance_or_field=distance,
                line_side="FULL",
                line_end_type="ROUND",
                method="PLANAR"
            )
            
            fence_vertices = arcpy.management.FeatureVerticesToPoints(
                in_features=fence_layer,
                out_feature_class=f"{scratch_gdb}\\{fence_base_name}_FeatureVertice",
                point_location="ALL"
            )

            pond_buffer_line = arcpy.management.FeatureToLine(
                in_features=pond_buffer,
                out_feature_class=f"{scratch_gdb}\\{pond_base_name}_Buff_Line",
                cluster_tolerance=None,
                attributes="ATTRIBUTES"
            )

            arcpy.analysis.Near(
                in_features=fence_vertices,
                near_features=pond_buffer_line,
                search_radius=None,
                location="LOCATION",
                angle="NO_ANGLE",
                method="PLANAR",
                distance_unit="",
                match_fields=None
            )

            arcpy.management.SelectLayerByAttribute(
                in_layer_or_view=fence_vertices,
                selection_type="NEW_SELECTION",
                where_clause="NEAR_DIST <> -1",
                invert_where_clause=None
            )

            new_fence_points = arcpy.management.XYTableToPoint(
                in_table=fence_vertices,
                out_feature_class=f"{scratch_gdb}\\{fence_base_name}_FeatureVertice_XYTableToPoint",
                x_field="NEAR_X",
                y_field="NEAR_Y",
                coordinate_system='PROJCS["GDM_2000_MRSO_Peninsular_Malaysia",GEOGCS["GCS_GDM_2000",DATUM["D_GDM_2000",SPHEROID["GRS_1980",6378137.0,298.257222101]],PRIMEM["Greenwich",0.0],UNIT["Degree",0.0174532925199433]],PROJECTION["Rectified_Skew_Orthomorphic_Natural_Origin"],PARAMETER["False_Easting",804671.0],PARAMETER["False_Northing",0.0],PARAMETER["Scale_Factor",0.99984],PARAMETER["Azimuth",323.0257964666666],PARAMETER["Longitude_Of_Center",102.25],PARAMETER["Latitude_Of_Center",4.0],PARAMETER["XY_Plane_Rotation",-36.86989764584402],UNIT["Meter",1.0]];-30656400 -28732700 10000;-100000 10000;-100000 10000;0.001;0.001;0.001;IsHighPrecision'
            )
            modified_fence_line = arcpy.management.PointsToLine(
                Input_Features=new_fence_points,
                Output_Feature_Class=f"{scratch_gdb}\\{fence_base_name}_FeatureVertice_XYTableToPoint_PointsToLine",
                Line_Field="ORIG_FID",
                Sort_Field="NEAR_FID",
                Close_Line="NO_CLOSE",
                Line_Construction_Method="CONTINUOUS",
                Attribute_Source="NONE",
                Transfer_Fields=None
            )
            
            modified_fence_line_fields = [fld.name for fld in arcpy.ListFields(modified_fence_line) if fld.name not in ["OBJECTID", "Shape", "Shape_Length"]]
            modified_joined_fence_line = arcpy.analysis.SpatialJoin(
                target_features=modified_fence_line,
                join_features=f"{fence_layer} Join_Count",
                out_feature_class=f"{scratch_gdb}\\{fence_base_name}_F_SpatialJoin",
                join_operation="JOIN_ONE_TO_ONE",
                join_type="KEEP_ALL",
                match_option="WITHIN_A_DISTANCE",
                search_radius=distance,
                distance_field_name="",
                match_fields=None
            )

            arcpy.management.DeleteField(
                in_table=modified_joined_fence_line,
                drop_field=modified_fence_line_fields,
                method="DELETE_FIELDS"
            )
            # Clearing Selection
            arcpy.management.SelectLayerByAttribute(fence_layer, "CLEAR_SELECTION")
            arcpy.management.SelectLayerByLocation(
                in_layer=fence_layer,
                overlap_type="INTERSECT",
                select_features=pond_layer,
                search_distance=distance,
                selection_type="NEW_SELECTION",
                invert_spatial_relationship="NOT_INVERT"
            )
            arcpy.management.DeleteRows(
                in_rows=fence_line_to_move
            )
            arcpy.management.Append(
                inputs = [modified_joined_fence_line], 
                target= fence, 
                schema_type="NO_TEST"
            )
            arcpy.AddMessage(f"Resolving conflict between {pond} and {fence} are successful.")
        else:
            arcpy.AddMessage(f"Data could not be found in either {pond} or {fence} feature classes.")
    except Exception as e:
        tb = traceback.format_exc()
        error_message = f"resolve_fence error: {e}\nTraceback details:\n{tb}"
        arcpy.AddError(error_message)

def get_xy(pt_or_geom):
    """
    Returns X and Y as a point geometry
    Author: Shahmin Aurnov
    """
    if hasattr(pt_or_geom, "firstPoint") and pt_or_geom.firstPoint:
        p = pt_or_geom.firstPoint
        return p.X, p.Y
    else:
        return pt_or_geom.X, pt_or_geom.Y

def assign_distance(fc, class_field, rules_dict):
    """
    Assigns distance values based on class field
    Author: Shahmin Aurnov
    """
    if "DIST_M" not in [f.name for f in arcpy.ListFields(fc)]:
        arcpy.management.AddField(fc, "DIST_M", "DOUBLE")
    
    with arcpy.da.UpdateCursor(fc, [class_field, "DIST_M"]) as cur:
        for cls, dist_m in cur:
            try:
                cls_code = int(cls)
                new_dist = rules_dict.get(cls_code)
            except (TypeError, ValueError):
                new_dist = None
            cur.updateRow((cls, new_dist))

def adjust_based_on_distance(road_fc, track_fc, target_fc, road_class_field, track_class_field,
                                    road_distance_rules, track_distance_rules, working_gdb):
    """
    Adjusts fence geometries based on proximity to roads and tracks, applying distance rules.
    Author: Shahmin Aurnov
    """
    arcpy.env.workspace = working_gdb
    arcpy.env.overwriteOutput = True

    ### Step-1: Preparing Datasets for conflict resolution between fence and road/track
    # Temporary feature classes for roads and tracks
    road_tmp = fr"{working_gdb}\roads_tmp"
    track_tmp = fr"{working_gdb}\tracks_tmp"


    # Copying features for roads and tracks
    arcpy.conversion.ExportFeatures(road_fc, road_tmp)
    arcpy.conversion.ExportFeatures(track_fc, track_tmp)

    # Assigning distances
    assign_distance(road_tmp, road_class_field, road_distance_rules)
    assign_distance(track_tmp, track_class_field, track_distance_rules)

    # Merging road and track features into one base layer
    base_all_fc = fr"{working_gdb}\base_all"
    arcpy.management.Merge([road_tmp, track_tmp], base_all_fc)

    # Copying target fences to avoid modifying the originals
    out_layer = fr"{working_gdb}\BJ0400_Fence_L_moved"
    arcpy.conversion.ExportFeatures(target_fc, out_layer)

    ### Step-2: Starting work to identify the side and position of fences along road and track lines
    # Running Near analysis between fences and merged base features
    search_radius = max(max(road_distance_rules.values()), max(track_distance_rules.values()))
    arcpy.analysis.Near(out_layer, base_all_fc, search_radius=search_radius)

    # Extracting base feature geometries and their distance rules into a dictionary
    base_oid_field = arcpy.Describe(base_all_fc).oidFieldName
    base_geom_dict = {
        oid: (geom, dist_m)
        for oid, geom, dist_m in arcpy.da.SearchCursor(base_all_fc, [base_oid_field, "SHAPE@", "DIST_M"])
    }

    ### Step-3: Updating fence geometries based on proximity to base features
    fields = ["OID@", "SHAPE@", "NEAR_FID", "NEAR_DIST"]
    moved, skipped_no_road, skipped_degenerate, skipped_no_rule = 0, 0, 0, 0

    with arcpy.da.UpdateCursor(out_layer, fields) as cur:
        for oid, geom, near_fid, near_dist in cur:
            if near_fid == -1 or geom is None:
                skipped_no_road += 1
                continue

            base_info = base_geom_dict.get(near_fid)
            if not base_info:
                skipped_no_road += 1
                continue

            base_geom, move_distance = base_info
            if move_distance is None:
                skipped_no_rule += 1
                continue

            # Calculating fence axis and normalization
            fp = geom.firstPoint
            lp = geom.lastPoint
            vx, vy = lp.X - fp.X, lp.Y - fp.Y
            axis_len = math.hypot(vx, vy)
            if axis_len == 0:
                ext = geom.extent
                vx, vy = ext.XMax - ext.XMin, ext.YMax - ext.YMin
                axis_len = math.hypot(vx, vy)
                if axis_len == 0:
                    skipped_degenerate += 1
                    continue

            vx, vy = vx / axis_len, vy / axis_len
            nLx, nLy, nRx, nRy = -vy, vx, vy, -vx

            # Getting the base point for the fence
            ref_pt_geom = geom.labelPoint
            try:
                base_pt_geom, _, _, _ = base_geom.queryPointAndDistance(ref_pt_geom)
            except SystemError:
                base_pt_geom = base_geom.centroid

            rx, ry = get_xy(base_pt_geom)

            # Determining which side of the fence to adjust
            ox, oy = fp.X, fp.Y
            vrx, vry = rx - ox, ry - oy
            cross = vx * vry - vy * vrx
            nx, ny = (nRx, nRy) if cross > 0 else (nLx, nLy)

            # Calculating the required translation offset
            offset = move_distance - near_dist
            if offset <= 0:
                continue

            tx, ty = nx * offset, ny * offset

            # Applying translation to fence vertices
            new_parts = []
            for part in geom:
                arr = arcpy.Array()
                for pt in part:
                    if pt:
                        arr.add(arcpy.Point(pt.X + tx, pt.Y + ty, pt.Z, pt.M))
                    else:
                        arr.add(pt)
                new_parts.append(arr)

            new_geom = arcpy.Polyline(arcpy.Array(new_parts), geom.spatialReference)
            cur.updateRow((oid, new_geom, near_fid, near_dist))
            moved += 1

    ### Step-4: Cleaning up output by deleting unwanted fields
    reference_fields = [f.name for f in arcpy.ListFields(target_fc)]
    output_fields = [f.name for f in arcpy.ListFields(out_layer)]
    fields_to_delete = [f.name for f in arcpy.ListFields(out_layer) if f.name not in reference_fields and not f.required]
    if fields_to_delete:
        arcpy.management.DeleteField(out_layer, fields_to_delete)

    ### Step-5: Appending the adjusted fences back to the original target feature class
    arcpy.management.DeleteRows(target_fc)
    arcpy.management.Append(inputs=[out_layer], target=target_fc, schema_type="NO_TEST")

    return {
        "moved": moved,
        "skipped_no_road": skipped_no_road,
        "skipped_degenerate": skipped_degenerate,
        "skipped_no_rule": skipped_no_rule,
        "output_fc": target_fc
    }


def layer_from_map(layer_name, map_name):
    aprx = arcpy.mp.ArcGISProject("CURRENT")
    m = next(mp for mp in aprx.listMaps() if mp.name == map_name)

    lyr = next(
        lyr for lyr in m.listLayers()
        if lyr.isFeatureLayer and lyr.name == layer_name
    )
    return lyr.dataSource


def fix_wall_fence_conflict_with_road(road_fc, track_fc, target_fc, road_distance_rules, 
                                      track_distance_rules, working_gdb, logger, 
                                      road_class_field='RCS', track_class_field='TCS'):
    try:
        # map_name = "04 Built-Up Generalization"
        # road_layer = layer_from_map(os.path.basename(road_fc), map_name)
        # track_layer = layer_from_map(os.path.basename(track_fc), map_name)
        # target_layer = layer_from_map(os.path.basename(target_fc), map_name)

        result = adjust_based_on_distance(
                    road_fc=road_fc,
                    track_fc=track_fc,
                    target_fc=target_fc,
                    road_class_field=road_class_field, 
                    track_class_field=track_class_field,
                    road_distance_rules=road_distance_rules,
                    track_distance_rules=track_distance_rules,
                    working_gdb=working_gdb
                )
        return result

    except Exception as e:
        exc_type, exc_value, exc_traceback = sys.exc_info()
        tb = traceback.format_exc()
        error_message = f"Built-Up Area Generalisation error: {e}\nTraceback details:\n{tb}"
        arcpy.AddError(error_message)
        logger.error(error_message)
        simplified_msgs('Built-Up Area Generalisation', f'{exc_value}\n')


def merge_buildings_too_closed_between_building_and_street(in_fc_name, building_fc_name, fc_list, working_gdb, logger, area_threshold = 100000):
    arcpy.env.workspace = working_gdb
    count_overlap_output = f"{working_gdb}\\{building_fc_name}_CountOverlap"
    backup_fc = f"{working_gdb}\\{building_fc_name}_backup"
    in_feature = None
    building_feature = None
    in_feature_list = [fc for fc in fc_list if in_fc_name in fc]
    building_feature_list = [fc for fc in fc_list if building_fc_name in fc]
    if(in_feature_list):
        in_feature = in_feature_list[0]
    if(building_feature_list):
        building_feature = building_feature_list[0]

    arcpy.AddMessage(f"in_feature: {in_feature} and building_feature: {building_feature}")
    in_feature_to_polygon = f"{working_gdb}\\{in_fc_name}_FeatureToPolygon"
    # # Convert Line to Polygon
    arcpy.management.FeatureToPolygon(in_feature, in_feature_to_polygon, None, "ATTRIBUTES")
    arcpy.management.MakeFeatureLayer(in_feature_to_polygon, "in_feature_to_poly_layer")
    # # Delete polygons > area threshold
    arcpy.management.SelectLayerByAttribute("in_feature_to_poly_layer", "NEW_SELECTION", f"Shape_Area > {area_threshold}")
    arcpy.management.DeleteFeatures("in_feature_to_poly_layer")
    # # Delete polygons that intersect buildings
    arcpy.management.SelectLayerByLocation(
        "in_feature_to_poly_layer", "INTERSECT", building_feature, selection_type="NEW_SELECTION", invert_spatial_relationship="INVERT"
    )
    arcpy.management.DeleteFeatures("in_feature_to_poly_layer")
    # # Count overlapping buildings
    arcpy.analysis.CountOverlappingFeatures(building_feature, count_overlap_output, 1)
    arcpy.management.MakeFeatureLayer(count_overlap_output, "count_overlap_lyr")
    # # Select buildings with Count_ > 1
    arcpy.management.SelectLayerByAttribute("count_overlap_lyr", "NEW_SELECTION", "Count_ > 1")
    # # Delete polygons intersecting overlapping buildings
    arcpy.management.SelectLayerByLocation(
        "in_feature_to_poly_layer", "INTERSECT", "count_overlap_lyr", selection_type="NEW_SELECTION", invert_spatial_relationship="INVERT"
    )
    arcpy.management.DeleteFeatures("in_feature_to_poly_layer")
    if not arcpy.Exists(backup_fc):
        arcpy.management.CopyFeatures(building_feature, backup_fc)
        logger.info(f"Backup created: {backup_fc}")
    else:
        logger.info(f"Backup already exists: {backup_fc}")
    # # Delete buildings that intersect cleaned polygons
    arcpy.management.MakeFeatureLayer(building_feature, "building_lyr")
    arcpy.management.SelectLayerByLocation("building_lyr", "INTERSECT", "in_feature_to_poly_layer")
    arcpy.management.DeleteFeatures("building_lyr")
    logger.info("Deleted buildings intersecting polygons")
    arcpy.management.Append("in_feature_to_poly_layer", building_feature, "NO_TEST")
    logger.info("Polygons appended into building feature class")
    return None


def align_feature_with_reference_fc(align_fc, referenece_fc, fc_list, working_gdb, logger):
    align_feature = None
    reference_feature = None
    if(align_fc):
        # Check If Align FC exists in Feature Class List
        align_feature_list = [fc for fc in fc_list if align_fc in fc]
        if(align_feature_list):
          align_feature =  align_feature_list[0]
    if(referenece_fc):
        # Check If Align FC exists in Feature Class List
        reference_feature_list = [fc for fc in fc_list if referenece_fc in fc]
        if(reference_feature_list):
          reference_feature =  reference_feature_list[0]
    ref_fc_buffer=arcpy.analysis.PairwiseBuffer(
        in_features=reference_feature,
        out_feature_class=rf"{working_gdb}\\ref_fc_buffer",
        buffer_distance_or_field="30 Meters",
        dissolve_option="ALL",
        dissolve_field=None,
        method="PLANAR",
        max_deviation="0 Meters"
    )
    logger.info(f"The buffer for {reference_feature} has been created")
    ref_fc_buffer_toline=arcpy.management.FeatureToLine(
        in_features=ref_fc_buffer,
        out_feature_class=rf"{working_gdb}\\ref_fc_buffer_toline",
        cluster_tolerance=None,
        attributes="NO_ATTRIBUTES"
    )
    arcpy.edit.AlignFeatures(
        in_features=align_feature,
        target_features=ref_fc_buffer_toline,
        search_distance="50 Meters",
        match_fields=None
    )
    logger.info(f"The {align_fc} has been aligned with {referenece_fc} successfully.")


def move_feature_1_around_feature_2_to_specific_distance(fc_list, ref_fc_classes: list, to_move_fc_classes : list, working_gdb, logger, min_distance = "12.5") -> None:
    arcpy.env.overwriteOutput = True
    arcpy.env.workspace = working_gdb
    logger.info(f"Starting moving {to_move_fc_classes} around {ref_fc_classes} to {min_distance} meters distance")
    
    ref_original_fcs = []
    to_move_original_fcs = []
    if(fc_list == None or ref_fc_classes == None):
        logger.error("No feature class list was provided. Exiting move_feature_1_around_feature_2_to_specific_distance..")
        return None
    
    # Validate Inputs
    for fc in ref_fc_classes + to_move_fc_classes:
        if fc not in [os.path.basename(fc_name) for fc_name in fc_list]:
            raise ValueError(f"Feature class not found in fc_list: {fc}")
        else:
            for temp_fc in fc_list:
                if fc == os.path.basename(temp_fc)  and fc in ref_fc_classes:
                    ref_original_fcs.append(temp_fc)
                if fc == os.path.basename(temp_fc) and fc in to_move_fc_classes:
                    to_move_original_fcs.append(temp_fc)
    logger.info("Creating working copies")
    arcpy.AddMessage(f"ref_original_fcs: {(ref_original_fcs)}")
    arcpy.AddMessage(f"to_move_original_fcs: {(to_move_original_fcs)}")
    ref_wrk = []
    move_wrk = []
    for fc in to_move_original_fcs:
        add_source_tracking(fc)
    
    # Create Working Copies (Preserve Attributes)
    for fc in ref_original_fcs:
        if(has_features(fc)):
            out_fc = os.path.join(working_gdb, f"{os.path.basename(fc)}_wrk")
            arcpy.management.CopyFeatures(fc, out_fc)
            ref_wrk.append(out_fc)

    for fc in to_move_original_fcs:
        if(has_features(fc)):
            out_fc = os.path.join(working_gdb, f"{os.path.basename(fc)}_wrk")
            arcpy.management.CopyFeatures(fc, out_fc)
            move_wrk.append(out_fc)

    # Merge Reference Features
    logger.info("Merging reference feature classes")

    ref_merged = os.path.join(working_gdb, "ref_merged")
    if(len(ref_wrk) < 1):
        logger.warning(f"No feature could be found for reference feature classes {ref_fc_classes}. Skipping...")
        return None
    arcpy.management.Merge(ref_wrk, ref_merged)
    
    
    # Create Buffer at Required Distance
    logger.info(f"Creating buffer at {min_distance}")

    ref_buffer = os.path.join(working_gdb, "ref_buffer")
    arcpy.analysis.Buffer(
        ref_merged,
        ref_buffer,
        min_distance,
        dissolve_option="ALL"
    )

    # Convert Buffer to Boundary Line
    logger.info("Extracting buffer boundary")

    buffer_boundary = os.path.join(working_gdb, "buffer_boundary")
    arcpy.management.PolygonToLine(ref_buffer, buffer_boundary)

    # Merge Move Feature Classes
    logger.info("Merging features to move")

    move_merged = os.path.join(working_gdb, "move_merged")
    arcpy.management.Merge(move_wrk, move_merged)

    # Select Only Features Violating Distance
    logger.info("Selecting features inside buffer")

    arcpy.management.MakeFeatureLayer(move_merged, "move_lyr")

    arcpy.management.SelectLayerByLocation(
        "move_lyr",
        "INTERSECT",
        ref_buffer
    )
    # Near Analysis to Buffer Boundary
    logger.info("Running Near analysis")

    arcpy.analysis.Near(
        "move_lyr",
        buffer_boundary,
        location="LOCATION"
    )

    # Move Features (Preserve Geometry)
    logger.info("Moving geometries")

    with arcpy.da.UpdateCursor(
        "move_lyr",
        ["OID@", "SHAPE@", "NEAR_X", "NEAR_Y"]
    ) as cursor:

        for oid, shape, nx, ny in cursor:
            if nx is None or ny is None:
                continue

            if shape.type == "polygon":
                ref_pt = shape.centroid
            else:
                ref_pt = shape

            dx = nx - ref_pt.X
            dy = ny - ref_pt.Y

            new_shape = shape.move(dx, dy)
            cursor.updateRow([oid, new_shape, nx, ny])

    # Split Moved Results by Geometry Type
    logger.info("Separating moved features by geometry")

    moved_geom_dict = {}
    with arcpy.da.SearchCursor(
        move_merged,
        ["SRC_FC", "SRC_OID", "SHAPE@"]
    ) as cursor:
        for src_fc, src_oid, geom in cursor:
            moved_geom_dict[(src_fc, src_oid)] = geom

    # Replace Geometry in Original Feature Classes
    logger.info("Updating original feature classes")

    for fc in to_move_original_fcs:
        desc = arcpy.Describe(fc)
        fc_name = desc.baseName
        with arcpy.da.UpdateCursor(fc, ["OID@", "SHAPE@"]) as uc:
            for oid, shape in uc:
                key = (fc_name, oid)
                if key in moved_geom_dict:
                    uc.updateRow([oid, moved_geom_dict[key]])
    return None


def extend_cemetery_with_road_river(
    cemetery,              # Cemetery layer that needs to be fixed
    road,       # extend layer with which to fix cemetery
    gdb):

    arcpy.env.overwriteOutput = True
    
    distance_m=20.0
    prefix_base="BH0010_fix"
    # ----------------------------
    # Inputs (dynamic)
    # ----------------------------
    dist_txt = f"{distance_m} Meters"

    # Unique suffix so repeated runs do not collide
    ts = _dt.datetime.now().strftime("%Y%m%d_%H%M%S")
    prefix = f"{prefix_base}_{ts}"

    # ----------------------------
    # Output / intermediate paths
    # ----------------------------
    road_buffer_fc = os.path.join(gdb, f"{prefix}_Road_Buffer")

    # Working copies 
    cem_work_fc = os.path.join(gdb, f"{prefix}_Cemetery_WORK")  # copy of entire cemetery
    cem_sel_fc = os.path.join(gdb, f"{prefix}_Cemetery_SEL")    # selected (within buffer) copy
    cem_line_fc = os.path.join(gdb, f"{prefix}_Cemeter_FeatureToLine")
    cem_poly_fc = os.path.join(gdb, f"{prefix}_Cemeter_FeatureToPoly")
    sj_fc = os.path.join(gdb, f"{prefix}_Cemeter_SpatialJoin")
    merge_fc = os.path.join(gdb, f"{prefix}_Cemeter_Merge_FINAL")

    # Backup 
    cem_backup_fc = os.path.join(gdb, f"{prefix}_Cemetery_BACKUP")

    arcpy.AddMessage("Starting safe run...")
    arcpy.AddMessage("Creating backup copy of cemetery...")
    arcpy.management.CopyFeatures(cemetery, cem_backup_fc)

    arcpy.AddMessage("Creating full working copy of cemetery...")
    arcpy.management.CopyFeatures(cemetery, cem_work_fc)

    # ----------------------------
    # STEP 1: Buffer road
    # ----------------------------
    arcpy.analysis.Buffer(
        in_features=road,
        out_feature_class=road_buffer_fc,
        buffer_distance_or_field=dist_txt,
        line_side="FULL",
        line_end_type="ROUND",
        dissolve_option="NONE",
        dissolve_field=None,
        method="PLANAR"
    )
    arcpy.AddMessage(f"Layer buffer created: {road_buffer_fc}")

    # ----------------------------
    # STEP 2: Select cemetery within buffer
    # ----------------------------
    cem_lyr = arcpy.management.MakeFeatureLayer(cemetery, f"{prefix}_cem_lyr")
    arcpy.management.SelectLayerByLocation(
        in_layer=cem_lyr,
        overlap_type="INTERSECT",
        select_features=road_buffer_fc,
        search_distance=None,
        selection_type="NEW_SELECTION",
        invert_spatial_relationship="NOT_INVERT"
    )
    sel_count = int(arcpy.management.GetCount(cem_lyr)[0])
    arcpy.AddMessage(f"Cemetery selected within {dist_txt}: {sel_count}")

    if sel_count>0:
        # Copy selected to a separate FC (so downstream tools are bounded to only what you intended)
        arcpy.management.CopyFeatures(cem_lyr, cem_sel_fc)

        # ----------------------------
        # STEP 3: Snap selected cemetery (on selected copy, not on original)
        # ----------------------------

        snap_env = [
        [road, "VERTEX", dist_txt], 
        [road, "EDGE", dist_txt]
        ]
        arcpy.edit.Snap(cem_sel_fc, snap_env)
        arcpy.AddMessage("Selected cemetery snapped")

        # ----------------------------
        # STEP 4: FeatureToLine (from selected copy)
        # ----------------------------
        arcpy.management.FeatureToLine(
            in_features=cem_sel_fc,
            out_feature_class=cem_line_fc,
            cluster_tolerance=None,
            attributes="ATTRIBUTES"
        )
        arcpy.AddMessage(f"Selected cemetery converted to line: {cem_line_fc}")

        # ----------------------------
        # STEP 5: AlignFeatures 
        # ----------------------------
        arcpy.edit.AlignFeatures(
            in_features=cem_line_fc,
            target_features=road,
            search_distance=dist_txt,
            match_fields=None
        )
        arcpy.AddMessage("Line cemetery aligned to extending layer")

        # ----------------------------
        # STEP 6: FeatureToPolygon
        # ----------------------------
        arcpy.management.FeatureToPolygon(
            in_features=cem_line_fc,
            out_feature_class=cem_poly_fc,
            cluster_tolerance=None,
            attributes="ATTRIBUTES",
            label_features=None
        )
        arcpy.AddMessage(f"Line converted to polygon: {cem_poly_fc}")

        # ----------------------------
        # STEP 7: Snap polygon again (vertex)
        # ----------------------------
        snap_env_poly = [
        [road, "VERTEX", dist_txt]
        ]

        arcpy.edit.Snap(cem_poly_fc, snap_env_poly)
        arcpy.AddMessage("Polygon snapped again to extending layer")

        # ----------------------------
        # STEP 8: SpatialJoin 
        # ----------------------------
        arcpy.analysis.SpatialJoin(
            target_features=cem_poly_fc,
            join_features=cem_sel_fc,  # join from selected original subset 
            out_feature_class=sj_fc,
            join_operation="JOIN_ONE_TO_ONE",
            join_type="KEEP_ALL",
            match_option="HAVE_THEIR_CENTER_IN",
            search_radius=None,
            distance_field_name="",
            match_fields=None
        )
        arcpy.AddMessage(f"Spatial join done: {sj_fc}")

        # Safety check (non-destructive): ensure the join actually matched
        # If Join_Count is 0 for any row, attributes can become NULL/Unknown.
        zero_join = 0
        with arcpy.da.SearchCursor(sj_fc, ["Join_Count"]) as cur:
            for (jc,) in cur:
                if jc == 0:
                    zero_join += 1
        arcpy.AddMessage(f"SpatialJoin Join_Count=0 rows: {zero_join}")

        # Now delete extra fields added by SpatialJoin
        arcpy.management.DeleteField(
            in_table=sj_fc,
            drop_field="Join_Count;TARGET_FID",
            method="DELETE_FIELDS"
        )
        arcpy.AddMessage("Extra fields deleted from SpatialJoin output")

        # ----------------------------
        # STEP 9: Delete matching features from WORKING cemetery copy (not the original)
        # This preserves your process, but avoids destructive edits on the real layer mid-run.
        # ----------------------------
        cem_work_lyr = arcpy.management.MakeFeatureLayer(cem_work_fc, f"{prefix}_cem_work_lyr")

        arcpy.management.SelectLayerByLocation(
            in_layer=cem_work_lyr,
            overlap_type="HAVE_THEIR_CENTER_IN",
            select_features=sj_fc,
            search_distance=None,
            selection_type="NEW_SELECTION",
            invert_spatial_relationship="NOT_INVERT"
        )
        del_count = int(arcpy.management.GetCount(cem_work_lyr)[0])
        arcpy.AddMessage(f"Features to delete from WORK copy: {del_count}")

        arcpy.management.DeleteFeatures(cem_work_lyr)
        arcpy.AddMessage("Deleted selected features from WORK copy")

        arcpy.management.SelectLayerByAttribute(
            in_layer_or_view=cem_work_lyr,
            selection_type="CLEAR_SELECTION"
        )
        arcpy.AddMessage("Selection cleared for WORK copy")

        # ----------------------------
        # STEP 10: Merge WORK remainder + SpatialJoin output 
        # ----------------------------
        arcpy.management.Merge(
            inputs=f"{cem_work_fc};{sj_fc}",
            output=merge_fc,
            field_mappings=None,
            add_source="NO_SOURCE_INFO",
            field_match_mode="USE_FIRST_SCHEMA"
        )
        arcpy.AddMessage(f"Merged into final output: {merge_fc}")

        # ----------------------------
        # STEP 11: Update the ORIGINAL cemetery layer at the very end, inside a transaction
        # If anything fails here, edits are rolled back.
        # ----------------------------
        arcpy.AddMessage("Updating original cemetery layer inside a single edit transaction...")

        editor = arcpy.da.Editor(gdb)
        editor.startEditing(False, True)  # False=not multiuser mode; True=with undo (works well for file gdb)
        editor.startOperation()

        try:
            # Delete all from original cemetery layer 
            arcpy.management.DeleteFeatures(cemetery)

            # Append merged output back to original cemetery layer
            arcpy.management.Append(
                inputs=merge_fc,
                target=cemetery,
                schema_type="NO_TEST",
                field_mapping=None,
                subtype="",
                expression="",
                match_fields=None,
                update_geometry="NOT_UPDATE_GEOMETRY",
                enforce_domains="NO_ENFORCE_DOMAINS",
                feature_service_mode="USE_FEATURE_SERVICE_MODE"
            )

            editor.stopOperation()
            editor.stopEditing(True)  # commit
            arcpy.AddMessage("Append completed. Process finished safely.")

        except Exception as ex:
            # Rollback in-transaction edits
            editor.abortOperation()
            editor.stopEditing(False)  # discard
            arcpy.AddMessage("ERROR occurred; all edits were rolled back. Original layer remains unchanged.")
            arcpy.AddMessage(f"Exception: {ex}")
            raise

        arcpy.AddMessage(f"Backup created at: {cem_backup_fc}")
        arcpy.AddMessage(f"Final merged output: {merge_fc}")

    else:
        arcpy.AddMessage(f"No cemetery features found within {dist_txt} meter of the road. Skipping the process and going to next step...")


def calculate_poly_angle(p1, p2, p3):
    v1 = (p1.X - p2.X, p1.Y - p2.Y)
    v2 = (p3.X - p2.X, p3.Y - p2.Y)

    dot = v1[0] * v2[0] + v1[1] * v2[1]
    mag1 = math.hypot(v1[0], v1[1])
    mag2 = math.hypot(v2[0], v2[1])

    cosang = dot / (mag1 * mag2)
    cosang = max(-1, min(1, cosang))
    return math.degrees(math.acos(cosang))


def count_true_angles(points, tolerance=5):
    """
    tolerance = degrees from 180 considered 'straight'
    """
    true_angles = 0

    for i in range(len(points)):
        p1 = points[i - 1]
        p2 = points[i]
        p3 = points[(i + 1) % len(points)]

        ang = calculate_poly_angle(p1, p2, p3)

        # ignore nearly straight angles
        if abs(ang - 180) > tolerance:
            true_angles += 1

    return true_angles


def get_polygon_oids_with_four_angles(fc):
    four_angle_oids = set()
    with arcpy.da.SearchCursor(fc, ["OID@", "SHAPE@"]) as cursor:
        for oid, geom in cursor:
            for part in geom:
                points = [p for p in part if p]

                # remove closing point
                if points[0].equals(points[-1]):
                    points = points[:-1]

                angle_count = count_true_angles(points)

                if angle_count == 4:
                    four_angle_oids.add(oid)
    four_angle_oids = f"({','.join(map(str, four_angle_oids))})"
    return four_angle_oids
# end function for identify_polygon_oids_with_four_angles


# function for enlarge polygon from all side
def get_edge_lengths(polygon):
    lengths = []
    for part in polygon:
        for i in range(len(part) - 1):
            p1 = part[i]
            p2 = part[i + 1]
            if p1 and p2:
                length = math.hypot(p2.X - p1.X, p2.Y - p1.Y)
                lengths.append(length)
    return lengths


def enlarge_polygon_side(fc, TARGET_LENGTH):
    with arcpy.da.UpdateCursor(fc, ["SHAPE@"]) as cursor:
        for row in cursor:
            geom = row[0]

            # Get all edge lengths
            edge_lengths = get_edge_lengths(geom)

            if not edge_lengths:
                continue

            shortest_edge = min(edge_lengths)
            # Only scale if under 35 meters
            if shortest_edge < TARGET_LENGTH:
                scale_ratio = TARGET_LENGTH / shortest_edge
                center = geom.centroid
                scaled_geom = geom.scale(center, scale_ratio, scale_ratio)
                row[0] = scaled_geom
                cursor.updateRow(row)
    arcpy.management.RepairGeometry(in_features=fc, delete_null="DELETE_NULL", validation_method="ESRI")


# end of function for enlarge polygon from all side

def main_enlarge_building_polygon_side(primary_polygon_fc, tolerance, working_gdb):
    simplify_building_polygons = arcpy.cartography.SimplifyBuilding(in_features=primary_polygon_fc,out_feature_class=rf"{working_gdb}\SimplifyBuild",simplification_tolerance=f"{tolerance} Meters",
                                                                    minimum_area="0 SquareMeters",conflict_option="NO_CHECK",in_barriers=None,collapsed_point_option="NO_KEEP")
    arcpy.management.DeleteFeatures(primary_polygon_fc)
    arcpy.management.Append(simplify_building_polygons, primary_polygon_fc, "NO_TEST")
    polygon_ids = get_polygon_oids_with_four_angles(primary_polygon_fc)
    if len(polygon_ids) != 0:
        # for exact 4 angles polygon
        polygon_with_four_angles=arcpy.management.MakeFeatureLayer(in_features=primary_polygon_fc, out_layer="polygon_with_four_angles", where_clause=f"OBJECTID IN {polygon_ids}")
        primary_fc_minimumbound = arcpy.management.MinimumBoundingGeometry(in_features=polygon_with_four_angles,out_feature_class=rf"{working_gdb}\Polygons_MinimumBoundi",
                                                                           geometry_type="RECTANGLE_BY_AREA",group_option="NONE", group_field=None,mbg_fields_option="NO_MBG_FIELDS")
        enlarge_polygon_side(primary_fc_minimumbound, tolerance)
        selected_primary_polygon_fc = arcpy.management.SelectLayerByAttribute(in_layer_or_view=primary_polygon_fc,selection_type="NEW_SELECTION",where_clause=f"OBJECTID IN {polygon_ids}",
                                                                              invert_where_clause=None)
        arcpy.management.DeleteFeatures(selected_primary_polygon_fc)
        arcpy.management.Append(primary_fc_minimumbound, primary_polygon_fc, "NO_TEST")

def terrace_buildings_to_builtup_area_(fc_list, building_fc_name, road_fc_name, built_up_fc_name, working_gdb, field_name="RET"):
    building_fc = resolve_fc_from_fc_list(building_fc_name, fc_list)
    road_fc = resolve_fc_from_fc_list(road_fc_name, fc_list)
    built_up_fc = resolve_fc_from_fc_list(built_up_fc_name, fc_list)
    terrace_fc = arcpy.management.SelectLayerByAttribute(building_fc, "NEW_SELECTION", f"{field_name} = 3")
    
    # Aggreate selected terrace houses
    aggregated_terrace_houses = arcpy.cartography.AggregatePolygons(in_features=terrace_fc, out_feature_class=f"{working_gdb}\\aggregated_terrace_houses", aggregation_distance="60 Meters", orthogonality_option="ORTHOGONAL")

    # Make feature layer
    area_field = arcpy.da.Describe(aggregated_terrace_houses)['areaFieldName']
    selected_aggregate_features = arcpy.conversion.ExportFeatures(aggregated_terrace_houses, f"{working_gdb}\\selected_aggregate_features", f"{area_field} > 8600")

    
    for row in arcpy.da.SearchCursor(selected_aggregate_features, ["SHAPE@", "OID@"]):
        geom = row[0]
        oid = row[1]
        terrace_fc = arcpy.management.SelectLayerByLocation(building_fc, "WITHIN", geom, None, "NEW_SELECTION")
        # Dissolved selected terrace house
        dissolved_terrace_house = arcpy.analysis.PairwiseDissolve(terrace_fc, f"{working_gdb}\\dissolved_terrace_house")
        # Select road feature 
        selected_road_fc = arcpy.management.SelectLayerByLocation(road_fc, "WITHIN_A_DISTANCE", dissolved_terrace_house, "25 Meters", "NEW_SELECTION")
        arcpy.AddMessage(f"Selected road features count: {count_features(selected_road_fc)}")
        # Dissolved selected road feature
        if count_features(selected_road_fc) > 0:
            arcpy.AddMessage(f"Object ID: {oid}")
            dissolved_road_feature = arcpy.analysis.PairwiseDissolve(selected_road_fc, f"{working_gdb}\\dissolved_road_feature_{oid}")
            # Buffer the dissolved road
            road_buffer_fc = arcpy.analysis.Buffer(dissolved_road_feature, f"{working_gdb}\\road_buffer_fc_{oid}", "50 Meters","FULL","FLAT","ALL", None,"PLANAR")
            # Convert polygon to line
            buffer_poly_to_line = arcpy.management.PolygonToLine(road_buffer_fc,f"{working_gdb}\\buffer_poly_to_line_{oid}", "IDENTIFY_NEIGHBORS")
            # Merge buffer polygon and dissolved road feature
            merged_road_fc = arcpy.management.Merge([dissolved_road_feature, buffer_poly_to_line], f"{working_gdb}\\merged_road_fc_{oid}")
            # Split the road feature
            splitted_road_fc = arcpy.management.SplitLine(merged_road_fc, f"{working_gdb}\\splitted_road_fc_{oid}")
            # Create convex hull polygon feature
            convex_hull_fc_road = arcpy.management.MinimumBoundingGeometry(dissolved_road_feature, f"{working_gdb}\\convex_hull_fc_road_{oid}", "CONVEX_HULL", "ALL", None, "NO_MBG_FIELDS")
            # Select splitted lines by convex hull
            selected_splitted_road_fc = arcpy.management.SelectLayerByLocation(splitted_road_fc, "INTERSECT", convex_hull_fc_road, None, "NEW_SELECTION")
            # Export the selected features
            exported_selected_split_features = arcpy.conversion.ExportFeatures(selected_splitted_road_fc, f"{working_gdb}\\exported_selected_split_features_{oid}")
            # Extend line to near line
            arcpy.edit.ExtendLine(exported_selected_split_features, "20 Meters", "EXTENSION")
            # Line to polygon
            split_line_fc_to_poly = arcpy.management.FeatureToPolygon(exported_selected_split_features, f"{working_gdb}\\split_line_fc_to_poly_{oid}", None, "ATTRIBUTES", None)
            # Snapping to remove gap
            arcpy.edit.Snap(exported_selected_split_features, [[split_line_fc_to_poly, "VERTEX", "60 Meters"]])
            # Convert line to polygon
            polygon_from_lines = arcpy.management.FeatureToPolygon(exported_selected_split_features, f"{working_gdb}\\polygon_from_lines_{oid}", None, "ATTRIBUTES", None)
            # Dissolved created polygon
            dissolved_polygon_from_lines = arcpy.analysis.PairwiseDissolve(polygon_from_lines, f"{working_gdb}\\dissolved_polygon_from_lines_{oid}")
            # Simplify polygon
            simplify_building = arcpy.cartography.SimplifyPolygon(dissolved_polygon_from_lines, f"{working_gdb}\\simplified_polygon_{oid}", "BEND_SIMPLIFY", "30 Meters")
            # Select buildings within simplified polygon
            selected_build_up_bldg = arcpy.management.SelectLayerByLocation(building_fc, "WITHIN", simplify_building, None, "NEW_SELECTION")
            # Delete selected buildings
            arcpy.management.DeleteFeatures(selected_build_up_bldg)
            # Append simplified polygon to built-up area
            arcpy.management.Append(simplify_building, built_up_fc, "NO_TEST")



# # Builtup Generalization
def gen_buildup(fc_list, small_bldg_2_point_a, small_bldg_2_point_p, working_gdb, features_in_cemetery, enlarge_barrier_fcs, delete_small_bldgs,  enlarge_building_features,   
                  in_buildings_list, edge_features_list, in_feature_loc, delete_small_features, val_dict, logger, map_name):
    arcpy.AddMessage('Starting buildup features generalization.....')
    # Set the workspace
    arcpy.env.overwriteOutput = True
    dynamic_fc_names = resolve_lyr()
    try:
        # Convert small building to point
        convert_small_bldg_2_point(fc_list, small_bldg_2_point_a, small_bldg_2_point_p, val_dict['Built_min_size_bldg1'], val_dict['Built_delete_input'], 
                                   val_dict['Built_create_one_point'], val_dict['Built_unique_field'], working_gdb)
        # Delete buildings in Cemetery
        features_in_cemetery = list(filter(str.strip, features_in_cemetery))
        features_in_cemetery = [fc for a_lyr in features_in_cemetery for fc in fc_list if str(a_lyr) in fc]
        cemetery = [fc for fc in fc_list if dynamic_fc_names.Cemetery_A in fc][0]
        delete_features_in_poly(features_in_cemetery, cemetery, val_dict['Built_min_size_bldg2'])
        # Enlarge builtup Features (Cemetery)
        enlarge_barrier_fcs = list(filter(str.strip, enlarge_barrier_fcs))
        enlarge_barrier_fcs = [fc for a_lyr in enlarge_barrier_fcs for fc in fc_list if str(a_lyr) in fc]
        enlarge_polygon_barrier(cemetery, None, None, val_dict['Built_enlarge_min_size'], val_dict['Built_enlarge_val'], enlarge_barrier_fcs, working_gdb)

        #Enlarge cemetery features to road and river
        road = [fc for fc in fc_list if dynamic_fc_names.Road_L in fc][0]
        river = [fc for fc in fc_list if dynamic_fc_names.River_Bank_L in fc][0]

        extend_cemetery_with_road_river(cemetery, road, working_gdb)
        extend_cemetery_with_road_river(cemetery, river, working_gdb)

        # Delete small buildings
        delete_small_building(fc_list, delete_small_bldgs, val_dict['Built_del_min_area'])
        # Enlarge small buildings
        enlarge_building_features = list(filter(str.strip, enlarge_building_features))
        enlarge_building_features = [fc for a_lyr in enlarge_building_features for fc in fc_list if str(a_lyr) in fc]
        #extend_polygon_sides(enlarge_building_features, working_gdb, enlarge_bldg_min_width, enlarge_bldg_min_length, enlarge_bldg_additional_criteria, simplification_tolerance)
        # Simplify buildings
        for polygon_fc in enlarge_building_features:
            if has_features(polygon_fc):
                simplify_buildings(polygon_fc, val_dict['Built_simpl_bldg_distance'], working_gdb)

       

        current_working_dir = os.getcwd()
        dlpk_path = os.path.join(current_working_dir, "building_ft_identifier_v1.dlpk")
        road_fc = [fc for fc in fc_list if dynamic_fc_names.Road_L in fc][0]
        Residential_Building_A = [fc for fc in fc_list if dynamic_fc_names.Residential_Building_A in fc][0]
        Town_Built_up_A = [fc for fc in fc_list if dynamic_fc_names.Town_Built_up_A in fc][0]
        Residential_Building_P = [fc for fc in fc_list if dynamic_fc_names.Residential_Building_P in fc][0]

        arcpy.AddMessage(f"{val_dict['Built_townbuiltup_generator_mode']} Started")
        if val_dict['Built_townbuiltup_generator_mode'] == "Default Mode":
            # # Delineaate town built-Up Areas
            delineate_built_up_area(fc_list, in_buildings_list, edge_features_list, val_dict['Built_delineate_grp_dist'], 
                                    val_dict['Built_delineate_min_detail_size'], val_dict['Built_delineate_min_bldg_count'], 
                                    working_gdb, val_dict['Built_delineate_ref_scale'], val_dict['Built_townbuiltup_min_area'])
            area_based_delete(Town_Built_up_A, val_dict['Built_townbuiltup_min_area'])
        if val_dict['Built_townbuiltup_generator_mode'] == "AI Mode":
            arcpy.AddMessage(f"Using deep learning package: {dlpk_path}")
            terrace_buildings_to_builtup_area(Residential_Building_P, road_fc, Residential_Building_A, Town_Built_up_A, working_gdb, dlpk_path, val_dict['Built_townbuiltup_min_area'])
            area_based_delete(Town_Built_up_A, val_dict['Built_townbuiltup_min_area'])
        if val_dict['Built_townbuiltup_generator_mode'] == "Hybrid Mode":
            # # Delineaate town built-Up Areas
            arcpy.AddMessage(f"Using deep learning package: {dlpk_path}")
            terrace_buildings_to_builtup_area(Residential_Building_P, road_fc, Residential_Building_A, Town_Built_up_A, working_gdb, dlpk_path, val_dict['Built_townbuiltup_min_area'])
            delineate_built_up_area(fc_list, in_buildings_list, edge_features_list, val_dict['Built_delineate_grp_dist'], 
                                    val_dict['Built_delineate_min_detail_size'], val_dict['Built_delineate_min_bldg_count'], 
                                    working_gdb, val_dict['Built_delineate_ref_scale'], val_dict['Built_townbuiltup_min_area'])
            
            area_based_delete(Town_Built_up_A, val_dict['Built_townbuiltup_min_area'])
            



        
        # Generalised Buildings
        generalised_buildings(fc_list, val_dict['Built_general_min_area'])
        
        # Delete small features (Swimming)
        recreation = [fc for fc in fc_list if dynamic_fc_names.Swimming_Pool_A in fc][0] ## edited
        delete_small_features = list(filter(str.strip, delete_small_features))
        delete_small_features = [fc for a_lyr in delete_small_features for fc in fc_list if str(a_lyr) in fc]
        remove_by_converting(recreation, delete_small_features, val_dict['Built_del_small_recreation_min_size'], None, working_gdb)
        # Erase vagetaton
        erase_polygons_by_replace(cemetery, delete_small_features, val_dict['Built_erase_sql'], working_gdb)
        pond = [fc for fc in fc_list if dynamic_fc_names.Pond_A in fc][0]
        fence = [fc for fc in fc_list if dynamic_fc_names.Fence_L in fc][0]
        lake = [fc for fc in fc_list if dynamic_fc_names.Lake_A in fc][0]
        
        # Resolve fence for pond, lake and swimming pool
        resolve_fence(pond, fence, working_gdb)
        resolve_fence(lake, fence, working_gdb)
        resolve_fence(recreation, fence, working_gdb)

        # Fix Conflict Between Fence and Road / Track
        road_fc = [fc for fc in fc_list if dynamic_fc_names.Road_L in fc][0]
        track_fc = [fc for fc in fc_list if dynamic_fc_names.Track_L in fc][0]
        # # Fence Feature Class
        fence_fc = [fc for fc in fc_list if dynamic_fc_names.Fence_L in fc][0]
        # # Wall Feature Class
        wall_fc = [fc for fc in fc_list if dynamic_fc_names.Wall_L in fc][0]

        fence_road_distance_rules={1: 77.8, 2: 67.8, 3: 77.8, 4: 67.8, 5: 62.8, 6: 65.3}
        fence_track_distance_rules={1: 36.3, 2: 31.3}
        fix_wall_fence_conflict_with_road(road_fc, track_fc, fence_fc, fence_road_distance_rules, fence_track_distance_rules, working_gdb, logger,  
                                          val_dict['Built_fix_wall_fence_road_class_field'], val_dict['Built_fix_wall_fence_track_class_field'])

        wall_road_distance_rules={1: 82.8, 2: 72.8, 3: 82.8, 4: 72.8, 5: 67.8, 6: 70.3}
        wall_track_distance_rules={1: 41.3, 2: 36.3}
        fix_wall_fence_conflict_with_road(road_fc, track_fc, wall_fc, wall_road_distance_rules, wall_track_distance_rules, working_gdb, logger, 
                                          val_dict['Built_fix_wall_fence_road_class_field'], val_dict['Built_fix_wall_fence_track_class_field'])
        # # Merge Buildings that are too close between Buildings and Street
        merge_buildings_too_closed_between_building_and_street(dynamic_fc_names.Road_L, dynamic_fc_names.Residential_Building_A, fc_list, working_gdb, logger)
        # # Align State Boundary in Reference to River Bank Line 
        align_feature_with_reference_fc(dynamic_fc_names.State_Coverage_L, dynamic_fc_names.River_Bank_L, fc_list, working_gdb, logger)
        # Move Buildings in accordance with Historical Sites
        move_feature_1_around_feature_2_to_specific_distance(fc_list, 
                                                             [dynamic_fc_names.Historical_Site_A], 
                                                             [dynamic_fc_names.Residential_Building_A, dynamic_fc_names.Residential_Building_P], 
                                                             working_gdb, logger, min_distance = val_dict['Built_move_feature_around_feature_minimum_distance'])
        residential_building_polygon = [fc for fc in fc_list if dynamic_fc_names.Residential_Building_A in fc][0]
        residential_building_side_tolerance = 35
        
        if has_features(residential_building_polygon):
            main_enlarge_building_polygon_side(residential_building_polygon, residential_building_side_tolerance, working_gdb)

        #Apply defrinition query to building_P layers for hiding building points that doesn't have any name. 
        apply_layer_definition (small_bldg_2_point_p, val_dict['Builtup_Apply_Layer_Definition_expression'] , map_name)

    except Exception as e:
        exc_type, exc_value, exc_traceback = sys.exc_info()
        tb = traceback.format_exc()
        error_message = f"Built-Up Area Generalisation error: {e}\nTraceback details:\n{tb}"
        arcpy.AddError(error_message)
        logger.error(error_message)
        simplified_msgs('Built-Up Area Generalisation', f'{exc_value}\n')