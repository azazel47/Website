import os
import requests
from dotenv import load_dotenv

load_dotenv()

ARCGIS_URL = os.getenv("ARCGIS_BASEMAP_URL")
ARCGIS_USER = os.getenv("ARCGIS_USERNAME")
ARCGIS_PASS = os.getenv("ARCGIS_PASSWORD")

def get_arcgis_token() -> str:
    """Mendapatkan token dari ArcGIS Server (jika butuh login)"""
    token_url = ARCGIS_URL.replace("/MapServer", "/generateToken")
    payload = {
        "username": ARCGIS_USER,
        "password": ARCGIS_PASS,
        "client": "requestip",
        "f": "json"
    }

    try:
        r = requests.post(token_url, data=payload, verify=False)
        data = r.json()
        return data.get("token")
    except Exception as e:
        print("❌ Gagal mendapatkan token:", e)
        return None
