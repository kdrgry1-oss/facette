import {
  createGooglePopupFlow,
  googleErrorMessage,
  isEmbeddedWebView,
  safeReturnPath,
} from "./googleAuthFlow";

describe("Google auth flow", () => {
  test("accepts only local return paths", () => {
    expect(safeReturnPath("/urun/1?x=1")).toBe("/urun/1?x=1");
    expect(safeReturnPath("https://evil.example")).toBe("/hesabim");
    expect(safeReturnPath("//evil.example")).toBe("/hesabim");
  });

  test("exchanges popup credential and completes once", async () => {
    const exchange = jest.fn().mockResolvedValue({ token: "app-token", user: { id: "u1" } });
    const success = jest.fn();
    const error = jest.fn();
    const flow = createGooglePopupFlow({ exchangeCredential: exchange, onSuccess: success, onError: error });
    flow.begin();
    await flow.credential({ credential: "google-test-double" });
    await flow.credential({ credential: "duplicate" });
    expect(exchange).toHaveBeenCalledTimes(1);
    expect(success).toHaveBeenCalledWith({ token: "app-token", user: { id: "u1" } });
    expect(error).not.toHaveBeenCalled();
  });

  test("surfaces popup errors without exchanging a credential", () => {
    const exchange = jest.fn();
    const error = jest.fn();
    const flow = createGooglePopupFlow({ exchangeCredential: exchange, onSuccess: jest.fn(), onError: error });
    flow.begin();
    flow.popupError({ type: "popup_failed_to_open" });
    expect(exchange).not.toHaveBeenCalled();
    expect(error).toHaveBeenCalledWith("popup_failed_to_open", expect.anything());
  });

  test("times out a popup that never calls back", () => {
    jest.useFakeTimers();
    const error = jest.fn();
    const flow = createGooglePopupFlow({ exchangeCredential: jest.fn(), onSuccess: jest.fn(), onError: error, timeoutMs: 50 });
    flow.begin();
    jest.advanceTimersByTime(50);
    expect(error).toHaveBeenCalledWith("timeout", undefined);
    jest.useRealTimers();
  });

  test("detects embedded webviews and maps callback errors", () => {
    expect(isEmbeddedWebView({ navigator: { userAgent: "Instagram 300" } })).toBe(true);
    expect(isEmbeddedWebView({ navigator: { userAgent: "Chrome" } })).toBe(false);
    expect(googleErrorMessage("csrf")).toMatch(/güvenlik/);
  });
});
