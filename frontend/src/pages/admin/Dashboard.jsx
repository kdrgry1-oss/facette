import { useState, useEffect } from "react";
import { Link } from "react-router-dom";
import { Package, ShoppingCart, Users, TrendingUp, Eye } from "lucide-react";
import axios from "axios";

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;

export default function AdminDashboard() {
  const [stats, setStats] = useState({
    total_orders: 0,
    total_products: 0,
    total_users: 0,
    today_orders: 0,
    total_revenue: 0,
    recent_orders: []
  });
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetchStats();
  }, []);

  const fetchStats = async () => {
    try {
      const res = await axios.get(`${API}/reports/dashboard`);
      setStats(res.data);
    } catch (err) {
      console.error(err);
    } finally {
      setLoading(false);
    }
  };

  const statCards = [
    { icon: ShoppingCart, label: "Toplam Sipariş", value: stats.total_orders, color: "bg-blue-500" },
    { icon: Package, label: "Toplam Ürün", value: stats.total_products, color: "bg-green-500" },
    { icon: Users, label: "Toplam Üye", value: stats.total_users, color: "bg-purple-500" },
    { icon: TrendingUp, label: "Bugün Sipariş", value: stats.today_orders, color: "bg-orange-500" },
  ];

  const formatStatus = (status) => {
    const statusMap = {
      pending: { label: "Bekliyor", class: "status-pending" },
      confirmed: { label: "Onaylandı", class: "status-confirmed" },
      preparing: { label: "Hazırlanıyor", class: "status-preparing" },
      shipped: { label: "Kargoda", class: "status-shipped" },
      delivered: { label: "Teslim Edildi", class: "status-delivered" },
      cancelled: { label: "İptal", class: "status-cancelled" },
    };
    return statusMap[status] || { label: status, class: "" };
  };

  return (
    <div data-testid="admin-dashboard">
      <h1 className="text-2xl font-bold mb-6">Dashboard</h1>

      {/* Stats Cards */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4 mb-8">
        {statCards.map((card, index) => {
          const Icon = card.icon;
          return (
            <div key={index} className="bg-white p-6 rounded-lg shadow-sm">
              <div className="flex items-center gap-4">
                <div className={`w-12 h-12 ${card.color} rounded-lg flex items-center justify-center`}>
                  <Icon size={24} className="text-white" />
                </div>
                <div>
                  <p className="text-2xl font-bold">{loading ? "..." : card.value}</p>
                  <p className="text-sm text-gray-500">{card.label}</p>
                </div>
              </div>
            </div>
          );
        })}
      </div>

      {/* Revenue Card */}
      <div className="bg-white p-6 rounded-lg shadow-sm mb-8">
        <div className="flex items-center justify-between">
          <div>
            <p className="text-sm text-gray-500">Toplam Ciro</p>
            <p className="text-3xl font-bold">{stats.total_revenue.toFixed(2)} TL</p>
          </div>
          <TrendingUp size={48} className="text-green-500" />
        </div>
      </div>

      {/* Recent Orders */}
      <div className="bg-white rounded-lg shadow-sm">
        <div className="p-4 border-b flex items-center justify-between">
          <h2 className="font-semibold">Son Siparişler</h2>
          <Link to="/admin/siparisler" className="text-sm text-blue-600 hover:underline">
            Tümünü Gör
          </Link>
        </div>
        <div className="overflow-x-auto">
          <table className="admin-table">
            <thead>
              <tr>
                <th>Sipariş No</th>
                <th>Müşteri</th>
                <th>Tutar</th>
                <th>Durum</th>
                <th>Tarih</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {stats.recent_orders.length === 0 ? (
                <tr>
                  <td colSpan={6} className="text-center py-8 text-gray-500">
                    Henüz sipariş bulunmuyor
                  </td>
                </tr>
              ) : (
                stats.recent_orders.map((order) => {
                  const status = formatStatus(order.status);
                  return (
                    <tr key={order.id}>
                      <td className="font-medium">{order.order_number}</td>
                      <td>{order.shipping_address?.first_name} {order.shipping_address?.last_name}</td>
                      <td>{order.total.toFixed(2)} TL</td>
                      <td><span className={status.class}>{status.label}</span></td>
                      <td>{new Date(order.created_at).toLocaleDateString('tr-TR')}</td>
                      <td>
                        <Link to={`/admin/siparisler?id=${order.id}`} className="text-blue-600 hover:underline">
                          <Eye size={16} />
                        </Link>
                      </td>
                    </tr>
                  );
                })
              )}
            </tbody>
          </table>
        </div>
      </div>

      {/* Quick Actions */}
      <div className="grid md:grid-cols-3 gap-4 mt-8">
        <Link to="/admin/urunler" className="bg-white p-4 rounded-lg shadow-sm hover:shadow-md transition-shadow text-center">
          <Package size={32} className="mx-auto mb-2 text-gray-400" />
          <p className="font-medium">Ürün Ekle</p>
        </Link>
        <Link to="/admin/bannerlar" className="bg-white p-4 rounded-lg shadow-sm hover:shadow-md transition-shadow text-center">
          <Eye size={32} className="mx-auto mb-2 text-gray-400" />
          <p className="font-medium">Banner Düzenle</p>
        </Link>
        <Link to="/admin/kampanyalar" className="bg-white p-4 rounded-lg shadow-sm hover:shadow-md transition-shadow text-center">
          <TrendingUp size={32} className="mx-auto mb-2 text-gray-400" />
          <p className="font-medium">Kampanya Oluştur</p>
        </Link>
      </div>
    </div>
  );
}
