from fastapi import FastAPI, APIRouter, UploadFile, File, HTTPException, Query, BackgroundTasks
from fastapi.responses import StreamingResponse
from fastapi.middleware.gzip import GZipMiddleware
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
import asyncio
from concurrent.futures import ThreadPoolExecutor
import time

# Import utility functions yang sudah dioptimasi
from utils.coordinate_converter import dms_to_dd
from utils.kkprl_loader import load_kkprl_json, get_kkprl_metadata, clear_kkprl_cache
from utils.mil12_loader import load_12mil_shapefile, clear_12mil_cache
from utils.kawasan_loader import load_kawasan_konservasi, clear_kawasan_cache

from utils.spatial_analysis import (
    create_point_geodataframe,
    create_polygon_geodataframe,
    analyze_all_layers,
    clear_cache,
    get_analysis_stats
)

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / '.env')

# MongoDB connection dengan timeout
mongo_url = os.environ['MONGO_URL']
client = AsyncIOMotorClient(
    mongo_url, 
    maxPoolSize=10,
    minPoolSize=1,
    maxIdleTimeMS=30000,
    serverSelectionTimeoutMS=5000
)
db = client[os.environ['DB_NAME']]

# Create the main app without a prefix
app = FastAPI(
    title="Spatial Analysis API",
    description="Optimized Spatial Analysis API for maritime boundary checking",
    version="2.0.0"
)

# Create a router with the /api prefix
api_router = APIRouter(prefix="/api")

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Thread pool untuk operasi CPU-intensive
thread_pool = ThreadPoolExecutor(max_workers=4)

# Cache untuk data preprocessing
_preprocessed_data = {}
_MAX_ROWS = 300  # Batas maksimal rows untuk analisis

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

class AnalysisResponse(BaseModel):
    success: bool
    coordinates: List[Dict[str, Any]]
    geometry_type: str
    geojson: Dict[str, Any]
    total_rows: int
    analysis_time: float
    overlap_12mil: Dict[str, Any]
    overlap_kawasan: Dict[str, Any]
    overlap_kkprl: Dict[str, Any]

# Helper functions
async def run_in_threadpool(func, *args, **kwargs):
    """Run blocking functions in thread pool"""
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(thread_pool, func, *args, **kwargs)

def preprocess_excel_data(contents: bytes, format_type: str, geometry_type: str) -> Dict[str, Any]:
    """Preprocess Excel data dengan optimasi"""
    start_time = time.time()
    
    # Read Excel file dengan optimasi
    df = pd.read_excel(BytesIO(contents), engine='openpyxl')
    
    if df.empty:
        raise ValueError("Excel file contains no data")
    
    # Batasi jumlah rows
    if len(df) > _MAX_ROWS:
        logger.warning(f"Data truncated from {len(df)} to {_MAX_ROWS} rows")
        df = df.head(_MAX_ROWS)
    
    # Coordinate conversion based on format_type
    if format_type == "OSS-UTM":
        required_cols = ['bujur_derajat', 'bujur_menit', 'bujur_detik', 'BT_BB',
                         'lintang_derajat', 'lintang_menit', 'lintang_detik', 'LU_LS']
        missing_cols = [col for col in required_cols if col not in df.columns]
        if missing_cols:
            raise ValueError(f"Missing columns for OSS-UTM format: {missing_cols}")
        
        # Optimasi: Gunakan vectorized operations untuk konversi DMS to DD
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
            raise ValueError("Decimal-Degree format requires 'x' and 'y' columns")
        df = df.rename(columns={'x': 'longitude', 'y': 'latitude'})
    else:
        raise ValueError("format_type must be 'OSS-UTM' or 'Decimal-Degree'")
    
    # Ensure id column exists
    if 'id' not in df.columns:
        df['id'] = [f"point_{i+1}" for i in range(len(df))]
    
    # Convert to list of dicts
    coordinates = df[['id', 'longitude', 'latitude']].to_dict('records')
    
    # Create GeoDataFrame based on geometry_type
    if geometry_type == "Point":
        gdf = create_point_geodataframe(coordinates)
    elif geometry_type == "Polygon":
        gdf = create_polygon_geodataframe(coordinates)
    else:
        raise ValueError("geometry_type must be 'Point' or 'Polygon'")
    
    # Convert to GeoJSON (for frontend)
    geojson = json.loads(gdf.to_json())
    
    processing_time = time.time() - start_time
    logger.info(f"Excel data processed in {processing_time:.2f}s - {len(coordinates)} coordinates")
    
    return {
        "gdf": gdf,
        "coordinates": coordinates,
        "geojson": geojson,
        "geometry_type": geometry_type,
        "total_rows": len(coordinates)
    }

