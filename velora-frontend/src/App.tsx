import { useEffect, useRef, useState } from 'react'
import { PhoneCall, ShieldCheck, UserPlus } from 'lucide-react'
import { Button } from '@/components/ui/button'
import SignupPage from './pages/SignupPage'
import LoginPage from './pages/LoginPage'
import PasswordResetPage from './pages/PasswordResetPage'
import ServiceMenuPage from './pages/ServiceMenuPage'
import ConsentPage from './pages/ConsentPage'
import SubjectProfilePage from './pages/SubjectProfilePage'
import ChildVoiceSamplePage from './pages/ChildVoiceSamplePage'
import UploadPage from './pages/UploadPage'
import SelfVoicePage from './pages/SelfVoicePage'
import AnalyzingPage from './pages/AnalyzingPage'
import ResultsPage from './pages/ResultsPage'
import ReliabilityPage from './pages/ReliabilityPage'
import FollowupPage from './pages/FollowupPage'
import AdminPage from './pages/AdminPage'
import HistoryPage from './pages/HistoryPage'
import AdminLoginPage from './pages/AdminLoginPage'
import RecordingGuidePage from './pages/RecordingGuidePage'
import {
  clearAdminSession,
  deleteResultHistoryItem,
  getResultsHistory,
  hasAdminSession,
  hasUserSession,
  confirmPasswordReset,
  loginAccount,
  loginAdmin,
  requestPasswordReset,
  saveConsentSubject,
  signupAccount,
} from './lib/api'

export type AppStep =
  | 'home'
  | 'signup'
  | 'login'
  | 'passwordReset'
  | 'service'
  | 'subjectProfile'
  | 'consent'
  | 'childVoice'
  | 'upload'
  | 'selfVoice'
  | 'analyzing'
  | 'results'
  | 'reliability'
  | 'followup'
  | 'history'
  | 'recordingGuide'
  | 'adminLogin'
  | 'admin'

export type VerificationType = 'parent_call' | 'self_voice'

export interface AppState {
  consentToken: string
  email: string
  displayName: string
  signupPurpose: string
  ageGroup: string
  subjectDisplayName: string
  subjectAgeGroup: string
  subjectGender: string
  subjectRelation: string
  fileId: string
  voiceSampleId: string
  voiceSampleDurationSeconds: number
  verificationType: VerificationType
  analysisId: string
  analysisResult: Record<string, unknown> | null
  resultsData: Record<string, unknown> | null
  loginPassword: string
  loginError: string
  signupPassword: string
  signupPasswordConfirm: string
  signupError: string
  resetToken: string
  resetPassword: string
  resetPasswordConfirm: string
  resetMessage: string
  resetError: string
  adminId: string
  adminPassword: string
  adminError: string
}

const initialState: AppState = {
  consentToken: '',
  email: '',
  displayName: '',
  signupPurpose: '',
  ageGroup: '',
  subjectDisplayName: '',
  subjectAgeGroup: '',
  subjectGender: '',
  subjectRelation: '',
  fileId: '',
  voiceSampleId: '',
  voiceSampleDurationSeconds: 0,
  verificationType: 'parent_call',
  analysisId: '',
  analysisResult: null,
  resultsData: null,
  loginPassword: '',
  loginError: '',
  signupPassword: '',
  signupPasswordConfirm: '',
  signupError: '',
  resetToken: '',
  resetPassword: '',
  resetPasswordConfirm: '',
  resetMessage: '',
  resetError: '',
  adminId: '',
  adminPassword: '',
  adminError: '',
}

const appSessionKey = 'sorimemo_app_session'
const activeConsentTokenKey = 'sorimemo_active_consent_token'
const pendingAnalysisKey = 'sorimemo_pending_analysis'
const pendingAnalysisTtlMs = 15 * 60 * 1000
const passwordPolicyMessage = '비밀번호는 영문자와 숫자를 포함해 8자 이상 입력해 주세요.'

const isValidPassword = (password: string) => (
  password.length >= 8 && /[A-Za-z]/.test(password) && /\d/.test(password)
)

const subjectRelationDisplayName = (relation: string) => ({
  self: '본인',
  mother: '어머니',
  father: '아버지',
  spouse: '배우자',
}[relation] || '')

interface PersistedAppSession {
  step: AppStep
  historyBackStep: AppStep
  resultsBackStep: AppStep
  consentBackStep: AppStep
  serviceBackStep?: AppStep
  state: Partial<AppState>
}

interface PendingAnalysisResume {
  consentToken: string
  fileId: string
  voiceSampleId: string
  voiceSampleDurationSeconds: number
  verificationType: VerificationType
  expiresAt: number
}

const loadAppSession = (): PersistedAppSession | null => {
  try {
    return JSON.parse(sessionStorage.getItem(appSessionKey) || 'null') as PersistedAppSession | null
  } catch {
    return null
  }
}

const getActiveConsentToken = () => {
  try {
    return sessionStorage.getItem(activeConsentTokenKey) || ''
  } catch {
    return ''
  }
}

const setActiveConsentToken = (token: string) => {
  try {
    if (token) {
      sessionStorage.setItem(activeConsentTokenKey, token)
    } else {
      sessionStorage.removeItem(activeConsentTokenKey)
    }
  } catch {
    // Consent token persistence is best-effort only.
  }
}

const persistableState = (state: AppState): Partial<AppState> => ({
  consentToken: state.consentToken,
  email: state.email,
  ageGroup: state.ageGroup,
  fileId: state.fileId,
  voiceSampleId: state.voiceSampleId,
  voiceSampleDurationSeconds: state.voiceSampleDurationSeconds,
  verificationType: state.verificationType,
  analysisId: state.analysisId,
  analysisResult: state.analysisResult,
  resultsData: state.resultsData,
})

