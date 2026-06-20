const API_URL = import.meta.env.VITE_API_URL || "";
const USER_TOKEN_KEY = "sorimemo_user_token";
const ADMIN_TOKEN_KEY = "sorimemo_admin_token";

// ---------- fallback demo data ----------
const DEMO_POLICY = {
  version: "1.0.0",
  title: "안심소리 기억케어 데이터 처리 및 개인정보 보호 정책",
  sections: [
    { title: "서비스 목적", content: "안심소리 기억케어는 자녀가 업로드한 부모님과의 자연스러운 통화 음성을 분석하여 인지기능 변화와 연관될 수 있는 위험 신호를 비의료적으로 선별하는 참고용 서비스입니다. 본 서비스는 의료 진단을 목적으로 하지 않습니다." },
    { title: "데이터 수집 범위", content: "자녀 음성 샘플과 통화 녹음 파일을 수집합니다. 자녀 음성은 통화 속 자녀 화자를 구분하는 데 사용됩니다." },
    { title: "데이터 보관 및 삭제", content: "원본 음성 파일은 분석 완료 후 즉시 삭제되며, 익명화된 특징 데이터는 최대 90일간 보관 후 자동 삭제됩니다." },
    { title: "화자 분리 안내", content: "통화 녹음에는 자녀와 부모님의 음성이 함께 포함될 수 있습니다. 등록된 자녀 음성과 일치하는 화자는 분석에서 제외하고, 부모님 음성을 분석합니다." },
    { title: "AI 모델 개선 및 연구 활용", content: "선택 동의한 경우에만 업로드 음성, 분석 결과, 연령대, 성별, 검증 유형 정보가 개인 식별정보 제거 또는 가명처리 후 SoriMemo AI 모델 개선과 품질 평가 목적으로 활용될 수 있습니다. 동의하지 않아도 서비스 이용에는 제한이 없습니다." },
    { title: "비의료적 서비스 고지", content: "본 서비스의 분석 결과는 의료적 진단이나 치료 판단이 아닌, 인지기능 변화와 연관될 수 있는 위험 신호를 참고용으로 제공하는 비의료적 정보입니다." },
  ],
  consent_items: [
    { key: "data_collection", label: "자녀 음성 샘플과 통화 녹음 파일의 분석 처리에 동의합니다.", required: true },
    { key: "privacy_policy", label: "개인정보 처리 방침에 동의합니다.", required: true },
    { key: "non_medical_disclaimer", label: "비의료적 서비스임을 이해하고 동의합니다.", required: true },
    { key: "third_party_voice", label: "통화에 부모님 음성이 포함되며 자녀 음성을 제외한 뒤 분석함을 이해합니다.", required: true },
    { key: "model_training", label: "AI 모델 개선 및 연구 활용에 동의합니다. 개인 식별정보 제거 또는 가명처리 후 학습 품질 개선 목적으로 활용될 수 있습니다. 이 항목은 선택 사항입니다.", required: false },
  ],
};

async function tryFetch(url: string, init?: RequestInit, timeoutMs = 0): Promise<Response> {
  const controller = timeoutMs > 0 ? new AbortController() : null;
  const timeoutId = controller
    ? window.setTimeout(() => controller.abort(), timeoutMs)
    : null;

  try {
    const res = await fetch(url, {
      ...init,
      signal: controller?.signal ?? init?.signal,
    });
    return res;
  } catch (error) {
    if (error instanceof DOMException && error.name === "AbortError") {
      throw new Error("서버 응답이 지연되고 있습니다. 파일 크기나 네트워크 상태를 확인한 뒤 다시 시도해 주세요.");
    }
    throw new Error("서버와 연결할 수 없습니다. 백엔드 실행 상태와 API 주소를 확인해 주세요.");
  } finally {
    if (timeoutId) window.clearTimeout(timeoutId);
  }
}

async function responseErrorMessage(res: Response, fallback: string): Promise<string> {
  const contentType = res.headers.get("content-type") || "";
  if (contentType.includes("application/json")) {
    try {
      const err = await res.json();
      return err.detail || err.message || fallback;
    } catch {
      return fallback;
    }
  }
  if (res.status === 413) return "파일 크기가 서버 허용 범위를 초과했습니다. 더 짧은 파일로 다시 시도해 주세요.";
  if (res.status === 415) return "지원하지 않는 음성 파일 형식입니다. m4a, wav, mp3, 3ga, amr 파일로 다시 시도해 주세요.";
  if (res.status >= 500) return "서버에서 파일 처리 중 오류가 발생했습니다. 잠시 후 다시 시도해 주세요.";
  return `${fallback} (HTTP ${res.status})`;
}

