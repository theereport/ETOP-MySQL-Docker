const DEFAULT_API_BASE = "http://127.0.0.1:8000/api/v1";

export const API_BASE = import.meta.env.VITE_API_BASE_URL?.replace(/\/$/, "") ?? DEFAULT_API_BASE;

export class ApiError extends Error {
  status: number;
  details?: unknown;
  constructor(message: string, status: number, details?: unknown) {
    super(message); this.name = "ApiError"; this.status = status; this.details = details;
  }
}

type RequestOptions = Omit<RequestInit, "body"> & { body?: unknown };

export async function requestJson<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const url = path.startsWith("http") ? path : `${API_BASE}${path.startsWith("/") ? path : `/${path}`}`;
  const headers = new Headers(options.headers);
  headers.set("Accept", "application/json");
  let body: BodyInit | undefined;
  if (options.body !== undefined) { headers.set("Content-Type", "application/json"); body = JSON.stringify(options.body); }
  const response = await fetch(url, { ...options, headers, body });
  if (!response.ok) {
    let message = `Request failed with status ${response.status}.`; let details: unknown;
    try { details = await response.json(); if (details && typeof details === "object" && "detail" in details && typeof (details as {detail?:unknown}).detail === "string") message = (details as {detail:string}).detail; } catch {}
    throw new ApiError(message, response.status, details);
  }
  if (response.status === 204) return undefined as T;
  return (await response.json()) as T;
}
