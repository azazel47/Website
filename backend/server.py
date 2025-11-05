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
import tempfile
import zipfile
import json
import geopandas as gpd

# Import utility functions
from utils.coordinate_converter import dms_to_dd
from utils.kkprl_loader import load_kkprl_json, get_kkprl_metadata
from utils.mil12_loader import load_12mil_shapefile
from utils.kawasan_loader import load_kawasan_konservasi
from fastapi.responses import FileResponse
from shapely.geometry import Point, Polygon
from utils.spatial_analysis import (
    create_point_geodataframe,
    create_polygon_geodataframe,
    analyze_point_overlap,
    analyze_polygon_overlap,
    analyze_overlap_12mil,
    analyze_overlap_kawasan,
)

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / '.env')

# MongoDB connection
mongo_url = os.environ['MONGO_URL']
client = AsyncIOMotorClient(mongo_url)
db = client[os.environ['DB_NAME']]

# Create the main app without a prefix
app = FastAPI()

# Create a router with the /api prefix
api_router = APIRouter(prefix="/api")

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Define Models
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

@api_router.post("/download-shapefile")
async def download_shapefile(request: DownloadShapefileRequest):
    """Generate shapefile (ZIP) dari hasil analisis koordinat"""
    try:
        coords = request.coordinates
        geom_type = request.geometry_type
        filename = request.filename or "hasil_analisis"

        if not coords or len(coords) == 0:
            raise HTTPException(status_code=400, detail="Tidak ada data koordinat")

        # Buat GeoDataFrame dari koordinat
        df = pd.DataFrame(coords)

        if geom_type == "Point":
            geometries = [Point(c["longitude"], c["latitude"]) for c in coords]
        elif geom_type == "Polygon":
            points = [(c["longitude"], c["latitude"]) for c in coords]
            geometries = [Polygon(points)]
            df = pd.DataFrame([{"id": "polygon_1"}])  # satu baris saja
        else:
            raise HTTPException(status_code=400, detail="geometry_type tidak valid")

        gdf = gpd.GeoDataFrame(df, geometry=geometries, crs="EPSG:4326")

        # Simpan shapefile ke folder sementara
        tmpdir = tempfile.mkdtemp()
        shp_path = os.path.join(tmpdir, f"{filename}.shp")

        from pyproj import CRS
        gdf.to_file(shp_path, driver="ESRI Shapefile")

        # tulis file .prj manual
        crs = CRS.from_epsg(4326)
        with open(os.path.join(tmpdir, f"{filename}.prj"), "w") as f:
            f.write(crs.to_wkt())

        # Zip semua file shapefile
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
      
# Routes
@api_router.get("/")
async def root():
    return {"message": "Spatio Downloader API - Ready"}

@api_router.post("/status", response_model=StatusCheck)
async def create_status_check(input: StatusCheckCreate):
    status_dict = input.model_dump()
    status_obj = StatusCheck(**status_dict)
    
    doc = status_obj.model_dump()
    doc['timestamp'] = doc['timestamp'].isoformat()
    
    _ = await db.status_checks.insert_one(doc)
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
    """Get metadata about KKPRL data"""
    return get_kkprl_metadata()
    
