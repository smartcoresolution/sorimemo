import { useEffect, useRef, useState } from 'react'
import { CheckCircle, Download, FileAudio, Mic, Square } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { uploadVoiceSample } from '@/lib/api'

interface ChildVoiceSamplePageProps {
  consentToken: string
  onComplete: (voiceSampleId: string, durationSeconds: number) => void
}

type VoiceInputMode = 'record' | 'file' | null

type FileSystemAccessWindow = Window & {
  showOpenFilePicker?: (options?: {
    multiple?: boolean
    types?: Array<{
      description: string
      accept: Record<string, string[]>
    }>
  }) => Promise<Array<{ getFile: () => Promise<File> }>>
}

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

const CHILD_VOICE_SCRIPT = [
  '안녕하세요. 저는 부모님과의 통화 분석을 위해 제 목소리를 등록하고 있습니다.',
  '이 음성은 통화 녹음에서 제 목소리를 구분하기 위한 기준 샘플입니다.',
  '저는 평소 부모님과 전화할 때와 비슷한 속도와 크기로 말하고 있습니다.',
  '오늘 날씨와 최근에 있었던 일, 그리고 가족과 나눈 대화를 자연스럽게 떠올리며 말해 보겠습니다.',
  '이 녹음은 부모님 음성을 더 정확히 확인하기 위한 참고용으로 사용됩니다.',
]

const maxRecordingSeconds = 60
const activeConsentTokenKey = 'sorimemo_active_consent_token'
const voiceSampleStateKey = (consentToken: string) => `sorimemo_child_voice_sample:${consentToken}`
const childVoiceUploadKey = (consentToken: string) => `sorimemo_child_voice_upload:${consentToken}`
const childVoiceCompleteKey = (consentToken: string) => `sorimemo_child_voice_complete:${consentToken}`
const parentAudioUploadStateKey = (consentToken: string) => `sorimemo_parent_audio_upload:${consentToken}`
const parentAudioUploadErrorKey = (consentToken: string) => `sorimemo_parent_audio_upload_error:${consentToken}`
const parentUploadResumeKey = (consentToken: string) => `sorimemo_parent_upload_resume:${consentToken}`
const childVoiceUploadTtlMs = 10 * 60 * 1000
const childVoiceCompleteTtlMs = 30 * 60 * 1000
const qualityCheckDurationNotice = '보통 2~3분 정도 걸릴 수 있습니다.'
const qualityCheckWaitNotice = '창을 닫지 말고 잠시만 기다려 주세요.'

const markChildVoiceUpload = (consentToken: string) => {
  try {
    sessionStorage.setItem(childVoiceUploadKey(consentToken), JSON.stringify({
      expiresAt: Date.now() + childVoiceUploadTtlMs,
    }))
  } catch {
    // Upload resume markers are best-effort only.
  }
}

const clearChildVoiceUpload = (consentToken: string) => {
  try {
    sessionStorage.removeItem(childVoiceUploadKey(consentToken))
  } catch {
    // Upload resume markers are best-effort only.
  }
}

const clearChildVoiceComplete = (consentToken: string) => {
  try {
    sessionStorage.removeItem(voiceSampleStateKey(consentToken))
    sessionStorage.removeItem(childVoiceCompleteKey(consentToken))
  } catch {
    // Completion markers are best-effort only.
  }
}

const clearParentUploadState = (consentToken: string) => {
  try {
    sessionStorage.removeItem(parentAudioUploadStateKey(consentToken))
    sessionStorage.removeItem(parentAudioUploadErrorKey(consentToken))
    sessionStorage.removeItem(parentUploadResumeKey(consentToken))
  } catch {
    // Parent upload state is best-effort only.
  }
}

const markChildVoiceComplete = (consentToken: string, sampleId: string, durationSeconds: number) => {
  try {
    sessionStorage.setItem(childVoiceCompleteKey(consentToken), JSON.stringify({
      sampleId,
      durationSeconds,
      expiresAt: Date.now() + childVoiceCompleteTtlMs,
    }))
  } catch {
    // Completion markers are best-effort only.
  }
}

