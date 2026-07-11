import json
import os
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler

FIELDS = ["paidDate", "paidTime", "merchant", "taxableAmount", "vat", "amount", "cardName", "approvalNumber"]
SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "paidDate": {"type": ["string", "null"], "description": "YYYY-MM-DD"},
        "paidTime": {"type": ["string", "null"], "description": "HH:mm:ss"},
        "merchant": {"type": ["string", "null"]},
        "taxableAmount": {"type": ["integer", "null"]},
        "vat": {"type": ["integer", "null"]},
        "amount": {"type": ["integer", "null"]},
        "cardName": {"type": ["string", "null"]},
        "approvalNumber": {"type": ["string", "null"]},
        "confidence": {
            "type": "object",
            "additionalProperties": False,
            "properties": {key: {"type": "string", "enum": ["high", "medium", "low"]} for key in FIELDS},
            "required": FIELDS,
        },
        "warnings": {"type": "array", "items": {"type": "string"}},
    },
    "required": FIELDS + ["confidence", "warnings"],
}

PROMPT = """한국 카드 영수증을 정밀 판독한다. 확대해서 숫자를 한 글자씩 확인하고 추측하지 않는다.
- merchant: 카드사/PG사가 아닌 영수증 상단의 실제 매장명 또는 가맹점명
- paidDate, paidTime: 출력일이 아니라 매출일, 거래일시, 승인일시에 해당하는 결제 날짜와 시간. 시간은 초가 보이면 HH:mm:ss, 초가 없으면 HH:mm:00
- taxableAmount: 반드시 부가세 과세물품가액, 과세물품가액, 공급가액에 인쇄된 값
- vat: 반드시 부가세 또는 VAT에 인쇄된 값. 면세 또는 0이면 0
- amount: 합계, 받을금액, 결제금액 중 실제 카드 결제 총액
- cardName: 카드번호가 아닌 카드사명 또는 카드명
- approvalNumber: 승인번호 바로 옆의 전체 숫자/문자. 사업자번호와 혼동 금지
쉼표와 원 기호를 제거해 금액을 정수로 반환한다. 가려졌거나 흐리면 null과 low를 반환하고 경고에 한국어로 이유를 적는다."""

class handler(BaseHTTPRequestHandler):
    def do_POST(self):
        try:
            length = int(self.headers.get("Content-Length", 0))
            body = json.loads(self.rfile.read(length))
            image = body.get("imageBase64", "")
            if not image.startswith("data:image/"):
                self.send_json(400, {"error": "유효한 영수증 이미지가 필요합니다."})
                return
            api_key = (os.getenv("OPENAI_API_KEY") or "").strip()
            if not api_key:
                self.send_json(401, {"error": "OpenAI API 키를 먼저 연결해주세요."})
                return
            payload = {
                "model": os.getenv("OPENAI_MODEL", "gpt-5.4-mini"),
                "input": [{"role": "user", "content": [
                    {"type": "input_text", "text": PROMPT},
                    {"type": "input_image", "image_url": image, "detail": "high"},
                ]}],
                "text": {"format": {"type": "json_schema", "name": "receipt", "strict": True, "schema": SCHEMA}},
            }
            request = urllib.request.Request(
                "https://api.openai.com/v1/responses",
                data=json.dumps(payload).encode("utf-8"),
                headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            )
            with urllib.request.urlopen(request, timeout=55) as response:
                result = json.loads(response.read())
            output_text = result.get("output_text")
            if not output_text:
                for item in result.get("output", []):
                    for content in item.get("content", []):
                        if content.get("type") == "output_text":
                            output_text = content.get("text")
            extracted = json.loads(output_text)
            self.send_json(200, {
                "success": True,
                "extracted": {key: extracted[key] for key in FIELDS},
                "confidence": extracted["confidence"],
                "warnings": extracted["warnings"],
            })
        except urllib.error.HTTPError as error:
            detail = error.read().decode("utf-8", "replace")
            try:
                api_error = json.loads(detail).get("error", {})
                message = api_error.get("message", "OpenAI API 요청에 실패했습니다.")
            except Exception:
                message = "OpenAI API 요청에 실패했습니다."
            self.send_json(error.code, {"error": message})
        except Exception as error:
            self.send_json(500, {"error": str(error)})

    def do_GET(self):
        self.send_json(200, {"status": "ready"})

    def send_json(self, status, data):
        encoded = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)
