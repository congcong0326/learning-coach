import { requestJson } from './client'

export type ProblemTag = {
  slug: string
  name: string
  translated_name: string
}

export type ProblemCategorySummary = {
  slug: string
  name: string
  description: string
}

export type ProblemListItem = {
  id: number
  frontend_id: string
  slug: string
  title: string
  translated_title: string
  difficulty: 'Easy' | 'Medium' | 'Hard'
  tags: ProblemTag[]
  categories: ProblemCategorySummary[]
}

export type ProblemListResponse = {
  items: ProblemListItem[]
  total: number
  page: number
  page_size: number
}

export type ProblemListParams = {
  page?: number
  page_size?: number
}

export type ProblemDetail = ProblemListItem & {
  statement_md: string
  leetcode_url: string
  sample_test_case: string
  python3_snippet: string
}

export function getProblems(
  params: ProblemListParams = {},
): Promise<ProblemListResponse> {
  const searchParams = new URLSearchParams()
  if (params.page !== undefined) {
    searchParams.set('page', String(params.page))
  }
  if (params.page_size !== undefined) {
    searchParams.set('page_size', String(params.page_size))
  }

  const query = searchParams.toString()
  return requestJson<ProblemListResponse>(
    query ? `/api/problems?${query}` : '/api/problems',
  )
}

export function getProblem(slug: string): Promise<ProblemDetail> {
  return requestJson<ProblemDetail>(`/api/problems/${encodeURIComponent(slug)}`)
}
