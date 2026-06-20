from pathlib import Path


path = Path("/opt/sorimemo-prod/backend/app/routers/upload.py")
source = path.read_text()

old = '''    sample_id, sample_path = save_voice_sample(file_bytes, file.filename or "sample.wav")

    try:
        embedding = get_voice_sample_embedding(sample_path)
    except Exception:
        embedding = None

    import librosa
    y, sr = librosa.load(sample_path, sr=16000)
    duration = len(y) / sr

    if duration < 3.0:
        raise HTTPException(status_code=400, detail="음성 샘플은 최소 3초 이상이어야 합니다.")
    if duration > 30.0:
        raise HTTPException(status_code=400, detail="음성 샘플은 30초를 초과할 수 없습니다.")

    voice_sample_store[sample_id] = {
        "path": sample_path,
        "consent_token": x_consent_token,
        "duration": duration,
        "embedding": embedding.tolist() if embedding is not None else None,
    }
'''

new = '''    sample_id, sample_path = save_voice_sample(file_bytes, file.filename or "sample.wav")

    import librosa
    import soundfile as sf

    y, sr = librosa.load(sample_path, sr=16000)
    original_duration = len(y) / sr

    if original_duration < 3.0:
        raise HTTPException(status_code=400, detail="음성 샘플은 최소 3초 이상이어야 합니다.")

    duration = min(original_duration, 30.0)
    sample_storage_path = sample_path
    if original_duration > 30.0:
        y = y[: int(30.0 * sr)]
        sample_storage_path = sample_path.rsplit(".", 1)[0] + "_std.wav"
        sf.write(sample_storage_path, y, sr, subtype="PCM_16")

    try:
        embedding = get_voice_sample_embedding(sample_storage_path)
    except Exception:
        embedding = None

    voice_sample_store[sample_id] = {
        "path": sample_storage_path,
        "consent_token": x_consent_token,
        "duration": duration,
        "embedding": embedding.tolist() if embedding is not None else None,
    }
'''

if old not in source:
    raise SystemExit("target block not found")

path.write_text(source.replace(old, new))
