"""Receipts are reviewed before any database inventory changes."""
import hashlib
import secrets
from datetime import datetime, timezone

from flask import current_app, render_template, request, redirect, url_for, session
from itsdangerous import URLSafeTimedSerializer, BadSignature, SignatureExpired
from sqlalchemy.exc import IntegrityError

from receipt_service import ReceiptRecognitionError, parse_manual_lines, recognize_receipt, UNITS, CATEGORIES

MAX_IMAGE_BYTES = 4 * 1024 * 1024


def get_signer():
    return URLSafeTimedSerializer(current_app.secret_key, salt="receipt-import-v1")


def setup_receipt_routes(app, db, Food):
    class ReceiptImport(db.Model):
        __tablename__ = "receipt_import"
        id = db.Column(db.Integer, primary_key=True)
        fingerprint = db.Column(db.String(64), unique=True, nullable=False)
        created_at = db.Column(db.DateTime(timezone=True), nullable=False)

    def csrf_value():
        if "receipt_csrf" not in session:
            session["receipt_csrf"] = secrets.token_urlsafe(32)
        return session["receipt_csrf"]

    def valid_csrf():
        return secrets.compare_digest(str(request.form.get("csrf", "")), str(session.get("receipt_csrf", "missing")))

    @app.get('/receipt')
    def receipt_home():
        return render_template('receipt.html', csrf=csrf_value())

    @app.post('/receipt/analyze')
    def receipt_analyze():
        if not valid_csrf():
            return render_template('receipt.html', csrf=csrf_value(), error='画面を再読み込みしてください'), 403
        source = request.form.get('manual', '').strip()
        try:
            if source:
                if len(source)>4000:
                    return render_template('receipt.html', csrf=csrf_value(), error='入力は4000文字までです'), 400
                items = parse_manual_lines(source)
                # Manual entries have a fresh import token, not content-deduplicated.
                fingerprint = hashlib.sha256(secrets.token_bytes(32)).hexdigest()
            else:
                upload = request.files.get('receipt')
                if not upload or not upload.filename:
                    return render_template('receipt.html', csrf=csrf_value(), error='レシート画像か商品一覧を入力してください'), 400
                raw = upload.stream.read(MAX_IMAGE_BYTES+1)
                if not raw or len(raw)>MAX_IMAGE_BYTES:
                    return render_template('receipt.html', csrf=csrf_value(), error='画像は4MB以下にしてください'), 400
                if raw.startswith(b'\xff\xd8\xff'):
                    mime = 'image/jpeg'
                elif raw.startswith(b'\x89PNG\r\n\x1a\n'):
                    mime = 'image/png'
                elif raw.startswith(b'RIFF') and raw[8:12] == b'WEBP':
                    mime = 'image/webp'
                else:
                    return render_template('receipt.html', csrf=csrf_value(), error='JPEG・PNG・WebPの画像だけ使えます'), 400
                fingerprint = hashlib.sha256(raw).hexdigest()
                if ReceiptImport.query.filter_by(fingerprint=fingerprint).first():
                    return render_template('receipt.html', csrf=csrf_value(), error='このレシートは登録済みです'), 409
                items = recognize_receipt(raw, mime)
        except ReceiptRecognitionError as exc:
            return render_template('receipt.html', csrf=csrf_value(), error=str(exc)), 400

        token = get_signer().dumps({'fingerprint':fingerprint, 'count':len(items)})
        return render_template('receipt_review.html', items=items, token=token, csrf=csrf_value(),
                               units=UNITS, categories=CATEGORIES)

    @app.post('/receipt/confirm')
    def receipt_confirm():
        if not valid_csrf():
            return render_template('receipt.html', csrf=csrf_value(), error='画面を再読み込みしてください'), 403
        token = request.form.get('token','')
        try:
            payload = get_signer().loads(token, max_age=3600)
            fingerprint = payload['fingerprint']
            count = payload['count']
            if not isinstance(count,int) or count<1 or count>30 or len(fingerprint)!=64:
                raise BadSignature('invalid payload')
        except (BadSignature, SignatureExpired, KeyError, TypeError):
            return render_template('receipt.html', csrf=csrf_value(), error='確認画面の有効期限が切れました。最初からやり直してください'), 400
        if ReceiptImport.query.filter_by(fingerprint=fingerprint).first():
            return render_template('receipt.html', csrf=csrf_value(), error='このレシートは登録済みです'), 409

        checked = []
        for i in range(count):
            if request.form.get(f'include_{i}') != 'on':
                continue
            name = request.form.get(f'name_{i}', '').strip()
            unit = request.form.get(f'unit_{i}', '')
            category = request.form.get(f'category_{i}', '')
            try:
                quantity = int(request.form.get(f'quantity_{i}', ''))
                from app import parse_expiration_date
                expiration = parse_expiration_date(request.form.get(f'expiration_{i}', ''))
            except ValueError:
                return render_template('receipt.html', csrf=csrf_value(), error='数量または賞味期限が正しくありません'), 400
            if not name or len(name)>100 or unit not in UNITS or category not in CATEGORIES or not 1<=quantity<=10000:
                return render_template('receipt.html', csrf=csrf_value(), error='商品情報を確認してください'), 400
            checked.append((name,quantity,unit,category,expiration))
        if not checked:
            return render_template('receipt.html', csrf=csrf_value(), error='登録する食品を1件以上選択してください'), 400

        # Atomic: merge compatible batches, persist receipt fingerprint, commit once.
        try:
            for name,quantity,unit,category,expiration in checked:
                food = Food.query.filter_by(name=name,unit=unit,category=category,
                                            expiration_date=expiration).first()
                if food:
                    if food.quantity+quantity>10000:
                        db.session.rollback()
                        return render_template('receipt.html', csrf=csrf_value(), error='在庫が上限10000を超える商品があります'), 400
                    food.quantity+=quantity
                else:
                    db.session.add(Food(name=name,quantity=quantity,unit=unit,
                                        category=category,expiration_date=expiration))
            db.session.add(ReceiptImport(fingerprint=fingerprint,created_at=datetime.now(timezone.utc)))
            db.session.commit()
        except IntegrityError:
            db.session.rollback()
            return render_template('receipt.html', csrf=csrf_value(), error='このレシートは既に登録された可能性があります'), 409
        return redirect(url_for('index'))

    return ReceiptImport
