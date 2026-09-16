const API_BASE = process.env.NEXT_PUBLIC_HAZE_API_BASE_URL ?? "http://localhost:8000/api/v1";

export class ApiError extends Error {
  constructor(
    message: string,
    public readonly status: number,
  ) {
    super(message);
  }
}

async function parseResponse<T>(response: Response): Promise<T> {
  if (!response.ok) {
    const body = await response.text();
    throw new ApiError(body || response.statusText, response.status);
  }

  return response.json() as Promise<T>;
}

export type QueryValue = string | number | boolean | null | undefined;

function buildUrl(path: string, query?: Record<string, QueryValue>) {
  if (!query) return `${API_BASE}${path}`;

  const params = new URLSearchParams();
  for (const [key, value] of Object.entries(query)) {
    if (value === null || value === undefined || value === "") continue;
    params.set(key, String(value));
  }

  const search = params.toString();
  return search ? `${API_BASE}${path}?${search}` : `${API_BASE}${path}`;
}

/**
 * `query` carries `at` for the endpoints that accept it. Not every read does:
 * /institutions, /health, /model/metrics and /scenarios have no `at` parameter
 * in openapi.json, so callers must not pass one to those.
 */
export async function apiGet<T>(path: string, query?: Record<string, QueryValue>): Promise<T> {
  const response = await fetch(buildUrl(path, query), {
    method: "GET",
    cache: "no-store",
    headers: { Accept: "application/json" },
  });

  return parseResponse<T>(response);
}
