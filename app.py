import os
import re
from datetime import date, datetime
from zoneinfo import ZoneInfo
from flask import Flask, render_template, request, redirect
from flask_sqlalchemy import SQLAlchemy

app = Flask(__name__)

database_url = os.environ.get("DATABASE_URL")

if database_url:
    app.config["SQLALCHEMY_DATABASE_URI"] = database_url
else:
    app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///fridge.db"

app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

db = SQLAlchemy(app)


class Food(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    quantity = db.Column(db.Integer, nullable=False)
    unit = db.Column(db.String(20), nullable=False)
    expiry_date = db.Column(db.Date, nullable=True)


def expiry_status(expiry_date, today):
    if expiry_date is None:
        return "unset", "未設定"
    days = (expiry_date - today).days
    if days < 0:
        return "expired", "期限切れ"
    if days == 0:
        return "soon", "本日まで"
    if days <= 3:
        return "soon", f"あと{days}日"
    return "fresh", "期限まで余裕あり"


@app.route("/")
def index():
    foods = Food.query.all()
    today = datetime.now(ZoneInfo("Asia/Tokyo")).date()
    return render_template("index.html", foods=foods, today=today,
                           expiry_status=expiry_status)


@app.route("/add", methods=["POST"])
def add_food():
    expiry_text = request.form.get("expiry_date", "").strip()
    expiry_date = None
    if expiry_text:
        try:
            if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", expiry_text):
                raise ValueError
            expiry_date = date.fromisoformat(expiry_text)
        except ValueError:
            return "賞味期限は実在する日付（YYYY-MM-DD）で入力してください。", 400
    name = request.form["name"]
    quantity = int(request.form["quantity"])
    unit = request.form["unit"]

    food = Food(
        name=name,
        quantity=quantity,
        unit=unit,
        expiry_date=expiry_date
    )

    db.session.add(food)
    db.session.commit()

    return redirect("/")


with app.app_context():
    db.create_all()


if __name__ == "__main__":
    app.run(debug=True)
