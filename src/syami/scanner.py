from dataclasses import dataclass
from pathlib import Path
import os
import time


@dataclass
class FileMetadata:
    path: str
    filename: str
    extension: str
    size: int
    created_at: float
    modified_at: float
    indexed_at: float


def scan_directory(root_path: str):
    root = Path(root_path).resolve()

    if not root.exists():
        raise FileNotFoundError(f"Directory does not exist: {root}")

    if not root.is_dir():
        raise NotADirectoryError(f"Not a directory: {root}")

    for current_root, _, filenames in os.walk(root):
        for filename in filenames:
            file_path = Path(current_root) / filename

            try:
                stat = file_path.stat()
            except OSError:
                # File may have disappeared or become inaccessible
                # between discovery and metadata collection.
                continue

            yield FileMetadata(
                path=str(file_path.resolve()),
                filename=file_path.name,
                extension=file_path.suffix.lower(),
                size=stat.st_size,
                created_at=stat.st_ctime,
                modified_at=stat.st_mtime,
                indexed_at=time.time(),
            )