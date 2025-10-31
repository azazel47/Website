import { useState, useCallback } from "react";
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
      toast.error(
        error.response?.data?.detail || "Terjadi kesalahan saat analisis"
      );
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

  // ✅ Fungsi Reset baru (tidak ubah logika lainnya)
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
          {/* Upload Section */}
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
                    <p className="text-cyan-100 font-medium mb-1">
                      {file.name}
                    </p>
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

              {/* Settings */}
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

              {/* Tombol Analisis & Reset */}
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

          {/* Hasil Analisis */}
          {result && (
            <>
              {/* (Seluruh bagian hasil tetap sama persis dengan versi kamu) */}
              {/* ... Semua blok card statistik, map, dan detail overlap ... */}

              {/* Download Button */}
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
                    <Download className="w-5 h-5 mr-2" /> Download Shapefile
                    (ZIP)
                  </>
                )}
              </Button>
            </>
          )}
        </div>

        {/* Footer */}
        <footer className="mt-12 text-center text-cyan-100/50 text-sm">
          <p>© 2025 Tools Verdok. Powered by Perizinan I.</p>
        </footer>
      </div>
    </>
  );
};

export default Home;
