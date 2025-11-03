import requests
import json
import geopandas as gpd
from typing import Optional
import logging
from functools import lru_cache

logger = logging.getLogger(__name__)

# Cache untuk KKPRL data
_kkprl_cache = None

@lru_cache(maxsize=1)
def load_kkprl_json() -> Optional[gpd.GeoDataFrame]:
    """
    Loads and parses the KKPRL JSON data from GitHub dengan caching
    """
    global _kkprl_cache

    # Return cached data if available
    if _kkprl_cache is not None:
        return _kkprl_cache

    try:
        # Fetch JSON dari GitHub
        url = "https://raw.githubusercontent.com/azazel47/Verdok/main/kkprl.json"
        logger.info(f"Fetching KKPRL data from {url}")
        response = requests.get(url, timeout=30)
        response.raise_for_status()
        data = response.json()

        # Convert format ArcGIS ke GeoJSON
        features = []
        for feat in data.get("features", []):
            if "geometry" in feat and "rings" in feat["geometry"]:
                # Pastikan rings tidak kosong
                rings = feat["geometry"]["rings"]
                if rings and len(rings) > 0:
                    features.append({
                        "type": "Feature",
                        "properties": feat.get("attributes", {}),
                        "geometry": {
                            "type": "Polygon",
                            "coordinates": rings
                        }
                    })

        if not features:
            logger.warning("No valid features found in KKPRL JSON")
            return None

        # Buat GeoDataFrame
        gdf = gpd.GeoDataFrame.from_features(features)
        
        # Pastikan CRS
        if gdf.crs is None:
            gdf.set_crs(epsg=4326, inplace=True)
        elif gdf.crs != "EPSG:4326":
            gdf = gdf.to_crs("EPSG:4326")

        # Optimasi: Pilih hanya kolom yang diperlukan
        expected_columns = ["KEGIATAN", "NAMA", "LOKASI", "NO_KKPRL"]
        available_columns = [col for col in expected_columns if col in gdf.columns]
        
        # Tambahkan kolom yang tidak ada dengan nilai default
        for col in expected_columns:
            if col not in gdf.columns:
                gdf[col] = "Tidak Dikenal"
        
        # Cache hasil
        _kkprl_cache = gdf
        logger.info(f"Successfully loaded {len(gdf)} KKPRL features")

        return gdf

    except requests.RequestException as e:
        logger.error(f"Failed to fetch KKPRL JSON: {e}")
        return None
    except json.JSONDecodeError as e:
        logger.error(f"Failed to decode KKPRL JSON: {e}")
        return None
    except Exception as e:
        logger.error(f"Unexpected error loading KKPRL JSON: {e}")
        return None

def get_kkprl_metadata() -> dict:
    """
    Get metadata tentang KKPRL data.
    """
    gdf = load_kkprl_json()
    if gdf is None:
        return {"status": "error", "message": "Failed to load KKPRL data"}

    return {
        "status": "success",
        "total_features": len(gdf),
        "columns": list(gdf.columns),
        "crs": str(gdf.crs),
        "bounds": gdf.total_bounds.tolist() if not gdf.empty else []
    }

def clear_kkprl_cache():
    """Bersihkan cache KKPRL"""
    global _kkprl_cache
    _kkprl_cache = None
    load_kkprl_json.cache_clear()
    logger.info("KKPRL cache cleared")