const persistAppSession = (
  step: AppStep,
  historyBackStep: AppStep,
  resultsBackStep: AppStep,
  consentBackStep: AppStep,
  serviceBackStep: AppStep,
  state: AppState,
) => {
  try {
    sessionStorage.setItem(appSessionKey, JSON.stringify({
      step,
      historyBackStep,
      resultsBackStep,
      consentBackStep,
      serviceBackStep,
      state: persistableState(state),
    }))
  } catch {
    // Session persistence is best-effort only.
  }
}

const savePendingAnalysisResume = (state: AppState) => {
  if (!state.fileId) return
  try {
    const payload: PendingAnalysisResume = {
      consentToken: state.consentToken,
      fileId: state.fileId,
      voiceSampleId: state.voiceSampleId,
      voiceSampleDurationSeconds: Number(state.voiceSampleDurationSeconds || 0),
      verificationType: state.verificationType,
      expiresAt: Date.now() + pendingAnalysisTtlMs,
    }
    localStorage.setItem(pendingAnalysisKey, JSON.stringify(payload))
  } catch {
    // Analysis resume state is best-effort only.
  }
}

const loadPendingAnalysisResume = (): PendingAnalysisResume | null => {
  try {
    const saved = JSON.parse(localStorage.getItem(pendingAnalysisKey) || 'null') as PendingAnalysisResume | null
    if (!saved?.fileId || !saved.expiresAt || saved.expiresAt <= Date.now()) {
      localStorage.removeItem(pendingAnalysisKey)
      return null
    }
    return saved
  } catch {
    return null
  }
}

const clearPendingAnalysisResume = () => {
  try {
    localStorage.removeItem(pendingAnalysisKey)
  } catch {
    // Analysis resume state is best-effort only.
  }
}

const historyKeyFor = (email: string) => `sorimemo_history:${email.trim().toLowerCase()}`
const childVoiceUploadKey = (consentToken: string) => `sorimemo_child_voice_upload:${consentToken}`
const childVoiceCompleteKey = (consentToken: string) => `sorimemo_child_voice_complete:${consentToken}`
const parentUploadResumeKey = (consentToken: string) => `sorimemo_parent_upload_resume:${consentToken}`
const parentAudioUploadStateKey = (consentToken: string) => `sorimemo_parent_audio_upload:${consentToken}`
const parentAudioUploadErrorKey = (consentToken: string) => `sorimemo_parent_audio_upload_error:${consentToken}`
const selfVoiceUploadKey = (consentToken: string) => `sorimemo_self_voice_upload:${consentToken}`
const selfVoiceAudioUploadStateKey = (consentToken: string) => `sorimemo_self_voice_audio_upload:${consentToken}`
const selfVoiceAudioUploadPendingKey = (consentToken: string) => `sorimemo_self_voice_audio_upload_pending:${consentToken}`
const analysisJobKey = (fileId: string) => `sorimemo_analysis_job:${fileId}`
const userProtectedSteps = new Set<AppStep>([
  'service',
  'consent',
  'childVoice',
  'upload',
  'selfVoice',
  'analyzing',
  'results',
  'reliability',
  'followup',
  'history',
  'recordingGuide',
])

const getChildVoiceCompleteResume = (session: PersistedAppSession | null) => {
  const consentToken = session?.state?.consentToken
  if (!consentToken) return null
  try {
    const saved = JSON.parse(sessionStorage.getItem(childVoiceCompleteKey(consentToken)) || 'null') as {
      sampleId?: string
      durationSeconds?: number
      expiresAt?: number
    } | null
    if (!saved?.sampleId || !saved.expiresAt || saved.expiresAt <= Date.now()) return null
    return saved
  } catch {
    return null
  }
}

const hasChildVoiceUploadResume = (session: PersistedAppSession | null) => {
  const consentToken = session?.state?.consentToken
  if (!consentToken || session?.step !== 'childVoice') return false
  try {
    const saved = JSON.parse(sessionStorage.getItem(childVoiceUploadKey(consentToken)) || 'null') as {
      expiresAt?: number
    } | null
    return Boolean(saved?.expiresAt && saved.expiresAt > Date.now())
  } catch {
    return false
  }
}

const hasParentUploadResume = (session: PersistedAppSession | null) => {
  const consentToken = session?.state?.consentToken
  if (!consentToken) return false
  try {
    const saved = JSON.parse(sessionStorage.getItem(parentUploadResumeKey(consentToken)) || 'null') as {
      expiresAt?: number
    } | null
    return Boolean(saved?.expiresAt && saved.expiresAt > Date.now())
  } catch {
    return false
  }
}

const hasSelfVoiceUploadResume = (session: PersistedAppSession | null) => {
  const consentToken = session?.state?.consentToken
  if (!consentToken || session?.step !== 'selfVoice') return false
  try {
    const saved = JSON.parse(sessionStorage.getItem(selfVoiceUploadKey(consentToken)) || 'null') as {
      expiresAt?: number
    } | null
    return Boolean(saved?.expiresAt && saved.expiresAt > Date.now())
  } catch {
    return false
  }
}

const hasAnalysisJobResume = (session: PersistedAppSession | null) => {
  const fileId = session?.state?.fileId
  if (!fileId || session?.step !== 'analyzing') return false
  try {
    const saved = JSON.parse(sessionStorage.getItem(analysisJobKey(fileId)) || 'null') as {
      jobId?: string
      expiresAt?: number
    } | null
    return Boolean(saved?.jobId && saved.expiresAt && saved.expiresAt > Date.now())
  } catch {
    return false
  }
}

const clearParentUploadTransientState = (consentToken: string) => {
  if (!consentToken) return
  try {
    sessionStorage.removeItem(parentUploadResumeKey(consentToken))
    sessionStorage.removeItem(parentAudioUploadStateKey(consentToken))
    sessionStorage.removeItem(parentAudioUploadErrorKey(consentToken))
  } catch {
    // Upload state cleanup is best-effort only.
  }
}

