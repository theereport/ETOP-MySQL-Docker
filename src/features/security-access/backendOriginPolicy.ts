const DEFAULT_BACKEND_ORIGINS = [
  'http://127.0.0.1:8000',
  'http://localhost:8000',
]
const DEFAULT_BACKEND_ORIGIN_SET = new Set(DEFAULT_BACKEND_ORIGINS)

export function configuredBackendOrigins(
  configuredBaseUrl: string | undefined,
  locationOrigin: string,
): Set<string> {
  if (configuredBaseUrl) {
    try {
      return new Set([new URL(configuredBaseUrl, locationOrigin).origin])
    } catch {
      return new Set()
    }
  }
  return new Set(DEFAULT_BACKEND_ORIGINS)
}

export function shouldAttachETOPSession(
  requestUrl: string,
  allowedOrigins: ReadonlySet<string>,
  locationOrigin: string,
): boolean {
  try {
    return allowedOrigins.has(new URL(requestUrl, locationOrigin).origin)
  } catch {
    return false
  }
}

export function rewriteLegacyETOPRequestUrl(
  requestUrl: string,
  configuredBaseUrl: string | undefined,
  locationOrigin: string,
): string {
  if (!configuredBaseUrl) return requestUrl
  try {
    const requested = new URL(requestUrl, locationOrigin)
    if (!DEFAULT_BACKEND_ORIGIN_SET.has(requested.origin)) return requestUrl
    const configured = new URL(configuredBaseUrl, locationOrigin)
    requested.protocol = configured.protocol
    requested.host = configured.host
    return requested.toString()
  } catch {
    return requestUrl
  }
}
