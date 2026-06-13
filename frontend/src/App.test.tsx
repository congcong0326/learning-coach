import { render, screen, waitFor } from '@testing-library/react'
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

    await waitFor(() => expect(window.location.pathname).toBe('/login'))
  })

  it('renders only the problem library navigation for authenticated users', async () => {
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
      await screen.findByRole('heading', { name: 'Coding Problem Library' }),
    ).toBeInTheDocument()
    expect(screen.getByRole('link', { name: '题库' })).toBeInTheDocument()
    expect(screen.queryByText('学习计划')).not.toBeInTheDocument()
    expect(screen.queryByText('工作台')).not.toBeInTheDocument()
    expect(screen.queryByText('API 设置')).not.toBeInTheDocument()
    expect(screen.queryByText('复盘')).not.toBeInTheDocument()
    expect(await screen.findByText('API 正常')).toBeInTheDocument()
  })

  it('redirects authenticated root visits to the problem library', async () => {
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
        return new Response(JSON.stringify(healthResponse), {
          status: 200,
          headers: { 'Content-Type': 'application/json' },
        })
      }),
    )
    window.history.pushState({}, '', '/')

    render(<App />)

    await waitFor(() => expect(window.location.pathname).toBe('/problems'))
  })
})
