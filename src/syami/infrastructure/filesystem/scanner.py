from dataclasses import dataclass
from pathlib import Path
import os
import time
from collections.abc import Callable


@dataclass
class FileMetadata:
    path: str
    filename: str
    extension: str
    size: int
    created_at: float
    modified_at: float
    indexed_at: float


def scan_directory(
    root_path: str,
    should_exclude: Callable[[str, bool], bool] | None = None,
    on_error: Callable[[str, OSError], None] | None = None,
):
    root = Path(root_path).resolve()

    if not root.exists():
        raise FileNotFoundError(
            f"Directory does not exist: {root}"
        )

    if not root.is_dir():
        raise NotADirectoryError(
            f"Not a directory: {root}"
        )

    if should_exclude is None:
        should_exclude = lambda path, is_directory: False

    for current_root, directories, filenames in os.walk(root):
        current_path = Path(current_root)

        # Remove excluded directories from os.walk's
        # traversal list so their contents are never visited.
        directories[:] = [
            directory
            for directory in directories
            if not should_exclude(
                str(current_path / directory),
                True,
            )
        ]

        for filename in filenames:
            file_path = current_path / filename

            if should_exclude(
                str(file_path),
                False,
            ):
                continue

            try:
                stat = file_path.stat()
            except OSError as error:
                if on_error is not None:
                    on_error(
                        str(file_path),
                        error,
                    )

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