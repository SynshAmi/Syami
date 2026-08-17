import hashlib
from pathlib import Path


def calculate_file_hash(file_path: str) -> str:
    path = Path(file_path)

    if not path.is_file():
        raise FileNotFoundError(f"File does not exist: {path}")

    sha256 = hashlib.sha256()

    with path.open("rb") as file:
        while chunk := file.read(1024 * 1024):
            sha256.update(chunk)

    return sha256.hexdigest()