import os
import uuid
import tempfile
import subprocess
from pathlib import Path
import numpy as np
import librosa
import soundfile as sf
from typing import Optional

from app.config import env_float, env_str

UPLOAD_DIR = env_str("SORIMEMO_UPLOAD_DIR", "/tmp/sorimemo_uploads")
PROCESSED_DIR = env_str("SORIMEMO_PROCESSED_DIR", "/tmp/sorimemo_processed")
VOICE_SAMPLES_DIR = env_str("SORIMEMO_VOICE_SAMPLES_DIR", "/tmp/sorimemo_voice_samples")

os.makedirs(UPLOAD_DIR, exist_ok=True)
os.makedirs(PROCESSED_DIR, exist_ok=True)
os.makedirs(VOICE_SAMPLES_DIR, exist_ok=True)

TARGET_SR = 16000
MIN_DURATION = env_float("SORIMEMO_MIN_AUDIO_DURATION", "45.0")
MIN_SELF_VOICE_DURATION = env_float("SORIMEMO_MIN_SELF_VOICE_DURATION", "30.0")
MAX_DURATION = env_float("SORIMEMO_MAX_AUDIO_DURATION", "180.0")
MAX_SILENCE_RATIO = env_float("SORIMEMO_MAX_SILENCE_RATIO", "0.65")
MIN_SNR_DB = env_float("SORIMEMO_MIN_SNR_DB", "12.0")
MIN_SPEECH_DURATION = env_float("SORIMEMO_MIN_SPEECH_DURATION", "25.0")
MIN_RMS_DBFS = env_float("SORIMEMO_MIN_RMS_DBFS", "-45.0")


def get_quality_policy() -> dict:
    return {
        "target_sample_rate": TARGET_SR,
        "min_duration_seconds": MIN_DURATION,
        "min_self_voice_duration_seconds": MIN_SELF_VOICE_DURATION,
        "max_duration_seconds": MAX_DURATION,
        "max_silence_ratio": MAX_SILENCE_RATIO,
        "min_snr_db": MIN_SNR_DB,
        "min_speech_duration_seconds": MIN_SPEECH_DURATION,
        "min_rms_dbfs": MIN_RMS_DBFS,
        "upload_dir": UPLOAD_DIR,
        "processed_dir": PROCESSED_DIR,
        "voice_samples_dir": VOICE_SAMPLES_DIR,
    }


def save_uploaded_file(file_bytes: bytes, original_filename: str) -> tuple[str, str]:
    file_id = str(uuid.uuid4())
    ext = os.path.splitext(original_filename)[1].lower() or ".wav"
    filepath = os.path.join(UPLOAD_DIR, f"{file_id}{ext}")
    with open(filepath, "wb") as f:
        f.write(file_bytes)
    return file_id, filepath


def save_voice_sample(file_bytes: bytes, original_filename: str) -> tuple[str, str]:
    sample_id = str(uuid.uuid4())
    ext = os.path.splitext(original_filename)[1].lower() or ".wav"
    filepath = os.path.join(VOICE_SAMPLES_DIR, f"{sample_id}{ext}")
    with open(filepath, "wb") as f:
        f.write(file_bytes)
    return sample_id, filepath


def convert_to_standard_wav(input_path: str, file_id: str) -> str:
    output_path = os.path.join(PROCESSED_DIR, f"{file_id}_std.wav")
    cmd = [
        "ffmpeg", "-y", "-i", input_path,
        "-ar", str(TARGET_SR),
        "-ac", "1",
        "-sample_fmt", "s16",
        output_path
    ]
    try:
        subprocess.run(cmd, capture_output=True, check=True)
    except FileNotFoundError:
        _convert_with_librosa(input_path, output_path)
    return output_path


def _convert_with_librosa(input_path: str, output_path: str) -> None:
    y, _ = librosa.load(input_path, sr=TARGET_SR, mono=True)
    sf.write(output_path, y, TARGET_SR, subtype="PCM_16")


def trim_wav_to_duration(wav_path: str, max_duration_seconds: float) -> tuple[float, bool]:
    y, sr = librosa.load(wav_path, sr=TARGET_SR, mono=True)
    original_duration = len(y) / sr
    if original_duration <= max_duration_seconds:
        return original_duration, False

    max_samples = int(max_duration_seconds * sr)
    sf.write(wav_path, y[:max_samples], sr, subtype="PCM_16")
    return original_duration, True


