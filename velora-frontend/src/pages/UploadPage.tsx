import { useEffect, useRef, useState } from 'react'
import { CheckCircle, CloudUpload, Music, PhoneCall, X } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { fetchLatestAudioUpload, uploadAudio } from '@/lib/api'

interface UploadPageProps {
  consentToken: string
  voiceSampleId: string
  voiceSampleDurationSeconds: number
  initialFileId?: string
  onComplete: (fileId: string, voiceSampleId: string, voiceSampleDurationSeconds: number) => void
  onLocalStateChange?: (hasLocalState: boolean) => void
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
  original_duration_seconds?: number | null
  trimmed_to_seconds?: number | null
  was_trimmed?: boolean
  speech_duration_seconds?: number | null
  rms_dbfs?: number | null
  child_voice_present?: boolean | null
  child_voice_duration_seconds?: number | null
  parent_voice_duration_seconds?: number | null
  detected_speaker_count?: number | null
  diarization_confidence?: number | null
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

const audioUploadStateKey = (consentToken: string) => `sorimemo_parent_audio_upload:${consentToken}`
const audioUploadErrorKey = (consentToken: string) => `sorimemo_parent_audio_upload_error:${consentToken}`
const audioUploadPendingKey = (consentToken: string) => `sorimemo_parent_audio_upload_pending:${consentToken}`
const childVoiceCompleteKey = (consentToken: string) => `sorimemo_child_voice_complete:${consentToken}`
const childVoiceSampleStateKey = (consentToken: string) => `sorimemo_child_voice_sample:${consentToken}`
const parentUploadResumeKey = (consentToken: string) => `sorimemo_parent_upload_resume:${consentToken}`
const parentUploadResumeTtlMs = 10 * 60 * 1000
const audioUploadPendingTtlMs = 10 * 60 * 1000
const qualityCheckDurationNotice = '보통 2~3분 정도 걸릴 수 있습니다.'
const qualityCheckWaitNotice = '창을 닫지 말고 잠시만 기다려 주세요.'
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

const markParentUploadResume = (consentToken: string) => {
  try {
    sessionStorage.setItem(parentUploadResumeKey(consentToken), JSON.stringify({
      expiresAt: Date.now() + parentUploadResumeTtlMs,
    }))
  } catch {
    // Upload resume markers are best-effort only.
  }
}

const clearParentUploadResume = (consentToken: string) => {
  try {
    sessionStorage.removeItem(parentUploadResumeKey(consentToken))
  } catch {
    // Upload resume markers are best-effort only.
  }
}

const getSavedVoiceSample = (consentToken: string) => {
  try {
    const completed = JSON.parse(sessionStorage.getItem(childVoiceCompleteKey(consentToken)) || 'null') as {
      sampleId?: string
      durationSeconds?: number
      expiresAt?: number
    } | null
    if (completed?.sampleId && (!completed.expiresAt || completed.expiresAt > Date.now())) {
      return {
        sampleId: completed.sampleId,
        durationSeconds: Number(completed.durationSeconds || 0),
      }
    }
    const saved = JSON.parse(sessionStorage.getItem(childVoiceSampleStateKey(consentToken)) || 'null') as {
      sampleId?: string
      durationSeconds?: number
    } | null
    if (saved?.sampleId) {
      return {
        sampleId: saved.sampleId,
        durationSeconds: Number(saved.durationSeconds || 0),
      }
    }
  } catch {
    // Voice sample restore is best-effort only.
  }
  return { sampleId: '', durationSeconds: 0 }
}

const markAudioUploadPending = (consentToken: string, file: File) => {
  try {
    const startedAt = new Date().toISOString()
    sessionStorage.setItem(audioUploadPendingKey(consentToken), JSON.stringify({
      fileName: file.name,
      fileSizeMb: (file.size / 1024 / 1024).toFixed(1),
      startedAt,
      expiresAt: Date.now() + audioUploadPendingTtlMs,
    }))
    return startedAt
  } catch {
    return new Date().toISOString()
  }
}

const clearAudioUploadPending = (consentToken: string) => {
  try {
    sessionStorage.removeItem(audioUploadPendingKey(consentToken))
  } catch {
    // Pending upload state is best-effort only.
  }
}

const wait = (ms: number) => new Promise(resolve => window.setTimeout(resolve, ms))

export default function UploadPage({
  consentToken,
  voiceSampleId,
  voiceSampleDurationSeconds,
  onComplete,
  onLocalStateChange,
}: UploadPageProps) {
  const [audioFile, setAudioFile] = useState<File | null>(null)
  const [audioFileName, setAudioFileName] = useState('')
  const [audioFileSizeMb, setAudioFileSizeMb] = useState('')
  const [fileId, setFileId] = useState('')
  const [quality, setQuality] = useState<QualityReport | null>(null)
  const [uploading, setUploading] = useState(false)
  const [audioUploadStatus, setAudioUploadStatus] = useState('')
  const [uploadAttemptKey, setUploadAttemptKey] = useState('')
  const [, setUploadDebug] = useState('')
  const [error, setError] = useState('')

  useEffect(() => {
    onLocalStateChange?.(Boolean(audioFile || fileId || quality || uploading || error))
  }, [audioFile, error, fileId, onLocalStateChange, quality, uploading])

  const sharedAudioInputRef = useRef<HTMLInputElement>(null)
  const uploadRequestIdRef = useRef(0)
  const restoreInFlightRef = useRef(false)
  const uploadResultAppliedRef = useRef(false)
  const restoreSuppressedRef = useRef(false)
  const savedVoiceSample = getSavedVoiceSample(consentToken)
  const effectiveVoiceSampleId = voiceSampleId || savedVoiceSample.sampleId
  const effectiveVoiceSampleDurationSeconds = voiceSampleDurationSeconds || savedVoiceSample.durationSeconds || 0

  const normalizeQualityReport = (qualityReport: Record<string, any> = {}): QualityReport => ({
    duration_seconds: Number(qualityReport.duration_seconds || 0),
    snr_db: Number(qualityReport.snr_db || 0),
    silence_ratio: Number(qualityReport.silence_ratio || 0),
    sample_rate: Number(qualityReport.sample_rate || 0),
    channels: Number(qualityReport.channels || 0),
    format_original: String(qualityReport.format_original || ''),
    quality_pass: Boolean(qualityReport.quality_pass),
    rejection_reason: qualityReport.rejection_reason || null,
    original_duration_seconds: qualityReport.original_duration_seconds ?? null,
    trimmed_to_seconds: qualityReport.trimmed_to_seconds ?? null,
    was_trimmed: Boolean(qualityReport.was_trimmed),
    speech_duration_seconds: qualityReport.speech_duration_seconds ?? null,
    rms_dbfs: qualityReport.rms_dbfs ?? null,
    child_voice_present: qualityReport.child_voice_present ?? null,
    child_voice_duration_seconds: qualityReport.child_voice_duration_seconds ?? null,
    parent_voice_duration_seconds: qualityReport.parent_voice_duration_seconds ?? null,
    detected_speaker_count: qualityReport.detected_speaker_count ?? null,
    diarization_confidence: qualityReport.diarization_confidence ?? null,
  })

  const applyUploadResult = (
    result: Record<string, any>,
    fallbackFileName = '',
    fallbackFileSizeMb = '',
  ) => {
    uploadResultAppliedRef.current = true
    const qualityReport = normalizeQualityReport(result.quality_report || result.quality || {})
    const restoredFileName = String(result.file_name || fallbackFileName || audioFile?.name || audioFileName || '')
    const restoredFileSizeMb = String(
      result.file_size_mb
      || fallbackFileSizeMb
      || (audioFile ? (audioFile.size / 1024 / 1024).toFixed(1) : audioFileSizeMb)
      || ''
    )
    sessionStorage.setItem(audioUploadStateKey(consentToken), JSON.stringify({
      fileId: result.file_id,
      fileName: restoredFileName,
      fileSizeMb: restoredFileSizeMb,
      quality: qualityReport,
    }))
    sessionStorage.removeItem(audioUploadErrorKey(consentToken))
    clearAudioUploadPending(consentToken)
    clearParentUploadResume(consentToken)
    setAudioFile(null)
    setAudioFileName(restoredFileName)
    setAudioFileSizeMb(restoredFileSizeMb)
    setUploadAttemptKey('')
    setFileId(String(result.file_id || ''))
    setQuality(qualityReport)
    setAudioUploadStatus('')
    setError('')
    setUploadDebug('')
  }

  const restoreSavedAudioUpload = () => {
    try {
      const saved = JSON.parse(sessionStorage.getItem(audioUploadStateKey(consentToken)) || 'null') as {
        fileId?: string
        fileName?: string
        fileSizeMb?: string
        quality?: QualityReport
      } | null
      if (saved?.fileId && saved.quality) {
        uploadResultAppliedRef.current = true
        setFileId(saved.fileId)
        setQuality(saved.quality)
        setAudioFileName(saved.fileName || '선택한 통화녹음 파일')
        setAudioFileSizeMb(saved.fileSizeMb || '')
        setAudioFile(null)
        setUploading(false)
        setUploadAttemptKey('')
        setAudioUploadStatus('')
        setError('')
        setUploadDebug('')
        sessionStorage.removeItem(audioUploadErrorKey(consentToken))
        clearAudioUploadPending(consentToken)
        clearParentUploadResume(consentToken)
        return true
      }
    } catch {
      // Restoring upload state is best-effort.
    }
    return false
  }

  const restorePendingAudioUpload = async () => {
    if (restoreInFlightRef.current || uploadResultAppliedRef.current) return
    restoreInFlightRef.current = true
    try {
      const pending = JSON.parse(sessionStorage.getItem(audioUploadPendingKey(consentToken)) || 'null') as {
        fileName?: string
        fileSizeMb?: string
        startedAt?: string
        expiresAt?: number
      } | null
      if (!pending?.startedAt || !pending.expiresAt || pending.expiresAt <= Date.now()) {
        clearAudioUploadPending(consentToken)
        return
      }
      for (let attempt = 0; attempt < 8; attempt += 1) {
        if (uploadResultAppliedRef.current) return
        try {
          const latest = await fetchLatestAudioUpload(consentToken, pending.startedAt)
          applyUploadResult(latest, pending.fileName, pending.fileSizeMb)
          return
        } catch {
          await wait(1000)
        }
      }
      setAudioUploadStatus('품질검사 결과를 아직 확인하지 못했습니다. 같은 파일을 다시 선택해 주세요.')
    } catch {
      setAudioUploadStatus('')
    } finally {
      restoreInFlightRef.current = false
    }
  }

  useEffect(() => {
    if (restoreSuppressedRef.current) return
    if (restoreSavedAudioUpload()) return
    try {
      const savedError = JSON.parse(sessionStorage.getItem(audioUploadErrorKey(consentToken)) || 'null') as {
        message?: string
        debug?: string
        fileName?: string
        fileSizeMb?: string
      } | null
      if (savedError?.message) {
        setError(savedError.message)
        setUploadDebug(savedError.debug || '')
        setAudioFileName(savedError.fileName || '선택한 통화녹음 파일')
        setAudioFileSizeMb(savedError.fileSizeMb || '')
        setAudioFile(null)
        setFileId('')
        setQuality(null)
      }
    } catch {
      // Restoring upload state is best-effort.
    }
  }, [consentToken])

  useEffect(() => {
    if (restoreSuppressedRef.current) return
    if (audioFile || fileId || quality || uploading || error) return
    if (restoreSavedAudioUpload()) return
    if (uploadResultAppliedRef.current) return
    void restorePendingAudioUpload()
  }, [audioFile, consentToken, error, fileId, quality, uploading])

  const setCurrentAudioFile = (file: File) => {
    restoreSuppressedRef.current = true
    uploadResultAppliedRef.current = false
    restoreInFlightRef.current = false
    uploadRequestIdRef.current += 1
    setAudioFile(file)
    setAudioFileName(file.name)
    setAudioFileSizeMb((file.size / 1024 / 1024).toFixed(1))
    setFileId('')
    setQuality(null)
    setUploadAttemptKey('')
    setAudioUploadStatus('파일 선택 완료. 통화 파일 품질 검사를 시작합니다.')
    setError('')
    setUploadDebug('')
    sessionStorage.removeItem(audioUploadStateKey(consentToken))
    sessionStorage.removeItem(audioUploadErrorKey(consentToken))
    clearAudioUploadPending(consentToken)
  }

  const clearAudio = () => {
    restoreSuppressedRef.current = true
    uploadResultAppliedRef.current = false
    restoreInFlightRef.current = false
    uploadRequestIdRef.current += 1
    setAudioFile(null)
    setAudioFileName('')
    setAudioFileSizeMb('')
    setFileId('')
    setQuality(null)
    setUploadAttemptKey('')
    sessionStorage.removeItem(audioUploadStateKey(consentToken))
    sessionStorage.removeItem(audioUploadErrorKey(consentToken))
    clearAudioUploadPending(consentToken)
    setAudioUploadStatus('')
    setError('')
    setUploadDebug('')
  }

  const pickAudioFile = async () => {
    const filePicker = (window as FileSystemAccessWindow).showOpenFilePicker
    if (filePicker) {
      try {
        const [handle] = await filePicker({
          multiple: false,
          types: [{ description: '통화녹음 파일', accept: audioPickerAccept }],
        })
        if (handle) return await handle.getFile()
      } catch (error) {
        if (error instanceof DOMException && error.name === 'AbortError') return null
      }
    }
    sharedAudioInputRef.current?.click()
    return null
  }

  const openAudioFileSearch = async () => {
    restoreSuppressedRef.current = true
    setAudioUploadStatus('')
    setError('')
    setUploadDebug('')
    sessionStorage.removeItem(audioUploadErrorKey(consentToken))
    clearAudioUploadPending(consentToken)
    clearParentUploadResume(consentToken)
    const file = await pickAudioFile()
    if (file) {
      clearParentUploadResume(consentToken)
      setCurrentAudioFile(file)
    }
  }

  const handleAudioUpload = async (selectedFile = audioFile) => {
    if (!selectedFile) {
      setAudioUploadStatus('파일 선택 정보가 없어 다시 선택이 필요합니다.')
      return
    }
    const requestId = uploadRequestIdRef.current + 1
    uploadRequestIdRef.current = requestId
    if (!effectiveVoiceSampleId) {
      setAudioUploadStatus('')
      setError('자녀 음성 샘플 정보가 없습니다. 자녀 음성 등록을 먼저 완료해 주세요.')
      return
    }
    markAudioUploadPending(consentToken, selectedFile)
    setUploading(true)
    markParentUploadResume(consentToken)
    setAudioUploadStatus('통화녹음 파일을 업로드하고 품질검사를 진행하고 있습니다.')
    setError('')
    setUploadDebug(`요청 시작: ${selectedFile.name} / ${(selectedFile.size / 1024 / 1024).toFixed(1)}MB`)
    try {
      const result = await uploadAudio(selectedFile, consentToken, {
        uploadContext: 'parent_call',
        voiceSampleId: effectiveVoiceSampleId,
      })
      if (uploadRequestIdRef.current !== requestId) return
      setUploadDebug(sessionStorage.getItem('sorimemo_last_upload_debug') || '응답 수신')
      sessionStorage.removeItem(audioUploadErrorKey(consentToken))
      applyUploadResult({
        ...result,
        file_name: selectedFile.name,
        file_size_mb: (selectedFile.size / 1024 / 1024).toFixed(1),
      }, selectedFile.name, (selectedFile.size / 1024 / 1024).toFixed(1))
    } catch (e) {
      if (uploadRequestIdRef.current !== requestId) return
      const message = e instanceof Error ? e.message : '업로드에 실패했습니다.'
      const debug = sessionStorage.getItem('sorimemo_last_upload_debug') || message
      setAudioUploadStatus('')
      setError(message)
      setUploadDebug(debug)
      try {
        sessionStorage.setItem(audioUploadErrorKey(consentToken), JSON.stringify({
          message,
          debug,
          fileName: selectedFile.name,
          fileSizeMb: (selectedFile.size / 1024 / 1024).toFixed(1),
          createdAt: new Date().toISOString(),
        }))
      } catch {
        // Debug persistence is best-effort only.
      }
      clearParentUploadResume(consentToken)
      clearAudioUploadPending(consentToken)
    } finally {
      if (uploadRequestIdRef.current === requestId) setUploading(false)
      clearParentUploadResume(consentToken)
      restoreSuppressedRef.current = false
    }
  }

  useEffect(() => {
    if (!audioFile || fileId || quality || uploading) return
    const attemptKey = `${audioFile.name}:${audioFile.size}:${audioFile.lastModified}`
    if (uploadAttemptKey === attemptKey) return
    setUploadAttemptKey(attemptKey)
    void handleAudioUpload(audioFile)
  }, [audioFile, fileId, quality, uploading, uploadAttemptKey])

  const qualityDuration = Number(quality?.duration_seconds || 0)
  const qualitySnr = Number(quality?.snr_db || 0)
  const qualitySilenceRatio = Number(quality?.silence_ratio || 0)
  const rejectionReason = quality?.rejection_reason || ''
  const isCallTypeFailure = rejectionReason.includes('통화 유형 오류') || quality?.child_voice_present === false
  const canProceed = Boolean(fileId && quality?.quality_pass)

  return (
    <div className="space-y-5 pt-2">
      <section className="rounded-2xl border border-[#dce9e6] bg-white p-4">
        <div className="mb-4 flex items-start gap-3 rounded-xl bg-[#f1f8f6] px-4 py-4">
          <PhoneCall className="mt-0.5 h-6 w-6 shrink-0 text-[#0f7d82]" />
          <div>
            <p className="text-[19px] font-black text-[#183f40]">부모님과의 통화녹음 업로드</p>
            <p className="mt-2 max-w-[245px] text-[17px] font-bold leading-[1.52] text-[#607b79]">스마트폰 전화 앱이나 내 파일에 저장된 통화녹음 음성 파일을 선택해 주세요.</p>
          </div>
        </div>
        {!audioFile && !fileId && !quality && !uploading && !error && (
          <button
            type="button"
            onClick={openAudioFileSearch}
            className="flex w-full flex-col items-center rounded-2xl border border-dashed border-[#b8cfcb] bg-[#f7fbfa] px-4 py-6 text-center"
          >
            <CloudUpload className="h-10 w-10 text-[#0f7d82]" />
            <span className="mt-3 text-[19px] font-black text-[#183f40]">내 파일에서 통화녹음 선택</span>
            <span className="mt-2 text-[16px] font-bold text-[#7d9593]">.m4a, .wav 등 음성 파일 지원</span>
          </button>
        )}

        {uploading && (
          <div className="rounded-2xl bg-[#eef7fb] px-4 py-5 text-center">
            <CloudUpload className="mx-auto h-10 w-10 text-[#0f7d82]" />
            <p className="mt-3 text-[19px] font-black text-[#183f40]">통화녹음 파일 품질검사 중</p>
            <p className="mt-2 text-[17px] font-bold leading-[1.5] text-[#426160]">
              파일을 업로드하고 서버에서 음질, 길이, 무음 비율을 확인하고 있습니다.
            </p>
            <p className="mt-3 text-[18px] font-black leading-[1.42] text-[#183f40]">
              {qualityCheckDurationNotice}
            </p>
            <p className="mt-2 text-[16px] font-bold leading-[1.42] text-[#607b79]">
              {qualityCheckWaitNotice}
            </p>
          </div>
        )}

        {(audioFile || fileId) && !uploading && !quality && (
          <div className="mt-4 rounded-2xl bg-[#f1f8f6] p-4">
            <div className="flex items-center gap-3">
              <div className="flex h-12 w-12 items-center justify-center rounded-xl bg-[#0f7d82] text-white">
                <Music className="h-6 w-6" />
              </div>
              <div className="min-w-0 flex-1">
                <p className="truncate text-[17px] font-black text-[#183f40]">{audioFile?.name || audioFileName || '파일명 확인 중'}</p>
                {(audioFile || audioFileSizeMb) && (
                  <p className="text-[16px] font-bold text-[#6f8785]">{audioFile ? (audioFile.size / 1024 / 1024).toFixed(1) : audioFileSizeMb}MB</p>
                )}
              </div>
              <button type="button" onClick={clearAudio} className="text-[#7d9593]">
                <X className="h-5 w-5" />
              </button>
            </div>
            <div className="mt-4 space-y-2 text-[16px] font-bold leading-[1.45] text-[#426160]">
              <p className="flex items-center gap-2"><CheckCircle className="h-5 w-5 shrink-0 text-[#0f7d82]" /> 형식: 서버 품질 검사에서 확인</p>
              <p className="flex items-center gap-2"><CheckCircle className="h-5 w-5 shrink-0 text-[#0f7d82]" /> 전체 통화: 최소 45초 이상</p>
              <p className="flex items-center gap-2"><CheckCircle className="h-5 w-5 shrink-0 text-[#0f7d82]" /> 긴 통화: 분석용으로 앞부분 3분만 사용</p>
              <p className="flex items-center gap-2"><CheckCircle className="h-5 w-5 shrink-0 text-[#0f7d82]" /> 부모 발화량: 30초 이상 권장</p>
            </div>
          </div>
        )}

        {quality && (
          <div className={`mt-4 rounded-2xl p-4 ${quality.quality_pass ? 'bg-[#edf8f4]' : 'bg-red-50'}`}>
            <p className={`flex items-center justify-center gap-2 text-[20px] font-black ${quality.quality_pass ? 'text-[#0f7d82]' : 'text-red-600'}`}>
              <CheckCircle className="h-6 w-6" />
              {quality.quality_pass ? '품질 검증 통과' : isCallTypeFailure ? '통화 유형 확인 실패' : '품질 검증 실패'}
            </p>
            {quality.quality_pass ? (
              <>
                <p className="mt-3 text-center text-[17px] font-bold leading-[1.5] text-[#426160]">
                  통화녹음 파일 품질검사가 완료되었습니다.
                </p>
                <p className="mx-auto mt-3 max-w-[250px] text-center text-[17px] font-black leading-[1.5] text-[#426160]">
                  길이 {qualityDuration.toFixed(1)}초 · SNR {qualitySnr.toFixed(1)}dB · 무음 {(qualitySilenceRatio * 100).toFixed(1)}%
                </p>
              </>
            ) : (
              <>
                <p className="mt-3 text-center text-[17px] font-bold leading-[1.5] text-[#7f1d1d]">
                  길이 {qualityDuration.toFixed(1)}초 · SNR {qualitySnr.toFixed(1)}dB · 무음 {(qualitySilenceRatio * 100).toFixed(1)}%
                </p>
                {quality.rejection_reason && (
                  <p className="mt-3 text-center text-[17px] font-bold leading-[1.5] text-red-600">
                    사유: {quality.rejection_reason}
                  </p>
                )}
                <p className="mt-3 text-center text-[17px] font-bold leading-[1.5] text-red-600">
                  {isCallTypeFailure
                    ? '자녀와 부모님이 함께 대화한 통화녹음 파일을 선택해 주세요.'
                    : '조용한 곳에서 부모님과 다시 통화녹음을 진행한 뒤 새 파일을 선택해 주세요.'}
                </p>
                <Button
                  type="button"
                  onClick={() => void openAudioFileSearch()}
                  className="mt-4 h-[60px] w-full rounded-full bg-red-600 text-[18px] font-black text-white shadow-none hover:bg-red-700"
                >
                  다시 파일 선택
                </Button>
              </>
            )}
          </div>
        )}

        {error && (
          <div className="mt-4 rounded-2xl bg-red-50 p-4 text-center">
            <p className="text-[19px] font-black text-red-600">통화 파일 처리 오류</p>
            <p className="mt-2 text-[17px] font-bold leading-[1.5] text-red-600">{error}</p>
            {(audioFileName || audioFileSizeMb) && (
              <p className="mt-2 text-[16px] font-bold leading-[1.45] text-[#7f1d1d]">
                {audioFileName || '파일명 확인 중'}{audioFileSizeMb ? ` · ${audioFileSizeMb}MB` : ''}
              </p>
            )}
            <Button
              type="button"
              onClick={clearAudio}
              className="mt-4 h-[60px] w-full rounded-full bg-red-600 text-[18px] font-black text-white shadow-none hover:bg-red-700"
            >
              다시 파일 선택
            </Button>
          </div>
        )}

        {audioUploadStatus && (
          <div className="mt-3 rounded-xl bg-[#eef7fb] px-4 py-3 text-center text-[17px] font-bold leading-[1.5] text-[#426160]">
            <p>{audioUploadStatus}</p>
          </div>
        )}

        {canProceed && (
          <Button
            onClick={() => {
              clearParentUploadResume(consentToken)
              onComplete(fileId, effectiveVoiceSampleId, effectiveVoiceSampleDurationSeconds)
            }}
            className="mt-4 h-[68px] w-full rounded-full bg-[#0f7d82] text-[20px] font-black text-white shadow-none hover:bg-[#0b6f74]"
          >
            분석 시작
          </Button>
        )}
      </section>

      <input
        ref={sharedAudioInputRef}
        type="file"
        className="hidden"
        onClick={e => {
          e.currentTarget.value = ''
        }}
        onChange={e => {
          const file = e.target.files?.[0]
          if (!file) {
            setAudioUploadStatus('파일 선택이 완료되지 않았습니다. 다시 선택해 주세요.')
            return
          }
          clearParentUploadResume(consentToken)
          setCurrentAudioFile(file)
        }}
      />

    </div>
  )
}
