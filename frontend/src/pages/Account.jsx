import { Navigate } from "react-router-dom";
import Header from "../components/Header";
import Footer from "../components/Footer";
import { useAuth } from "../context/AuthContext";

export default function Account() {
  const { user, logout, loading } = useAuth();

  if (loading) {
    return (
      <div className="min-h-screen">
        <Header />
        <div className="container-main py-16 text-center">
          <p>Yükleniyor...</p>
        </div>
        <Footer />
      </div>
    );
  }

  if (!user) {
    return <Navigate to="/giris" />;
  }

  return (
    <div className="min-h-screen" data-testid="account-page">
      <Header />

      <div className="container-main py-8">
        <h1 className="text-2xl font-medium mb-8">Hesabım</h1>

        <div className="grid md:grid-cols-4 gap-8">
          {/* Sidebar */}
          <div className="md:col-span-1">
            <nav className="space-y-2">
              <a href="#profile" className="block py-2 text-sm font-medium">Profil Bilgileri</a>
              <a href="#orders" className="block py-2 text-sm text-gray-600 hover:text-black">Siparişlerim</a>
              <a href="#addresses" className="block py-2 text-sm text-gray-600 hover:text-black">Adreslerim</a>
              <button 
                onClick={logout}
                className="block py-2 text-sm text-red-500 hover:text-red-600"
              >
                Çıkış Yap
              </button>
            </nav>
          </div>

          {/* Content */}
          <div className="md:col-span-3">
            <div className="bg-white border p-6">
              <h2 className="text-lg font-medium mb-4">Profil Bilgileri</h2>
              <div className="space-y-4">
                <div>
                  <label className="block text-sm text-gray-500 mb-1">E-posta</label>
                  <p className="font-medium">{user.email}</p>
                </div>
                {user.first_name && (
                  <div>
                    <label className="block text-sm text-gray-500 mb-1">Ad Soyad</label>
                    <p className="font-medium">{user.first_name} {user.last_name}</p>
                  </div>
                )}
              </div>
            </div>
          </div>
        </div>
      </div>

      <Footer />
    </div>
  );
}
