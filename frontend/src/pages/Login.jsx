import { useState } from "react";
import { useNavigate, Link } from "react-router-dom";
import { toast } from "sonner";
import Header from "../components/Header";
import Footer from "../components/Footer";
import { useAuth } from "../context/AuthContext";

export default function Login() {
  const navigate = useNavigate();
  const { login, register, user } = useAuth();
  const [isRegister, setIsRegister] = useState(false);
  const [loading, setLoading] = useState(false);
  const [formData, setFormData] = useState({
    email: "",
    password: "",
    first_name: "",
    last_name: "",
    phone: "",
  });

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
    <div className="min-h-screen" data-testid="login-page">
      <Header />

      <div className="container-main py-16">
        <div className="max-w-md mx-auto">
          <h1 className="text-2xl font-medium text-center mb-8">
            {isRegister ? "Üye Ol" : "Giriş Yap"}
          </h1>

          <form onSubmit={handleSubmit} className="space-y-4">
            {isRegister && (
              <>
                <div>
                  <label className="block text-sm mb-1">Ad</label>
                  <input
                    type="text"
                    value={formData.first_name}
                    onChange={(e) => setFormData({ ...formData, first_name: e.target.value })}
                    className="w-full border px-4 py-3 text-sm focus:outline-none focus:border-black"
                  />
                </div>
                <div>
                  <label className="block text-sm mb-1">Soyad</label>
                  <input
                    type="text"
                    value={formData.last_name}
                    onChange={(e) => setFormData({ ...formData, last_name: e.target.value })}
                    className="w-full border px-4 py-3 text-sm focus:outline-none focus:border-black"
                  />
                </div>
              </>
            )}
            
            <div>
              <label className="block text-sm mb-1">E-posta *</label>
              <input
                type="email"
                value={formData.email}
                onChange={(e) => setFormData({ ...formData, email: e.target.value })}
                required
                className="w-full border px-4 py-3 text-sm focus:outline-none focus:border-black"
                data-testid="email-input"
              />
            </div>
            
            <div>
              <label className="block text-sm mb-1">Şifre *</label>
              <input
                type="password"
                value={formData.password}
                onChange={(e) => setFormData({ ...formData, password: e.target.value })}
                required
                minLength={6}
                className="w-full border px-4 py-3 text-sm focus:outline-none focus:border-black"
                data-testid="password-input"
              />
            </div>

            <button
              type="submit"
              disabled={loading}
              className="btn-primary w-full disabled:opacity-50"
              data-testid="submit-btn"
            >
              {loading ? "İşleniyor..." : isRegister ? "Üye Ol" : "Giriş Yap"}
            </button>
          </form>

          <div className="text-center mt-6">
            <button
              onClick={() => setIsRegister(!isRegister)}
              className="text-sm underline"
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