def perform_spatial_analysis(gdf) -> Dict[str, Any]:
    """Perform spatial analysis dengan optimasi"""
    start_time = time.time()
    
    # Gunakan fungsi analisis gabungan yang sudah dioptimasi
    analysis_result = analyze_all_layers(gdf)
    
    analysis_time = time.time() - start_time
    logger.info(f"Spatial analysis completed in {analysis_time:.2f}s")
    
    # Tambahkan waktu analisis ke hasil
    if analysis_result.get("success"):
        analysis_result["analysis_time"] = analysis_time
    
    return analysis_result

# Routes
@api_router.get("/")
async def root():
    return {
        "message": "Spatial Analysis API - Optimized", 
        "version": "2.0.0",
        "status": "ready"
    }

@api_router.get("/health")
async def health_check():
    """Health check endpoint dengan comprehensive status"""
    try:
        # Check MongoDB connection
        await db.command('ping')
        mongo_status = "connected"
    except Exception as e:
        mongo_status = f"error: {str(e)}"
    
    # Check spatial data cache status
    cache_stats = get_analysis_stats()
    
    return {
        "status": "healthy",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "database": mongo_status,
        "cache": cache_stats,
        "max_rows": _MAX_ROWS
    }

@api_router.post("/status", response_model=StatusCheck)
async def create_status_check(input: StatusCheckCreate):
    """Create status check dengan optimasi"""
    status_dict = input.model_dump()
    status_obj = StatusCheck(**status_dict)
    
    doc = status_obj.model_dump()
    doc['timestamp'] = doc['timestamp'].isoformat()
    
    # Gunakan insert_one tanpa menunggu hasil (fire and forget)
    await db.status_checks.insert_one(doc)
    return status_obj

@api_router.get("/status", response_model=List[StatusCheck])
async def get_status_checks(limit: int = Query(100, ge=1, le=1000)):
    """Get status checks dengan pagination"""
    cursor = db.status_checks.find({}, {"_id": 0}).sort("timestamp", -1).limit(limit)
    status_checks = await cursor.to_list(length=limit)
    
    for check in status_checks:
        if isinstance(check['timestamp'], str):
            check['timestamp'] = datetime.fromisoformat(check['timestamp'])
    
    return status_checks

@api_router.get("/cache/clear")
async def clear_all_cache():
    """Clear semua cache (untuk development/maintenance)"""
    clear_cache()
    clear_kkprl_cache()
    clear_12mil_cache()
    clear_kawasan_cache()
    _preprocessed_data.clear()
    
    logger.info("All caches cleared")
    return {"message": "All caches cleared successfully"}

@api_router.get("/cache/status")
async def cache_status():
    """Get status cache saat ini"""
    return get_analysis_stats()

@api_router.get("/kkprl-metadata")
async def kkprl_metadata():
    """Get metadata tentang KKPRL data"""
    return get_kkprl_metadata()

@api_router.post("/analyze-coordinates", response_model=AnalysisResponse)
async def analyze_coordinates(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    format_type: str = Query(..., description="OSS-UTM or Decimal-Degree"),
    geometry_type: str = Query(..., description="Point or Polygon")
):
    """Analyze coordinates dari Excel file dengan optimasi performa"""
    start_time = time.time()
    
    try:
        # Validasi file type
        if not file.filename or not file.filename.endswith(('.xlsx', '.xls')):
            raise HTTPException(
                status_code=400, 
                detail="File must be Excel format (.xlsx or .xls)"
            )
        
        # Baca file contents
        contents = await file.read()
        if len(contents) == 0:
            raise HTTPException(status_code=400, detail="File is empty")
        
        # Preprocess data di thread pool
        preprocessed_data = await run_in_threadpool(
            preprocess_excel_data, contents, format_type, geometry_type
        )
        
        gdf = preprocessed_data["gdf"]
        coordinates = preprocessed_data["coordinates"]
        geojson = preprocessed_data["geojson"]
        total_rows = preprocessed_data["total_rows"]
        
        # Lakukan analisis spasial di thread pool
        analysis_result = await run_in_threadpool(perform_spatial_analysis, gdf)
        
        if not analysis_result.get("success"):
            raise HTTPException(
                status_code=500, 
                detail=analysis_result.get("message", "Spatial analysis failed")
            )
        
        total_time = time.time() - start_time
        
        # Response final
        return AnalysisResponse(
            success=True,
            coordinates=coordinates,
            geometry_type=geometry_type,
            geojson=geojson,
            total_rows=total_rows,
            analysis_time=total_time,
            overlap_12mil=analysis_result.get("overlap_12mil", {}),
            overlap_kawasan=analysis_result.get("overlap_kawasan", {}),
            overlap_kkprl=analysis_result.get("overlap_kkprl", {})
        )

    except pd.errors.EmptyDataError:
        raise HTTPException(status_code=400, detail="Excel file is empty or invalid")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error analyzing coordinates: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")

