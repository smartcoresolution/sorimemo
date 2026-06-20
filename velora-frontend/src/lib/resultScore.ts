export type CognitiveStatus = 'Normal' | 'MCI' | 'AD'

export const RESULT_LABELS: Record<CognitiveStatus, { label: string; color: string }> = {
  Normal: { label: '인지기능 위험 낮음', color: '#16a36a' },
  MCI: { label: '인지기능 변화 가능성 있음', color: '#f6a51a' },
  AD: { label: '치매 관련 위험 신호 높음', color: '#ef4444' },
}

export const isCognitiveStatus = (value: unknown): value is CognitiveStatus =>
  value === 'Normal' || value === 'MCI' || value === 'AD'

export const getPredictedStatus = (
  analysis: Record<string, any> | undefined,
  probabilities: Record<string, number> = {},
): CognitiveStatus => {
  if (isCognitiveStatus(analysis?.cognitive_status)) return analysis.cognitive_status

  const rows: Array<{ name: CognitiveStatus; value: number }> = [
    { name: 'Normal', value: Number(probabilities.Normal || 0) },
    { name: 'MCI', value: Number(probabilities.MCI || 0) },
    { name: 'AD', value: Number(probabilities.AD || 0) },
  ]
  return rows.reduce((top, row) => (row.value > top.value ? row : top), rows[0]).name
}

export const getReferenceScore = (status: CognitiveStatus, probabilities: Record<string, number> = {}) => {
  const confidence = Math.max(0, Math.min(1, Number(probabilities[status] || 0)))
  if (status === 'Normal') return Math.round(80 + confidence * 20)
  if (status === 'MCI') return Math.round(50 + confidence * 29)
  return Math.max(10, Math.round(50 - confidence * 50))
}

export const getStatusFromReferenceScore = (score: number): CognitiveStatus => {
  if (score >= 80) return 'Normal'
  if (score >= 50) return 'MCI'
  return 'AD'
}

export const getProbabilityRows = (probabilities: Record<string, number> = {}) => [
  { name: 'Normal' as CognitiveStatus, value: Math.round(Number(probabilities.Normal || 0) * 100), ...RESULT_LABELS.Normal },
  { name: 'MCI' as CognitiveStatus, value: Math.round(Number(probabilities.MCI || 0) * 100), ...RESULT_LABELS.MCI },
  { name: 'AD' as CognitiveStatus, value: Math.round(Number(probabilities.AD || 0) * 100), ...RESULT_LABELS.AD },
]