const clearSelfVoiceUploadTransientState = (consentToken: string) => {
  if (!consentToken) return
  try {
    sessionStorage.removeItem(selfVoiceUploadKey(consentToken))
    sessionStorage.removeItem(selfVoiceAudioUploadStateKey(consentToken))
    sessionStorage.removeItem(selfVoiceAudioUploadPendingKey(consentToken))
  } catch {
    // Upload state cleanup is best-effort only.
  }
}

const stepFromPath = (path: string, restoredStep?: AppStep): AppStep => {
  if (path === '/admin/login') return 'adminLogin'
  if (path === '/admin' || path.startsWith('/admin/')) {
    return hasAdminSession() ? 'admin' : 'adminLogin'
  }
  if (restoredStep === 'adminLogin' || restoredStep === 'admin') return 'login'
  return 'login'
}

const initialStepFromPath = (path: string, session: PersistedAppSession | null): AppStep => {
  const restoredStep = session?.step
  if (path === '/admin/login') return 'adminLogin'
  if (path === '/admin' || path.startsWith('/admin/')) {
    return hasAdminSession() ? 'admin' : 'adminLogin'
  }
  if (!hasUserSession()) return stepFromPath(path, restoredStep)
  if (loadPendingAnalysisResume()) return 'analyzing'
  if (hasSelfVoiceUploadResume(session)) return 'selfVoice'
  if (hasParentUploadResume(session)) return 'upload'
  if (hasChildVoiceUploadResume(session)) return 'childVoice'
  if (getChildVoiceCompleteResume(session)) return 'upload'
  if (hasAnalysisJobResume(session)) return 'analyzing'
  if (
    restoredStep &&
    restoredStep !== 'home' &&
    restoredStep !== 'signup' &&
    restoredStep !== 'login' &&
    restoredStep !== 'passwordReset' &&
    restoredStep !== 'adminLogin' &&
    restoredStep !== 'admin' &&
    session?.state?.email
  ) {
    return restoredStep
  }
  return stepFromPath(path, restoredStep)
}

const pathForStep = (step: AppStep) => {
  if (step === 'adminLogin') return '/admin/login'
  if (step === 'admin') return '/admin'
  return '/'
}

const restoredStateForInitialLoad = (session: PersistedAppSession | null): Partial<AppState> => {
  const activeConsentToken = getActiveConsentToken()
  const pendingAnalysis = loadPendingAnalysisResume()
  if (pendingAnalysis) {
    return {
      consentToken: pendingAnalysis.consentToken || activeConsentToken,
      email: session?.state?.email || '',
      ageGroup: session?.state?.ageGroup || '',
      fileId: pendingAnalysis.fileId,
      voiceSampleId: pendingAnalysis.voiceSampleId || '',
      voiceSampleDurationSeconds: Number(pendingAnalysis.voiceSampleDurationSeconds || 0),
      verificationType: pendingAnalysis.verificationType,
    }
  }
  if (!session) return {}
  if (session.step === 'adminLogin' || session.step === 'admin') {
    return {
      adminId: session.state.adminId || '',
    }
  }
  if (session.step === 'analyzing') {
    return {
      consentToken: session.state.consentToken || activeConsentToken,
      email: session.state.email || '',
      ageGroup: session.state.ageGroup || '',
      fileId: session.state.fileId || '',
      voiceSampleId: session.state.voiceSampleId || '',
      voiceSampleDurationSeconds: Number(session.state.voiceSampleDurationSeconds || 0),
      verificationType: session.state.verificationType || (session.state.voiceSampleId ? 'parent_call' : 'self_voice'),
    }
  }
  const completedChildVoice = getChildVoiceCompleteResume(session)
  if (hasParentUploadResume(session)) {
    return {
      consentToken: session.state.consentToken || activeConsentToken,
      email: session.state.email || '',
      ageGroup: session.state.ageGroup || '',
      fileId: session.state.fileId || '',
      voiceSampleId: session.state.voiceSampleId || completedChildVoice?.sampleId || '',
      voiceSampleDurationSeconds: Number(session.state.voiceSampleDurationSeconds || completedChildVoice?.durationSeconds || 0),
      verificationType: 'parent_call',
    }
  }
  if (hasSelfVoiceUploadResume(session)) {
    return {
      consentToken: session.state.consentToken || activeConsentToken,
      email: session.state.email || '',
      ageGroup: session.state.ageGroup || '',
      verificationType: 'self_voice',
    }
  }
  if (completedChildVoice) {
    return {
      consentToken: session.state.consentToken || activeConsentToken,
      email: session.state.email || '',
      ageGroup: session.state.ageGroup || '',
      voiceSampleId: completedChildVoice.sampleId || '',
      voiceSampleDurationSeconds: Number(completedChildVoice.durationSeconds || 0),
      verificationType: 'parent_call',
    }
  }
  if (hasChildVoiceUploadResume(session)) {
    return {
      consentToken: session.state.consentToken || activeConsentToken,
      email: session.state.email || '',
      ageGroup: session.state.ageGroup || '',
      verificationType: 'parent_call',
    }
  }
  if (hasAnalysisJobResume(session)) {
    return {
      consentToken: session.state.consentToken || activeConsentToken,
      email: session.state.email || '',
      ageGroup: session.state.ageGroup || '',
      fileId: session.state.fileId || '',
      voiceSampleId: session.state.voiceSampleId || '',
      voiceSampleDurationSeconds: Number(session.state.voiceSampleDurationSeconds || 0),
      verificationType: session.state.verificationType || 'parent_call',
    }
  }
  return {
    consentToken: session.state.consentToken || activeConsentToken,
    email: session.state.email || '',
    ageGroup: session.state.ageGroup || '',
  }
}

const historySignature = (item: Record<string, any>) => {
  const analysis = item.analysis as Record<string, any> | undefined
  const verificationType = item.verification_type || 'parent_call'
  const savedAt = item.saved_at || item.created_at || analysis?.created_at || ''
  const date = new Date(String(savedAt))
  const minute = Number.isNaN(date.getTime()) ? '' : date.toISOString().slice(0, 16)
  const confidence = Math.round(Number(analysis?.confidence_score || 0) * 100)
  const probabilities = analysis?.model_probabilities || {}
  const normal = Math.round(Number(probabilities.Normal || 0) * 100)
  const mci = Math.round(Number(probabilities.MCI || 0) * 100)
  const ad = Math.round(Number(probabilities.AD || 0) * 100)
  return `${verificationType}:${minute}:${confidence}:${normal}:${mci}:${ad}`
}

