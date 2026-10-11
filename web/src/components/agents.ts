// The agents of the workflow, in the order they run (matches the node names streamed by /analyze/stream).
export const AGENTS = [
  { node: 'guardrail', label: 'Guardrails', doing: 'Checking the input is safe and on topic' },
  { node: 'classify', label: 'Classification', doing: 'Reading the description: type, severity, industry, region' },
  { node: 'investigate', label: 'Investigation', doing: 'Searching 100,000 past disruptions for comparable cases' },
  { node: 'impact', label: 'Impact', doing: 'Estimating production impact, revenue loss and recovery time' },
  { node: 'response', label: 'Response', doing: 'Ranking strategies on comparable cases and writing the plan' },
  { node: 'recovery', label: 'Recovery', doing: 'Mapping milestones and supplier resilience' },
  { node: 'judge', label: 'Quality check', doing: 'Checking the answer against the evidence' },
  { node: 'report', label: 'Report', doing: 'Compiling the briefing' },
] as const
