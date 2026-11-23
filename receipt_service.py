"""Local Japanese receipt OCR (no external image API).

Tesseract extracts printed text. A conservative rule-based parser produces
food candidates; users must review them before any inventory is changed.
"""
import io
import re
import unicodedata

from PIL import Image, ImageEnhance, ImageOps, UnidentifiedImageError
import pytesseract

UNITS = ("個", "本", "袋", "パック")
CATEGORIES = ("野菜", "肉・魚", "乳製品", "卵", "飲料", "調味料", "その他")

# These are intentionally conservative: don't silently create inventory from
# arbitrary strings such as store names, prices or nonfood products.
FOOD_TERMS = (
    ("乳製品", ("牛乳", "ミルク", "ヨーグルト", "チーズ", "バター", "生クリーム")),
    ("卵", ("たまご", "タマゴ", "玉子", "鶏卵", "エッグ", "卵")),
    ("野菜", ("トマト", "キュウリ", "きゅうり", "キャベツ", "レタス", "にんじん", "人参", "玉ねぎ", "たまねぎ", "じゃがいも", "大根", "ねぎ", "ネギ", "白菜", "ほうれん草", "小松菜", "もやし", "ピーマン", "ブロッコリー", "きのこ", "しいたけ", "えのき", "しめじ", "なす", "ナス", "かぼちゃ", "さつまいも", "生姜", "しょうが", "にんにく")),
    ("肉・魚", ("鶏肉", "豚肉", "牛肉", "ひき肉", "挽肉", "鶏むね", "鶏もも", "刺身", "鮭", "サケ", "サーモン", "サバ", "鯖", "まぐろ", "マグロ", "ツナ", "ハム", "ベーコン", "ウインナー", "ソーセージ", "切り身")),
    ("飲料", ("豆乳", "ジュース", "コーヒー", "紅茶", "緑茶", "麦茶", "ほうじ茶", "ウーロン茶", "お茶", "ミネラルウォーター", "炭酸水", "飲料", "コーラ", "スポーツドリンク")),
    ("調味料", ("しょうゆ", "醤油", "みそ", "味噌", "ケチャップ", "マヨネーズ", "ドレッシング", "みりん", "料理酒", "こしょう", "胡椒", "砂糖", "食塩", "サラダ油", "ごま油", "オリーブオイル", "酢", "ソース")),
    ("その他", ("食パン", "菓子パン", "パン", "米", "ごはん", "ご飯", "うどん", "そば", "ラーメン", "パスタ", "納豆", "豆腐", "ちくわ", "こんにゃく", "餅", "のり", "海苔", "カレー", "チョコ", "クッキー", "せんべい", "おにぎり", "弁当", "りんご", "リンゴ", "バナナ", "みかん", "いちご", "イチゴ")),
)

SKIP_TERMS = (
    "合計", "小計", "総計", "消費税", "税抜", "税込", "税額", "内税", "外税", "軽減税率",
    "お預", "お釣", "釣銭", "現金", "支払", "決済", "クレジット", "電子マネー",
    "ポイント", "割引", "値引", "クーポン", "レジ", "レシート", "領収", "担当",
    "店員", "電話", "営業時間", "ありがとう", "店舗", "商品点数", "サービスカウンター",
    "カード", "精算", "袋代", "お買上", "お買い上", "免税", "引換", "還元", "合算",
)

# Detect purchase counts only when explicitly separated from the product name.
# For example, the "10個" in "たまご10個" is package size, not 10 packs.
MULTIPLIER_RE = re.compile(r"(?:[xX×＊*]\s*(\d{1,3})|(?:^|\s)(\d{1,3})\s*(本|袋|パック|個|点)(?=\s|$))")
TRAILING_PRICE_RE = re.compile(r"\s+[¥￥]?\d{2,3}(?:,\d{3})*(?:円)?\s*$|\s+[¥￥]?\d{4,6}(?:円)?\s*$")


class ReceiptRecognitionError(Exception):
    pass


def normalize_items(raw):
    """Reuse the previous manual-entry contract and validation rules."""
    if not isinstance(raw, list):
        raise ReceiptRecognitionError("商品の一覧を読み取れませんでした")
    items = []
    for obj in raw[:30]:
        if not isinstance(obj, dict):
            continue
        name = str(obj.get("name") or "").strip()
        if not name or len(name) > 100:
            continue
        try:
            quantity = int(obj.get("quantity", 1))
        except (ValueError, TypeError):
            quantity = 1
        quantity = max(1, min(10000, quantity))
        unit = str(obj.get("unit") or "個")
        category = str(obj.get("category") or "その他")
        items.append({
            "name": name, "quantity": quantity,
            "unit": unit if unit in UNITS else "個",
            "category": category if category in CATEGORIES else "その他",
            "expiration_date": "",
        })
    if not items:
        raise ReceiptRecognitionError("食品を認識できませんでした。手入力をご利用ください")
    return items


def parse_manual_lines(text):
    """One food per line: name,quantity,unit,category."""
    raw = []
    for line in text.splitlines():
        if not line.strip():
            continue
        parts = [p.strip() for p in line.replace("，", ",").split(",")]
        if len(parts) > 4:
            raise ReceiptRecognitionError("1行は「商品名,数量,単位,カテゴリ」で入力してください")
        raw.append({
            "name": parts[0],
            "quantity": parts[1] if len(parts) > 1 and parts[1] else 1,
            "unit": parts[2] if len(parts) > 2 and parts[2] else "個",
            "category": parts[3] if len(parts) > 3 and parts[3] else "その他",
        })
    if len(raw) > 30:
        raise ReceiptRecognitionError("一度に登録できる商品は30件までです")
    return normalize_items(raw)


