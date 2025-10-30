import geopandas as gpd
import requests
import zipfile
import io
import logging

logger = logging.getLogger(__name__)



def load_kawasan_konservasi():
    url = "https://raw.githubusercontent.com/azazel47/Website/main/Kawasan%20Konservasi%202022%20update.zip"
    try:
        r = requests.get(url)
        r.raise_for_status()  # pastikan request berhasil

        with zipfile.ZipFile(io.BytesIO(r.content)) as z:
            shp_files = [f for f in z.namelist() if f.endswith(".shp")]
            if not shp_files:
                raise FileNotFoundError("Tidak ditemukan file .shp di ZIP Kawasan GitHub")

            # Ekstrak ke folder sementara
            with io.BytesIO() as tmpfile:
                tmpfile.write(r.content)
                tmpfile.seek(0)
                with zipfile.ZipFile(tmpfile) as z2:
                    # Pilih shapefile pertama
                    shp_file_name = shp_files[0]
                    with z2.open(shp_file_name) as shp_f:
                        # GeoPandas tidak bisa langsung baca file-like zip internal, jadi ekstrak
                        import tempfile
                        import pathlib
                        with tempfile.TemporaryDirectory() as tmpdir:
                            z2.extractall(tmpdir)
                            gdf = gpd.read_file(pathlib.Path(tmpdir) / shp_file_name)
                            gdf.set_crs(epsg=4326, inplace=True)
                            logger.info(f"Berhasil load {len(gdf)} fitur Kawasan dari GitHub")
                            return gdf
    except Exception as e:
        logger.error(f"Gagal load Kawasan dari GitHub: {e}", exc_info=True)
        return gpd.GeoDataFrame(columns=["NAMA_KK", "geometry"], geometry="geometry", crs="EPSG:4326")
