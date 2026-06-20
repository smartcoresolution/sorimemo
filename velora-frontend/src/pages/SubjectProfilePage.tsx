import { UserRound, UsersRound } from 'lucide-react'
import { Button } from '@/components/ui/button'
import type { VerificationType } from '@/App'

interface SubjectProfilePageProps {
  verificationType: VerificationType
  subjectDisplayName: string
  subjectAgeGroup: string
  subjectGender: string
  subjectRelation: string
  error: string
  onChange: (partial: {
    subjectDisplayName?: string
    subjectAgeGroup?: string
    subjectGender?: string
    subjectRelation?: string
    signupError?: string
  }) => void
  onComplete: () => void
}

const ageOptions = [
  ['40s', '40대'],
  ['50s', '50대'],
  ['60s', '60대'],
  ['70s', '70대'],
  ['80s', '80대'],
  ['90s', '90대 이상'],
  ['other', '기타'],
]

const relationName = (relation: string) => ({
  mother: '어머니',
  father: '아버지',
  spouse: '배우자',
  other: '',
}[relation] || '')

export default function SubjectProfilePage({
  verificationType,
  subjectDisplayName,
  subjectAgeGroup,
  subjectGender,
  subjectRelation,
  error,
  onChange,
  onComplete,
}: SubjectProfilePageProps) {
  const isSelf = verificationType === 'self_voice'
  const needsCustomName = !isSelf && subjectRelation === 'other'
  const canContinue = Boolean(subjectAgeGroup && subjectGender && (isSelf || subjectRelation) && (!needsCustomName || subjectDisplayName.trim()))
  const inputClass = "h-[62px] w-full rounded-xl border border-[#e3ece9] bg-white px-5 text-[18px] font-black text-[#183f40] shadow-sm shadow-teal-950/5 outline-none transition placeholder:text-[17px] placeholder:font-bold placeholder:text-[#9aa9a7] focus:border-[#0f7d82] focus:ring-2 focus:ring-[#d7efea]"
  const nextLabel = isSelf ? '본인 음성 등록으로 이동' : '자녀 음성 등록으로 이동'

  return (
    <div className="space-y-5 pt-2">
      <section className="rounded-[24px] bg-white p-6 shadow-sm shadow-teal-950/5">
        <div className="flex items-start gap-4">
          <div className="flex h-14 w-14 shrink-0 items-center justify-center rounded-xl bg-[#e9f7f4] text-[#0f7d82]">
            {isSelf ? <UserRound className="h-7 w-7" /> : <UsersRound className="h-7 w-7" />}
          </div>
          <div>
            <p className="text-[23px] font-black leading-8 text-[#183f40]">{isSelf ? '본인 검증 정보' : '부모님 검증 정보'}</p>
            <p className="mt-2 text-[17px] font-bold leading-7 text-[#6f8785]">
              분석 결과와 관리자 확인을 위해 필요한 최소 정보만 입력합니다.
            </p>
          </div>
        </div>
      </section>

      <section className="space-y-3">
        {!isSelf && (
          <select
            value={subjectRelation}
            onChange={event => onChange({
              subjectRelation: event.target.value,
              subjectDisplayName: relationName(event.target.value),
              signupError: '',
            })}
            className={inputClass}
          >
            <option value="">관계 선택</option>
            <option value="mother">어머니</option>
            <option value="father">아버지</option>
            <option value="spouse">배우자</option>
            <option value="other">기타 가족</option>
          </select>
        )}

        {needsCustomName && (
          <input
            value={subjectDisplayName}
            onChange={event => onChange({ subjectDisplayName: event.target.value, signupError: '' })}
            className={inputClass}
            placeholder="추가 구분명 예: 할머니"
          />
        )}

        <select
          value={subjectAgeGroup}
          onChange={event => onChange({ subjectAgeGroup: event.target.value, signupError: '' })}
          className={inputClass}
        >
          <option value="">연령대 선택</option>
          {ageOptions.map(([value, label]) => <option key={value} value={value}>{label}</option>)}
        </select>

        <select
          value={subjectGender}
          onChange={event => onChange({ subjectGender: event.target.value, signupError: '' })}
          className={inputClass}
        >
          <option value="">성별 선택</option>
          <option value="female">여성</option>
          <option value="male">남성</option>
          <option value="other">기타/응답 안 함</option>
        </select>
      </section>

      {error && <p className="rounded-xl bg-red-50 px-4 py-3 text-center text-[16px] font-black text-red-600">{error}</p>}

      <Button
        onClick={onComplete}
        disabled={!canContinue}
        className="h-[68px] w-full rounded-full bg-[#0f7d82] text-[20px] font-black text-white shadow-none hover:bg-[#0b6f74]"
      >
        {nextLabel}
      </Button>
    </div>
  )
}
