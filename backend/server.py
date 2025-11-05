from fastapi import FastAPI, APIRouter, UploadFile, File, HTTPException, Query
from fastapi.responses import StreamingResponse
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
import json

# === Import utils ===
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

# === Setup ===
ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / ".env")

mongo_url = os.environ.get("MONGO_URL")
client = AsyncIOMotorClient(mongo_url) if mongo_url else None
db = client[os.environ.get("DB_NAME", "test")] if client else None

app = FastAPI(title="Spatio Downloader API")
api_router = APIRouter(prefix="/api")

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# === Models ===
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

# === Routes ===
@api_router.get("/")
async def root():
    return {"message": "Spatio Downloader API - Ready"}

@api_router.get("/kkprl-metadata")
async def kkprl_metadata():
    """Metadata tentang data KKPRL"""
    return get_kkprl_metadata()

@api_router.get("/kkprl-geojson")
async def get_kkprl_geojson():
    """Mengirim data KKPRL dalam format GeoJSON untuk visualisasi"""
    gdf = load_kkprl_json()
    if gdf is None:
        raise HTTPException(status_code=404, detail="KKPRL data not available")
    return json.loads(gdf.to_json())

@api_router.post("/status", response_model=StatusCheck)
async def create_status_check(input: StatusCheckCreate):
    status_obj = StatusCheck(client_name=input.client_name)
    doc = status_obj.model_dump()
    doc["timestamp"] = doc["timestamp"].isoformat()
    if db:
        await db.status_checks.insert_one(doc)
    return status_obj

@api_router.get("/status", response_model=List[StatusCheck])
async def get_status_checks():
    if not db:
        return []
    status_checks = await db.status_checks.find({}, {"_id": 0}).to_list(1000)
    for check in status_checks:
        if isinstance(check["timestamp"], str):
            check["timestamp"] = datetime.fromisoformat(check["timestamp"])
    return status_checks

@api_router.post("/analyze-coordinates")
async def analyze_coordinates(
    file: UploadFile = File(...),
    format_type: str = Query(..., description="OSS-UTM or Decimal-Degree"),
    geometry_type: str = Query(..., description="Point or Polygon"),
):
    """Analisis koordinat dari file Excel"""
    try:
        contents = await file.read()
        if len(contents) == 0:
            raise HTTPException(status_code=400, detail="File kosong")

        df = pd.read_excel(BytesIO(contents))
        if df.empty:
            raise HTTPException(status_code=400, detail="Tidak ada data dalam file")

        # === Konversi Koordinat ===
        if format_type == "OSS-UTM":
            required_cols = [
                "bujur_derajat",
                "bujur_menit",
                "bujur_detik",
                "BT_BB",
                "lintang_derajat",
                "lintang_menit",
                "lintang_detik",
                "LU_LS",
            ]
            missing = [c for c in required_cols if c not in df.columns]
            if missing:
                raise HTTPException(status_code=400, detail=f"Kolom hilang: {missing}")

            df["longitude"] = df.apply(
                lambda r: dms_to_dd(r["bujur_derajat"], r["bujur_menit"], r["bujur_detik"], r["BT_BB"]), axis=1
            )
            df["latitude"] = df.apply(
                lambda r: dms_to_dd(r["lintang_derajat"], r["lintang_menit"], r["lintang_detik"], r["LU_LS"]), axis=1
            )
        elif format_type == "Decimal-Degree":
            if "x" not in df.columns or "y" not in df.columns:
                raise HTTPException(status_code=400, detail="Kolom 'x' dan 'y' wajib ada")
            df = df.rename(columns={"x": "longitude", "y": "latitude"})
        else:
            raise HTTPException(status_code=400, detail="format_type tidak valid")

        if "id" not in df.columns:
            df["id"] = [f"point_{i+1}" for i in range(len(df))]

        df = df.head(300)
        coordinates = df[["id", "longitude", "latitude"]].to_dict("records")

        # === Buat GeoDataFrame ===
        if geometry_type == "Point":
            gdf = create_point_geodataframe(coordinates)
        else:
            gdf = create_polygon_geodataframe(coordinates)

        geojson = json.loads(gdf.to_json())

        # === Analisis Overlap KKPRL ===
        kkprl_gdf = load_kkprl_json()
        if kkprl_gdf is not None:
            if geometry_type == "Point":
                overlap_analysis = analyze_point_overlap(gdf, kkprl_gdf)
            else:
                overlap_analysis = analyze_polygon_overlap(gdf, kkprl_gdf)
        else:
            overlap_analysis = {"has_overlap": False, "message": "KKPRL tidak tersedia"}

        # === Analisis 12 Mil Laut dan Kawasan Konservasi ===
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
            "total_rows": len(coordinates),
        }

    except Exception as e:
        logger.error(f"Error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

# === Register Router ===
app.include_router(api_router)

app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=os.environ.get("CORS_ORIGINS", "*").split(","),
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.on_event("shutdown")
async def shutdown_db_client():
    if client:
        client.close()
