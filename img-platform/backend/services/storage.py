import os
from pathlib import Path


BACKEND_DIR = Path(__file__).resolve().parents[1]


def get_upload_root() -> Path:
    return Path(os.getenv("UPLOAD_DIR", BACKEND_DIR / "uploads")).expanduser()


def get_minimax_output_root() -> Path:
    return Path(os.getenv("MINIMAX_OUTPUT_DIR", Path.home() / "minimax-output")).expanduser()


def ensure_dir(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    return path


def upload_category_dir(category: str) -> Path:
    return ensure_dir(get_upload_root() / category.strip("/"))


def upload_url(category: str, filename: str) -> str:
    return f"/uploads/{category.strip('/')}/{filename}"


def local_path_from_public_url(public_url: str) -> Path:
    path = public_url.split("?", 1)[0]
    if path.startswith("/uploads/"):
        return get_upload_root() / path.removeprefix("/uploads/")
    if path.startswith("/minimax-output/"):
        return get_minimax_output_root() / Path(path).name
    raise ValueError("Unsupported local public URL")
