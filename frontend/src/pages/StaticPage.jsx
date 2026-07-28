import { useState, useEffect } from "react";
import { sanitizeHtml } from "../lib/sanitizeHtml";
import { useParams } from "react-router-dom";
import axios from "axios";
import Header from "../components/Header";
import Footer from "../components/Footer";

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;

export default function StaticPage() {
  const { slug } = useParams();
  const [page, setPage] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetchPage();
  }, [slug]);

  const fetchPage = async () => {
    setLoading(true);
    try {
      const res = await axios.get(`${API}/pages/${slug}`);
      setPage(res.data);
    } catch (err) {
      console.error(err);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen" data-testid="static-page">
      <Header />

      <div className="container-main py-12 max-w-3xl">
        {loading ? (
          <div className="animate-pulse space-y-4">
            <div className="h-8 bg-gray-200 w-1/3" />
            <div className="h-4 bg-gray-200 w-full" />
            <div className="h-4 bg-gray-200 w-2/3" />
            <div className="h-4 bg-gray-200 w-full" />
          </div>
        ) : page ? (
          <>
            <h1 className="text-3xl md:text-4xl font-light tracking-tight text-black mb-8 md:mb-10">{page.title}</h1>
            {/* İçerik tipografisi — @tailwindcss/typography YOK; bu yüzden alt-eleman
                seçicileriyle (arbitrary variants) minimalist, okunaklı ve site fontuyla uyumlu
                stil verilir. Tüm statik sayfalar (Hakkımızda, Mesafeli Satış, KVKK...) aynı görünür. */}
            <div
              className="max-w-none text-neutral-700 font-light
                [&_p]:text-[15px] md:[&_p]:text-base [&_p]:leading-[1.9] [&_p]:mb-5 [&_p]:text-neutral-600
                [&_.lead]:text-lg md:[&_.lead]:text-2xl [&_.lead]:leading-relaxed [&_.lead]:tracking-tight [&_.lead]:text-black [&_.lead]:mb-10 [&_.lead]:font-light
                [&_h2]:text-2xl md:[&_h2]:text-3xl [&_h2]:font-light [&_h2]:tracking-tight [&_h2]:text-black [&_h2]:mt-12 [&_h2]:mb-4
                [&_h3]:text-lg md:[&_h3]:text-xl [&_h3]:font-medium [&_h3]:tracking-tight [&_h3]:text-black [&_h3]:mt-9 [&_h3]:mb-3
                [&_h4]:text-base [&_h4]:font-semibold [&_h4]:text-black [&_h4]:mt-6 [&_h4]:mb-2
                [&_strong]:font-semibold [&_strong]:text-black
                [&_a]:text-black [&_a]:underline [&_a]:underline-offset-2 hover:[&_a]:opacity-60
                [&_ul]:list-disc [&_ul]:pl-5 [&_ul]:mb-5 [&_ol]:list-decimal [&_ol]:pl-5 [&_ol]:mb-5 [&_li]:mb-2 [&_li]:leading-relaxed [&_li]:text-neutral-600
                [&_hr]:my-10 md:[&_hr]:my-12 [&_hr]:border-neutral-200
                [&_blockquote]:border-l-2 [&_blockquote]:border-black [&_blockquote]:pl-5 [&_blockquote]:italic [&_blockquote]:text-neutral-800 [&_blockquote]:my-8"
              dangerouslySetInnerHTML={{ __html: sanitizeHtml(page.content) }}
            />
          </>
        ) : (
          <div className="text-center py-16">
            <p className="text-gray-500">Sayfa bulunamadı</p>
          </div>
        )}
      </div>

      <Footer />
    </div>
  );
}
