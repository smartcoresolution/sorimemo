import { useCallback, useEffect, useMemo, useState } from 'react'
import {
  Activity,
  AlertTriangle,
  BarChart3,
  Bell,
  ClipboardList,
  Database,
  FileText,
  GitBranch,
  LayoutDashboard,
  LogOut,
  MessageSquare,
  Mic,
  RotateCw,
  Search,
  Server,
  Settings,
  ShieldCheck,
  SlidersHorizontal,
  Stethoscope,
  Trash2,
  Users,
} from 'lucide-react'
import { getAdminDashboard, runAdminRetentionCleanup } from '@/lib/api'
import { getPredictedStatus, getReferenceScore } from '@/lib/resultScore'

interface AdminPageProps {
  onBack: () => void
}

type AdminTab = 'dashboard' | 'users' | 'audio' | 'results' | 'detail' | 'models' | 'training' | 'logs' | 'settings'
type RiskLabel = 'Normal' | 'MCI 의심' | 'AD 의심' | '재분석 필요'
type QualityLabel = '좋음' | '보통' | '부족'

interface PatientRow {
  id: string
  accountName: string
  subjectName: string
  subjectType: string
  ageGroup: string
  latestDate: string
  latestResult: RiskLabel
  status: string
}

interface AudioRow {
  id: string
  patientName: string
  uploadedAt: string
  duration: string
  quality: QualityLabel
  separationStatus: string
  analysisStatus: string
}

interface ResultRow {
  id: string
  patientName: string
  result: RiskLabel
  confidence: number
  referenceScore: number
  qualityScore: number
  createdAt: string
  recommendation: string
}

interface LogRow {
  id: string
  actor: string
  action: string
  target: string
  createdAt: string
  level: 'info' | 'warning'
}

const number = (value: unknown) => Number(value || 0)

const displaySubject = (value: string) => value || '-'

const relationLabel = (relation: unknown) => ({
  self: '본인',
  mother: '어머니',
  father: '아버지',
  spouse: '배우자',
  other: '기타',
}[String(relation || '')] || String(relation || '-'))

const subjectTypeLabel = (type: unknown, relation: unknown) => (
  String(type) === 'self' ? '본인' : relationLabel(relation)
)

const toReferenceScore = (item: Record<string, unknown>) => {
  const probabilities = (item.model_probabilities || {}) as Record<string, number>
  const status = getPredictedStatus({ cognitive_status: item.cognitive_status }, probabilities)
  return getReferenceScore(status, probabilities)
}

const formatDateTime = (value: unknown) => {
  if (!value) return '-'
  const date = new Date(String(value))
  if (Number.isNaN(date.getTime())) return String(value)
  return date.toLocaleString('ko-KR', {
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  })
}

const riskBadgeClass: Record<RiskLabel, string> = {
  Normal: 'bg-emerald-50 text-emerald-700 ring-emerald-100',
  'MCI 의심': 'bg-amber-50 text-amber-700 ring-amber-100',
  'AD 의심': 'bg-red-50 text-red-700 ring-red-100',
  '재분석 필요': 'bg-slate-100 text-slate-700 ring-slate-200',
}

const qualityBadgeClass: Record<QualityLabel, string> = {
  좋음: 'bg-emerald-50 text-emerald-700 ring-emerald-100',
  보통: 'bg-sky-50 text-sky-700 ring-sky-100',
  부족: 'bg-red-50 text-red-700 ring-red-100',
}

function RiskBadge({ value }: { value: RiskLabel }) {
  return <span className={`inline-flex rounded-md px-2 py-1 text-[11px] font-black ring-1 ${riskBadgeClass[value]}`}>{value}</span>
}

function QualityBadge({ value }: { value: QualityLabel }) {
  return <span className={`inline-flex rounded-md px-2 py-1 text-[11px] font-black ring-1 ${qualityBadgeClass[value]}`}>{value}</span>
}

