from pathlib import Path

from pypdf import PdfReader


def extract_text(file_path: str) -> str:
    path = Path(file_path)

    if not path.exists():
        raise FileNotFoundError(f"File does not exist: {path}")

    if path.suffix.lower() != ".pdf":
        raise ValueError(f"Expected a PDF file: {path}")

    reader = PdfReader(path)

    pages = []

    for page in reader.pages:
        text = page.extract_text()

        if text:
            pages.append(text)

    return "\n".join(pages)