@api_router.post("/analyze-direct")
async def analyze_direct_coordinates(
    coordinates: List[Dict[str, Any]],
    geometry_type: str = Query(..., description="Point or Polygon")
):
    """Analyze coordinates langsung dari JSON data (untuk testing)"""
    try:
        start_time = time.time()
        
        # Validasi input
        if not coordinates:
            raise HTTPException(status_code=400, detail="Coordinates list is empty")
        
        if len(coordinates) > _MAX_ROWS:
            raise HTTPException(
                status_code=400, 
                detail=f"Maximum {_MAX_ROWS} coordinates allowed"
            )
        
        # Create GeoDataFrame
        if geometry_type == "Point":
            gdf = create_point_geodataframe(coordinates)
        elif geometry_type == "Polygon":
            gdf = create_polygon_geodataframe(coordinates)
        else:
            raise HTTPException(
                status_code=400, 
                detail="geometry_type must be 'Point' or 'Polygon'"
            )
        
        # Convert to GeoJSON
        geojson = json.loads(gdf.to_json())
        
        # Perform analysis
        analysis_result = await run_in_threadpool(perform_spatial_analysis, gdf)
        
        total_time = time.time() - start_time
        
        return {
            "success": True,
            "coordinates": coordinates,
            "geometry_type": geometry_type,
            "geojson": geojson,
            "total_rows": len(coordinates),
            "analysis_time": total_time,
            "overlap_12mil": analysis_result.get("overlap_12mil", {}),
            "overlap_kawasan": analysis_result.get("overlap_kawasan", {}),
            "overlap_kkprl": analysis_result.get("overlap_kkprl", {})
        }
        
    except Exception as e:
        logger.error(f"Error in direct analysis: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

# Include the router in the main app
app.include_router(api_router)

# Middleware
app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=os.environ.get('CORS_ORIGINS', '*').split(','),
    allow_methods=["*"],
    allow_headers=["*"],
)

# GZip middleware untuk kompresi response
app.add_middleware(GZipMiddleware, minimum_size=1000)

@app.on_event("startup")
async def startup_event():
    """Preload data saat startup untuk response pertama yang lebih cepat"""
    logger.info("Starting up Spatial Analysis API...")
    
    # Preload data penting di background
    async def preload_data():
        try:
            logger.info("Preloading spatial data...")
            await run_in_threadpool(load_kkprl_json)
            await run_in_threadpool(load_12mil_shapefile)
            await run_in_threadpool(load_kawasan_konservasi)
            logger.info("Spatial data preloaded successfully")
        except Exception as e:
            logger.warning(f"Preloading data failed: {e}")
    
    # Jalankan preloading di background tanpa blocking startup
    asyncio.create_task(preload_data())

@app.on_event("shutdown")
async def shutdown_event():
    """Cleanup resources saat shutdown"""
    logger.info("Shutting down Spatial Analysis API...")
    
    # Shutdown thread pool
    thread_pool.shutdown(wait=True)
    
    # Close MongoDB connection
    client.close()
    
    logger.info("Cleanup completed")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "server:app",
        host="0.0.0.0",
        port=8000,
        workers=1,  # Untuk Railway, gunakan 1 worker
        timeout_keep_alive=5,
        access_log=False  # Nonaktifkan access log untuk performa
    )
