import geopandas as gpd
import tempfile
import zipfile
import gdown
from pathlib import Path
import logging

logger = logging.getLogger(__name__)
_12mil_cache = None

def load_12mil_shapefile():
    global _12mil_cache
    if _12mil_cache is not None:
        return _12mil_cache

    try:
        file_id = "140lv4AAS9UmiA-5wII1CCv0CxrZXFNvk"
        url = f"https://drive.google.com/uc?id={file_id}"
        logger.info(f"Mengunduh shapefile ZIP 12 mil laut dari Google Drive (ID: {file_id})")

        with tempfile.TemporaryDirectory() as tmpdir:
            zip_path = Path(tmpdir) / "12mil.zip"

            # Gunakan gdown agar bisa unduh file besar dengan konfirmasi
            gdown.download(url, str(zip_path), quiet=False)

            # Ekstrak isi ZIP
            with zipfile.ZipFile(zip_path, "r") as zip_ref:
                zip_ref.extractall(tmpdir)

            # Cari file .shp
            shp_files = list(Path(tmpdir).rglob("*.shp"))
            if not shp_files:
                raise FileNotFoundError("Tidak ditemukan file .shp di dalam ZIP 12 mil laut")

            shp_path = shp_files[0]
            logger.info(f"Membaca shapefile dari {shp_path}")

            gdf = gpd.read_file(shp_path)
            gdf.set_crs(epsg=4326, inplace=True)
            _12mil_cache = gdf
            logger.info(f"Berhasil memuat shapefile 12 mil laut: {len(gdf)} fitur")
            return gdf

    except Exception as e:
        logger.error(f"Gagal memuat shapefile 12 mil laut: {e}", exc_info=True)
        return None
