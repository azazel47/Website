import { useState, useCallback, useEffect } from "react";
import axios from "axios";
import { useDropzone } from "react-dropzone";
import { MapContainer, GeoJSON, Marker, Popup, useMap } from "react-leaflet";
import { saveAs } from "file-saver";
import { toast } from "sonner";
import {
  Upload,
  Download,
  Map as MapIcon,
  FileSpreadsheet,
  Loader2,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Badge } from "@/components/ui/badge";
import L from "leaflet";
import "leaflet/dist/leaflet.css";
import "esri-leaflet";

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL;
const API = `${BACKEND_URL}/api`;

// 🧩 Komponen untuk menambahkan basemap & layer ArcGIS dari ruanglaut.id
function ArcGISLayers() {
  const map = useMap();

  useEffect(() => {
    // Basemap default dari ArcGIS
    const basemap = L.esri.basemapLayer("Topographic").addTo(map);

    // Layer KKPRL dari ArcGIS Server ruanglaut.id
    const kkprlLayer = L.esri
      .dynamicMapLayer({
        url: "https://arcgis.ruanglaut.id/arcgis/rest/services/KKPRL/KKPRL/MapServer",
        opacity: 0.8,
      })
      .addTo(map);

    // Hapus layer saat komponen di-unmount
    return () => {
      map.removeLayer(basemap);
      map.removeLayer(kkprlLayer);
    };
  }, [map]);

  return null;
}

const Home = () => {
  const [file, setFile] = useState(null);
  const [formatType, setFormatType] = useState("Decimal-Degree");
  const [geometryType, setGeometryType] = useState("Point");
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState(null);
  const [downloadLoading, setDownloadLoading] = useState(false);

  const onDrop = useCallback((acceptedFiles) => {
    if (acceptedFiles?.length > 0) {
      setFile(acceptedFiles[0]);
      toast.success("File berhasil dipilih");
    }
  }, []);

  const { getRootProps, getInputProps, isDragActive } = useDropzone({
    key: file ? file.name : "empty",
    onDrop,
    accept: {
      "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": [
        ".xlsx",
      ],
      "application/vnd.ms-excel": [".xls"],
    },
    maxFiles: 1,
  });

  const handleAnalyze = async () => {
    if (!file) {
      toast.error("Silakan pilih file Excel terlebih dahulu");
      return;
    }

    setLoading(true);
    try {
      const formData = new FormData();
      formData.append("file", file);

      const response = await axios.post(
        `${API}/analyze-coordinates?format_type=${formatType}&geometry_type=${geometryType}`,
        formData,
        {
          headers: {
            "Content-Type": "multipart/form-data",
          },
        }
      );

      setResult(response.data);
      console.log("📦 Data diterima dari backend:", response.data);
      toast.success("Analisis selesai!");
    } catch (error) {
      console.error("Error:", error);
      toast.error(error.response?.data?.detail || "Terjadi kesalahan saat analisis");
    } finally {
      setLoading(false);
    }
  };

  const handleDownload = async () => {
    if (!result) return;

    setDownloadLoading(true);
    try {
      const response = await axios.post(
        `${API}/download-shapefile`,
        {
          coordinates: result.coordinates,
          geometry_type: result.geometry_type,
          filename: "koordinat_output",
        },
        { responseType: "blob" }
      );

      const blob = new Blob([response.data], { type: "application/zip" });
      saveAs(blob, "koordinat_output.zip");
      toast.success("Shapefile berhasil diunduh!");
    } catch (error) {
      console.error("Error:", error);
      toast.error("Gagal mengunduh shapefile");
    } finally {
      setDownloadLoading(false);
    }
  };

  const handleReset = () => {
    setFile(null);
    setFormatType("Decimal-Degree");
    setGeometryType("Point");
    setResult(null);
    toast.info("Form telah direset");
  };

  return (
    <>
      <div className="bg-pattern" />
      <div className="relative z-10 min-h-screen p-4 sm:p-6 lg:p-8">
        {/* Header */}
        <header className="mb-8 text-center" data-testid="header">
          <div className="inline-block mb-4">
            <MapIcon className="w-16 h-16 text-cyan-400 mx-auto" strokeWidth={1.5} />
          </div>
          <h1 className="text-4xl sm:text-5xl lg:text-6xl font-bold mb-4 bg-gradient-to-r from-cyan-300 via-sky-400 to-blue-500 bg-clip-text text-transparent">
            Tools Verdok
          </h1>
          <p className="text-base sm:text-lg text-cyan-100/80 max-w-2xl mx-auto">
            Analisis Koordinat Spasial & Download Shapefile
          </p>
        </header>

        {/* Upload Section */}
        {/* ... (semua kode upload dan analisis kamu tetap sama) ... */}

        {/* Hasil Analisis */}
        {result && (
          <Card className="glass glow-hover border-cyan-500/30 mt-6">
            <CardHeader>
              <CardTitle className="text-2xl text-cyan-300 flex items-center gap-2">
                <MapIcon className="w-6 h-6" /> Peta Visualisasi
              </CardTitle>
            </CardHeader>
            <CardContent>
              <div className="h-[500px] rounded-lg overflow-hidden">
                <MapContainer
                  center={[
                    result.coordinates[0]?.latitude || 0,
                    result.coordinates[0]?.longitude || 0,
                  ]}
                  zoom={15}
                  style={{ height: "100%", width: "100%" }}
                >
                  {/* Tambahkan Layer ArcGIS */}
                  <ArcGISLayers />

                  {/* GeoJSON hasil analisis */}
                  {result.geojson && <GeoJSON data={result.geojson} />}

                  {/* Marker */}
                  {result.geometry_type === "Point" &&
                    result.coordinates.map((coord, idx) => (
                      <Marker
                        key={idx}
                        position={[coord.latitude, coord.longitude]}
                      >
                        <Popup>
                          <div className="text-sm">
                            <strong>ID:</strong> {coord.id}
                            <br />
                            <strong>Lat:</strong> {coord.latitude.toFixed(6)}
                            <br />
                            <strong>Lng:</strong> {coord.longitude.toFixed(6)}
                          </div>
                        </Popup>
                      </Marker>
                    ))}
                </MapContainer>
              </div>
            </CardContent>
          </Card>
        )}

        {/* Footer */}
        <footer className="mt-12 text-center text-cyan-100/50 text-sm">
          <p>© 2025 Tools Verdok. Powered by Perizinan I.</p>
        </footer>
      </div>
    </>
  );
};

export default Home;
