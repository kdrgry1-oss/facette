import { useState, useEffect } from "react";
import { Eye, Truck, FileText, Package, CheckSquare, Square, Printer } from "lucide-react";
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
];

export default function AdminOrders() {
  const [orders, setOrders] = useState([]);
  const [loading, setLoading] = useState(true);
  const [page, setPage] = useState(1);
  const [total, setTotal] = useState(0);
  const [statusFilter, setStatusFilter] = useState("");
  const [selectedOrder, setSelectedOrder] = useState(null);
  const [detailOpen, setDetailOpen] = useState(false);
  const [selectedOrders, setSelectedOrders] = useState([]);
  const [bulkAction, setBulkAction] = useState("");
  const [selectedCargo, setSelectedCargo] = useState("MNG");

  useEffect(() => {
    fetchOrders();
  }, [page, statusFilter]);

  const fetchOrders = async () => {
    setLoading(true);
    try {
      const token = localStorage.getItem('token');
      let url = `${API}/orders?page=${page}&limit=20`;
      if (statusFilter) url += `&status=${statusFilter}`;
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
      const res = await axios.post(`${API}/orders/${orderId}/invoice`, {}, {
        headers: { Authorization: `Bearer ${token}` }
      });
      toast.success(`Fatura oluşturuldu: ${res.data.invoice_number}`);
      fetchOrders();
    } catch (err) {
      toast.error("Fatura oluşturulamadı");
    }
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
          <select
            value={statusFilter}
            onChange={(e) => setStatusFilter(e.target.value)}
            className="border px-3 py-2 rounded text-sm"
          >
            <option value="">Tüm Durumlar</option>
            {statusOptions.map((opt) => (
              <option key={opt.value} value={opt.value}>{opt.label}</option>
            ))}
          </select>
        </div>
      </div>

      {/* Bulk Actions Bar */}
      {selectedOrders.length > 0 && (
        <div className="bg-blue-50 border border-blue-200 rounded-lg p-4 mb-4 flex items-center justify-between">
          <span className="text-sm font-medium">{selectedOrders.length} sipariş seçildi</span>
          <div className="flex items-center gap-3">
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
                      <div className="flex -space-x-2">
                        {order.items?.slice(0, 3).map((item, i) => (
                          <img key={i} src={item.image} alt="" className="w-8 h-10 object-cover border-2 border-white bg-gray-100" />
                        ))}
                        {order.items?.length > 3 && (
                          <span className="w-8 h-10 bg-gray-200 flex items-center justify-center text-xs">+{order.items.length - 3}</span>
                        )}
                      </div>
                    </td>
                    <td className="font-medium">{order.total?.toFixed(2)} TL</td>
                    <td>
                      {order.cargo?.tracking_number ? (
                        <div className="text-xs">
                          <p className="font-medium text-green-600">{order.cargo.company}</p>
                          <p className="text-gray-500">{order.cargo.tracking_number}</p>
                        </div>
                      ) : (
                        <button 
                          onClick={() => handleGenerateCargoBarcode(order.id)}
                          className="text-xs text-blue-600 hover:underline flex items-center gap-1"
                        >
                          <Truck size={14} />
                          Barkod Oluştur
                        </button>
                      )}
                    </td>
                    <td>
                      {order.invoice?.invoice_number ? (
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
                      <button 
                        onClick={() => openDetail(order)}
                        className="p-1 hover:bg-gray-100 rounded text-blue-600"
                        title="Detayları Gör"
                      >
                        <Eye size={18} />
                      </button>
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
                {!selectedOrder.cargo?.tracking_number && (
                  <button 
                    onClick={() => handleGenerateCargoBarcode(selectedOrder.id)}
                    className="flex items-center gap-2 px-4 py-2 bg-green-600 text-white text-sm rounded hover:bg-green-700"
                  >
                    <Truck size={16} />
                    Kargo Barkodu Oluştur
                  </button>
                )}
                <button className="flex items-center gap-2 px-4 py-2 border text-sm rounded hover:bg-gray-50">
                  <Printer size={16} />
                  Yazdır
                </button>
              </div>

              {/* Invoice & Cargo Info */}
              {(selectedOrder.invoice || selectedOrder.cargo) && (
                <div className="grid md:grid-cols-2 gap-4">
                  {selectedOrder.invoice && (
                    <div className="p-4 bg-green-50 border border-green-200 rounded">
                      <h3 className="font-medium text-green-800 mb-2">Fatura Bilgileri</h3>
                      <p className="text-sm">Fatura No: <span className="font-medium">{selectedOrder.invoice.invoice_number}</span></p>
                      <p className="text-sm text-gray-600">Tarih: {formatDate(selectedOrder.invoice.invoice_date)}</p>
                    </div>
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
                  {selectedOrder.items?.map((item, i) => (
                    <div key={i} className="flex items-center gap-4 p-4">
                      <img src={item.image} alt="" className="w-16 h-20 object-cover bg-gray-100" />
                      <div className="flex-1">
                        <p className="font-medium">{item.name}</p>
                        {item.size && <p className="text-sm text-gray-500">Beden: {item.size}</p>}
                        <p className="text-sm text-gray-500">Adet: {item.quantity}</p>
                      </div>
                      <p className="font-medium">{(item.price * item.quantity).toFixed(2)} TL</p>
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
    </div>
  );
}
