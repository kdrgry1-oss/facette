/**
 * Attribution tracker — runs once per visit on the storefront.
 *
 * What it does:
 * 1. On first load, captures utm_source/medium/campaign/term/content, gclid, fbclid,
 *    referrer and landing page.
 * 2. Persists a server-assigned `facette_sid` in localStorage.
 * 3. Calls POST /api/attribution/track-visit so sessions accumulate touches over time.
 *
 * Usage: import and invoke once at the top of the app root (e.g. in App.js useEffect).
 * The returned session_id is auto-attached to orders via window.__FACETTE_SID__.
 */
import axios from "axios";

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;
const SID_KEY = "facette_sid";
const UTM_KEY = "facette_attr_first";

function readUTM() {
  try {
    const p = new URLSearchParams(window.location.search);
    return {
      utm_source: p.get("utm_source") || "",
      utm_medium: p.get("utm_medium") || "",
      utm_campaign: p.get("utm_campaign") || "",
      utm_term: p.get("utm_term") || "",
      utm_content: p.get("utm_content") || "",
      gclid: p.get("gclid") || "",
      fbclid: p.get("fbclid") || "",
    };
  } catch (_) { return {}; }
}

export async function trackVisit() {
  try {
    if (typeof window === "undefined") return;
    const existingSid = localStorage.getItem(SID_KEY) || null;
    const utm = readUTM();
    const hasNewUtm = !!(utm.utm_source || utm.utm_campaign || utm.gclid || utm.fbclid);
    const payload = {
      ...utm,
      referrer: document.referrer || "",
      landing_page: window.location.pathname + window.location.search,
      session_id: existingSid,
    };
    const { data } = await axios.post(`${API}/attribution/track-visit`, payload, { timeout: 5000 });
    if (data?.session_id) {
      localStorage.setItem(SID_KEY, data.session_id);
      window.__FACETTE_SID__ = data.session_id;
      if (hasNewUtm) {
        // Persist first-touch for debug/display
        localStorage.setItem(UTM_KEY, JSON.stringify({ ...utm, channel: data.channel, ts: new Date().toISOString() }));
      }
    }
  } catch (_) {
    // Silent – never break storefront over attribution.
  }
}

export function getSessionId() {
  try { return window.__FACETTE_SID__ || localStorage.getItem(SID_KEY) || null; }
  catch (_) { return null; }
}
