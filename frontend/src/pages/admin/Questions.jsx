import { useState, useEffect } from "react";
import { MessageCircle, Check, Clock, Send, RefreshCw } from "lucide-react";
import axios from "axios";
import { toast } from "sonner";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from "../../components/ui/dialog";

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;

// Marketplace styling config – border color, badge background, label
const MARKETPLACE_STYLE = {
  trendyol: {
    border: "#F27A1A",
    bg: "#F27A1A",
    text: "#ffffff",
    label: "Trendyol",
    short: "ty",
  },
  hepsiburada: {
    border: "#FF6000",
    bg: "#FF6000",
    text: "#ffffff",
    label: "Hepsiburada",
    short: "hb",
  },
  temu: {
    border: "#111827",
    bg: "#111827",
    text: "#ffffff",
    label: "Temu",
    short: "temu",
  },
};

const MarketplaceBadge = ({ marketplace }) => {
  const style = MARKETPLACE_STYLE[marketplace] || MARKETPLACE_STYLE.trendyol;
  return (
    <span
      data-testid={`mp-badge-${marketplace || "trendyol"}`}
      className="inline-flex items-center gap-1 px-3 py-1 rounded-md text-[11px] font-black uppercase tracking-widest shadow-sm"
      style={{ background: style.bg, color: style.text }}
    >
      {style.label}
    </span>
  );
};

