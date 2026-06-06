import { useEffect, useState } from "react";
import { useLocation } from "react-router-dom";
import axios from "axios";
import { useAuth } from "../context/AuthContext";

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;

function MaintenanceScreen({ title, message, logoUrl, siteName }) {
  return (
    <div
      data-testid="maintenance-screen"
      className="fixed inset-0 z-[9999] flex items-center justify-center bg-[#f6f3ee] text-[#1a1a1a] px-6"
    >
      <div className="max-w-xl w-full text-center">
        {logoUrl ? (
          <img
            src={logoUrl}
            alt={siteName}
            className="h-12 mx-auto mb-10 object-contain"
            data-testid="maintenance-logo"
          />
        ) : (
          <div
            className="mb-10 tracking-[0.5em] text-2xl font-light uppercase"
            data-testid="maintenance-sitename"
          >
            {siteName}
          </div>
        )}

        <div className="mb-8 flex justify-center">
          <span className="inline-flex h-2 w-2 rounded-full bg-[#1a1a1a] animate-pulse" />
        </div>

        <h1
          className="text-3xl sm:text-4xl font-light leading-tight mb-5"
          style={{ fontFamily: "Georgia, 'Times New Roman', serif" }}
          data-testid="maintenance-title"
        >
          {title}
        </h1>

        <p
          className="text-base text-[#5a5a5a] leading-relaxed max-w-md mx-auto"
          data-testid="maintenance-message"
        >
          {message}
        </p>

        <div className="mt-12 h-px w-24 mx-auto bg-[#d8d2c7]" />
        <p className="mt-6 text-xs uppercase tracking-[0.25em] text-[#9a9488]">
          {siteName}
        </p>
      </div>
    </div>
  );
}

export default function MaintenanceGate({ children }) {
  const { isAdmin, loading: authLoading } = useAuth();
  const location = useLocation();
  const [status, setStatus] = useState(null);

  useEffect(() => {
    axios
      .get(`${API}/settings/maintenance`)
      .then((res) => setStatus(res.data))
      .catch(() => setStatus({ maintenance_mode: false }));
  }, []);

  // Admin paneline (giriş dahil) bakım modunda da her zaman erişilebilir olmalı.
  const isAdminRoute = location.pathname.startsWith("/admin");

  // Durum henüz yüklenmediyse içeriği göster (flash önleme).
  if (!status || !status.maintenance_mode || isAdminRoute) {
    return children;
  }

  // Bakım modu açık ve admin rotası değil: admin doğrulaması bitene kadar bekle.
  if (authLoading) return null;
  if (isAdmin) return children;

  return (
    <MaintenanceScreen
      title={status.maintenance_title}
      message={status.maintenance_message}
      logoUrl={status.logo_url}
      siteName={status.site_name}
    />
  );
}
