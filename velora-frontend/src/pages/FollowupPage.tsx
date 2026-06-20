import { CalendarCheck, HeartPulse, PhoneCall, RefreshCw, ShieldCheck } from 'lucide-react'
import { Button } from '@/components/ui/button'

interface FollowupPageProps {
  resultsData: Record<string, unknown> | null
  onNewAnalysis: () => void
  onHistory: () => void
}

export default function FollowupPage({ resultsData, onNewAnalysis, onHistory }: FollowupPageProps) {
  const analysis = resultsData?.analysis as Record<string, unknown> | undefined
  const guidance = (resultsData?.guidance as Array<Record<string, unknown>>) || []
  const nextSteps = (resultsData?.next_steps as string[]) || []
  const riskLevel = String(analysis?.risk_level || 'middle')
  const isHigh = riskLevel === 'high'

  const defaultSteps = isHigh
    ? ['가까운 시일 내 전문기관 상담 일정을 검토하세요.', '비슷한 조건의 통화를 한 번 더 검증해 결과 변화를 확인하세요.', '수면, 약 복용, 통화 환경처럼 결과에 영향을 줄 수 있는 상황을 기록하세요.']
    : ['2-4주 뒤 비슷한 길이의 통화로 다시 검증하세요.', '부모님 발화가 30초 이상 포함되도록 자연스러운 주제를 선택하세요.', '위험 점수보다 반복 측정의 변화 추세를 우선 확인하세요.']
  const steps = nextSteps.length ? nextSteps : defaultSteps

  return (
    <div className="space-y-5 pt-2">
      <section className="rounded-[30px] bg-white px-5 py-7 text-center shadow-sm shadow-teal-950/5">
        <div className="mx-auto flex h-20 w-20 items-center justify-center rounded-full bg-[#d7efea] text-[#0f7d82]">
          <HeartPulse className="h-10 w-10" />
        </div>
        <p className="mt-5 text-[21px] font-black text-[#183f40]">검증 이후 후속 대응</p>
        <p className="mx-auto mt-3 max-w-[280px] text-[17px] font-bold leading-[1.55] text-[#607b79]">
          이번 결과는 의료 진단이 아니라 통화 음성 기반 위험 신호입니다. 같은 조건의 반복 검증과 생활 관찰을 함께 보세요.
        </p>
      </section>

      <section className="rounded-2xl border border-[#e3ece9] bg-white p-4">
        <p className="flex items-center gap-2 text-[18px] font-black text-[#183f40]">
          <CalendarCheck className="h-6 w-6 text-[#0f7d82]" />
          권장 다음 단계
        </p>
        <div className="mt-3 space-y-2">
          {steps.slice(0, 4).map((step, idx) => (
            <p key={idx} className="flex gap-3 text-[17px] font-bold leading-[1.5] text-[#426160]">
              <span className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-[#d7efea] text-[14px] font-black text-[#0f7d82]">
                {idx + 1}
              </span>
              {step}
            </p>
          ))}
        </div>
      </section>

      {guidance.length > 0 && (
        <section className="rounded-2xl border border-[#e3ece9] bg-white p-4">
          <p className="text-[18px] font-black text-[#183f40]">맞춤 안내</p>
          <div className="mt-3 space-y-3">
            {guidance.slice(0, 3).map((item, idx) => (
              <div key={idx} className="rounded-xl bg-[#f7fbfa] px-3 py-3">
                <p className="text-[17px] font-black text-[#183f40]">{item.title as string}</p>
                <p className="mt-2 text-[16px] font-bold leading-[1.5] text-[#6f8785]">{item.description as string}</p>
              </div>
            ))}
          </div>
        </section>
      )}

      <section className="rounded-2xl bg-[#eff9f6] p-4">
        <p className="flex items-center gap-2 text-[18px] font-black text-[#183f40]">
          <PhoneCall className="h-6 w-6 text-[#0f7d82]" />
          다음 통화 팁
        </p>
        <p className="mt-3 text-[17px] font-bold leading-[1.5] text-[#426160]">
          건강, 식사, 최근 만난 사람, 오늘 일정처럼 부모님이 자연스럽게 길게 말할 수 있는 주제가 좋습니다.
        </p>
      </section>

      <p className="flex items-start gap-3 rounded-2xl bg-[#f7fbfa] px-4 py-4 text-[16px] font-bold leading-[1.5] text-[#7d9593]">
        <ShieldCheck className="mt-1 h-6 w-6 shrink-0 text-[#0f7d82]" />
        이상 신호가 반복되거나 일상 기능 변화가 함께 보이면 전문기관 상담을 권장합니다.
      </p>

      <div className="space-y-3">
        <Button onClick={onNewAnalysis} className="h-[64px] w-full rounded-full bg-[#0f7d82] text-[18px] font-black text-white shadow-none hover:bg-[#0b6f74]">
          <RefreshCw className="mr-2 h-4 w-4" />
          다시 새로 검증
        </Button>
        <Button onClick={onHistory} variant="outline" className="h-[60px] w-full rounded-full border-[#dce9e6] bg-white text-[18px] font-black text-[#0f7d82] shadow-none hover:bg-[#f4faf8]">
          지난 검증 이력 보기
        </Button>
      </div>
    </div>
  )
}
