import { useState, useEffect } from "react";
import { useNavigate, useLocation } from "react-router-dom";
import { toast } from "sonner";
import Header from "../components/Header";
import Footer from "../components/Footer";
import { useAuth } from "../context/AuthContext";
import axios from "axios";

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;

export default function Login() {
  const navigate = useNavigate();
  const location = useLocation();
  const { login, register, user, setUser } = useAuth();
  const [isRegister, setIsRegister] = useState(false);
  const [loading, setLoading] = useState(false);
  // FAZ 3+ — Hangi sosyal sağlayıcılar aktif?
  const [socialProviders, setSocialProviders] = useState({ apple: false, facebook: false });
  useEffect(() => {
    fetch(`${API}/auth/social/providers`).then((r) => r.ok && r.json())
      .then((d) => d && setSocialProviders(d)).catch(() => {});
  }, []);
  const [formData, setFormData] = useState({
    email: "",
    password: "",
    first_name: "",
    last_name: "",
    phone: "",
  });

  // Handle Google OAuth callback
  useEffect(() => {
    const hash = window.location.hash;
    if (hash.includes('session_id=')) {
      const sessionId = hash.split('session_id=')[1]?.split('&')[0];
      if (sessionId) {
        handleGoogleCallback(sessionId);
      }
    }
  }, []);

  const handleGoogleCallback = async (sessionId) => {
    setLoading(true);
    try {
      const res = await axios.post(`${API}/auth/google/session?session_id=${sessionId}`);
      if (res.data.success) {
        localStorage.setItem('token', res.data.token);
        setUser(res.data.user);
        toast.success("Google ile giriş başarılı!");
        // Clear hash and redirect
        window.history.replaceState(null, '', window.location.pathname);
        navigate("/hesabim");
      }
    } catch (err) {
      toast.error("Google ile giriş başarısız");
      window.history.replaceState(null, '', window.location.pathname);
    } finally {
      setLoading(false);
    }
  };

  // REMINDER: DO NOT HARDCODE THE URL, OR ADD ANY FALLBACKS OR REDIRECT URLS, THIS BREAKS THE AUTH
  const handleGoogleLogin = () => {
    const redirectUrl = window.location.origin + '/giris';
    window.location.href = `https://auth.emergentagent.com/?redirect=${encodeURIComponent(redirectUrl)}`;
  };

  if (user) {
    navigate("/hesabim");
    return null;
  }

  const handleSubmit = async (e) => {
    e.preventDefault();
    setLoading(true);

    try {
      if (isRegister) {
        await register(formData);
        toast.success("Kayıt başarılı!");
      } else {
        await login(formData.email, formData.password);
        toast.success("Giriş başarılı!");
      }
      navigate("/hesabim");
    } catch (err) {
      toast.error(err.response?.data?.detail || "İşlem başarısız");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen">
      <Header />

      <div className="max-w-screen-2xl mx-auto px-4 py-16">
        <div className="max-w-sm mx-auto">
          <h1 className="text-xl font-medium text-center mb-8">
            {isRegister ? "Üye Ol" : "Giriş Yap"}
          </h1>

          {/* Google Login Button */}
          <button
            onClick={handleGoogleLogin}
            disabled={loading}
            className="w-full flex items-center justify-center gap-3 border border-gray-300 px-4 py-3 text-sm hover:bg-gray-50 transition-colors mb-6"
          >
            <svg className="w-5 h-5" viewBox="0 0 24 24">
              <path fill="#4285F4" d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z"/>
              <path fill="#34A853" d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z"/>
              <path fill="#FBBC05" d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l2.85-2.22.81-.62z"/>
              <path fill="#EA4335" d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z"/>
            </svg>
            Google ile {isRegister ? "Üye Ol" : "Giriş Yap"}
          </button>

          {/* Apple Sign-In — credential'lar admin tarafından etkinleştirildiyse görünür */}
          {socialProviders.apple && (
            <button type="button"
              onClick={() => toast.info("Apple Sign-In yakında aktif olacak (Developer credential girildi)")}
              disabled={loading}
              className="w-full flex items-center justify-center gap-3 border border-black bg-black text-white px-4 py-3 text-sm hover:bg-gray-900 transition-colors mb-3"
              data-testid="apple-login-btn">
              <svg className="w-5 h-5" viewBox="0 0 24 24" fill="currentColor">
                <path d="M17.05 12.54c.02 2.8 2.43 3.73 2.46 3.74-.02.07-.38 1.29-1.24 2.55-.75 1.1-1.53 2.19-2.76 2.22-1.21.02-1.59-.71-2.97-.71-1.38 0-1.8.69-2.94.73-1.18.04-2.08-1.18-2.83-2.28C5.2 16.53 4 12.93 5.61 10.54c.8-1.19 2.23-1.94 3.77-1.96 1.15-.02 2.23.78 2.93.78.7 0 2.02-.96 3.41-.82.58.02 2.21.23 3.26 1.77-.08.05-1.94 1.13-1.93 3.37zM14.51 7.34c.63-.76 1.05-1.82.94-2.88-.9.04-2 .6-2.65 1.36-.58.67-1.09 1.75-.95 2.78 1.01.08 2.03-.51 2.66-1.26z"/>
              </svg>
              Apple ile {isRegister ? "Üye Ol" : "Giriş Yap"}
            </button>
          )}

          {/* Facebook Login */}
          {socialProviders.facebook && (
            <button type="button"
              onClick={() => toast.info("Facebook Login yakında aktif olacak (App ID girildi)")}
              disabled={loading}
              className="w-full flex items-center justify-center gap-3 border border-blue-600 bg-blue-600 text-white px-4 py-3 text-sm hover:bg-blue-700 transition-colors mb-3"
              data-testid="facebook-login-btn">
              <svg className="w-5 h-5" viewBox="0 0 24 24" fill="currentColor">
                <path d="M24 12.073c0-6.627-5.373-12-12-12S0 5.446 0 12.073C0 18.062 4.388 23.027 10.125 23.927v-8.385H7.078v-3.47h3.047V9.43c0-3.007 1.792-4.669 4.533-4.669 1.312 0 2.686.235 2.686.235v2.953H15.83c-1.491 0-1.956.925-1.956 1.874v2.25h3.328l-.532 3.47h-2.796v8.385C19.612 23.027 24 18.062 24 12.073z"/>
              </svg>
              Facebook ile {isRegister ? "Üye Ol" : "Giriş Yap"}
            </button>
          )}

          <div className="flex items-center gap-4 mb-6">
            <div className="flex-1 h-px bg-gray-200" />
            <span className="text-xs text-gray-500">veya</span>
            <div className="flex-1 h-px bg-gray-200" />
          </div>

          <form onSubmit={handleSubmit} className="space-y-4">
            {isRegister && (
              <>
                <div>
                  <label className="block text-xs mb-1">Ad</label>
                  <input
                    type="text"
                    value={formData.first_name}
                    onChange={(e) => setFormData({ ...formData, first_name: e.target.value })}
                    className="w-full border px-3 py-2.5 text-sm focus:outline-none focus:border-black"
                  />
                </div>
                <div>
                  <label className="block text-xs mb-1">Soyad</label>
                  <input
                    type="text"
                    value={formData.last_name}
                    onChange={(e) => setFormData({ ...formData, last_name: e.target.value })}
                    className="w-full border px-3 py-2.5 text-sm focus:outline-none focus:border-black"
                  />
                </div>
              </>
            )}
            
            <div>
              <label className="block text-xs mb-1">E-posta *</label>
              <input
                type="email"
                value={formData.email}
                onChange={(e) => setFormData({ ...formData, email: e.target.value })}
                required
                className="w-full border px-3 py-2.5 text-sm focus:outline-none focus:border-black"
                data-testid="email-input"
              />
            </div>
            
            <div>
              <label className="block text-xs mb-1">Şifre *</label>
              <input
                type="password"
                value={formData.password}
                onChange={(e) => setFormData({ ...formData, password: e.target.value })}
                required
                minLength={6}
                className="w-full border px-3 py-2.5 text-sm focus:outline-none focus:border-black"
                data-testid="password-input"
              />
            </div>

            <button
              type="submit"
              disabled={loading}
              className="w-full bg-black text-white py-3 text-xs uppercase tracking-wider hover:bg-gray-900 disabled:opacity-50"
              data-testid="submit-btn"
            >
              {loading ? "İşleniyor..." : isRegister ? "Üye Ol" : "Giriş Yap"}
            </button>
          </form>

          <div className="text-center mt-6">
            <button
              onClick={() => setIsRegister(!isRegister)}
              className="text-xs underline"
            >
              {isRegister ? "Zaten üye misiniz? Giriş yapın" : "Hesabınız yok mu? Üye olun"}
            </button>
          </div>
        </div>
      </div>

      <Footer />
    </div>
  );
}
