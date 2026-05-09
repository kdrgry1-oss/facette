/**
 * native.js — Capacitor native bridge stub
 *
 * Capacitor paketleri yüklü değilse (web build), tüm fonksiyonlar no-op
 * davranır. Kullanıcı `yarn add @capacitor/core @capacitor/ios
 * @capacitor/android @capacitor/push-notifications @capacitor/app
 * @capacitor/preferences` çalıştırdığında otomatik aktive olur.
 *
 * Detaylı kurulum: /app/CAPACITOR_DEPLOYMENT_GUIDE.md
 */
import axios from "axios";

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;

// Lazy / safe imports — paketler yüklü değilse undefined dönecek
let Capacitor, PushNotifications, App, Preferences;
try {
  // eslint-disable-next-line global-require
  Capacitor = require("@capacitor/core").Capacitor;
  PushNotifications = require("@capacitor/push-notifications").PushNotifications;
  App = require("@capacitor/app").App;
  Preferences = require("@capacitor/preferences").Preferences;
} catch (e) {
  // Web build — Capacitor henüz kurulmamış. Tüm fonksiyonlar no-op olacak.
}

export const isNative = !!(Capacitor && Capacitor.isNativePlatform && Capacitor.isNativePlatform());
export const platform = Capacitor ? Capacitor.getPlatform() : "web"; // ios | android | web

/* -------------------------------------------------------------------------- */
/*  PUSH NOTIFICATIONS — FCM (Android) + APNs (iOS)                            */
/* -------------------------------------------------------------------------- */
export async function setupPushNotifications() {
  if (!isNative || !PushNotifications) return;

  let perm = await PushNotifications.checkPermissions();
  if (perm.receive === "prompt") {
    perm = await PushNotifications.requestPermissions();
  }
  if (perm.receive !== "granted") return;

  await PushNotifications.register();

  PushNotifications.addListener("registration", async (token) => {
    const userToken = localStorage.getItem("token");
    if (!userToken) return;

    let deviceId = (await Preferences.get({ key: "device_id" })).value;
    if (!deviceId) {
      deviceId = `${platform}-${Date.now()}-${Math.random().toString(36).substr(2, 9)}`;
      await Preferences.set({ key: "device_id", value: deviceId });
    }

    try {
      await axios.post(
        `${API}/app/devices/register`,
        {
          platform,
          device_id: deviceId,
          push_token: token.value,
          app_version: "1.0.0",
        },
        { headers: { Authorization: `Bearer ${userToken}` } }
      );
    } catch (e) {
      console.warn("Device register failed:", e);
    }
  });

  PushNotifications.addListener("pushNotificationActionPerformed", (action) => {
    const data = action.notification.data || {};
    if (data.deep_link) {
      const path = String(data.deep_link).replace("facette://", "/");
      window.location.href = path;
    }
  });
}

/* -------------------------------------------------------------------------- */
/*  VERSION CHECK — force update                                              */
/* -------------------------------------------------------------------------- */
export async function checkAppVersion() {
  if (!isNative || !App) return null;
  const info = await App.getInfo();
  try {
    const res = await axios.get(
      `${API}/app/version-check?platform=${platform}&current_version=${info.version}`
    );
    return res.data;
  } catch {
    return null;
  }
}

/* -------------------------------------------------------------------------- */
/*  DEEP LINKS — facette://order/123                                          */
/* -------------------------------------------------------------------------- */
export function setupDeepLinks() {
  if (!isNative || !App) return;
  App.addListener("appUrlOpen", (event) => {
    const url = String(event.url || "").replace("facette://", "/");
    if (url) window.location.href = url;
  });
}

/* -------------------------------------------------------------------------- */
/*  BOOTSTRAP — App.js'den çağrılır                                            */
/* -------------------------------------------------------------------------- */
export async function bootstrapNative() {
  if (!isNative) return { isNative: false };

  setupDeepLinks();
  await setupPushNotifications();
  const versionInfo = await checkAppVersion();

  if (versionInfo?.force_update_required && versionInfo.store_url) {
    // Native blocking alert + redirect
    if (
      window.confirm(
        `Uygulamanın yeni sürümü gerekli (mevcut ${versionInfo.current_version} → ${versionInfo.latest_version}).
Mağazaya yönlendirilmek ister misiniz?`
      )
    ) {
      window.location.href = versionInfo.store_url;
    }
  }

  return { isNative: true, platform, versionInfo };
}
