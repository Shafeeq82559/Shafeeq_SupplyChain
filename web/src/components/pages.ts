export const PAGES = [
  { id: 'analyze', label: 'Analyze', title: 'Analyze a disruption', built: true },
  { id: 'cases', label: 'Similar cases', title: 'Search past disruptions', built: true },
  { id: 'prioritize', label: 'Prioritize', title: 'Rank open disruptions', built: true },
  { id: 'predict', label: 'Predict & explain', title: 'Predict impact and explain it', built: true },
  { id: 'risk', label: 'Risk & resilience', title: "Score a supplier's resilience", built: true },
  { id: 'insights', label: 'Insights', title: 'What the past disruptions show', built: true },
  { id: 'evaluation', label: 'Evaluation', title: 'How well it works', built: true },
] as const

export type PageId = (typeof PAGES)[number]['id']
