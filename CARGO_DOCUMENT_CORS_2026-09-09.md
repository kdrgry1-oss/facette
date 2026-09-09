# Cargo document CORS fix

Live read-only preflight reproduced the regression introduced by 7e50926:
`authorization,cache-control` -> 400 Disallowed CORS headers;
`authorization` -> 200. The document helper was adding a request Cache-Control
header that the API explicitly does not permit. Refreshing cannot fix this.

Remove that request header, retaining bearer-header authentication and the API's
existing Cache-Control: no-store/private response policy. Do not broaden CORS or
RBAC. Decode Axios Blob errors so 401/403/404/429/network/server errors remain
actionable. Bulk label and invoice requests report failures, including partial
failures, instead of hiding all errors as “no printable documents”. Open bulk
label popup before requests so a blocked popup cannot increment print counters.

Backend order/payment/stock/carrier state logic is unchanged. A real cargo-label
GET increments print metadata, so no production order label is requested during
the non-mutating test. Browser fixtures use the actual helper with synthetic
documents; live preflights verify allowed request headers without accessing orders.
