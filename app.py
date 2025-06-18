from flask import Flask, render_template, request, redirect, url_for, flash, send_file
from flask_login import LoginManager, login_user, logout_user, login_required, UserMixin, current_user
from pymongo import MongoClient
from werkzeug.security import generate_password_hash, check_password_hash
from bson.objectid import ObjectId
from datetime import datetime
import qrcode
from io import BytesIO
import base64
import os
import csv
import zipfile
import pyshorteners
from dotenv import load_dotenv

load_dotenv()

# Setup
app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY")

UPLOAD_FOLDER = os.getenv("UPLOAD_FOLDER", "uploads")
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER
app.config["MAX_CONTENT_LENGTH"] = 10 * 1024 * 1024  # 10MB upload limit

# Login
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = "login"

# MongoDB
client = MongoClient(os.getenv("MONGO_URI"))
db = client["qr_app"]
users_collection = db["users"]
qrcodes_collection = db["qrcodes"]

# User class
class User(UserMixin):
    def __init__(self, user_data):
        self.id = str(user_data["_id"])
        self.username = user_data["username"]

@login_manager.user_loader
def load_user(user_id):
    user_data = users_collection.find_one({"_id": ObjectId(user_id)})
    return User(user_data) if user_data else None

# URL shortener
def shorten_url(url):
    try:
        return pyshorteners.Shortener().tinyurl.short(url)
    except:
        return url

@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        username = request.form["username"].strip()
        password = request.form["password"]
        if users_collection.find_one({"username": username}):
            flash("Username already exists", "danger")
            return redirect(url_for("register"))
        users_collection.insert_one({
            "username": username,
            "password": generate_password_hash(password)
        })
        flash("Registration successful", "success")
        return redirect(url_for("login"))
    return render_template("register.html")

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form["username"].strip()
        password = request.form["password"]
        user = users_collection.find_one({"username": username})
        if user and check_password_hash(user["password"], password):
            login_user(User(user))
            flash("Logged in successfully", "success")
            return redirect(url_for("index"))
        flash("Invalid credentials", "danger")
    return render_template("login.html")

@app.route("/logout")
@login_required
def logout():
    logout_user()
    flash("Logged out", "info")
    return redirect(url_for("login"))

@app.route("/", methods=["GET", "POST"])
@login_required
def index():
    qr_img = None
    file_name = None

    if request.method == "POST":
        qr_type = request.form.get("qr_type")
        file_name = request.form.get("filename", "").strip()
        url = request.form.get("url", "").strip()

        if qr_type == "whatsapp":
            phone = request.form.get("phone")
            message = request.form.get("message")
            data = f"https://wa.me/{phone}?text={message}"
        elif qr_type == "location":
            lat = request.form.get("lat")
            lon = request.form.get("lon")
            data = f"https://www.google.com/maps?q={lat},{lon}"
        elif qr_type == "vcard":
            name = request.form.get("name")
            phone = request.form.get("phone")
            email = request.form.get("email")
            data = f"BEGIN:VCARD\nVERSION:3.0\nFN:{name}\nTEL:{phone}\nEMAIL:{email}\nEND:VCARD"
        else:
            data = shorten_url(url)

        if not file_name or not data:
            flash("Missing data or filename", "warning")
            return redirect(url_for("index"))

        qr = qrcode.QRCode(version=1, error_correction=qrcode.constants.ERROR_CORRECT_H, box_size=10, border=4)
        qr.add_data(data)
        qr.make(fit=True)
        img = qr.make_image(fill_color="black", back_color="white")

        buffer = BytesIO()
        img.save(buffer, format="PNG")
        buffer.seek(0)
        img_base64 = base64.b64encode(buffer.getvalue()).decode("utf-8")
        qr_img = f"data:image/png;base64,{img_base64}"

        qrcodes_collection.insert_one({
            "file_name": file_name,
            "data": data,
            "type": qr_type,
            "user_id": ObjectId(current_user.id),
            "created_at": datetime.utcnow()
        })
        flash("QR Code generated and saved!", "success")

    return render_template("index.html", qr_img=qr_img, file_name=file_name)

@app.route("/history")
@login_required
def history():
    records = list(qrcodes_collection.find({"user_id": ObjectId(current_user.id)}).sort("created_at", -1))
    return render_template("history.html", records=records)

@app.route("/delete/<qr_id>", methods=["POST"])
@login_required
def delete_qr(qr_id):
    qr = qrcodes_collection.find_one({"_id": ObjectId(qr_id), "user_id": ObjectId(current_user.id)})
    if qr:
        qrcodes_collection.delete_one({"_id": ObjectId(qr_id)})
        flash("QR deleted", "success")
    else:
        flash("Not found or access denied", "danger")
    return redirect(url_for("history"))

@app.route("/download/<qr_id>")
@login_required
def download_qr(qr_id):
    qr = qrcodes_collection.find_one({"_id": ObjectId(qr_id), "user_id": ObjectId(current_user.id)})
    if not qr:
        flash("QR Code not found", "danger")
        return redirect(url_for("history"))

    data = qr.get("data") or qr.get("url")
    filename = qr.get("file_name", "QR")
    qr_code = qrcode.make(data)
    buffer = BytesIO()
    qr_code.save(buffer, format="PNG")
    buffer.seek(0)

    return send_file(buffer, mimetype="image/png", as_attachment=True, download_name=f"{filename}.png")

@app.route("/download_zip")
@login_required
def download_zip():
    records = list(qrcodes_collection.find({"user_id": ObjectId(current_user.id)}))
    zip_buffer = BytesIO()

    with zipfile.ZipFile(zip_buffer, "w") as zipf:
        for qr in records:
            data = qr.get("data") or qr.get("url")
            if not data:
                continue
            qr_code = qrcode.make(data)
            buffer = BytesIO()
            qr_code.save(buffer, format="PNG")
            filename = f"{qr.get('file_name', 'QR')}.png"
            zipf.writestr(filename, buffer.getvalue())

    zip_buffer.seek(0)
    return send_file(zip_buffer, as_attachment=True, download_name=f"{current_user.username}_qrcodes.zip")

@app.route("/bulk_upload", methods=["GET", "POST"])
@login_required
def bulk_upload():
    if request.method == "POST":
        file = request.files["csv_file"]
        if not file or not file.filename.endswith(".csv"):
            flash("Invalid file", "danger")
            return redirect(url_for("bulk_upload"))

        reader = csv.DictReader(file.read().decode("utf-8").splitlines())
        for row in reader:
            url = row.get("url", "")
            file_name = row.get("filename", "QR")
            if not url:
                continue
            short_url = shorten_url(url)
            qrcodes_collection.insert_one({
                "file_name": file_name,
                "url": short_url,
                "user_id": ObjectId(current_user.id),
                "created_at": datetime.utcnow()
            })

        flash("Bulk QR generation done", "success")
        return redirect(url_for("history"))
    return render_template("bulk_upload.html")


# Run in local development only
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
