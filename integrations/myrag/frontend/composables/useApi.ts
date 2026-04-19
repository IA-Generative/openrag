/**
 * MyRAG API composable — centralized API calls.
 */
export function useApi() {
  const config = useRuntimeConfig()
  const baseUrl = config.public.myragApiUrl

  async function get<T = any>(path: string, params?: Record<string, string>): Promise<T> {
    const url = new URL(`${baseUrl}${path}`)
    if (params) {
      Object.entries(params).forEach(([k, v]) => url.searchParams.set(k, v))
    }
    const resp = await fetch(url.toString())
    if (!resp.ok) throw new Error(`API error ${resp.status}: ${await resp.text()}`)
    return resp.json()
  }

  async function post<T = any>(path: string, body?: any): Promise<T> {
    const resp = await fetch(`${baseUrl}${path}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: body ? JSON.stringify(body) : undefined,
    })
    if (!resp.ok) throw new Error(`API error ${resp.status}: ${await resp.text()}`)
    return resp.json()
  }

  async function patch<T = any>(path: string, body?: any): Promise<T> {
    const resp = await fetch(`${baseUrl}${path}`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: body ? JSON.stringify(body) : undefined,
    })
    if (!resp.ok) throw new Error(`API error ${resp.status}: ${await resp.text()}`)
    return resp.json()
  }

  async function uploadFile(path: string, file: File, fields?: Record<string, string>) {
    const form = new FormData()
    form.append('file', file)
    if (fields) {
      Object.entries(fields).forEach(([k, v]) => form.append(k, v))
    }
    const resp = await fetch(`${baseUrl}${path}`, { method: 'POST', body: form })
    if (!resp.ok) throw new Error(`Upload error ${resp.status}: ${await resp.text()}`)
    return resp.json()
  }

  return { get, post, patch, uploadFile, baseUrl }
}
