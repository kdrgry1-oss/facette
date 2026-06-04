import { useState } from "react";
import { useNavigate, Navigate } from "react-router-dom";
import { toast } from "sonner";
import { useAuth } from "../../context/AuthContext";

export default function AdminLogin() {
  const navigate = useNavigate();
  const { login, verifyMfa, user, isAdmin, logout, loading: authLoading } = useAuth();
  const [loading, setLoading] = useState(false);
  const [formData, setFormData] = useState({
    email: "",
    password: "",
  });
  const [mfaToken, setMfaToken] = useState(null);
  const [mfaCode, setMfaCode] = useState("");

  if (authLoading) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-gray-100">
        <p>Yükleniyor...</p>
      </div>
    );
  }

  if (user && isAdmin) {
    return <Navigate to="/admin" />;
  }

  const finishLogin = (userData) => {
    if (userData?.is_admin) {
      toast.success("Admin girişi başarılı!");
      navigate("/admin");
    } else {
      toast.error("Bu alana giriş yetkiniz bulunmamaktadır.");
      logout();
    }
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    setLoading(true);
    try {
      const result = await login(formData.email, formData.password);
      if (result?.mfaRequired) {
        setMfaToken(result.mfaToken);
        toast.info("Doğrulama kodunu girin (Authenticator)");
      } else {
        finishLogin(result);
      }
    } catch (err) {
      toast.error(err.response?.data?.detail || "Giriş başarısız");
    } finally {
      setLoading(false);
    }
  };

  const handleMfaVerify = async (e) => {
    e.preventDefault();
    setLoading(true);
    try {
      const userData = await verifyMfa(mfaToken, mfaCode);
      finishLogin(userData);
    } catch (err) {
      toast.error(err.response?.data?.detail || "Kod doğrulanamadı");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen flex items-center justify-center bg-gray-100">
      <div className="bg-white p-8 rounded-lg shadow-md w-full max-w-md">
        <h1 className="text-2xl font-bold text-center mb-8 tracking-wider">FACETTE ADMIN</h1>

        {!mfaToken ? (
          <form onSubmit={handleSubmit} className="space-y-4">
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">E-posta</label>
              <input
                type="email"
                value={formData.email}
                onChange={(e) => setFormData({ ...formData, email: e.target.value })}
                required
                className="w-full border border-gray-300 px-3 py-2 rounded focus:outline-none focus:ring-1 focus:ring-black"
                data-testid="admin-email-input"
              />
            </div>

            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Şifre</label>
              <input
                type="password"
                value={formData.password}
                onChange={(e) => setFormData({ ...formData, password: e.target.value })}
                required
                className="w-full border border-gray-300 px-3 py-2 rounded focus:outline-none focus:ring-1 focus:ring-black"
                data-testid="admin-password-input"
              />
            </div>

            <button
              type="submit"
              disabled={loading}
              className="w-full bg-black text-white py-3 rounded hover:bg-gray-900 transition-colors disabled:opacity-50 mt-4"
              data-testid="admin-submit-btn"
            >
              {loading ? "Giriş Yapılıyor..." : "Giriş Yap"}
            </button>
          </form>
        ) : (
          <form onSubmit={handleMfaVerify} className="space-y-4" data-testid="admin-mfa-form">
            <p className="text-sm text-gray-600 text-center">
              Authenticator uygulamandaki 6 haneli kodu gir.
            </p>
            <input
              type="text"
              inputMode="numeric"
              autoFocus
              maxLength={6}
              value={mfaCode}
              onChange={(e) => setMfaCode(e.target.value.replace(/\D/g, ""))}
              placeholder="000000"
              className="w-full border border-gray-300 px-3 py-3 rounded text-center text-2xl tracking-[0.5em] focus:outline-none focus:ring-1 focus:ring-black"
              data-testid="admin-mfa-code-input"
            />
            <button
              type="submit"
              disabled={loading || mfaCode.length !== 6}
              className="w-full bg-black text-white py-3 rounded hover:bg-gray-900 transition-colors disabled:opacity-50"
              data-testid="admin-mfa-verify-btn"
            >
              {loading ? "Doğrulanıyor..." : "Doğrula ve Giriş Yap"}
            </button>
            <button
              type="button"
              onClick={() => { setMfaToken(null); setMfaCode(""); }}
              className="w-full text-sm text-gray-500 hover:text-black"
            >
              ← Geri
            </button>
          </form>
        )}
      </div>
    </div>
  );
}
