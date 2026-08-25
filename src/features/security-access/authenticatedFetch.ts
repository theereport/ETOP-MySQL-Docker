import {
  clearWorkflowToken,
  getWorkflowToken,
} from '../workflow-foundation/api'
import {
  configuredBackendOrigins,
  rewriteLegacyETOPRequestUrl,
  shouldAttachETOPSession,
} from './backendOriginPolicy'

let installed = false

export function installAuthenticatedFetch(): void {
  if (installed) return
  installed = true

  const nativeFetch = window.fetch.bind(window)
  const locationOrigin = window.location.origin
  const configuredBaseUrl = import.meta.env.VITE_API_BASE_URL
  const allowedOrigins = configuredBackendOrigins(
    configuredBaseUrl,
    locationOrigin,
  )

  window.fetch = async (
    input: RequestInfo | URL,
    init?: RequestInit,
  ): Promise<Response> => {
    const originalUrl = input instanceof Request ? input.url : String(input)
    const requestUrl = rewriteLegacyETOPRequestUrl(
      originalUrl,
      configuredBaseUrl,
      locationOrigin,
    )
    const requestInput: RequestInfo | URL = requestUrl === originalUrl
      ? input
      : input instanceof Request
        ? new Request(requestUrl, input)
        : requestUrl
    if (!shouldAttachETOPSession(requestUrl, allowedOrigins, locationOrigin)) {
      return nativeFetch(requestInput, init)
    }

    const headers = new Headers(input instanceof Request ? input.headers : undefined)
    if (init?.headers) {
      new Headers(init.headers).forEach((value, name) => headers.set(name, value))
    }
    const token = getWorkflowToken()
    if (token && !headers.has('Authorization')) {
      headers.set('Authorization', `Bearer ${token}`)
    }
    const response = await nativeFetch(requestInput, {
      ...init,
      headers,
      credentials: init?.credentials ?? 'include',
    })
    if (token && response.status === 401) {
      clearWorkflowToken()
    }
    return response
  }
}
