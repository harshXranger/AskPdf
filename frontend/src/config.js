const fallbackApiBaseUrl = "http://127.0.0.1:5000";

export const API_BASE_URL =
  (import.meta.env.VITE_API_BASE_URL || fallbackApiBaseUrl).replace(/\/$/, "");

export const apiUrl = (path) =>
  `${API_BASE_URL}${path.startsWith("/") ? path : `/${path}`}`;