@api_router.post("/analyze-coordinates")
async def analyze_coordinates(
    file: UploadFile = File(...),
    format_type: str = Query(..., description="OSS-UTM or Decimal-Degree"),
    geometry_type: str = Query(..., description="Point or Polygon")
):
    """Analyze coordinates from Excel file"""
    try:
        # Read Excel file
        contents = await file.read()
        if len(contents) == 0:
            raise HTTPException(status_code=400, detail="File is empty")
        
        df = pd.read_excel(BytesIO(contents))
        
        if df.empty:
            raise HTTPException(status_code=400, detail="Excel file contains no data")
        
        # Coordinate conversion based on format_type
        if format_type == "OSS-UTM":
            required_cols = ['bujur_derajat', 'bujur_menit', 'bujur_detik', 'BT_BB',
                             'lintang_derajat', 'lintang_menit', 'lintang_detik', 'LU_LS']
            missing_cols = [col for col in required_cols if col not in df.columns]
            if missing_cols:
                raise HTTPException(
                    status_code=400, 
                    detail=f"Missing columns for OSS-UTM format: {missing_cols}"
                )
            
            # Convert DMS to DD
            df['longitude'] = df.apply(
                lambda row: dms_to_dd(
                    row['bujur_derajat'], 
                    row['bujur_menit'], 
                    row['bujur_detik'], 
                    row['BT_BB']
                ), 
                axis=1
            )
            df['latitude'] = df.apply(
                lambda row: dms_to_dd(
                    row['lintang_derajat'], 
                    row['lintang_menit'], 
                    row['lintang_detik'], 
                    row['LU_LS']
                ), 
                axis=1
            )
        elif format_type == "Decimal-Degree":
            if 'x' not in df.columns or 'y' not in df.columns:
                raise HTTPException(
                    status_code=400, 
                    detail="Decimal-Degree format requires 'x' and 'y' columns"
                )
            df = df.rename(columns={'x': 'longitude', 'y': 'latitude'})
        else:
            raise HTTPException(
                status_code=400, 
                detail="format_type must be 'OSS-UTM' or 'Decimal-Degree'"
            )
        
        # Ensure id column exists
        if 'id' not in df.columns:
            df['id'] = [f"point_{i+1}" for i in range(len(df))]
        
        # Limit to 300 rows
        if len(df) > 300:
            logger.warning(f"Data truncated from {len(df)} to 300 rows")
            df = df.head(300)
        
        # Convert to list of dicts
        coordinates = df[['id', 'longitude', 'latitude']].to_dict('records')
        
        # Create GeoDataFrame based on geometry_type
        if geometry_type == "Point":
            gdf = create_point_geodataframe(coordinates)
        elif geometry_type == "Polygon":
            gdf = create_polygon_geodataframe(coordinates)
        else:
            raise HTTPException(
                status_code=400, 
                detail="geometry_type must be 'Point' or 'Polygon'"
            )
        
        # Convert to GeoJSON (for frontend)
        geojson = json.loads(gdf.to_json())
        
        # === KKPRL Overlap Analysis ===
        kkprl_gdf = load_kkprl_json()
        if kkprl_gdf is not None:
            if geometry_type == "Point":
                overlap_analysis = analyze_point_overlap(gdf, kkprl_gdf)
            else:
                overlap_analysis = analyze_polygon_overlap(gdf, kkprl_gdf)
        else:
            overlap_analysis = {
                "has_overlap": False,
                "message": "KKPRL data not available"
            }
        
        # === Analisis 12 Mil Laut ===
        # === Analisis 12 Mil Laut ===
        overlap_12mil = analyze_overlap_12mil(gdf)
        #mil12_gdf = load_12mil_shapefile()
        #if mil12_gdf is not None:
            # call the helper that returns {"has_overlap", "wp_list", "message", ...}
            #overlap_12mil = analyze_overlap_12mil(gdf, mil12_gdf)
        #else:
            #overlap_12mil = {"has_overlap": False, "message": "Data 12 mil laut tidak tersedia"}
        
        # === Analisis Kawasan Konservasi ===
        overlap_kawasan = analyze_overlap_kawasan(gdf)
        #kawasan_gdf = load_kawasan_konservasi()
        #if kawasan_gdf is not None:
            #overlap_kawasan = analyze_overlap_kawasan(gdf, kawasan_gdf)
        #else:
            #overlap_kawasan = {"has_overlap": False, "message": "Data Kawasan Konservasi tidak tersedia"}
    
    # Final response
        return {
            "success": True,
            "coordinates": coordinates,
            "geometry_type": geometry_type,
            "geojson": geojson,
            "overlap_analysis": overlap_analysis,
            "total_rows": len(coordinates),
            "overlap_12mil": overlap_12mil,
            "overlap_kawasan": overlap_kawasan,
        }

    except pd.errors.EmptyDataError:
        raise HTTPException(status_code=400, detail="Excel file is empty or invalid")
    except HTTPException:
        # re-raise FastAPI HTTPExceptions unchanged
        raise
    except Exception as e:
        logger.error(f"Error analyzing coordinates: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))
# Include the router in the main app
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
