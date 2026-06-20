import os


TRUE_VALUES = {"1", "true", "yes", "on"}


def env_name(name: str) -> str:
    if not name.startswith("SORIMEMO_"):
        raise ValueError("SoriMemo environment names must start with SORIMEMO_")
    return name.replace("SORIMEMO_", "VELORA_", 1)


def env_str(name: str, default: str = "") -> str:
    legacy_name = env_name(name)
    value = os.getenv(name)
    if value is not None:
        return value
    return os.getenv(legacy_name, default)


def env_bool(name: str, default: str = "false") -> bool:
    return env_str(name, default).strip().lower() in TRUE_VALUES


def env_int(name: str, default: int | str) -> int:
    return int(env_str(name, str(default)))


def env_float(name: str, default: float | str) -> float:
    return float(env_str(name, str(default)))
