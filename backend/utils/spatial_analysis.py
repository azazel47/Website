import geopandas as gpd
import pandas as pd
from shapely.geometry import Point, Polygon
from typing import List, Dict, Tuple, Optional
import logging

logger = logging.getLogger(__name__)

def create_point_geodataframe(coordinates: List[Dict], crs: str = "EPSG:4326") -> gpd.GeoDataFrame:
    """
    Create a GeoDataFrame of points from a list of coordinates.

    Args:
        coordinates: List of dictionaries with 'id', 'longitude', 'latitude'
        crs: Coordinate reference system (default: EPSG:4326)

    Returns:
        GeoDataFrame with point geometries
    """
    df = pd.DataFrame(coordinates)
    geometry = [Point(row['longitude'], row['latitude']) for _, row in df.iterrows()]
    gdf = gpd.GeoDataFrame(df, geometry=geometry, crs=crs)
    return gdf

def create_polygon_geodataframe(coordinates: List[Dict], crs: str = "EPSG:4326") -> gpd.GeoDataFrame:
    """
    Create a GeoDataFrame with a single polygon from a list of coordinates.

    Args:
        coordinates: List of dictionaries with 'longitude', 'latitude'
        crs: Coordinate reference system (default: EPSG:4326)

    Returns:
        GeoDataFrame with polygon geometry
    """
    coords = [(c['longitude'], c['latitude']) for c in coordinates]

    # Ensure polygon is closed (first and last coordinate are the same)
    if coords and coords[0] != coords[-1]:
        coords.append(coords[0])

    geometry = [Polygon(coords)]
    gdf = gpd.GeoDataFrame(
        pd.DataFrame({"id": ["polygon_1"]}),
        geometry=geometry,
        crs=crs
    )
    return gdf

def analyze_point_overlap(gdf: gpd.GeoDataFrame, kkprl_gdf: gpd.GeoDataFrame) -> Dict:
    """
    Analyze overlap between points and KKPRL polygons using spatial join.

    Args:
        gdf: GeoDataFrame containing points
        kkprl_gdf: GeoDataFrame containing KKPRL polygons

    Returns:
        Dictionary with overlap analysis results
    """
    try:
        # Select relevant columns from KKPRL
        kkprl_subset = kkprl_gdf[["NO_KKPRL", "NAMA_SUBJ", "KEGIATAN", "PROVINSI", "LUAS_HA", "geometry"]].copy()

        # Perform spatial join
        joined = gpd.sjoin(gdf, kkprl_subset, how='left', predicate='within')

        # Find points that overlap
        points_in_kkprl = joined[joined['index_right'].notna()]

        overlap_count = len(points_in_kkprl)
        has_overlap = overlap_count > 0

        overlap_details = []
        if has_overlap:
            # Group by KKPRL to get unique overlapping areas
            for _, row in points_in_kkprl.iterrows():
                overlap_details.append({
                    "point_id": row.get('id', 'Unknown'),
                    "no_kkprl": row.get('NO_KKPRL', 'N/A'),
                    "nama_subj": row.get('NAMA_SUBJ', 'N/A'),
                    "kegiatan": row.get('KEGIATAN', 'N/A'),
                    "provinsi": row.get('PROVINSI', 'N/A'),
                    "luas_ha": row.get('LUAS_HA', 0)
                })

        # Get unique NAMA_SUBJ for summary message
        unique_subjects = points_in_kkprl['NAMA_SUBJ'].dropna().unique().tolist() if has_overlap else []

        return {
            "has_overlap": has_overlap,
            "overlap_count": overlap_count,
            "total_points": len(gdf),
            "unique_subjects": unique_subjects,
            "overlap_details": overlap_details,
            "message": f"{overlap_count} titik overlap dengan KKPRL terbit" if has_overlap else "Tidak ada titik yang overlap dengan KKPRL terbit"
        }

    except Exception as e:
        logger.error(f"Error in point overlap analysis: {e}")
        return {
            "has_overlap": False,
            "error": str(e),
            "message": "Error during overlap analysis"
        }

def analyze_polygon_overlap(gdf: gpd.GeoDataFrame, kkprl_gdf: gpd.GeoDataFrame) -> Dict:
    """
    Analyze overlap between polygon and KKPRL polygons using overlay.

    Args:
        gdf: GeoDataFrame containing a polygon
        kkprl_gdf: GeoDataFrame containing KKPRL polygons

    Returns:
        Dictionary with overlap analysis results
    """
    try:
        # Select relevant columns from KKPRL
        kkprl_subset = kkprl_gdf[["NO_KKPRL", "NAMA_SUBJ", "KEGIATAN", "PROVINSI", "LUAS_HA", "geometry"]].copy()

        # Perform overlay intersection
        overlay_result = gpd.overlay(gdf, kkprl_subset, how='intersection')

        has_overlap = not overlay_result.empty
        overlap_count = len(overlay_result)

        overlap_details = []
        if has_overlap:
            for _, row in overlay_result.iterrows():
                overlap_details.append({
                    "no_kkprl": row.get('NO_KKPRL', 'N/A'),
                    "nama_subj": row.get('NAMA_SUBJ', 'N/A'),
                    "kegiatan": row.get('KEGIATAN', 'N/A'),
                    "provinsi": row.get('PROVINSI', 'N/A'),
                    "luas_ha": row.get('LUAS_HA', 0),
                    "intersection_area_m2": row.geometry.area if hasattr(row, 'geometry') else 0
                })

        # Get unique NAMA_SUBJ for summary message
        unique_subjects = overlay_result['NAMA_SUBJ'].dropna().unique().tolist() if has_overlap else []

        return {
            "has_overlap": has_overlap,
            "overlap_count": overlap_count,
            "unique_subjects": unique_subjects,
            "overlap_details": overlap_details,
            "message": f"Poligon overlap dengan {overlap_count} KKPRL terbit" if has_overlap else "Poligon tidak overlap dengan KKPRL terbit"
        }

    except Exception as e:
        logger.error(f"Error in polygon overlap analysis: {e}")
        return {
            "has_overlap": False,
            "error": str(e),
            "message": "Error during overlap analysis"
        }

