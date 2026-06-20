import { useEffect, useState } from 'react'
import { AlertCircle, Check, ChevronRight, Lock } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Checkbox } from '@/components/ui/checkbox'
import { fetchPolicy, submitConsent } from '@/lib/api'
import type { VerificationType } from '@/App'

interface ConsentPageProps {
  ageGroup: string
  userName: string
  verificationType: VerificationType
  subjectDisplayName: string
  subjectAgeGroup: string
  subjectGender: string
  subjectRelation: string
  onComplete: (token: string, ageGroup: string) => void
}

interface ConsentItem {
  key: string
  label: string
  required: boolean
}

export default function ConsentPage({
  ageGroup,
  userName,
  verificationType,
  subjectDisplayName,
  subjectAgeGroup,
  subjectGender,
  subjectRelation,
  onComplete,
}: ConsentPageProps) {
  const [items, setItems] = useState<ConsentItem[]>([])
  const [checks, setChecks] = useState<Record<string, boolean>>({})
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  useEffect(() => {
    fetchPolicy()
      .then(data => {
        setItems(data.consent_items)
        const initial: Record<string, boolean> = {}
        data.consent_items.forEach((item: ConsentItem) => {
          initial[item.key] = false
        })
        setChecks(initial)
      })
      .catch(() => setError('정책 정보를 불러오지 못했습니다.'))
  }, [])

  const requiredItems = items.filter(item => item.required)
  const optionalItems = items.filter(item => !item.required)
  const allRequiredChecked = requiredItems.length > 0 && requiredItems.every(item => checks[item.key])
  const allChecked = items.length > 0 && items.every(item => checks[item.key])

  const toggleAll = () => {
    const nextValue = !allChecked
    const next: Record<string, boolean> = {}
    items.forEach(item => {
      next[item.key] = nextValue
    })
    setChecks(next)
  }

  const handleSubmit = async () => {
    if (!allRequiredChecked) {
      setError('필수 동의 항목을 확인해 주세요.')
      return
    }

    setLoading(true)
    setError('')
    try {
      const result = await submitConsent({
        user_name: userName || undefined,
        age_group: ageGroup || 'other',
        subject_type: verificationType === 'self_voice' ? 'self' : 'parent',
        subject_relation: verificationType === 'self_voice' ? 'self' : subjectRelation,
        subject_display_name: subjectDisplayName,
        subject_age_group: subjectAgeGroup || 'other',
        subject_gender: subjectGender,
        data_collection_agreed: checks.data_collection ?? false,
        privacy_policy_agreed: checks.privacy_policy ?? false,
        non_medical_disclaimer_agreed: checks.non_medical_disclaimer ?? false,
        third_party_voice_agreed: checks.third_party_voice ?? false,
        model_training_agreed: checks.model_training ?? false,
      })
      onComplete(result.consent_token, ageGroup || 'other')
    } catch (e) {
      setError(e instanceof Error ? e.message : '동의 처리 중 오류가 발생했습니다.')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="space-y-4 pt-1">
      <section className="rounded-2xl border border-[#dce9e6] bg-[#f7fbfa] px-3 py-4">
        <div className="mb-3 flex items-start gap-3 px-1">
          <AlertCircle className="mt-0.5 h-6 w-6 shrink-0 text-[#0f7d82]" />
          <div className="max-w-[260px]">
            <p className="text-[18px] font-black text-[#183f40]">안내</p>
            <p className="mt-2 text-[17px] font-bold leading-[1.52] text-[#5f7775]">
              안심소리 기억케어는 치매를 진단하지 않습니다. 자녀가 업로드한 부모님과의 통화에서 자녀 음성을 제외하고, 상대 화자의 인지 저하 위험 신호를 참고용으로 확인합니다.
            </p>
          </div>
        </div>
        <button
          onClick={toggleAll}
          className="flex min-h-[60px] w-full items-center justify-between rounded-xl bg-white px-4 py-3 text-left text-[19px] font-black text-[#183f40]"
        >
          <span className="flex items-center gap-3">
            <span className={`flex h-6 w-6 items-center justify-center rounded-md ${allChecked ? 'bg-[#0f7d82]' : 'bg-[#e9f1ef]'}`}>
              {allChecked && <Check className="h-4 w-4 text-white" />}
            </span>
            전체 동의
          </span>
          <ChevronRight className="h-6 w-6 text-[#90a5a3]" />
        </button>

        <div className="mt-3 space-y-2">
          {requiredItems.map(item => (
            <label key={item.key} className="flex min-h-[64px] items-start gap-3 rounded-xl bg-white px-4 py-3">
              <Checkbox
                checked={checks[item.key] ?? false}
                onCheckedChange={checked => setChecks(prev => ({ ...prev, [item.key]: checked === true }))}
                className="mt-1 h-6 w-6 shrink-0 border-[#b9cbc8] data-[state=checked]:bg-[#0f7d82]"
              />
              <span className="max-w-[250px] text-[17px] font-black leading-[1.45] text-[#365b59]">
                <span className="mr-1 text-[#0f7d82]">필수</span>
                {item.label}
              </span>
            </label>
          ))}
        </div>
        {optionalItems.length > 0 && (
          <div className="mt-4 space-y-2">
            <p className="px-1 text-[17px] font-black text-[#183f40]">선택 동의</p>
            {optionalItems.map(item => (
              <label key={item.key} className="flex min-h-[72px] items-start gap-3 rounded-xl bg-white px-4 py-3">
                <Checkbox
                  checked={checks[item.key] ?? false}
                  onCheckedChange={checked => setChecks(prev => ({ ...prev, [item.key]: checked === true }))}
                  className="mt-1 h-6 w-6 shrink-0 border-[#b9cbc8] data-[state=checked]:bg-[#0f7d82]"
                />
                <span className="max-w-[250px] text-[17px] font-black leading-[1.48] text-[#365b59]">
                  <span className="mr-1 text-[#8a9e9b]">선택</span>
                  {item.label}
                </span>
              </label>
            ))}
          </div>
        )}
      </section>

      {error && <p className="rounded-xl bg-red-50 px-4 py-3 text-center text-[17px] font-bold leading-[1.42] text-red-600">{error}</p>}

      <Button
        onClick={handleSubmit}
        disabled={loading || !allRequiredChecked}
        className="h-[68px] w-full rounded-full bg-[#0f7d82] text-[20px] font-black text-white shadow-none hover:bg-[#0b6f74]"
      >
        {loading ? '처리 중...' : '확인하고 계속'}
      </Button>

      <p className="flex items-center justify-center gap-2 pt-1 text-center text-[16px] font-bold leading-[1.45] text-[#8aa09e]">
        <Lock className="h-5 w-5 shrink-0" />
        원본 통화 파일은 분석 후 삭제되는 것을 원칙으로 합니다.
      </p>
    </div>
  )
}