function StatCard({
  label,
  value,
  sub,
  icon: Icon,
}: {
  label: string
  value: string
  sub: string
  icon: typeof Activity
}) {
  return (
    <div className="rounded-[8px] border border-[#dce9e6] bg-white p-4 shadow-sm shadow-teal-950/5">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <p className="text-[11px] font-bold text-[#6f8785]">{label}</p>
          <p className="mt-1 text-[24px] font-black leading-8 text-[#183f40]">{value}</p>
        </div>
        <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-[8px] bg-[#e9f7f4] text-[#0f7d82]">
          <Icon className="h-4 w-4" />
        </span>
      </div>
      <p className="mt-2 text-[11px] font-semibold leading-4 text-[#829895]">{sub}</p>
    </div>
  )
}

function Panel({ title, icon: Icon, children, action }: { title: string; icon: typeof Activity; children: React.ReactNode; action?: React.ReactNode }) {
  return (
    <section className="rounded-[8px] border border-[#dce9e6] bg-white p-4 shadow-sm shadow-teal-950/5">
      <div className="flex items-center justify-between gap-3">
        <p className="flex items-center gap-2 text-[14px] font-black text-[#183f40]">
          <Icon className="h-4 w-4 text-[#0f7d82]" />
          {title}
        </p>
        {action}
      </div>
      <div className="mt-4">{children}</div>
    </section>
  )
}

function EmptyState({ text }: { text: string }) {
  return <p className="rounded-[8px] bg-[#f7fbfa] px-3 py-4 text-[12px] font-semibold text-[#6f8785]">{text}</p>
}

function buildAdminRows(data: Record<string, any>) {
  const operations = data.operations || {}
  const management = data.management || {}
  const dbUsers = (management.users || []) as Array<Record<string, unknown>>
  const dbAudioFiles = (management.audio_files || []) as Array<Record<string, unknown>>
  const dbResults = (management.analysis_results || []) as Array<Record<string, unknown>>
  const dbLogs = (management.audit_logs || []) as Array<Record<string, unknown>>
  const recentJobs = (operations.recent_jobs || []) as Array<Record<string, unknown>>

  const results: ResultRow[] = dbResults.length > 0
    ? dbResults.map((item, index) => ({
      id: String(item.id || `result-${index + 1}`),
      patientName: String(item.user_name || item.login_id || '사용자'),
      result: (['Normal', 'MCI 의심', 'AD 의심', '재분석 필요'].includes(String(item.result)) ? item.result : 'Normal') as RiskLabel,
      confidence: number(item.confidence_score),
      referenceScore: toReferenceScore(item),
      qualityScore: item.quality === '좋음' ? 88 : item.quality === '보통' ? 74 : 58,
      createdAt: String(item.created_at || ''),
      recommendation: String(item.recommendation || (item.result === 'Normal' ? '정기 관찰을 유지합니다.' : '전문기관 상담을 권장합니다.')),
    }))
    : []

  const patients: PatientRow[] = dbUsers.length > 0
    ? dbUsers.map((item, index) => {
      const latestResult = (['Normal', 'MCI 의심', 'AD 의심', '재분석 필요'].includes(String(item.latest_result)) ? item.latest_result : 'Normal') as RiskLabel
      return {
        id: String(item.id || `patient-${index + 1}`),
        accountName: String(item.email || item.user_name || '사용자'),
        subjectName: String(item.subject_name || '-'),
        subjectType: subjectTypeLabel(item.subject_type, item.subject_relation),
        ageGroup: String(item.subject_age_group || item.age_group || '-'),
        latestDate: String(item.latest_analysis_at || item.last_login_at || item.created_at || ''),
        latestResult,
        status: String(item.status || (latestResult === 'Normal' ? '정상' : latestResult === 'MCI 의심' ? '주의' : '고위험')),
      }
    })
    : results.map((item, index) => ({
    id: `patient-${index + 1}`,
    accountName: ['김민준', '박서연', '이도윤', '최하은', '정지호'][index % 5],
    subjectName: item.patientName,
    subjectType: '-',
    ageGroup: ['60대', '70대', '80대'][index % 3],
    latestDate: item.createdAt,
    latestResult: item.result,
    status: item.result === 'Normal' ? '정상' : item.result === 'MCI 의심' ? '주의' : '고위험',
  }))

  const audioRows: AudioRow[] = dbAudioFiles.length > 0
    ? dbAudioFiles.map((item, index) => ({
      id: String(item.id || `audio-${index + 1}`),
      patientName: String(item.user_name || item.login_id || '사용자'),
      uploadedAt: String(item.uploaded_at || ''),
      duration: `${Math.round(number(item.duration_seconds))}초`,
      quality: (['좋음', '보통', '부족'].includes(String(item.quality)) ? item.quality : '보통') as QualityLabel,
      separationStatus: String(item.separation_status || '대기'),
      analysisStatus: String(item.analysis_status || '대기'),
    }))
    : (recentJobs.length > 0 ? recentJobs : results).map((item, index) => {
    const isJob = 'job_id' in item
    const status = isJob ? String(item.status || '대기') : '분석 완료'
    const quality: QualityLabel = index % 4 === 2 ? '부족' : index % 2 === 0 ? '좋음' : '보통'
    return {
      id: String((item as Record<string, unknown>).job_id || (item as ResultRow).id || `audio-${index + 1}`),
      patientName: patients[index % patients.length]?.subjectName || '사용자',
      uploadedAt: String((item as Record<string, unknown>).created_at || new Date().toISOString()),
      duration: `${78 + index * 19}초`,
      quality,
      separationStatus: status === 'failed' ? '실패' : '완료',
      analysisStatus: status === 'failed' ? '재처리 필요' : status === 'completed' || !isJob ? '분석 완료' : '대기',
    }
  })

  const logs: LogRow[] = dbLogs.length > 0
    ? dbLogs.map((item, index) => ({
      id: String(item.id || `log-${index + 1}`),
      actor: String(item.actor || 'system'),
      action: String(item.action || '관리자 작업'),
      target: String(item.target_type || item.target_id || '-'),
      createdAt: String(item.created_at || ''),
      level: String(item.action || '').includes('failed') ? 'warning' : 'info',
    }))
    : [
    { id: 'log-1', actor: 'admin', action: '관리자 대시보드 접근', target: 'dashboard', createdAt: new Date().toISOString(), level: 'info' },
    { id: 'log-2', actor: 'admin', action: '최근 분석 결과 조회', target: 'analysis_results', createdAt: results[0]?.createdAt || new Date().toISOString(), level: 'info' },
    { id: 'log-3', actor: 'system', action: '개인정보 다운로드 기능 비활성 상태 확인', target: 'privacy_guard', createdAt: new Date().toISOString(), level: 'warning' },
  ]

  return { patients, audioRows, results, logs }
}

export default function AdminPage({ onBack }: AdminPageProps) {
  const [data, setData] = useState<Record<string, any> | null>(null)
  const [error, setError] = useState('')
  const [cleanupStatus, setCleanupStatus] = useState('')
  const [operationNotice, setOperationNotice] = useState('')
  const [refreshStatus, setRefreshStatus] = useState('')
  const [isRefreshing, setIsRefreshing] = useState(false)
  const [activeTab, setActiveTab] = useState<AdminTab>('dashboard')
  const [selectedResultId, setSelectedResultId] = useState('')
  const [query, setQuery] = useState('')

  const loadDashboard = useCallback(async (showStatus = false) => {
    if (showStatus) {
      setIsRefreshing(true)
      setRefreshStatus('새로고침 중...')
    }
    try {
      const payload = await getAdminDashboard()
      setData(payload)
      setError('')
      if (showStatus) {
        setRefreshStatus(`새로고침 완료 · ${new Date().toLocaleTimeString('ko-KR', { hour: '2-digit', minute: '2-digit', second: '2-digit' })}`)
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : '관리자 데이터를 불러오지 못했습니다.')
      if (showStatus) setRefreshStatus('새로고침 실패')
    } finally {
      if (showStatus) setIsRefreshing(false)
    }
  }, [])

  useEffect(() => {
    loadDashboard()
  }, [loadDashboard])

  const runCleanup = async () => {
    setCleanupStatus('만료 데이터 정리 중...')
    try {
      const result = await runAdminRetentionCleanup()
      const cleanup = result.cleanup || {}
      setCleanupStatus(`정리 완료 · 결과 ${number(cleanup.expired_analysis_results_deleted)} · 음성 ${number(cleanup.expired_audio_files_removed) + number(cleanup.expired_voice_sample_files_removed)}`)
      loadDashboard()
    } catch (e) {
      setCleanupStatus(e instanceof Error ? e.message : '만료 데이터 정리에 실패했습니다.')
    }
  }

  const showPendingOperation = (kind: 'reanalysis' | 'notification' | 'report' | 'memo') => {
    setOperationNotice(
      kind === 'reanalysis'
        ? '재분석 기능은 준비 중입니다. 추후 분석 작업 재실행 API와 연결됩니다.'
        : kind === 'notification'
          ? '알림 기능은 준비 중입니다. 추후 가입자 안내 발송 기능과 연결됩니다.'
          : kind === 'report'
            ? '리포트 생성 기능은 준비 중입니다. 추후 PDF/요약 리포트 생성 API와 연결됩니다.'
            : '관리자 메모 기능은 준비 중입니다. 추후 메모 저장 및 변경 이력 API와 연결됩니다.',
    )
  }

  const rows = useMemo(() => data ? buildAdminRows(data) : { patients: [], audioRows: [], results: [], logs: [] }, [data])
  const system = data?.system || {}
  const pipeline = data?.pipeline || {}
  const storage = data?.storage || {}
  const governance = data?.governance || {}
  const operations = data?.operations || {}
  const alerts = (data?.alerts || []) as Array<Record<string, unknown>>
  const retention = governance.retention || {}
  const modelTraining = governance.model_training || {}
  const trainingConsents = (data?.management?.training_consents || []) as Array<Record<string, unknown>>
  const modelLayer = pipeline.model_layer || {}
  const completedCount = number(system.requests_completed)
  const uploadedCount = number(pipeline.mobile_capture?.queue)
  const poorAudioCount = rows.audioRows.filter(item => item.quality === '부족').length
  const reanalysisCount = rows.results.filter(item => item.result === '재분석 필요').length + rows.audioRows.filter(item => item.analysisStatus.includes('재')).length
  const highRiskCount = rows.results.filter(item => item.result === 'MCI 의심' || item.result === 'AD 의심').length
  const modelAccuracy = modelLayer.accuracy == null ? '-' : `${Math.round(number(modelLayer.accuracy) * 100)}%`
  const nodeRatio = Math.min(1, number(system.active_ai_nodes) / Math.max(1, number(system.max_ai_nodes)))

  const filteredPatients = rows.patients.filter(item => `${item.accountName}${item.subjectName}${item.subjectType}${item.status}`.includes(query.trim()))
  const selectedResult = rows.results.find(item => item.id === selectedResultId) || rows.results[0]

  const tabs: Array<{ id: AdminTab; label: string; icon: typeof Activity }> = [
    { id: 'dashboard', label: '대시보드', icon: LayoutDashboard },
    { id: 'users', label: '사용자', icon: Users },
    { id: 'audio', label: '음성 데이터', icon: Mic },
    { id: 'results', label: '분석 결과', icon: ClipboardList },
    { id: 'detail', label: '분석 상세', icon: FileText },
    { id: 'models', label: 'AI 모델', icon: GitBranch },
    { id: 'training', label: '학습 데이터', icon: Database },
    { id: 'logs', label: '관리자 로그', icon: ShieldCheck },
    { id: 'settings', label: '환경 설정', icon: Settings },
  ]

  if (error) {
    return (
      <div className="flex min-h-[700px] flex-col justify-center text-center">
        <AlertTriangle className="mx-auto h-10 w-10 text-red-500" />
        <p className="mt-3 text-[13px] font-bold text-red-600">{error}</p>
        <button onClick={onBack} className="mt-5 h-12 rounded-[8px] bg-[#0f7d82] text-sm font-black text-white">돌아가기</button>
      </div>
    )
  }

  if (!data) {
    return <div className="flex min-h-[700px] items-center justify-center text-[13px] font-bold text-[#6f8785]">관리자 콘솔 로딩 중...</div>
  }

  return (
    <div className="min-h-[720px] bg-[#eef5f2] text-[#183f40]">
      <div className="grid gap-3 lg:grid-cols-[220px_minmax(0,1fr)]">
        <aside className="rounded-[8px] border border-[#dce9e6] bg-white p-3 shadow-sm shadow-teal-950/5">
          <div className="rounded-[8px] bg-[#152329] p-4 text-white">
            <div className="flex items-center gap-2">
              <Server className="h-5 w-5 text-[#7bd88f]" />
              <p className="text-[15px] font-black">SoriMemo Admin</p>
            </div>
            <p className="mt-1 text-[11px] leading-4 text-white/60">안심소리 기억케어 운영 콘솔</p>
          </div>
          <nav className="mt-3 grid grid-cols-2 gap-2 lg:grid-cols-1">
            {tabs.map(item => {
              const Icon = item.icon
              const active = activeTab === item.id
              return (
                <button
                  key={item.id}
                  onClick={() => setActiveTab(item.id)}
                  className={`flex h-10 items-center gap-2 rounded-[8px] px-3 text-left text-[12px] font-black transition ${active ? 'bg-[#0f7d82] text-white' : 'bg-[#f7fbfa] text-[#426260] hover:bg-[#edf7f4]'}`}
                >
                  <Icon className="h-4 w-4 shrink-0" />
                  <span className="truncate">{item.label}</span>
                </button>
              )
            })}
          </nav>
        </aside>

        <main className="min-w-0 space-y-3">
          <header className="rounded-[8px] border border-[#dce9e6] bg-white p-4 shadow-sm shadow-teal-950/5">
            <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
              <div>
                <p className="text-[18px] font-black text-[#172326]">{tabs.find(item => item.id === activeTab)?.label}</p>
                <p className="mt-1 text-[12px] font-semibold text-[#6f8785]">{new Date().toLocaleDateString('ko-KR')} · admin · 개인정보 접근 기록 대상</p>
                {refreshStatus && <p className="mt-1 text-[12px] font-bold text-[#0f7d82]">{refreshStatus}</p>}
              </div>
              <div className="flex gap-2">
                <button
                  onClick={() => loadDashboard(true)}
                  disabled={isRefreshing}
                  className="flex h-10 items-center gap-1 rounded-[8px] border border-[#dce9e6] bg-white px-3 text-[12px] font-black text-[#0f7d82] disabled:opacity-60"
                >
                  <RotateCw className={`h-4 w-4 ${isRefreshing ? 'animate-spin' : ''}`} />
                  {isRefreshing ? '새로고침 중' : '새로고침'}
                </button>
                <button onClick={onBack} className="flex h-10 items-center gap-1 rounded-[8px] bg-[#152329] px-3 text-[12px] font-black text-white">
                  <LogOut className="h-4 w-4" />
                  로그아웃
                </button>
              </div>
            </div>
          </header>

          {activeTab === 'dashboard' && (
            <div className="space-y-3">
              <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
                <StatCard label="전체 사용자" value={String(rows.patients.length)} sub="가입자/검증 대상 기준" icon={Users} />
                <StatCard label="이번 달 분석" value={String(completedCount)} sub={`업로드 ${uploadedCount}건 중 완료`} icon={BarChart3} />
                <StatCard label="주의 필요" value={String(highRiskCount)} sub="AI 참고 결과 기준 위험 신호" icon={AlertTriangle} />
                <StatCard label="음성 품질 부족" value={String(poorAudioCount)} sub={`재분석 필요 ${reanalysisCount}건`} icon={Mic} />
              </div>
              <div className="grid gap-3 xl:grid-cols-[1.2fr_0.8fr]">
                <Panel title="최근 분석 결과" icon={ClipboardList}>
                  <div className="overflow-x-auto">
                    <table className="w-full min-w-[620px] text-left text-[12px]">
                      <thead className="text-[#6f8785]">
                        <tr className="border-b border-[#e4eeeb]">
                          <th className="py-2 font-black">대상자</th>
                          <th className="py-2 font-black">AI 참고 결과</th>
                          <th className="py-2 font-black">참고값</th>
                          <th className="py-2 font-black">생성일</th>
                          <th className="py-2 font-black">조치</th>
                        </tr>
                      </thead>
                      <tbody>
                        {rows.results.map(item => (
                          <tr key={item.id} className="border-b border-[#eef5f2] last:border-0">
                            <td className="py-3 font-black">{displaySubject(item.patientName)}</td>
                            <td className="py-3"><RiskBadge value={item.result} /></td>
                            <td className="py-3 font-black text-[#0f7d82]">{item.referenceScore}</td>
                            <td className="py-3 text-[#6f8785]">{formatDateTime(item.createdAt)}</td>
                            <td className="py-3">
                              <button
                                onClick={() => {
                                  setSelectedResultId(item.id)
                                  setActiveTab('detail')
                                }}
                                className="rounded-[8px] bg-[#e9f7f4] px-3 py-2 text-[11px] font-black text-[#0f7d82]"
                              >
                                상세
                              </button>
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </Panel>
                <Panel title="시스템 상태" icon={Server}>
                  <div className="space-y-3">
                    <div className="rounded-[8px] bg-[#152329] p-4 text-white">
                      <div className="flex justify-between text-[12px] font-bold text-white/70">
                        <span>활성 AI 서버 노드</span>
                        <span>{number(system.active_ai_nodes)}/{number(system.max_ai_nodes)}</span>
                      </div>
                      <div className="mt-2 h-2 rounded-full bg-white/10">
                        <div className="h-full rounded-full bg-[#7bd88f]" style={{ width: `${nodeRatio * 100}%` }} />
                      </div>
                    </div>
                    {alerts.length === 0 ? <EmptyState text="운영 알림 없음" /> : alerts.map((alert, index) => (
                      <p key={index} className="rounded-[8px] bg-amber-50 px-3 py-3 text-[12px] font-bold text-amber-700">{String(alert.message)}</p>
                    ))}
                  </div>
                </Panel>
              </div>
            </div>
          )}

          {activeTab === 'users' && (
            <Panel title="사용자 관리" icon={Users} action={(
              <label className="flex h-10 min-w-[180px] items-center gap-2 rounded-[8px] border border-[#dce9e6] px-3">
                <Search className="h-4 w-4 text-[#0f7d82]" />
                <input value={query} onChange={event => setQuery(event.target.value)} className="w-full bg-transparent text-[12px] font-semibold outline-none" placeholder="검색" />
              </label>
            )}>
              <div className="overflow-x-auto">
                <table className="w-full min-w-[720px] text-left text-[12px]">
                  <thead className="text-[#6f8785]">
                    <tr className="border-b border-[#e4eeeb]">
                      <th className="py-2">가입자</th>
                      <th className="py-2">검증 대상</th>
                      <th className="py-2">유형</th>
                      <th className="py-2">연령대</th>
                      <th className="py-2">최근 분석</th>
                      <th className="py-2">결과</th>
                      <th className="py-2">상태</th>
                    </tr>
                  </thead>
                  <tbody>
                    {filteredPatients.map(item => (
                      <tr key={item.id} className="border-b border-[#eef5f2] last:border-0">
                        <td className="py-3 font-black">{displaySubject(item.accountName)}</td>
                        <td className="py-3 font-black">{displaySubject(item.subjectName)}</td>
                        <td className="py-3">{item.subjectType}</td>
                        <td className="py-3">{item.ageGroup}</td>
                        <td className="py-3 text-[#6f8785]">{formatDateTime(item.latestDate)}</td>
                        <td className="py-3"><RiskBadge value={item.latestResult} /></td>
                        <td className="py-3 font-black text-[#0f7d82]">{item.status}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </Panel>
          )}

          {activeTab === 'audio' && (
            <Panel title="음성 데이터 관리" icon={Mic}>
              {operationNotice && (
                <p className="mb-3 rounded-[8px] bg-[#f7fbfa] px-4 py-3 text-[13px] font-bold leading-5 text-[#0f7d82]">
                  {operationNotice}
                </p>
              )}
              {rows.audioRows.length === 0 ? (
                <EmptyState text="등록된 음성 데이터가 없습니다. 새 검증을 시작하면 여기에 음성 파일 상태가 표시됩니다." />
              ) : (
                <div className="grid gap-3 md:grid-cols-3">
                  {rows.audioRows.map(item => (
                  <div key={item.id} className="rounded-[8px] border border-[#e4eeeb] bg-[#f7fbfa] p-4">
                    <div className="flex items-start justify-between gap-3">
                      <div>
                        <p className="text-[13px] font-black">{displaySubject(item.patientName)}</p>
                        <p className="mt-1 text-[11px] font-semibold text-[#6f8785]">{formatDateTime(item.uploadedAt)} · {item.duration}</p>
                      </div>
                      <QualityBadge value={item.quality} />
                    </div>
                    <div className="mt-3 grid grid-cols-2 gap-2 text-[11px] font-bold">
                      <p className="rounded-[8px] bg-white px-2 py-2">분리 {item.separationStatus}</p>
                      <p className="rounded-[8px] bg-white px-2 py-2">분석 {item.analysisStatus}</p>
                    </div>
                    <div className="mt-3 flex gap-2">
                      <button onClick={() => showPendingOperation('reanalysis')} className="flex h-9 flex-1 items-center justify-center gap-1 rounded-[8px] bg-[#0f7d82] text-[11px] font-black text-white">
                        <RotateCw className="h-3.5 w-3.5" />
                        재분석
                      </button>
                      <button onClick={() => showPendingOperation('notification')} className="flex h-9 flex-1 items-center justify-center gap-1 rounded-[8px] border border-[#dce9e6] bg-white text-[11px] font-black text-[#0f7d82]">
                        <Bell className="h-3.5 w-3.5" />
                        알림
                      </button>
                    </div>
                  </div>
                  ))}
                </div>
              )}
            </Panel>
          )}

          {activeTab === 'results' && (
            <Panel title="분석 결과 관리" icon={ClipboardList}>
              {operationNotice && (
                <p className="mb-3 rounded-[8px] bg-[#f7fbfa] px-4 py-3 text-[13px] font-bold leading-5 text-[#0f7d82]">
                  {operationNotice}
                </p>
              )}
              {rows.results.length === 0 ? (
                <EmptyState text="등록된 분석 결과가 없습니다. 새 검증을 완료하면 여기에 결과가 표시됩니다." />
              ) : (
                <div className="grid gap-3 md:grid-cols-3">
                  {rows.results.map(item => (
                  <div key={item.id} className="rounded-[8px] border border-[#e4eeeb] bg-white p-4">
                    <div className="flex items-center justify-between gap-3">
                      <p className="text-[13px] font-black">{displaySubject(item.patientName)}</p>
                      <RiskBadge value={item.result} />
                    </div>
                    <p className="mt-3 text-[28px] font-black text-[#0f7d82]">{item.referenceScore}</p>
                    <p className="mt-1 text-[11px] font-semibold text-[#6f8785]">참고값 · 신뢰도 {Math.round(item.confidence * 100)}% · 음질 {item.qualityScore}점</p>
                    <p className="mt-3 min-h-[42px] text-[12px] font-semibold leading-5 text-[#426260]">{item.recommendation}</p>
                    <div className="mt-3 flex gap-2">
                      <button
                        onClick={() => {
                          setSelectedResultId(item.id)
                          setActiveTab('detail')
                        }}
                        className="flex h-9 flex-1 items-center justify-center gap-1 rounded-[8px] bg-[#0f7d82] text-[11px] font-black text-white"
                      >
                        <FileText className="h-3.5 w-3.5" />
                        리포트
                      </button>
                      <button onClick={() => showPendingOperation('memo')} className="flex h-9 flex-1 items-center justify-center gap-1 rounded-[8px] border border-[#dce9e6] text-[11px] font-black text-[#0f7d82]">
                        <MessageSquare className="h-3.5 w-3.5" />
                        메모
                      </button>
                    </div>
                  </div>
                  ))}
                </div>
              )}
            </Panel>
          )}

          {activeTab === 'detail' && selectedResult && (
            <div className="space-y-3">
              <Panel
                title="분석 상세"
                icon={FileText}
                action={(
                  <button
                    onClick={() => setActiveTab('results')}
                    className="rounded-[8px] border border-[#dce9e6] bg-white px-3 py-2 text-[11px] font-black text-[#0f7d82]"
                  >
                    결과 목록
                  </button>
                )}
              >
                <div className="grid gap-3 lg:grid-cols-[0.8fr_1.2fr]">
                  <div className="rounded-[8px] bg-[#f7fbfa] p-4">
                    <p className="text-[12px] font-bold text-[#6f8785]">대상자 정보</p>
                    <p className="mt-2 text-[20px] font-black">{displaySubject(selectedResult.patientName)}</p>
                    <div className="mt-4 space-y-2 text-[12px] font-semibold text-[#426260]">
                      <p>분석 ID: {selectedResult.id.slice(0, 12)}</p>
                      <p>생성일: {formatDateTime(selectedResult.createdAt)}</p>
                      <p>음성 품질: {selectedResult.qualityScore}점</p>
                    </div>
                  </div>
                  <div className="rounded-[8px] bg-white p-4 ring-1 ring-[#e4eeeb]">
                    <div className="flex items-center justify-between gap-3">
                      <p className="text-[12px] font-bold text-[#6f8785]">AI 분석 참고 결과 · 참고값</p>
                      <RiskBadge value={selectedResult.result} />
                    </div>
                    <p className="mt-2 text-[30px] font-black text-[#0f7d82]">{selectedResult.referenceScore}</p>
                    <div className="mt-4 grid gap-2 sm:grid-cols-3">
                      {[
                        ['발화 속도', '보통'],
                        ['무음 비율', selectedResult.result === 'Normal' ? '낮음' : '증가'],
                        ['반복 표현', selectedResult.result === 'Normal' ? '낮음' : '주의'],
                      ].map(([label, value]) => (
                        <div key={label} className="rounded-[8px] bg-[#f7fbfa] px-3 py-3">
                          <p className="text-[10px] font-bold text-[#6f8785]">{label}</p>
                          <p className="mt-1 text-[13px] font-black">{value}</p>
                        </div>
                      ))}
                    </div>
                  </div>
                </div>
              </Panel>
              <Panel title="권장 조치 및 관리자 메모" icon={Stethoscope}>
                <div className="grid gap-3 lg:grid-cols-2">
                  <div className="rounded-[8px] bg-[#f7fbfa] p-4">
                    <p className="text-[13px] font-black">권장 조치</p>
                    <p className="mt-2 text-[12px] font-semibold leading-5 text-[#426260]">{selectedResult.recommendation}</p>
                  </div>
                  <textarea
                    className="min-h-[120px] rounded-[8px] border border-[#dce9e6] p-3 text-[12px] font-semibold outline-none focus:border-[#0f7d82] focus:ring-2 focus:ring-[#d7efea]"
                    placeholder="관리자 메모를 입력하세요. 저장 API 연동 전까지는 화면 기록용입니다."
                  />
                </div>
                <p className="mt-3 rounded-[8px] bg-red-50 px-3 py-3 text-[12px] font-bold leading-5 text-red-700">
                  본 결과는 음성 기반 AI 분석에 따른 참고 정보이며, 의학적 진단이 아닙니다. 정확한 진단은 전문 의료기관의 검사를 통해 확인해야 합니다.
                </p>
              </Panel>
            </div>
          )}

          {activeTab === 'models' && (
            <Panel title="AI 모델 관리" icon={GitBranch}>
              <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-4">
                {[
                  ['모델 상태', modelLayer.status || 'unknown'],
                  ['모델 소스', modelLayer.model_source || '-'],
                  ['학습 지표(참고)', modelAccuracy],
                  ['추론 장치', modelLayer.runtime?.inference_device || '-'],
                ].map(([label, value]) => (
                  <div key={label} className="rounded-[8px] bg-[#f7fbfa] p-4">
                    <p className="text-[11px] font-bold text-[#6f8785]">{label}</p>
                    <p className="mt-2 break-words text-[15px] font-black">{String(value)}</p>
                  </div>
                ))}
              </div>
              <div className="mt-3 rounded-[8px] border border-[#e4eeeb] p-4">
                <p className="text-[13px] font-black">학습 클래스</p>
                <p className="mt-2 text-[12px] font-semibold text-[#426260]">{Array.isArray(modelLayer.classes) && modelLayer.classes.length > 0 ? modelLayer.classes.join(' / ') : 'Normal / MCI 의심 / AD 의심'}</p>
              </div>
              <p className="mt-3 rounded-[8px] bg-amber-50 px-4 py-3 text-[12px] font-bold leading-5 text-amber-800">
                학습 지표는 모델 학습 당시 테스트 데이터 기준의 참고값입니다. 개별 가입자 분석의 실제 정확도는 전문기관 검사 결과 같은 정답 라벨이 있어야 산정할 수 있습니다.
              </p>
            </Panel>
          )}

          {activeTab === 'training' && (
            <Panel title="학습용 장기 보관" icon={Database}>
              <p className="mb-3 rounded-[8px] bg-[#f7fbfa] px-4 py-3 text-[12px] font-bold leading-5 text-[#426260]">
                AI 모델 개선 및 연구 활용에 선택 동의한 데이터만 별도 기준으로 관리합니다. 기본 서비스용 음성 보관 기간과 분리해서 확인해야 합니다.
              </p>
              <div className="grid gap-2 sm:grid-cols-2 xl:grid-cols-4">
                {[
                  ['선택 동의 상태', modelTraining.enabled ? '사용 중' : '미사용', '동의 화면에서 학습 활용 선택 동의를 받을 수 있는 상태입니다.'],
                  ['장기 보관 기간', `${number(modelTraining.retention_days || 1095)}일`, '선택 동의 데이터의 학습 활용 목적 최대 보관 기간입니다.'],
                  ['학습 동의 건수', number(modelTraining.consent_count), 'AI 모델 개선 및 연구 활용에 동의한 동의 기록 수입니다.'],
                  ['학습용 원본 보관', number(modelTraining.audio_retained_count), '선택 동의와 연결되어 아직 원본이 남아 있는 음성 파일 건수입니다.'],
                ].map(([label, value, description]) => (
                  <div key={String(label)} className="rounded-[8px] bg-[#f7fbfa] px-3 py-3">
                    <p className="text-[10px] font-bold text-[#7d9593]">{String(label)}</p>
                    <p className="mt-1 text-[18px] font-black text-[#183f40]">{String(value)}</p>
                    <p className="mt-2 text-[11px] font-semibold leading-4 text-[#6f8785]">{String(description)}</p>
                  </div>
                ))}
              </div>
              <p className="mt-3 rounded-[8px] bg-amber-50 px-4 py-3 text-[12px] font-bold leading-5 text-amber-800">
                학습용 장기 보관은 선택 동의가 있는 데이터에만 적용해야 합니다. 동의하지 않은 사용자의 원본 음성은 기본 음성 보관 정책에 따라 삭제 대상입니다.
              </p>
              <div className="mt-3 grid gap-2 lg:grid-cols-2">
                <div className="rounded-[8px] bg-[#f7fbfa] px-4 py-3">
                  <p className="text-[11px] font-bold text-[#7d9593]">원본 통화 파일 저장 위치</p>
                  <p className="mt-1 break-all text-[13px] font-black text-[#183f40]">{String(modelTraining.upload_dir || '-')}</p>
                </div>
                <div className="rounded-[8px] bg-[#f7fbfa] px-4 py-3">
                  <p className="text-[11px] font-bold text-[#7d9593]">자녀/본인 샘플 저장 위치</p>
                  <p className="mt-1 break-all text-[13px] font-black text-[#183f40]">{String(modelTraining.voice_samples_dir || '-')}</p>
                </div>
              </div>
              <div className="mt-3 overflow-x-auto rounded-[8px] border border-[#e4eeeb]">
                <table className="w-full min-w-[860px] text-left text-[12px]">
                  <thead className="bg-[#f7fbfa] text-[#6f8785]">
                    <tr>
                      <th className="px-3 py-2 font-black">가입자</th>
                      <th className="px-3 py-2 font-black">검증 대상</th>
                      <th className="px-3 py-2 font-black">유형</th>
                      <th className="px-3 py-2 font-black">동의일</th>
                      <th className="px-3 py-2 font-black">원본 상태</th>
                      <th className="px-3 py-2 font-black">파일명</th>
                      <th className="px-3 py-2 font-black">저장 경로</th>
                    </tr>
                  </thead>
                  <tbody>
                    {trainingConsents.length === 0 ? (
                      <tr>
                        <td colSpan={7} className="px-3 py-5 text-center font-bold text-[#6f8785]">
                          {number(modelTraining.consent_count) > 0
                            ? '학습 동의 건수는 있으나 상세 목록을 불러오지 못했습니다. 백엔드 재시작 후 새로고침해 주세요.'
                            : '학습 활용 선택 동의 데이터가 없습니다.'}
                        </td>
                      </tr>
                    ) : trainingConsents.map(item => (
                      <tr key={String(item.consent_id)} className="border-t border-[#eef5f2]">
                        <td className="px-3 py-3 font-black">{displaySubject(String(item.login_id || item.account_name || '사용자'))}</td>
                        <td className="px-3 py-3 font-black">{displaySubject(String(item.subject_name || '-'))}</td>
                        <td className="px-3 py-3">{subjectTypeLabel(item.subject_type, item.subject_relation)}</td>
                        <td className="px-3 py-3 text-[#6f8785]">{formatDateTime(item.agreed_at)}</td>
                        <td className="px-3 py-3 font-black text-[#0f7d82]">
                          {item.raw_deleted_at
                            ? '삭제됨'
                            : item.audio_status === 'training_retained'
                              ? '장기 보관 중'
                              : item.audio_file_id ? '보관 중' : '업로드 없음'}
                        </td>
                        <td className="px-3 py-3">{String(item.original_filename || '-')}</td>
                        <td className="max-w-[300px] break-all px-3 py-3 text-[#6f8785]">{String(item.storage_path || item.wav_path || '-')}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </Panel>
          )}

          {activeTab === 'logs' && (
            <Panel title="관리자 로그" icon={ShieldCheck}>
              <div className="space-y-2">
                {rows.logs.map(item => (
                  <div key={item.id} className="flex flex-col gap-1 rounded-[8px] bg-[#f7fbfa] px-3 py-3 sm:flex-row sm:items-center sm:justify-between">
                    <div>
                      <p className="text-[12px] font-black">{item.action}</p>
                      <p className="mt-1 text-[11px] font-semibold text-[#6f8785]">{item.actor} · {item.target}</p>
                    </div>
                    <p className={`text-[11px] font-black ${item.level === 'warning' ? 'text-amber-700' : 'text-[#0f7d82]'}`}>{formatDateTime(item.createdAt)}</p>
                  </div>
                ))}
              </div>
            </Panel>
          )}

          {activeTab === 'settings' && (
            <div className="space-y-3">
              <Panel title="보관/삭제 정책" icon={SlidersHorizontal} action={(
                <button onClick={runCleanup} className="flex h-9 items-center gap-1 rounded-[8px] bg-[#0f7d82] px-3 text-[11px] font-black text-white">
                  <Trash2 className="h-3.5 w-3.5" />
                  정리 실행
                </button>
              )}>
                <p className="mb-3 rounded-[8px] bg-[#f7fbfa] px-4 py-3 text-[12px] font-bold leading-5 text-[#426260]">
                  개인정보와 음성 원본을 오래 보관하지 않도록 운영 기준을 확인하는 영역입니다. 정리 실행은 만료된 데이터만 정책에 따라 삭제합니다.
                </p>
                <div className="grid gap-2 sm:grid-cols-2 xl:grid-cols-4">
                  {[
                    ['결과 보관', `${number(retention.result_retention_days)}일`, 'AI 참고 결과, 참고값, 권장 조치 등 리포트 데이터를 보관하는 기간입니다.'],
                    ['음성 보관', `${number(retention.audio_retention_days)}일`, '가입자가 업로드한 통화 녹음 원본 파일을 서버에 보관하는 기간입니다.'],
                    ['샘플 보관', `${number(retention.voice_sample_retention_days)}일`, '자녀 음성 등록 또는 본인 음성 등록 샘플 파일을 보관하는 기간입니다.'],
                    ['샘플 자동삭제', retention.delete_voice_sample_after_analysis ? 'ON' : 'OFF', '분석이 끝난 뒤 화자 구분용 샘플 음성을 자동 삭제할지 여부입니다.'],
                  ].map(([label, value, description]) => (
                    <div key={String(label)} className="rounded-[8px] bg-[#f7fbfa] px-3 py-3">
                      <p className="text-[10px] font-bold text-[#7d9593]">{String(label)}</p>
                      <p className="mt-1 text-[14px] font-black text-[#183f40]">{String(value)}</p>
                      <p className="mt-2 text-[11px] font-semibold leading-4 text-[#6f8785]">{String(description)}</p>
                    </div>
                  ))}
                </div>
                {cleanupStatus && <p className="mt-3 rounded-[8px] bg-[#f7fbfa] px-3 py-2 text-[12px] font-bold text-[#0f7d82]">{cleanupStatus}</p>}
              </Panel>
              <Panel title="데이터 저장 현황" icon={Database}>
                <p className="mb-3 rounded-[8px] bg-[#f7fbfa] px-4 py-3 text-[12px] font-bold leading-5 text-[#426260]">
                  현재 서버에 남아 있는 데이터 수량입니다. 결과와 특징값은 서비스 이력 확인에 쓰이고, 원본 음성은 최소 기간만 보관하는 것이 원칙입니다.
                </p>
                <div className="grid gap-2 sm:grid-cols-2 xl:grid-cols-4">
                  {[
                    ['특징/결과 저장', number(storage.feature_result_count), '분석 결과와 추출 특징값이 저장된 건수입니다.'],
                    ['원본 보관', number(storage.raw_audio_retained_count), '아직 삭제되지 않은 원본 음성 파일 건수입니다.'],
                    ['삭제 처리', number(storage.audio_deleted_count) + number(storage.voice_samples_deleted_count), '정책에 따라 삭제 표시 또는 삭제 처리된 음성 데이터 건수입니다.'],
                    ['메모리 작업', number(operations.memory_jobs), '서버 메모리에 남아 있는 임시 분석 작업 건수입니다.'],
                  ].map(([label, value, description]) => (
                    <div key={String(label)} className="rounded-[8px] bg-[#f7fbfa] px-3 py-3">
                      <p className="text-[10px] font-bold text-[#7d9593]">{String(label)}</p>
                      <p className="mt-1 text-[18px] font-black text-[#183f40]">{String(value)}</p>
                      <p className="mt-2 text-[11px] font-semibold leading-4 text-[#6f8785]">{String(description)}</p>
                    </div>
                  ))}
                </div>
              </Panel>
            </div>
          )}
        </main>
      </div>
    </div>
  )
}
