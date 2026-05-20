export class ApiError extends Error {
  readonly status: number
  readonly detail: string

  constructor(status: number, detail: string) {
    super(detail)
    this.name = 'ApiError'
    this.status = status
    this.detail = detail
  }
}

type RequestJsonOptions = {
  method?: string
  body?: unknown
}

function parseErrorDetail(payload: unknown): string {
  if (payload && typeof payload === 'object' && 'detail' in payload) {
    const detail = (payload as { detail?: unknown }).detail
    if (typeof detail === 'string') {
      return detail
    }
  }
  return 'request_failed'
}

export async function requestJson<T>(
  path: string,
  options: RequestJsonOptions = {},
): Promise<T> {
  const headers: HeadersInit = {
    Accept: 'application/json',
  }
  const init: RequestInit = {
    method: options.method ?? 'GET',
    headers,
    credentials: 'include',
  }

  if (options.body !== undefined) {
    headers['Content-Type'] = 'application/json'
    init.body = JSON.stringify(options.body)
  }

  const response = await fetch(path, {
    ...init,
  })
  const text = await response.text()
  const payload = text ? (JSON.parse(text) as unknown) : undefined

  if (!response.ok) {
    throw new ApiError(response.status, parseErrorDetail(payload))
  }

  return payload as T
}