const normalizeHistory = (items: Array<Record<string, any>>) => {
  const seenIds = new Set<string>()
  const seenSignatures = new Set<string>()
  return items.filter(item => {
    const analysis = item.analysis as Record<string, unknown> | undefined
    const analysisId = String(analysis?.analysis_id || '')
    const modelSource = String(analysis?.model_source || '').toLowerCase()
    const signature = historySignature(item)
    if (analysisId.startsWith('demo-analysis-') || modelSource === 'demo') return false
    if (!analysisId || seenIds.has(analysisId) || seenSignatures.has(signature)) return false
    seenIds.add(analysisId)
    seenSignatures.add(signature)
    return true
  })
}

const loadHistoryFor = (email: string) => {
  if (!email.trim()) return []
  try {
    const key = historyKeyFor(email)
    const rawHistory = JSON.parse(localStorage.getItem(key) || '[]') as Array<Record<string, any>>
    const deduped = normalizeHistory(rawHistory)
    if (deduped.length !== rawHistory.length) {
      localStorage.setItem(key, JSON.stringify(deduped))
    }
    return deduped
  } catch {
    return []
  }
}

function App() {
  const restoredSession = loadAppSession()
  const initialStep: AppStep = initialStepFromPath(window.location.pathname, restoredSession)
  const [step, setStep] = useState<AppStep>(initialStep)
  const [historyBackStep, setHistoryBackStep] = useState<AppStep>(restoredSession?.historyBackStep || 'login')
  const [resultsBackStep, setResultsBackStep] = useState<AppStep>(restoredSession?.resultsBackStep || 'upload')
  const [consentBackStep, setConsentBackStep] = useState<AppStep>(restoredSession?.consentBackStep || 'signup')
  const [serviceBackStep, setServiceBackStep] = useState<AppStep>(restoredSession?.serviceBackStep || 'login')
  const [, setIsMember] = useState(() => localStorage.getItem('sorimemo_member_ready') === 'true')
  const [history, setHistory] = useState<Array<Record<string, any>>>([])
  const [state, setState] = useState<AppState>({ ...initialState, ...restoredStateForInitialLoad(restoredSession) })
  const [uploadResetNonce, setUploadResetNonce] = useState(0)
  const [uploadHasLocalState, setUploadHasLocalState] = useState(false)
  const browserHistoryReadyRef = useRef(false)
  const initialBrowserStepRef = useRef<AppStep>(initialStep)
  const recordingGuideBackInterceptRef = useRef<(() => boolean) | null>(null)

  useEffect(() => {
    const initialBrowserStep = initialBrowserStepRef.current
    const baseStep: AppStep = 'home'
    const basePath = pathForStep(initialBrowserStep)
    window.history.replaceState({ sorimemoApp: true, step: initialBrowserStep }, '', basePath)
    if (initialBrowserStep !== baseStep) {
      window.history.replaceState({ sorimemoApp: true, step: initialBrowserStep }, '', basePath)
    }
    browserHistoryReadyRef.current = true

    const handlePopState = (event: PopStateEvent) => {
      const nextStep = event.state?.sorimemoApp ? event.state.step as AppStep : 'home'
      if (nextStep) setStep(nextStep)
    }

    window.addEventListener('popstate', handlePopState)
    return () => window.removeEventListener('popstate', handlePopState)
  }, [])

  useEffect(() => {
    if (!browserHistoryReadyRef.current) return
    const currentState = window.history.state as { sorimemoApp?: boolean; step?: AppStep } | null
    if (currentState?.sorimemoApp && currentState.step === step) return
    window.history.pushState({ sorimemoApp: true, step }, '', pathForStep(step))
  }, [step])

  useEffect(() => {
    persistAppSession(step, historyBackStep, resultsBackStep, consentBackStep, serviceBackStep, state)
  }, [consentBackStep, historyBackStep, resultsBackStep, serviceBackStep, state, step])

  useEffect(() => {
    if (!userProtectedSteps.has(step) || hasUserSession()) return
    setActiveConsentToken('')
    updateState({
      consentToken: '',
      fileId: '',
      voiceSampleId: '',
      voiceSampleDurationSeconds: 0,
      analysisId: '',
      analysisResult: null,
      resultsData: null,
      loginError: '로그인 세션이 만료되었습니다. 다시 로그인해 주세요.',
    })
    setStep('login')
  }, [step])

  const updateState = (partial: Partial<AppState>) => {
    setState(prev => ({ ...prev, ...partial }))
  }

  const refreshHistory = async () => {
    try {
      const payload = await getResultsHistory(10)
      setHistory(normalizeHistory((payload.items || []) as Array<Record<string, any>>))
    } catch {
      setHistory(loadHistoryFor(state.email))
    }
  }

  const saveHistory = async (resultsData: Record<string, unknown>) => {
    setHistory(prev => {
      const nextItem: Record<string, any> = { ...(resultsData as Record<string, any>), saved_at: new Date().toISOString() }
      const nextAnalysis = nextItem.analysis as Record<string, unknown> | undefined
      const nextAnalysisId = String(nextAnalysis?.analysis_id || '')
      const nextSignature = historySignature(nextItem)
      const withoutDuplicate = prev.filter(item => {
        const itemAnalysis = item.analysis as Record<string, unknown> | undefined
        return String(itemAnalysis?.analysis_id || '') !== nextAnalysisId && historySignature(item) !== nextSignature
      })
      const next = [nextItem, ...withoutDuplicate].slice(0, 10)
      return next
    })
    await refreshHistory()
  }

  const deleteHistoryItem = async (analysisId: string) => {
    try {
      await deleteResultHistoryItem(analysisId)
    } catch {
      // Keep local cleanup best-effort if the server item was already gone.
    }
    setHistory(prev => {
      const next = prev.filter(item => String(item.analysis?.analysis_id || '') !== analysisId)
      return next
    })
    const currentAnalysis = state.resultsData?.analysis as Record<string, unknown> | undefined
    if (String(currentAnalysis?.analysis_id || '') === analysisId) {
      updateState({
        analysisId: '',
        analysisResult: null,
        resultsData: null,
      })
    }
  }

  const resetCurrentAnalysis = (verificationType: VerificationType = 'parent_call') => {
    const activeConsentToken = state.consentToken || getActiveConsentToken()
    clearPendingAnalysisResume()
    if (verificationType === 'self_voice') {
      clearSelfVoiceUploadTransientState(activeConsentToken)
    } else {
      clearParentUploadTransientState(activeConsentToken)
    }
    updateState({
      consentToken: activeConsentToken,
      verificationType,
      fileId: '',
      voiceSampleId: '',
      voiceSampleDurationSeconds: 0,
      subjectDisplayName: verificationType === 'self_voice' ? (state.displayName || '본인') : '',
      subjectAgeGroup: verificationType === 'self_voice' ? state.ageGroup : '',
      subjectGender: '',
      subjectRelation: verificationType === 'self_voice' ? 'self' : '',
      analysisId: '',
      analysisResult: null,
      resultsData: null,
    })
    if (!activeConsentToken) {
      setConsentBackStep('service')
      setStep('consent')
      return
    }
    setStep('subjectProfile')
  }

  const handleSignupComplete = async () => {
    if (!state.email.trim()) {
      updateState({ signupError: '이메일을 입력해 주세요.' })
      return
    }
    if (!state.displayName.trim() || !state.signupPurpose) {
      updateState({ signupError: '가입자 표시명과 가입 목적을 입력해 주세요.' })
      return
    }
    if (!isValidPassword(state.signupPassword)) {
      updateState({ signupError: passwordPolicyMessage })
      return
    }
    if (state.signupPassword !== state.signupPasswordConfirm) {
      updateState({ signupError: '비밀번호 확인이 일치하지 않습니다.' })
      return
    }
    try {
      const account = await signupAccount({
        email: state.email.trim(),
        password: state.signupPassword,
        age_group: state.ageGroup || 'other',
        display_name: state.displayName.trim(),
        signup_purpose: state.signupPurpose,
      })
      localStorage.setItem('sorimemo_member_ready', 'true')
      setActiveConsentToken('')
      setIsMember(true)
      updateState({
        email: account.email || state.email.trim(),
        displayName: account.display_name || state.displayName.trim(),
        signupPurpose: account.signup_purpose || state.signupPurpose,
        ageGroup: account.age_group || state.ageGroup || 'other',
        consentToken: '',
        fileId: '',
        voiceSampleId: '',
        voiceSampleDurationSeconds: 0,
        verificationType: 'parent_call',
        analysisId: '',
        analysisResult: null,
        resultsData: null,
        signupPassword: '',
        signupPasswordConfirm: '',
        signupError: '',
      })
      void refreshHistory()
      setConsentBackStep('signup')
      setStep('consent')
    } catch (error) {
      updateState({ signupError: error instanceof Error ? error.message : '회원가입 중 오류가 발생했습니다.' })
    }
  }

  const handleLogin = async () => {
    if (!state.email.trim() || !state.loginPassword.trim()) {
      updateState({ loginError: '이메일과 비밀번호를 입력해 주세요.' })
      return
    }
    try {
      const account = await loginAccount({
        email: state.email.trim(),
        password: state.loginPassword,
      })
      localStorage.setItem('sorimemo_member_ready', 'true')
      setActiveConsentToken('')
      setIsMember(true)
      updateState({
        email: account.email || state.email.trim(),
        displayName: account.display_name || state.displayName,
        signupPurpose: account.signup_purpose || state.signupPurpose,
        ageGroup: account.age_group || state.ageGroup || 'other',
        consentToken: '',
        fileId: '',
        voiceSampleId: '',
        voiceSampleDurationSeconds: 0,
        verificationType: 'parent_call',
        analysisId: '',
        analysisResult: null,
        resultsData: null,
        loginPassword: '',
        loginError: '',
      })
      void refreshHistory()
      setConsentBackStep('login')
      setStep('consent')
    } catch (error) {
      updateState({ loginError: error instanceof Error ? error.message : '로그인 중 오류가 발생했습니다.' })
    }
  }

  const handleSubjectProfileComplete = async () => {
    if (!state.subjectAgeGroup || !state.subjectGender) {
      updateState({ signupError: '검증 대상자의 연령대와 성별을 입력해 주세요.' })
      return
    }
    if (state.verificationType === 'parent_call' && !state.subjectRelation) {
      updateState({ signupError: '부모님과의 관계를 선택해 주세요.' })
      return
    }
    if (state.verificationType === 'parent_call' && state.subjectRelation === 'other' && !state.subjectDisplayName.trim()) {
      updateState({ signupError: '기타 가족은 추가 구분명을 입력해 주세요.' })
      return
    }
    const consentToken = state.consentToken || getActiveConsentToken()
    if (!consentToken) {
      updateState({ signupError: '동의 절차를 먼저 완료해 주세요.' })
      setStep('consent')
      return
    }
    const subjectDisplayName = state.verificationType === 'self_voice'
      ? '본인'
      : state.subjectRelation === 'other'
        ? state.subjectDisplayName.trim()
        : subjectRelationDisplayName(state.subjectRelation)
    try {
      await saveConsentSubject(consentToken, {
        subject_type: state.verificationType === 'self_voice' ? 'self' : 'parent',
        subject_relation: state.verificationType === 'self_voice' ? 'self' : state.subjectRelation,
        subject_display_name: subjectDisplayName,
        subject_age_group: state.subjectAgeGroup,
        subject_gender: state.subjectGender,
      })
      updateState({ subjectDisplayName, signupError: '' })
      setStep(state.verificationType === 'self_voice' ? 'selfVoice' : 'childVoice')
    } catch (error) {
      updateState({ signupError: error instanceof Error ? error.message : '검증 대상자 정보 저장에 실패했습니다.' })
    }
  }

  const handlePasswordResetRequest = async () => {
    if (!state.email.trim()) {
      updateState({ resetError: '가입 이메일을 입력해 주세요.' })
      return
    }
    try {
      const payload = await requestPasswordReset(state.email.trim())
      updateState({
        resetToken: payload.reset_token || state.resetToken,
        resetMessage: payload.reset_token
          ? '재설정 코드가 발급되었습니다. 아래 코드 입력란에 자동으로 입력했습니다.'
          : payload.message || '가입된 이메일이면 재설정 코드가 발급됩니다.',
        resetError: '',
      })
    } catch (error) {
      updateState({ resetError: error instanceof Error ? error.message : '비밀번호 재설정 요청에 실패했습니다.' })
    }
  }

  const handlePasswordResetConfirm = async () => {
    if (!state.email.trim() || !state.resetToken.trim() || !state.resetPassword.trim()) {
      updateState({ resetError: '이메일, 재설정 코드, 새 비밀번호를 모두 입력해 주세요.' })
      return
    }
    if (!isValidPassword(state.resetPassword)) {
      updateState({ resetError: passwordPolicyMessage })
      return
    }
    if (state.resetPassword !== state.resetPasswordConfirm) {
      updateState({ resetError: '새 비밀번호 확인이 일치하지 않습니다.' })
      return
    }
    try {
      const payload = await confirmPasswordReset({
        email: state.email.trim(),
        reset_token: state.resetToken.trim(),
        new_password: state.resetPassword,
      })
      updateState({
        loginPassword: '',
        resetToken: '',
        resetPassword: '',
        resetPasswordConfirm: '',
        resetMessage: payload.message || '비밀번호가 변경되었습니다.',
        resetError: '',
      })
      setStep('login')
    } catch (error) {
      updateState({ resetError: error instanceof Error ? error.message : '비밀번호 변경에 실패했습니다.' })
    }
  }

  const handleAdminLogin = async () => {
    if (!state.adminId.trim() || !state.adminPassword.trim()) {
      updateState({ adminError: '관리자 ID와 비밀번호를 입력해 주세요.' })
      return
    }
    try {
      await loginAdmin({
        admin_id: state.adminId.trim(),
        password: state.adminPassword,
      })
      updateState({ adminPassword: '', adminError: '' })
      setStep('admin')
      return
    } catch (error) {
      clearAdminSession()
      updateState({ adminError: error instanceof Error ? error.message : '관리자 로그인 중 오류가 발생했습니다.' })
    }
  }

  const goBack = () => {
    if (step === 'recordingGuide' && recordingGuideBackInterceptRef.current?.()) return
    if (step === 'signup') setStep('home')
    if (step === 'login') setStep('home')
    if (step === 'passwordReset') setStep('login')
    if (step === 'service') setStep(serviceBackStep)
    if (step === 'subjectProfile') setStep('consent')
    if (step === 'consent') setStep(consentBackStep)
    if (step === 'childVoice') setStep('service')
    if (step === 'upload') {
      if (uploadHasLocalState) {
        clearParentUploadTransientState(state.consentToken || getActiveConsentToken())
        updateState({ fileId: '' })
        setUploadResetNonce(prev => prev + 1)
        setUploadHasLocalState(false)
        setStep('upload')
        return
      }
      setStep('childVoice')
    }
    if (step === 'selfVoice') setStep('service')
    if (step === 'analyzing') {
      clearPendingAnalysisResume()
      setStep(state.verificationType === 'self_voice' ? 'selfVoice' : 'upload')
    }
    if (step === 'results') {
      if (resultsBackStep === 'upload') {
        clearParentUploadTransientState(state.consentToken || getActiveConsentToken())
        updateState({ fileId: '' })
      }
      if (resultsBackStep === 'selfVoice') {
        clearSelfVoiceUploadTransientState(state.consentToken || getActiveConsentToken())
        updateState({ fileId: '', voiceSampleId: '', verificationType: 'self_voice' })
      }
      setStep(resultsBackStep)
    }
    if (step === 'reliability') setStep('results')
    if (step === 'followup') setStep('results')
    if (step === 'history') setStep(historyBackStep)
    if (step === 'recordingGuide') setStep(state.consentToken ? 'consent' : 'service')
    if (step === 'adminLogin') setStep('home')
    if (step === 'admin') setStep('home')
  }

  const goHome = () => {
    setStep('home')
  }

  const screenTitle = {
    home: '',
    signup: '회원 가입',
    login: '로그인',
    passwordReset: '비밀번호 재설정',
    service: '서비스 시작',
    subjectProfile: '검증 대상 정보',
    consent: '동의 절차',
    childVoice: '자녀 음성 등록',
    upload: '부모통화검증',
    selfVoice: '내 목소리 검증',
    analyzing: '통화 음성 분석',
    results: '분석 결과',
    reliability: '결과 자세히보기',
    followup: '후속 대응 안내',
    history: '지난 검증 이력',
    recordingGuide: '녹음 방법 안내',
    adminLogin: '관리자 로그인',
    admin: '관리자 콘솔',
  }[step]
  const largeTitleSteps: AppStep[] = [
    'signup',
    'login',
    'passwordReset',
    'service',
    'subjectProfile',
    'consent',
    'childVoice',
    'upload',
    'selfVoice',
    'analyzing',
    'results',
    'reliability',
    'recordingGuide',
  ]
  const usesLargeTitle = largeTitleSteps.includes(step)

  const isAdminRoute = step === 'adminLogin' || step === 'admin'

  if (isAdminRoute) {
    return (
      <div className="min-h-screen bg-[#101820] text-[#172326]">
        {step === 'adminLogin' && (
          <main className="mx-auto flex min-h-screen w-full max-w-[440px] items-center px-5 py-8">
            <AdminLoginPage
              adminId={state.adminId}
              adminPassword={state.adminPassword}
              error={state.adminError}
              onChange={updateState}
              onSubmit={handleAdminLogin}
              onBack={() => {
                window.history.pushState({ sorimemoApp: true, step: 'home' }, '', '/')
                setStep('home')
              }}
            />
          </main>
        )}

        {step === 'admin' && (
          <main className="mx-auto min-h-screen w-full max-w-6xl px-4 py-5 sm:px-6 sm:py-8">
            <AdminPage
              onBack={() => {
                clearAdminSession()
                setStep('adminLogin')
              }}
            />
          </main>
        )}
      </div>
    )
  }

  return (
    <div className="min-h-screen bg-[#eef5f2] px-3 py-4 text-[#143c3d] sm:py-8">
      <div className="mx-auto w-full max-w-[430px] overflow-hidden rounded-[34px] border border-black/10 bg-[#fbfdfb] shadow-2xl shadow-teal-950/10">
        {step !== 'home' && (
          <header className="flex items-center justify-between px-5 pb-2 pt-5">
            <button
              onClick={goBack}
              className="flex h-11 w-14 items-center justify-start rounded-full text-[24px] font-black text-[#0b7074] hover:bg-[#e8f3f1]"
              aria-label="이전"
            >
              ←
            </button>
            <h1 className={`${usesLargeTitle ? 'text-[26px] font-black' : 'text-[20px] font-black'} text-[#173c3d]`}>
              {screenTitle}
            </h1>
            <button
              onClick={goHome}
              className="flex h-11 w-16 items-center justify-end rounded-full text-[17px] font-black text-[#0b7074] hover:bg-[#e8f3f1]"
              aria-label="홈으로"
            >
              홈
            </button>
          </header>
        )}

        <main className="min-h-[760px] px-5 pb-6">
          {step === 'home' && (
            <section className="flex min-h-[760px] flex-col">
              <div className="flex justify-end pt-5">
                <Button
                  variant="outline"
                  className="h-12 rounded-full border-[#d7e6e2] bg-white px-5 text-[16px] font-black text-[#0f6f73] shadow-none hover:bg-[#f4faf8]"
                  onClick={() => setStep('signup')}
                >
                  <UserPlus className="mr-2 h-5 w-5" />
                  회원가입
                </Button>
              </div>
              <div className="flex flex-1 flex-col items-center justify-center text-center">
                <p className="text-[42px] font-black tracking-tight text-[#0c7478]">SoriMemo</p>
                <p className="mt-2 text-[18px] font-black text-[#255a5b]">목소리 속 인지 변화 참고 신호</p>

                <div className="mt-12 flex h-36 w-36 items-center justify-center rounded-full bg-[#d7efea]">
                  <div className="flex h-28 w-28 items-center justify-center rounded-full bg-[#15908e] shadow-lg shadow-teal-800/20">
                    <PhoneCall className="h-16 w-16 text-white" />
                  </div>
                </div>

                <p className="mt-10 whitespace-pre-line text-[18px] font-bold leading-[1.55] text-[#255a5b]">
                  부모님과의 통화 또는 내 목소리에서{'\n'}인지기능 변화와 관련된{'\n'}참고 신호를 살펴봅니다.
                </p>
              </div>

              <div className="space-y-3 pb-4">
                <Button
                  className="h-16 w-full rounded-full bg-[#0f7d82] text-[18px] font-black text-white shadow-none hover:bg-[#0b6f74]"
                  onClick={() => setStep('login')}
                >
                  서비스 시작
                </Button>
                <p className="flex items-center justify-center gap-2 pt-5 text-[16px] font-bold leading-[1.45] text-[#7c9694]">
                  <ShieldCheck className="h-5 w-5 shrink-0" />
                  의료 진단이 아닌 비의료적 참고 정보입니다
                </p>
              </div>
            </section>
          )}

          {step === 'signup' && (
            <SignupPage
              email={state.email}
              displayName={state.displayName}
              signupPurpose={state.signupPurpose}
              password={state.signupPassword}
              passwordConfirm={state.signupPasswordConfirm}
              error={state.signupError}
              onChange={updateState}
              onComplete={handleSignupComplete}
            />
          )}

          {step === 'login' && (
            <LoginPage
              email={state.email}
              password={state.loginPassword}
              error={state.loginError}
              onChange={updateState}
              onSubmit={handleLogin}
              onPasswordReset={() => {
                updateState({ resetError: '', resetMessage: '', resetToken: '' })
                setStep('passwordReset')
              }}
            />
          )}

          {step === 'passwordReset' && (
            <PasswordResetPage
              email={state.email}
              resetToken={state.resetToken}
              newPassword={state.resetPassword}
              newPasswordConfirm={state.resetPasswordConfirm}
              message={state.resetMessage}
              error={state.resetError}
              onChange={updateState}
              onRequest={handlePasswordResetRequest}
              onConfirm={handlePasswordResetConfirm}
            />
          )}

          {step === 'service' && (
            <ServiceMenuPage
              onParentCall={() => resetCurrentAnalysis('parent_call')}
              onSelfVoice={() => resetCurrentAnalysis('self_voice')}
              onHistory={() => {
                setHistoryBackStep('service')
                void refreshHistory()
                setStep('history')
              }}
            />
          )}

          {step === 'subjectProfile' && (
            <SubjectProfilePage
              verificationType={state.verificationType}
              subjectDisplayName={state.subjectDisplayName}
              subjectAgeGroup={state.subjectAgeGroup}
              subjectGender={state.subjectGender}
              subjectRelation={state.subjectRelation}
              error={state.signupError}
              onChange={updateState}
              onComplete={handleSubjectProfileComplete}
            />
          )}

          {step === 'recordingGuide' && (
            <RecordingGuidePage
              onBackIntercept={handler => {
                recordingGuideBackInterceptRef.current = handler
              }}
              onComplete={() => {
                setServiceBackStep('recordingGuide')
                setStep('service')
              }}
            />
          )}

          {step === 'consent' && (
            <ConsentPage
              ageGroup={state.ageGroup}
              userName={state.displayName}
              verificationType={state.verificationType}
              subjectDisplayName={state.subjectDisplayName}
              subjectAgeGroup={state.subjectAgeGroup}
              subjectGender={state.subjectGender}
              subjectRelation={state.subjectRelation}
              onComplete={(token, ageGroup) => {
                setActiveConsentToken(token)
                updateState({ consentToken: token, ageGroup })
                setStep('service')
              }}
            />
          )}

          {step === 'history' && (
            <HistoryPage
              items={history}
              onSelect={item => {
                updateState({
                  verificationType: item.verification_type === 'self_voice' ? 'self_voice' : 'parent_call',
                  analysisId: String(item.analysis?.analysis_id || ''),
                  analysisResult: item.analysis || null,
                  resultsData: item,
                })
                setResultsBackStep('history')
                setStep('results')
              }}
              onRestart={() => setStep('service')}
              onDelete={deleteHistoryItem}
            />
          )}

          {step === 'childVoice' && (
            <ChildVoiceSamplePage
              consentToken={state.consentToken || getActiveConsentToken()}
              onComplete={(voiceSampleId, voiceSampleDurationSeconds) => {
                updateState({
                  consentToken: state.consentToken || getActiveConsentToken(),
                  voiceSampleId,
                  voiceSampleDurationSeconds,
                  verificationType: 'parent_call',
                })
                setStep('upload')
              }}
            />
          )}

          {step === 'upload' && (
            <UploadPage
              key={`upload-${state.consentToken || getActiveConsentToken()}-${uploadResetNonce}`}
              consentToken={state.consentToken || getActiveConsentToken()}
              voiceSampleId={state.voiceSampleId}
              voiceSampleDurationSeconds={state.voiceSampleDurationSeconds}
              onLocalStateChange={setUploadHasLocalState}
              onComplete={(fileId, voiceSampleId, voiceSampleDurationSeconds) => {
                const nextState = {
                  ...state,
                  fileId,
                  voiceSampleId: voiceSampleId || state.voiceSampleId,
                  voiceSampleDurationSeconds: voiceSampleDurationSeconds || state.voiceSampleDurationSeconds || 0,
                  verificationType: 'parent_call' as VerificationType,
                }
                savePendingAnalysisResume(nextState)
                persistAppSession('analyzing', historyBackStep, resultsBackStep, consentBackStep, serviceBackStep, nextState)
                updateState(nextState)
                setStep('analyzing')
              }}
            />
          )}

          {step === 'selfVoice' && (
            <SelfVoicePage
              consentToken={state.consentToken || getActiveConsentToken()}
              onComplete={(fileId, durationSeconds) => {
                const activeConsentToken = state.consentToken || getActiveConsentToken()
                clearSelfVoiceUploadTransientState(activeConsentToken)
                const nextState = {
                  ...state,
                  consentToken: activeConsentToken,
                  fileId,
                  voiceSampleId: '',
                  voiceSampleDurationSeconds: durationSeconds,
                  verificationType: 'self_voice' as VerificationType,
                }
                savePendingAnalysisResume(nextState)
                persistAppSession('analyzing', historyBackStep, resultsBackStep, consentBackStep, serviceBackStep, nextState)
                updateState(nextState)
                setStep('analyzing')
              }}
              onBack={() => setStep('service')}
            />
          )}

          {step === 'analyzing' && (
            <AnalyzingPage
              fileId={state.fileId}
              voiceSampleId={state.voiceSampleId}
              verificationType={state.verificationType}
              onComplete={(analysisId, analysisResult, resultsData) => {
                clearPendingAnalysisResume()
                const activeConsentToken = state.consentToken || getActiveConsentToken()
                if (state.verificationType === 'self_voice') {
                  clearSelfVoiceUploadTransientState(activeConsentToken)
                } else {
                  clearParentUploadTransientState(activeConsentToken)
                }
                const enrichedResultsData = {
                  ...resultsData,
                  verification_type: state.verificationType,
                  voice_sample: {
                    ...((resultsData.voice_sample as Record<string, unknown> | undefined) || {}),
                    duration_seconds: state.voiceSampleDurationSeconds,
                  },
                }
                updateState({ analysisId, analysisResult, resultsData: enrichedResultsData })
                void saveHistory(enrichedResultsData)
                setResultsBackStep(state.verificationType === 'self_voice' ? 'selfVoice' : 'upload')
                setStep('results')
              }}
              onBack={() => {
                clearPendingAnalysisResume()
                const isSelfVoiceAnalysis = state.verificationType === 'self_voice' || !state.voiceSampleId
                updateState({
                  fileId: '',
                  verificationType: isSelfVoiceAnalysis ? 'self_voice' : 'parent_call',
                })
                setStep(isSelfVoiceAnalysis ? 'selfVoice' : 'upload')
              }}
            />
          )}

          {step === 'results' && (
            <ResultsPage
              resultsData={state.resultsData}
              onRestart={() => resetCurrentAnalysis(state.verificationType)}
              onReliability={() => setStep('reliability')}
            />
          )}

          {step === 'reliability' && <ReliabilityPage resultsData={state.resultsData} />}

          {step === 'followup' && (
            <FollowupPage
              resultsData={state.resultsData}
              onNewAnalysis={resetCurrentAnalysis}
              onHistory={() => {
                setHistoryBackStep('followup')
                void refreshHistory()
                setStep('history')
              }}
            />
          )}

        </main>

        <div className="flex justify-center pb-3">
          <div className="h-1.5 w-28 rounded-full bg-black/80" />
        </div>
      </div>
    </div>
  )
}

export default App
