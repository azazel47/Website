import geopandas as gpd
import pandas as pd
from shapely.geometry import Point, Polygon
from shapely.strtree import STRtree
from typing import List, Dict, Optional
from .kawasan_loader import load_kawasan_konservasi
from .mil12_loader import load_12mil_shapefile
import logging

logger = logging.getLogger(__name__)

# =====================
# Helper functions
# =====================

def create_point_geodataframe(coordinates: List[Dict], crs: str = "EPSG:4326") -> gpd.GeoDataFrame:
    df = pd.DataFrame(coordinates)
    geometry = [Point(row['longitude'], row['latitude']) for _, row in df.iterrows()]
    return gpd.GeoDataFrame(df, geometry=geometry, crs=crs)


def create_polygon_geodataframe(coordinates: List[Dict], crs: str = "EPSG:4326") -> gpd.GeoDataFrame:
    coords = [(c['longitude'], c['latitude']) for c in coordinates]
    if coords and coords[0] != coords[-1]:
        coords.append(coords[0])
    geometry = [Polygon(coords)]
    return gpd.GeoDataFrame(pd.DataFrame({"id": ["polygon_1"]}), geometry=geometry, crs=crs)

# =====================
# Spatial Analyses
# =====================

def analyze_point_overlap(gdf: gpd.GeoDataFrame, kkprl_gdf: gpd.GeoDataFrame) -> Dict:
    try:
        if kkprl_gdf.empty or gdf.empty:
            return {"has_overlap": False, "message": "Data kosong"}

        kkprl_subset = kkprl_gdf[["NO_KKPRL", "NAMA_SUBJ", "KEGIATAN", "PROVINSI", "LUAS_HA", "geometry"]].copy()
        if gdf.crs != kkprl_subset.crs:
            kkprl_subset = kkprl_subset.to_crs(gdf.crs)

        # 🔹 Spatial index
        tree = STRtree(kkprl_subset.geometry)
        idx_map = {id(geom): i for i, geom in enumerate(kkprl_subset.geometry)}

        overlap_details = []
        for _, point in gdf.iterrows():
            candidates = tree.query(point.geometry)
            for geom in candidates:
                if point.geometry.within(geom):
                    row = kkprl_subset.iloc[idx_map[id(geom)]]
                    overlap_details.append({
                        "point_id": point.get('id', 'Unknown'),
                        "no_kkprl": row.NO_KKPRL,
                        "nama_subj": row.NAMA_SUBJ,
                        "kegiatan": row.KEGIATAN,
                        "provinsi": row.PROVINSI,
                        "luas_ha": row.LUAS_HA
                    })

        has_overlap = len(overlap_details) > 0
        subjects = list({d["nama_subj"] for d in overlap_details})
        return {
            "has_overlap": has_overlap,
            "overlap_count": len(overlap_details),
            "unique_subjects": subjects,
            "overlap_details": overlap_details,
            "message": f"{len(overlap_details)} titik overlap dengan KKPRL" if has_overlap else "Tidak ada overlap"
        }
    except Exception as e:
        logger.error(f"Error in point overlap analysis: {e}", exc_info=True)
        return {"has_overlap": False, "message": str(e)}


def analyze_polygon_overlap(gdf: gpd.GeoDataFrame, kkprl_gdf: gpd.GeoDataFrame) -> Dict:
    try:
        if kkprl_gdf.empty or gdf.empty:
            return {"has_overlap": False, "message": "Data kosong"}

        kkprl_subset = kkprl_gdf[["NO_KKPRL", "NAMA_SUBJ", "KEGIATAN", "PROVINSI", "LUAS_HA", "geometry"]].copy()
        if gdf.crs != kkprl_subset.crs:
            kkprl_subset = kkprl_subset.to_crs(gdf.crs)

        # 🔹 Spatial index
        tree = STRtree(kkprl_subset.geometry)
        idx_map = {id(geom): i for i, geom in enumerate(kkprl_subset.geometry)}

        overlap_details = []
        for geom in gdf.geometry:
            candidates = tree.query(geom)
            for candidate in candidates:
                if geom.intersects(candidate):
                    row = kkprl_subset.iloc[idx_map[id(candidate)]]
                    overlap_details.append({
                        "no_kkprl": row.NO_KKPRL,
                        "nama_subj": row.NAMA_SUBJ,
                        "kegiatan": row.KEGIATAN,
                        "provinsi": row.PROVINSI,
                        "luas_ha": row.LUAS_HA
                    })

        has_overlap = len(overlap_details) > 0
        return {
            "has_overlap": has_overlap,
            "overlap_count": len(overlap_details),
            "overlap_details": overlap_details,
            "message": f"{len(overlap_details)} KKPRL overlap" if has_overlap else "Tidak ada overlap"
        }
    except Exception as e:
        logger.error(f"Error in polygon overlap: {e}", exc_info=True)
        return {"has_overlap": False, "message": str(e)}


