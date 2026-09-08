import axios from "axios";

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;

export async function fetchAdminDocument(path) {
  // Accept only an API-relative path; never attach the bearer to external links.
  if (!path.startsWith("/") || path.startsWith("//") || path.includes("\\") || /[?&]token=/i.test(path)) {
    throw new Error("Geçersiz belge adresi");
  }
  const token = localStorage.getItem("token");
  if (!token) throw new Error("Lütfen yeniden giriş yapın");
  const result = await axios.get(`${API}${path}`, {
    headers: { Authorization: `Bearer ${token}`, "Cache-Control": "no-store" },
    responseType: "blob",
  });
  return result.data;
}

export async function openAdminDocument(path, features = "", print = false) {
  const popup = window.open("about:blank", "_blank", features);
  if (!popup) throw new Error("Yazdırma penceresi engellendi. Açılır pencerelere izin verin.");
  popup.opener = null;
  try {
    const blob = await fetchAdminDocument(path);
    const url = URL.createObjectURL(blob);
    if (print) popup.onload = () => popup.print();
    popup.location.replace(url);
    // Revoke after the document has had time to load, without retaining PII URLs forever.
    setTimeout(() => URL.revokeObjectURL(url), 300000);
  } catch (error) {
    popup.close();
    throw error;
  }
}
