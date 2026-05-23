"""数据与媒体存储：生产环境用 Vercel Blob，本地无 Token 时回退到磁盘。"""

import json
import os
import urllib.request

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_BLOB_PATH = "macau-rent/data.json"
LOCAL_DATA_FILE = os.path.join(ROOT_DIR, "data.json")
LOCAL_UPLOAD_DIR = os.path.join(ROOT_DIR, "public", "uploads")


def _use_blob() -> bool:
    return bool(os.environ.get("BLOB_READ_WRITE_TOKEN"))


def _seed_data() -> list:
    if os.path.exists(LOCAL_DATA_FILE):
        with open(LOCAL_DATA_FILE, "r", encoding="utf-8") as f:
            try:
                return json.load(f)
            except json.JSONDecodeError:
                return []
    return []


def load_data() -> list:
    if not _use_blob():
        return _seed_data()

    import vercel_blob

    try:
        meta = vercel_blob.head(DATA_BLOB_PATH)
        url = meta.get("url") or meta.get("downloadUrl")
        if not url:
            return _seed_data()
        with urllib.request.urlopen(url) as resp:
            return json.load(resp)
    except Exception:
        return _seed_data()


def save_data(data: list) -> None:
    payload = json.dumps(data, ensure_ascii=False, indent=4).encode("utf-8")

    if not _use_blob():
        os.makedirs(os.path.dirname(LOCAL_DATA_FILE), exist_ok=True)
        with open(LOCAL_DATA_FILE, "w", encoding="utf-8") as f:
            f.write(payload.decode("utf-8"))
        return

    import vercel_blob

    vercel_blob.put(
        DATA_BLOB_PATH,
        payload,
        {"access": "public", "addRandomSuffix": "false"},
    )


def upload_media(filename: str, content: bytes, content_type: str | None = None) -> str:
    if not _use_blob():
        os.makedirs(LOCAL_UPLOAD_DIR, exist_ok=True)
        path = os.path.join(LOCAL_UPLOAD_DIR, filename)
        with open(path, "wb") as f:
            f.write(content)
        return f"/uploads/{filename}"

    import vercel_blob

    pathname = f"macau-rent/uploads/{filename}"
    options = {"access": "public", "addRandomSuffix": "false"}
    if content_type:
        options["contentType"] = content_type
    resp = vercel_blob.put(pathname, content, options)
    return resp["url"]
