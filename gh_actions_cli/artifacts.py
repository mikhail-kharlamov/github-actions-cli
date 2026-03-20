from __future__ import annotations

from io import BytesIO
from pathlib import Path
from zipfile import ZipFile


def extract_artifact_zip(archive_bytes: bytes, destination: Path) -> list[Path]:
    destination.mkdir(parents=True, exist_ok=True)
    written_paths: list[Path] = []
    with ZipFile(BytesIO(archive_bytes)) as archive:
        for member in archive.namelist():
            extracted = Path(archive.extract(member, destination))
            written_paths.append(extracted)
    return written_paths
