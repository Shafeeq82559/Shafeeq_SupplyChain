// Typed client for the FastAPI backend (proxied at /api by vite.config.ts).

export interface Range { predicted: number; low_p10: number; high_p90: number }
export interface Contribution { label: string; value: string | number; contribution: number }
export interface CaseRow {
  disruption_id: string; disruption_type: string; industry: string; supplier_region: string; supplier_tier: number
  disruption_severity: number; production_impact_pct: number; revenue_loss_usd: number; response_type: string
  full_recovery_days: number; permanent_supplier_change: boolean; hybrid_score?: number
}
export interface Plan {
  recommended_strategy: string; rationale: string; immediate_actions: string[]; recovery_plan: string[]; risks: string[]
  fallback_strategy?: string; cited_cases?: string[]; generated_by?: string
  evidence_note?: string; close_call?: string; minor_event_note?: string; guardrail_note?: string; fact_sheet?: string
}
export interface RankedStrategy {
  rank: number; response_type: string; strategy_score: number; expected_full_recovery_days: number
  expected_revenue_loss_usd: number; supplier_change_risk: number; evidence_cases: number; evidence_total: number
  feasible_now?: boolean; feasibility_note?: string
}
export interface Milestone { day: number; milestone: string }
export interface TraceStep { agent: string; status: string; duration_ms: number; summary: string }
export interface Analysis {
  query: string
  executive_summary: string
  assumptions?: string[]
  override_notes?: string[]
  ambiguity_notes?: string[]
  profile: {
    disruption_type: string; industry: string; supplier_region: string; supplier_tier: number
    supplier_size: string; has_backup_supplier: boolean; disruption_severity: number
  }
  classification: { method?: string }
  impact_assessment: {
    predictions: {
      production_impact_pct: Range; revenue_loss_usd: Range; full_recovery_days: Range; high_impact_probability: number
    }
    priority: { priority_level: string; priority_label: string; priority_score: number; factor_contributions: Record<string, number> }
    drivers: Record<string, { top: Contribution[]; unit: string; summary: string }>
  }
  investigation: {
    historical_summary: string; filters_applied: Record<string, unknown>; total_matching_filters: number
    relaxations: string[]; similar_cases: CaseRow[]
  }
  response: { plan: Plan; strategy_ranking: RankedStrategy[]; basis?: { description: string } }
  recovery: {
    timeline: { full_recovery_days: { predicted: number }; partial_recovery_days: { predicted: number } }
    milestones: Milestone[]; supplier_change_probability: number; supplier_change_outlook: string
    resilience: { resilience_score: number; resilience_grade: string; risk_band: string }
    monitoring_kpis: string[]
  }
  judgement: {
    scores: Record<string, number>; reasons: Record<string, string>; overall_feedback?: string
    judge: string; overall_score: number; passed: boolean; threshold: number; fallback_reason?: string
  }
  revisions: number
  trace: TraceStep[]
  total_duration_ms: number
}
export interface Health {
  status: string; llm: { enabled: boolean; model: string; provider: string }; models_ready: boolean; index_ready: boolean
}
export interface Provider { provider: string; available: boolean; active: boolean }
export type Overrides = Partial<{
  disruption_type: string; industry: string; supplier_region: string; supplier_tier: number
  supplier_size: string; has_backup_supplier: boolean; disruption_severity: number
}>

export class ApiError extends Error {
  status: number
  constructor(status: number, message: string) { super(message); this.status = status }
}

async function call<T>(method: string, path: string, body?: unknown, signal?: AbortSignal): Promise<T> {
  let res: Response
  try {
    res = await fetch(`/api${path}`, {
      method, signal,
      headers: body ? { 'Content-Type': 'application/json' } : undefined,
      body: body ? JSON.stringify(body) : undefined,
    })
  } catch (e) {
    if ((e as Error).name === 'AbortError') throw e
    throw new ApiError(0, 'Cannot reach the API. Start it with: uvicorn src.main:app --port 8000')
  }
  if (res.status === 422) {
    const d = (await res.json()).detail
    const v = d?.violations as (string | { field: string; message: string })[] | undefined
    throw new ApiError(422, 'Input rejected: ' + (v ? v.map((x) => (typeof x === 'string' ? x : `${x.field}: ${x.message}`)).join('; ') : JSON.stringify(d)))
  }
  if (!res.ok) {
    const raw = await res.text()
    let detail = raw
    try { const d = JSON.parse(raw).detail; if (typeof d === 'string') detail = d } catch { /* keep the raw text */ }
    throw new ApiError(res.status, `API error ${res.status}: ${detail.slice(0, 240)}`)
  }
  return res.json() as Promise<T>
}

