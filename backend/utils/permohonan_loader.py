import requests
import json
import geopandas as gpd
from typing import Optional
import logging

logger = logging.getLogger(__name__)

# Cache untuk Permohonan data
_Permohonan_cache = None

def load_Permohonan_json() -> Optional[gpd.GeoDataFrame]:
    """
    Loads and parses the Permohonan JSON data from GitHub, converting it to a GeoDataFrame.

    The JSON is expected to be in an ArcGIS format with 'attributes' and 'rings'
    for geometry. This function converts it to a standard GeoJSON-like
    structure before creating the GeoDataFrame.

    Returns:
        GeoDataFrame of Permohonan data if successful, otherwise None
    """
    global _Permohonan_cache

    # Return cached data if available
    if _Permohonan_cache is not None:
        return _Permohonan_cache

    try:
        # Fetch JSON from GitHub
        url = "https://raw.githubusercontent.com/azazel47/Verdok/main/permohonan.json"
        logger.info(f"Fetching Permohonan data from {url}")
        response = requests.get(url, timeout=30)
        response.raise_for_status()
        data = response.json()

        # Convert format ArcGIS (attributes + rings) to GeoJSON (properties + coordinates)
        features = []
        for feat in data.get("features", []):
            if "geometry" in feat and "rings" in feat["geometry"]:
                features.append({
                    "type": "Feature",
                    "properties": feat.get("attributes", {}),
                    "geometry": {
                        "type": "Polygon",
                        "coordinates": feat["geometry"]["rings"]
                    }
                })

        if not features:
            logger.warning("No valid features found in Permohonan JSON")
            return None

        gdf = gpd.GeoDataFrame.from_features(features)
        gdf.set_crs(epsg=4326, inplace=True)

        # Cache the result
        _Permohonan_cache = gdf
        logger.info(f"Successfully loaded {len(gdf)} Permohonan features")

        return gdf

    except requests.RequestException as e:
        logger.error(f"Failed to fetch Permohonan JSON: {e}")
        return None
    except json.JSONDecodeError as e:
        logger.error(f"Failed to decode Permohonan JSON: {e}")
        return None
    except Exception as e:
        logger.error(f"Unexpected error loading Permohonan JSON: {e}")
        return None

def get_Permohonan_metadata() -> dict:
    """
    Get metadata about Permohonan data.

    Returns:
        Dictionary containing metadata
    """
    gdf = load_Permohonan_json()
    if gdf is None:
        return {"status": "error", "message": "Failed to load Permohonan data"}

    return {
        "status": "success",
        "total_features": len(gdf),
        "columns": list(gdf.columns),
        "crs": str(gdf.crs)
    }