def _category_of(value):
    normalized = unicodedata.normalize("NFKC", value).lower()
    for category, terms in FOOD_TERMS:
        if any(unicodedata.normalize("NFKC", term).lower() in normalized for term in terms):
            return category
    return None


def _unit_of(name, category, explicit=None):
    if explicit in UNITS:
        return explicit
    if category == "卵" and re.search(r"\d+\s*個", name):
        return "パック"
    if "牛乳" in name or "ミルク" in name or any(t in name for t in ("ジュース", "お茶", "コーヒー", "コーラ", "豆乳")):
        return "本"
    if "パン" in name or "もやし" in name:
        return "袋"
    return "個"


def parse_receipt_text(text):
    """Conservatively extract familiar food items from Japanese OCR text.

    Other products are not invented or classified blindly; the raw OCR text
    is exposed in the review screen to let the user add anything missed.
    """
    extracted = []
    for original in text.splitlines():
        line = unicodedata.normalize("NFKC", original).strip()
        if not line or len(line) > 150 or any(t.lower() in line.lower() for t in SKIP_TERMS):
            continue
        # Ignore bare prices, dates, URLs and register metadata.
        if not re.search(r"[ぁ-んァ-ヶ一-龥]", line):
            continue
        line = re.sub(r"^[\s#*＊◆■・\-]+", "", line)
        line = re.sub(r"[\s　]+", " ", line)
        # A price (or several prices) at the right end of a line isn't a food name.
        for _ in range(3):
            stripped = TRAILING_PRICE_RE.sub("", line).strip()
            if stripped == line:
                break
            line = stripped
        category = _category_of(line)
        if category is None:
            continue
        qty = 1
        unit = None
        match = MULTIPLIER_RE.search(line)
        if match:
            candidate = int(match.group(1) or match.group(2))
            if 1 <= candidate <= 100:
                qty = candidate
                unit = match.group(3)
                if unit == "点":
                    unit = None
                line = (line[:match.start()] + " " + line[match.end():]).strip()
        # Never keep prices inside the visible product name; leave package sizes.
        # Some receipts print counts after a price (e.g., "牛乳 218 2点").
        # A second pass removes that price after the count is stripped.
        for _ in range(3):
            stripped = TRAILING_PRICE_RE.sub("", line).strip()
            if stripped == line:
                break
            line = stripped
        name = re.sub(r"\s{2,}", " ", line).strip(" -・*/")[:100]
        if not name or not _category_of(name):
            continue
        extracted.append({"name": name, "quantity": qty,
                          "unit": _unit_of(name, category, unit), "category": category})
        if len(extracted) >= 30:
            break
    if not extracted:
        raise ReceiptRecognitionError(
            "食品の候補を抽出できませんでした。撮影し直すか、下の手入力をご利用ください"
        )
    return normalize_items(extracted)


def recognize_receipt_detailed(image_bytes, mime):
    """Return (food candidates, raw OCR text) without external API calls."""
    try:
        with Image.open(io.BytesIO(image_bytes)) as opened:
            allowed = {"image/jpeg": "JPEG", "image/png": "PNG", "image/webp": "WEBP"}
            if opened.format != allowed.get(mime):
                raise ReceiptRecognitionError("画像の形式が一致しません。JPEG・PNG・WebPをご利用ください")
            width, height = opened.size
            if width < 120 or height < 120 or width * height > 16_000_000:
                raise ReceiptRecognitionError("画像サイズが適切ではありません。別の写真をお試しください")
            fixed = ImageOps.exif_transpose(opened)
            if max(fixed.size) > 1800:
                fixed.thumbnail((1800, 1800), Image.Resampling.LANCZOS)
            gray = ImageOps.grayscale(fixed)
            image = ImageEnhance.Contrast(ImageOps.autocontrast(gray)).enhance(1.35)
        # Hard timeout prevents malformed/huge inputs from blocking a web worker.
        raw_text = pytesseract.image_to_string(
            image, lang="jpn+eng", config="--psm 6", timeout=60
        )
    except pytesseract.TesseractNotFoundError as exc:
        raise ReceiptRecognitionError("サーバーにTesseractがありません。Dockerの設定を確認してください") from exc
    except pytesseract.TesseractError as exc:
        raise ReceiptRecognitionError("OCRが失敗しました。日本語言語データの設定を確認してください") from exc
    except RuntimeError as exc:  # pytesseract may raise RuntimeError on timeout.
        raise ReceiptRecognitionError("画像の読み取りが時間切れになりました。小さな写真でお試しください") from exc
    except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombError) as exc:
        raise ReceiptRecognitionError("画像を開けませんでした。別の写真をお試しください") from exc
    raw_text = raw_text.strip()
    if not raw_text:
        raise ReceiptRecognitionError("レシートの文字を読み取れませんでした。明るい場所で撮影してください")
    try:
        candidates = parse_receipt_text(raw_text)
    except ReceiptRecognitionError:
        # Text can be legible even when no product matches our limited list.
        # Allow the review page to display it and accept manually added foods.
        candidates = []
    return candidates, raw_text[:6000]


def recognize_receipt(image_bytes, mime):
    """Compatibility with existing receipt routes and tests."""
    return recognize_receipt_detailed(image_bytes, mime)[0]
