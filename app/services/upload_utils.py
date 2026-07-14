from __future__ import annotations

import re
from pathlib import Path
from typing import Optional
from uuid import uuid4

from fastapi import HTTPException, UploadFile


def safe_unique_filename(filename: Optional[str], fallback: str = "document") -> str:
    source = Path(filename or fallback)
    stem = re.sub(r"[^A-Za-z0-9._-]+", "_", source.stem).strip("._-") or fallback
    suffix = source.suffix.lower()
    return f"{stem[:80]}_{uuid4().hex[:12]}{suffix}"


def save_upload_file(file: UploadFile, target: Path, max_bytes: int) -> int:
    total = 0
    target.parent.mkdir(parents=True, exist_ok=True)
    try:
        with target.open("wb") as out:
            while True:
                chunk = file.file.read(1024 * 1024)
                if not chunk:
                    break
                total += len(chunk)
                if total > max_bytes:
                    raise HTTPException(status_code=413, detail=f"File is larger than {max_bytes} bytes")
                out.write(chunk)
    except Exception:
        target.unlink(missing_ok=True)
        raise
    finally:
        file.file.seek(0)
    return total