export interface StepEvent { node: string; step: TraceStep }

/** Runs the analysis and reports each agent as it finishes (newline-delimited JSON from /analyze/stream). */
async function analyzeStream(
  query: string, profile: Overrides, observedImpact: number | undefined,
  onStep: (e: StepEvent) => void, signal?: AbortSignal,
): Promise<Analysis> {
  let res: Response
  try {
    res = await fetch('/api/analyze/stream', {
      method: 'POST', signal, headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ query, profile, ...(observedImpact ? { production_impact_pct: observedImpact } : {}) }),
    })
  } catch (e) {
    if ((e as Error).name === 'AbortError') throw e
    throw new ApiError(0, 'Cannot reach the API. Start it with: uvicorn src.main:app --port 8000')
  }
  if (!res.ok || !res.body) throw new ApiError(res.status, `API error ${res.status}: ${(await res.text()).slice(0, 240)}`)

  const reader = res.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''
  let result: Analysis | null = null
  const handle = (line: string) => {
    if (!line.trim()) return
    const ev = JSON.parse(line)
    if (ev.type === 'step') onStep({ node: ev.node, step: ev.step })
    else if (ev.type === 'result') result = ev.data as Analysis
    else if (ev.type === 'error') {
      throw new ApiError(ev.status ?? 500, ev.violations ? 'Input rejected: ' + (ev.violations as string[]).join('; ') : ev.message ?? 'The analysis failed.')
    }
  }
  for (;;) {
    const { value, done } = await reader.read()
    if (done) break
    buffer += decoder.decode(value, { stream: true })
    const lines = buffer.split('\n')
    buffer = lines.pop() ?? ''
    lines.forEach(handle)
  }
  handle(buffer)
  if (!result) throw new ApiError(500, 'The analysis ended without a result. Try again.')
  return result
}

export const api = {
  analyzeStream,
  health: (signal?: AbortSignal) => call<Health>('GET', '/health', undefined, signal),
  providers: () => call<{ providers: Provider[] }>('GET', '/llm/providers'),
  setProvider: (provider: string) => call<unknown>('POST', '/llm/provider', { provider }),
  analyze: (query: string, profile: Overrides, observedImpact: number | undefined, signal?: AbortSignal) =>
    call<Analysis>('POST', '/analyze', { query, profile, ...(observedImpact ? { production_impact_pct: observedImpact } : {}) }, signal),
  feedback: (payload: unknown) => call<unknown>('POST', '/feedback', payload),
  deepCheck: (query: string, plan: unknown) => call<DeepCheckResult>('POST', '/analyze/deep-check', { query, plan }),
  search: (body: unknown, signal?: AbortSignal) => call<SearchResponse>('POST', '/search', body, signal),
  prioritize: (items: unknown[]) => call<PrioritizeResponse>('POST', '/prioritize', { items }),
  predict: (profile: unknown) => call<PredictResponse>('POST', '/predict', profile),
  explain: (profile: unknown, target: string, narrate: boolean) => call<ExplainResponse>('POST', '/explain', { profile, target, narrate }),
  risk: (body: unknown) => call<RiskResponse>('POST', '/risk', body),
  stats: () => call<Stats>('GET', '/stats'),
  insights: () => call<Insights>('GET', '/insights'),
  evaluation: () => call<Evaluation>('GET', '/evaluation'),
  feedbackStats: () => call<FeedbackStats>('GET', '/feedback/stats'),
}

