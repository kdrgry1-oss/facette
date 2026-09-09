import { useEffect, useState } from 'react';
import axios from 'axios';
import Header from '../components/Header';
import Footer from '../components/Footer';
import FullLookSections from '../components/FullLookSections';
import { applyRuntimeSeo, setCategorySeo } from '../lib/seo';
const API = `${process.env.REACT_APP_BACKEND_URL}/api`;

export default function FullLook() {
  const [data, setData] = useState(null);
  const [error, setError] = useState(false);
  const [retry, setRetry] = useState(0);
  useEffect(() => {
    const controller = new AbortController();
    setError(false); setData(null);
    axios.get(`${API}/full-look`, {signal: controller.signal}).then(r => { if (!controller.signal.aborted) setData(r.data); })
      .catch(() => { if (!controller.signal.aborted) setError(true); });
    return () => controller.abort();
  }, [retry]);
  useEffect(() => {
    const controller = new AbortController();
    applyRuntimeSeo('/kategori/full-look', () => setCategorySeo(data?.title || 'Full Look', 'full-look', '', data?.description), { signal: controller.signal });
    return () => controller.abort();
  }, [data?.title, data?.description]);
  return <div className="sf-page min-h-screen bg-white"><Header /><main className="full-look-page">
    <header className="full-look-heading"><h1>{data?.title || 'Full Look'}</h1>{data?.description && <p>{data.description}</p>}</header>
    {error ? <div className="p-12 text-center" role="alert"><p>Kombinler şu an yüklenemedi.</p><button className="underline mt-4" onClick={() => setRetry(r => r + 1)}>Tekrar dene</button></div>
      : !data ? <p className="p-12 text-center" role="status">Kombinler yükleniyor…</p>
      : !data.looks?.length ? <p className="p-12 text-center text-stone-500">Yeni kombin seçkimiz yakında burada.</p>
      : <FullLookSections looks={data.looks} />}
  </main><Footer /></div>;
}
