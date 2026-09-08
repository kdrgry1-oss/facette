import axios from "axios";
import { fetchAdminDocument, openAdminDocument } from "./adminDocuments";

jest.mock("axios", () => ({ get: jest.fn() }));

beforeEach(() => { localStorage.setItem("token", "test-session"); });
afterEach(() => { jest.restoreAllMocks(); jest.clearAllMocks(); localStorage.clear(); jest.useRealTimers(); });

test("credentials travel in the header, never in the document URL", async () => {
  const blob = new Blob(["test invoice"], { type: "text/html" });
  axios.get.mockResolvedValue({ data: blob });
  expect(await fetchAdminDocument("/orders/test/invoice/print")).toBe(blob);
  const [url, options] = axios.get.mock.calls[0];
  expect(url).not.toContain("test-session");
  expect(url).not.toContain("token=");
  expect(options.headers.Authorization).toBe("Bearer test-session");
  expect(options.responseType).toBe("blob");
});

test.each(["https://other.test/file", "//other.test/file", "/\\other.test", "/file?token=secret"])(
  "rejects unsafe path %s before sending credentials", async (path) => {
    await expect(fetchAdminDocument(path)).rejects.toThrow();
    expect(axios.get).not.toHaveBeenCalled();
  });

test("requires a current session", async () => {
  localStorage.removeItem("token");
  await expect(fetchAdminDocument("/orders/test/invoice/print")).rejects.toThrow();
  expect(axios.get).not.toHaveBeenCalled();
});

test("a blocked popup does not make a label-printing request", async () => {
  jest.spyOn(window, "open").mockReturnValue(null);
  await expect(openAdminDocument("/orders/test/cargo-label")).rejects.toThrow("engellendi");
  expect(axios.get).not.toHaveBeenCalled();
});

test("request failure closes the blank popup", async () => {
  const popup = { opener: {}, close: jest.fn() };
  jest.spyOn(window, "open").mockReturnValue(popup);
  axios.get.mockRejectedValue(new Error("Forbidden"));
  await expect(openAdminDocument("/orders/test/cargo-label")).rejects.toThrow("Forbidden");
  expect(popup.opener).toBeNull();
  expect(popup.close).toHaveBeenCalled();
});
