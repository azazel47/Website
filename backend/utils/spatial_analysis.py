import geopandas as gpd
import pandas as pd
from shapely.geometry import Point, Polygon, shape
from shapely.prepared import prep
from shapely.errors import TopologicalError
from functools import lru_cache
from typing import List, Dict, Optional
import logging

logger = logging.getLogger(__name__)
logger.setLevel(logging.WARNING)  # minimize overhead logging

# ============================================================
# 1️⃣ LOAD DATA DENGAN CACHE PERMANEN DI MEMORI
# ============================================================
@lru_cache(maxsize=1)
def get_kawasan_gdf():
    from .kawasan_loader import load_kawasan_konservasi
    kawasan_gdf, _ = load_kawasan_konservasi()
    if isinstance(kawasan_gdf, tuple):
        kawasan_gdf = kawasan_gdf[0]
    if kawasan_gdf is not None and not kawasan_gdf.empty:
        if kawasan_gdf.crs is None:
            kawasan_gdf.set_crs(epsg=4326, inplace=True)
        elif kawasan_gdf.crs.to_epsg() != 4326:
            kawasan_gdf = kawasan_gdf.to_crs(epsg=4326)
    return kawasan_gdf

@lru_cache(maxsize=1)
def get_mil12_gdf():
    from .mil12_loader import load_12mil_shapefile
    mil12_gdf, _ = load_12mil_shapefile()
    if mil12_gdf is not None and not mil12_gdf.empty:
        if mil12_gdf.crs is None:
            mil12_gdf.set_crs(epsg=4326, inplace=True)
        elif mil12_gdf.crs.to_epsg() != 4326:
            mil12_gdf = mil12_gdf.to_crs(epsg=4326)
    return mil12_gdf

# ============================================================
# 2️⃣ FUNGSI PEMBUAT GEO-DATAFRAME
# ============================================================
def create_point_gdf(coordinates: List[Dict]) -> gpd.GeoDataFrame:
    df = pd.DataFrame(coordinates)
    geometry = [Point(row['longitude'], row['latitude']) for _, row in df.iterrows()]
    return gpd.GeoDataFrame(df, geometry=geometry, crs="EPSG:4326")

def create_polygon_gdf(coordinates: List[Dict]) -> gpd.GeoDataFrame:
    coords = [(c['longitude'], c['latitude']) for c in coordinates]
    if coords and coords[0] != coords[-1]:
        coords.append(coords[0])
    poly = Polygon(coords)
    return gpd.GeoDataFrame(pd.DataFrame({"id": ["polygon_1"]}), geometry=[poly], crs="EPSG:4326")

# Tambahkan di bawah definisi fungsi create_point_gdf
create_point_geodataframe = create_point_gdf
create_polygon_geodataframe = create_polygon_gdf

# ============================================================
# 3️⃣ ANALISIS OVERLAP — DENGAN PREPARED GEOMETRIES
# ============================================================

def analyze_overlap_12mil(gdf: gpd.GeoDataFrame) -> dict:
    try:
        mil12_gdf = get_mil12_gdf()
        if mil12_gdf is None or mil12_gdf.empty:
            return {"has_overlap": False, "message": "Data 12 mil tidak tersedia"}

        # Gunakan prepared geometry untuk mempercepat intersects
        prepared = [prep(geom) for geom in mil12_gdf.geometry]

        overlaps = []
        for geom in gdf.geometry:
            for pgeom, row in zip(prepared, mil12_gdf.itertuples()):
                if pgeom.intersects(geom):
                    overlaps.append(row.WP)

        if not overlaps:
            return {"has_overlap": False, "message": "Berada di luar 12 mil laut"}

        unique_wp = sorted(set(overlaps))
        return {
            "has_overlap": True,
            "wp_list": unique_wp,
            "message": f"Berada di dalam 12 mil laut: {', '.join(unique_wp)}"
        }

    except Exception as e:
        return {"has_overlap": False, "message": f"Error: {str(e)}"}


def analyze_overlap_kawasan(gdf: gpd.GeoDataFrame) -> dict:
    try:
        kawasan_gdf = get_kawasan_gdf()
        if kawasan_gdf is None or kawasan_gdf.empty:
            return {"has_overlap": False, "message": "Data kawasan konservasi tidak tersedia"}

        prepared = [prep(geom) for geom in kawasan_gdf.geometry]

        overlaps = []
        for geom in gdf.geometry:
            for pgeom, row in zip(prepared, kawasan_gdf.itertuples()):
                if pgeom.intersects(geom):
                    overlaps.append({
                        "NAMA_KK": getattr(row, "NAMA_KK", "Tidak diketahui"),
                        "KEWENANGAN": getattr(row, "KEWENANGAN", "Tidak diketahui"),
                        "DASAR_HKM": getattr(row, "DASAR_HKM", "Tidak diketahui"),
                    })

        if not overlaps:
            return {"has_overlap": False, "message": "Tidak berada di Kawasan Konservasi"}

        nama_list = sorted(set(o["NAMA_KK"] for o in overlaps))
        return {
            "has_overlap": True,
            "nama_kawasan": nama_list,
            "overlap_count": len(overlaps),
            "overlap_details": overlaps,
            "message": f"Berada di Kawasan Konservasi: {', '.join(nama_list)}"
        }

    except TopologicalError:
        return {"has_overlap": False, "message": "Geometri tidak valid (TopologicalError)"}
    except Exception as e:
        return {"has_overlap": False, "message": f"Error: {str(e)}"}
