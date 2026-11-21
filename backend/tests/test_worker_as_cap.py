"""Trần RAM bản địa hóa phải lấy từ file .env, không giữ số PM2 cũ."""

from pathlib import Path

from app.core.config import (
    read_dotenv_assignment,
    resolve_image_localization_worker_max_as_mb,
)


def test_dotenv_assignment_skips_comments():
    text = "\n# IMAGE_LOCALIZATION_WORKER_MAX_AS_MB=2500\nIMAGE_LOCALIZATION_WORKER_MAX_AS_MB=4000\n"
    assert read_dotenv_assignment(text, "IMAGE_LOCALIZATION_WORKER_MAX_AS_MB") == "4000"


def test_env_file_beats_stale_pm2_value(tmp_path: Path):
    env_file = tmp_path / ".env"
    env_file.write_text("IMAGE_LOCALIZATION_WORKER_MAX_AS_MB=4000\n", encoding="utf-8")
    assert (
        resolve_image_localization_worker_max_as_mb(
            env_file,
            tmp_path / ".env.local",
            process_value="2500",
        )
        == 4000
    )


def test_env_local_beats_env_file(tmp_path: Path):
    env_file = tmp_path / ".env"
    env_local = tmp_path / ".env.local"
    env_file.write_text("IMAGE_LOCALIZATION_WORKER_MAX_AS_MB=4000\n", encoding="utf-8")
    env_local.write_text("IMAGE_LOCALIZATION_WORKER_MAX_AS_MB=3200\n", encoding="utf-8")
    assert (
        resolve_image_localization_worker_max_as_mb(
            env_file,
            env_local,
            process_value="2500",
        )
        == 3200
    )
