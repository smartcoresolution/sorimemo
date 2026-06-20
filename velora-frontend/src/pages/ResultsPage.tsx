import { ChevronRight, FileSearch2, Info, RefreshCw } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { getPredictedStatus, getReferenceScore, getStatusFromReferenceScore } from '@/lib/resultScore'

interface ResultsPageProps {
  resultsData: Record<string, unknown> | null
  onRestart: () => void
  onReliability: () => void
}

const RESULT_COPY = {
  Normal: {
    ringText: '현재는\n위험 신호가\n낮습니다',
    summary: '이번 음성에서는 인지기능 저하와 관련된\n뚜렷한 위험 신호가 많이 보이지 않았습니다.',
  },
  MCI: {
    ringText: '변화 가능성\n신호가\n보입니다',
    summary: '이번 음성에서 인지기능 변화와 관련된\n일부 참고 신호가 함께 보였습니다.',
  },
  AD: {
    ringText: '위험 신호가\n상대적으로\n높습니다',
    summary: '이번 음성에서 인지기능 저하와 관련된\n강한 참고 신호가 상대적으로 높게 보였습니다.',
  },
}

export default function ResultsPage({ resultsData, onRestart, onReliability }: ResultsPageProps) {
  if (!resultsData) {
    return (
      <div className="flex min-h-[700px] flex-col justify-center text-center">
        <p className="text-[18px] font-bold text-[#6f8785]">결과 데이터를 불러올 수 없습니다.</p>
        <Button onClick={onRestart} className="mt-5 h-12 rounded-full bg-[#0f7d82] text-white shadow-none">
          홈에서 다시 시작
        </Button>
      </div>
    )
  }

  const analysis = resultsData.analysis as Record<string, unknown>
  const probabilities = analysis.model_probabilities as Record<string, number>
  const predictedStatus = getPredictedStatus(analysis as Record<string, any>, probabilities)
  const referenceScore = getReferenceScore(predictedStatus, probabilities)
  const displayStatus = getStatusFromReferenceScore(referenceScore)
  const resultCopy = RESULT_COPY[displayStatus]

  return (
    <div className="space-y-4 pt-2">
      <section className="rounded-[26px] border border-[#eef3f1] bg-white px-5 pb-7 pt-5 text-center shadow-[0_6px_18px_rgba(15,63,64,0.08)]">
        <div className="relative mx-auto h-56 w-56">
          <svg className="h-full w-full -rotate-90" viewBox="0 0 120 120">
            <circle
              cx="60"
              cy="60"
              r="50"
              fill="none"
              stroke="#0f7d82"
              strokeWidth="10"
              strokeLinecap="round"
            />
          </svg>
          <div className="absolute inset-0 flex flex-col items-center justify-center">
            <p className="whitespace-pre-line text-[23px] font-black leading-[1.35] text-[#183f40]">
              {resultCopy.ringText}
            </p>
          </div>
        </div>
        <p className="mx-auto mt-3 max-w-[270px] whitespace-pre-line text-[18px] font-black leading-[1.65] text-[#244f50]">
          {resultCopy.summary}
        </p>
      </section>

      <section className="space-y-3">
        <button onClick={onReliability} className="flex h-[68px] w-full items-center justify-between rounded-[16px] bg-[#008b8a] px-5 text-white shadow-[0_8px_18px_rgba(0,125,130,0.18)]">
          <span className="flex items-center gap-3 text-[20px] font-black">
            <FileSearch2 className="h-7 w-7" />
            결과 자세히 보기
          </span>
          <ChevronRight className="h-5 w-5" />
        </button>
      </section>

      <section className="flex items-start gap-3 rounded-[16px] border border-[#dbecea] bg-[#f8fbfb] px-4 py-4">
        <div className="flex h-12 w-12 shrink-0 items-center justify-center rounded-xl border-2 border-[#0f8d8f] text-[#0f8d8f]">
          <Info className="h-7 w-7" />
        </div>
        <p className="max-w-[255px] text-[17px] font-bold leading-[1.55] text-[#5d7675]">
          {analysis.disclaimer as string || '이 결과는 의료 진단이 아닌 참고용 정보입니다. 음성에서 보인 특징을 바탕으로 위험 신호를 미리 살펴보는 용도이며, 정확한 판단은 전문 상담이나 검사가 필요합니다.'}
        </p>
      </section>
      <Button
        onClick={onRestart}
        variant="outline"
        className="h-[60px] w-full rounded-[16px] border-2 border-[#0f7d82] bg-white text-[18px] font-black text-[#0f7d82] shadow-none hover:bg-[#f4faf8]"
      >
        <RefreshCw className="mr-2 h-4 w-4" />
        다시 분석하기
      </Button>
    </div>
  )
}