async function parseJsonResponse(res: Response, fallback: string) {
  const text = await res.text();
  if (!res.ok) {
    throw new Error(responseErrorTextMessage(res, text, fallback));
  }
  try {
    return JSON.parse(text);
  } catch {
    throw new Error("서버 응답 형식이 올바르지 않습니다. 잠시 후 다시 시도해 주세요.");
  }
}

function responseErrorTextMessage(res: Response, body: string, fallback: string): string {
  const contentType = res.headers.get("content-type") || "";
  if (contentType.includes("application/json")) {
    try {
      const err = JSON.parse(body);
      return err.detail || err.message || fallback;
    } catch {
      return fallback;
    }
  }
  if (res.status === 413) return "파일 크기가 서버 허용 범위를 초과했습니다. 더 짧은 파일로 다시 시도해 주세요.";
  if (res.status === 415) return "지원하지 않는 음성 파일 형식입니다. m4a, wav, mp3, 3ga, amr 파일로 다시 시도해 주세요.";
  if (res.status >= 500) return `서버에서 파일 처리 중 오류가 발생했습니다. 잠시 후 다시 시도해 주세요. (HTTP ${res.status})`;
  return `${fallback} (HTTP ${res.status})`;
}

function authHeaders(extra?: Record<string, string>) {
  const token = localStorage.getItem(USER_TOKEN_KEY);
  return {
    ...(extra || {}),
    ...(token ? { Authorization: `Bearer ${token}` } : {}),
  };
}

function storeAuthPayload(payload: any) {
  if (payload?.access_token) {
    localStorage.setItem(USER_TOKEN_KEY, payload.access_token);
  }
  return payload;
}

export function clearUserSession() {
  localStorage.removeItem(USER_TOKEN_KEY);
}

export function hasUserSession() {
  return Boolean(localStorage.getItem(USER_TOKEN_KEY));
}

// ---------- public API ----------

export async function fetchPolicy() {
  try {
    const res = await tryFetch(`${API_URL}/api/consent/policy`);
    if (!res.ok) throw new Error("Failed to fetch policy");
    return res.json();
  } catch {
    return DEMO_POLICY;
  }
}

export async function submitConsent(data: {
  user_name?: string;
  age_group: string;
  subject_type?: "self" | "parent";
  subject_relation?: string;
  subject_display_name?: string;
  subject_age_group?: string;
  subject_gender?: string;
  data_collection_agreed: boolean;
  privacy_policy_agreed: boolean;
  non_medical_disclaimer_agreed: boolean;
  third_party_voice_agreed: boolean;
  model_training_agreed?: boolean;
}) {
  try {
    const res = await tryFetch(`${API_URL}/api/consent/agree`, {
      method: "POST",
      headers: authHeaders({ "Content-Type": "application/json" }),
      body: JSON.stringify(data),
    });
    if (!res.ok) {
      const err = await res.json();
      throw new Error(err.detail || "Consent failed");
    }
    return res.json();
  } catch (error) {
    throw error instanceof Error ? error : new Error("동의 처리 중 오류가 발생했습니다.");
  }
}

export async function saveConsentSubject(consentToken: string, data: {
  subject_type: "self" | "parent";
  subject_relation?: string;
  subject_display_name: string;
  subject_age_group: string;
  subject_gender?: string;
}) {
  const res = await tryFetch(`${API_URL}/api/consent/${consentToken}/subject`, {
    method: "POST",
    headers: authHeaders({ "Content-Type": "application/json" }),
    body: JSON.stringify(data),
  });
  return parseJsonResponse(res, "검증 대상자 정보 저장에 실패했습니다.");
}

export async function signupAccount(data: {
  email: string;
  password: string;
  age_group: string;
  display_name?: string;
  signup_purpose?: string;
}) {
  const res = await tryFetch(`${API_URL}/api/auth/signup`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data),
  });
  return storeAuthPayload(await parseJsonResponse(res, "회원가입에 실패했습니다."));
}

export async function loginAccount(data: {
  email: string;
  password: string;
}) {
  const res = await tryFetch(`${API_URL}/api/auth/login`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data),
  });
  return storeAuthPayload(await parseJsonResponse(res, "로그인에 실패했습니다."));
}

export async function requestPasswordReset(email: string) {
  const res = await tryFetch(`${API_URL}/api/auth/password-reset/request`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email }),
  });
  return parseJsonResponse(res, "비밀번호 재설정 요청에 실패했습니다.");
}

export async function confirmPasswordReset(data: {
  email: string;
  reset_token: string;
  new_password: string;
}) {
  const res = await tryFetch(`${API_URL}/api/auth/password-reset/confirm`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data),
  });
  return parseJsonResponse(res, "비밀번호 재설정에 실패했습니다.");
}

