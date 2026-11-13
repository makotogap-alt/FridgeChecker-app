"""Receipt image extraction: no upload stored; external API is opt-in."""
import base64
import json
import os
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

UNITS = ("個", "本", "袋", "パック")
CATEGORIES = ("野菜", "肉・魚", "乳製品", "卵", "飲料", "調味料", "その他")


class ReceiptRecognitionError(Exception):
    pass


def normalize_items(raw):
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
    """One food per line, optionally: name,quantity,unit,category."""
    raw = []
    for line in text.splitlines():
        if not line.strip():
            continue
        parts = [p.strip() for p in line.replace("，", ",").split(",")]
        if len(parts) > 4:
            raise ReceiptRecognitionError("1行は「商品名,数量,単位,カテゴリ」で入力してください")
        raw.append({
            "name": parts[0], "quantity": parts[1] if len(parts)>1 and parts[1] else 1,
            "unit": parts[2] if len(parts)>2 and parts[2] else "個",
            "category": parts[3] if len(parts)>3 and parts[3] else "その他",
        })
    if len(raw)>30:
        raise ReceiptRecognitionError("一度に登録できる商品は30件までです")
    return normalize_items(raw)


def recognize_receipt(image_bytes, mime):
    key = os.environ.get("OPENAI_API_KEY")
    if not key:
        raise ReceiptRecognitionError("画像認識にはOPENAI_API_KEYの設定が必要です。下の手入力でも一括登録できます")

    instructions = (
        "日本のスーパーのレシートから購入した食品だけを抽出してください。"
        "店名、値段、合計、消費税、割引、非食品は除外。記載のない食品を創作しないこと。"
        "JSON object {\"items\":[{\"name\":string,\"quantity\":integer,\"unit\":string,\"category\":string}]}だけ返す。"
        "数量はパックや本数など購入単位。卵10個入り1パックは数量1・単位パック、"
        "牛乳2本は数量2・単位本。数量が不明なら1。"
        "unit は 個/本/袋/パック のいずれか。"
        "category は 野菜/肉・魚/乳製品/卵/飲料/調味料/その他 のいずれか。"
        "曖昧な名称でも印字された商品名に忠実に。30件まで。"
    )
    payload = {
        "model": os.environ.get("RECEIPT_MODEL", "gpt-4.1-mini"),
        "messages": [{"role": "user", "content": [
            {"type": "text", "text": instructions},
            {"type": "image_url", "image_url": {
                "url": f"data:{mime};base64,{base64.b64encode(image_bytes).decode('ascii')}"}},
        ]}],
        "response_format": {"type": "json_object"},
        "max_tokens": 2000,
    }
    request = Request(
        "https://api.openai.com/v1/chat/completions",
        data=json.dumps(payload, ensure_ascii=False).encode(),
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urlopen(request, timeout=25) as response:
            result = json.load(response)
        obj = json.loads(result["choices"][0]["message"]["content"])
        return normalize_items(obj.get("items"))
    except (HTTPError, URLError, TimeoutError, KeyError, ValueError, TypeError) as exc:
        raise ReceiptRecognitionError("画像認識に失敗しました。画像を撮り直すか手入力をご利用ください") from exc
