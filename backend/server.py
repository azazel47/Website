from fastapi import FastAPI, APIRouter, UploadFile, File, HTTPException, Query
from fastapi.responses import StreamingResponse, FileResponse, JSONResponse
from starlette.middleware.cors import CORSMiddleware
from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient
from shapely.geometry import Point, Polygon
from pyproj import CRS
from io import BytesIO
import geopandas as gpd
import pandas as pd
import tempfile
import zipfile
import os, json, uuid, logging, requests
from pathlib import Path
from datetime import datetime, timezone
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field, ConfigDict

# ==== IMPORT UTILITIES ====
from utils.coordinate_converter import dms_to_dd
from utils.kkprl_loader import load_kkprl_json, get_kkprl_metadata
from utils.mil12_loader import load_12mil_shapefile
from utils.kawasan_loader import load_kawasan_konservasi
from utils.spatial_analysis import (
    create_point_geodataframe,
    create_polygon_geodataframe,
    analyze_point_overlap,
    analyze_polygon_overlap,
    analyze_overlap_12mil,
    analyze_overlap_kawasan,
)

# ==== ENVIRONMENT ====
ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / '.env')

mongo_url = os.environ.get("MONGO_URL")
client = AsyncIOMotorClient(mongo_url)
db = client[os.environ.get("DB_NAME")]

ARCGIS_URL = os.environ.get("ARCGIS_URL", "https://arcgis.ruanglaut.id/arcgis")
ARCGIS_USERNAME = os.environ.get("ARCGIS_USERNAME")
ARCGIS_PASSWORD = os.environ.get("ARCGIS_PASSWORD")

# ==== FASTAPI SETUP ====
app = FastAPI(title="Spatio Downloader API")
api_router = APIRouter(prefix="/api")

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ==== MODELS ====
class StatusCheck(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    client_name: str
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

class StatusCheckCreate(BaseModel):
    client_name: str

class DownloadShapefileRequest(BaseModel):
    coordinates: List[Dict[str, Any]]
    geometry_type: str
    filename: Optional[str] = "output"

# ==== GENERATE ARCGIS TOKEN ====
@app.get("/api/arcgis-token")
def get_arcgis_token():
    token_url = f"{ARCGIS_BASE_URL}/tokens/generateToken"

    payload = {
        "username": ARCGIS_USERNAME,
        "password": ARCGIS_PASSWORD,
        "client": "requestip",
        "f": "json"
    }

    try:
        res = requests.post(token_url, data=payload, timeout=10)
        data = res.json()
        if "token" in data:
            return {"success": True, "token": data["token"], "expires": data["expires"]}
        else:
            return {"success": False, "error": data}
    except Exception as e:
        return JSONResponse(content={"success": False, "error": str(e)}, status_code=500)

# ==== PROXY UNTUK ARCGIS MAP SERVICE ====
@api_router.get("/proxy/arcgis")
def proxy_arcgis(x: int, y: int, z: int):
    """Proxy untuk ambil tile dari ArcGIS MapServer"""
    try:
        token_data = get_arcgis_token()
        token = token_data.get("token") if isinstance(token_data, dict) else token_data
        arcgis_tile_url = f"{ARCGIS_URL}/rest/services/KKPRL/KKPRL/MapServer/tile/{z}/{y}/{x}?token={token}"

        resp = requests.get(arcgis_tile_url, verify=False, timeout=10)
        if resp.status_code == 200:
            return StreamingResponse(BytesIO(resp.content), media_type="image/png")
        else:
            raise HTTPException(status_code=resp.status_code, detail=f"Gagal ambil tile dari ArcGIS: {resp.status_code}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# ==== SHAPEFILE DOWNLOAD ====
@api_router.post("/download-shapefile")
async def download_shapefile(request: DownloadShapefileRequest):
    try:
        coords, geom_type = request.coordinates, request.geometry_type
        filename = request.filename or "hasil_analisis"

        if not coords:
            raise HTTPException(status_code=400, detail="Tidak ada data koordinat")

        df = pd.DataFrame(coords)
        if geom_type == "Point":
            geometries = [Point(c["longitude"], c["latitude"]) for c in coords]
        elif geom_type == "Polygon":
            points = [(c["longitude"], c["latitude"]) for c in coords]
            geometries = [Polygon(points)]
            df = pd.DataFrame([{"id": "polygon_1"}])
        else:
            raise HTTPException(status_code=400, detail="geometry_type tidak valid")

        gdf = gpd.GeoDataFrame(df, geometry=geometries, crs="EPSG:4326")

        tmpdir = tempfile.mkdtemp()
        base = os.path.join(tmpdir, filename)
        gdf.to_file(base + ".shp", driver="ESRI Shapefile")

        # tulis .prj manual
        crs = CRS.from_epsg(4326)
        with open(base + ".prj", "w") as f:
            f.write(crs.to_wkt())

        # zip
        zip_path = base + ".zip"
        with zipfile.ZipFile(zip_path, "w") as zipf:
            for ext in [".shp", ".shx", ".dbf", ".prj", ".cpg"]:
                fpath = base + ext
                if os.path.exists(fpath):
                    zipf.write(fpath, arcname=os.path.basename(fpath))

        return FileResponse(zip_path, media_type="application/zip", filename=f"{filename}.zip")
    except Exception as e:
        logger.error(e, exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

# ==== ANALISIS KOORDINAT ====
@api_router.post("/analyze-coordinates")
async def analyze_coordinates(file: UploadFile = File(...), format_type: str = Query(...), geometry_type: str = Query(...)):
    try:
        contents = await file.read()
        df = pd.read_excel(BytesIO(contents))
        if df.empty:
            raise HTTPException(status_code=400, detail="Excel kosong")

        if format_type == "Decimal-Degree":
            df = df.rename(columns={"x": "longitude", "y": "latitude"})
        elif format_type == "OSS-UTM":
            df["longitude"] = df.apply(lambda r: dms_to_dd(r["bujur_derajat"], r["bujur_menit"], r["bujur_detik"], r["BT_BB"]), axis=1)
            df["latitude"] = df.apply(lambda r: dms_to_dd(r["lintang_derajat"], r["lintang_menit"], r["lintang_detik"], r["LU_LS"]), axis=1)

        if "id" not in df.columns:
            df["id"] = [f"point_{i+1}" for i in range(len(df))]

        coords = df[["id", "longitude", "latitude"]].to_dict("records")
        gdf = create_point_geodataframe(coords) if geometry_type == "Point" else create_polygon_geodataframe(coords)
        geojson = json.loads(gdf.to_json())

        kkprl_gdf = load_kkprl_json()
        overlap_analysis = analyze_point_overlap(gdf, kkprl_gdf) if geometry_type == "Point" else analyze_polygon_overlap(gdf, kkprl_gdf)
        overlap_12mil = analyze_overlap_12mil(gdf)
        overlap_kawasan = analyze_overlap_kawasan(gdf)

        return {
            "success": True,
            "coordinates": coords,
            "geometry_type": geometry_type,
            "geojson": geojson,
            "overlap_analysis": overlap_analysis,
            "overlap_12mil": overlap_12mil,
            "overlap_kawasan": overlap_kawasan,
        }
    except Exception as e:
        logger.error(e, exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

# ==== APP SETUP ====
app.include_router(api_router)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.on_event("shutdown")
async def shutdown_db_client():
    client.close()
