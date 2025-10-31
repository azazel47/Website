import geopandas as gpd
from shapely.strtree import STRtree
from shapely.geometry import Point, Polygon
from typing import Optional, List, Dict
import logging
from functools import lru_cache

from .kawasan_loader import load_kawasan_konservasi
from .mil12_loader import load_12mil_shapefile
from .kkprl_loader import load_kkprl_json

logger = logging.getLogger(__name__)

# Cache untuk data yang sering diakses
@lru_cache(maxsize=1)
def get_cached_kawasan():
    return load_kawasan_konservasi()

@lru_cache(maxsize=1)
def get_cached_12mil():
    return load_12mil_shapefile()

@lru_cache(maxsize=1)
def get_cached_kkprl():
    return load_kkprl_json()

def create_point_geodataframe(lat: float, lon: float) -> gpd.GeoDataFrame:
    """
    Membuat GeoDataFrame dari koordinat latitude dan longitude.
    CRS default: EPSG:4326
    """
    try:
        geom = Point(lon, lat)
        gdf = gpd.GeoDataFrame(
            [{"latitude": lat, "longitude": lon, "geometry": geom}],
            geometry="geometry",
            crs="EPSG:4326"
        )
        return gdf
    except Exception as e:
        raise ValueError(f"Gagal membuat GeoDataFrame: {e}")

def create_polygon_geodataframe(coords: List[Dict]) -> gpd.GeoDataFrame:
    """
    Membuat GeoDataFrame Polygon dari daftar koordinat.

    Mendukung berbagai format kunci:
    - {'lat', 'lon'}
    - {'lat', 'lng'}
    - {'latitude', 'longitude'}
    - {'x', 'y'}
    """
    try:
        polygon_coords = []
        for c in coords:
            lon = (
                c.get("lon") or 
                c.get("lng") or 
                c.get("x") or 
                c.get("longitude")
            )
            lat = (
                c.get("lat") or 
                c.get("y") or 
                c.get("latitude")
            )
            if lon is None or lat is None:
                raise ValueError(f"Koordinat tidak valid: {c}")
            polygon_coords.append((float(lon), float(lat)))

        # Tutup polygon jika belum tertutup
        if polygon_coords[0] != polygon_coords[-1]:
            polygon_coords.append(polygon_coords[0])

        polygon = Polygon(polygon_coords)
        gdf = gpd.GeoDataFrame(geometry=[polygon], crs="EPSG:4326")
        return gdf

    except Exception as e:
        raise ValueError(f"Gagal membuat GeoDataFrame polygon: {e}")

