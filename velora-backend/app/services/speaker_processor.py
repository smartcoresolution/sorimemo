import numpy as np
import librosa
from typing import Optional

TARGET_SR = 16000


def perform_speaker_diarization(
    wav_path: str,
    voice_sample_embedding: Optional[np.ndarray] = None,
    max_duration: Optional[float] = None,
) -> dict:
    y, sr = librosa.load(wav_path, sr=TARGET_SR, duration=max_duration)
    duration = len(y) / sr

    frame_duration = 1.0
    hop_duration = 0.5
    frame_samples = int(frame_duration * sr)
    hop_samples = int(hop_duration * sr)

    segments = []
    for start_sample in range(0, len(y) - frame_samples, hop_samples):
        end_sample = start_sample + frame_samples
        frame = y[start_sample:end_sample]

        energy = np.sqrt(np.mean(frame ** 2))
        if energy < 0.005:
            continue

        mfcc = librosa.feature.mfcc(y=frame, sr=sr, n_mfcc=13)
        mfcc_mean = np.mean(mfcc, axis=1)

        spectral_centroid = np.mean(librosa.feature.spectral_centroid(y=frame, sr=sr))

        start_time = start_sample / sr
        end_time = end_sample / sr

        segments.append({
            "start_time": round(start_time, 2),
            "end_time": round(end_time, 2),
            "mfcc_mean": mfcc_mean,
            "spectral_centroid": spectral_centroid,
            "energy": energy,
        })

    if len(segments) < 2:
        target_segments = [{
            "speaker": "speaker_A",
            "start_time": 0.0,
            "end_time": round(duration, 2),
            "duration": round(duration, 2),
        }]
        return {
            "total_speakers": 1,
            "target_speaker": "speaker_A",
            "target_segments": target_segments,
            "excluded_segments": [],
            "diarization_confidence": 0.75,
        }

    features = np.array([
        np.concatenate([s["mfcc_mean"], [s["spectral_centroid"], s["energy"]]])
        for s in segments
    ])

    from sklearn.cluster import KMeans
    n_clusters = min(2, len(features))
    kmeans = KMeans(n_clusters=n_clusters, random_state=42, n_init=10)
    labels = kmeans.fit_predict(features)

    cluster_counts = np.bincount(labels)

    if voice_sample_embedding is not None and len(voice_sample_embedding) >= 13:
        cluster_centroids_mfcc = []
        for c in range(n_clusters):
            cluster_mfccs = features[labels == c, :13]
            cluster_centroids_mfcc.append(np.mean(cluster_mfccs, axis=0))

        sample_mfcc = voice_sample_embedding[:13]
        distances = [
            np.linalg.norm(centroid - sample_mfcc)
            for centroid in cluster_centroids_mfcc
        ]
        similarities = [
            float(np.dot(centroid, sample_mfcc) / (np.linalg.norm(centroid) * np.linalg.norm(sample_mfcc) + 1e-9))
            for centroid in cluster_centroids_mfcc
        ]
        target_cluster = int(np.argmin(distances))
        voice_sample_distance = float(distances[target_cluster])
        voice_sample_similarity = float(similarities[target_cluster])
    else:
        target_cluster = int(np.argmax(cluster_counts))
        voice_sample_distance = None
        voice_sample_similarity = None

    target_segs = []
    excluded_segs = []

    for seg, label in zip(segments, labels):
        entry = {
            "speaker": f"speaker_{'A' if label == target_cluster else 'B'}",
            "start_time": seg["start_time"],
            "end_time": seg["end_time"],
            "duration": round(seg["end_time"] - seg["start_time"], 2),
        }
        if label == target_cluster:
            target_segs.append(entry)
        else:
            excluded_segs.append(entry)

    target_segs = _merge_segments(target_segs)
    excluded_segs = _merge_segments(excluded_segs)

    silhouette_score = 0.0
    if n_clusters > 1 and len(features) > n_clusters:
        from sklearn.metrics import silhouette_score as sk_silhouette
        try:
            silhouette_score = sk_silhouette(features, labels)
        except Exception:
            silhouette_score = 0.5

    confidence = float(np.clip(0.5 + silhouette_score * 0.5, 0.3, 1.0))

    return {
        "total_speakers": n_clusters,
        "target_speaker": "speaker_A",
        "target_segments": target_segs,
        "excluded_segments": excluded_segs,
        "diarization_confidence": round(confidence, 4),
        "voice_sample_distance": round(voice_sample_distance, 4) if voice_sample_distance is not None else None,
        "voice_sample_similarity": round(voice_sample_similarity, 4) if voice_sample_similarity is not None else None,
    }


def _merge_segments(segments: list[dict], max_gap: float = 0.25) -> list[dict]:
    if not segments:
        return []

    ordered = sorted(segments, key=lambda seg: (seg["start_time"], seg["end_time"]))
    merged: list[dict] = []
    for seg in ordered:
        if not merged or seg["start_time"] > merged[-1]["end_time"] + max_gap:
            merged.append(dict(seg))
            continue

        merged[-1]["end_time"] = max(merged[-1]["end_time"], seg["end_time"])
        merged[-1]["duration"] = round(merged[-1]["end_time"] - merged[-1]["start_time"], 2)

    return merged


def extract_target_audio(wav_path: str, target_segments: list[dict]) -> np.ndarray:
    y, sr = librosa.load(wav_path, sr=TARGET_SR)

    if not target_segments:
        return y

    target_audio = []
    for seg in target_segments:
        start_sample = int(seg["start_time"] * sr)
        end_sample = int(seg["end_time"] * sr)
        target_audio.append(y[start_sample:end_sample])

    if target_audio:
        return np.concatenate(target_audio)
    return y
