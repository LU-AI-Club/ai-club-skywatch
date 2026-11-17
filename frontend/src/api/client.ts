import { config } from "../config";

export type QueryParams = Record<string, string | number | undefined | null>;

// The one place the app builds a request to the API. Empty/undefined params are
// dropped so callers can pass optional filters without guarding each one.
export async function fetchJSON<T>(
  path: string,
  params?: QueryParams,
  signal?: AbortSignal,
): Promise<T> {
  const url = new URL(path, config.apiBaseUrl);
  if (params) {
    for (const [key, value] of Object.entries(params)) {
      if (value !== undefined && value !== null && value !== "") {
        url.searchParams.set(key, String(value));
      }
    }
  }
  const response = await fetch(url.toString(), {
    headers: { Accept: "application/json, application/geo+json" },
    signal,
  });
  if (!response.ok) {
    throw new Error(`API returned ${response.status} for ${path}`);
  }
  return (await response.json()) as T;
}