def _optimize_geometries(gdf: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    """Optimasi geometri untuk performa query yang lebih baik"""
    if gdf is None or gdf.empty:
        return gdf
    
    gdf = gdf.copy()
    # Simplify geometri untuk mengurangi kompleksitas (toleransi kecil untuk presisi)
    if not gdf.empty:
        gdf['geometry'] = gdf['geometry'].simplify(tolerance=0.00001, preserve_topology=True)
    
    return gdf

def _fast_spatial_join(gdf: gpd.GeoDataFrame, reference_gdf: gpd.GeoDataFrame, predicate: str = 'intersects') -> List:
    """
    Fast spatial join menggunakan STRtree dengan optimasi
    """
    try:
        # Optimasi kedua GeoDataFrame
        gdf_opt = _optimize_geometries(gdf)
        ref_opt = _optimize_geometries(reference_gdf)
        
        # Buat spatial index untuk reference data
        tree = STRtree(ref_opt.geometry)
        idx_map = {id(geom): i for i, geom in enumerate(ref_opt.geometry)}
        
        matches = []
        for geom in gdf_opt.geometry:
            if not geom.is_valid:
                continue
                
            # Query spatial index
            candidates = tree.query(geom)
            for candidate in candidates:
                if geom.intersects(candidate):
                    row_idx = idx_map[id(candidate)]
                    matches.append((geom, row_idx))
        
        return matches
    except Exception as e:
        logger.error(f"Error in fast spatial join: {e}")
        return []

# ============================================================
# 🧠 FUNGSI ANALISIS OVERLOAD YANG DIOPTIMASI
# ============================================================

def analyze_overlap_kawasan(gdf: gpd.GeoDataFrame) -> dict:
    """Analisis overlap dengan Kawasan Konservasi (Optimized)"""
    try:
        kawasan_gdf, kawasan_index = get_cached_kawasan()
        
        if kawasan_gdf is None or kawasan_gdf.empty:
            return {"has_overlap": False, "message": "Data Kawasan kosong"}
        
        # Pastikan CRS sama
        if gdf.crs != kawasan_gdf.crs:
            kawasan_gdf = kawasan_gdf.to_crs(gdf.crs)
        
        # Gunakan spatial join yang dioptimasi
        matches = _fast_spatial_join(gdf, kawasan_gdf)
        
        if not matches:
            return {"has_overlap": False, "message": "Tidak berada di Kawasan Konservasi"}
        
        # Kumpulkan hasil
        nama_list = []
        for geom, row_idx in matches:
            row = kawasan_gdf.iloc[row_idx]
            nama_list.append(row.get("NAMA_KK", "Tidak Dikenal"))
        
        unique_names = sorted(set(nama_list))
        return {
            "has_overlap": True,
            "nama_kawasan": unique_names,
            "overlap_count": len(matches),
            "message": f"Berada di Kawasan Konservasi: {', '.join(unique_names)}"
        }

    except Exception as e:
        logger.error(f"Error in analyze_overlap_kawasan: {e}", exc_info=True)
        return {"has_overlap": False, "message": f"Error: {str(e)}"}

def analyze_overlap_12mil(gdf: gpd.GeoDataFrame) -> dict:
    """Analisis overlap dengan batas 12 mil laut (Optimized)"""
    try:
        mil12_gdf, mil12_index = get_cached_12mil()
        
        if mil12_gdf is None or mil12_gdf.empty:
            return {"has_overlap": False, "message": "Data 12 mil kosong"}
        
        # Pastikan CRS sama
        if gdf.crs != mil12_gdf.crs:
            mil12_gdf = mil12_gdf.to_crs(gdf.crs)
        
        # Gunakan spatial join yang dioptimasi
        matches = _fast_spatial_join(gdf, mil12_gdf)
        
        if not matches:
            return {"has_overlap": False, "message": "Berada di luar 12 mil laut"}
        
        # Kumpulkan hasil
        wp_list = []
        for geom, row_idx in matches:
            row = mil12_gdf.iloc[row_idx]
            wp_list.append(row.get("WP", "Tidak Dikenal"))
        
        unique_wp = sorted(set(wp_list))
        return {
            "has_overlap": True,
            "wp_list": unique_wp,
            "overlap_count": len(matches),
            "message": f"Berada di dalam 12 mil laut: {', '.join(unique_wp)}"
        }

    except Exception as e:
        logger.error(f"Error in analyze_overlap_12mil: {e}", exc_info=True)
        return {"has_overlap": False, "message": f"Error: {str(e)}"}

def analyze_overlap_kkprl(gdf: gpd.GeoDataFrame) -> dict:
    """Analisis overlap dengan KKPRL (Optimized)"""
    try:
        kkprl_gdf = get_cached_kkprl()
        
        if kkprl_gdf is None or kkprl_gdf.empty:
            return {"has_overlap": False, "message": "Data KKPRL kosong"}
        
        # Pastikan CRS sama
        if gdf.crs != kkprl_gdf.crs:
            kkprl_gdf = kkprl_gdf.to_crs(gdf.crs)
        
        # Gunakan spatial join yang dioptimasi
        matches = _fast_spatial_join(gdf, kkprl_gdf)
        
        if not matches:
            return {"has_overlap": False, "message": "Tidak ada tumpang tindih dengan KKPRL"}
        
        # Kumpulkan hasil detail
        overlap_details = []
        for geom, row_idx in matches:
            row = kkprl_gdf.iloc[row_idx]
            overlap_details.append({
                "Kegiatan": row.get("KEGIATAN", "Tidak Dikenal"),
                "Nama": row.get("NAMA", "Tidak Dikenal"),
                "Lokasi": row.get("LOKASI", "Tidak Dikenal"),
                "No_KKPRL": row.get("NO_KKPRL", "Tidak Dikenal"),
            })
        
        return {
            "has_overlap": True,
            "jumlah": len(overlap_details),
            "detail": overlap_details,
            "message": f"Ditemukan {len(overlap_details)} tumpang tindih KKPRL"
        }

    except Exception as e:
        logger.error(f"Error in analyze_overlap_kkprl: {e}", exc_info=True)
        return {"has_overlap": False, "message": f"Error: {str(e)}"}

# ==========================================================
# 🟢 ANALISIS UTAMA (GABUNGAN SEMUA) - DIOPTIMASI
# ==========================================================

def analyze_all_layers(user_gdf: gpd.GeoDataFrame) -> dict:
    """Analisis semua lapisan sekaligus dengan paralelisasi sederhana"""
    try:
        logger.info("Running optimized full overlay analysis...")
        
        # Eksekusi semua analisis
        result_kawasan = analyze_overlap_kawasan(user_gdf)
        result_12mil = analyze_overlap_12mil(user_gdf)
        result_kkprl = analyze_overlap_kkprl(user_gdf)
        
        # Hitung statistik performa
        total_overlaps = (
            (result_kawasan.get('overlap_count', 0) if result_kawasan.get('has_overlap') else 0) +
            (result_12mil.get('overlap_count', 0) if result_12mil.get('has_overlap') else 0) +
            (result_kkprl.get('jumlah', 0) if result_kkprl.get('has_overlap') else 0)
        )
        
        return {
            "success": True,
            "total_overlaps": total_overlaps,
            "overlap_kawasan": result_kawasan,
            "overlap_12mil": result_12mil,
            "overlap_kkprl": result_kkprl,
            "analysis_time": "optimized"  # Flag untuk frontend
        }

    except Exception as e:
        logger.error(f"Error in analyze_all_layers: {e}", exc_info=True)
        return {"success": False, "message": f"Error: {str(e)}"}

# ==========================================================
# 🟢 FUNGSI BANTU TAMBAHAN
# ==========================================================

def clear_cache():
    """Bersihkan cache - berguna untuk development"""
    global get_cached_kawasan, get_cached_12mil, get_cached_kkprl
    get_cached_kawasan.cache_clear()
    get_cached_12mil.cache_clear()
    get_cached_kkprl.cache_clear()
    logger.info("Spatial analysis cache cleared")

def get_analysis_stats() -> dict:
    """Dapatkan statistik tentang data yang di-cache"""
    try:
        kawasan_gdf, _ = get_cached_kawasan()
        mil12_gdf, _ = get_cached_12mil()
        kkprl_gdf = get_cached_kkprl()
        
        return {
            "kawasan_features": len(kawasan_gdf) if kawasan_gdf is not None else 0,
            "12mil_features": len(mil12_gdf) if mil12_gdf is not None else 0,
            "kkprl_features": len(kkprl_gdf) if kkprl_gdf is not None else 0,
            "cache_status": "active"
        }
    except Exception as e:
        return {"cache_status": f"error: {str(e)}"}
