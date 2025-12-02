from fastapi import FastAPI, APIRouter, UploadFile, File, HTTPException, Query
from fastapi.responses import StreamingResponse
from fastapi.responses import FileResponse
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
from shapely.geometry import Point, Polygon
import zipfile
import geopandas as gpd
import tempfile
import shutil
import gc
from contextlib import asynccontextmanager

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

# === GLOBAL FILE PATH ===
# Kita akan menyimpan GeoJSON di folder temporary OS
KKPRL_CACHE_FILE = Path(tempfile.gettempdir()) / "kkprl_cached.geojson"

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("🚀 Server starting... Memuat data KKPRL ke RAM...")
    try:
        gdf = load_kkprl_json()
        if gdf is not None:
            logger.info(f"💾 Menyimpan {len(gdf)} fitur ke file disk: {KKPRL_CACHE_FILE}")
            gdf.to_file(KKPRL_CACHE_FILE, driver="GeoJSON")
            
            del gdf
            gc.collect()
            logger.info("✅ File Cache siap! RAM telah dibersihkan.")
            
        else:
            logger.warning("⚠️ Gagal memuat KKPRL.")
            
    except Exception as e:
        logger.error(f"❌ Error saat startup: {e}")
    
    yield
    
    #logger.info("🛑 Server shutting down...")
    #if client:
        #client.close()

    # Cleanup saat shutdown
    if KKPRL_CACHE_FILE.exists():
        try:
            os.remove(KKPRL_CACHE_FILE)
        except:
            pass
    if client:
        client.close()
        
# Init App dengan Lifespan
app = FastAPI(title="Spatio Downloader API", lifespan=lifespan)

# === CORS CONFIGURATION ===
env_origins = os.environ.get("CORS_ALLOW_ORIGINS", "*")
parsed_origins = [o.strip() for o in env_origins.split(",") if o.strip()]

app.add_middleware(
    CORSMiddleware,
    allow_origins=parsed_origins,
    allow_credentials=True,
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
    return {"message": "Spatio Downloader API - Ready"}

@api_router.get("/kkprl-metadata")
async def kkprl_metadata():
    """Metadata tentang data KKPRL"""
    return get_kkprl_metadata()

@api_router.get("/kkprl-geojson")
async def get_kkprl_geojson():
    if not KKPRL_CACHE_FILE.exist():
    """Mengirim data KKPRL dalam format GeoJSON untuk visualisasi"""
    gdf = load_kkprl_json()
    if gdf is None:
        raise HTTPException(status_code=404, detail="KKPRL data not available")
    gdf.to_file(KKPRL_CACHE_FILE, driver="GeoJSON")
    del gdf
    gc.collect
    
    return FileResponse(
        path=KKPRL_CACHE_FILE, 
        media_type="application/geo+json", 
        filename="kkprl.geojson"
    )
    
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
        
        gc.collect()

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

@api_router.post("/download-shapefile")
async def download_shapefile(request: DownloadShapefileRequest):
    """Generate shapefile (ZIP) dari hasil analisis koordinat"""
    try:
        coords = request.coordinates
        geom_type = request.geometry_type
        filename = request.filename or "hasil_analisis"

        if not coords or len(coords) == 0:
            raise HTTPException(status_code=400, detail="Tidak ada data koordinat")

        print(f"🔍 Struktur koordinat yang diterima: {coords[0] if coords else 'empty'}")
        print(f"🔍 Jumlah koordinat: {len(coords)}, Tipe geometri: {geom_type}")
        
        # Handle berbagai format koordinat dari frontend
        geometries = []
        valid_coords = []
        
        if geom_type == "Point":
            for coord in coords:
                # Cari longitude dengan berbagai kemungkinan field name
                lng = (coord.get("longitude") or coord.get("lng") or 
                       coord.get("x"))
                
                # Cari latitude dengan berbagai kemungkinan field name  
                lat = (coord.get("latitude") or coord.get("lat") or 
                       coord.get("y"))
                
                if lng is not None and lat is not None:
                    try:
                        geometries.append(Point(float(lng), float(lat)))
                        valid_coords.append({
                            "longitude": float(lng),
                            "latitude": float(lat),
                            "id": coord.get("id", f"point_{len(valid_coords)}")
                        })
                    except (ValueError, TypeError) as e:
                        print(f"⚠️ Koordinat tidak valid: {coord}, error: {e}")
                        continue
        
        elif geom_type == "Polygon":
            points = []
            polygon_coords = []
            
            for coord in coords:
                # Handle format yang sama seperti Point
                lng = (coord.get("longitude") or coord.get("lng") or 
                       coord.get("x"))
                
                lat = (coord.get("latitude") or coord.get("lat") or 
                       coord.get("y"))
                
                if lng is not None and lat is not None:
                    try:
                        points.append((float(lng), float(lat)))
                        polygon_coords.append({
                            "longitude": float(lng),
                            "latitude": float(lat),
                            "id": coord.get("id", f"polygon_point_{len(polygon_coords)}")
                        })
                    except (ValueError, TypeError) as e:
                        print(f"⚠️ Koordinat polygon tidak valid: {coord}, error: {e}")
                        continue
            
            if len(points) >= 3:
                # Untuk Polygon, kita hanya punya 1 geometry tapi banyak koordinat
                geometries = [Polygon(points)]
                # Untuk Polygon, kita buat 1 record dengan semua koordinat
                valid_coords = [{
                    "id": "polygon_1",
                    "num_points": len(points),
                    "longitude": points[0][0],  # ambil titik pertama sebagai representasi
                    "latitude": points[0][1]
                }]
            else:
                raise HTTPException(status_code=400, detail="Polygon membutuhkan minimal 3 titik")
        
        else:
            raise HTTPException(status_code=400, detail="geometry_type tidak valid")

        if len(geometries) == 0:
            raise HTTPException(status_code=400, detail="Tidak ada koordinat valid yang dapat diproses")

        print(f"✅ Berhasil memproses {len(geometries)} geometri dari {len(coords)} koordinat input")
        print(f"✅ Jumlah valid_coords: {len(valid_coords)}, Jumlah geometries: {len(geometries)}")

        # Buat GeoDataFrame - pastikan jumlah geometries sama dengan valid_coords
        gdf = gpd.GeoDataFrame(valid_coords, geometry=geometries, crs="EPSG:4326")
        
        # Simpan shapefile ke folder sementara
        tmpdir = tempfile.mkdtemp()
        shp_path = os.path.join(tmpdir, f"{filename}.shp")
        
        try:
            # Export ke shapefile
            gdf.to_file(shp_path, driver='ESRI Shapefile', encoding='utf-8')
            
            # Zip semua file shapefile
            zip_path = os.path.join(tmpdir, f"{filename}.zip")
            with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zipf:
                for file in os.listdir(tmpdir):
                    if file.endswith(('.shp', '.shx', '.dbf', '.prj', '.cpg')):
                        file_path = os.path.join(tmpdir, file)
                        zipf.write(file_path, arcname=file)
            
            print(f"✅ Shapefile berhasil dibuat: {zip_path}")
            
            # Return file response
            return FileResponse(
                path=zip_path,
                media_type="application/zip",
                filename=f"{filename}.zip"
            )
            
        except Exception as e:
            # Cleanup jika error
            if os.path.exists(tmpdir):
                shutil.rmtree(tmpdir)
            raise e

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Gagal membuat shapefile: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Gagal membuat shapefile: {str(e)}")
        

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