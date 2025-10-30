import geopandas as gpd
import requests
import zipfile
import io
import logging

logger = logging.getLogger(__name__)


def load_kawasan_from_github():
    url = "https://raw.githubusercontent.com/azazel47/Website/main/Kawasan%20Konservasi%202022%20update.zip"
    try:
        r = requests.get(url)
        r.raise_for_status()
        with zipfile.ZipFile(io.BytesIO(r.content)) as z:
            shp_files = [f for f in z.namelist() if f.endswith(".shp")]
            if not shp_files:
                raise FileNotFoundError("Tidak ditemukan .shp di ZIP Kawasan Konservasi GitHub")
            with tempfile.TemporaryDirectory() as tmpdir:
                z.extractall(tmpdir)
                gdf = gpd.read_file(pathlib.Path(tmpdir) / shp_files[0])
                gdf.set_crs(epsg=4326, inplace=True)
                logger.info(f"Berhasil load {len(gdf)} fitur Kawasan Konservasi dari GitHub")
                return gdf
    except Exception as e:
        logger.error(f"Gagal load Kawasan Konservasi dari GitHub: {e}", exc_info=True)
        return gpd.GeoDataFrame(
            columns=["NAMA_KK", "KEWENANGAN", "DASAR_HKM", "geometry"],
            geometry="geometry",
            crs="EPSG:4326"
        )
