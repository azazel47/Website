import geopandas as gpd
import tempfile
import zipfile
from pathlib import Path
import logging

logger = logging.getLogger(__name__)
_12mil_cache = None

def load_12mil_shapefile():
    """
    Memuat shapefile 12 mil dari file ZIP lokal.
        """
    global _12mil_cache
    if _12mil_cache is not None:
        return _12mil_cache

    try:
        # Lokasi file ZIP (ubah jika folder kamu berbeda)
        zip_path = Path(__file__).resolve().parent.parent / "12_Mil.zip"

        if not zip_path.exists():
            raise FileNotFoundError(f"File ZIP tidak ditemukan di {zip_path}")

        logger.info(f"Memuat shapefile 12 mil: {zip_path}")

        # Ekstraksi ke folder sementara
        with tempfile.TemporaryDirectory() as tmpdir:
            with zipfile.ZipFile(zip_path, "r") as zip_ref:
                zip_ref.extractall(tmpdir)

            shp_files = list(Path(tmpdir).rglob("*.shp"))
            if not shp_files:
                raise FileNotFoundError("Tidak ditemukan file .shp di dalam ZIP 12 Mil")

            # Baca shapefile
            gdf = gpd.read_file(shp_files[0])
            gdf.set_crs(epsg=4326, inplace=True)

            _12mil_cache = gdf
            logger.info(f"Berhasil memuat {len(gdf)} fitur 12 Mil.")
            return gdf

    except Exception as e:
        logger.error(f"Gagal memuat shapefile 12 Mil: {e}", exc_info=True)
        return None
