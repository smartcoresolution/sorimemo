import numpy as np
import librosa

TARGET_SR = 16000


def extract_speech_statistics(y: np.ndarray, sr: int) -> dict:
    frame_length = 2048
    hop_length = 512

    energy = np.array([
        np.sum(np.abs(y[i:i + frame_length]))
        for i in range(0, len(y) - frame_length, hop_length)
    ])

    if len(energy) == 0:
        return {
            "total_speech_duration": 0.0,
            "silence_ratio": 1.0,
            "speech_density": 0.0,
            "mean_utterance_length": 0.0,
            "utterance_count": 0,
        }

    threshold = np.percentile(energy, 20) * 1.5
    is_speech = energy > threshold

    total_frames = len(energy)
    speech_frames = np.sum(is_speech)
    silence_frames = total_frames - speech_frames

    frame_duration = hop_length / sr
    total_duration = len(y) / sr
    speech_duration = float(speech_frames * frame_duration)
    silence_ratio = float(silence_frames / total_frames) if total_frames > 0 else 0.0

    utterances = []
    in_utterance = False
    utt_start = 0
    for i, s in enumerate(is_speech):
        if s and not in_utterance:
            in_utterance = True
            utt_start = i
        elif not s and in_utterance:
            in_utterance = False
            utterances.append((utt_start, i))
    if in_utterance:
        utterances.append((utt_start, len(is_speech)))

    utterance_count = len(utterances)
    if utterance_count > 0:
        utt_lengths = [(end - start) * frame_duration for start, end in utterances]
        mean_utterance_length = float(np.mean(utt_lengths))
    else:
        mean_utterance_length = 0.0

    speech_density = speech_duration / total_duration if total_duration > 0 else 0.0

    return {
        "total_speech_duration": round(speech_duration, 2),
        "silence_ratio": round(silence_ratio, 4),
        "speech_density": round(speech_density, 4),
        "mean_utterance_length": round(mean_utterance_length, 3),
        "utterance_count": utterance_count,
    }


def extract_acoustic_features(y: np.ndarray, sr: int) -> dict:
    mfcc = librosa.feature.mfcc(y=y, sr=sr, n_mfcc=13)
    mfcc_mean = np.mean(mfcc, axis=1).tolist()
    mfcc_std = np.std(mfcc, axis=1).tolist()

    pitches, magnitudes = librosa.piptrack(y=y, sr=sr)
    pitch_values = []
    for t in range(pitches.shape[1]):
        idx = magnitudes[:, t].argmax()
        pitch = pitches[idx, t]
        if pitch > 50:
            pitch_values.append(pitch)

    if len(pitch_values) > 0:
        pitch_arr = np.array(pitch_values)
        pitch_mean = float(np.mean(pitch_arr))
        pitch_std = float(np.std(pitch_arr))
        pitch_range = float(np.max(pitch_arr) - np.min(pitch_arr))
    else:
        pitch_mean = 0.0
        pitch_std = 0.0
        pitch_range = 0.0

    rms = librosa.feature.rms(y=y)[0]
    energy_mean = float(np.mean(rms))
    energy_std = float(np.std(rms))
    energy_variability = float(energy_std / energy_mean) if energy_mean > 0 else 0.0

    onset_env = librosa.onset.onset_strength(y=y, sr=sr)
    tempo = librosa.feature.tempo(onset_envelope=onset_env, sr=sr)
    speech_rate = float(tempo[0]) if len(tempo) > 0 else 0.0

    if len(pitch_values) > 10:
        pitch_diffs = np.diff(pitch_arr)
        prosody_stability = float(1.0 / (1.0 + np.std(pitch_diffs) / (np.mean(np.abs(pitch_diffs)) + 1e-6)))
    else:
        prosody_stability = 0.5

    spectral_centroid = librosa.feature.spectral_centroid(y=y, sr=sr)[0]
    spectral_centroid_mean = float(np.mean(spectral_centroid))

    spectral_bandwidth = librosa.feature.spectral_bandwidth(y=y, sr=sr)[0]
    spectral_bandwidth_mean = float(np.mean(spectral_bandwidth))

    zcr = librosa.feature.zero_crossing_rate(y)[0]
    zero_crossing_rate = float(np.mean(zcr))

    return {
        "mfcc_mean": [round(v, 4) for v in mfcc_mean],
        "mfcc_std": [round(v, 4) for v in mfcc_std],
        "pitch_mean": round(pitch_mean, 2),
        "pitch_std": round(pitch_std, 2),
        "pitch_range": round(pitch_range, 2),
        "energy_mean": round(energy_mean, 6),
        "energy_std": round(energy_std, 6),
        "energy_variability": round(energy_variability, 4),
        "speech_rate": round(speech_rate, 2),
        "prosody_stability": round(prosody_stability, 4),
        "spectral_centroid_mean": round(spectral_centroid_mean, 2),
        "spectral_bandwidth_mean": round(spectral_bandwidth_mean, 2),
        "zero_crossing_rate": round(zero_crossing_rate, 6),
    }


def compute_feature_quality(acoustic: dict, statistics: dict) -> float:
    scores = []

    if statistics["utterance_count"] >= 5:
        scores.append(1.0)
    elif statistics["utterance_count"] >= 2:
        scores.append(0.7)
    else:
        scores.append(0.3)

    if statistics["silence_ratio"] < 0.5:
        scores.append(1.0)
    elif statistics["silence_ratio"] < 0.7:
        scores.append(0.7)
    else:
        scores.append(0.4)

    if acoustic["pitch_mean"] > 50:
        scores.append(1.0)
    else:
        scores.append(0.3)

    if acoustic["energy_mean"] > 0.001:
        scores.append(1.0)
    elif acoustic["energy_mean"] > 0.0001:
        scores.append(0.6)
    else:
        scores.append(0.3)

    return round(float(np.mean(scores)), 4)
