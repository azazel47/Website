import geopandas as gpd
from shapely.strtree import STRtree
from shapely.geometry import shape
from typing import Optional
import logging

from .kawasan_loader import load_kawasan_konservasi
from .mil12_loader import load_12mil_shapefile
from .kkprl_loader import load_kkprl_data

logger = logging.getLogger(__name__)


# ==========================================================
# 🟢 Helper umum
# ==========================================================
def _safe_intersects(geom, candidate):
    """Cek intersect dengan aman, hanya jika keduanya Geometry valid"""
    if geom is None or geom.is_empty or not hasattr(candidate, "intersects"):
        return False
    try:
        return geom.intersects(candidate)
    except Exception:
        return False


def _safe_buffer_fix(gdf: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    """Perbaiki geometry invalid"""
    if "geometry" in gdf:
        gdf["geometry"] = gdf["geometry"].buffer(0)
    return gdf


# ==========================================================
# 🟢 Kawasan Konservasi
# ==========================================================
def analyze_overlap_kawasan(gdf: gpd.GeoDataFrame, kawasan_gdf: Optional[gpd.GeoDataFrame] = None) -> dict:
    """Analisis overlap dengan Kawasan Konservasi"""
    try:
        if kawasan_gdf is None:
            kawasan_gdf, kawasan_index = load_kawasan_konservasi()
        elif isinstance(kawasan_gdf, tuple):
            kawasan_gdf, kawasan_index = kawasan_gdf
        else:
            kawasan_index = STRtree(kawasan_gdf.geometry)

        if kawasan_gdf is None or kawasan_gdf.empty:
            return {"has_overlap": False, "message": "Data Kawasan kosong"}

        if gdf.crs != kawasan_gdf.crs:
            kawasan_gdf = kawasan_gdf.to_crs(gdf.crs)

        kawasan_gdf = _safe_buffer_fix(kawasan_gdf)
        gdf = _safe_buffer_fix(gdf)

        idx_map = {id(geom): i for i, geom in enumerate(kawasan_gdf.geometry)}
        overlaps, nama_list = [], []

        for geom in gdf.geometry:
            candidates = kawasan_index.query(geom)
            for c in candidates:
                if _safe_intersects(geom, c):
                    row = kawasan_gdf.iloc[idx_map[id(c)]]
                    overlaps.append(row["NAMA_KK"])
                    nama_list.append(row["NAMA_KK"])

        if not overlaps:
            return {"has_overlap": False, "message": "Tidak berada di Kawasan Konservasi"}

        unique_names = sorted(set(nama_list))
        return {
            "has_overlap": True,
            "nama_kawasan": unique_names,
            "message": f"Berada di Kawasan Konservasi: {', '.join(unique_names)}"
        }

    except Exception as e:
        logger.error(f"Error in analyze_overlap_kawasan: {e}", exc_info=True)
        return {"has_overlap": False, "message": f"Error: {str(e)}"}


# ==========================================================
# 🟢 Batas 12 Mil Laut
# ==========================================================
def analyze_overlap_12mil(gdf: gpd.GeoDataFrame, mil12_gdf: Optional[gpd.GeoDataFrame] = None) -> dict:
    """Analisis overlap dengan batas 12 mil laut"""
    try:
        if mil12_gdf is None:
            mil12_gdf, _ = load_12mil_shapefile()
        if isinstance(mil12_gdf, tuple):
            mil12_gdf = mil12_gdf[0]

        if mil12_gdf is None or mil12_gdf.empty:
            return {"has_overlap": False, "message": "Data 12 mil kosong"}

        if gdf.crs != mil12_gdf.crs:
            mil12_gdf = mil12_gdf.to_crs(gdf.crs)

        mil12_gdf = _safe_buffer_fix(mil12_gdf)
        gdf = _safe_buffer_fix(gdf)

        tree = STRtree(mil12_gdf.geometry)
        idx_map = {id(geom): i for i, geom in enumerate(mil12_gdf.geometry)}

        overlaps = []
        for geom in gdf.geometry:
            candidates = tree.query(geom)
            for c in candidates:
                if _safe_intersects(geom, c):
                    row = mil12_gdf.iloc[idx_map[id(c)]]
                    overlaps.append(row["WP"])

        if not overlaps:
            return {"has_overlap": False, "message": "Berada di luar 12 mil laut"}

        unique_wp = sorted(set(overlaps))
        return {
            "has_overlap": True,
            "wp_list": unique_wp,
            "message": f"Berada di dalam 12 mil laut: {', '.join(unique_wp)}"
        }

    except Exception as e:
        logger.error(f"Error in analyze_overlap_12mil: {e}", exc_info=True)
        return {"has_overlap": False, "message": f"Error: {str(e)}"}


# ==========================================================
# 🟢 KKPRL (Kesesuaian Kegiatan Pemanfaatan Ruang Laut)
# ==========================================================
def analyze_overlap_kkprl(gdf: gpd.GeoDataFrame, kkprl_gdf: Optional[gpd.GeoDataFrame] = None) -> dict:
    """Analisis overlap dengan KKPRL"""
    try:
        if kkprl_gdf is None:
            kkprl_gdf = load_kkprl_data()

        if isinstance(kkprl_gdf, tuple):
            kkprl_gdf = kkprl_gdf[0]

        if kkprl_gdf is None or kkprl_gdf.empty:
            return {"has_overlap": False, "message": "Data KKPRL kosong"}

        if gdf.crs != kkprl_gdf.crs:
            kkprl_gdf = kkprl_gdf.to_crs(gdf.crs)

        kkprl_gdf = _safe_buffer_fix(kkprl_gdf)
        gdf = _safe_buffer_fix(gdf)

        tree = STRtree(kkprl_gdf.geometry)
        idx_map = {id(geom): i for i, geom in enumerate(kkprl_gdf.geometry)}

        overlaps = []
        for geom in gdf.geometry:
            candidates = tree.query(geom)
            for c in candidates:
                if _safe_intersects(geom, c):
                    row = kkprl_gdf.iloc[idx_map[id(c)]]
                    overlaps.append({
                        "Kegiatan": row.get("KEGIATAN"),
                        "Nama": row.get("NAMA"),
                        "Lokasi": row.get("LOKASI"),
                    })

        if not overlaps:
            return {"has_overlap": False, "message": "Tidak ada tumpang tindih dengan KKPRL"}

        return {
            "has_overlap": True,
            "jumlah": len(overlaps),
            "detail": overlaps,
            "message": f"Ditemukan {len(overlaps)} tumpang tindih KKPRL"
        }

    except Exception as e:
        logger.error(f"Error in analyze_overlap_kkprl: {e}", exc_info=True)
        return {"has_overlap": False, "message": f"Error: {str(e)}"}


# ==========================================================
# 🟢 Analisis utama (gabungan semua)
# ==========================================================
def analyze_all_layers(user_gdf: gpd.GeoDataFrame) -> dict:
    """Analisis semua lapisan sekaligus"""
    try:
        logger.info("Running full overlay analysis...")

        result_kawasan = analyze_overlap_kawasan(user_gdf)
        result_12mil = analyze_overlap_12mil(user_gdf)
        result_kkprl = analyze_overlap_kkprl(user_gdf)

        return {
            "success": True,
            "overlap_kawasan": result_kawasan,
            "overlap_12mil": result_12mil,
            "overlap_kkprl": result_kkprl
        }

    except Exception as e:
        logger.error(f"Error in analyze_all_layers: {e}", exc_info=True)
        return {"success": False, "message": f"Error: {str(e)}"}
