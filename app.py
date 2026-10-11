import os
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


@app.route("/")
def index():
    foods = Food.query.all()
    return render_template("index.html", foods=foods)


@app.route("/add", methods=["POST"])
def add_food():
    name = request.form["name"]
    quantity = int(request.form["quantity"])
    unit = request.form["unit"]

    food = Food(
        name=name,
        quantity=quantity,
        unit=unit
    )

    db.session.add(food)
    db.session.commit()

    return redirect("/")


with app.app_context():
    db.create_all()


if __name__ == "__main__":
    app.run(debug=True)