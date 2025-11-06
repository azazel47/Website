import { useState, useCallback, useEffect } from "react";
import axios from "axios";
import { useDropzone } from "react-dropzone";
import { MapContainer, TileLayer, GeoJSON, Marker, Popup } from "react-leaflet";
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

    const res = await axios.post(
      `${API}/analyze-coordinates?format_type=${formatType}&geometry_type=${geometryType}`,
      formData,
      { headers: { "Content-Type": "multipart/form-data" } }
    );

    console.log("📊 Response dari backend:", res.data); // ✅ pastikan ada titik koma di akhir
    setResult(res.data);
    toast.success("Analisis selesai!");
  } catch (err) {
    toast.error(err.response?.data?.detail || "Terjadi kesalahan saat analisis");
  } finally {
    setLoading(false);
  }
};

    // === Download Shapefile ===
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
    <>
      <div className="bg-pattern" />
      <div className="relative z-10 min-h-screen p-4 sm:p-6 lg:p-8">
        {/* === Header === */}
        <header className="mb-8 text-center">
          <div className="inline-block mb-4">
            <MapIcon
              className="w-16 h-16 text-cyan-400 mx-auto"
              strokeWidth={1.5}
            />
          </div>
          <h1 className="text-4xl sm:text-5xl lg:text-6xl font-bold mb-4 bg-gradient-to-r from-cyan-300 via-sky-400 to-blue-500 bg-clip-text text-transparent">
            Tools Verdok
          </h1>
          <p className="text-base sm:text-lg text-cyan-100/80 max-w-2xl mx-auto">
            Analisis Koordinat Spasial & Download Shapefile
          </p>
        </header>

        <div className="max-w-7xl mx-auto space-y-6">
          {/* === Upload Section === */}
          <Card className="glass glow-hover border-cyan-500/30">
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
              <div
                {...getRootProps()}
                className={`border-2 border-dashed rounded-lg p-8 text-center cursor-pointer transition-all ${
                  isDragActive
                    ? "border-cyan-400 bg-cyan-500/10"
                    : "border-cyan-500/50 hover:border-cyan-400 hover:bg-cyan-500/5"
                }`}
              >
                <input {...getInputProps()} />
                <Upload className="w-12 h-12 mx-auto mb-4 text-cyan-400" />
                {file ? (
                  <>
                    <p className="text-cyan-100 font-medium mb-1">{file.name}</p>
                    <p className="text-cyan-100/60 text-sm">
                      Klik atau drag untuk mengganti file
                    </p>
                  </>
                ) : (
                  <>
                    <p className="text-cyan-100 font-medium mb-1">
                      {isDragActive
                        ? "Drop file di sini..."
                        : "Drag & drop file Excel"}
                    </p>
                    <p className="text-cyan-100/60 text-sm">
                      atau klik untuk memilih file (.xlsx, .xls)
                    </p>
                  </>
                )}
              </div>

              {/* === Settings === */}
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                <div>
                  <label className="text-sm font-medium text-cyan-200">
                    Format Koordinat
                  </label>
                  <Select value={formatType} onValueChange={setFormatType}>
                    <SelectTrigger className="glass border-cyan-500/30 text-cyan-100">
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent className="glass border-cyan-500/30">
                      <SelectItem value="Decimal-Degree">
                        Decimal Degree
                      </SelectItem>
                      <SelectItem value="OSS-UTM">OSS-UTM (DMS)</SelectItem>
                    </SelectContent>
                  </Select>
                </div>

                <div>
                  <label className="text-sm font-medium text-cyan-200">
                    Tipe Geometri
                  </label>
                  <Select value={geometryType} onValueChange={setGeometryType}>
                    <SelectTrigger className="glass border-cyan-500/30 text-cyan-100">
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent className="glass border-cyan-500/30">
                      <SelectItem value="Point">Point</SelectItem>
                      <SelectItem value="Polygon">Polygon</SelectItem>
                    </SelectContent>
                  </Select>
                </div>
              </div>

              <div className="flex flex-col md:flex-row gap-3">
                <Button
                  onClick={handleAnalyze}
                  disabled={!file || loading}
                  className="flex-1 bg-gradient-to-r from-cyan-500 to-blue-600 hover:from-cyan-400 hover:to-blue-500 text-white font-semibold py-6 text-lg glow"
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

                <Button
                  onClick={handleReset}
                  variant="outline"
                  className="flex-1 border border-cyan-400/40 text-cyan-200 hover:bg-cyan-500/10 py-6 text-lg"
                >
                  Reset
                </Button>
              </div>
            </CardContent>
          </Card>

              {/* === Hasil Analisis === */}
              {result && (
                <>
                  <div className="space-y-6">
                    {/* Statistik */}
                    <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
                      {/* Total */}
                      <Card className="glass glow-hover border-cyan-500/30">
                        <CardContent className="p-6">
                          <div className="text-3xl font-bold text-cyan-300 mb-1">
                            {result.total_rows}
                          </div>
                          <div className="text-sm text-cyan-100/70">Total Koordinat</div>
                        </CardContent>
                      </Card>
              
                      {/* Overlap Kawasan */}
                      <Card className="glass glow-hover border-cyan-500/30">
                        <CardContent className="p-6">
                          <div className="flex items-center justify-between mb-1">
                            <div className="text-lg font-bold text-cyan-300">
                              {result.overlap_kawasan?.has_overlap
                                ? "Dalam Kawasan Konservasi"
                                : "Di luar Kawasan Konservasi"}
                            </div>
                            <span
                              className={`px-2 py-1 rounded-md text-xs font-semibold ${
                                result.overlap_kawasan?.has_overlap
                                  ? "bg-red-500/30 text-red-300 border border-red-400/30"
                                  : "bg-emerald-500/20 text-emerald-300 border border-emerald-400/30"
                              }`}
                            >
                              {result.overlap_kawasan?.has_overlap ? "Perhatian" : "Aman"}
                            </span>
                          </div>
                        </CardContent>
                      </Card>
              
                      {/* Status KKPRL */}
                      <Card className="glass glow-hover border-cyan-500/30">
                        <CardContent className="p-6">
                          <div className="flex items-center justify-between">
                            <div>
                              <div className="text-lg font-bold text-cyan-300 mb-1">
                                {result.overlap_analysis?.has_overlap
                                  ? "Ada Overlap"
                                  : "Tidak Ada"}
                              </div>
                              <div className="text-sm text-cyan-100/70">
                                Penerbitan KKPRL
                              </div>
                            </div>
                            <Badge
                              className={`text-xs ${
                                result.overlap_analysis?.has_overlap
                                  ? "bg-orange-500/20 text-orange-300 border-orange-500/50"
                                  : "bg-green-500/20 text-green-300 border-green-500/50"
                              }`}
                            >
                              {result.overlap_analysis?.has_overlap ? "Perhatian" : "Aman"}
                            </Badge>
                          </div>
                        </CardContent>
                      </Card>
              
                      {/* 12 Mil Laut */}
                      <Card className="glass glow-hover border-cyan-500/30">
                        <CardContent className="p-6 space-y-2">
                          <div className="flex items-center justify-between">
                            <div>
                              <div className="text-lg font-bold text-cyan-300 mb-1">
                                {result.overlap_12mil?.has_overlap
                                  ? "Dalam 12 Mil Laut"
                                  : "Di Luar 12 Mil Laut"}
                              </div>
                            </div>
                            <Badge
                              className={`text-xs ${
                                result.overlap_12mil?.has_overlap
                                  ? "bg-blue-500/20 text-blue-300 border-blue-500/50"
                                  : "bg-green-500/20 text-green-300 border-green-500/50"
                              }`}
                            >
                              {result.overlap_12mil?.has_overlap ? "Dalam" : "Luar"}
                            </Badge>
                          </div>
              
                          {result.overlap_12mil?.wp_list?.length > 0 && (
                            <div className="mt-2">
                              <p className="text-cyan-100/70 text-sm mb-1">
                                Wilayah Provinsi:
                              </p>
                              <div className="flex flex-wrap gap-2">
                                {result.overlap_12mil.wp_list.map((wp, i) => (
                                  <span
                                    key={i}
                                    className="bg-blue-500/20 text-blue-200 border border-blue-500/40 px-3 py-1 rounded-full text-xs font-medium"
                                  >
                                    {wp}
                                  </span>
                                ))}
                              </div>
                            </div>
                          )}
                        </CardContent>
                      </Card>
                    </div>
              
                    {/* === Peta === */}
                    <Card className="glass glow-hover border-cyan-500/30">
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
                            zoom={13}
                            style={{ height: "100%", width: "100%" }}
                          >
                            <TileLayer
                              url="https://mt1.google.com/vt/lyrs=s,h&x={x}&y={y}&z={z}"
                              attribution="Imagery © Google"
                            />
                            {kkprlData && <GeoJSON data={kkprlData} />}
                          </MapContainer>
                        </div>
                      </CardContent>
                    </Card>
              
                    {/* === Tombol Download === */}
                    <Button
                      onClick={handleDownload}
                      disabled={downloadLoading}
                      className="w-full bg-gradient-to-r from-green-500 to-teal-600 hover:from-green-400 hover:to-teal-500 text-white font-semibold py-6 text-lg glow"
                    >
                      {downloadLoading ? (
                        <>
                          <Loader2 className="w-5 h-5 mr-2 animate-spin" /> Mengunduh...
                        </>
                      ) : (
                        <>
                          <Download className="w-5 h-5 mr-2" /> Download Shapefile (ZIP)
                        </>
                      )}
                    </Button>
                  
                  <footer className="mt-12 text-center text-cyan-100/50 text-sm">
                    <p>© 2025 Tools Verdok. Powered by Perizinan I.</p>
                  </footer>
                </div>
              </>
            );
          };

          export default Home;
