import geopandas as gpd
import requests
import zipfile
import io
import logging
from shapely.strtree import STRtree
<<<<<<< HEAD

logger = logging.getLogger(__name__)
_12mil_cache = None
_12mil_index = None  # ⬅️ cache untuk spatial index
=======
from functools import lru_cache

logger = logging.getLogger(__name__)

# Global cache variables
_12mil_cache = None
_12mil_index = None
>>>>>>> b8a15ad9b255fa1f9732073be0735d7910e2f1a6

@lru_cache(maxsize=1)
def load_12mil_shapefile():
<<<<<<< HEAD
    global _12mil, _12mil_index
=======
    """
    Load 12 mil shapefile dengan caching yang dioptimasi
    """
    global _12mil_cache, _12mil_index
>>>>>>> b8a15ad9b255fa1f9732073be0735d7910e2f1a6
    
    if _12mil_cache is not None and _12mil_index is not None:
        return _12mil_cache, _12mil_index
        
    url = "https://raw.githubusercontent.com/azazel47/Website/main/12_Mil.zip"
    try:
        logger.info("Downloading 12 Mil data from GitHub...")
        r = requests.get(url, timeout=60)
        r.raise_for_status()

        with zipfile.ZipFile(io.BytesIO(r.content)) as z:
            shp_files = [f for f in z.namelist() if f.endswith(".shp")]
            if not shp_files:
                raise FileNotFoundError("Tidak ditemukan file .shp di ZIP 12 Mil GitHub")

            # Ekstrak ke memory
            with io.BytesIO() as tmpfile:
                tmpfile.write(r.content)
                tmpfile.seek(0)
                with zipfile.ZipFile(tmpfile) as z2:
                    # Gunakan file shapefile pertama
                    shp_file_name = shp_files[0]
                    
                    # Ekstrak semua file terkait shapefile
                    related_files = [f for f in z2.namelist() 
                                   if f.startswith(shp_file_name.replace('.shp', ''))]
                    
                    import tempfile
                    import os
                    with tempfile.TemporaryDirectory() as tmpdir:
                        # Ekstrak semua file terkait
                        for file_name in related_files:
                            z2.extract(file_name, tmpdir)
                        
                        # Baca shapefile
                        base_name = os.path.splitext(shp_file_name)[0]
                        shp_path = os.path.join(tmpdir, shp_file_name)
                        gdf = gpd.read_file(shp_path)
                        
                        # Pastikan CRS
                        if gdf.crs is None:
                            gdf.set_crs(epsg=4326, inplace=True)
                        elif gdf.crs != "EPSG:4326":
                            gdf = gdf.to_crs("EPSG:4326")
                        
                        # Optimasi: pilih hanya kolom yang diperlukan
                        if 'WP' not in gdf.columns:
                            # Cari kolom yang mungkin berisi data WP
                            possible_wp_cols = [col for col in gdf.columns 
                                              if 'wp' in col.lower() or 'prov' in col.lower()]
                            if possible_wp_cols:
                                gdf = gdf.rename(columns={possible_wp_cols[0]: 'WP'})
                            else:
                                gdf['WP'] = 'Unknown'
                        
                        # Buat spatial index
                        spatial_index = STRtree(gdf.geometry)
                        
                        # Cache results
                        _12mil_cache = gdf
                        _12mil_index = spatial_index
                        
                        logger.info(f"Berhasil load {len(gdf)} fitur 12 Mil dari GitHub")
                        return gdf, spatial_index
                        
    except Exception as e:
        logger.error(f"Gagal load 12 Mil dari GitHub: {e}", exc_info=True)
        # Return empty GeoDataFrame dengan struktur yang benar
        empty_gdf = gpd.GeoDataFrame(columns=["WP", "geometry"], geometry="geometry", crs="EPSG:4326")
        empty_index = STRtree([])
        return empty_gdf, empty_index

def clear_12mil_cache():
    """Bersihkan cache 12 mil"""
    global _12mil_cache, _12mil_index
    _12mil_cache = None
    _12mil_index = None
    load_12mil_shapefile.cache_clear()
    logger.info("12 Mil cache cleared")