def analyze_overlap_12mil(gdf: gpd.GeoDataFrame, mil12_gdf: Optional[gpd.GeoDataFrame] = None) -> dict:
    try:
        if mil12_gdf is None:
            mil12_gdf, _ = load_12mil_shapefile()
        if isinstance(mil12_gdf, tuple):
            mil12_gdf = mil12_gdf[0]
        if mil12_gdf is None or mil12_gdf.empty:
            return {"has_overlap": False, "message": "Data 12 mil kosong"}

        if gdf.crs != mil12_gdf.crs:
            mil12_gdf = mil12_gdf.to_crs(gdf.crs)

        tree = STRtree(mil12_gdf.geometry)
        idx_map = {id(geom): i for i, geom in enumerate(mil12_gdf.geometry)}

        overlaps = []
        for geom in gdf.geometry:
            candidates = tree.query(geom)
            for c in candidates:
                if geom.intersects(c):
                    row = mil12_gdf.iloc[idx_map[id(c)]]
                    overlaps.append(row.WP)

        if not overlaps:
            return {"has_overlap": False, "message": "Berada di luar 12 mil laut"}

        unique_wp = sorted(set(overlaps))
        return {"has_overlap": True, "wp_list": unique_wp,
                "message": f"Berada di dalam 12 mil laut: {', '.join(unique_wp)}"}
    except Exception as e:
        return {"has_overlap": False, "message": str(e)}


def analyze_overlap_kawasan(gdf: gpd.GeoDataFrame, kawasan_gdf: Optional[gpd.GeoDataFrame] = None) -> dict:
    try:
        if kawasan_gdf is None:
            kawasan_gdf, kawasan_index = load_kawasan_konservasi()
        else:
            kawasan_index = STRtree(kawasan_gdf.geometry)

        if isinstance(kawasan_gdf, tuple):
            kawasan_gdf = kawasan_gdf[0]

        if kawasan_gdf is None or kawasan_gdf.empty:
            return {"has_overlap": False, "message": "Data Kawasan kosong"}

        if gdf.crs != kawasan_gdf.crs:
            kawasan_gdf = kawasan_gdf.to_crs(gdf.crs)

        idx_map = {id(geom): i for i, geom in enumerate(kawasan_gdf.geometry)}
        overlap_details, nama_list = [], []

        for geom in gdf.geometry:
            candidates = kawasan_index.query(geom)
            for candidate in candidates:
                if geom.intersects(candidate):
                    row = kawasan_gdf.iloc[idx_map[id(candidate)]]
                    overlap_details.append({
                        "NAMA_KK": row.get("NAMA_KK", "N/A"),
                        "KEWENANGAN": row.get("KEWENANGAN", "N/A"),
                        "DASAR_HKM": row.get("DASAR_HKM", "N/A")
                    })
                    nama_list.append(row.get("NAMA_KK", "N/A"))

        if not overlap_details:
            return {"has_overlap": False, "message": "Tidak berada di dalam Kawasan Konservasi"}

        nama_list = sorted(set(nama_list))
        return {
            "has_overlap": True,
            "overlap_count": len(overlap_details),
            "nama_kawasan": nama_list,
            "overlap_details": overlap_details,
            "message": f"Berada di Kawasan Konservasi: {', '.join(nama_list)}"
        }
    except Exception as e:
        logger.error(f"Error Kawasan Konservasi: {e}", exc_info=True)
        return {"has_overlap": False, "message": str(e)}
