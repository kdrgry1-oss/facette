import { useState, useEffect } from "react";
import { MessageCircle, Check, Clock, Search, Send, RefreshCw } from "lucide-react";
import axios from "axios";
import { toast } from "sonner";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from "../../components/ui/dialog";

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;

export default function AdminQuestions() {
  const [questions, setQuestions] = useState([]);
  const [loading, setLoading] = useState(true);
  const [syncing, setSyncing] = useState(false);
  const [statusFilter, setStatusFilter] = useState("WAITING_FOR_ANSWER");
  const [page, setPage] = useState(0);
  const [total, setTotal] = useState(0);

  // Answer modal
  const [answerOpen, setAnswerOpen] = useState(false);
  const [selectedQuestion, setSelectedQuestion] = useState(null);
  const [answerText, setAnswerText] = useState("");
  const [sendingAnswer, setSendingAnswer] = useState(false);

  useEffect(() => {
    fetchQuestions();
  }, [statusFilter, page]);

  const fetchQuestions = async () => {
    setLoading(true);
    try {
      const token = localStorage.getItem("token");
      let url = `${API}/trendyol/questions?page=${page}&size=20`;
      if (statusFilter) url += `&status=${statusFilter}`;
      const res = await axios.get(url, { headers: { Authorization: `Bearer ${token}` } });
      setQuestions(res.data?.questions || []);
      setTotal(res.data?.total || 0);
    } catch (err) {
      console.error(err);
      toast.error("Sorular yüklenemedi");
    } finally {
      setLoading(false);
    }
  };

  const syncQuestions = async () => {
    setSyncing(true);
    try {
      const token = localStorage.getItem("token");
      const res = await axios.get(`${API}/trendyol/questions/sync`, {
        headers: { Authorization: `Bearer ${token}` }
      });
      toast.success(`${res.data.synced} yeni soru çekildi`);
      fetchQuestions();
    } catch (err) {
      toast.error("Senkronizasyon başarısız");
    } finally {
      setSyncing(false);
    }
  };

  const handleAnswer = async () => {
    if (!answerText.trim()) return;
    setSendingAnswer(true);
    try {
      const token = localStorage.getItem("token");
      await axios.post(
        `${API}/trendyol/questions/${selectedQuestion.question_id}/answer`,
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
    const deadline = new Date(created.getTime() + 24 * 60 * 60 * 1000); // 24 hours
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
    <div className="p-6 max-w-6xl mx-auto">
      <div className="flex justify-between items-center mb-6">
        <div>
          <h1 className="text-2xl font-bold flex items-center gap-2">
            <MessageCircle className="text-blue-600" />
            Müşteri Soruları (Trendyol)
          </h1>
          <p className="text-sm text-gray-500 mt-1">
            Gelen müşteri sorularını görün ve yanıtlayın.
          </p>
        </div>
        <button
          onClick={syncQuestions}
          disabled={syncing}
          className="flex items-center gap-2 px-4 py-2 bg-orange-50 text-orange-600 border border-orange-200 rounded-lg text-sm font-medium hover:bg-orange-100 disabled:opacity-50"
        >
          <RefreshCw size={16} className={syncing ? "animate-spin" : ""} />
          Trendyol'dan Çek
        </button>
      </div>

      <div className="bg-white rounded-xl border shadow-sm">
        <div className="p-4 border-b flex gap-4">
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
        </div>

        <div className="divide-y max-h-[70vh] overflow-y-auto">
          {loading ? (
            <div className="p-8 text-center text-gray-500">Yükleniyor...</div>
          ) : questions.length === 0 ? (
            <div className="p-8 text-center text-gray-500">Soru bulunamadı</div>
          ) : (
            questions.map(q => (
              <div key={q.question_id} className={`p-4 hover:bg-gray-50 transition-colors ${q.status === 'WAITING_FOR_ANSWER' ? 'bg-blue-50/30' : ''}`}>
                <div className="flex justify-between items-start mb-2">
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
                    className="flex items-center gap-1 px-3 py-1.5 text-sm font-medium text-blue-600 bg-blue-50 rounded-lg hover:bg-blue-100"
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
                  <div className="mt-3 pl-4 border-l-2 border-green-400">
                    <p className="text-xs text-gray-500 mb-1">Verilen Cevap:</p>
                    <p className="text-sm text-gray-800">{q.answer}</p>
                  </div>
                )}
              </div>
            ))
          )}
        </div>
      </div>

      <Dialog open={answerOpen} onOpenChange={setAnswerOpen}>
        <DialogContent className="max-w-xl">
          <DialogHeader>
            <DialogTitle>Müşteri Sorusunu Yanıtla</DialogTitle>
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
                />
              </div>

              {selectedQuestion.status === 'WAITING_FOR_ANSWER' && (
                <div className="flex justify-end pt-2">
                  <button
                    onClick={handleAnswer}
                    disabled={sendingAnswer || !answerText.trim()}
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
