import { Lock, Mail, User } from 'lucide-react'
import { Button } from '@/components/ui/button'

interface SignupPageProps {
  email: string
  displayName: string
  signupPurpose: string
  password: string
  passwordConfirm: string
  error: string
  onChange: (partial: { email?: string; displayName?: string; signupPurpose?: string; signupPassword?: string; signupPasswordConfirm?: string; signupError?: string }) => void
  onComplete: () => void
}

export default function SignupPage({ email, displayName, signupPurpose, password, passwordConfirm, error, onChange, onComplete }: SignupPageProps) {
  const canContinue = Boolean(email.trim() && displayName.trim() && signupPurpose && password && passwordConfirm)
  const inputClass = "h-[60px] w-full rounded-xl border border-[#e3ece9] bg-white px-14 text-[19px] font-black text-[#183f40] shadow-sm shadow-teal-950/5 outline-none transition placeholder:text-[#9aabaa] focus:border-[#0f7d82] focus:ring-2 focus:ring-[#d7efea]"
  const maskedInputClass = `${inputClass} [-webkit-text-security:disc]`

  return (
    <div className="space-y-5 pt-2">
      <section className="space-y-4">
        <label className="relative block">
          <Mail className="absolute left-4 top-1/2 h-6 w-6 -translate-y-1/2 text-[#0f7d82]" />
          <input
            type="email"
            autoComplete="off"
            name="sorimemo-signup-email"
            value={email}
            onChange={event => onChange({ email: event.target.value, signupError: '' })}
            className={inputClass}
            placeholder="이메일"
          />
        </label>
        <label className="relative block">
          <User className="absolute left-4 top-1/2 h-6 w-6 -translate-y-1/2 text-[#0f7d82]" />
          <input
            autoComplete="name"
            name="sorimemo-signup-display-name"
            value={displayName}
            onChange={event => onChange({ displayName: event.target.value, signupError: '' })}
            className={inputClass}
            placeholder="가입자 이름 또는 표시명"
          />
        </label>
        <select
          value={signupPurpose}
          onChange={event => onChange({ signupPurpose: event.target.value, signupError: '' })}
          className="h-[60px] w-full rounded-xl border border-[#e3ece9] bg-white px-6 text-[19px] font-black text-[#183f40] shadow-sm shadow-teal-950/5 outline-none transition focus:border-[#0f7d82] focus:ring-2 focus:ring-[#d7efea]"
        >
          <option value="">가입 목적 선택</option>
          <option value="parent_care">부모님 검증</option>
          <option value="self_check">본인 검증</option>
          <option value="both">부모님/본인 모두</option>
        </select>
        <label className="relative block">
          <Lock className="absolute left-4 top-1/2 h-6 w-6 -translate-y-1/2 text-[#0f7d82]" />
          <input
            value={password}
            onChange={event => onChange({ signupPassword: event.target.value, signupError: '' })}
            className={maskedInputClass}
            type="text"
            autoComplete="off"
            autoCorrect="off"
            autoCapitalize="none"
            spellCheck={false}
            name="sorimemo-signup-code"
            placeholder="비밀번호"
          />
        </label>
        <label className="relative block">
          <Lock className="absolute left-4 top-1/2 h-6 w-6 -translate-y-1/2 text-[#0f7d82]" />
          <input
            value={passwordConfirm}
            onChange={event => onChange({ signupPasswordConfirm: event.target.value, signupError: '' })}
            className={maskedInputClass}
            type="text"
            autoComplete="off"
            autoCorrect="off"
            autoCapitalize="none"
            spellCheck={false}
            name="sorimemo-signup-code-confirm"
            placeholder="비밀번호 확인"
          />
        </label>
      </section>

      {error && <p className="rounded-xl bg-red-50 px-4 py-3 text-center text-[17px] font-bold leading-[1.42] text-red-600">{error}</p>}

      <Button
        onClick={onComplete}
        disabled={!canContinue}
        className="h-[68px] w-full rounded-full bg-[#0f7d82] text-[20px] font-black text-white shadow-none hover:bg-[#0b6f74]"
      >
        서비스 확인으로 이동
      </Button>
    </div>
  )
}
