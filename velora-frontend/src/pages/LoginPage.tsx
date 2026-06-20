import { Lock, Mail } from 'lucide-react'
import { Button } from '@/components/ui/button'

interface LoginPageProps {
  email: string
  password: string
  error: string
  onChange: (partial: { email?: string; loginPassword?: string; loginError?: string }) => void
  onSubmit: () => void
  onPasswordReset: () => void
}

export default function LoginPage({ email, password, error, onChange, onSubmit, onPasswordReset }: LoginPageProps) {
  const inputClass = "h-16 w-full rounded-xl border border-[#e3ece9] bg-white px-12 text-[17px] font-bold text-[#183f40] shadow-sm shadow-teal-950/5 outline-none transition placeholder:text-[#8aa09e] focus:border-[#0f7d82] focus:ring-2 focus:ring-[#d7efea]"
  const maskedInputClass = `${inputClass} [-webkit-text-security:disc]`

  return (
    <div className="flex min-h-[700px] flex-col justify-center pt-2">
      <section className="rounded-[28px] border border-[#dce9e6] bg-white p-5 shadow-sm shadow-teal-950/5">
        <p className="text-center text-[26px] font-black text-[#183f40]">로그인</p>

        <div className="mt-5 space-y-3">
          <label className="relative block">
            <Mail className="absolute left-4 top-1/2 h-5 w-5 -translate-y-1/2 text-[#0f7d82]" />
            <input
              type="email"
              autoComplete="off"
              name="velora-login-email"
              value={email}
              onChange={event => onChange({ email: event.target.value, loginError: '' })}
              className={inputClass}
              placeholder="이메일"
            />
          </label>
          <label className="relative block">
            <Lock className="absolute left-4 top-1/2 h-5 w-5 -translate-y-1/2 text-[#0f7d82]" />
            <input
              type="text"
              autoComplete="off"
              autoCorrect="off"
              autoCapitalize="none"
              spellCheck={false}
              name="velora-login-code"
              value={password}
              onChange={event => onChange({ loginPassword: event.target.value, loginError: '' })}
              className={maskedInputClass}
              placeholder="비밀번호"
            />
          </label>
        </div>

        {error && <p className="mt-4 rounded-xl bg-red-50 px-4 py-3 text-center text-[17px] font-bold leading-[1.45] text-red-600">{error}</p>}

        <Button
          onClick={onSubmit}
          className="mt-5 h-16 w-full rounded-full bg-[#0f7d82] text-[18px] font-black text-white shadow-none hover:bg-[#0b6f74]"
        >
          로그인
        </Button>
        <button
          type="button"
          onClick={onPasswordReset}
          className="mt-4 h-12 w-full text-[17px] font-black text-[#0f7d82]"
        >
          비밀번호를 잊으셨나요?
        </button>
      </section>
    </div>
  )
}
