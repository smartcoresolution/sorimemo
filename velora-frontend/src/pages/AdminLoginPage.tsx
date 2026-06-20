import { Lock, ShieldCheck, User } from 'lucide-react'
import { Button } from '@/components/ui/button'

interface AdminLoginPageProps {
  adminId: string
  adminPassword: string
  error: string
  onChange: (partial: { adminId?: string; adminPassword?: string; adminError?: string }) => void
  onSubmit: () => void
  onBack: () => void
}

export default function AdminLoginPage({ adminId, adminPassword, error, onChange, onSubmit, onBack }: AdminLoginPageProps) {
  const inputClass = "h-[52px] w-full rounded-xl border border-[#e3ece9] bg-white px-11 text-[14px] font-medium text-[#183f40] shadow-sm shadow-teal-950/5 outline-none transition focus:border-[#0f7d82] focus:ring-2 focus:ring-[#d7efea]"

  return (
    <div className="w-full">
      <section className="rounded-[8px] border border-white/10 bg-white p-6 shadow-xl shadow-black/20">
        <p className="text-center text-[22px] font-black text-[#172326]">SoriMemo Admin</p>
        <p className="mt-2 text-center text-[13px] leading-5 text-[#718082]">
          관리자 콘솔 전용 로그인
        </p>

        <div className="mt-6 space-y-3">
          <label className="relative block">
            <User className="absolute left-4 top-1/2 h-4 w-4 -translate-y-1/2 text-[#0f7d82]" />
            <input
              autoComplete="off"
              name="sorimemo-admin-id"
              value={adminId}
              onChange={event => onChange({ adminId: event.target.value, adminError: '' })}
              className={inputClass}
              placeholder="Admin ID"
            />
          </label>
          <label className="relative block">
            <Lock className="absolute left-4 top-1/2 h-4 w-4 -translate-y-1/2 text-[#0f7d82]" />
            <input
              type="password"
              autoComplete="current-password"
              autoCorrect="off"
              autoCapitalize="none"
              spellCheck={false}
              name="sorimemo-admin-code"
              value={adminPassword}
              onChange={event => onChange({ adminPassword: event.target.value, adminError: '' })}
              className={inputClass}
              placeholder="Password"
            />
          </label>
        </div>

        {error && <p className="mt-4 rounded-xl bg-red-50 px-3 py-2 text-center text-[12px] font-semibold text-red-600">{error}</p>}

        <Button
          onClick={onSubmit}
          className="mt-5 h-12 w-full rounded-[8px] bg-[#0f7d82] text-[14px] font-black text-white shadow-none hover:bg-[#0b6f74]"
        >
          관리자 콘솔 입장
        </Button>
        <Button
          onClick={onBack}
          variant="outline"
          className="mt-3 h-12 w-full rounded-[8px] border-[#dce9e6] bg-white text-[14px] font-black text-[#0f7d82] shadow-none hover:bg-[#f4faf8]"
        >
          서비스 화면으로 나가기
        </Button>
        <p className="mt-4 flex items-start gap-2 rounded-[8px] bg-[#f7fbfa] px-3 py-3 text-[11px] font-semibold leading-4 text-[#6f8785]">
          <ShieldCheck className="mt-0.5 h-3.5 w-3.5 shrink-0 text-[#0f7d82]" />
          관리자 콘솔의 개인정보 및 음성 데이터 접근은 운영 로그 기록 대상입니다.
        </p>
      </section>
    </div>
  )
}
