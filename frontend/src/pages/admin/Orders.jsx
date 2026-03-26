import { useState, useEffect } from "react";
import { FolderOpen, RefreshCw, Printer, FileText, Copy, FileCheck, MessageSquare, Package, Truck, Tag, CheckSquare, Square, Filter, Search, Eye, Store, Info } from "lucide-react";
import axios from "axios";
import { toast } from "sonner";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from "../../components/ui/dialog";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "../../components/ui/select";

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;

const statusOptions = [
  { value: "pending", label: "Bekliyor", class: "status-pending" },
  { value: "confirmed", label: "Onaylandı", class: "status-confirmed" },
  { value: "preparing", label: "Hazırlanıyor", class: "status-preparing" },
  { value: "shipping", label: "Kargoda", class: "status-shipped" },
  { value: "delivered", label: "Teslim Edildi", class: "status-delivered" },
  { value: "cancelled", label: "İptal Edildi", class: "status-cancelled" },
];

const cargoCompanies = [
  { value: "MNG", label: "MNG Kargo" },
  { value: "DHL", label: "DHL" },
  { value: "YURTICI", label: "Yurtiçi Kargo" },
  { value: "ARAS", label: "Aras Kargo" },
  { value: "PTT", label: "PTT Kargo" },
];

export default function AdminOrders() {
  const [orders, setOrders] = useState([]);
  const [loading, setLoading] = useState(true);
  const [page, setPage] = useState(1);
  const [total, setTotal] = useState(0);
  const [statusFilter, setStatusFilter] = useState("");
  const [advancedFiltersOpen, setAdvancedFiltersOpen] = useState(false);
  const [filters, setFilters] = useState({
    search: "", phone: "", email: "", order_number: "", 
    cargo_tracking: "", start_date: "", end_date: "", 
    payment_method: "", platform: ""
  });
  const [selectedOrder, setSelectedOrder] = useState(null);
  const [detailOpen, setDetailOpen] = useState(false);
  const [selectedOrders, setSelectedOrders] = useState([]);
  const [bulkAction, setBulkAction] = useState("");
  const [selectedCargo, setSelectedCargo] = useState("MNG");
  const [shipModalOpen, setShipModalOpen] = useState(false);
  const [exporting, setExporting] = useState(false);
  const [cargoTrackingNumbers, setCargoTrackingNumbers] = useState({});

  // Trendyol Manual Import State
  const [trendyolModalOpen, setTrendyolModalOpen] = useState(false);
  const [trendyolQueryType, setTrendyolQueryType] = useState('order_number');
  const [trendyolOrderNumber, setTrendyolOrderNumber] = useState("");
  const [trendyolStartDate, setTrendyolStartDate] = useState("");
  const [trendyolEndDate, setTrendyolEndDate] = useState("");
  const [trendyolPreviewOrders, setTrendyolPreviewOrders] = useState([]);
  const [trendyolSelectedOrders, setTrendyolSelectedOrders] = useState([]);
  const [trendyolPreviewing, setTrendyolPreviewing] = useState(false);
  const [trendyolImporting, setTrendyolImporting] = useState(false);
  const [shipOrderId, setShipOrderId] = useState(null);
  const [trackingNumber, setTrackingNumber] = useState("");

  // Trendyol Invoice Upload State
  const [invoiceLinkInput, setInvoiceLinkInput] = useState("");
  const [invoiceNumberInput, setInvoiceNumberInput] = useState("");
  const [uploadingInvoice, setUploadingInvoice] = useState(false);

  useEffect(() => {
    fetchOrders();
  }, [page, statusFilter]);

  const fetchOrders = async () => {
    setLoading(true);
    try {
      const token = localStorage.getItem('token');
      let url = `${API}/orders?page=${page}&limit=20`;
      if (statusFilter) url += `&status=${statusFilter}`;
      Object.keys(filters).forEach(key => {
        if (filters[key]) url += `&${key}=${filters[key]}`;
      });
      const res = await axios.get(url, { headers: { Authorization: `Bearer ${token}` } });
      setOrders(res.data?.orders || []);
      setTotal(res.data?.total || 0);
    } catch (err) {
      console.error(err);
    } finally {
      setLoading(false);
    }
  };

  const handleStatusChange = async (orderId, newStatus) => {
    try {
      const token = localStorage.getItem('token');
      await axios.put(`${API}/orders/${orderId}/status?status=${newStatus}`, {}, {
        headers: { Authorization: `Bearer ${token}` }
      });
      toast.success("Sipariş durumu güncellendi");
      fetchOrders();
      if (selectedOrder?.id === orderId) {
        setSelectedOrder({ ...selectedOrder, status: newStatus });
      }
    } catch (err) {
      toast.error("Güncelleme başarısız");
    }
  };

  const handleGenerateInvoice = async (orderId) => {
    try {
      const token = localStorage.getItem('token');
      const res = await axios.post(`${API}/orders/${orderId}/create-invoice?invoice_type=e-arsiv`, {}, {
        headers: { Authorization: `Bearer ${token}` }
      });
      if (res.data.success) {
        toast.success(`Fatura oluşturuldu: ${res.data.invoice_number}`);
        fetchOrders();
      } else {
        toast.error(res.data.message || "Fatura oluşturulamadı");
      }
    } catch (err) {
      toast.error(err.response?.data?.detail || "Fatura oluşturulamadı");
    }
  };

  const handlePrintInvoice = async (orderId) => {
    const token = localStorage.getItem('token');
    window.open(`${API}/orders/${orderId}/invoice/print?token=${token}`, '_blank');
  };

  const handleGenerateCargoBarcode = async (orderId, company = selectedCargo) => {
    try {
      const token = localStorage.getItem('token');
      const res = await axios.post(`${API}/orders/${orderId}/cargo-barcode?cargo_company=${company}`, {}, {
        headers: { Authorization: `Bearer ${token}` }
      });
      toast.success(`Kargo barkodu: ${res.data.tracking_number}`);
      fetchOrders();
    } catch (err) {
      toast.error("Kargo barkodu oluşturulamadı");
    }
  };

  const openShipModal = (orderId) => {
    setShipOrderId(orderId);
    setTrackingNumber("");
    setShipModalOpen(true);
  };

  const handleUploadTrendyolInvoice = async (orderNumber) => {
    if (!invoiceLinkInput) {
      toast.error("Lütfen fatura linkini girin");
      return;
    }
    setUploadingInvoice(true);
    try {
      const token = localStorage.getItem('token');
      const res = await axios.post(`${API}/integrations/trendyol/invoices/${orderNumber}`, {
        invoice_link: invoiceLinkInput,
        invoice_number: invoiceNumberInput
      }, {
        headers: { Authorization: `Bearer ${token}` }
      });
      toast.success(res.data.message || "Fatura Trendyol'a yüklendi");
      setInvoiceLinkInput("");
      setInvoiceNumberInput("");
      fetchOrders();
      // Update selected order view without closing modal
      setSelectedOrder(prev => ({
        ...prev,
        invoice_link: invoiceLinkInput,
        invoice_number: invoiceNumberInput
      }));
    } catch (err) {
      toast.error(err.response?.data?.detail || "Fatura yüklenemedi");
    } finally {
      setUploadingInvoice(false);
    }
  };


  const handleShipOrder = async () => {
    if (!trackingNumber.trim()) {
      toast.error("Lütfen takip numarası giriniz");
      return;
    }
    try {
      const token = localStorage.getItem('token');
      const res = await axios.post(
        `${API}/orders/${shipOrderId}/ship?cargo_company=${selectedCargo}&tracking_number=${trackingNumber}`,
        {},
        { headers: { Authorization: `Bearer ${token}` } }
      );
      toast.success(res.data.message || "Sipariş kargoya verildi");
      setShipModalOpen(false);
      fetchOrders();
    } catch (err) {
      toast.error("Kargo işlemi başarısız");
    }
  };

  const handleCreateMngShipment = async (orderId) => {
    try {
      const token = localStorage.getItem('token');
      const res = await axios.post(
        `${API}/orders/${orderId}/create-mng-shipment`,
        {},
        { headers: { Authorization: `Bearer ${token}` } }
      );
      toast.success(`MNG Kargo oluşturuldu: ${res.data.tracking_number}`);
      fetchOrders();
    } catch (err) {
      toast.error("MNG Kargo oluşturulamadı");
    }
  };

  const handlePrintLabel = (orderId) => {
    const labelUrl = `${API}/orders/${orderId}/cargo-label`;
    const printWindow = window.open(labelUrl, '_blank', 'width=400,height=600');
    if (printWindow) {
      printWindow.onload = () => {
        setTimeout(() => {
          printWindow.print();
        }, 500);
      };
    }
  };

  const handleTrendyolPrintLabel = async (cargoTrackingNumber) => {
    try {
      const token = localStorage.getItem('token');
      const res = await axios.get(`${API}/integrations/trendyol/orders/label/${cargoTrackingNumber}`, {
        headers: { Authorization: `Bearer ${token}` },
        responseType: 'blob'
      });
      const url = window.URL.createObjectURL(new Blob([res.data], { type: 'application/pdf' }));
      window.open(url, '_blank');
    } catch (err) {
      toast.error("Trendyol kargo etiketi alınamadı");
    }
  };

  const handleBulkPrintLabels = async () => {
    if (selectedOrders.length === 0) {
      toast.error("Lütfen sipariş seçiniz");
      return;
    }
    try {
      const token = localStorage.getItem('token');
      const res = await axios.post(
        `${API}/orders/bulk-labels`,
        selectedOrders,
        { 
          headers: { Authorization: `Bearer ${token}` },
          responseType: 'text'
        }
      );
      
      // Open in new window for printing
      const printWindow = window.open('', '_blank', 'width=400,height=600');
      if (printWindow) {
        printWindow.document.write(res.data);
        printWindow.document.close();
        setTimeout(() => {
          printWindow.print();
        }, 500);
      }
    } catch (err) {
      toast.error("Etiketler oluşturulamadı");
    }
  };

  const handleSendConfirmationSMS = async (orderId) => {
    try {
      const token = localStorage.getItem('token');
      const res = await axios.post(
        `${API}/orders/${orderId}/send-confirmation-sms`,
        {},
        { headers: { Authorization: `Bearer ${token}` } }
      );
      if (res.data.success) {
        toast.success("Sipariş onay SMS'i gönderildi");
      } else {
        toast.error(res.data.error || "SMS gönderilemedi");
      }
    } catch (err) {
      toast.error("SMS gönderilemedi: " + (err.response?.data?.detail || err.message));
    }
  };

  const handleSendShippingSMS = async (orderId) => {
    try {
      const token = localStorage.getItem('token');
      const res = await axios.post(
        `${API}/orders/${orderId}/send-shipping-sms`,
        {},
        { headers: { Authorization: `Bearer ${token}` } }
      );
      if (res.data.success) {
        toast.success("Kargo SMS'i gönderildi");
      } else {
        toast.error(res.data.error || "SMS gönderilemedi");
      }
    } catch (err) {
      toast.error("SMS gönderilemedi: " + (err.response?.data?.detail || err.message));
    }
  };

  const handleBulkCargoBarcode = async () => {
    if (selectedOrders.length === 0) {
      toast.error("Lütfen sipariş seçiniz");
      return;
    }
    try {
      const token = localStorage.getItem('token');
      const res = await axios.post(`${API}/orders/bulk/cargo-barcode?cargo_company=${selectedCargo}`, 
        selectedOrders, 
        { headers: { Authorization: `Bearer ${token}` } }
      );
      toast.success(`${res.data.success_count} sipariş için kargo barkodu oluşturuldu`);
      setSelectedOrders([]);
      fetchOrders();
    } catch (err) {
      toast.error("Toplu barkod oluşturulamadı");
    }
  };

  const handleBulkStatusChange = async (status) => {
    if (selectedOrders.length === 0) {
      toast.error("Lütfen sipariş seçiniz");
      return;
    }
    try {
      const token = localStorage.getItem('token');
      await axios.post(`${API}/orders/bulk/status?status=${status}`, 
        selectedOrders, 
        { headers: { Authorization: `Bearer ${token}` } }
      );
      toast.success(`${selectedOrders.length} sipariş güncellendi`);
      setSelectedOrders([]);
      fetchOrders();
    } catch (err) {
      toast.error("Toplu güncelleme başarısız");
    }
  };

  const handleTrendyolPreview = async () => {
    setTrendyolPreviewing(true);
    setTrendyolPreviewOrders([]);
    setTrendyolSelectedOrders([]);
    try {
      const token = localStorage.getItem('token');
      const payload = {};
      if (trendyolQueryType === 'order_number') {
        if (!trendyolOrderNumber) {
          toast.error("Lütfen sipariş numarası giriniz.");
          setTrendyolPreviewing(false);
          return;
        }
        payload.order_number = trendyolOrderNumber;
      } else {
        if (!trendyolStartDate || !trendyolEndDate) {
          toast.error("Lütfen tarih aralığı seçiniz.");
          setTrendyolPreviewing(false);
          return;
        }
        payload.start_date_ms = new Date(trendyolStartDate).getTime();
        payload.end_date_ms = new Date(trendyolEndDate).getTime();
      }
      
      const res = await axios.post(`${API}/integrations/trendyol/orders/preview`, payload, {
        headers: { Authorization: `Bearer ${token}` }
      });
      if (res.data.success) {
        setTrendyolPreviewOrders(res.data.orders);
        if (res.data.orders.length === 0) toast.info("Belirtilen kriterlerde sipariş bulunamadı.");
      }
    } catch (err) {
      toast.error(err.response?.data?.detail || "Trendyol siparişleri sorgulanamadı.");
    } finally {
      setTrendyolPreviewing(false);
    }
  };

  const handleTrendyolImportSelected = async () => {
    if (trendyolSelectedOrders.length === 0) {
      toast.error("Lütfen aktarılacak siparişleri seçin.");
      return;
    }
    setTrendyolImporting(true);
    try {
      const token = localStorage.getItem('token');
      const ordersToImport = trendyolPreviewOrders.filter(o => trendyolSelectedOrders.includes(o.orderNumber));
      const res = await axios.post(`${API}/integrations/trendyol/orders/import-selected`, { orders: ordersToImport }, {
        headers: { Authorization: `Bearer ${token}` }
      });
      
      if (res.data.success) {
        toast.success(`${res.data.imported} sipariş aktarıldı, ${res.data.updated} güncellendi.`);
        if (res.data.errors && res.data.errors.length > 0) {
           toast.error(`${res.data.errors.length} sipariş aktarılamadı. Hataları loglardan inceleyin.`);
        }
        setTrendyolModalOpen(false);
        fetchOrders();
      }
    } catch (err) {
      toast.error("Aktarım başarısız oldu.");
    } finally {
      setTrendyolImporting(false);
    }
  };

  const toggleSelectOrder = (orderId) => {
    setSelectedOrders(prev => 
      prev.includes(orderId) 
        ? prev.filter(id => id !== orderId)
        : [...prev, orderId]
    );
  };

  const toggleSelectAll = () => {
    if (selectedOrders.length === orders.length) {
      setSelectedOrders([]);
    } else {
      setSelectedOrders(orders.map(o => o.id));
    }
  };

  const openDetail = (order) => {
    setSelectedOrder(order);
    setDetailOpen(true);
  };

  const formatDate = (dateStr) => {
    return new Date(dateStr).toLocaleDateString('tr-TR', {
      day: '2-digit',
      month: '2-digit',
      year: 'numeric',
      hour: '2-digit',
      minute: '2-digit'
    });
  };

  const getStatusInfo = (status) => {
    return statusOptions.find(s => s.value === status) || statusOptions[0];
  };

  return (
    <div data-testid="admin-orders">
      <div className="flex items-center justify-between mb-6">
        <h1 className="text-2xl font-bold">Siparişler</h1>
        <div className="flex items-center gap-4">
          <button 
            onClick={() => setTrendyolModalOpen(true)}
            className="flex items-center gap-2 px-4 py-2 bg-orange-50 text-orange-600 border border-orange-200 rounded hover:bg-orange-100 text-sm font-medium transition-colors"
            title="Trendyol Sipariş Sorgula ve Aktar"
          >
            <Store size={16} /> <Info size={14} className="opacity-70" /> Trendyol Sipariş Çek
          </button>
          <button 
            onClick={() => setAdvancedFiltersOpen(!advancedFiltersOpen)}
            className={`flex items-center gap-2 px-4 py-2 border rounded hover:bg-gray-50 text-sm ${advancedFiltersOpen ? 'bg-gray-100 border-gray-300' : ''}`}
          >
            <Filter size={16} /> Gelişmiş Filtreler
          </button>
          <select
            value={statusFilter}
            onChange={(e) => { setStatusFilter(e.target.value); setPage(1); }}
            className="border px-3 py-2 rounded text-sm"
          >
            <option value="">Tüm Durumlar</option>
            {statusOptions.map((opt) => (
              <option key={opt.value} value={opt.value}>{opt.label}</option>
            ))}
          </select>
        </div>
      </div>

      {/* Advanced Filters Pane */}
      {advancedFiltersOpen && (
        <div className="bg-white border rounded-lg p-4 mb-6 shadow-sm">
          <div className="grid grid-cols-2 lg:grid-cols-4 xl:grid-cols-5 gap-3">
            <input type="text" placeholder="Genel Arama" className="border px-3 py-1.5 rounded text-sm" value={filters.search} onChange={e => setFilters({...filters, search: e.target.value})} />
            <input type="text" placeholder="Sipariş No" className="border px-3 py-1.5 rounded text-sm" value={filters.order_number} onChange={e => setFilters({...filters, order_number: e.target.value})} />
            <input type="text" placeholder="Telefon" className="border px-3 py-1.5 rounded text-sm" value={filters.phone} onChange={e => setFilters({...filters, phone: e.target.value})} />
            <input type="text" placeholder="E-posta" className="border px-3 py-1.5 rounded text-sm" value={filters.email} onChange={e => setFilters({...filters, email: e.target.value})} />
            <input type="text" placeholder="Kargo Takip No" className="border px-3 py-1.5 rounded text-sm" value={filters.cargo_tracking} onChange={e => setFilters({...filters, cargo_tracking: e.target.value})} />
            <select className="border px-3 py-1.5 rounded text-sm" value={filters.platform} onChange={e => setFilters({...filters, platform: e.target.value})}>
              <option value="">Tüm Platformlar</option>
              <option value="facette">Web (Facette)</option>
              <option value="trendyol">Trendyol</option>
            </select>
            <select className="border px-3 py-1.5 rounded text-sm" value={filters.payment_method} onChange={e => setFilters({...filters, payment_method: e.target.value})}>
              <option value="">Tüm Ödeme Tipleri</option>
              <option value="credit_card">Kredi Kartı</option>
              <option value="bank_transfer">Havale/EFT</option>
              <option value="cash_on_delivery">Kapıda Ödeme</option>
            </select>
            <div className="flex gap-2 items-center text-sm text-gray-500">
              <span className="shrink-0">Tarih:</span>
              <input type="date" title="Başlangıç Tarihi" className="border px-2 py-1.5 rounded flex-1" value={filters.start_date} onChange={e => setFilters({...filters, start_date: e.target.value})} />
              <span>-</span>
              <input type="date" title="Bitiş Tarihi" className="border px-2 py-1.5 rounded flex-1" value={filters.end_date} onChange={e => setFilters({...filters, end_date: e.target.value})} />
            </div>
            <div className="flex gap-2 xl:col-span-2">
              <button onClick={() => { setPage(1); fetchOrders(); }} className="w-1/2 bg-black text-white px-3 py-1.5 rounded text-sm hover:bg-gray-800 flex justify-center items-center gap-1">
                <Search size={14} /> Ara
              </button>
              <button 
                onClick={() => {
                  setFilters({ search: "", phone: "", email: "", order_number: "", cargo_tracking: "", start_date: "", end_date: "", payment_method: "", platform: "" });
                  setPage(1);
                  setTimeout(fetchOrders, 0); // Need to wait for filters to clear before fetching
                }} 
                className="w-1/2 px-3 py-1.5 border hover:border-gray-400 rounded text-sm bg-gray-50 hover:bg-white transition-colors"
                type="button"
              >
                Sıfırla
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Bulk Actions Bar */}
      {selectedOrders.length > 0 && (
        <div className="bg-blue-50 border border-blue-200 rounded-lg p-4 mb-4 flex items-center justify-between">
          <span className="text-sm font-medium">{selectedOrders.length} sipariş seçildi</span>
          <div className="flex items-center gap-3">
            <button 
              onClick={handleBulkPrintLabels}
              className="flex items-center gap-1 px-3 py-1.5 bg-purple-600 text-white text-sm rounded hover:bg-purple-700"
            >
              <Tag size={16} />
              Toplu Etiket Yazdır
            </button>
            <select
              value={selectedCargo}
              onChange={(e) => setSelectedCargo(e.target.value)}
              className="border px-2 py-1 rounded text-sm"
            >
              {cargoCompanies.map(c => (
                <option key={c.value} value={c.value}>{c.label}</option>
              ))}
            </select>
            <button 
              onClick={handleBulkCargoBarcode}
              className="flex items-center gap-1 px-3 py-1.5 bg-green-600 text-white text-sm rounded hover:bg-green-700"
            >
              <Package size={16} />
              Toplu Barkod Oluştur
            </button>
            <select
              onChange={(e) => {
                if (e.target.value) {
                  handleBulkStatusChange(e.target.value);
                  e.target.value = "";
                }
              }}
              className="border px-2 py-1 rounded text-sm"
              defaultValue=""
            >
              <option value="" disabled>Toplu Durum Güncelle</option>
              {statusOptions.map(s => (
                <option key={s.value} value={s.value}>{s.label}</option>
              ))}
            </select>
          </div>
        </div>
      )}

      {/* Stats */}
      <div className="grid grid-cols-2 md:grid-cols-6 gap-4 mb-6">
        <div 
          onClick={() => setStatusFilter("")}
          className={`bg-white p-4 rounded-lg shadow-sm cursor-pointer hover:shadow-md ${!statusFilter ? "ring-2 ring-black" : ""}`}
        >
          <p className="text-2xl font-bold">{total}</p>
          <p className="text-sm text-gray-500">Toplam</p>
        </div>
        {statusOptions.slice(0, 5).map((status) => (
          <div 
            key={status.value}
            onClick={() => setStatusFilter(status.value)}
            className={`bg-white p-4 rounded-lg shadow-sm cursor-pointer hover:shadow-md ${statusFilter === status.value ? "ring-2 ring-black" : ""}`}
          >
            <p className="text-2xl font-bold">
              {orders.filter(o => o.status === status.value).length}
            </p>
            <p className="text-sm text-gray-500">{status.label}</p>
          </div>
        ))}
      </div>

      {/* Orders Table */}
      <div className="bg-white rounded-lg shadow-sm overflow-hidden">
        <table className="admin-table">
          <thead>
            <tr>
              <th className="w-10">
                <button onClick={toggleSelectAll} className="p-1">
                  {selectedOrders.length === orders.length ? (
                    <CheckSquare size={18} />
                  ) : (
                    <Square size={18} />
                  )}
                </button>
              </th>
              <th>Sipariş No</th>
              <th>Müşteri</th>
              <th>Ürünler</th>
              <th>Tutar</th>
              <th>Platform</th>
              <th>Kargo</th>
              <th>Fatura</th>
              <th>Durum</th>
              <th>Tarih</th>
              <th>İşlemler</th>
            </tr>
          </thead>
          <tbody>
            {loading ? (
              <tr>
                <td colSpan={10} className="text-center py-8">Yükleniyor...</td>
              </tr>
            ) : orders.length === 0 ? (
              <tr>
                <td colSpan={10} className="text-center py-8 text-gray-500">Sipariş bulunamadı</td>
              </tr>
            ) : (
              orders.map((order) => {
                const statusInfo = getStatusInfo(order.status);
                return (
                  <tr key={order.id}>
                    <td>
                      <button onClick={() => toggleSelectOrder(order.id)} className="p-1">
                        {selectedOrders.includes(order.id) ? (
                          <CheckSquare size={18} className="text-blue-600" />
                        ) : (
                          <Square size={18} />
                        )}
                      </button>
                    </td>
                    <td className="font-medium">{order.order_number}</td>
                    <td>
                      <div>
                        <p className="font-medium">{order.shipping_address?.first_name} {order.shipping_address?.last_name}</p>
                        <p className="text-xs text-gray-500">{order.shipping_address?.phone}</p>
                      </div>
                    </td>
                    <td>
                      <div className="flex flex-col gap-0.5">
                        {/* Trendyol stores items in 'lines', web orders in 'items' */}
                        {(order.lines?.length > 0 ? order.lines : order.items)?.slice(0, 2).map((item, i) => (
                          <div key={i} className="flex items-center gap-1 text-xs">
                            {item.image && <img src={item.image} alt="" className="w-6 h-6 object-cover bg-gray-100 rounded shrink-0" />}
                            <span className="truncate max-w-[120px]">{item.productName || item.name || 'Ürün'}</span>
                            {item.quantity > 1 && <span className="text-gray-500">x{item.quantity}</span>}
                          </div>
                        ))}
                        {((order.lines?.length > 0 ? order.lines : order.items)?.length || 0) > 2 && (
                          <span className="text-xs text-gray-500">+{(order.lines?.length || order.items?.length || 0) - 2} daha</span>
                        )}
                        {!order.lines?.length && !order.items?.length && (
                          <span className="text-xs text-gray-400">—</span>
                        )}
                      </div>
                    </td>
                    <td>
                      <div className="flex flex-col">
                        <span className="font-medium">{order.total?.toFixed(2)} TL</span>
                        {order.platform === 'trendyol' && order.discount_amount > 0 && (
                          <>
                            <span className="text-xs text-gray-400">{order.subtotal?.toFixed(2)} TL (Liste)</span>
                            <span className="text-xs text-red-500 font-medium">-{order.discount_amount?.toFixed(2)} TL (İskonto)</span>
                          </>
                        )}
                      </div>
                    </td>
                    <td>
                      {order.platform === 'trendyol' ? (
                        <span className="inline-block px-2 py-0.5 bg-[#F27A1A] text-white text-[10px] uppercase font-bold tracking-wider rounded">Trendyol</span>
                      ) : (
                        <span className="inline-block px-2 py-0.5 bg-gray-800 text-white text-[10px] uppercase font-bold tracking-wider rounded">Web</span>
                      )}
                    </td>
                    <td>
                      {order.platform === 'trendyol' ? (
                        order.cargo_tracking_number ? (
                          <div className="text-xs">
                            <p className="font-medium text-orange-600">{order.cargo_provider_name || 'Trendyol Kargo'}</p>
                            <a 
                              href={order.cargo_tracking_link || '#'} 
                              target="_blank" 
                              rel="noopener noreferrer"
                              className="text-blue-600 hover:underline"
                            >
                              {order.cargo_tracking_number}
                            </a>
                            <button 
                              onClick={() => handleTrendyolPrintLabel(order.cargo_tracking_number)}
                              className="ml-2 text-purple-600 hover:text-purple-800"
                              title="Trendyol Etiketi Yazdır"
                            >
                              <Tag size={14} />
                            </button>
                          </div>
                        ) : (
                          <span className="text-xs text-gray-500">Kargo Bekleniyor</span>
                        )
                      ) : order.cargo?.tracking_number ? (
                        <div className="text-xs">
                          <p className="font-medium text-green-600">{order.cargo.company_name || order.cargo.company}</p>
                          <a 
                            href={order.cargo.tracking_url} 
                            target="_blank" 
                            rel="noopener noreferrer"
                            className="text-blue-600 hover:underline"
                          >
                            {order.cargo.tracking_number}
                          </a>
                          <button 
                            onClick={() => handlePrintLabel(order.id)}
                            className="ml-2 text-purple-600 hover:text-purple-800"
                            title="Etiket Yazdır"
                          >
                            <Tag size={14} />
                          </button>
                        </div>
                      ) : (
                        <div className="flex gap-1">
                          <button 
                            onClick={() => handleCreateMngShipment(order.id)}
                            className="text-xs text-green-600 hover:underline flex items-center gap-1"
                            title="MNG ile Gönder"
                          >
                            <Truck size={14} />
                            MNG
                          </button>
                          <button 
                            onClick={() => openShipModal(order.id)}
                            className="text-xs text-blue-600 hover:underline"
                            title="Manuel Giriş"
                          >
                            Manuel
                          </button>
                        </div>
                      )}
                    </td>
                    <td>
                      {order.platform === 'trendyol' && order.invoice_link ? (
                        <div className="text-xs">
                          <a 
                            href={order.invoice_link} 
                            target="_blank" 
                            rel="noopener noreferrer"
                            className="flex items-center gap-1 text-blue-600 hover:underline"
                            title="Trendyol Faturası"
                          >
                            <FileText size={14} />
                            Fatura Gör
                          </a>
                        </div>
                      ) : order.invoice?.invoice_number ? (
                        <div className="text-xs">
                          <p className="text-green-600">{order.invoice.invoice_number}</p>
                        </div>
                      ) : (
                        <button 
                          onClick={() => handleGenerateInvoice(order.id)}
                          className="text-xs text-blue-600 hover:underline flex items-center gap-1"
                        >
                          <FileText size={14} />
                          Fatura Kes
                        </button>
                      )}
                    </td>
                    <td>
                      <Select
                        value={order.status}
                        onValueChange={(value) => handleStatusChange(order.id, value)}
                      >
                        <SelectTrigger className="w-32 h-8 text-xs">
                          <SelectValue>
                            <span className={statusInfo.class}>{statusInfo.label}</span>
                          </SelectValue>
                        </SelectTrigger>
                        <SelectContent>
                          {statusOptions.map((opt) => (
                            <SelectItem key={opt.value} value={opt.value}>{opt.label}</SelectItem>
                          ))}
                        </SelectContent>
                      </Select>
                    </td>
                    <td className="text-sm text-gray-500">{formatDate(order.created_at)}</td>
                    <td>
                      {/* Ticimax benzeri işlem butonları */}
                      <div className="flex items-center gap-0.5">
                        {/* 1. Detay - Ticimax: mavi klasör */}
                        <button
                          onClick={() => openDetail(order)}
                          title="Sipariş Detayı"
                          className="tci-btn tci-btn-blue"
                        >
                          <FolderOpen size={15} />
                        </button>
                        {/* 2. Kargo Durum Yenile */}
                        <button
                          onClick={() => handleCreateMngShipment(order.id)}
                          title="MNG ile Kargoya Ver / Güncelle"
                          className="tci-btn tci-btn-orange"
                        >
                          <RefreshCw size={15} />
                        </button>
                        {/* 3. Fatura Yazdır - gri yazıcı */}
                        <button
                          onClick={() => handlePrintInvoice(order.id)}
                          title="Fatura Yazdır"
                          className="tci-btn tci-btn-gray"
                        >
                          <Printer size={15} />
                        </button>
                        {/* 4. E-Arşiv Fatura Oluştur - yeşil */}
                        <button
                          onClick={() => handleGenerateInvoice(order.id)}
                          title={order.invoice?.invoice_number ? `Fatura: ${order.invoice.invoice_number}` : "E-Arşiv Fatura Oluştur"}
                          className={`tci-btn ${order.invoice?.invoice_number ? 'tci-btn-green-active' : 'tci-btn-green'}`}
                        >
                          <FileText size={15} />
                        </button>
                        {/* 5. Kargo Etiketi - yeşil çift */}
                        {order.platform === 'trendyol' && order.cargo_tracking_number ? (
                          <button
                            onClick={() => handleTrendyolPrintLabel(order.cargo_tracking_number)}
                            title={`Trendyol Etiketi: ${order.cargo_tracking_number}`}
                            className="tci-btn tci-btn-orange"
                          >
                            <Copy size={15} />
                          </button>
                        ) : (
                          <button
                            onClick={() => order.cargo?.tracking_number ? handlePrintLabel(order.id) : openShipModal(order.id)}
                            title={order.cargo?.tracking_number ? `Kargo Etiketi: ${order.cargo.tracking_number}` : "Kargoya Ver / Etiket"}
                            className={`tci-btn ${order.cargo?.tracking_number ? 'tci-btn-green-active' : 'tci-btn-gray'}`}
                          >
                            <Copy size={15} />
                          </button>
                        )}
                        {/* 6. SMS Gönder */}
                        <button
                          onClick={() => order.cargo?.tracking_number ? handleSendShippingSMS(order.id) : handleSendConfirmationSMS(order.id)}
                          title={order.cargo?.tracking_number ? "Kargo SMS Gönder" : "Onay SMS Gönder"}
                          className="tci-btn tci-btn-gray"
                        >
                          <MessageSquare size={15} />
                        </button>
                      </div>
                    </td>
                  </tr>
                );
              })
            )}
          </tbody>
        </table>
      </div>

      {/* Pagination */}
      {total > 20 && (
        <div className="flex justify-center gap-2 mt-4">
          {[...Array(Math.ceil(total / 20))].map((_, i) => (
            <button
              key={i}
              onClick={() => setPage(i + 1)}
              className={`w-8 h-8 rounded ${page === i + 1 ? "bg-black text-white" : "bg-white hover:bg-gray-100"}`}
            >
              {i + 1}
            </button>
          ))}
        </div>
      )}

      {/* Order Detail Modal */}
      <Dialog open={detailOpen} onOpenChange={setDetailOpen}>
        <DialogContent className="max-w-3xl max-h-[90vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle className="flex items-center justify-between">
              <span>Sipariş Detayı - {selectedOrder?.order_number}</span>
            </DialogTitle>
          </DialogHeader>
          
          {selectedOrder && (
            <div className="space-y-6">
              {/* Action Buttons */}
              <div className="flex gap-2 flex-wrap">
                {!selectedOrder.invoice?.invoice_number && (
                  <button 
                    onClick={() => handleGenerateInvoice(selectedOrder.id)}
                    className="flex items-center gap-2 px-4 py-2 bg-blue-600 text-white text-sm rounded hover:bg-blue-700"
                  >
                    <FileText size={16} />
                    Fatura Kes
                  </button>
                )}
                {!selectedOrder.cargo?.tracking_number && !selectedOrder.cargo_tracking_number ? (
                  <>
                    <button 
                      onClick={() => handleCreateMngShipment(selectedOrder.id)}
                      className="flex items-center gap-2 px-4 py-2 bg-green-600 text-white text-sm rounded hover:bg-green-700"
                    >
                      <Truck size={16} />
                      MNG ile Gönder
                    </button>
                    <button 
                      onClick={() => openShipModal(selectedOrder.id)}
                      className="flex items-center gap-2 px-4 py-2 border text-sm rounded hover:bg-gray-50"
                    >
                      <Truck size={16} />
                      Manuel Kargo
                    </button>
                  </>
                ) : (
                  <>
                    {selectedOrder.platform === 'trendyol' && selectedOrder.cargo_tracking_number ? (
                      <button 
                        onClick={() => handleTrendyolPrintLabel(selectedOrder.cargo_tracking_number)}
                        className="flex items-center gap-2 px-4 py-2 bg-orange-600 text-white text-sm rounded hover:bg-orange-700"
                      >
                        <Tag size={16} />
                        Trendyol Etiketi Yazdır
                      </button>
                    ) : (
                      <button 
                        onClick={() => handlePrintLabel(selectedOrder.id)}
                        className="flex items-center gap-2 px-4 py-2 bg-purple-600 text-white text-sm rounded hover:bg-purple-700"
                      >
                        <Tag size={16} />
                        Etiket Yazdır
                      </button>
                    )}
                    <button 
                      onClick={() => handleSendShippingSMS(selectedOrder.id)}
                      className="flex items-center gap-2 px-4 py-2 bg-orange-600 text-white text-sm rounded hover:bg-orange-700"
                    >
                      <MessageSquare size={16} />
                      Kargo SMS
                    </button>
                  </>
                )}
                {!selectedOrder.sms_confirmation_sent && (
                  <button 
                    onClick={() => handleSendConfirmationSMS(selectedOrder.id)}
                    className="flex items-center gap-2 px-4 py-2 bg-teal-600 text-white text-sm rounded hover:bg-teal-700"
                  >
                    <MessageSquare size={16} />
                    Onay SMS
                  </button>
                )}
                <button 
                  onClick={() => window.print()}
                  className="flex items-center gap-2 px-4 py-2 border text-sm rounded hover:bg-gray-50"
                >
                  <Printer size={16} />
                  Yazdır
                </button>
              </div>

              {/* Invoice & Cargo Info */}
              {(selectedOrder.invoice || selectedOrder.cargo || selectedOrder.invoice_link || selectedOrder.platform === 'trendyol') && (
                <div className="grid md:grid-cols-2 gap-4">
                  {(selectedOrder.invoice || selectedOrder.invoice_link) ? (
                    <div className="p-4 bg-green-50 border border-green-200 rounded">
                      <h3 className="font-medium text-green-800 mb-2">Fatura Bilgileri</h3>
                      <p className="text-sm">Fatura No: <span className="font-medium">{selectedOrder.invoice?.invoice_number || selectedOrder.invoice_number}</span></p>
                      {selectedOrder.invoice?.invoice_date && <p className="text-sm text-gray-600">Tarih: {formatDate(selectedOrder.invoice.invoice_date)}</p>}
                      {selectedOrder.invoice_link && (
                        <a href={selectedOrder.invoice_link} target="_blank" rel="noreferrer" className="text-sm text-blue-600 hover:underline mt-2 inline-block">Faturayı Görüntüle</a>
                      )}
                    </div>
                  ) : (
                    selectedOrder.platform === 'trendyol' && (
                      <div className="p-4 border rounded">
                        <h3 className="font-medium mb-2">Trendyol'a Fatura Yükle</h3>
                        <div className="space-y-2">
                          <input
                            type="text"
                            placeholder="Fatura Numarası (Opsiyonel)"
                            className="w-full text-sm border rounded px-2 py-1"
                            value={invoiceNumberInput}
                            onChange={e => setInvoiceNumberInput(e.target.value)}
                          />
                          <input
                            type="url"
                            placeholder="PDF Linki (Zorunlu)"
                            className="w-full text-sm border rounded px-2 py-1"
                            value={invoiceLinkInput}
                            onChange={e => setInvoiceLinkInput(e.target.value)}
                          />
                          <button
                            onClick={() => handleUploadTrendyolInvoice(selectedOrder.order_number)}
                            disabled={uploadingInvoice || !invoiceLinkInput.trim()}
                            className="w-full px-3 py-1.5 bg-orange-600 text-white text-sm rounded hover:bg-orange-700 disabled:opacity-50"
                          >
                            {uploadingInvoice ? "Yükleniyor..." : "Faturayı İlet"}
                          </button>
                        </div>
                      </div>
                    )
                  )}
                  {selectedOrder.cargo && (
                    <div className="p-4 bg-blue-50 border border-blue-200 rounded">
                      <h3 className="font-medium text-blue-800 mb-2">Kargo Bilgileri</h3>
                      <p className="text-sm">Firma: <span className="font-medium">{selectedOrder.cargo.company}</span></p>
                      <p className="text-sm">Takip No: <span className="font-medium">{selectedOrder.cargo.tracking_number}</span></p>
                    </div>
                  )}
                </div>
              )}

              {/* Status */}
              <div className="flex items-center justify-between p-4 bg-gray-50 rounded">
                <div>
                  <p className="text-sm text-gray-500">Durum</p>
                  <span className={getStatusInfo(selectedOrder.status).class}>
                    {getStatusInfo(selectedOrder.status).label}
                  </span>
                </div>
                <Select
                  value={selectedOrder.status}
                  onValueChange={(value) => handleStatusChange(selectedOrder.id, value)}
                >
                  <SelectTrigger className="w-40">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {statusOptions.map((opt) => (
                      <SelectItem key={opt.value} value={opt.value}>{opt.label}</SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>

              {/* Customer Info */}
              <div className="grid md:grid-cols-2 gap-4">
                <div className="p-4 border rounded">
                  <h3 className="font-medium mb-2">Müşteri Bilgileri</h3>
                  <p>{selectedOrder.shipping_address?.first_name} {selectedOrder.shipping_address?.last_name}</p>
                  <p className="text-sm text-gray-500">{selectedOrder.shipping_address?.email}</p>
                  <p className="text-sm text-gray-500">{selectedOrder.shipping_address?.phone}</p>
                </div>
                <div className="p-4 border rounded">
                  <h3 className="font-medium mb-2">Teslimat Adresi</h3>
                  <p className="text-sm">{selectedOrder.shipping_address?.address}</p>
                  <p className="text-sm">{selectedOrder.shipping_address?.district} / {selectedOrder.shipping_address?.city}</p>
                </div>
              </div>

              {/* Items */}
              <div className="border rounded">
                <h3 className="font-medium p-4 border-b">Sipariş Kalemleri</h3>
                <div className="divide-y">
                  {(selectedOrder.lines?.length > 0 ? selectedOrder.lines : selectedOrder.items)?.map((item, i) => (
                    <div key={i} className="flex items-center justify-between p-4">
                      <div className="flex items-center gap-4">
                        {item.image && <img src={item.image} alt="" className="w-16 h-20 object-cover bg-gray-100" />}
                        <div>
                          <p className="font-medium">{item.productName || item.name || "Ürün"}</p>
                          {item.size && <p className="text-sm text-gray-500">Beden: {item.size}</p>}
                          <p className="text-sm text-gray-500">Adet: {item.quantity}</p>
                        </div>
                      </div>
                      <div className="text-right text-sm">
                        {item.unit_price > 0 && typeof item.unit_price !== 'undefined' && (
                          <p className="text-gray-400 line-through text-xs">{item.unit_price.toFixed(2)} TL</p>
                        )}
                        {item.discount_amount > 0 && (
                          <p className="text-orange-500 text-xs">İndirim: -{item.discount_amount.toFixed(2)} TL</p>
                        )}
                        <p className="font-medium">
                          {((item.price || item.amount) * (item.quantity === 1 ? 1 : (item.price ? item.quantity : 1))).toFixed(2)} TL
                        </p>
                      </div>
                    </div>
                  ))}
                </div>
              </div>

              {/* Totals */}
              <div className="p-4 bg-gray-50 rounded space-y-2">
                <div className="flex justify-between text-sm">
                  <span>Ara Toplam</span>
                  <span>{selectedOrder.subtotal?.toFixed(2)} TL</span>
                </div>
                <div className="flex justify-between text-sm">
                  <span>Kargo</span>
                  <span>{selectedOrder.shipping_cost?.toFixed(2)} TL</span>
                </div>
                {selectedOrder.discount > 0 && (
                  <div className="flex justify-between text-sm text-green-600">
                    <span>İndirim</span>
                    <span>-{selectedOrder.discount?.toFixed(2)} TL</span>
                  </div>
                )}
                <div className="flex justify-between font-medium text-lg pt-2 border-t">
                  <span>Toplam</span>
                  <span>{selectedOrder.total?.toFixed(2)} TL</span>
                </div>
              </div>
            </div>
          )}
        </DialogContent>
      </Dialog>

      {/* Ship Order Modal */}
      <Dialog open={shipModalOpen} onOpenChange={setShipModalOpen}>
        <DialogContent className="max-w-md">
          <DialogHeader>
            <DialogTitle>Siparişi Kargoya Ver</DialogTitle>
          </DialogHeader>
          <div className="space-y-4">
            <div>
              <label className="block text-sm font-medium mb-1">Kargo Firması</label>
              <select
                value={selectedCargo}
                onChange={(e) => setSelectedCargo(e.target.value)}
                className="w-full border px-3 py-2 rounded"
              >
                {cargoCompanies.map(c => (
                  <option key={c.value} value={c.value}>{c.label}</option>
                ))}
              </select>
            </div>
            <div>
              <label className="block text-sm font-medium mb-1">Takip Numarası</label>
              <input
                type="text"
                value={trackingNumber}
                onChange={(e) => setTrackingNumber(e.target.value)}
                placeholder="Kargo takip numarasını girin"
                className="w-full border px-3 py-2 rounded"
              />
            </div>
            <div className="flex gap-2 justify-end">
              <button
                onClick={() => setShipModalOpen(false)}
                className="px-4 py-2 border rounded hover:bg-gray-50"
              >
                İptal
              </button>
              <button
                onClick={handleShipOrder}
                className="px-4 py-2 bg-green-600 text-white rounded hover:bg-green-700"
              >
                Kargoya Ver
              </button>
            </div>
          </div>
        </DialogContent>
      </Dialog>

      {/* Trendyol Import Modal */}
      <Dialog open={trendyolModalOpen} onOpenChange={setTrendyolModalOpen}>
        <DialogContent className="max-w-4xl max-h-[90vh] flex flex-col">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2 text-orange-600">
              <Store size={20} /> Trendyol Manuel Sipariş Aktarımı
            </DialogTitle>
          </DialogHeader>
          <div className="flex flex-col gap-4 overflow-hidden h-full mt-4">
            <div className="flex flex-col sm:flex-row gap-4 p-4 border rounded-lg bg-orange-50/30">
              <div className="flex flex-col gap-2 w-full sm:w-1/3">
                <label className="text-sm font-medium">Sorgulama Tipi</label>
                <select 
                  className="border rounded px-3 py-2 text-sm focus:ring-orange-300 outline-none"
                  value={trendyolQueryType}
                  onChange={e => setTrendyolQueryType(e.target.value)}
                >
                  <option value="order_number">Sipariş Numarası İle</option>
                  <option value="date_range">Tarih Aralığı İle</option>
                </select>
              </div>
              
              {trendyolQueryType === 'order_number' ? (
                <div className="flex flex-col gap-2 w-full sm:w-1/2">
                  <label className="text-sm font-medium">Trendyol Sipariş No</label>
                  <input 
                    type="text" 
                    value={trendyolOrderNumber}
                    onChange={e => setTrendyolOrderNumber(e.target.value)}
                    className="border rounded px-3 py-2 text-sm focus:ring-orange-300 outline-none"
                    placeholder="Örn: 921381293"
                  />
                </div>
              ) : (
                <div className="flex flex-col gap-2 w-full sm:w-2/3">
                  <label className="text-sm font-medium">Tarih Aralığı</label>
                  <div className="flex items-center gap-2">
                    <input 
                      type="date" 
                      value={trendyolStartDate}
                      onChange={e => setTrendyolStartDate(e.target.value)}
                      className="border rounded px-3 py-2 text-sm focus:ring-orange-300 outline-none flex-1"
                    />
                    <span>-</span>
                    <input 
                      type="date" 
                      value={trendyolEndDate}
                      onChange={e => setTrendyolEndDate(e.target.value)}
                      className="border rounded px-3 py-2 text-sm focus:ring-orange-300 outline-none flex-1"
                    />
                  </div>
                </div>
              )}
              
              <div className="flex items-end flex-1 sm:w-auto">
                <button 
                  onClick={handleTrendyolPreview}
                  disabled={trendyolPreviewing}
                  className="w-full bg-orange-500 hover:bg-orange-600 text-white px-4 py-2 rounded text-sm font-medium transition-colors disabled:opacity-50 flex items-center justify-center gap-2"
                >
                  {trendyolPreviewing ? "Sorgulanıyor..." : <><Search size={16} /> Sorgula</>}
                </button>
              </div>
            </div>

            {/* Preview Results */}
            <div className="flex-1 overflow-auto border rounded-lg bg-white relative">
              <table className="w-full text-sm text-left relative">
                <thead className="bg-gray-50 text-gray-600 font-medium border-b sticky top-0 z-10 shadow-sm">
                  <tr>
                    <th className="py-3 px-4 w-12 text-center">
                      <input 
                        type="checkbox" 
                        onChange={(e) => {
                          if (e.target.checked) setTrendyolSelectedOrders(trendyolPreviewOrders.map(o => o.orderNumber));
                          else setTrendyolSelectedOrders([]);
                        }}
                        checked={trendyolPreviewOrders.length > 0 && trendyolSelectedOrders.length === trendyolPreviewOrders.length}
                        className="rounded text-orange-600 focus:ring-orange-500"
                      />
                    </th>
                    <th className="py-3 px-4">Sipariş No</th>
                    <th className="py-3 px-4">Tarih</th>
                    <th className="py-3 px-4">Müşteri</th>
                    <th className="py-3 px-4">Tutar</th>
                    <th className="py-3 px-4">Durum</th>
                  </tr>
                </thead>
                <tbody>
                  {trendyolPreviewOrders.length === 0 ? (
                    <tr>
                      <td colSpan={6} className="text-center py-12 text-gray-500">
                        Henüz arama yapılmadı veya sonuç bulunamadı.
                      </td>
                    </tr>
                  ) : (
                    trendyolPreviewOrders.map((o) => (
                      <tr key={o.orderNumber} className="border-b hover:bg-gray-50 transition-colors">
                        <td className="py-2 px-4 text-center">
                          <input 
                            type="checkbox" 
                            checked={trendyolSelectedOrders.includes(o.orderNumber)}
                            onChange={(e) => {
                              if (e.target.checked) setTrendyolSelectedOrders([...trendyolSelectedOrders, o.orderNumber]);
                              else setTrendyolSelectedOrders(trendyolSelectedOrders.filter(id => id !== o.orderNumber));
                            }}
                            className="rounded text-orange-600 focus:ring-orange-500"
                          />
                        </td>
                        <td className="py-2 px-4 font-medium">{o.orderNumber}</td>
                        <td className="py-2 px-4 text-gray-500"> {new Date(o.orderDate).toLocaleString('tr-TR')} </td>
                        <td className="py-2 px-4">{o.shipmentAddress?.firstName} {o.shipmentAddress?.lastName}</td>
                        <td className="py-2 px-4 font-semibold">{o.totalPrice?.toFixed(2)} ₺</td>
                        <td className="py-2 px-4">
                           <span className="px-2 py-1 bg-gray-100 rounded text-xs">{o.status}</span>
                        </td>
                      </tr>
                    ))
                  )}
                </tbody>
              </table>
            </div>

            <div className="flex justify-between items-center bg-gray-50 p-3 rounded-lg border">
              <div className="text-sm font-medium text-gray-600">
                Seçilen: {trendyolSelectedOrders.length} / {trendyolPreviewOrders.length}
              </div>
              <div className="flex gap-2">
                <button 
                  onClick={() => setTrendyolModalOpen(false)}
                  className="px-4 py-2 border rounded hover:bg-gray-100 text-sm transition-colors"
                >
                  İptal
                </button>
                <button 
                  onClick={handleTrendyolImportSelected}
                  disabled={trendyolImporting || trendyolSelectedOrders.length === 0}
                  className="bg-black hover:bg-gray-800 text-white px-4 py-2 rounded text-sm transition-colors disabled:opacity-50"
                >
                  {trendyolImporting ? "Aktarılıyor..." : "Seçili Olanları Aktar"}
                </button>
              </div>
            </div>
          </div>
        </DialogContent>
      </Dialog>
    </div>
  );
}
