import { useEffect, useRef, useState } from 'react'
import { CheckCircle, Download, FileAudio, Mic, Square } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { fetchLatestAudioUpload, uploadAudio } from '@/lib/api'

interface SelfVoicePageProps {
  consentToken: string
  onComplete: (fileId: string, durationSeconds: number) => void
  onBack: () => void
}

interface QualityReport {
  duration_seconds: number
  snr_db: number
  silence_ratio: number
  sample_rate: number
  channels: number
  format_original: string
  quality_pass: boolean
  rejection_reason: string | null
  self_voice_prompt_checked?: boolean | null
  self_voice_prompt_match_score?: number | null
  self_voice_prompt_keyword_coverage?: number | null
  self_voice_prompt_stt_confidence?: number | null
  self_voice_prompt_transcript_char_count?: number | null
}

type FileSystemAccessWindow = Window & {
  showOpenFilePicker?: (options?: {
    multiple?: boolean
    types?: Array<{
      description: string
      accept: Record<string, string[]>
    }>
  }) => Promise<Array<{ getFile: () => Promise<File> }>>
}

type VoiceInputMode = 'record' | 'file' | null

const audioFileExtensions = ['.m4a', '.mp3', '.wav', '.flac', '.ogg', '.aac', '.wma', '.webm', '.3gp', '.3ga', '.amr']
const audioPickerAccept: Record<string, string[]> = {
  'audio/*': audioFileExtensions,
  'audio/wav': ['.wav'],
  'audio/x-wav': ['.wav'],
  'audio/mpeg': ['.mp3'],
  'audio/mp4': ['.m4a', '.3gp', '.3ga'],
  'audio/aac': ['.aac'],
  'audio/ogg': ['.ogg'],
  'audio/flac': ['.flac'],
  'audio/webm': ['.webm'],
  'application/octet-stream': audioFileExtensions,
}
const audioInputAccept = [
  'audio/*',
  '.wav',
  '.m4a',
  '.mp3',
  '.flac',
  '.ogg',
  '.aac',
  '.wma',
  '.webm',
  '.3gp',
  '.3ga',
  '.amr',
].join(',')

const activeConsentTokenKey = 'sorimemo_active_consent_token'
const selfVoiceUploadTtlMs = 10 * 60 * 1000
const selfVoiceUploadKey = (consentToken: string) => `sorimemo_self_voice_upload:${consentToken}`
const selfVoiceAudioUploadStateKey = (consentToken: string) => `sorimemo_self_voice_audio_upload:${consentToken}`
const selfVoiceAudioUploadPendingKey = (consentToken: string) => `sorimemo_self_voice_audio_upload_pending:${consentToken}`
const qualityCheckDurationNotice = '보통 2~3분 정도 걸릴 수 있습니다.'
const qualityCheckWaitNotice = '창을 닫지 말고 잠시만 기다려 주세요.'

const getActiveConsentToken = () => {
  try {
    return sessionStorage.getItem(activeConsentTokenKey) || ''
  } catch {
    return ''
  }
}

const markSelfVoiceUpload = (consentToken: string) => {
  if (!consentToken) return
  try {
    sessionStorage.setItem(selfVoiceUploadKey(consentToken), JSON.stringify({
      expiresAt: Date.now() + selfVoiceUploadTtlMs,
    }))
  } catch {
    // Upload resume markers are best-effort only.
  }
}

const clearSelfVoiceUpload = (consentToken: string) => {
  if (!consentToken) return
  try {
    sessionStorage.removeItem(selfVoiceUploadKey(consentToken))
  } catch {
    // Upload resume markers are best-effort only.
  }
}

const markSelfVoiceUploadPending = (consentToken: string, file: File) => {
  const startedAt = new Date().toISOString()
  if (!consentToken) return startedAt
  try {
    sessionStorage.setItem(selfVoiceAudioUploadPendingKey(consentToken), JSON.stringify({
      fileName: file.name,
      fileSizeMb: (file.size / 1024 / 1024).toFixed(1),
      startedAt,
      expiresAt: Date.now() + selfVoiceUploadTtlMs,
    }))
  } catch {
    // Pending upload state is best-effort only.
  }
  return startedAt
}