export async function uploadAudio(file: File, consentToken: string, options?: {
  voiceSampleId?: string;
  uploadContext?: "parent_call" | "self_voice";
}) {
  const formData = new FormData();
  formData.append("file", file);
  const debugBase = {
    filename: file.name,
    size: file.size,
    type: file.type,
    consentTokenPrefix: consentToken.slice(0, 8),
    startedAt: new Date().toISOString(),
  };
  sessionStorage.setItem("sorimemo_last_upload_debug", JSON.stringify({
    ...debugBase,
    stage: "request_start",
  }));
  try {
    const res = await tryFetch(`${API_URL}/api/upload/audio`, {
      method: "POST",
      headers: authHeaders({
        "X-Consent-Token": consentToken,
        ...(options?.uploadContext ? { "X-Upload-Context": options.uploadContext } : {}),
        ...(options?.voiceSampleId ? { "X-Voice-Sample-Id": options.voiceSampleId } : {}),
      }),
      body: formData,
    }, 180000);
    const responseText = await res.text();
    sessionStorage.setItem("sorimemo_last_upload_debug", JSON.stringify({
      ...debugBase,
      stage: "response",
      status: res.status,
      ok: res.ok,
      body: responseText.slice(0, 600),
      receivedAt: new Date().toISOString(),
    }));
    if (!res.ok) {
      throw new Error(responseErrorTextMessage(res, responseText, "통화 파일 업로드에 실패했습니다."));
    }
    const result = JSON.parse(responseText);
    const uploadStateKey = options?.uploadContext === "self_voice"
      ? `sorimemo_self_voice_audio_upload:${consentToken}`
      : `sorimemo_parent_audio_upload:${consentToken}`;
    const uploadErrorKey = options?.uploadContext === "self_voice"
      ? `sorimemo_self_voice_audio_upload_error:${consentToken}`
      : `sorimemo_parent_audio_upload_error:${consentToken}`;
    if (result.quality_report?.quality_pass) {
      sessionStorage.setItem(uploadStateKey, JSON.stringify({
        fileId: result.file_id,
        fileName: file.name,
        fileSizeMb: (file.size / 1024 / 1024).toFixed(1),
        quality: result.quality_report,
      }));
    } else {
      sessionStorage.removeItem(uploadStateKey);
    }
    sessionStorage.removeItem(uploadErrorKey);
    return result;
  } catch (error) {
    sessionStorage.setItem("sorimemo_last_upload_debug", JSON.stringify({
      ...debugBase,
      stage: "error",
      message: error instanceof Error ? error.message : String(error),
      failedAt: new Date().toISOString(),
    }));
    throw error instanceof Error ? error : new Error("통화 파일 업로드 중 오류가 발생했습니다.");
  }
}

export async function fetchLatestAudioUpload(consentToken: string, uploadStartedAt?: string) {
  const res = await tryFetch(`${API_URL}/api/upload/audio/latest`, {
    method: "GET",
    headers: authHeaders({
      "X-Consent-Token": consentToken,
      ...(uploadStartedAt ? { "X-Upload-Started-At": uploadStartedAt } : {}),
    }),
  }, 30000);
  if (!res.ok) {
    throw new Error(await responseErrorMessage(res, "최근 통화녹음 업로드 결과를 찾을 수 없습니다."));
  }
  return res.json();
}

export async function uploadVoiceSample(file: File, consentToken: string) {
  const formData = new FormData();
  formData.append("file", file);
  try {
    const res = await tryFetch(`${API_URL}/api/upload/voice-sample`, {
      method: "POST",
      headers: authHeaders({ "X-Consent-Token": consentToken }),
      body: formData,
    }, 180000);
    if (!res.ok) {
      throw new Error(await responseErrorMessage(res, "자녀 음성 등록에 실패했습니다."));
    }
    return res.json();
  } catch (error) {
    throw error instanceof Error ? error : new Error("자녀 음성 등록 중 오류가 발생했습니다.");
  }
}

export async function startAnalysis(fileId: string, voiceSampleId?: string) {
  let url = `${API_URL}/api/analysis/start/${fileId}`;
  if (voiceSampleId) url += `?voice_sample_id=${voiceSampleId}&voice_sample_role=exclude`;
  try {
    const res = await tryFetch(url, {
      method: "POST",
      headers: authHeaders(),
    });
    if (!res.ok) {
      const err = await res.json();
      throw new Error(err.detail || "Analysis failed");
    }
    return res.json();
  } catch (error) {
    throw error instanceof Error ? error : new Error("분석 시작 중 오류가 발생했습니다.");
  }
}

