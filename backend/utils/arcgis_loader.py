import os
import requests
from dotenv import load_dotenv

load_dotenv()

ARCGIS_URL = os.getenv("ARCGIS_BASEMAP_URL")
ARCGIS_USER = os.getenv("ARCGIS_USERNAME")
ARCGIS_PASS = os.getenv("ARCGIS_PASSWORD")

def get_arcgis_token() -> str:
    """Ambil token dari ArcGIS Server"""
    token_url = ARCGIS_URL.split("/MapServer")[0] + "/generateToken"
    payload = {
        "username": ARCGIS_USER,
        "password": ARCGIS_PASS,
        "client": "requestip",
        "f": "json"
    }

    try:
        r = requests.post(token_url, data=payload, verify=False)
        r.raise_for_status()
        data = r.json()
        if "token" in data:
            return data["token"]
        else:
            print("❌ Gagal ambil token:", data)
            return None
    except Exception as e:
        print(f"❌ Error token request: {e}")
        return None