const clearSelfVoiceUploadPending = (consentToken: string) => {
  if (!consentToken) return
  try {
    sessionStorage.removeItem(selfVoiceAudioUploadPendingKey(consentToken))
  } catch {
    // Pending upload state is best-effort only.
  }
}

const wait = (ms: number) => new Promise(resolve => window.setTimeout(resolve, ms))

const SELF_VOICE_SCRIPT = [
  '오늘은 조용한 곳에서 제 목소리를 자연스럽게 녹음하고 있습니다.',
  '아침에는 물을 한 잔 마시고 창밖의 날씨를 살펴보았습니다.',
  '요즘은 가족과 친구들의 안부를 묻고, 하루 일정을 차분히 정리하려고 합니다.',
  '장을 볼 때는 필요한 물건을 미리 적어 두고, 천천히 확인하면서 고릅니다.',
  '가끔 단어가 바로 떠오르지 않을 때도 있지만, 서두르지 않고 다시 생각해 봅니다.',
  '이 녹음은 제 목소리의 말 속도와 멈춤, 발음의 변화를 참고하기 위한 것입니다.',
]

export default function SelfVoicePage({ consentToken, onComplete }: SelfVoicePageProps) {
  const effectiveConsentToken = consentToken || getActiveConsentToken()
  const [voiceFile, setVoiceFile] = useState<File | null>(null)
  const [fileId, setFileId] = useState('')
  const [voiceFileLabel, setVoiceFileLabel] = useState('')
  const [quality, setQuality] = useState<QualityReport | null>(null)
  const [uploading, setUploading] = useState(false)
  const [recording, setRecording] = useState(false)
  const [recordingPaused, setRecordingPaused] = useState(false)
  const [recordingSeconds, setRecordingSeconds] = useState(0)
  const [voiceDownloadUrl, setVoiceDownloadUrl] = useState('')
  const [voiceInputMode, setVoiceInputMode] = useState<VoiceInputMode>(null)
  const [uploadStatus, setUploadStatus] = useState('')
  const [qualityFailureReason, setQualityFailureReason] = useState('')
  const [error, setError] = useState('')

  const voiceInputRef = useRef<HTMLInputElement>(null)
  const recorderRef = useRef<MediaRecorder | null>(null)
  const streamRef = useRef<MediaStream | null>(null)
  const chunksRef = useRef<BlobPart[]>([])
  const timerRef = useRef<number | null>(null)
  const fileSelectionHandledRef = useRef(false)
  const uploadRequestIdRef = useRef(0)
  const restoreInFlightRef = useRef(false)
  const uploadResultAppliedRef = useRef(false)

  const normalizeQualityReport = (qualityReport: Record<string, any> = {}): QualityReport => ({
    duration_seconds: Number(qualityReport.duration_seconds || 0),
    snr_db: Number(qualityReport.snr_db || 0),
    silence_ratio: Number(qualityReport.silence_ratio || 0),
    sample_rate: Number(qualityReport.sample_rate || 0),
    channels: Number(qualityReport.channels || 0),
    format_original: String(qualityReport.format_original || ''),
    quality_pass: Boolean(qualityReport.quality_pass),
    rejection_reason: qualityReport.rejection_reason || null,
    self_voice_prompt_checked: qualityReport.self_voice_prompt_checked ?? null,
    self_voice_prompt_match_score: qualityReport.self_voice_prompt_match_score ?? null,
    self_voice_prompt_keyword_coverage: qualityReport.self_voice_prompt_keyword_coverage ?? null,
    self_voice_prompt_stt_confidence: qualityReport.self_voice_prompt_stt_confidence ?? null,
    self_voice_prompt_transcript_char_count: qualityReport.self_voice_prompt_transcript_char_count ?? null,
  })

  const applySelfVoiceUploadResult = (
    result: Record<string, any>,
    fallbackFileName = '',
    fallbackMode: Exclude<VoiceInputMode, null> = 'file',
  ) => {
    if (!effectiveConsentToken) return
    uploadResultAppliedRef.current = true
    const qualityReport = normalizeQualityReport(result.quality_report || result.quality || {})
    const restoredFileName = String(result.file_name || fallbackFileName || voiceFile?.name || voiceFileLabel || '선택한 내 목소리 파일')
    if (qualityReport.quality_pass) {
      try {
        sessionStorage.setItem(selfVoiceAudioUploadStateKey(effectiveConsentToken), JSON.stringify({
          fileId: result.file_id,
          fileName: restoredFileName,
          fileSizeMb: result.file_size_mb || (voiceFile ? (voiceFile.size / 1024 / 1024).toFixed(1) : ''),
          quality: qualityReport,
          expiresAt: Date.now() + selfVoiceUploadTtlMs,
        }))
      } catch {
        // Upload state persistence is best-effort only.
      }
    } else {
      try {
        sessionStorage.removeItem(selfVoiceAudioUploadStateKey(effectiveConsentToken))
      } catch {
        // Upload state persistence is best-effort only.
      }
    }
    clearSelfVoiceUploadPending(effectiveConsentToken)
    clearSelfVoiceUpload(effectiveConsentToken)
    if (voiceDownloadUrl) URL.revokeObjectURL(voiceDownloadUrl)
    setVoiceFile(null)
    setVoiceFileLabel(restoredFileName)
    setVoiceDownloadUrl('')
    setVoiceInputMode(fallbackMode)
    setFileId(String(result.file_id || ''))
    setQuality(qualityReport)
    setUploading(false)
    setUploadStatus('')
    setQualityFailureReason(qualityReport.quality_pass ? '' : qualityReport.rejection_reason || '품질검사를 통과하지 못했습니다.')
    setError('')
  }

  const restoreSavedSelfVoiceUpload = () => {
    if (!effectiveConsentToken) return false
    try {
      const saved = JSON.parse(sessionStorage.getItem(selfVoiceAudioUploadStateKey(effectiveConsentToken)) || 'null') as {
        fileId?: string
        fileName?: string
        quality?: QualityReport
        expiresAt?: number
      } | null
      if (saved?.fileId && saved.quality && saved.expiresAt && saved.expiresAt > Date.now()) {
        uploadResultAppliedRef.current = true
        setVoiceFile(null)
        setVoiceFileLabel(saved.fileName || '선택한 내 목소리 파일')
        setVoiceDownloadUrl('')
        setVoiceInputMode('file')
        setFileId(saved.fileId)
        setQuality(saved.quality)
        setUploading(false)
        setUploadStatus('')
        setError('')
        clearSelfVoiceUploadPending(effectiveConsentToken)
        clearSelfVoiceUpload(effectiveConsentToken)
        return true
      }
      if (saved) sessionStorage.removeItem(selfVoiceAudioUploadStateKey(effectiveConsentToken))
    } catch {
      // Restoring upload state is best-effort.
    }
    return false
  }

  const restorePendingSelfVoiceUpload = async () => {
    if (!effectiveConsentToken || restoreInFlightRef.current || uploadResultAppliedRef.current) return
    restoreInFlightRef.current = true
    try {
      const pending = JSON.parse(sessionStorage.getItem(selfVoiceAudioUploadPendingKey(effectiveConsentToken)) || 'null') as {
        fileName?: string
        startedAt?: string
        expiresAt?: number
      } | null
      if (!pending?.startedAt || !pending.expiresAt || pending.expiresAt <= Date.now()) {
        clearSelfVoiceUploadPending(effectiveConsentToken)
        return
      }
      setUploadStatus('품질검사 결과를 확인하고 있습니다.')
      for (let attempt = 0; attempt < 8; attempt += 1) {
        if (uploadResultAppliedRef.current) return
        try {
          const latest = await fetchLatestAudioUpload(effectiveConsentToken, pending.startedAt)
          applySelfVoiceUploadResult(latest, pending.fileName)
          return
        } catch {
          await wait(1000)
        }
      }
      setUploading(false)
      setUploadStatus('품질검사 결과를 아직 확인하지 못했습니다. 같은 파일을 다시 선택해 주세요.')
      clearSelfVoiceUpload(effectiveConsentToken)
    } catch {
      setUploading(false)
      setUploadStatus('')
    } finally {
      restoreInFlightRef.current = false
    }
  }

  useEffect(() => {
    if (!effectiveConsentToken) return
    if (restoreSavedSelfVoiceUpload()) return
    void restorePendingSelfVoiceUpload()
  }, [effectiveConsentToken])

  useEffect(() => {
    return () => {
      if (timerRef.current) window.clearInterval(timerRef.current)
      streamRef.current?.getTracks().forEach(track => track.stop())
      if (voiceDownloadUrl) URL.revokeObjectURL(voiceDownloadUrl)
    }
  }, [voiceDownloadUrl])

  const setCurrentVoiceFile = (file: File, mode: Exclude<VoiceInputMode, null> = 'file') => {
    if (voiceDownloadUrl) URL.revokeObjectURL(voiceDownloadUrl)
    clearSelfVoiceUpload(effectiveConsentToken)
    clearSelfVoiceUploadPending(effectiveConsentToken)
    try {
      sessionStorage.removeItem(selfVoiceAudioUploadStateKey(effectiveConsentToken))
    } catch {
      // Upload state persistence is best-effort only.
    }
    uploadResultAppliedRef.current = false
    restoreInFlightRef.current = false
    uploadRequestIdRef.current += 1
    setVoiceFile(file)
    setVoiceFileLabel(mode === 'record' ? '녹음한 내 목소리' : file.name)
    setVoiceDownloadUrl(URL.createObjectURL(file))
    setVoiceInputMode(mode)
    setFileId('')
    setQuality(null)
    setUploadStatus('')
    setQualityFailureReason('')
    setError('')
  }

  const clearVoiceFile = () => {
    if (voiceDownloadUrl) URL.revokeObjectURL(voiceDownloadUrl)
    clearSelfVoiceUpload(effectiveConsentToken)
    clearSelfVoiceUploadPending(effectiveConsentToken)
    try {
      sessionStorage.removeItem(selfVoiceAudioUploadStateKey(effectiveConsentToken))
    } catch {
      // Upload state persistence is best-effort only.
    }
    uploadResultAppliedRef.current = false
    restoreInFlightRef.current = false
    uploadRequestIdRef.current += 1
    setVoiceFile(null)
    setVoiceFileLabel('')
    setVoiceDownloadUrl('')
    setVoiceInputMode(null)
    setFileId('')
    setQuality(null)
    setUploadStatus('')
    setQualityFailureReason('')
    setError('')
  }

  const downloadVoiceFile = () => {
    if (!voiceDownloadUrl || !voiceFile) return
    const link = document.createElement('a')
    link.href = voiceDownloadUrl
    link.download = voiceFile.name
    link.style.display = 'none'
    document.body.appendChild(link)
    link.click()
    link.remove()
  }

  const stopTracks = () => {
    streamRef.current?.getTracks().forEach(track => track.stop())
    streamRef.current = null
  }

  const clearRecordingTimer = () => {
    if (timerRef.current) {
      window.clearInterval(timerRef.current)
      timerRef.current = null
    }
  }

  const startRecordingTimer = () => {
    clearRecordingTimer()
    timerRef.current = window.setInterval(() => {
      setRecordingSeconds(prev => prev + 1)
    }, 1000)
  }

  const prepareRecording = () => {
    setError('')
    clearRecordingTimer()
    clearSelfVoiceUpload(effectiveConsentToken)
    clearSelfVoiceUploadPending(effectiveConsentToken)
    try {
      sessionStorage.removeItem(selfVoiceAudioUploadStateKey(effectiveConsentToken))
    } catch {
      // Upload state persistence is best-effort only.
    }
    uploadResultAppliedRef.current = false
    restoreInFlightRef.current = false
    uploadRequestIdRef.current += 1
    if (voiceDownloadUrl) {
      URL.revokeObjectURL(voiceDownloadUrl)
      setVoiceDownloadUrl('')
    }
    setVoiceFile(null)
    setVoiceFileLabel('')
    setVoiceInputMode('record')
    setFileId('')
    setQuality(null)
    setUploadStatus('')
    setQualityFailureReason('')
    setRecordingSeconds(0)
    setRecordingPaused(false)
  }

  const startRecording = async () => {
    setError('')
    clearRecordingTimer()
    clearSelfVoiceUpload(effectiveConsentToken)
    clearSelfVoiceUploadPending(effectiveConsentToken)
    try {
      sessionStorage.removeItem(selfVoiceAudioUploadStateKey(effectiveConsentToken))
    } catch {
      // Upload state persistence is best-effort only.
    }
    uploadResultAppliedRef.current = false
    restoreInFlightRef.current = false
    uploadRequestIdRef.current += 1
    if (voiceDownloadUrl) {
      URL.revokeObjectURL(voiceDownloadUrl)
      setVoiceDownloadUrl('')
    }
    setVoiceFile(null)
    setVoiceFileLabel('')
    setVoiceInputMode('record')
    setFileId('')
    setQuality(null)
    setUploadStatus('')
    setQualityFailureReason('')
    setRecordingSeconds(0)
    setRecordingPaused(false)
    if (!navigator.mediaDevices?.getUserMedia || typeof MediaRecorder === 'undefined') {
      setError('현재 브라우저에서 녹음을 지원하지 않습니다. 파일 업로드를 이용해 주세요.')
      return
    }

    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true })
      streamRef.current = stream
      chunksRef.current = []
      const mimeType = MediaRecorder.isTypeSupported('audio/webm;codecs=opus') ? 'audio/webm;codecs=opus' : ''
      const recorder = new MediaRecorder(stream, mimeType ? { mimeType } : undefined)
      recorder.ondataavailable = event => {
        if (event.data.size > 0) chunksRef.current.push(event.data)
      }
      recorder.onstop = () => {
        const blob = new Blob(chunksRef.current, { type: recorder.mimeType || 'audio/webm' })
        const file = new File([blob], `sorimemo_self_voice_${Date.now()}.webm`, { type: blob.type })
        setCurrentVoiceFile(file, 'record')
        stopTracks()
      }

      recorderRef.current = recorder
      recorder.start()
      setRecording(true)
      setRecordingSeconds(0)
      startRecordingTimer()
    } catch {
      setError('마이크 권한을 확인해 주세요.')
      clearRecordingTimer()
      setRecording(false)
      setRecordingPaused(false)
      stopTracks()
    }
  }

  const pauseRecording = () => {
    clearRecordingTimer()
    if (recorderRef.current?.state === 'recording') {
      recorderRef.current.pause()
      setRecordingPaused(true)
    }
  }

  const resumeRecording = () => {
    if (recorderRef.current?.state === 'paused') {
      recorderRef.current.resume()
      setRecordingPaused(false)
      startRecordingTimer()
    }
  }

  const stopRecording = () => {
    clearRecordingTimer()
    recorderRef.current?.stop()
    recorderRef.current = null
    setRecording(false)
    setRecordingPaused(false)
  }

  const handleUpload = async (selectedFile = voiceFile) => {
    if (!selectedFile) return
    if (!effectiveConsentToken) {
      setError('유효한 동의 토큰이 없습니다. 동의 절차를 다시 완료해 주세요.')
      return
    }
    const requestId = uploadRequestIdRef.current + 1
    uploadRequestIdRef.current = requestId
    setUploading(true)
    markSelfVoiceUpload(effectiveConsentToken)
    markSelfVoiceUploadPending(effectiveConsentToken, selectedFile)
    setUploadStatus('내 목소리 품질검사를 진행하고 있습니다.')
    setError('')
    setQualityFailureReason('')
    try {
      const [result] = await Promise.all([
        uploadAudio(selectedFile, effectiveConsentToken, {
          uploadContext: 'self_voice',
        }),
        wait(1200),
      ])
      if (uploadRequestIdRef.current !== requestId) return
      applySelfVoiceUploadResult({
        ...result,
        file_name: selectedFile.name,
        file_size_mb: (selectedFile.size / 1024 / 1024).toFixed(1),
      }, selectedFile.name, voiceInputMode || 'file')
    } catch (e) {
      if (uploadRequestIdRef.current !== requestId) return
      setUploadStatus('')
      setFileId('')
      setQualityFailureReason(e instanceof Error ? e.message : '음성 업로드에 실패했습니다.')
      clearSelfVoiceUploadPending(effectiveConsentToken)
    } finally {
      if (uploadRequestIdRef.current === requestId) setUploading(false)
      if (uploadResultAppliedRef.current) clearSelfVoiceUpload(effectiveConsentToken)
    }
  }

  const openVoiceFileSearch = async () => {
    setError('')
    if (!effectiveConsentToken) {
      setError('유효한 동의 토큰이 없습니다. 동의 절차를 다시 완료해 주세요.')
      return
    }
    clearVoiceFile()
    const filePicker = (window as FileSystemAccessWindow).showOpenFilePicker
    if (filePicker) {
      try {
        const [handle] = await filePicker({
          multiple: false,
          types: [
            {
              description: '음성 파일',
              accept: audioPickerAccept,
            },
          ],
        })
        const file = await handle?.getFile()
        if (file) {
          setCurrentVoiceFile(file, 'file')
          void handleUpload(file)
        } else {
          clearSelfVoiceUpload(effectiveConsentToken)
          setUploadStatus('')
        }
        return
      } catch (error) {
        clearSelfVoiceUpload(effectiveConsentToken)
        setUploadStatus('')
        if (!(error instanceof DOMException && error.name === 'AbortError')) {
          setError('파일 탐색기를 열지 못했습니다. 브라우저 새로고침 후 다시 시도해 주세요.')
        }
        return
      }
    }
    voiceInputRef.current?.click()
  }

  const handleVoiceFileInput = (input: HTMLInputElement) => {
    if (fileSelectionHandledRef.current) return
    const file = input.files?.[0]
    if (!file) return
    fileSelectionHandledRef.current = true
    clearSelfVoiceUpload(effectiveConsentToken)
    setCurrentVoiceFile(file, 'file')
    void handleUpload(file)
  }

  const time = `${String(Math.floor(recordingSeconds / 60)).padStart(2, '0')}:${String(recordingSeconds % 60).padStart(2, '0')}`
  const canProceed = Boolean(fileId && quality?.quality_pass)
  const qualityPassed = Boolean(fileId && quality?.quality_pass)
  const showQualityWaitNotice = uploading || uploadStatus.includes('품질검사 결과를 확인')

  return (
    <div className="space-y-3 pt-1">
      <section className="overflow-hidden rounded-[24px] bg-[#0d777c] p-4 text-white shadow-lg shadow-teal-900/15">
        <div className="rounded-2xl bg-white/12 px-4 py-2.5 text-[16px] font-bold leading-[1.34] text-white">
          {SELF_VOICE_SCRIPT.map(line => (
            <p key={line} className="mb-1.5 last:mb-0">
              {line}
            </p>
          ))}
        </div>
        {!qualityPassed && (
          <>
            <div className="mt-4 flex items-center justify-between rounded-2xl bg-white/10 px-4 py-3">
              <span className="text-[16px] font-black text-white/90">
                {recording ? (recordingPaused ? '녹음 일시정지' : '녹음 중') : voiceFile ? '음성 선택 완료' : '녹음 준비'}
              </span>
              <span className="text-[26px] font-light tabular-nums text-white">{recording || voiceFile ? time : '00:30'}</span>
            </div>
            <div className="mt-3 h-1.5 rounded-full bg-white/25">
              <div
                className="h-full rounded-full bg-white"
                style={{ width: `${Math.min(100, Math.max(8, (recordingSeconds / 30) * 100))}%` }}
              />
            </div>
          </>
        )}

        {recording ? (
          <div className="mt-4 grid grid-cols-2 gap-2">
            <Button
              onClick={recordingPaused ? resumeRecording : pauseRecording}
              className="h-14 rounded-full bg-white/12 text-[17px] font-black text-white shadow-none ring-1 ring-white/30 hover:bg-white/20"
            >
              {recordingPaused ? (
                <>
                  <Mic className="mr-2 h-4 w-4" />
                  계속 녹음
                </>
              ) : (
                <>
                  <Square className="mr-2 h-4 w-4" />
                  녹음 멈춤
                </>
              )}
            </Button>
            <Button
              onClick={stopRecording}
              className="h-14 rounded-full bg-white text-[17px] font-black text-[#0d777c] shadow-none hover:bg-[#eef8f6]"
            >
              <CheckCircle className="mr-2 h-4 w-4" />
              녹음 끝내기
            </Button>
          </div>
        ) : !voiceInputMode && !voiceFile ? (
          <div className="mt-4 grid grid-cols-2 gap-2">
            <Button
              onClick={prepareRecording}
              className="h-14 rounded-full bg-white text-[16px] font-black text-[#0d777c] shadow-none hover:bg-[#eef8f6]"
            >
              <Mic className="mr-2 h-5 w-5" />
              내 목소리 녹음
            </Button>
            <Button
              variant="outline"
              className="h-14 rounded-full border-white/30 bg-white/10 text-[16px] font-black text-white shadow-none hover:bg-white/20"
              onClick={openVoiceFileSearch}
            >
              <FileAudio className="mr-2 h-5 w-5" />
              음성파일 선택
            </Button>
          </div>
        ) : voiceInputMode === 'record' && !voiceFile ? (
          <div className="mt-4">
            <Button
              onClick={startRecording}
              className="h-16 w-full justify-center rounded-full bg-white px-5 text-[18px] font-black text-[#0d777c] shadow-none hover:bg-[#eef8f6]"
            >
              <Mic className="mr-2 h-6 w-6 shrink-0" />
              녹음 시작
            </Button>
          </div>
        ) : null}

        {voiceFile && !qualityPassed && (
          <div className="mt-3 space-y-2">
            {!fileId && (
              <Button
                onClick={() => handleUpload()}
                disabled={uploading || recording}
                className="h-14 w-full rounded-full bg-white px-4 text-[17px] font-black text-[#0d777c] shadow-none hover:bg-[#eef8f6]"
              >
                {uploading ? '품질검사 중' : '선택된 내 목소리 등록'}
              </Button>
            )}
          </div>
        )}

        {quality && !quality.quality_pass && (
          <div className="mt-3 rounded-2xl bg-red-50 px-4 py-4 text-[#7f1d1d]">
            <p className="text-[18px] font-black">품질검사를 통과하지 못했습니다.</p>
            <p className="mt-2 text-[17px] font-bold leading-[1.5]">
              길이 {quality.duration_seconds.toFixed(1)}초 · SNR {quality.snr_db.toFixed(1)}dB · 무음 {(quality.silence_ratio * 100).toFixed(1)}%
            </p>
            {(qualityFailureReason || quality.rejection_reason) && (
              <p className="mt-2 text-[17px] font-bold leading-[1.5]">
                사유: {(qualityFailureReason || quality.rejection_reason || '').replace(' 더 긴 녹음을 업로드해 주세요.', '')}
              </p>
            )}
            <p className="mt-2 text-[17px] font-bold leading-[1.5]">
              조용한 곳에서 내 목소리로 30~60초 정도 다시 녹음해 주세요.
            </p>
            <Button
              type="button"
              onClick={() => {
                if (voiceInputMode === 'record') {
                  prepareRecording()
                } else {
                  void openVoiceFileSearch()
                }
              }}
              className="mt-3 h-[60px] w-full rounded-full bg-[#dc2626] px-5 text-[18px] font-black text-white shadow-none hover:bg-[#b91c1c]"
            >
              {voiceInputMode === 'record' ? '다시 녹음' : '다시 파일 선택'}
            </Button>
          </div>
        )}
        {uploadStatus && (!quality || quality.quality_pass) && (
          <div className="mt-3 rounded-2xl bg-white/10 px-4 py-3 text-center text-white">
            <p className="text-[18px] font-black leading-[1.42]">
              {uploadStatus}
            </p>
            {showQualityWaitNotice && (
              <>
                <p className="mt-2 text-[18px] font-black leading-[1.42]">
                  {qualityCheckDurationNotice}
                </p>
                <p className="mt-2 text-[16px] font-bold leading-[1.42] text-white/80">
                  {qualityCheckWaitNotice}
                </p>
              </>
            )}
          </div>
        )}

        {error && (
          <div className="mt-3 rounded-2xl bg-red-50 px-4 py-4 text-center text-red-600">
            <p className="text-[18px] font-black leading-[1.45]">{error}</p>
            {voiceFile && (
              <Button
                type="button"
                onClick={() => {
                  if (voiceInputMode === 'record') {
                    prepareRecording()
                  } else {
                    void openVoiceFileSearch()
                  }
                }}
                className="mt-3 h-[60px] w-full rounded-full bg-[#dc2626] px-5 text-[18px] font-black text-white shadow-none hover:bg-[#b91c1c]"
              >
                {voiceInputMode === 'record' ? '다시 녹음' : '다시 파일 선택'}
              </Button>
            )}
          </div>
        )}

        {qualityFailureReason && !quality && (
          <div className="mt-3 rounded-2xl bg-red-50 px-4 py-4 text-[#7f1d1d]">
            <p className="text-[18px] font-black">품질검사를 통과하지 못했습니다.</p>
            <p className="mt-2 text-[17px] font-bold leading-[1.5]">
              사유: {qualityFailureReason}
            </p>
            <p className="mt-2 text-[17px] font-bold leading-[1.5]">
              조용한 곳에서 내 목소리로 30~60초 정도 다시 녹음해 주세요.
            </p>
            <Button
              type="button"
              onClick={() => {
                if (voiceInputMode === 'record') {
                  prepareRecording()
                } else {
                  void openVoiceFileSearch()
                }
              }}
              className="mt-3 h-[60px] w-full rounded-full bg-[#dc2626] px-5 text-[18px] font-black text-white shadow-none hover:bg-[#b91c1c]"
            >
              {voiceInputMode === 'record' ? '다시 녹음' : '다시 파일 선택'}
            </Button>
          </div>
        )}

        {qualityPassed && (
          <div className="mt-4 space-y-3">
            {voiceDownloadUrl && voiceInputMode === 'record' && (
              <Button
                type="button"
                variant="outline"
                onClick={downloadVoiceFile}
                className="h-14 w-full rounded-full border-white/30 bg-white/10 px-4 text-[16px] font-black text-white shadow-none hover:bg-white/20"
              >
                <Download className="mr-2 h-5 w-5" />
                품질검사 완료 음성 다운로드
              </Button>
            )}
            <Button
              onClick={() => onComplete(fileId, quality?.duration_seconds || recordingSeconds || 0)}
              className="h-14 w-full rounded-full bg-white text-[18px] font-black text-[#0d777c] shadow-none hover:bg-[#eef8f6]"
            >
              분석 시작
            </Button>
            <p className="rounded-xl bg-white/10 px-4 py-3 text-center text-[17px] font-bold leading-[1.5] text-white">
              품질검사가 완료되었고 내 목소리 음성이 등록되었습니다.
            </p>
          </div>
        )}
        {!qualityPassed && (
          <Button
            onClick={() => onComplete(fileId, quality?.duration_seconds || recordingSeconds || 0)}
            disabled={!canProceed}
            className="mt-3 h-14 w-full rounded-full bg-white text-[18px] font-black text-[#0d777c] shadow-none hover:bg-[#eef8f6] disabled:bg-white/30 disabled:text-white/60"
          >
            분석 시작
          </Button>
        )}

        <input
          ref={voiceInputRef}
          type="file"
          accept={audioInputAccept}
          className="hidden"
          onClick={e => {
            fileSelectionHandledRef.current = false
            e.currentTarget.value = ''
          }}
          onInput={e => handleVoiceFileInput(e.currentTarget)}
          onChange={e => handleVoiceFileInput(e.currentTarget)}
        />
      </section>
    </div>
  )
}
