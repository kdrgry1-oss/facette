import { Link } from "react-router-dom";
import { Instagram, Facebook, Twitter } from "lucide-react";

export default function Footer() {
  return (
    <footer className="bg-black text-white mt-20">
      <div className="container-main py-16">
        <div className="grid grid-cols-1 md:grid-cols-4 gap-10">
          {/* Logo & Description */}
          <div className="md:col-span-1">
            <h3 className="text-2xl font-bold tracking-[0.3em] mb-4">FACETTE</h3>
            <p className="text-gray-400 text-sm leading-relaxed">
              Farkı Hisset. Kadın modasında yeni koleksiyon ve trendler.
            </p>
            <div className="flex gap-4 mt-6">
              <a href="#" className="hover:text-gray-400 transition-colors" aria-label="Instagram">
                <Instagram size={20} />
              </a>
              <a href="#" className="hover:text-gray-400 transition-colors" aria-label="Facebook">
                <Facebook size={20} />
              </a>
              <a href="#" className="hover:text-gray-400 transition-colors" aria-label="Twitter">
                <Twitter size={20} />
              </a>
            </div>
          </div>

          {/* Quick Links */}
          <div>
            <h4 className="text-sm font-semibold uppercase tracking-wider mb-4">Alışveriş</h4>
            <ul className="space-y-2">
              <li><Link to="/kategori/en-yeniler" className="text-gray-400 text-sm hover:text-white transition-colors">En Yeniler</Link></li>
              <li><Link to="/kategori/elbise" className="text-gray-400 text-sm hover:text-white transition-colors">Elbise</Link></li>
              <li><Link to="/kategori/pantolon" className="text-gray-400 text-sm hover:text-white transition-colors">Pantolon</Link></li>
              <li><Link to="/kategori/ceket" className="text-gray-400 text-sm hover:text-white transition-colors">Ceket</Link></li>
              <li><Link to="/kategori/aksesuar" className="text-gray-400 text-sm hover:text-white transition-colors">Aksesuar</Link></li>
            </ul>
          </div>

          {/* Customer Service */}
          <div>
            <h4 className="text-sm font-semibold uppercase tracking-wider mb-4">Müşteri Hizmetleri</h4>
            <ul className="space-y-2">
              <li><Link to="/sayfa/hakkimizda" className="text-gray-400 text-sm hover:text-white transition-colors">Hakkımızda</Link></li>
              <li><Link to="/sayfa/iade-kosullari" className="text-gray-400 text-sm hover:text-white transition-colors">İade & Değişim</Link></li>
              <li><Link to="/sayfa/kvkk" className="text-gray-400 text-sm hover:text-white transition-colors">KVKK</Link></li>
              <li><Link to="/sayfa/gizlilik" className="text-gray-400 text-sm hover:text-white transition-colors">Gizlilik Politikası</Link></li>
              <li><Link to="/sayfa/iletisim" className="text-gray-400 text-sm hover:text-white transition-colors">İletişim</Link></li>
            </ul>
          </div>

          {/* Contact */}
          <div>
            <h4 className="text-sm font-semibold uppercase tracking-wider mb-4">İletişim</h4>
            <ul className="space-y-2 text-gray-400 text-sm">
              <li>info@facette.com</li>
              <li>+90 212 000 00 00</li>
              <li className="pt-2">
                Pazartesi - Cumartesi<br />
                10:00 - 18:00
              </li>
            </ul>
          </div>
        </div>

        {/* Bottom */}
        <div className="border-t border-gray-800 mt-12 pt-8 flex flex-col md:flex-row justify-between items-center gap-4">
          <p className="text-gray-500 text-xs">
            © 2024 FACETTE. Tüm hakları saklıdır.
          </p>
          <div className="flex items-center gap-4">
            <img src="https://upload.wikimedia.org/wikipedia/commons/5/5e/Visa_Inc._logo.svg" alt="Visa" className="h-6 opacity-60" />
            <img src="https://upload.wikimedia.org/wikipedia/commons/2/2a/Mastercard-logo.svg" alt="Mastercard" className="h-6 opacity-60" />
          </div>
        </div>
      </div>
    </footer>
  );
}
