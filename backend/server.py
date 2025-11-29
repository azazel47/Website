from fastapi import FastAPI, APIRouter, UploadFile, File, HTTPException, Query
from fastapi.responses import StreamingResponse, FileResponse
from fastapi.middleware.cors import CORSMiddleware # Perbaikan import
from motor.motor_asyncio import AsyncIOMotorClient
import os
import uvicorn
import logging
from pathlib import Path
from pydantic import BaseModel, Field, ConfigDict
from typing import List, Optional, Dict, Any
import uuid
from datetime import datetime, timezone
import pandas as pd
from io import BytesIO
import json
from shapely.geometry import Point, Polygon
import zipfile
import geopandas as gpd
import tempfile
import shutil
# Import penting untuk startup/shutdown handler modern
from contextlib import asynccontextmanager

# === Import utils ===
# Pastikan file-file ini ada di folder utils/
from utils.coordinate_converter import dms_to_dd
from utils.kkprl_loader import load_kkprl_json, get_kkprl_metadata
from utils.mil12_loader import load_12mil_shapefile, analyze_overlap_12mil
from utils.kawasan_loader import load_kawasan_konservasi, analyze_overlap_kawasan
from utils.spatial_analysis import (
    create_point_geodataframe,
    create_polygon_geodataframe,
    analyze_point_overlap,
    analyze_polygon_overlap,
)

# === Setup Logging ===
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("uvicorn.info")

# === Setup Env & DB ===
ROOT_DIR = Path(__file__).parent
from dotenv import load_dotenv
load_dotenv(ROOT_DIR / ".env")

mongo_url = os.environ.get("MONGO_URL")
client = AsyncIOMotorClient(mongo_url) if mongo_url else None
db = client[os.environ.get("DB_NAME", "test")] if client else None

# === LIFESPAN (PENTING UNTUK RAILWAY) ===
# Kode ini dijalankan SATU KALI saat server baru nyala
@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("🚀 Server starting... Memuat data Spasial ke Memori...")
    
    # 1. Load Data KKPRL (Berat) saat startup
    try:
        kkprl_gdf = load_kkprl_json()
        if kkprl_gdf is not None:
            logger.info(f"✅ Data KKPRL berhasil dimuat: {len(kkprl_gdf)} features")
        else:
            logger.warning("⚠️ Data KKPRL gagal dimuat saat startup (akan dicoba lagi saat request)")
    except Exception as e:
        logger.error(f"❌ Error loading KKPRL: {e}")

    # 2. Load Data Lain (Opsional, jika ingin dimuat di awal)
    # load_12mil_shapefile()
    
    yield # Server berjalan melayani request di sini

    # Shutdown logic
    logger.info("🛑 Server shutting down...")
    if client:
        client.close()
        logger.info("✅ MongoDB connection closed")

# === Init App ===
app = FastAPI(title="Spatio Downloader API", lifespan=lifespan)

# === CORS SETUP ===
env_origins = os.environ.get("CORS_ALLOW_ORIGINS", "")
parsed_origins = [o.strip() for o in env_origins.split(",") if o.strip()]

# Fallback aman: jika tidak ada env, izinkan semua (hati-hati di production)
if not parsed_origins:
    parsed_origins = ["*"]

app.add_middleware(
    CORSMiddleware,
    allow_origins=parsed_origins,
    allow_credentials=True, # WAJIB True agar frontend Vercel bisa akses response
    allow_methods=["*"],
    allow_headers=["*"],
)

api_router = APIRouter(prefix="/api")

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
    return {
        "message": "Spatio Downloader API - Ready",
        "cors_origins": parsed_origins
    }

@api_router.get("/kkprl-metadata")
async def kkprl_metadata():
    """Metadata tentang data KKPRL"""
    return get_kkprl_metadata()

