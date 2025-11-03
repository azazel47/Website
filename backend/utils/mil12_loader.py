import geopandas as gpd
import requests
import zipfile
import io
import tempfile
import pathlib
import logging

logger = logging.getLogger(__name__)

_12mil_cache = None  # Cache GeoDataFrame 12 mil

def load_12mil_shapefile() -> gpd.GeoDataFrame:
    """
    Load shapefile 12 mil laut dari GitHub dan cache hasilnya.
    """
    global _12mil_cache
    if _12mil_cache is not None:
        return _12mil_cache

    url = "https://raw.githubusercontent.com/azazel47/Website/main/12_Mil.zip"
    try:
        r = requests.get(url)
        r.raise_for_status()

        with zipfile.ZipFile(io.BytesIO(r.content)) as z:
            shp_files = [f for f in z.namelist() if f.endswith(".shp")]
            if not shp_files:
                raise FileNotFoundError("Tidak ditemukan file .shp di ZIP 12 Mil GitHub")

            with tempfile.TemporaryDirectory() as tmpdir:
                z.extractall(tmpdir)
                shp_path = pathlib.Path(tmpdir) / shp_files[0]
                gdf = gpd.read_file(shp_path)
                gdf.set_crs(epsg=4326, inplace=True)
                logger.info(f"Berhasil load {len(gdf)} fitur 12 Mil dari GitHub")
                _12mil_cache = gdf
                return gdf

    except Exception as e:
        logger.error(f"Gagal load 12 Mil dari GitHub: {e}", exc_info=True)
        return gpd.GeoDataFrame(columns=["WP", "geometry"], geometry="geometry", crs="EPSG:4326")

def get_mil12_gdf() -> gpd.GeoDataFrame:
    """Helper untuk ambil GeoDataFrame 12 mil, memanfaatkan cache"""
    return load_12mil_shapefile()
