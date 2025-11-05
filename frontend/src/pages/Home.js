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

  // === Load KKPRL JSON (untuk layer di peta) ===
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
      "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": [
        ".xlsx",
      ],
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
              {/* === Dropzone === */}
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

          {/* === Map Section === */}
          {result && (
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
                    zoom={15}
                    style={{ height: "100%", width: "100%" }}
                  >
                    <TileLayer
                      url="https://mt1.google.com/vt/lyrs=s,h&x={x}&y={y}&z={z}"
                      attribution='Imagery © Google'
                    />

                    {/* === Layer KKPRL === */}
                    {kkprlData && (
                      <GeoJSON
                        data={kkprlData}
                        style={(feature) => {
                          const jenis = feature.properties?.["Jenis KKPRL"] || feature.properties?.JENIS_KKPRL || "";
                    
                          // === Jenis 1: PEMANFAATAN ===
                          if (jenis.toLowerCase().includes("PERSETUJUAN")) {
                            return {
                              color: "#EEF211",        // oranye terang
                              weight: 2,
                              fillColor: "#EEF211",    // oranye lembut
                              fillOpacity: 0.25,
                              dashArray: "5, 2",       // pola garis putus-putus halus
                            };
                          }
                    
                          // === Jenis 2: REKLAMASI ===
                          if (jenis.toLowerCase().includes("KONFIRMASI")) {
                            return {
                              color: "#F21111",        // hijau
                              weight: 2,
                              fillColor: "#F21111",    // hijau lembut
                              fillOpacity: 0.25,
                              dashArray: "",           // garis solid
                            };
                          }
                    
                          // === Default (tidak ada Jenis) ===
                          return {
                            color: "#eab308",          // kuning
                            weight: 1,
                            fillOpacity: 0.15,
                            dashArray: "1,3",
                          };
                        }}
                        onEachFeature={(feature, layer) => {
                          const props = feature.properties || {};
                          const no_kkprl = props.NO_KKPRL || props.no_kkprl || "—";
                          const nama = props.NAMA_SUBJ || props.nama_subj || "—";
                          const jenis = props.JENIS_KKPRL || props["Jenis KKPRL"] || "—";
                          const kegiatan = props.KEGIATAN || props.kegiatan || "—";
                          const prov = props.PROVINSI || props.provinsi || "—";
                    
                          const popupContent = `
                            <div style="font-size:13px; line-height:1.4; color:#0ff;">
                              <strong>NO KKPRL:</strong> ${no_kkprl}<br/>
                              <strong>Nama:</strong> ${nama}<br/>
                              <strong>Jenis:</strong> ${jenis}<br/>
                              <strong>Kegiatan:</strong> ${kegiatan}<br/>
                              <strong>Provinsi:</strong> ${prov}
                            </div>
                          `;
                          layer.bindPopup(popupContent);
                        }}
                      />
                    )}


                    {/* === Titik koordinat === */}
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

          {/* === Download === */}
          {result && (
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
          )}
        </div>

        <footer className="mt-12 text-center text-cyan-100/50 text-sm">
          <p>© 2025 Tools Verdok. Powered by Perizinan I.</p>
        </footer>
      </div>
    </>
  );
};

export default Home;
