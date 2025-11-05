from fastapi import FastAPI, APIRouter, UploadFile, File, HTTPException, Query
from fastapi.responses import StreamingResponse, FileResponse
from dotenv import load_dotenv
from starlette.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
import os
import logging
from pathlib import Path
from pydantic import BaseModel, Field, ConfigDict
from typing import List, Optional, Dict, Any
import uuid
from datetime import datetime, timezone
import pandas as pd
from io import BytesIO
import tempfile
import zipfile
import json
import geopandas as gpd
from shapely.geometry import Point, Polygon
import requests
from pyproj import CRS
from utils.arcgis_loader import get_arcgis_token

# Import utility functions
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

# ========== ENV & CONFIG ==========
ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / '.env')

mongo_url = os.environ['MONGO_URL']
client = AsyncIOMotorClient(mongo_url)
db = client[os.environ['DB_NAME']]

# ArcGIS Server credentials (gunakan .env)
ARCGIS_URL = os.environ.get("ARCGIS_URL", "https://arcgis.ruanglaut.id/arcgis/")
ARCGIS_USERNAME = os.environ.get("ARCGIS_USERNAME", "admin")
ARCGIS_PASSWORD = os.environ.get("ARCGIS_PASSWORD", "password")

# ========== FASTAPI SETUP ==========
app = FastAPI()
api_router = APIRouter(prefix="/api")

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# ========== MODELS ==========
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

# ========== ENDPOINT: Generate ArcGIS Token ==========
@api_router.get("/arcgis-token")
def get_arcgis_token():
    """Generate token dari ArcGIS Server (gunakan untuk akses Map Service pribadi)"""
    token_url = f"{ARCGIS_URL}/admin/generateToken"
    payload = {
        "username": ARCGIS_USERNAME,
        "password": ARCGIS_PASSWORD,
        "client": "requestip",
        "f": "json",
        "expiration": 60
    }

    try:
        response = requests.post(token_url, data=payload, verify=False)
        data = response.json()
        if "token" in data:
            logger.info("✅ Token ArcGIS berhasil dibuat")
            return {"success": True, "token": data["token"], "expires": data.get("expires")}
        else:
            logger.error(f"❌ Gagal membuat token: {data}")
            return {"success": False, "error": data.get("error", "Token generation failed")}
    except Exception as e:
        logger.error(f"Error membuat token ArcGIS: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# ========== ENDPOINT: Download Shapefile ==========
@api_router.post("/download-shapefile")
async def download_shapefile(request: DownloadShapefileRequest):
    try:
        coords = request.coordinates
        geom_type = request.geometry_type
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
        shp_path = os.path.join(tmpdir, f"{filename}.shp")

        gdf.to_file(shp_path, driver="ESRI Shapefile")

        # tulis file .prj manual
        crs = CRS.from_epsg(4326)
        with open(os.path.join(tmpdir, f"{filename}.prj"), "w") as f:
            f.write(crs.to_wkt())

        # zip shapefile
        zip_path = os.path.join(tmpdir, f"{filename}.zip")
        with zipfile.ZipFile(zip_path, "w") as zipf:
            for ext in [".shp", ".shx", ".dbf", ".prj", ".cpg"]:
                f = os.path.join(tmpdir, f"{filename}{ext}")
                if os.path.exists(f):
                    zipf.write(f, arcname=os.path.basename(f))

        logger.info(f"✅ Shapefile berhasil dibuat: {zip_path}")
        return FileResponse(zip_path, media_type="application/zip", filename=f"{filename}.zip")

    except Exception as e:
        logger.error(f"Gagal membuat shapefile: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Gagal membuat shapefile: {str(e)}")

# ========== ENDPOINT LAIN ==========
@api_router.get("/")
async def root():
    return {"message": "Spatio Downloader API - Ready"}

@api_router.post("/status", response_model=StatusCheck)
async def create_status_check(input: StatusCheckCreate):
    status_obj = StatusCheck(**input.model_dump())
    doc = status_obj.model_dump()
    doc['timestamp'] = doc['timestamp'].isoformat()
    await db.status_checks.insert_one(doc)
    return status_obj

@api_router.get("/status", response_model=List[StatusCheck])
async def get_status_checks():
    status_checks = await db.status_checks.find({}, {"_id": 0}).to_list(1000)
    for check in status_checks:
        if isinstance(check['timestamp'], str):
            check['timestamp'] = datetime.fromisoformat(check['timestamp'])
    return status_checks

@api_router.get("/kkprl-metadata")
async def kkprl_metadata():
    return get_kkprl_metadata()

# ========== ANALISIS KOORDINAT ==========
@api_router.post("/analyze-coordinates")
async def analyze_coordinates(
    file: UploadFile = File(...),
    format_type: str = Query(...),
    geometry_type: str = Query(...)
):
    try:
        contents = await file.read()
        df = pd.read_excel(BytesIO(contents))
        if df.empty:
            raise HTTPException(status_code=400, detail="Excel kosong")

        if format_type == "Decimal-Degree":
            df = df.rename(columns={'x': 'longitude', 'y': 'latitude'})
        elif format_type == "OSS-UTM":
            df['longitude'] = df.apply(
                lambda r: dms_to_dd(r['bujur_derajat'], r['bujur_menit'], r['bujur_detik'], r['BT_BB']), axis=1)
            df['latitude'] = df.apply(
                lambda r: dms_to_dd(r['lintang_derajat'], r['lintang_menit'], r['lintang_detik'], r['LU_LS']), axis=1)
        else:
            raise HTTPException(status_code=400, detail="format_type invalid")

        if 'id' not in df.columns:
            df['id'] = [f"point_{i+1}" for i in range(len(df))]

        coordinates = df[['id', 'longitude', 'latitude']].to_dict('records')

        gdf = create_point_geodataframe(coordinates) if geometry_type == "Point" else create_polygon_geodataframe(coordinates)
        geojson = json.loads(gdf.to_json())

        # Analisis
        kkprl_gdf = load_kkprl_json()
        overlap_analysis = analyze_point_overlap(gdf, kkprl_gdf) if geometry_type == "Point" else analyze_polygon_overlap(gdf, kkprl_gdf)
        overlap_12mil = analyze_overlap_12mil(gdf)
        overlap_kawasan = analyze_overlap_kawasan(gdf)

        return {
            "success": True,
            "coordinates": coordinates,
            "geometry_type": geometry_type,
            "geojson": geojson,
            "overlap_analysis": overlap_analysis,
            "overlap_12mil": overlap_12mil,
            "overlap_kawasan": overlap_kawasan,
        }

    except Exception as e:
        logger.error(f"Error analyzing coordinates: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

# ========== APP SETUP ==========
app.include_router(api_router)

app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=os.environ.get('CORS_ORIGINS', '*').split(','),
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.on_event("shutdown")
async def shutdown_db_client():
    client.close()