// ---------------------------------------------------------------- other pages
export interface SearchHit extends CaseRow {
  narrative?: string; semantic_score?: number; keyword_score?: number
  response_time_days?: number; partial_recovery_days?: number; supplier_size?: string; has_backup_supplier?: boolean
  matchRank?: number // position in the original ranking (set by the page, so the list can be re-sorted)
}
export interface SearchResponse {
  results: SearchHit[]; total_matching_filters: number; mode: string; filters_applied: Record<string, unknown>
  classification: { disruption_type: string; method: string } | null; summary: string; latency_ms: number
}
export interface PrioritizedItem {
  rank: number; id: string; disruption_severity: number; production_impact_pct: number; revenue_loss_usd: number
  supplier_tier: number; has_backup_supplier: boolean; priority_score: number; priority_level: string; priority_label: string
  recommended_action: string; factor_contributions: Record<string, number>
}
export interface PrioritizeResponse { ranked: PrioritizedItem[]; weights: Record<string, number>; levels: { min_score: number; level: string; label: string }[] }
export interface WhatIf {
  response_type: string; predicted_full_recovery_days: number; predicted_partial_recovery_days: number
  predicted_revenue_loss_usd: number; predicted_production_impact_pct: number; supplier_change_probability: number
}
export interface PredictResponse {
  predictions: {
    production_impact_pct: Range; revenue_loss_usd: Range; full_recovery_days: Range; partial_recovery_days: Range
    high_impact_probability: number; supplier_change_probability: number
  }
  what_if_by_response: WhatIf[]
}
export interface FullContribution extends Contribution { feature?: string; direction?: string }
export interface ExplainResponse {
  target: string; unit: string; baseline: number; prediction: number; contributions: FullContribution[]; summary: string; narrative?: string
}
export interface RiskResponse {
  disruption_risk_probability: number; risk_band: string; resilience_score: number; resilience_grade: string
  exposure_by_type: {
    disruption_type: string; historical_frequency: number; high_impact_probability: number; predicted_full_recovery_days: number
    predicted_production_impact_pct: number; predicted_revenue_loss_usd: number; vulnerability: number
    typical_severity: number; vulnerability_at_typical_severity: number
  }[]
  top_risk_drivers: FullContribution[]; recommendations: string[]
}
interface GroupStats { count: number; avg_production_impact_pct: number; avg_revenue_loss_usd: number; avg_full_recovery_days: number; supplier_change_rate: number }
export interface Stats {
  total_records: number
  totals: { total_revenue_loss_usd: number; avg_production_impact_pct: number; median_full_recovery_days: number; backup_supplier_rate: number; permanent_supplier_change_rate: number }
  by_disruption_type: Record<string, GroupStats>
  by_industry: Record<string, GroupStats>
  by_severity: Record<string, { avg_production_impact_pct: number; avg_full_recovery_days: number }>
  recovery_days_by_type_and_response: Record<string, Record<string, number>>
}
export interface Insights {
  key_insights: string[]
  global_importance: Record<string, { label: string; share_pct: number }[]>
  model_metrics: Record<string, Record<string, number | null>>
}
export interface Evaluation {
  retrieval_eval?: { results: Record<string, Record<string, number>> }
  deepeval_results?: { judge_model?: string; n_cases?: number; summary: Record<string, { mean: number }> }
  ragas_results?: { judge_model?: string; n_cases?: number; summary: Record<string, { mean: number }> }
  llm_judge_eval?: { judge_model?: string; n_cases?: number; mean_overall: number; pass_rate: number; mean_by_criterion: Record<string, number> }
  search_eval?: {
    n_queries: number
    k: number
    queries_stating_severity: number
    results: Record<string, Record<string, { 'precision@10': number; ci95: [number, number]; 'hit@1': number; 'hit@10': number; MRR: number; 'nDCG@10': number }>>
    latency: Record<string, { p50_ms: number; p95_ms: number }>
    filters: Record<string, { p50_ms: number; p95_ms: number; results_breaking_a_filter: number }>
  }
  model_metrics?: Record<string, Record<string, number | null>>
  model_benchmark?: { regression: Record<string, Record<string, { MAE: number; R2: number }>> }
  classification_eval?: { n_queries: number; results: Record<string, { accuracy: Record<string, number>; severity_MAE: number }> }
}
export interface FeedbackStats {
  total_feedback: number; average_rating: number | null; helpful_rate: number | null
  strategy_multipliers: Record<string, number>
  recent: Record<string, unknown>[]
}

export interface DeepCheckResult {
  framework: string; judge_model: string; n_contexts: number; seconds: number
  scores: Record<'answer_relevancy' | 'faithfulness' | 'analysis_correctness' | 'evidence_relevance', { score: number; passed: boolean; reason: string } | null>
  errors: Record<string, string>
}
