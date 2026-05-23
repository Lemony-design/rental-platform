import json
import os
import urllib.request
import uuid

from dotenv import load_dotenv
from flask import Flask, jsonify, render_template, request
from werkzeug.utils import secure_filename

load_dotenv()

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_BLOB_PATH = "macau-rent/data.json"
LOCAL_DATA_FILE = os.path.join(ROOT_DIR, "data.json")
LOCAL_UPLOAD_DIR = os.path.join(ROOT_DIR, "public", "uploads")

app = Flask(__name__, template_folder=os.path.join(ROOT_DIR, "templates"))


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


def _guess_content_type(filename: str) -> str | None:
    lower = filename.lower()
    if lower.endswith((".jpg", ".jpeg")):
        return "image/jpeg"
    if lower.endswith(".png"):
        return "image/png"
    if lower.endswith(".webp"):
        return "image/webp"
    if lower.endswith(".gif"):
        return "image/gif"
    if lower.endswith(".mp4"):
        return "video/mp4"
    if lower.endswith(".mov"):
        return "video/quicktime"
    return None


@app.route("/")
def index():
    db = load_data()

    min_price = request.args.get("min_price", type=int, default=0)
    max_price = request.args.get("max_price", type=int, default=999999)
    location = request.args.get("location", "")
    rent_type = request.args.get("rent_type", "")
    layout = request.args.get("layout", "")
    bedroom = request.args.get("bedroom", "")
    housing_form = request.args.get("housing_form", "")

    filtered_db = []
    for prop in db:
        try:
            p_price = int(prop.get("price", 0))
        except (TypeError, ValueError):
            p_price = 0

        if not (min_price <= p_price <= max_price):
            continue
        if location and location != "不限" and prop.get("location") != location:
            continue
        if rent_type and rent_type != "不限" and prop.get("rent_type") != rent_type:
            continue
        if layout and layout != "不限" and prop.get("layout") != layout:
            continue
        if bedroom and bedroom != "不限" and prop.get("bedroom") != bedroom:
            continue
        if housing_form and housing_form != "不限" and prop.get("housing_form") != housing_form:
            continue

        filtered_db.append(prop)

    filtered_db.reverse()
    return render_template("index.html", properties=filtered_db)


@app.route("/property/<prop_id>")
def detail(prop_id):
    db = load_data()
    prop = next((p for p in db if p["id"] == prop_id), None)
    if prop:
        return render_template("detail.html", prop=prop)
    return "找不到该房源", 404


@app.route("/merchant/upload", methods=["GET"])
def upload_page():
    return render_template("upload.html")


@app.route("/api/upload", methods=["POST"])
def api_upload():
    title = request.form.get("title")
    location = request.form.get("location")
    price = request.form.get("price")
    desc = request.form.get("desc")
    rent_type = request.form.get("rent_type", "不限")
    layout = request.form.get("layout", "不限")
    bedroom = request.form.get("bedroom", "不限")
    housing_form = request.form.get("housing_form", "不限")

    files = request.files.getlist("media")

    if not title or not price or not files:
        return jsonify({"status": "error", "message": "标题、价格和至少一个媒体文件为必填项"}), 400

    if len(files) > 10:
        return jsonify({"status": "error", "message": "最多只能上传10个文件"}), 400

    media_urls = []
    for file in files:
        if file and file.filename:
            filename = secure_filename(file.filename)
            unique_filename = f"{uuid.uuid4().hex}_{filename}"
            content_type = file.content_type or _guess_content_type(filename)
            url = upload_media(unique_filename, file.read(), content_type)
            media_urls.append(url)

    db = load_data()
    new_id = str(uuid.uuid4().hex[:8])

    new_property = {
        "id": new_id,
        "title": title,
        "location": location,
        "price": price,
        "desc": desc,
        "rent_type": rent_type,
        "layout": layout,
        "bedroom": bedroom,
        "housing_form": housing_form,
        "media": media_urls,
    }

    db.append(new_property)
    save_data(db)

    return jsonify({"status": "success", "message": "房源发布成功！"}), 200


@app.route("/api/property/<prop_id>", methods=["DELETE"])
def delete_property(prop_id):
    db = load_data()
    prop_to_delete = next((p for p in db if p["id"] == prop_id), None)
    if prop_to_delete:
        db.remove(prop_to_delete)
        save_data(db)
        return jsonify({"status": "success"})
    return jsonify({"status": "error"}), 404