def compute_snr(y: np.ndarray) -> float:
    frame_length = 2048
    hop_length = 512
    energy = np.array([
        np.sum(y[i:i + frame_length] ** 2)
        for i in range(0, len(y) - frame_length, hop_length)
    ])
    energy = np.maximum(energy, 1e-10)
    threshold = np.percentile(energy, 15)
    signal_energy = energy[energy > threshold]
    noise_energy = energy[energy <= threshold]
    if len(noise_energy) == 0 or np.mean(noise_energy) < 1e-10:
        return 40.0
    snr = 10 * np.log10(np.mean(signal_energy) / np.mean(noise_energy))
    return float(np.clip(snr, 0, 60))


def compute_silence_ratio(y: np.ndarray, sr: int) -> float:
    frame_length = 2048
    hop_length = 512
    energy = np.array([
        np.sum(np.abs(y[i:i + frame_length]))
        for i in range(0, len(y) - frame_length, hop_length)
    ])
    threshold = np.percentile(energy, 20) * 1.5
    silence_frames = np.sum(energy < threshold)
    return float(silence_frames / len(energy)) if len(energy) > 0 else 0.0


def compute_speech_duration(y: np.ndarray, sr: int) -> float:
    if len(y) == 0:
        return 0.0
    intervals = librosa.effects.split(y, top_db=35)
    speech_samples = sum(max(0, int(end) - int(start)) for start, end in intervals)
    return float(speech_samples / sr)


def compute_rms_dbfs(y: np.ndarray) -> float:
    if len(y) == 0:
        return -120.0
    rms = float(np.sqrt(np.mean(np.square(y))))
    return float(20 * np.log10(max(rms, 1e-9)))


def quality_check(
    wav_path: str,
    min_duration_seconds: float | None = None,
    min_speech_duration_seconds: float | None = None,
) -> dict:
    y, sr = librosa.load(wav_path, sr=TARGET_SR)
    duration = len(y) / sr
    snr = compute_snr(y)
    silence_ratio = compute_silence_ratio(y, sr)
    speech_duration = compute_speech_duration(y, sr)
    rms_dbfs = compute_rms_dbfs(y)

    info = sf.info(wav_path)

    quality_pass = True
    rejection_reason = None
    effective_min_duration = MIN_DURATION if min_duration_seconds is None else min_duration_seconds
    effective_min_speech_duration = MIN_SPEECH_DURATION if min_speech_duration_seconds is None else min_speech_duration_seconds

    if duration < effective_min_duration:
        quality_pass = False
        rejection_reason = f"음성 길이가 {duration:.1f}초로 최소 {effective_min_duration:.1f}초 미만입니다. 더 긴 녹음을 업로드해 주세요."
    elif speech_duration < effective_min_speech_duration:
        quality_pass = False
        rejection_reason = f"실제 발화 구간이 {speech_duration:.1f}초로 최소 {effective_min_speech_duration:.1f}초 미만입니다. 발화가 충분히 포함된 녹음을 업로드해 주세요."
    elif silence_ratio > MAX_SILENCE_RATIO:
        quality_pass = False
        rejection_reason = f"무음 비율이 {silence_ratio*100:.1f}%로 너무 높습니다. 발화가 충분히 포함된 녹음을 업로드해 주세요."
    elif snr < MIN_SNR_DB:
        quality_pass = False
        rejection_reason = f"SNR이 {snr:.1f}dB로 너무 낮습니다. 잡음이 적은 환경에서 녹음해 주세요."
    elif rms_dbfs < MIN_RMS_DBFS:
        quality_pass = False
        rejection_reason = f"평균 음량이 {rms_dbfs:.1f}dBFS로 너무 낮습니다. 더 가까운 위치에서 통화녹음을 다시 진행해 주세요."

    return {
        "duration_seconds": round(duration, 2),
        "snr_db": round(snr, 2),
        "silence_ratio": round(silence_ratio, 4),
        "speech_duration_seconds": round(speech_duration, 2),
        "rms_dbfs": round(rms_dbfs, 2),
        "sample_rate": info.samplerate,
        "channels": info.channels,
        "quality_pass": quality_pass,
        "rejection_reason": rejection_reason,
    }


def get_voice_sample_embedding(sample_path: str) -> Optional[np.ndarray]:
    try:
        wav_path = sample_path
        if Path(sample_path).suffix.lower() != ".wav":
            wav_path = sample_path.rsplit(".", 1)[0] + "_std.wav"
            cmd = [
                "ffmpeg", "-y", "-i", sample_path,
                "-ar", str(TARGET_SR), "-ac", "1", "-sample_fmt", "s16",
                wav_path
            ]
            try:
                subprocess.run(cmd, capture_output=True, check=True)
            except FileNotFoundError:
                _convert_with_librosa(sample_path, wav_path)

        y, sr = librosa.load(wav_path, sr=TARGET_SR)
        mfcc = librosa.feature.mfcc(y=y, sr=sr, n_mfcc=20)
        embedding = np.mean(mfcc, axis=1)
        return embedding
    except Exception:
        return None
