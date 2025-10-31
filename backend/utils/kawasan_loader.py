import geopandas as gpd
import requests
import tempfile
import logging
from shapely.strtree import STRtree
from functools import lru_cache

logger = logging.getLogger(__name__)

# Global cache
_kawasan_cache = None
_kawasan_index = None

@lru_cache(maxsize=1)
def load_kawasan_konservasi():
    """
    Memuat GeoPackage Kawasan Konservasi dengan caching yang dioptimasi
    """
    global _kawasan_cache, _kawasan_index

    if _kawasan_cache is not None and _kawasan_index is not None:
        return _kawasan_cache, _kawasan_index

    url = "https://github.com/azazel47/Website/raw/main/Kawasan_Konservasi_2022_update.gpkg"
    try:
        logger.info(f"Downloading Kawasan Konservasi GeoPackage from GitHub: {url}")
        r = requests.get(url, timeout=60)
        r.raise_for_status()

        with tempfile.NamedTemporaryFile(suffix=".gpkg") as tmpfile:
            tmpfile.write(r.content)
            tmpfile.flush()
            gdf = gpd.read_file(tmpfile.name)

        # Pastikan CRS
        if gdf.crs is None:
            gdf.set_crs(epsg=4326, inplace=True)
        elif gdf.crs != "EPSG:4326":
            gdf = gdf.to_crs("EPSG:4326")

        # Optimasi: Pilih hanya kolom yang diperlukan
        expected_columns = ["NAMA_KK", "KEWENANGAN", "DASAR_HKM"]
        available_columns = [col for col in expected_columns if col in gdf.columns]
        
        # Tambahkan kolom yang tidak ada dengan nilai default
        for col in expected_columns:
            if col not in gdf.columns:
                gdf[col] = "Tidak Dikenal"
        
        # Pilih hanya kolom yang diperlukan + geometry
        columns_to_keep = available_columns + ["geometry"]
        gdf = gdf[columns_to_keep]

        # Buat spatial index
        spatial_index = STRtree(gdf.geometry)
        
        # Cache results
        _kawasan_cache = gdf
        _kawasan_index = spatial_index

        logger.info(f"Berhasil load dan index {len(gdf)} fitur Kawasan Konservasi")
        return gdf, spatial_index

    except Exception as e:
        logger.error(f"Gagal load Kawasan Konservasi dari GitHub: {e}", exc_info=True)
        # Return empty GeoDataFrame dengan struktur yang konsisten
        empty_gdf = gpd.GeoDataFrame(
            columns=["NAMA_KK", "KEWENANGAN", "DASAR_HKM", "geometry"], 
            geometry="geometry", 
            crs="EPSG:4326"
        )
        empty_index = STRtree([])
        return empty_gdf, empty_index

def clear_kawasan_cache():
    """Bersihkan cache kawasan konservasi"""
    global _kawasan_cache, _kawasan_index
    _kawasan_cache = None
    _kawasan_index = None
    load_kawasan_konservasi.cache_clear()
    logger.info("Kawasan Konservasi cache cleared")
