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

# Import utils
from utils.coordinate_converter import dms_to_dd
from utils.kkprl_loader import load_kkprl_json, get_kkprl_metadata
from utils.spatial_analysis import (
    create_point_geodataframe,
    create_polygon_geodataframe,
    analyze_point_overlap,
    analyze_polygon_overlap
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
    model_config = ConfigDict(extra="ignore")  # Ignore MongoDB's _id field
    
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    client_name: str
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

class StatusCheckCreate(BaseModel):
    client_name: str

class DownloadShapefileRequest(BaseModel):
    coordinates: List[Dict[str, Any]]
    geometry_type: str
    filename: Optional[str] = "output"


# Routes
@api_router.get("/")
async def root():
    return {"message": "Spatio Downloader API - Ready"}

@api_router.post("/status", response_model=StatusCheck)
async def create_status_check(input: StatusCheckCreate):
    status_dict = input.model_dump()
    status_obj = StatusCheck(**status_dict)
    
    # Convert to dict and serialize datetime to ISO string for MongoDB
    doc = status_obj.model_dump()
    doc['timestamp'] = doc['timestamp'].isoformat()
    
    _ = await db.status_checks.insert_one(doc)
    return status_obj

@api_router.get("/status", response_model=List[StatusCheck])
async def get_status_checks():
    # Exclude MongoDB's _id field from the query results
    status_checks = await db.status_checks.find({}, {"_id": 0}).to_list(1000)
    
    # Convert ISO string timestamps back to datetime objects
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
    """
    Analyze coordinates from Excel file
    
    Args:
        file: Excel file with coordinates
        format_type: Either 'OSS-UTM' or 'Decimal-Degree'
        geometry_type: Either 'Point' or 'Polygon'
    
    Returns:
        Analysis results with GeoJSON and overlap information
    """
    try:\n        # Read Excel file\n        contents = await file.read()\n        if len(contents) == 0:\n            raise HTTPException(status_code=400, detail=\"File is empty\")\n        \n        df = pd.read_excel(BytesIO(contents))\n        \n        if df.empty:\n            raise HTTPException(status_code=400, detail=\"Excel file contains no data\")\n        \n        # Coordinate conversion based on format_type\n        if format_type == \"OSS-UTM\":\n            # Check required columns\n            required_cols = ['bujur_derajat', 'bujur_menit', 'bujur_detik', 'BT_BB',\n                           'lintang_derajat', 'lintang_menit', 'lintang_detik', 'LU_LS']\n            missing_cols = [col for col in required_cols if col not in df.columns]\n            if missing_cols:\n                raise HTTPException(\n                    status_code=400, \n                    detail=f\"Missing columns for OSS-UTM format: {missing_cols}\"\n                )\n            \n            # Convert DMS to DD\n            df['longitude'] = df.apply(\n                lambda row: dms_to_dd(\n                    row['bujur_derajat'], \n                    row['bujur_menit'], \n                    row['bujur_detik'], \n                    row['BT_BB']\n                ), \n                axis=1\n            )\n            df['latitude'] = df.apply(\n                lambda row: dms_to_dd(\n                    row['lintang_derajat'], \n                    row['lintang_menit'], \n                    row['lintang_detik'], \n                    row['LU_LS']\n                ), \n                axis=1\n            )\n        elif format_type == \"Decimal-Degree\":\n            # Check for x, y columns\n            if 'x' not in df.columns or 'y' not in df.columns:\n                raise HTTPException(\n                    status_code=400, \n                    detail=\"Decimal-Degree format requires 'x' and 'y' columns\"\n                )\n            df = df.rename(columns={'x': 'longitude', 'y': 'latitude'})\n        else:\n            raise HTTPException(\n                status_code=400, \n                detail=\"format_type must be 'OSS-UTM' or 'Decimal-Degree'\"\n            )\n        \n        # Ensure id column exists\n        if 'id' not in df.columns:\n            df['id'] = [f\"point_{i+1}\" for i in range(len(df))]\n        \n        # Limit to 300 rows\n        if len(df) > 300:\n            logger.warning(f\"Data truncated from {len(df)} to 300 rows\")\n            df = df.head(300)\n        \n        # Convert to list of dicts\n        coordinates = df[['id', 'longitude', 'latitude']].to_dict('records')\n        \n        # Create GeoDataFrame based on geometry_type\n        if geometry_type == \"Point\":\n            gdf = create_point_geodataframe(coordinates)\n        elif geometry_type == \"Polygon\":\n            gdf = create_polygon_geodataframe(coordinates)\n        else:\n            raise HTTPException(\n                status_code=400, \n                detail=\"geometry_type must be 'Point' or 'Polygon'\"\n            )\n        \n        # Convert to GeoJSON\n        geojson = json.loads(gdf.to_json())\n        \n        # KKPRL Overlap Analysis\n        overlap_analysis = None\n        kkprl_gdf = load_kkprl_json()\n        \n        if kkprl_gdf is not None:\n            if geometry_type == \"Point\":\n                overlap_analysis = analyze_point_overlap(gdf, kkprl_gdf)\n            elif geometry_type == \"Polygon\":\n                overlap_analysis = analyze_polygon_overlap(gdf, kkprl_gdf)\n        else:\n            overlap_analysis = {\n                \"has_overlap\": False,\n                \"message\": \"KKPRL data not available\"\n            }\n        \n        return {\n            \"success\": True,\n            \"coordinates\": coordinates,\n            \"geometry_type\": geometry_type,\n            \"geojson\": geojson,\n            \"overlap_analysis\": overlap_analysis,\n            \"total_rows\": len(coordinates)\n        }\n        \n    except pd.errors.EmptyDataError:\n        raise HTTPException(status_code=400, detail=\"Excel file is empty or invalid\")\n    except Exception as e:\n        logger.error(f\"Error analyzing coordinates: {e}\")\n        raise HTTPException(status_code=500, detail=str(e))

@api_router.post("/download-shapefile")
async def download_shapefile(request: DownloadShapefileRequest):
    """
    Generate and download shapefile as ZIP
    
    Args:
        request: Contains coordinates, geometry_type, and optional filename
    
    Returns:
        ZIP file containing shapefile components
    """
    try:\n        # Create GeoDataFrame\n        if request.geometry_type == \"Point\":\n            gdf = create_point_geodataframe(request.coordinates)\n        elif request.geometry_type == \"Polygon\":\n            gdf = create_polygon_geodataframe(request.coordinates)\n        else:\n            raise HTTPException(\n                status_code=400, \n                detail=\"geometry_type must be 'Point' or 'Polygon'\"\n            )\n        \n        # Create temporary directory\n        with tempfile.TemporaryDirectory() as tmpdir:\n            tmpdir_path = Path(tmpdir)\n            shapefile_path = tmpdir_path / f\"{request.filename}.shp\"\n            \n            # Save as shapefile\n            gdf.to_file(shapefile_path, driver='ESRI Shapefile', encoding='utf-8')\n            \n            # Create ZIP file in memory\n            zip_buffer = BytesIO()\n            with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zip_file:\n                # Add all shapefile components to ZIP\n                for ext in ['.shp', '.shx', '.dbf', '.prj', '.cpg']:\n                    file_path = tmpdir_path / f\"{request.filename}{ext}\"\n                    if file_path.exists():\n                        zip_file.write(file_path, arcname=f\"{request.filename}{ext}\")\n            \n            # Reset buffer position\n            zip_buffer.seek(0)\n            \n            return StreamingResponse(\n                zip_buffer,\n                media_type=\"application/zip\",\n                headers={\"Content-Disposition\": f\"attachment; filename={request.filename}.zip\"}\n            )\n    \n    except Exception as e:\n        logger.error(f\"Error creating shapefile: {e}\")\n        raise HTTPException(status_code=500, detail=str(e))


# Include the router in the main app
app.include_router(api_router)

app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=os.environ.get('CORS_ORIGINS', '*').split(','),
    allow_methods=[\"*\"],
    allow_headers=[\"*\"],
)

@app.on_event(\"shutdown\")
async def shutdown_db_client():
    client.close()