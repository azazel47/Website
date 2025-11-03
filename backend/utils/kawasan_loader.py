import geopandas as gpd
import requests
import tempfile
import logging
from shapely.strtree import STRtree

logger = logging.getLogger(__name__)

_kawasan_cache = None
_kawasan_index = None  # ⬅️ cache untuk spatial index


def load_kawasan_konservasi():
    """
    Memuat GeoPackage Kawasan Konservasi dari GitHub dan cache di memori.
    """
    global _kawasan_cache, _kawasan_index

    if _kawasan_cache is not None and _kawasan_index is not None:
        return _kawasan_cache, _kawasan_index

    url = "https://github.com/azazel47/Website/raw/main/Kawasan_Konservasi_2022_update.gpkg"
    try:
        logger.info(f"Downloading Kawasan Konservasi GeoPackage from GitHub: {url}")
        r = requests.get(url)
        r.raise_for_status()

        with tempfile.NamedTemporaryFile(suffix=".gpkg") as tmpfile:
            tmpfile.write(r.content)
            tmpfile.flush()
            gdf = gpd.read_file(tmpfile.name)

        gdf.set_crs(epsg=4326, inplace=True)

        # Buat spatial index hanya sekali
        spatial_index = STRtree(gdf.geometry)
        _kawasan_cache = gdf
        _kawasan_index = spatial_index

        logger.info(f"Berhasil load dan index {len(gdf)} fitur Kawasan Konservasi")
        return gdf, spatial_index

    except Exception as e:
        logger.error(f"Gagal load Kawasan Konservasi dari GitHub: {e}", exc_info=True)
        empty = gpd.GeoDataFrame(columns=["NAMA_KK", "KEWENANGAN", "DASAR_HKM", "geometry"], geometry="geometry", crs="EPSG:4326")
        return empty, None
