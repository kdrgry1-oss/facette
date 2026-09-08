export const GOOGLE_POPUP_TIMEOUT_MS = 25000;

export function safeReturnPath(value, fallback = "/hesabim") {
  if (typeof value !== "string" || !value.startsWith("/") || value.startsWith("//")) {
    return fallback;
  }
  return value;
}

export function isEmbeddedWebView(win = typeof window !== "undefined" ? window : undefined) {
  if (!win) return false;
  const ua = win.navigator?.userAgent || "";
  return Boolean(
    win.ReactNativeWebView ||
    win.webkit?.messageHandlers ||
    /; wv\)|\bwv\b|FBAN|FBAV|Instagram|Line\//i.test(ua)
  );
}

export function googleErrorMessage(code) {
  const messages = {
    csrf: "Google giriş doğrulaması güvenlik kontrolünden geçemedi.",
    inactive: "Bu hesap devre dışı.",
    verification: "Google hesabı doğrulanamadı.",
    configuration: "Google ile giriş henüz yapılandırılmamış.",
    access_denied: "Google ile giriş iptal edildi.",
    popup_failed_to_open: "Google penceresi açılamadı.",
    popup_closed: "Google penceresi tamamlanmadan kapatıldı.",
    timeout: "Google yanıtı zamanında alınamadı.",
    invalid_response: "Google'dan geçerli bir yanıt alınamadı.",
  };
  return messages[code] || "Google ile giriş tamamlanamadı.";
}

// GIS callback yaşam döngüsünü DOM'dan ayırır; popup/credential/error/timeout yolları
// gerçek Google hesabı olmadan deterministik olarak test edilebilir.
export function createGooglePopupFlow({
  exchangeCredential,
  onSuccess,
  onError,
  setTimer = setTimeout,
  clearTimer = clearTimeout,
  timeoutMs = GOOGLE_POPUP_TIMEOUT_MS,
}) {
  let timer = null;
  let settled = false;

  const clear = () => {
    if (timer !== null) clearTimer(timer);
    timer = null;
  };
  const fail = (code, error) => {
    if (settled) return;
    settled = true;
    clear();
    onError(code, error);
  };

  return {
    begin() {
      settled = false;
      clear();
      timer = setTimer(() => fail("timeout"), timeoutMs);
    },
    async credential(response) {
      if (settled) return;
      const credential = response?.credential;
      if (!credential) return fail("invalid_response");
      clear();
      try {
        const result = await exchangeCredential(credential);
        if (!result?.token) return fail("invalid_response");
        if (settled) return;
        settled = true;
        onSuccess(result);
      } catch (error) {
        fail("verification", error);
      }
    },
    popupError(event) {
      const type = event?.type === "popup_failed_to_open" ? event.type : "popup_closed";
      fail(type, event);
    },
    dispose() {
      settled = true;
      clear();
    },
  };
}
