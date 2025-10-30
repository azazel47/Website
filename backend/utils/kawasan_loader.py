import geopandas as gpd
import requests
import tempfile
from pathlib import Path
import logging
import io

logger = logging.getLogger(__name__)
_kawasan_cache = None

def load_kawasan_konservasi():
    """
    Memuat GeoPackage Kawasan Konservasi dari GitHub.
    Cache di memory agar load cepat.
    """
    global _kawasan_cache
    if _kawasan_cache is not None:
        return _kawasan_cache

    url = "https://github.com/azazel47/Website/raw/main/Kawasan_Konservasi_2022_update.gpkg"
    try:
        logger.info(f"Downloading Kawasan Konservasi GeoPackage from GitHub: {url}")
        r = requests.get(url)
        r.raise_for_status()

        # Simpan sementara di memory
        with tempfile.NamedTemporaryFile(suffix=".gpkg") as tmpfile:
            tmpfile.write(r.content)
            tmpfile.flush()
            gdf = gpd.read_file(tmpfile.name)

        # Pastikan CRS
        gdf.set_crs(epsg=4326, inplace=True)

        # Cache
        _kawasan_cache = gdf
        logger.info(f"Berhasil load {len(gdf)} fitur Kawasan Konservasi dari GitHub")
        return gdf

    except Exception as e:
        logger.error(f"Gagal load Kawasan Konservasi dari GitHub: {e}", exc_info=True)
        # Return GeoDataFrame kosong sebagai fallback
        return gpd.GeoDataFrame(
            columns=["NAMA_KK", "KEWENANGAN", "DASAR_HKM", "geometry"],
            geometry="geometry",
            crs="EPSG:4326"
        )