@api_router.get("/kkprl-geojson")
async def get_kkprl_geojson():
    """Mengirim data KKPRL dalam format GeoJSON"""
    # Fungsi ini akan mengambil data yang SUDAH di-cache oleh lifespan
    gdf = load_kkprl_json()
    
    if gdf is None:
        raise HTTPException(status_code=500, detail="KKPRL data not available (Gagal dimuat di server)")
    
    # Konversi ke JSON (Hati-hati, jika data >50MB bisa lambat)
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
                "bujur_derajat", "bujur_menit", "bujur_detik", "BT_BB",
                "lintang_derajat", "lintang_menit", "lintang_detik", "LU_LS",
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
            # Normalisasi nama kolom (case insensitive handling bisa ditambahkan jika perlu)
            if "x" in df.columns: df.rename(columns={"x": "longitude"}, inplace=True)
            if "y" in df.columns: df.rename(columns={"y": "latitude"}, inplace=True)
            
            if "longitude" not in df.columns or "latitude" not in df.columns:
                raise HTTPException(status_code=400, detail="Kolom 'longitude'/'x' dan 'latitude'/'y' wajib ada")
        else:
            raise HTTPException(status_code=400, detail="format_type tidak valid")

        if "id" not in df.columns:
            df["id"] = [f"point_{i+1}" for i in range(len(df))]

        df = df.head(300) # Batasi 300 baris untuk keamanan performa
        coordinates = df[["id", "longitude", "latitude"]].to_dict("records")

        # === Buat GeoDataFrame ===
        if geometry_type == "Point":
            gdf = create_point_geodataframe(coordinates)
        else:
            gdf = create_polygon_geodataframe(coordinates)

        geojson = json.loads(gdf.to_json())

        # === Analisis Overlap KKPRL ===
        # Mengambil dari cache memory (cepat)
        kkprl_gdf = load_kkprl_json()
        
        if kkprl_gdf is not None:
            if geometry_type == "Point":
                overlap_analysis = analyze_point_overlap(gdf, kkprl_gdf)
            else:
                overlap_analysis = analyze_polygon_overlap(gdf, kkprl_gdf)
        else:
            overlap_analysis = {"has_overlap": False, "message": "KKPRL tidak tersedia (Gagal Load)"}

        # === Analisis Lainnya ===
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
        logger.error(f"Error Analisis: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

@api_router.post("/download-shapefile")
async def download_shapefile(request: DownloadShapefileRequest):
    """Generate shapefile (ZIP) dari hasil analisis koordinat"""
    try:
        coords = request.coordinates
        geom_type = request.geometry_type
        filename = request.filename or "hasil_analisis"

        if not coords or len(coords) == 0:
            raise HTTPException(status_code=400, detail="Tidak ada data koordinat")

        # Handle berbagai format koordinat
        geometries = []
        valid_coords = []
        
        if geom_type == "Point":
            for coord in coords:
                lng = coord.get("longitude") or coord.get("lng") or coord.get("x")
                lat = coord.get("latitude") or coord.get("lat") or coord.get("y")
                
                if lng is not None and lat is not None:
                    try:
                        geometries.append(Point(float(lng), float(lat)))
                        valid_coords.append({
                            "longitude": float(lng),
                            "latitude": float(lat),
                            "id": coord.get("id", f"point_{len(valid_coords)}")
                        })
                    except (ValueError, TypeError):
                        continue
        
        elif geom_type == "Polygon":
            points = []
            for coord in coords:
                lng = coord.get("longitude") or coord.get("lng") or coord.get("x")
                lat = coord.get("latitude") or coord.get("lat") or coord.get("y")
                
                if lng is not None and lat is not None:
                    try:
                        points.append((float(lng), float(lat)))
                    except (ValueError, TypeError):
                        continue
            
            if len(points) >= 3:
                geometries = [Polygon(points)]
                valid_coords = [{
                    "id": "polygon_1",
                    "num_points": len(points),
                    "longitude": points[0][0],
                    "latitude": points[0][1]
                }]
            else:
                raise HTTPException(status_code=400, detail="Polygon membutuhkan minimal 3 titik")
        
        else:
            raise HTTPException(status_code=400, detail="geometry_type tidak valid")

        if len(geometries) == 0:
            raise HTTPException(status_code=400, detail="Tidak ada geometri valid")

        # Export Shapefile
        gdf = gpd.GeoDataFrame(valid_coords, geometry=geometries, crs="EPSG:4326")
        
        tmpdir = tempfile.mkdtemp()
        shp_path = os.path.join(tmpdir, f"{filename}.shp")
        
        try:
            gdf.to_file(shp_path, driver='ESRI Shapefile', encoding='utf-8')
            zip_path = os.path.join(tmpdir, f"{filename}.zip")
            with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zipf:
                for file in os.listdir(tmpdir):
                    if file.endswith(('.shp', '.shx', '.dbf', '.prj', '.cpg')):
                        zipf.write(os.path.join(tmpdir, file), arcname=file)
            
            return FileResponse(
                path=zip_path,
                media_type="application/zip",
                filename=f"{filename}.zip"
            )
        except Exception as e:
            if os.path.exists(tmpdir): shutil.rmtree(tmpdir)
            raise e

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Gagal membuat shapefile: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Gagal membuat shapefile: {str(e)}")
        
@app.options("/{rest_of_path:path}")
async def cors_preflight(rest_of_path: str):
    return {}

# === Register Router ===
app.include_router(api_router)

if __name__ == "__main__":
    # Gunakan default 8080 jika env var tidak ada (aman untuk local & production)
    port = int(os.environ.get("PORT", 8080))
    uvicorn.run("server:app", host="0.0.0.0", port=port)