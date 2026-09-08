import { act } from "react";
import { createRoot } from "react-dom/client";
import Checkout from "./Checkout";
import axios from "axios";

let mockUser = null;
let mockTotal = 100;
const mockNavigate = jest.fn();
const mockSearch = new URLSearchParams();
const mockCartItems = [{ id: "test", productId: "test", name: "Test Ürün", quantity: 1, price: 100 }];
jest.mock("react-router-dom", () => ({ useNavigate: () => mockNavigate, useSearchParams: () => [mockSearch] }), { virtual: true });
jest.mock("../context/AuthContext", () => ({ useAuth: () => ({ user: mockUser }) }));
jest.mock("../context/CartContext", () => ({ useCart: () => ({ items: mockCartItems, total: mockTotal, clearCart: jest.fn() }) }));
jest.mock("../lib/shipping", () => ({ useShipping: () => ({ shippingFee: 99, freeShippingThreshold: 4000 }) }));
jest.mock("../components/Header", () => () => null);
jest.mock("../components/Footer", () => () => null);
jest.mock("../components/ProvinceDistrictSelect", () => () => null);
jest.mock("../utils/pixelEvents", () => ({ trackInitiateCheckout: jest.fn(), trackPurchase: jest.fn(), trackAddPaymentInfo: jest.fn(), trackAddShippingInfo: jest.fn() }));
jest.mock("../lib/dataLayer", () => ({ collectClickIds: () => ({}) }));
jest.mock("../lib/attribution", () => ({ getSessionId: () => "test-session" }));
jest.mock("sonner", () => ({ toast: { error: jest.fn(), success: jest.fn(), info: jest.fn() } }));
jest.mock("axios", () => ({ get: jest.fn(), post: jest.fn() }));

describe("checkout address isolation", () => {
  let root, container;
  beforeAll(() => { global.IS_REACT_ACT_ENVIRONMENT = true; });
  afterAll(() => { delete global.IS_REACT_ACT_ENVIRONMENT; });
  beforeEach(() => {
    mockUser = null;
    mockTotal = 100;
    localStorage.clear();
    container = document.createElement("div");
    root = createRoot(container);
    axios.get.mockResolvedValue({ data: {} });
    axios.post.mockResolvedValue({ data: { applied: [], eligible: [], discount: 0 } });
  });
  afterEach(async () => { await act(async () => root.unmount()); jest.clearAllMocks(); });

  test("guest checkout deletes the legacy address and never displays it", async () => {
    localStorage.setItem("facette_last_address", JSON.stringify({ first_name: "PRIVATE_PREVIOUS_CUSTOMER", address: "PRIVATE_ADDRESS" }));
    await act(async () => root.render(<Checkout />));
    expect(localStorage.getItem("facette_last_address")).toBeNull();
    expect(container.textContent).not.toContain("PRIVATE_PREVIOUS_CUSTOMER");
    expect(container.textContent).not.toContain("PRIVATE_ADDRESS");
  });

  test.each([[4210.52, false], [4210.53, true]])('rendered checkout includes bank discount at %s boundary', async (total, free) => {
    mockTotal = total;
    axios.post.mockResolvedValue({ data: { applied: [{ code: 'KARGO0', title: 'Ücretsiz Kargo', free_shipping: true, discount: 0 }], total_discount: 0 } });
    await act(async () => root.render(<Checkout />));
    const row = container.querySelector('[data-testid="shipping-cost"]');
    expect(row.textContent.includes('Bedava')).toBe(free);
    expect(row.textContent).toContain('99.00 TL');
    const promos = container.querySelector('[data-testid="applied-promotions"]');
    expect(promos.textContent.includes('Ücretsiz Kargo')).toBe(free);
  });

  test("account switch clears address and ignores the former account's delayed response", async () => {
    let resolveOld;
    mockUser = { id: "old", email: "old@example.test" };
    axios.get.mockImplementation((url) => url.endsWith("/my-addresses")
      ? new Promise((r) => { resolveOld = r; }) : Promise.resolve({ data: {} }));
    await act(async () => root.render(<Checkout />));
    mockUser = { id: "new", email: "new@example.test" };
    axios.get.mockResolvedValue({ data: {} });
    await act(async () => root.render(<Checkout />));
    await act(async () => resolveOld({ data: { addresses: [{ first_name: "PRIVATE_PREVIOUS_CUSTOMER", address: "PRIVATE_ADDRESS" }] } }));
    expect(container.textContent).not.toContain("PRIVATE_PREVIOUS_CUSTOMER");
    expect(container.textContent).not.toContain("PRIVATE_ADDRESS");
    expect(localStorage.getItem("facette_last_address")).toBeNull();
  });
});
