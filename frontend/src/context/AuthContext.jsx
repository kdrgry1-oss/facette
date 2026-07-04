import { createContext, useContext, useState, useEffect } from "react";
import axios from "axios";

const AuthContext = createContext();
const API = `${process.env.REACT_APP_BACKEND_URL}/api`;

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null);
  const [token, setToken] = useState(() => localStorage.getItem("token"));
  const [loading, setLoading] = useState(() => Boolean(localStorage.getItem("token")));

  useEffect(() => {
    if (token) {
      axios.defaults.headers.common["Authorization"] = `Bearer ${token}`;
      fetchUser();
    }
  }, [token]);

  const fetchUser = async () => {
    try {
      const res = await axios.get(`${API}/auth/me`);
      setUser(res.data);
    } catch (err) {
      logout();
    } finally {
      setLoading(false);
    }
  };

  const login = async (email, password) => {
    // O19: Şifreyi URL query yerine istek GÖVDESİNDE gönder (log/geçmiş/Referer sızıntısı olmasın).
    const res = await axios.post(`${API}/auth/login`, { email, password });
    if (res.data?.mfa_required) {
      return { mfaRequired: true, mfaToken: res.data.mfa_token };
    }
    const { token: newToken, user: userData } = res.data;
    localStorage.setItem("token", newToken);
    axios.defaults.headers.common["Authorization"] = `Bearer ${newToken}`;
    setToken(newToken);
    setUser(userData);
    return userData;
  };

  // Sosyal giriş (Google) sonrası: backend'den dönen JWT token + user'ı tam olarak yerleştir.
  // localStorage + axios Authorization header + context state hepsi senkron olmalı.
  const loginWithToken = (newToken, userData) => {
    localStorage.setItem("token", newToken);
    axios.defaults.headers.common["Authorization"] = `Bearer ${newToken}`;
    setToken(newToken);
    setUser(userData);
  };

  const verifyMfa = async (mfaToken, code) => {
    const res = await axios.post(`${API}/auth/mfa/verify`, { mfa_token: mfaToken, code });
    const { token: newToken, user: userData } = res.data;
    localStorage.setItem("token", newToken);
    axios.defaults.headers.common["Authorization"] = `Bearer ${newToken}`;
    setToken(newToken);
    setUser(userData);
    return userData;
  };

  const register = async (data) => {
    // O19: Kimlik bilgilerini gövdede gönder (şifre query'de sızmasın).
    const res = await axios.post(`${API}/auth/register`, {
      email: data.email || "",
      password: data.password || "",
      first_name: data.first_name || "",
      last_name: data.last_name || "",
      phone: data.phone || "",
    });
    const { token: newToken, user: userData } = res.data;
    localStorage.setItem("token", newToken);
    axios.defaults.headers.common["Authorization"] = `Bearer ${newToken}`;
    setToken(newToken);
    setUser(userData);
    return userData;
  };

  const logout = () => {
    localStorage.removeItem("token");
    delete axios.defaults.headers.common["Authorization"];
    setToken(null);
    setUser(null);
  };

  return (
    <AuthContext.Provider
      value={{
        user,
        setUser,
        token,
        loading,
        isAdmin: user?.is_admin || false,
        login,
        loginWithToken,
        verifyMfa,
        register,
        logout,
      }}
    >
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  return useContext(AuthContext);
}
