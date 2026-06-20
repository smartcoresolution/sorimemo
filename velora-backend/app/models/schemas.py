from pydantic import BaseModel, Field
from typing import Optional
from enum import Enum


class AgeGroup(str, Enum):
    FORTIES = "40s"
    FIFTIES = "50s"
    SIXTIES = "60s"
    SEVENTIES = "70s"
    EIGHTIES = "80s"
    NINETIES = "90s"
    OTHER = "other"


class RiskLevel(str, Enum):
    LOW = "low"
    MIDDLE = "middle"
    HIGH = "high"


class CognitiveStatus(str, Enum):
    NORMAL = "Normal"
    MCI = "MCI"
    AD = "AD"


class ConsentRequest(BaseModel):
    user_name: Optional[str] = Field(default=None, description="사용자 이름")
    age_group: AgeGroup
    subject_type: str = Field(default="parent", description="검증 대상 유형: self 또는 parent")
    subject_relation: Optional[str] = Field(default=None, description="가입자와 대상자의 관계")
    subject_display_name: Optional[str] = Field(default=None, description="검증 대상 표시명")
    subject_age_group: AgeGroup = AgeGroup.OTHER
    subject_gender: Optional[str] = Field(default=None, description="검증 대상 성별")
    data_collection_agreed: bool = Field(..., description="동의: 데이터 수집 및 분석")
    privacy_policy_agreed: bool = Field(..., description="동의: 개인정보 처리 방침")
    non_medical_disclaimer_agreed: bool = Field(..., description="동의: 비의료적 서비스 고지")
    third_party_voice_agreed: bool = Field(..., description="동의: 제3자 음성 포함 가능성")
    model_training_agreed: bool = Field(default=False, description="선택 동의: AI 모델 개선 및 연구 활용")


class ConsentResponse(BaseModel):
    consent_token: str
    policy_version: str
    retention_period_days: int
    message: str


class QualityReport(BaseModel):
    duration_seconds: float
    snr_db: float
    silence_ratio: float
    sample_rate: int
    channels: int
    format_original: str
    quality_pass: bool
    rejection_reason: Optional[str] = None
    original_duration_seconds: Optional[float] = None
    trimmed_to_seconds: Optional[float] = None
    was_trimmed: bool = False
    speech_duration_seconds: Optional[float] = None
    rms_dbfs: Optional[float] = None
    child_voice_present: Optional[bool] = None
    child_voice_duration_seconds: Optional[float] = None
    parent_voice_duration_seconds: Optional[float] = None
    detected_speaker_count: Optional[int] = None
    diarization_confidence: Optional[float] = None
    voice_sample_distance: Optional[float] = None
    voice_sample_similarity: Optional[float] = None
    self_voice_prompt_checked: Optional[bool] = None
    self_voice_prompt_match_score: Optional[float] = None
    self_voice_prompt_keyword_coverage: Optional[float] = None
    self_voice_prompt_stt_confidence: Optional[float] = None
    self_voice_prompt_transcript_char_count: Optional[int] = None


class UploadResponse(BaseModel):
    file_id: str
    quality_report: QualityReport
    message: str
    file_name: Optional[str] = None
    file_size_mb: Optional[str] = None


class SpeakerSegment(BaseModel):
    speaker: str
    start_time: float
    end_time: float
    duration: float


class DiarizationResult(BaseModel):
    total_speakers: int
    target_speaker: str
    target_segments: list[SpeakerSegment]
    excluded_segments: list[SpeakerSegment]
    diarization_confidence: float


class SpeechStatistics(BaseModel):
    total_speech_duration: float
    silence_ratio: float
    speech_density: float
    mean_utterance_length: float
    utterance_count: int


class AcousticFeatures(BaseModel):
    mfcc_mean: list[float]
    mfcc_std: list[float]
    pitch_mean: float
    pitch_std: float
    pitch_range: float
    energy_mean: float
    energy_std: float
    energy_variability: float
    speech_rate: float
    prosody_stability: float
    spectral_centroid_mean: float
    spectral_bandwidth_mean: float
    zero_crossing_rate: float


class LinguisticFeatures(BaseModel):
    transcript_available: bool
    vocabulary_diversity: float
    average_sentence_length: float
    repeated_word_ratio: float
    noun_verb_ratio: float
    fluency_marker_count: int
    figurative_expression_count: int
    language_quality_score: float
    semantic_impairment_score: float = 0.0
    semantic_severe_score: float = 0.0
    semantic_mild_score: float = 0.0
    semantic_normal_score: float = 0.0
    token_count: int = 0
    stt_available: bool = False
    stt_engine: str = "none"
    stt_confidence: float = 0.0
    transcript_char_count: int = 0
    stt_language: str = ""
    stt_note: str = ""
    extraction_note: str


class FeatureExtractionResult(BaseModel):
    acoustic_features: AcousticFeatures
    linguistic_features: LinguisticFeatures
    speech_statistics: SpeechStatistics
    feature_quality_score: float


class ConfidenceBreakdown(BaseModel):
    audio_quality_score: float = Field(..., description="입력 음성 품질 점수 (0-1)")
    diarization_clarity: float = Field(..., description="화자 분리 명확도 (0-1)")
    model_certainty: float = Field(..., description="AI 모델 확실성 (1 - entropy) (0-1)")


class ModelProbabilities(BaseModel):
    Normal: float
    MCI: float
    AD: float


class AnalysisResult(BaseModel):
    analysis_id: str
    file_id: str
    cognitive_status: CognitiveStatus = Field(..., description="학습 모델의 최종 3분류 결과(Normal/MCI/AD)")
    cognitive_status_label: str = Field(..., description="사용자 표시용 인지 상태 라벨")
    dementia_stage: str = Field(..., description="사용자 표시용 치매 정도 안내 문구")
    risk_score: float = Field(..., description="연속형 위험 점수 (0-100)")
    risk_level: RiskLevel
    risk_level_label: str = Field(..., description="사용자 표시용 위험도 라벨")
    risk_probability: float = Field(..., description="위험 경향성 확률 (0-1)")
    model_probabilities: ModelProbabilities
    acoustic_model_probabilities: Optional[ModelProbabilities] = None
    linguistic_adjustment: Optional[dict] = None
    result_message: str
    model_source: str
    confidence_score: float = Field(..., description="종합 신뢰도 (0-1)")
    confidence_breakdown: ConfidenceBreakdown
    features: FeatureExtractionResult
    diarization: DiarizationResult
    governance: dict
    processing_time_seconds: float
    disclaimer: str


class GuidanceItem(BaseModel):
    category: str
    title: str
    description: str
    priority: int


class ResultsResponse(BaseModel):
    analysis: AnalysisResult
    guidance: list[GuidanceItem]
    risk_explanation: str
    next_steps: list[str]
    legal_notice: str


class AnalysisStatusResponse(BaseModel):
    analysis_id: str
    status: str
    progress: int
    current_step: str
    message: str


class VoiceSampleResponse(BaseModel):
    sample_id: str
    duration_seconds: float
    original_duration_seconds: Optional[float] = None
    trimmed_to_seconds: Optional[float] = None
    was_trimmed: bool = False
    message: str
