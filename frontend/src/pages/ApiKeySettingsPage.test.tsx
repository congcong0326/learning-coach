import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { ApiKeySettingsPage } from './ApiKeySettingsPage'

const savedCredential = {
  id: 7,
  provider: 'openai',
  display_name: '个人 OpenAI key',
  base_url: 'https://api.openai.com/v1',
  api_mode: 'responses',
  model_name: 'gpt-4.1-mini',
  api_key_mask: 'sk-...abcd',
  is_default: true,
  is_enabled: true,
  is_preferred: true,
  is_active: true,
  failure_count: 0,
  status: 'valid',
  last_used_at: null,
  last_tested_at: null,
  last_error: '',
}

function renderPage() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  })
  return render(
    <QueryClientProvider client={client}>
      <ApiKeySettingsPage />
    </QueryClientProvider>,
  )
}

function okJson(payload: unknown) {
  return new Response(JSON.stringify(payload), {
    status: 200,
    headers: { 'Content-Type': 'application/json' },
  })
}

describe('ApiKeySettingsPage', () => {
  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('renders api assets as a table with routing state', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => okJson({ items: [savedCredential] })),
    )

    renderPage()

    expect(await screen.findByText('个人 OpenAI key')).toBeInTheDocument()
    expect(screen.getByText('名称')).toBeInTheDocument()
    expect(screen.getByText('Provider')).toBeInTheDocument()
    expect(screen.getByText('模型')).toBeInTheDocument()
    expect(screen.getByText('Base URL')).toBeInTheDocument()
    expect(screen.getByText('API key')).toBeInTheDocument()
    expect(screen.getByText('启用')).toBeInTheDocument()
    expect(screen.getByText('状态')).toBeInTheDocument()
    expect(screen.getByText('连续失败')).toBeInTheDocument()
    expect(screen.getByText('标记')).toBeInTheDocument()
    expect(screen.getByText('操作')).toBeInTheDocument()
    expect(screen.getByText('openai')).toBeInTheDocument()
    expect(screen.getByText('gpt-4.1-mini')).toBeInTheDocument()
    expect(screen.getByText('sk-...abcd')).toBeInTheDocument()
    expect(screen.getByText('首选')).toBeInTheDocument()
    expect(screen.getByText('当前通讯中')).toBeInTheDocument()
    expect(screen.getByText('0')).toBeInTheDocument()
    expect(
      screen.getByRole('button', { name: '编辑 个人 OpenAI key' }),
    ).toBeInTheDocument()
    expect(
      screen.getByRole('button', { name: '删除 个人 OpenAI key' }),
    ).toBeInTheDocument()
  })

  it('opens create modal and submits a new enabled preferred asset', async () => {
    const fetchMock = vi.fn(
      async (input: RequestInfo | URL, init?: RequestInit) => {
        const url = String(input)
        if (url === '/api/me/llm-credentials' && init?.method === 'POST') {
          return okJson({ ...savedCredential, id: 8, display_name: '备用 key' })
        }
        return okJson({ items: [savedCredential] })
      },
    )
    vi.stubGlobal('fetch', fetchMock)

    renderPage()

    fireEvent.click(await screen.findByRole('button', { name: '新增 API 资产' }))
    fireEvent.change(screen.getByLabelText('名称'), {
      target: { value: '备用 key' },
    })
    fireEvent.change(screen.getByLabelText('模型名称'), {
      target: { value: 'gpt-4.1-mini' },
    })
    fireEvent.change(screen.getByLabelText('API key'), {
      target: { value: 'sk-live-secret' },
    })
    fireEvent.click(screen.getByLabelText('设为首选资产'))
    fireEvent.click(screen.getByRole('button', { name: '创建' }))

    await waitFor(() =>
      expect(fetchMock).toHaveBeenCalledWith(
        '/api/me/llm-credentials',
        expect.objectContaining({
          method: 'POST',
          credentials: 'include',
          body: JSON.stringify({
            display_name: '备用 key',
            provider: 'openai',
            base_url: 'https://api.openai.com/v1',
            api_mode: 'responses',
            model_name: 'gpt-4.1-mini',
            api_key: 'sk-live-secret',
            is_enabled: true,
            is_preferred: true,
          }),
        }),
      ),
    )
  })

  it('opens edit modal and omits empty api key overwrite', async () => {
    const fetchMock = vi.fn(
      async (input: RequestInfo | URL, init?: RequestInit) => {
        const url = String(input)
        if (url === '/api/me/llm-credentials/7' && init?.method === 'PATCH') {
          return okJson({ ...savedCredential, model_name: 'gpt-4.1' })
        }
        return okJson({ items: [savedCredential] })
      },
    )
    vi.stubGlobal('fetch', fetchMock)

    renderPage()

    expect(await screen.findByText('个人 OpenAI key')).toBeInTheDocument()
    fireEvent.click(
      screen.getByRole('button', { name: '编辑 个人 OpenAI key' }),
    )
    fireEvent.change(screen.getByLabelText('模型名称'), {
      target: { value: 'gpt-4.1' },
    })
    fireEvent.click(screen.getByRole('button', { name: '更新' }))

    await waitFor(() =>
      expect(fetchMock).toHaveBeenCalledWith(
        '/api/me/llm-credentials/7',
        expect.objectContaining({
          method: 'PATCH',
          credentials: 'include',
          body: JSON.stringify({
            display_name: '个人 OpenAI key',
            base_url: 'https://api.openai.com/v1',
            api_mode: 'responses',
            model_name: 'gpt-4.1',
            is_enabled: true,
          }),
        }),
      ),
    )
  })

  it('clears stale save errors when the create modal reopens', async () => {
    function isVisible(element: Element) {
      let current: Element | null = element
      while (current) {
        const style = window.getComputedStyle(current)
        if (
          current.hasAttribute('hidden') ||
          style.display === 'none' ||
          style.visibility === 'hidden' ||
          style.opacity === '0'
        ) {
          return false
        }
        current = current.parentElement
      }
      return true
    }

    const visibleSaveErrors = () =>
      screen
        .queryAllByText('保存 API 资产失败')
        .filter((element) => isVisible(element))
    const fetchMock = vi.fn(
      async (input: RequestInfo | URL, init?: RequestInit) => {
        const url = String(input)
        if (url === '/api/me/llm-credentials' && init?.method === 'POST') {
          return new Response(JSON.stringify({ detail: 'save_failed' }), {
            status: 500,
            headers: { 'Content-Type': 'application/json' },
          })
        }
        return okJson({ items: [savedCredential] })
      },
    )
    vi.stubGlobal('fetch', fetchMock)

    renderPage()

    fireEvent.click(await screen.findByRole('button', { name: '新增 API 资产' }))
    fireEvent.change(screen.getByLabelText('名称'), {
      target: { value: '失败 key' },
    })
    fireEvent.change(screen.getByLabelText('模型名称'), {
      target: { value: 'gpt-4.1-mini' },
    })
    fireEvent.change(screen.getByLabelText('API key'), {
      target: { value: 'sk-failing-secret' },
    })
    fireEvent.click(screen.getByRole('button', { name: '创建' }))

    expect(await screen.findByText('保存 API 资产失败')).toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: '新增 API 资产' }))

    await waitFor(() => expect(visibleSaveErrors()).toHaveLength(0))
  })

  it('toggles enabled and sets preferred asset', async () => {
    const fetchMock = vi.fn(
      async (input: RequestInfo | URL, init?: RequestInit) => {
        const url = String(input)
        if (url === '/api/me/llm-credentials/7' && init?.method === 'PATCH') {
          return okJson({ ...savedCredential, is_enabled: false })
        }
        if (url === '/api/me/llm-credentials/7/preferred') {
          return okJson({ ...savedCredential, is_preferred: true })
        }
        return okJson({ items: [{ ...savedCredential, is_preferred: false }] })
      },
    )
    vi.stubGlobal('fetch', fetchMock)

    renderPage()

    expect(await screen.findByText('个人 OpenAI key')).toBeInTheDocument()
    fireEvent.click(screen.getByLabelText('个人 OpenAI key 启用'))
    fireEvent.click(screen.getByRole('button', { name: '设为首选' }))

    await waitFor(() =>
      expect(fetchMock).toHaveBeenCalledWith(
        '/api/me/llm-credentials/7',
        expect.objectContaining({
          method: 'PATCH',
          credentials: 'include',
          body: JSON.stringify({ is_enabled: false }),
        }),
      ),
    )
    await waitFor(() =>
      expect(fetchMock).toHaveBeenCalledWith(
        '/api/me/llm-credentials/7/preferred',
        expect.objectContaining({ method: 'POST', credentials: 'include' }),
      ),
    )
  })
})