export default function AdminQuestions() {
  const [questions, setQuestions] = useState([]);
  const [loading, setLoading] = useState(true);
  const [syncing, setSyncing] = useState(false);
  const [statusFilter, setStatusFilter] = useState("WAITING_FOR_ANSWER");
  const [marketplaceFilter, setMarketplaceFilter] = useState("all");
  const [page, setPage] = useState(0);
  const [total, setTotal] = useState(0);
  const [totals, setTotals] = useState({});

  // Answer modal
  const [answerOpen, setAnswerOpen] = useState(false);
  const [selectedQuestion, setSelectedQuestion] = useState(null);
  const [answerText, setAnswerText] = useState("");
  const [sendingAnswer, setSendingAnswer] = useState(false);

  useEffect(() => {
    fetchQuestions();
  }, [statusFilter, marketplaceFilter, page]);

  const fetchQuestions = async () => {
    setLoading(true);
    try {
      const token = localStorage.getItem("token");
      let url = `${API}/integrations/marketplace/questions?page=${page}&size=20&marketplace=${marketplaceFilter}`;
      if (statusFilter) url += `&status=${statusFilter}`;
      const res = await axios.get(url, { headers: { Authorization: `Bearer ${token}` } });
      setQuestions(res.data?.questions || []);
      setTotal(res.data?.total || 0);
      setTotals(res.data?.totals || {});
    } catch (err) {
      console.error(err);
      toast.error("Sorular yüklenemedi");
    } finally {
      setLoading(false);
    }
  };

  const syncQuestions = async (mp) => {
    setSyncing(true);
    try {
      const token = localStorage.getItem("token");
      const endpoint =
        mp === "trendyol"
          ? `${API}/integrations/trendyol/questions/sync`
          : `${API}/integrations/${mp}/questions/sync`;
      const res = await axios.get(endpoint, { headers: { Authorization: `Bearer ${token}` } }).catch(async (e) => {
        // trendyol uses GET, stubs use POST – retry as POST if GET fails
        if (mp !== "trendyol") {
          return await axios.post(endpoint, {}, { headers: { Authorization: `Bearer ${token}` } });
        }
        throw e;
      });
      toast.success(`${MARKETPLACE_STYLE[mp].label}: ${res.data.synced || 0} yeni soru`);
      fetchQuestions();
    } catch (err) {
      toast.error(err.response?.data?.detail || "Senkronizasyon başarısız");
    } finally {
      setSyncing(false);
    }
  };

  const handleAnswer = async () => {
    if (!answerText.trim()) return;
    setSendingAnswer(true);
    try {
      const token = localStorage.getItem("token");
      const mp = selectedQuestion.marketplace || "trendyol";
      const endpoint =
        mp === "trendyol"
          ? `${API}/integrations/trendyol/questions/${selectedQuestion.question_id}/answer`
          : `${API}/integrations/${mp}/questions/${selectedQuestion.question_id}/answer`;
      await axios.post(
        endpoint,
        { answer: answerText },
        { headers: { Authorization: `Bearer ${token}` } }
      );
      toast.success("Cevap gönderildi");
      setAnswerOpen(false);
      fetchQuestions();
    } catch (err) {
      toast.error(err.response?.data?.detail || "Cevap gönderilemedi");
    } finally {
      setSendingAnswer(false);
    }
  };

  const getRemainingTime = (isoStr) => {
    if (!isoStr) return null;
    const created = new Date(isoStr);
    const deadline = new Date(created.getTime() + 24 * 60 * 60 * 1000);
    const now = new Date();
    const diff = deadline.getTime() - now.getTime();
    if (diff <= 0) return { expired: true, text: "Süre Doldu" };
    const hours = Math.floor(diff / (1000 * 60 * 60));
    const minutes = Math.floor((diff % (1000 * 60 * 60)) / (1000 * 60));
    return { expired: false, text: `${hours}s ${minutes}d kaldı` };
  };

  const formatDate = (isoStr) => {
    if (!isoStr) return "-";
    return new Date(isoStr).toLocaleString("tr-TR");
  };

  return (
    <div className="p-6 max-w-6xl mx-auto" data-testid="admin-questions-page">
      <div className="flex justify-between items-center mb-6">
        <div>
          <h1 className="text-2xl font-bold flex items-center gap-2">
            <MessageCircle className="text-blue-600" />
            Müşteri Soruları
          </h1>
          <p className="text-sm text-gray-500 mt-1">
            Trendyol, Hepsiburada ve Temu pazaryerlerinden gelen soruları tek noktadan yönetin.
          </p>
        </div>
        <div className="flex gap-2">
          <button
            onClick={() => syncQuestions("trendyol")}
            disabled={syncing}
            data-testid="sync-trendyol-btn"
            className="flex items-center gap-2 px-3 py-2 bg-orange-50 text-orange-600 border border-orange-200 rounded-lg text-xs font-medium hover:bg-orange-100 disabled:opacity-50"
          >
            <RefreshCw size={14} className={syncing ? "animate-spin" : ""} />
            Trendyol
          </button>
          <button
            onClick={() => syncQuestions("hepsiburada")}
            disabled={syncing}
            data-testid="sync-hepsiburada-btn"
            className="flex items-center gap-2 px-3 py-2 bg-red-50 text-red-600 border border-red-200 rounded-lg text-xs font-medium hover:bg-red-100 disabled:opacity-50"
          >
            <RefreshCw size={14} className={syncing ? "animate-spin" : ""} />
            Hepsiburada
          </button>
          <button
            onClick={() => syncQuestions("temu")}
            disabled={syncing}
            data-testid="sync-temu-btn"
            className="flex items-center gap-2 px-3 py-2 bg-gray-900 text-white border border-gray-900 rounded-lg text-xs font-medium hover:bg-gray-700 disabled:opacity-50"
          >
            <RefreshCw size={14} className={syncing ? "animate-spin" : ""} />
            Temu
          </button>
        </div>
      </div>

      <div className="bg-white rounded-xl border shadow-sm">
        <div className="p-4 border-b flex flex-wrap gap-3 items-center">
          <select
            value={marketplaceFilter}
            onChange={(e) => { setMarketplaceFilter(e.target.value); setPage(0); }}
            data-testid="marketplace-filter"
            className="border rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-1"
          >
            <option value="all">Tüm Pazaryerleri</option>
            <option value="trendyol">Trendyol</option>
            <option value="hepsiburada">Hepsiburada</option>
            <option value="temu">Temu</option>
          </select>
          <select
            value={statusFilter}
            onChange={(e) => { setStatusFilter(e.target.value); setPage(0); }}
            className="border rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-1"
          >
            <option value="WAITING_FOR_ANSWER">Cevap Bekleyenler</option>
            <option value="ANSWERED">Cevaplananlar</option>
            <option value="REPORTED">Şikayet Edilenler</option>
            <option value="">Tümü</option>
          </select>
          <div className="ml-auto flex flex-wrap gap-2 text-[11px]">
            {Object.entries(totals).map(([mp, n]) => (
              <span
                key={mp}
                className="px-2 py-1 rounded-full font-bold uppercase tracking-wider text-white"
                style={{ background: MARKETPLACE_STYLE[mp]?.bg || "#666" }}
              >
                {MARKETPLACE_STYLE[mp]?.label || mp}: {n}
              </span>
            ))}
          </div>
        </div>

        <div className="divide-y max-h-[70vh] overflow-y-auto">
          {loading ? (
            <div className="p-8 text-center text-gray-500">Yükleniyor...</div>
          ) : questions.length === 0 ? (
            <div className="p-8 text-center text-gray-500">Soru bulunamadı</div>
          ) : (
            questions.map(q => {
              const mp = q.marketplace || "trendyol";
              const style = MARKETPLACE_STYLE[mp] || MARKETPLACE_STYLE.trendyol;
              return (
                <div
                  key={`${mp}-${q.question_id}`}
                  data-testid={`question-row-${mp}`}
                  className={`p-4 hover:bg-gray-50 transition-colors relative ${q.status === 'WAITING_FOR_ANSWER' ? 'bg-blue-50/30' : ''}`}
                  style={{ borderLeft: `6px solid ${style.border}` }}
                >
                  {/* Marketplace badge – top right */}
                  <div className="absolute top-3 right-3">
                    <MarketplaceBadge marketplace={mp} />
                  </div>

                  <div className="flex justify-between items-start mb-2 pr-28">
                    <div className="flex items-center gap-2">
                      {q.status === 'WAITING_FOR_ANSWER' ? (() => {
                        const timeObj = getRemainingTime(q.created_date);
                        return (
                          <>
                            <span className="flex items-center gap-1 text-xs font-medium text-orange-600 bg-orange-100 px-2 py-1 rounded-full">
                              <Clock size={12} /> Bekliyor
                            </span>
                            {timeObj && (
                              <span className={`text-xs font-medium px-2 py-1 rounded-full ${timeObj.expired ? 'text-red-600 bg-red-100' : 'text-blue-600 bg-blue-100'}`}>
                                {timeObj.text}
                              </span>
                            )}
                          </>
                        );
                      })() : (
                        <span className="flex items-center gap-1 text-xs font-medium text-green-600 bg-green-100 px-2 py-1 rounded-full">
                          <Check size={12} /> Cevaplandı
                        </span>
                      )}
                      <span className="text-xs text-gray-500 font-medium" title="Sorulma Zamanı">
                        {formatDate(q.created_date)}
                      </span>
                    </div>
                    <button
                      onClick={() => {
                        setSelectedQuestion(q);
                        setAnswerText(q.answer || "");
                        setAnswerOpen(true);
                      }}
                      data-testid={`answer-btn-${mp}-${q.question_id}`}
                      className="flex items-center gap-1 px-3 py-1.5 text-sm font-medium text-blue-600 bg-blue-50 rounded-lg hover:bg-blue-100 mt-8"
                    >
                      {q.status === 'WAITING_FOR_ANSWER' ? 'Cevapla' : 'Görüntüle'}
                    </button>
                  </div>
                  <div className="flex items-center gap-3 mb-3">
                    {q.image_url ? (
                      <img src={q.image_url} alt="..." className="w-12 h-16 object-cover rounded border bg-white" />
                    ) : (
                      <div className="w-12 h-16 bg-gray-100 rounded border flex items-center justify-center text-xs text-gray-400 text-center">Görsel Yok</div>
                    )}
                    <h3 className="font-medium text-gray-900">{q.product_name}</h3>
                  </div>
                  <div className="bg-gray-50 border rounded-lg p-3 text-sm text-gray-700 italic mb-2 relative">
                    <span className="absolute -left-2 -top-2 text-3xl text-gray-300">"</span>
                    <p className="pl-3">{q.question_text}</p>
                  </div>

                  <p className="text-xs text-gray-500 font-medium">— {q.customer_name}</p>

                  {q.answer && (
                    <div className="mt-3 pl-4 border-l-2" style={{ borderColor: style.border }}>
                      <p className="text-xs text-gray-500 mb-1">Verilen Cevap:</p>
                      <p className="text-sm text-gray-800">{q.answer}</p>
                    </div>
                  )}
                </div>
              );
            })
          )}
        </div>
      </div>

      <Dialog open={answerOpen} onOpenChange={setAnswerOpen}>
        <DialogContent className="max-w-xl">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-3">
              Müşteri Sorusunu Yanıtla
              {selectedQuestion && <MarketplaceBadge marketplace={selectedQuestion.marketplace || "trendyol"} />}
            </DialogTitle>
          </DialogHeader>

          {selectedQuestion && (
            <div className="space-y-4 pt-2">
              <div className="bg-gray-50 p-3 rounded-lg border text-sm">
                <div className="flex items-start gap-3 mb-2">
                  {selectedQuestion.image_url && (
                    <img src={selectedQuestion.image_url} alt="..." className="w-10 h-10 object-cover rounded border bg-white shrink-0" />
                  )}
                  <p className="font-medium text-gray-900 mt-1">{selectedQuestion.product_name}</p>
                </div>
                <p className="text-gray-700 italic">"{selectedQuestion.question_text}"</p>
                <p className="text-xs text-gray-500 mt-2">— {selectedQuestion.customer_name}</p>
              </div>

              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">Cevabınız</label>
                <textarea
                  className="w-full border rounded-lg p-3 text-sm min-h-[120px] focus:ring-1 focus:outline-none"
                  placeholder="Müşteriye verilecek cevabı buraya yazın..."
                  value={answerText}
                  onChange={(e) => setAnswerText(e.target.value)}
                  disabled={selectedQuestion.status !== 'WAITING_FOR_ANSWER'}
                  data-testid="answer-textarea"
                />
              </div>

              {selectedQuestion.status === 'WAITING_FOR_ANSWER' && (
                <div className="flex justify-end pt-2">
                  <button
                    onClick={handleAnswer}
                    disabled={sendingAnswer || !answerText.trim()}
                    data-testid="send-answer-btn"
                    className="flex items-center gap-2 px-4 py-2 bg-blue-600 text-white rounded-lg text-sm font-medium hover:bg-blue-700 disabled:opacity-50"
                  >
                    {sendingAnswer ? (
                      "Gönderiliyor..."
                    ) : (
                      <>
                        <Send size={16} /> Gönder
                      </>
                    )}
                  </button>
                </div>
              )}
            </div>
          )}
        </DialogContent>
      </Dialog>
    </div>
  );
}
