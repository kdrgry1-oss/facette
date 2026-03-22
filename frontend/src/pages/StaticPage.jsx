import { useState, useEffect } from "react";
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
            <h1 className="text-3xl font-medium mb-8">{page.title}</h1>
            <div 
              className="prose prose-lg max-w-none"
              dangerouslySetInnerHTML={{ __html: page.content }}
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
