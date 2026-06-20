import re
from collections import Counter


KOREAN_PARTICLE_HINTS = ("은", "는", "이", "가", "을", "를", "의")
KOREAN_VERB_ENDINGS = ("다", "요", "죠", "네요", "습니다", "해요", "했어요")
FLUENCY_MARKERS = {"음", "어", "아", "그", "저", "그러니까", "뭐", "막"}
FIGURATIVE_MARKERS = {"처럼", "같이", "듯", "비유", "마치"}
SEVERE_COGNITIVE_PATTERNS = (
    "기억이 잘 안",
    "기억이 안",
    "잘 모르겠",
    "모르겠다",
    "모르겠어",
    "헷갈리",
    "낯설",
    "집이 낯설",
    "집이 났",
    "우리 집방 맞지",
    "우리 집 방 맞지",
    "커튼 색깔이 원래",
    "누구였는지",
    "누구인지",
    "누구여",
    "이름이 생각이 안",
    "이름이 기억",
    "너 이름",
    "동생인가",
    "큰 애야",
    "큰 아들",
    "왜 들고",
    "어디로 가야",
    "너 지금 어디야",
    "오늘 오는 날",
    "무슨 옷",
    "밥을 먹었는지",
    "밥솥을 켰는지",
    "켰는지 모르",
    "누가 먹은",
    "오늘이 며칠",
    "몇 월 며칠",
    "순서가 잘 안",
    "자꾸 같은",
)
MILD_COGNITIVE_PATTERNS = (
    "깜빡",
    "다시 확인",
    "한 번만 더 확인",
    "한번만 더 확인",
    "아까도 물어본",
    "또 물어본",
    "가끔",
    "흐릿",
    "착각",
    "잘못 생각",
    "생각이 안 나",
    "생각이 안 나는",
    "안 떠올",
    "메모",
    "메모도 보",
    "적어두",
    "달력에 적",
    "언제 간다고",
    "금요일이라고 했나",
    "토요일이라고 했나",
    "요일 맞지",
    "표시",
    "휴대폰 알림",
    "단어가 바로 안",
    "이름이 입에서 안",
    "바로 안 떠오",
    "조금 지나면 생각",
)
NORMAL_CONTEXT_PATTERNS = (
    "계획이에요",
    "녹음 시작",
    "편하게 말씀",
    "다녀왔어",
    "끓이려고",
    "예약 확인",
    "재료는 다 사",
    "가져오라고",
    "도착하면",
    "괜찮아",
    "걱정하지 않아도",
    "먼저",
    "그동안",
    "특별히 이상한 건 없",
    "정리하다가",
    "사진첩",
    "예전 이야기",
    "같이 봐요",
    "생각하면 시간이",
    "몇 장 골라",
    "같이 보자",
    "다녀오려고",
    "공원에 다녀",
    "필요한 것도 사",
    "사오세요",
    "좋을 것 같아",
    "사올 생각",
)


def _tokenize(text: str) -> list[str]:
    return re.findall(r"[0-9A-Za-z가-힣]+", text.lower())


def _sentences(text: str) -> list[str]:
    return [part.strip() for part in re.split(r"[.!?\n。！？]+", text) if part.strip()]


def _pattern_score(text: str, patterns: tuple[str, ...], weight: float, cap: float) -> float:
    hits = sum(text.count(pattern) for pattern in patterns)
    return min(hits * weight, cap)


def extract_linguistic_features(transcript_text: str | None) -> dict:
    normalized = (transcript_text or "").strip()
    if not normalized:
        return {
            "transcript_available": False,
            "vocabulary_diversity": 0.0,
            "average_sentence_length": 0.0,
            "repeated_word_ratio": 0.0,
            "noun_verb_ratio": 0.0,
            "fluency_marker_count": 0,
            "figurative_expression_count": 0,
            "language_quality_score": 0.0,
            "semantic_impairment_score": 0.0,
            "semantic_severe_score": 0.0,
            "semantic_mild_score": 0.0,
            "semantic_normal_score": 0.0,
            "token_count": 0,
            "stt_available": False,
            "stt_engine": "none",
            "stt_confidence": 0.0,
            "transcript_char_count": 0,
            "extraction_note": "전사 텍스트가 제공되지 않아 언어 특징은 산출하지 않았습니다.",
        }

    tokens = _tokenize(normalized)
    sentence_list = _sentences(normalized)
    token_count = len(tokens)
    unique_count = len(set(tokens))
    counts = Counter(tokens)
    repeated_count = sum(count - 1 for count in counts.values() if count > 1)

    noun_like = sum(1 for token in tokens if token.endswith(KOREAN_PARTICLE_HINTS))
    verb_like = sum(1 for token in tokens if token.endswith(KOREAN_VERB_ENDINGS))
    if noun_like == 0:
        noun_like = max(0, token_count - verb_like)

    vocabulary_diversity = unique_count / token_count if token_count else 0.0
    average_sentence_length = token_count / len(sentence_list) if sentence_list else float(token_count)
    repeated_word_ratio = repeated_count / token_count if token_count else 0.0
    noun_verb_ratio = noun_like / max(verb_like, 1)
    fluency_marker_count = sum(counts.get(marker, 0) for marker in FLUENCY_MARKERS)
    figurative_expression_count = sum(normalized.count(marker) for marker in FIGURATIVE_MARKERS)
    semantic_severe_score = _pattern_score(normalized, SEVERE_COGNITIVE_PATTERNS, 0.16, 0.9)
    semantic_mild_score = _pattern_score(normalized, MILD_COGNITIVE_PATTERNS, 0.08, 0.55)
    semantic_impairment_score = min(semantic_severe_score + semantic_mild_score, 1.0)
    semantic_normal_score = _pattern_score(normalized, NORMAL_CONTEXT_PATTERNS, 0.08, 0.72)

    diversity_score = min(vocabulary_diversity / 0.65, 1.0)
    sentence_score = 1.0 if 4 <= average_sentence_length <= 18 else 0.65
    repetition_score = max(0.0, 1.0 - repeated_word_ratio * 2.5)
    language_quality_score = (diversity_score * 0.45) + (sentence_score * 0.25) + (repetition_score * 0.30)

    return {
        "transcript_available": True,
        "vocabulary_diversity": round(float(vocabulary_diversity), 4),
        "average_sentence_length": round(float(average_sentence_length), 2),
        "repeated_word_ratio": round(float(repeated_word_ratio), 4),
        "noun_verb_ratio": round(float(noun_verb_ratio), 4),
        "fluency_marker_count": int(fluency_marker_count),
        "figurative_expression_count": int(figurative_expression_count),
        "language_quality_score": round(float(language_quality_score), 4),
        "semantic_impairment_score": round(float(semantic_impairment_score), 4),
        "semantic_severe_score": round(float(semantic_severe_score), 4),
        "semantic_mild_score": round(float(semantic_mild_score), 4),
        "semantic_normal_score": round(float(semantic_normal_score), 4),
        "token_count": int(token_count),
        "stt_available": True,
        "stt_engine": "provided_or_auto",
        "stt_confidence": 0.0,
        "transcript_char_count": len(normalized),
        "extraction_note": "제공된 전사 텍스트에서 휴리스틱 언어 특징을 산출했습니다.",
    }
