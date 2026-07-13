from pathlib import Path
from uuid import uuid4

from fastapi import UploadFile

from backend.app.core.config import settings


async def save_upload(file: UploadFile) -> Path:
    original_name = Path(file.filename or "textbook.pdf").name
    saved_name = f"{uuid4().hex}_{original_name}"
    target_path = settings.upload_dir / saved_name

    content = await file.read()
    target_path.write_bytes(content)
    return target_path
