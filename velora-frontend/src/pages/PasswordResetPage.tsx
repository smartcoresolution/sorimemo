import { KeyRound, Lock, Mail } from 'lucide-react'
import { Button } from '@/components/ui/button'

interface PasswordResetPageProps {
  email: string
  resetToken: string
  newPassword: string
  newPasswordConfirm: string
  message: string
  error: string
  onChange: (partial: {
    email?: string
    resetToken?: string
    resetPassword?: string
    resetPasswordConfirm?: string
    resetMessage?: string
    resetError?: string
  }) => void
  onRequest: () => void
  onConfirm: () => void
}

export default function PasswordResetPage({
  email,
  resetToken,
  newPassword,
  newPasswordConfirm,
  message,
  error,
  onChange,
  onRequest,
  onConfirm,
}: PasswordResetPageProps) {
  const inputClass = "h-[60px] w-full rounded-xl border border-[#e3ece9] bg-white px-12 text-[18px] font-black text-[#183f40] shadow-sm shadow-teal-950/5 outline-none transition placeholder:text-[#8aa09e] focus:border-[#0f7d82] focus:ring-2 focus:ring-[#d7efea]"

  return (
    <div className="flex min-h-[700px] flex-col justify-center pt-2">
      <section className="rounded-[28px] border border-[#dce9e6] bg-white p-5 shadow-sm shadow-teal-950/5">
        <p className="text-center text-[24px] font-black text-[#183f40]">비밀번호 재설정</p>
        <p className="mx-auto mt-3 max-w-[280px] text-center text-[17px] font-bold leading-[1.5] text-[#7d9593]">
          가입 이메일로 재설정 코드를 발급한 뒤 새 비밀번호를 설정합니다.
        </p>

        <div className="mt-6 space-y-3">
          <label className="relative block">
            <Mail className="absolute left-4 top-1/2 h-5 w-5 -translate-y-1/2 text-[#0f7d82]" />
            <input
              type="email"
              autoComplete="email"
              value={email}
              onChange={event => onChange({ email: event.target.value, resetError: '', resetMessage: '' })}
              className={inputClass}
              placeholder="가입 이메일"
            />
          </label>
          <Button
            onClick={onRequest}
            variant="outline"
            className="h-[60px] w-full rounded-full border-[#dce9e6] bg-white text-[18px] font-black text-[#0f7d82] shadow-none hover:bg-[#f4faf8]"
          >
            재설정 코드 받기
          </Button>
          <label className="relative block">
            <KeyRound className="absolute left-4 top-1/2 h-5 w-5 -translate-y-1/2 text-[#0f7d82]" />
            <input
              autoComplete="one-time-code"
              value={resetToken}
              onChange={event => onChange({ resetToken: event.target.value, resetError: '' })}
              className={inputClass}
              placeholder="재설정 코드"
            />
          </label>
          <label className="relative block">
            <Lock className="absolute left-4 top-1/2 h-5 w-5 -translate-y-1/2 text-[#0f7d82]" />
            <input
              type="password"
              autoComplete="new-password"
              value={newPassword}
              onChange={event => onChange({ resetPassword: event.target.value, resetError: '' })}
              className={inputClass}
              placeholder="새 비밀번호"
            />
          </label>
          <label className="relative block">
            <Lock className="absolute left-4 top-1/2 h-5 w-5 -translate-y-1/2 text-[#0f7d82]" />
            <input
              type="password"
              autoComplete="new-password"
              value={newPasswordConfirm}
              onChange={event => onChange({ resetPasswordConfirm: event.target.value, resetError: '' })}
              className={inputClass}
              placeholder="새 비밀번호 확인"
            />
          </label>
        </div>

        {message && <p className="mt-4 rounded-xl bg-[#f1f8f6] px-4 py-3 text-center text-[17px] font-bold leading-[1.45] text-[#0f7d82]">{message}</p>}
        {error && <p className="mt-4 rounded-xl bg-red-50 px-4 py-3 text-center text-[17px] font-bold leading-[1.45] text-red-600">{error}</p>}

        <Button
          onClick={onConfirm}
          className="mt-5 h-[64px] w-full rounded-full bg-[#0f7d82] text-[19px] font-black text-white shadow-none hover:bg-[#0b6f74]"
        >
          새 비밀번호 저장
        </Button>
      </section>
    </div>
  )
}