export async function startAnalysisJob(fileId: string, voiceSampleId?: string, verificationType = "parent_call") {
  let url = `${API_URL}/api/analysis/jobs/start/${fileId}`;
  const params = new URLSearchParams({ verification_type: verificationType });
  if (voiceSampleId) {
    params.set("voice_sample_id", voiceSampleId);
    params.set("voice_sample_role", "exclude");
  }
  url += `?${params.toString()}`;
  const res = await tryFetch(url, {
    method: "POST",
    headers: authHeaders(),
  });
  if (!res.ok) {
    const err = await res.json();
    if (res.status === 404 || res.status === 410) {
      throw new Error(err.detail || "이전 업로드 파일을 찾을 수 없습니다. 통화 파일을 다시 업로드해 주세요.");
    }
    throw new Error(err.detail || "Analysis job failed");
  }
  return res.json();
}

export async function getAnalysisJobStatus(jobId: string) {
  const res = await tryFetch(`${API_URL}/api/analysis/jobs/${jobId}`, {
    headers: authHeaders(),
  });
  if (!res.ok) {
    const err = await res.json();
    if (res.status === 404 || res.status === 410) {
      throw new Error(err.detail || "분석 작업을 찾을 수 없습니다. 파일을 다시 업로드해 주세요.");
    }
    throw new Error(err.detail || "Failed to fetch analysis job");
  }
  return res.json();
}

export async function loginAdmin(data: {
  admin_id: string;
  password: string;
}) {
  const res = await tryFetch(`${API_URL}/api/admin/login`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data),
  });
  const payload = await parseJsonResponse(res, "관리자 ID 또는 비밀번호를 확인해 주세요.");
  localStorage.removeItem(ADMIN_TOKEN_KEY);
  sessionStorage.setItem(ADMIN_TOKEN_KEY, payload.access_token);
  return payload;
}

export function clearAdminSession() {
  localStorage.removeItem(ADMIN_TOKEN_KEY);
  sessionStorage.removeItem(ADMIN_TOKEN_KEY);
}

export function hasAdminSession() {
  return Boolean(sessionStorage.getItem(ADMIN_TOKEN_KEY));
}

function adminAuthHeaders(): Record<string, string> {
  const token = sessionStorage.getItem(ADMIN_TOKEN_KEY);
  return token ? { Authorization: `Bearer ${token}` } : {};
}

export async function getAdminDashboard() {
  try {
    const res = await tryFetch(`${API_URL}/api/admin/dashboard?_=${Date.now()}`, {
      cache: "no-store",
      headers: {
        ...adminAuthHeaders(),
        "Cache-Control": "no-cache",
      },
    });
    if (res.status === 401) {
      clearAdminSession();
      throw new Error("관리자 로그인이 필요합니다.");
    }
    return parseJsonResponse(res, "관리자 정보를 불러오지 못했습니다.");
  } catch (error) {
    throw error instanceof Error ? error : new Error("관리자 정보를 불러오지 못했습니다.");
  }
}

export async function runAdminRetentionCleanup() {
  const res = await tryFetch(`${API_URL}/api/admin/retention/cleanup`, {
    method: "POST",
    headers: adminAuthHeaders(),
  });
  if (res.status === 401) {
    clearAdminSession();
    throw new Error("관리자 로그인이 필요합니다.");
  }
  return parseJsonResponse(res, "보관 기간 정리 작업을 실행하지 못했습니다.");
}

export async function getResults(analysisId: string) {
  try {
    const res = await tryFetch(`${API_URL}/api/results/${analysisId}`, {
      headers: authHeaders(),
    });
    if (!res.ok) {
      throw new Error(await responseErrorMessage(res, "결과를 불러오지 못했습니다."));
    }
    return res.json();
  } catch (error) {
    throw error instanceof Error ? error : new Error("결과를 불러오지 못했습니다.");
  }
}

export async function getResultsSummary(analysisId: string) {
  const res = await tryFetch(`${API_URL}/api/results/${analysisId}/summary`, {
    headers: authHeaders(),
  });
  if (!res.ok) throw new Error("Failed to fetch summary");
  return res.json();
}

export async function getResultsHistory(limit = 10) {
  const res = await tryFetch(`${API_URL}/api/results/history?limit=${limit}`, {
    headers: authHeaders(),
  });
  if (!res.ok) throw new Error("Failed to fetch history");
  return res.json();
}

export async function deleteResultHistoryItem(analysisId: string) {
  const res = await tryFetch(`${API_URL}/api/results/${analysisId}`, {
    method: "DELETE",
    headers: authHeaders(),
  });
  if (!res.ok) {
    const err = await res.json();
    throw new Error(err.detail || "Failed to delete history item");
  }
  return res.json();
}
