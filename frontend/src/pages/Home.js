import { useState, useCallback, useEffect } from "react";
import axios from "axios";
import { useDropzone } from "react-dropzone";
import { MapContainer, TileLayer, GeoJSON, Marker, Popup } from "react-leaflet";
import { saveAs } from "file-saver";
import { toast } from "sonner";
import { Upload, Download, Map as MapIcon, FileSpreadsheet, Loader2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Badge } from "@/components/ui/badge";
import L from "leaflet";
import "leaflet/dist/leaflet.css";

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL;
const API = `${BACKEND_URL}/api`;

const Home = () => {
  const [file, setFile] = useState(null);
  const [formatType, setFormatType] = useState("Decimal-Degree");
  const [geometryType, setGeometryType] = useState("Point");
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState(null);
  const [kkprlData, setKkprlData] = useState(null);
  const [downloadLoading, setDownloadLoading] = useState(false);

  // === Load KKPRL Data ===
  const fetchKkprlData = async () => {
    try {
      const res = await axios.get(`${API}/kkprl-geojson`);
      setKkprlData(res.data);
      console.log("✅ KKPRL data loaded:", res.data);
    } catch (err) {
      console.error("❌ Gagal memuat data KKPRL:", err);
    }
  };

  useEffect(() => {
    fetchKkprlData();
  }, []);

  // === Dropzone ===
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
      "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": [".xlsx"],
      "application/vnd.ms-excel": [".xls"],
    },
    maxFiles: 1,
  });

  // === Analisis Koordinat ===
  const handleAnalyze = async () => {
    if (!file) {
      toast.error("Silakan pilih file Excel terlebih dahulu");
      return;
    }

    setLoading(true);
    try {
      const formData = new FormData();
      formData.append("file", file);

      const res = await axios.post(
        `${API}/analyze-coordinates?format_type=${formatType}&geometry_type=${geometryType}`,
        formData,
        { headers: { "Content-Type": "multipart/form-data" } }
      );

      setResult(res.data);
      toast.success("Analisis selesai!");
    } catch (err) {
      toast.error(err.response?.data?.detail || "Terjadi kesalahan saat analisis");
    } finally {
      setLoading(false);
    }
  };

  // === Download ===
  const handleDownload = async () => {
    if (!result) return;
    setDownloadLoading(true);
    try {
      const res = await axios.post(
        `${API}/download-shapefile`,
        {
          coordinates: result.coordinates,
          geometry_type: result.geometry_type,
          filename: "koordinat_output",
        },
        { responseType: "blob" }
      );
      const blob = new Blob([res.data], { type: "application/zip" });
      saveAs(blob, "koordinat_output.zip");
      toast.success("Shapefile berhasil diunduh!");
    } catch {
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
    <div className="bg-gray-950 text-cyan-100 min-h-screen p-6">
      <header className="text-center mb-8">
        <MapIcon className="w-16 h-16 text-cyan-400 mx-auto" />
        <h1 className="text-4xl font-bold mt-2">Tools Verdok</h1>
        <p className="text-cyan-300/80">Analisis Koordinat Spasial & KKPRL Overlay</p>
      </header>

      {/* === Upload & Settings === */}
      <Card className="border-cyan-500/30 mb-6">
        <CardHeader>
          <CardTitle className="text-cyan-300">Upload & Konfigurasi</CardTitle>
          <CardDescription>Pilih file Excel dan format koordinat</CardDescription>
        </CardHeader>
        <CardContent className="space-y-6">
          <div {...getRootProps()} className="border-2 border-dashed rounded-lg p-6 text-center">
            <input {...getInputProps()} />
            <Upload className="w-10 h-10 mx-auto text-cyan-400" />
            {file ? <p>{file.name}</p> : <p>Drop file Excel di sini</p>}
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div>
              <label>Format Koordinat</label>
              <Select value={formatType} onValueChange={setFormatType}>
                <SelectTrigger className="border-cyan-400/50 text-cyan-200">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="Decimal-Degree">Decimal Degree</SelectItem>
                  <SelectItem value="OSS-UTM">OSS-UTM (DMS)</SelectItem>
                </SelectContent>
              </Select>
            </div>

            <div>
              <label>Tipe Geometri</label>
              <Select value={geometryType} onValueChange={setGeometryType}>
                <SelectTrigger className="border-cyan-400/50 text-cyan-200">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="Point">Point</SelectItem>
                  <SelectItem value="Polygon">Polygon</SelectItem>
                </SelectContent>
              </Select>
            </div>
          </div>

          <Button onClick={handleAnalyze} disabled={!file || loading}>
            {loading ? <Loader2 className="animate-spin mr-2" /> : "Analisis Koordinat"}
          </Button>
        </CardContent>
      </Card>

      {/* === MAP === */}
      {result && (
        <Card className="border-cyan-500/30">
          <CardHeader>
            <CardTitle>Peta Visualisasi</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="h-[500px] rounded-lg overflow-hidden">
              <MapContainer
                center={[
                  result.coordinates[0]?.latitude || 0,
                  result.coordinates[0]?.longitude || 0,
                ]}
                zoom={13}
                style={{ height: "100%", width: "100%" }}
              >
                <TileLayer
                  url="https://mt1.google.com/vt/lyrs=s,h&x={x}&y={y}&z={z}"
                  attribution="Imagery © Google"
                />

                {/* Layer KKPRL */}
                {kkprlData && (
                  <GeoJSON
                    data={kkprlData}
                    style={{
                      color: "orange",
                      weight: 1,
                      fillOpacity: 0.3,
                    }}
                  />
                )}

                {/* Layer hasil analisis */}
                {result.geojson && (
                  <GeoJSON data={result.geojson} style={{ color: "cyan" }} />
                )}

                {result.geometry_type === "Point" &&
                  result.coordinates.map((coord, idx) => (
                    <Marker key={idx} position={[coord.latitude, coord.longitude]}>
                      <Popup>
                        <strong>ID:</strong> {coord.id}
                        <br />
                        <strong>Lat:</strong> {coord.latitude.toFixed(6)} <br />
                        <strong>Lng:</strong> {coord.longitude.toFixed(6)}
                      </Popup>
                    </Marker>
                  ))}
              </MapContainer>
            </div>
          </CardContent>
        </Card>
      )}
    </div>
  );
};

export default Home;
