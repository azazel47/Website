import { useState, useCallback } from "react";
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

// Fix Leaflet default marker icon issue
delete L.Icon.Default.prototype._getIconUrl;
L.Icon.Default.mergeOptions({
  iconRetinaUrl: "https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.7.1/images/marker-icon-2x.png",
  iconUrl: "https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.7.1/images/marker-icon.png",
  shadowUrl: "https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.7.1/images/marker-shadow.png",
});

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
    onDrop,
    accept: {
      "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": [".xlsx"],
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
        {
          responseType: "blob",
        }
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

  return (
    <>
      <div className="bg-pattern" />
      <div className="relative z-10 min-h-screen p-4 sm:p-6 lg:p-8">
        {/* Header */}
        <header className="mb-8 text-center" data-testid="header">
          <div className="inline-block mb-4">
            <MapIcon className="w-16 h-16 text-cyan-400 mx-auto" strokeWidth={1.5} />
          </div>
          <h1 className="text-4xl sm:text-5xl lg:text-6xl font-bold mb-4 bg-gradient-to-r from-cyan-300 via-sky-400 to-blue-500 bg-clip-text text-transparent" data-testid="main-title">
            Spatio Downloader
          </h1>
          <p className="text-base sm:text-lg text-cyan-100/80 max-w-2xl mx-auto" data-testid="subtitle">
            Analisis Koordinat Spasial & Download Shapefile dengan Mudah
          </p>
        </header>

        <div className="max-w-7xl mx-auto space-y-6">
          {/* Upload & Settings Section */}
          <Card className="glass glow-hover border-cyan-500/30" data-testid="upload-card">
            <CardHeader>
              <CardTitle className="text-2xl text-cyan-300 flex items-center gap-2">
                <FileSpreadsheet className="w-6 h-6" />
                Upload & Konfigurasi
              </CardTitle>
              <CardDescription className="text-cyan-100/60">
                Upload file Excel dan pilih format koordinat
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-6">
              {/* Dropzone */}
              <div
                {...getRootProps()}
                className={`border-2 border-dashed rounded-lg p-8 text-center cursor-pointer transition-all ${
                  isDragActive
                    ? "border-cyan-400 bg-cyan-500/10"
                    : "border-cyan-500/50 hover:border-cyan-400 hover:bg-cyan-500/5"
                }`}
                data-testid="dropzone"
              >
                <input {...getInputProps()} data-testid="file-input" />
                <Upload className="w-12 h-12 mx-auto mb-4 text-cyan-400" />
                {file ? (
                  <div>
                    <p className="text-cyan-100 font-medium mb-1">{file.name}</p>
                    <p className="text-cyan-100/60 text-sm">Klik atau drag untuk mengganti file</p>
                  </div>
                ) : (
                  <div>
                    <p className="text-cyan-100 font-medium mb-1">
                      {isDragActive ? "Drop file di sini..." : "Drag & drop file Excel"}
                    </p>
                    <p className="text-cyan-100/60 text-sm">atau klik untuk memilih file (.xlsx, .xls)</p>
                  </div>
                )}
              </div>

              {/* Settings */}
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                <div className="space-y-2">
                  <label className="text-sm font-medium text-cyan-200">Format Koordinat</label>
                  <Select value={formatType} onValueChange={setFormatType}>
                    <SelectTrigger className="glass border-cyan-500/30 text-cyan-100" data-testid="format-select">
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent className="glass border-cyan-500/30">
                      <SelectItem value="Decimal-Degree" data-testid="format-dd">Decimal Degree</SelectItem>
                      <SelectItem value="OSS-UTM" data-testid="format-oss">OSS-UTM (DMS)</SelectItem>
                    </SelectContent>
                  </Select>
                </div>

                <div className="space-y-2">
                  <label className="text-sm font-medium text-cyan-200">Tipe Geometri</label>
                  <Select value={geometryType} onValueChange={setGeometryType}>
                    <SelectTrigger className="glass border-cyan-500/30 text-cyan-100" data-testid="geometry-select">
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent className="glass border-cyan-500/30">
                      <SelectItem value="Point" data-testid="geometry-point">Point</SelectItem>
                      <SelectItem value="Polygon" data-testid="geometry-polygon">Polygon</SelectItem>
                    </SelectContent>
                  </Select>
                </div>
              </div>

              {/* Analyze Button */}
              <Button
                onClick={handleAnalyze}
                disabled={!file || loading}
                className="w-full bg-gradient-to-r from-cyan-500 to-blue-600 hover:from-cyan-400 hover:to-blue-500 text-white font-semibold py-6 text-lg glow"
                data-testid="analyze-button"
              >
                {loading ? (
                  <>
                    <Loader2 className="w-5 h-5 mr-2 animate-spin" />
                    Menganalisis...
                  </>
                ) : (
                  "Analisis Koordinat"
                )}
              </Button>
            </CardContent>
          </Card>

          {/* Results Section */}
          {result && (
            <div className="space-y-6">
              {/* Stats Cards */}
              <div className="grid grid-cols-1 md:grid-cols-3 gap-4" data-testid="stats-cards">
                <Card className="glass glow-hover border-cyan-500/30">
                  <CardContent className="p-6">
                    <div className="text-3xl font-bold text-cyan-300 mb-1" data-testid="total-points">
                      {result.total_rows}
                    </div>
                    <div className="text-sm text-cyan-100/70">Total Koordinat</div>
                  </CardContent>
                </Card>

                <Card className="glass glow-hover border-cyan-500/30">
                  <CardContent className="p-6">
                    <div className="text-3xl font-bold text-cyan-300 mb-1" data-testid="overlap-count">
                      {result.overlap_analysis?.overlap_count || 0}
                    </div>
                    <div className="text-sm text-cyan-100/70">Overlap KKPRL</div>
                  </CardContent>
                </Card>

                <Card className="glass glow-hover border-cyan-500/30">
                  <CardContent className="p-6">
                    <div className="flex items-center justify-between">
                      <div>
                        <div className="text-lg font-bold text-cyan-300 mb-1">
                          {result.overlap_analysis?.has_overlap ? "Ada Overlap" : "Tidak Ada"}
                        </div>
                        <div className="text-sm text-cyan-100/70">Status Analisis</div>
                      </div>
                      <Badge
                        variant={result.overlap_analysis?.has_overlap ? "destructive" : "default"}
                        className={`text-xs ${
                          result.overlap_analysis?.has_overlap
                            ? "bg-orange-500/20 text-orange-300 border-orange-500/50"
                            : "bg-green-500/20 text-green-300 border-green-500/50"
                        }`}
                        data-testid="overlap-badge"
                      >
                        {result.overlap_analysis?.has_overlap ? "Perhatian" : "Aman"}
                      </Badge>
                    </div>
                  </CardContent>
                </Card>
              </div>

              {/* Map */}
              <Card className="glass glow-hover border-cyan-500/30" data-testid="map-card">
                <CardHeader>
                  <CardTitle className="text-2xl text-cyan-300 flex items-center gap-2">
                    <MapIcon className="w-6 h-6" />
                    Peta Visualisasi
                  </CardTitle>
                </CardHeader>
                <CardContent>
                  <div className="h-[500px] rounded-lg overflow-hidden" data-testid="map-container">
                    <MapContainer
                      center={[
                        result.coordinates[0]?.latitude || 0,
                        result.coordinates[0]?.longitude || 0,
                      ]}
                      zoom={10}
                      style={{ height: "100%", width: "100%" }}
                    >
                      <TileLayer
                        url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
                        attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>'
                      />
                      {result.geojson && <GeoJSON data={result.geojson} />}
                      {result.geometry_type === "Point" &&
                        result.coordinates.map((coord, idx) => (
                          <Marker key={idx} position={[coord.latitude, coord.longitude]}>
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

              {/* Overlap Details */}
              {result.overlap_analysis?.has_overlap && (
                <Card className="glass glow-hover border-orange-500/30" data-testid="overlap-details-card">
                  <CardHeader>
                    <CardTitle className="text-2xl text-orange-300">Detail Overlap KKPRL</CardTitle>
                    <CardDescription className="text-cyan-100/60">
                      {result.overlap_analysis.message}
                    </CardDescription>
                  </CardHeader>
                  <CardContent>
                    <div className="space-y-3 max-h-96 overflow-y-auto">
                      {result.overlap_analysis.overlap_details?.map((detail, idx) => (
                        <div
                          key={idx}
                          className="glass p-4 rounded-lg border border-cyan-500/20 hover:border-cyan-400/40 transition-colors"
                          data-testid={`overlap-item-${idx}`}
                        >
                          <div className="grid grid-cols-2 gap-2 text-sm">
                            <div>
                              <span className="text-cyan-100/60">NO KKPRL:</span>
                              <p className="text-cyan-100 font-medium">{detail.no_kkprl}</p>
                            </div>
                            <div>
                              <span className="text-cyan-100/60">Nama:</span>
                              <p className="text-cyan-100 font-medium">{detail.nama_subj}</p>
                            </div>
                            <div>
                              <span className="text-cyan-100/60">Kegiatan:</span>
                              <p className="text-cyan-100 font-medium">{detail.kegiatan}</p>
                            </div>
                            <div>
                              <span className="text-cyan-100/60">Provinsi:</span>
                              <p className="text-cyan-100 font-medium">{detail.provinsi}</p>
                            </div>
                          </div>
                        </div>
                      ))}
                    </div>
                  </CardContent>
                </Card>
              )}

              {/* Download Button */}
              <Button
                onClick={handleDownload}
                disabled={downloadLoading}
                className="w-full bg-gradient-to-r from-green-500 to-teal-600 hover:from-green-400 hover:to-teal-500 text-white font-semibold py-6 text-lg glow"
                data-testid="download-button"
              >
                {downloadLoading ? (
                  <>
                    <Loader2 className="w-5 h-5 mr-2 animate-spin" />
                    Mengunduh...
                  </>
                ) : (
                  <>
                    <Download className="w-5 h-5 mr-2" />
                    Download Shapefile (ZIP)
                  </>
                )}
              </Button>
            </div>
          )}
        </div>

        {/* Footer */}
        <footer className="mt-12 text-center text-cyan-100/50 text-sm" data-testid="footer">
          <p>© 2025 Spatio Downloader. Powered by GeoSpatial Technology.</p>
        </footer>
      </div>
    </>
  );
};

export default Home;
