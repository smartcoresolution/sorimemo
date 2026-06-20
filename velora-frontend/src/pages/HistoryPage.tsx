import { BarChart3, ChevronRight, RefreshCw, Trash2 } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { getPredictedStatus, getReferenceScore, getStatusFromReferenceScore, RESULT_LABELS } from '@/lib/resultScore'

interface HistoryPageProps {
  items: Array<Record<string, any>>
  onSelect: (item: Record<string, any>) => void
  onRestart: () => void
  onDelete: (analysisId: string) => void
}

function getVerificationLabel(item: Record<string, any>) {
  return item.verification_type === 'self_voice' ? '내 목소리 검증' : '부모님 통화 검증'
}

function getPatternSummary(analysis: Record<string, any>) {
  const probabilities = analysis.model_probabilities || {}
  const predictedStatus = getPredictedStatus(analysis, probabilities)
  const referenceScore = getReferenceScore(predictedStatus, probabilities)
  const displayStatus = getStatusFromReferenceScore(referenceScore)
  return {
    key: displayStatus,
    value: referenceScore,
    ...RESULT_LABELS[displayStatus],
  }
}

function formatDate(value: unknown) {
  if (!value) return '이전 검증 기록'
  const date = new Date(String(value))
  if (Number.isNaN(date.getTime())) return '이전 검증 기록'
  return new Intl.DateTimeFormat('ko-KR', {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  }).format(date)
}

function formatShortDate(value: unknown) {
  if (!value) return '이전 기록'
  const date = new Date(String(value))
  if (Number.isNaN(date.getTime())) return '이전 기록'
  return new Intl.DateTimeFormat('ko-KR', {
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  }).format(date)
}

export default function HistoryPage({ items, onSelect, onRestart, onDelete }: HistoryPageProps) {
  const latestItem = items[0]
  const latestAnalysis = latestItem?.analysis as Record<string, any> | undefined
  const latestPattern = latestAnalysis ? getPatternSummary(latestAnalysis) : null
  const chartRows = items.slice(0, 5).map(item => {
    const analysis = item.analysis as Record<string, any>
    const pattern = getPatternSummary(analysis)
    const checkedAt = item.saved_at || item.created_at || analysis.created_at
    return {
      id: String(analysis.analysis_id || checkedAt),
      date: formatShortDate(checkedAt),
      value: pattern.value,
      label: pattern.label,
      color: pattern.color,
    }
  })

  return (
    <div className="space-y-4 pt-2">
      {items.length === 0 ? (
        <section className="flex min-h-[620px] flex-col items-center justify-center rounded-[28px] bg-white p-6 text-center">
          <BarChart3 className="h-12 w-12 text-[#0f7d82]" />
          <p className="mt-4 text-[22px] font-black text-[#183f40]">지난 검증 이력이 없습니다</p>
          <p className="mt-3 text-[17px] font-bold leading-[1.5] text-[#7d9593]">새 검증을 완료하면 음성 변화 이력이 이곳에 표시됩니다.</p>
          <Button onClick={onRestart} className="mt-6 h-16 w-full rounded-full bg-[#0f7d82] text-[18px] font-black text-white shadow-none">
            <RefreshCw className="mr-2 h-5 w-5" />
            다시 새로 검증
          </Button>
        </section>
      ) : (
        <>
          {latestItem && latestAnalysis && latestPattern && (
            <section className="rounded-[26px] border border-[#dce9e6] bg-white p-5 shadow-sm shadow-teal-950/5">
              <p className="text-[22px] font-black text-[#183f40]">최근 검증 요약</p>
              <p className="mt-3 text-[18px] font-bold leading-[1.5] text-[#6f8785]">
                참고값은 0에서 100 사이로 표시되며, 값이 낮을수록 위험 신호가 높게 해석됩니다.
              </p>

              <div className="mt-5 rounded-2xl bg-[#f1f8f6] p-4">
                <div className="mb-3 flex justify-between px-[80px] text-[15px] font-black text-[#8aa09e]">
                  <span>0</span>
                  <span>50</span>
                  <span>100</span>
                </div>
                <div className="space-y-3">
                  {chartRows.map(row => (
                    <div key={row.id} className="grid grid-cols-[92px_1fr_54px] items-center gap-2">
                      <p className="truncate text-[15px] font-black text-[#607b79]">{row.date}</p>
                      <div className="h-4 rounded-full bg-white">
                        <div className="h-full rounded-full" style={{ width: `${row.value}%`, backgroundColor: row.color }} />
                      </div>
                      <p className="text-right text-[16px] font-black text-[#183f40]">{row.value}</p>
                    </div>
                  ))}
                </div>
                <p className="mt-5 text-[18px] font-black leading-[1.45] text-[#183f40]">{chartRows[0]?.label}</p>
              </div>
            </section>
          )}

          <p className="px-1 text-[21px] font-black text-[#426160]">검증 이력</p>

          {items.map(item => {
            const analysis = item.analysis as Record<string, any>
            const pattern = getPatternSummary(analysis)
            const checkedAt = item.saved_at || item.created_at || analysis.created_at
            return (
              <div
                key={analysis.analysis_id}
                className="rounded-2xl border border-[#e3ece9] bg-white p-5 shadow-sm shadow-teal-950/5"
              >
                <div className="flex items-start justify-between gap-3">
                  <button onClick={() => onSelect(item)} className="min-w-0 flex-1 text-left">
                    <p className="text-[20px] font-black leading-[1.35] text-[#183f40]">{formatDate(checkedAt)}</p>
                    <p className="mt-3 text-[18px] font-bold leading-[1.5] text-[#6f8785]">
                      {getVerificationLabel(item)} · {pattern.label}
                    </p>
                    <p className="mt-2 text-[18px] font-black leading-[1.4] text-[#0f7d82]">
                      참고값 {pattern.value}
                    </p>
                  </button>
                  <div className="flex shrink-0 items-center gap-2">
                    <button
                      onClick={() => onDelete(String(analysis.analysis_id || ''))}
                      className="flex h-12 w-12 items-center justify-center rounded-full text-[#8aa09e] hover:bg-red-50 hover:text-red-500"
                      aria-label="이력 삭제"
                    >
                      <Trash2 className="h-6 w-6" />
                    </button>
                    <button
                      onClick={() => onSelect(item)}
                      className="flex h-12 w-12 items-center justify-center rounded-full text-[#8aa09e] hover:bg-[#f1f8f6]"
                      aria-label="결과 보기"
                    >
                      <ChevronRight className="h-7 w-7" />
                    </button>
                  </div>
                </div>
              </div>
            )
          })}
        </>
      )}
    </div>
  )
}
