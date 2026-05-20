import { render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'

import App from './App'

const healthResponse = {
  status: 'ok',
  service: 'learning-coach-backend',
}

const currentUser = {
  id: 1,
  username: 'alice',
  email: 'alice@example.com',
  display_name: 'alice',
  has_default_llm_credential: true,
}

describe('App shell', () => {
  afterEach(() => {
    vi.unstubAllGlobals()
    window.history.pushState({}, '', '/')
  })

  it('redirects unauthenticated root visits to login', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async (input: RequestInfo | URL) => {
        const url = String(input)
        if (url === '/api/auth/me') {
          return new Response(JSON.stringify({ detail: 'not_authenticated' }), {
            status: 401,
            headers: { 'Content-Type': 'application/json' },
          })
        }
        return new Response(JSON.stringify(healthResponse), {
          status: 200,
          headers: { 'Content-Type': 'application/json' },
        })
      }),
    )
    window.history.pushState({}, '', '/')

    render(<App />)

    expect(await screen.findByRole('heading', { name: '登录' })).toBeInTheDocument()
  })

  it('renders product navigation and backend health status', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async (input: RequestInfo | URL) => {
        const url = String(input)
        if (url === '/api/auth/me') {
          return new Response(JSON.stringify(currentUser), {
            status: 200,
            headers: { 'Content-Type': 'application/json' },
          })
        }
        if (url === '/api/health') {
          return new Response(JSON.stringify(healthResponse), {
            status: 200,
            headers: { 'Content-Type': 'application/json' },
          })
        }
        return new Response(
          JSON.stringify({ items: [], total: 0, page: 1, page_size: 20 }),
          { status: 200, headers: { 'Content-Type': 'application/json' } },
        )
      }),
    )
    window.history.pushState({}, '', '/problems')

    render(<App />)

    expect(
      screen.getByRole('heading', { name: 'Agentic Coding Learning Coach' }),
    ).toBeInTheDocument()
    expect(screen.getByRole('link', { name: '题库' })).toBeInTheDocument()
    expect(screen.getByRole('link', { name: '工作台' })).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'API 设置' })).toBeInTheDocument()
    expect(screen.getByRole('link', { name: '复盘' })).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Trace' })).toBeInTheDocument()
    expect(await screen.findByText('API 正常')).toBeInTheDocument()
  })

  it('redirects authenticated users without default API asset to settings', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async (input: RequestInfo | URL) => {
        const url = String(input)
        if (url === '/api/auth/me') {
          return new Response(
            JSON.stringify({ ...currentUser, has_default_llm_credential: false }),
            { status: 200, headers: { 'Content-Type': 'application/json' } },
          )
        }
        if (url === '/api/me/llm-credentials') {
          return new Response(JSON.stringify({ items: [] }), {
            status: 200,
            headers: { 'Content-Type': 'application/json' },
          })
        }
        return new Response(JSON.stringify(healthResponse), {
          status: 200,
          headers: { 'Content-Type': 'application/json' },
        })
      }),
    )
    window.history.pushState({}, '', '/')

    render(<App />)

    expect(await screen.findByRole('heading', { name: 'API 设置' })).toBeInTheDocument()
  })

  it('renders the workspace route', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async (input: RequestInfo | URL) => {
        const url = String(input)
        if (url === '/api/auth/me') {
          return new Response(JSON.stringify(currentUser), {
            status: 200,
            headers: { 'Content-Type': 'application/json' },
          })
        }
        if (url === '/api/health') {
          return new Response(JSON.stringify(healthResponse), {
            status: 200,
            headers: { 'Content-Type': 'application/json' },
          })
        }
        return new Response(JSON.stringify({}), {
          status: 200,
          headers: { 'Content-Type': 'application/json' },
        })
      }),
    )
    window.history.pushState({}, '', '/workspace')

    render(<App />)

    expect(
      await screen.findByRole('heading', { name: '做题工作台' }),
    ).toBeInTheDocument()
  })
})