const getActiveConsentToken = () => {
  try {
    return sessionStorage.getItem(activeConsentTokenKey) || ''
  } catch {
    return ''
  }
}

export default function ChildVoiceSamplePage({ consentToken, onComplete }: ChildVoiceSamplePageProps) {
  const effectiveConsentToken = consentToken || getActiveConsentToken()
  const [voiceFile, setVoiceFile] = useState<File | null>(null)
  const [voiceSampleId, setVoiceSampleId] = useState('')
  const [voiceSampleDurationSeconds, setVoiceSampleDurationSeconds] = useState(0)
  const [uploadingVoice, setUploadingVoice] = useState(false)
  const [voiceUploadStatus, setVoiceUploadStatus] = useState('')
  const [voiceDownloadUrl, setVoiceDownloadUrl] = useState('')
  const [voiceInputMode, setVoiceInputMode] = useState<VoiceInputMode>(null)
  const [recording, setRecording] = useState(false)
  const [recordingPaused, setRecordingPaused] = useState(false)
  const [recordingSeconds, setRecordingSeconds] = useState(0)
  const [error, setError] = useState('')
  const [qualityFailureReason, setQualityFailureReason] = useState('')

  const sharedAudioInputRef = useRef<HTMLInputElement>(null)
  const voiceRecordInputRef = useRef<HTMLInputElement>(null)
  const recorderRef = useRef<MediaRecorder | null>(null)
  const streamRef = useRef<MediaStream | null>(null)
  const chunksRef = useRef<BlobPart[]>([])
  const recordingTimerRef = useRef<number | null>(null)

  useEffect(() => {
    try {
      if (!effectiveConsentToken) return
      const active = JSON.parse(sessionStorage.getItem(childVoiceUploadKey(effectiveConsentToken)) || 'null') as {
        expiresAt?: number
      } | null
      if (active?.expiresAt && active.expiresAt > Date.now()) {
        setVoiceUploadStatus('자녀 음성 등록 화면으로 돌아왔습니다. 등록이 완료되지 않았다면 같은 파일을 다시 선택해 주세요.')
        clearChildVoiceUpload(effectiveConsentToken)
      }
    } catch {
      // Restoring upload state is best-effort.
    }
  }, [effectiveConsentToken])

  useEffect(() => {
    return () => {
      if (recordingTimerRef.current) window.clearInterval(recordingTimerRef.current)
      streamRef.current?.getTracks().forEach(track => track.stop())
      if (voiceDownloadUrl) URL.revokeObjectURL(voiceDownloadUrl)
    }
  }, [voiceDownloadUrl])

  const setCurrentVoiceFile = (file: File, mode: Exclude<VoiceInputMode, null> = 'file') => {
    if (voiceDownloadUrl) URL.revokeObjectURL(voiceDownloadUrl)
    if (effectiveConsentToken) {
      clearChildVoiceUpload(effectiveConsentToken)
      clearChildVoiceComplete(effectiveConsentToken)
      clearParentUploadState(effectiveConsentToken)
    }
    setVoiceFile(file)
    setVoiceDownloadUrl(URL.createObjectURL(file))
    setVoiceInputMode(mode)
    setVoiceSampleId('')
    setVoiceSampleDurationSeconds(0)
    setVoiceUploadStatus('')
    setError('')
    setQualityFailureReason('')
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

  const stopVoiceTracks = () => {
    streamRef.current?.getTracks().forEach(track => track.stop())
    streamRef.current = null
  }

  const clearRecordingTimer = () => {
    if (recordingTimerRef.current) {
      window.clearInterval(recordingTimerRef.current)
      recordingTimerRef.current = null
    }
  }

  const finishChildRecording = () => {
    recorderRef.current?.stop()
    recorderRef.current = null
    setRecording(false)
    setRecordingPaused(false)
    clearRecordingTimer()
  }

  const startRecordingTimer = () => {
    clearRecordingTimer()
    recordingTimerRef.current = window.setInterval(() => {
      setRecordingSeconds(prev => {
        const next = Math.min(prev + 1, maxRecordingSeconds)
        if (next >= maxRecordingSeconds) {
          finishChildRecording()
        }
        return next
      })
    }, 1000)
  }

  const prepareChildRecording = () => {
    setError('')
    setQualityFailureReason('')
    setVoiceUploadStatus('')
    setVoiceInputMode('record')
    setVoiceFile(null)
    setVoiceSampleId('')
    setVoiceSampleDurationSeconds(0)
    setRecordingSeconds(0)
    setRecordingPaused(false)
    if (voiceDownloadUrl) {
      URL.revokeObjectURL(voiceDownloadUrl)
      setVoiceDownloadUrl('')
    }
  }

  const startChildRecording = async () => {
    setError('')
    setQualityFailureReason('')
    if (voiceDownloadUrl) {
      URL.revokeObjectURL(voiceDownloadUrl)
      setVoiceDownloadUrl('')
    }
    setVoiceFile(null)
    setVoiceSampleId('')
    setVoiceSampleDurationSeconds(0)
    setVoiceUploadStatus('')
    setVoiceInputMode('record')
    if (!navigator.mediaDevices?.getUserMedia || typeof MediaRecorder === 'undefined') {
      voiceRecordInputRef.current?.click()
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
        setCurrentVoiceFile(new File([blob], `sorimemo_child_voice_${Date.now()}.webm`, { type: blob.type }), 'record')
        stopVoiceTracks()
      }

      recorderRef.current = recorder
      recorder.start()
      setRecording(true)
      setRecordingPaused(false)
      setRecordingSeconds(0)
      startRecordingTimer()
    } catch {
      setError('마이크 권한을 확인해 주세요. 권한이 어려우면 음성파일 선택을 이용해 주세요.')
      setVoiceInputMode(null)
      setRecording(false)
      setRecordingPaused(false)
      stopVoiceTracks()
    }
  }

  const pauseChildRecording = () => {
    if (recorderRef.current?.state === 'recording') {
      recorderRef.current.pause()
      setRecordingPaused(true)
      clearRecordingTimer()
    }
  }

  const resumeChildRecording = () => {
    if (recorderRef.current?.state === 'paused') {
      recorderRef.current.resume()
      setRecordingPaused(false)
      startRecordingTimer()
    }
  }

  const stopChildRecording = () => {
    finishChildRecording()
  }

  const pickAudioFile = async () => {
    const filePicker = (window as FileSystemAccessWindow).showOpenFilePicker
    if (filePicker) {
      try {
        const [handle] = await filePicker({
          multiple: false,
          types: [{ description: '음성 파일', accept: audioPickerAccept }],
        })
        if (handle) return await handle.getFile()
      } catch (error) {
        if (error instanceof DOMException && error.name === 'AbortError') return null
      }
    }
    sharedAudioInputRef.current?.click()
    return null
  }

  const openVoiceFileSearch = async () => {
    setVoiceInputMode('file')
    setVoiceUploadStatus('')
    setError('')
    setQualityFailureReason('')
    if (!effectiveConsentToken) {
      setError('유효한 동의 토큰이 없습니다. 동의 절차를 다시 완료해 주세요.')
      return
    }
    const file = await pickAudioFile()
    if (file) {
      setCurrentVoiceFile(file, 'file')
      void handleVoiceUpload(file)
    }
  }

  const handleVoiceUpload = async (selectedFile = voiceFile) => {
    if (!selectedFile) return
    if (!effectiveConsentToken) {
      setError('유효한 동의 토큰이 없습니다. 동의 절차를 다시 완료해 주세요.')
      return
    }
    setUploadingVoice(true)
    markChildVoiceUpload(effectiveConsentToken)
    setVoiceUploadStatus('자녀 음성 샘플 품질을 확인하고 등록하고 있습니다.')
    setError('')
    setQualityFailureReason('')
    try {
      const result = await uploadVoiceSample(selectedFile, effectiveConsentToken)
      const durationSeconds = Number(result.duration_seconds || 0)
      setVoiceSampleId(result.sample_id)
      setVoiceSampleDurationSeconds(durationSeconds)
      setVoiceUploadStatus('품질검사가 완료되었고 자녀 음성 샘플이 등록되었습니다.')
      sessionStorage.setItem(voiceSampleStateKey(effectiveConsentToken), JSON.stringify({
        sampleId: result.sample_id,
        durationSeconds,
        originalDurationSeconds: Number(result.original_duration_seconds || durationSeconds || 0),
        wasTrimmed: Boolean(result.was_trimmed),
        status: result.message || '자녀 음성 샘플 등록이 완료되었습니다.',
      }))
      markChildVoiceComplete(effectiveConsentToken, result.sample_id, durationSeconds)
    } catch (e) {
      setVoiceUploadStatus('')
      setVoiceSampleId('')
      setVoiceSampleDurationSeconds(0)
      const detail = e instanceof Error ? e.message : '음성 샘플 등록에 실패했습니다.'
      setQualityFailureReason(detail)
    } finally {
      setUploadingVoice(false)
      clearChildVoiceUpload(effectiveConsentToken)
    }
  }

  const proceedToParentAudioUpload = () => {
    if (!voiceSampleId) return
    onComplete(voiceSampleId, voiceSampleDurationSeconds)
  }

  return (
    <div className="space-y-3 pt-1">
      <section className="overflow-hidden rounded-[24px] bg-[#0d777c] p-4 text-white shadow-lg shadow-teal-900/15">
        <div className="space-y-2 rounded-2xl bg-white/12 px-4 py-4 text-[16px] font-bold leading-[1.42] text-white">
          {CHILD_VOICE_SCRIPT.map(line => (
            <p key={line}>{line}</p>
          ))}
        </div>

        {recording && (
          <div className="mt-4 rounded-2xl bg-white/12 px-4 py-3">
            <div className="flex items-center justify-between text-[14px] font-black text-white">
              <span>{recordingPaused ? '녹음 일시정지' : '녹음 중'}</span>
              <span className="tabular-nums">{recordingSeconds}s / {maxRecordingSeconds}s</span>
            </div>
            <div className="mt-3 h-2 overflow-hidden rounded-full bg-white/25">
              <div
                className="h-full rounded-full bg-white transition-all"
                style={{ width: `${Math.min(100, Math.max(6, (recordingSeconds / maxRecordingSeconds) * 100))}%` }}
              />
            </div>
          </div>
        )}

        {recording ? (
          <div className="mt-4 grid grid-cols-2 gap-2">
            <Button
              variant="outline"
              onClick={recordingPaused ? resumeChildRecording : pauseChildRecording}
              className="h-14 rounded-full border-white/30 bg-white/10 text-[16px] font-black text-white shadow-none hover:bg-white/20"
            >
              {recordingPaused ? <Mic className="mr-2 h-5 w-5" /> : <Square className="mr-2 h-5 w-5" />}
              {recordingPaused ? '계속 녹음' : '녹음 멈춤'}
            </Button>
            <Button
              onClick={stopChildRecording}
              className="h-14 rounded-full bg-white text-[16px] font-black text-[#0d777c] shadow-none hover:bg-[#eef8f6]"
            >
              <CheckCircle className="mr-2 h-5 w-5" />
              녹음 끝내기
            </Button>
          </div>
        ) : !voiceInputMode && !voiceFile ? (
          <div className="mt-4 space-y-2">
            <Button
              onClick={prepareChildRecording}
              className="h-16 w-full justify-center rounded-full bg-white px-5 text-[18px] font-black text-[#0d777c] shadow-none hover:bg-[#eef8f6]"
            >
              <Mic className="mr-2 h-6 w-6 shrink-0" />
              자녀 목소리 녹음
            </Button>
            <Button
              variant="outline"
              onClick={openVoiceFileSearch}
              className="h-16 w-full justify-center rounded-full border-white/30 bg-white/10 px-5 text-[18px] font-black text-white shadow-none hover:bg-white/20"
            >
              <FileAudio className="mr-2 h-6 w-6 shrink-0" />
              음성파일 선택
            </Button>
          </div>
        ) : voiceInputMode === 'record' && !voiceFile ? (
          <div className="mt-4 space-y-2">
            <Button
              onClick={startChildRecording}
              className="h-16 w-full justify-center rounded-full bg-white px-5 text-[18px] font-black text-[#0d777c] shadow-none hover:bg-[#eef8f6]"
            >
              <Mic className="mr-2 h-6 w-6 shrink-0" />
              녹음 시작
            </Button>
          </div>
        ) : null}

        {voiceFile && (voiceInputMode === 'record' || voiceInputMode === 'file') && (
          <div className="mt-3 space-y-2">
            {!voiceSampleId ? (
              <Button
                onClick={() => void handleVoiceUpload()}
                disabled={uploadingVoice}
                className="h-14 w-full rounded-full bg-white px-5 text-[17px] font-black text-[#0d777c] shadow-none hover:bg-[#eef8f6]"
              >
                {uploadingVoice ? '품질검사 중' : '선택된 음성 샘플 등록'}
              </Button>
            ) : (
              <>
                {voiceDownloadUrl && voiceInputMode === 'record' && (
                  <Button
                    type="button"
                    variant="outline"
                    onClick={downloadVoiceFile}
                    className="h-14 w-full rounded-full border-white/25 bg-white/10 px-5 text-[16px] font-black text-white shadow-none hover:bg-white/20"
                  >
                    <Download className="mr-2 h-5 w-5" />
                    품질검사 완료 음성 다운로드
                  </Button>
                )}
                <Button
                  onClick={proceedToParentAudioUpload}
                  className="h-14 w-full rounded-full bg-white px-5 text-[17px] font-black text-[#0d777c] shadow-none hover:bg-[#eef8f6]"
                >
                  부모님 대화 등록
                </Button>
              </>
            )}
          </div>
        )}
        {voiceUploadStatus && (
          <div className="mt-3 rounded-2xl bg-white/10 px-4 py-3 text-center text-white">
            <p className="text-[18px] font-black leading-[1.42]">
              {voiceUploadStatus}
            </p>
            {uploadingVoice && (
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
        {qualityFailureReason && (
          <div className="mt-3 rounded-2xl bg-red-50 px-4 py-4 text-[#7f1d1d]">
            <p className="text-[18px] font-black">품질검사를 통과하지 못했습니다.</p>
            <p className="mt-2 text-[17px] font-bold leading-[1.5]">
              사유: {qualityFailureReason}
            </p>
            <p className="mt-2 text-[17px] font-bold leading-[1.5]">
              조용한 곳에서 자녀 본인의 목소리로 30~60초 정도 다시 녹음해 주세요.
            </p>
            <Button
              type="button"
              onClick={() => {
                if (voiceInputMode === 'record') {
                  prepareChildRecording()
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
      </section>

      <input
        ref={voiceRecordInputRef}
        type="file"
        accept="audio/*"
        capture
        className="hidden"
        onChange={e => {
          const file = e.target.files?.[0]
          if (file) {
            clearChildVoiceUpload(effectiveConsentToken)
            setCurrentVoiceFile(file, 'record')
          }
        }}
      />
      <input
        ref={sharedAudioInputRef}
        type="file"
        className="hidden"
        onClick={e => {
          e.currentTarget.value = ''
        }}
        onChange={e => {
          const file = e.target.files?.[0]
          if (file) {
            clearChildVoiceUpload(effectiveConsentToken)
            setCurrentVoiceFile(file, 'file')
            void handleVoiceUpload(file)
          }
        }}
      />

      {error && <p className="rounded-xl bg-red-50 px-4 py-3 text-center text-[17px] font-bold leading-[1.5] text-red-600">{error}</p>}
    </div>
  )
}
