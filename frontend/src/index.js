// build: 2026-07-15b — bundle hash'ini değiştirip zehirlenmiş edge cache URL'ini atlatır
import React from "react";
import ReactDOM from "react-dom/client";
import "@/index.css";
import App from "@/App";

const root = ReactDOM.createRoot(document.getElementById("root"));
root.render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
);