def analyze_overlap_12mil_safe(gdf: gpd.GeoDataFrame, mil12_gdf: gpd.GeoDataFrame) -> dict:
    """
    Analisis apakah titik/poligon berada di dalam atau bersinggungan dengan batas 12 mil laut.
    Fungsi ini otomatis menyesuaikan CRS dan memperbaiki geometri invalid.

    Args:
        gdf: GeoDataFrame titik atau poligon yang akan dicek
        mil12_gdf: GeoDataFrame polygon 12 mil dengan kolom 'WP'

    Returns:
        Dictionary dengan status overlap dan daftar 'WP' jika overlap
    """
    try:
        # 1️⃣ Samakan CRS
        if gdf.crs != mil12_gdf.crs:
            mil12_gdf = mil12_gdf.to_crs(gdf.crs)

        # 2️⃣ Perbaiki geometri invalid
        mil12_gdf["geometry"] = mil12_gdf["geometry"].buffer(0)
        gdf["geometry"] = gdf["geometry"].buffer(0)

        # 3️⃣ Pastikan kolom 'WP' ada
        if "WP" not in mil12_gdf.columns:
            mil12_gdf["WP"] = "Unknown"

        # 4️⃣ Spatial join menggunakan 'intersects'
        joined = gpd.sjoin(
            gdf,
            mil12_gdf[["WP", "geometry"]],
            how="left",
            predicate="intersects"
        )

        # 5️⃣ Ambil yang overlap
        overlaps = joined[joined["index_right"].notna()]

        if overlaps.empty:
            return {"has_overlap": False, "message": "Berada di luar 12 mil laut"}

        wp_list = overlaps["WP"].dropna().unique().tolist()
        return {
            "has_overlap": True,
            "wp_list": wp_list,
            "message": f"Berada di dalam 12 mil laut Provinsi: {', '.join(wp_list)}"
        }

    except Exception as e:
        return {"has_overlap": False, "message": f"Error: {str(e)}"}


def analyze_overlap_kawasan(gdf: gpd.GeoDataFrame, kawasan_gdf: gpd.GeoDataFrame) -> dict:
    """
    Analisis apakah titik/poligon berada di dalam Kawasan Konservasi.
    Otomatis menyesuaikan kolom (NAMA_KK, KEWENANGAN, DASAR_HKM) jika berbeda nama.
    """
    try:
        # 1️⃣ Samakan CRS
        if gdf.crs != kawasan_gdf.crs:
            kawasan_gdf = kawasan_gdf.to_crs(gdf.crs)

        # 2️⃣ Perbaiki geometri invalid
        kawasan_gdf["geometry"] = kawasan_gdf["geometry"].buffer(0)

        # 3️⃣ Normalisasi nama kolom (handle shapefile berbeda format)
        rename_map = {
            "Nama": "NAMA_KK",
            "NAMOBJ": "NAMA_KK",
            "NAMA_KAWASAN": "NAMA_KK",
            "NAMA_KWS": "NAMA_KK",
            "Kewenangan": "KEWENANGAN",
            "KEWENANGAN_": "KEWENANGAN",
            "Dasar_Hukum": "DASAR_HKM",
            "DASAR_HKM_": "DASAR_HKM",
            "DASAR_HUKUM": "DASAR_HKM",
        }
        kawasan_gdf = kawasan_gdf.rename(columns={k: v for k, v in rename_map.items() if k in kawasan_gdf.columns})

        # 4️⃣ Pastikan kolom utama ada, jika tidak tambahkan default
        for col in ["NAMA_KK", "KEWENANGAN", "DASAR_HKM"]:
            if col not in kawasan_gdf.columns:
                kawasan_gdf[col] = "Tidak diketahui"

        # 5️⃣ Spatial join menggunakan "intersects" agar titik di tepi ikut terdeteksi
        joined = gpd.sjoin(
            gdf,
            kawasan_gdf[["NAMA_KK", "KEWENANGAN", "DASAR_HKM", "geometry"]],
            how="left",
            predicate="intersects"
        )

        overlaps = joined[joined["index_right"].notna()]
        if overlaps.empty:
            return {"has_overlap": False, "message": "Tidak berada di dalam Kawasan Konservasi"}

        # 6️⃣ Bangun daftar detail overlap
        overlap_details = []
        nama_list = []
        for _, row in overlaps.iterrows():
            detail = {
                "id": row.get("id", "Unknown"),
                "NAMA_KK": str(row.get("NAMA_KK", "N/A")),
                "KEWENANGAN": str(row.get("KEWENANGAN", "N/A")),
                "DASAR_HKM": str(row.get("DASAR_HKM", "N/A")),
            }
            overlap_details.append(detail)
            nama_list.append(detail["NAMA_KK"])

        # Hilangkan duplikat nama
        nama_list = sorted(list(set(nama_list)))

        # 7️⃣ Buat pesan ringkasan
        message = f"Berada di Kawasan Konservasi: {', '.join(nama_list)}"

        return {
            "has_overlap": True,
            "overlap_count": len(overlaps),
            "nama_kawasan": nama_list,
            "overlap_details": overlap_details,
            "message": message
        }

    except Exception as e:
        logger.error(f"Error during Kawasan Konservasi analysis: {e}", exc_info=True)
        return {"has_overlap": False, "message": f"Error: {str(e)}"}
