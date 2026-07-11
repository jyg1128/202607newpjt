import json
import os
import urllib.error
import urllib.request
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

ROOT = os.path.dirname(os.path.abspath(__file__))
RUNTIME_API_KEY = None
ENV_FILE = os.path.join(ROOT, ".env")
if os.path.exists(ENV_FILE):
    with open(ENV_FILE, encoding="utf-8") as f:
        for line in f:
            if "=" in line and not line.lstrip().startswith("#"):
                key, value = line.strip().split("=", 1)
                os.environ.setdefault(key, value.strip().strip('"'))

FIELDS = ["paidDate", "paidTime", "merchant", "taxableAmount", "vat", "amount", "cardName", "approvalNumber"]
SCHEMA = {
    "type": "object", "additionalProperties": False,
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
            "type": "object", "additionalProperties": False,
            "properties": {k: {"type": "string", "enum": ["high", "medium", "low"]} for k in FIELDS},
            "required": FIELDS
        },
        "warnings": {"type": "array", "items": {"type": "string"}}
    },
    "required": FIELDS + ["confidence", "warnings"]
}

PROMPT = """한국 카드 영수증을 정밀 판독한다. 확대해서 숫자를 한 글자씩 확인하고 추측하지 않는다.
- merchant: 카드사/PG사가 아닌 영수증 상단의 실제 매장명 또는 가맹점명
- paidDate, paidTime: 출력일이 아니라 '매출일', '거래일시', '승인일시'에 해당하는 결제 날짜와 시간. 시간은 초가 보이면 HH:mm:ss, 초가 없으면 HH:mm:00
- taxableAmount: 반드시 '부가세 과세물품가액', '과세물품가액', '공급가액'에 인쇄된 값
- vat: 반드시 '부가세', 'VAT'에 인쇄된 값. 면세 또는 0이면 0
- amount: 합계/받을금액/결제금액 중 실제 카드 결제 총액
- cardName: 카드번호가 아닌 카드사명 또는 카드명. 예: 신한카드, 현대카드
- approvalNumber: '승인번호' 바로 옆의 전체 숫자/문자. 사업자번호와 혼동 금지
쉼표와 원 기호를 제거해 금액을 정수로 반환한다. 가려졌거나 흐리면 null과 low를 반환하고 경고에 한국어로 이유를 적는다."""

class Handler(SimpleHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/api/config/status":
            self.send_json(200, {"connected": bool(RUNTIME_API_KEY or os.getenv("OPENAI_API_KEY"))})
            return
        super().do_GET()

    def do_POST(self):
        global RUNTIME_API_KEY
        if self.path == "/api/config":
            try:
                length = int(self.headers.get("Content-Length", 0))
                api_key = json.loads(self.rfile.read(length)).get("apiKey", "").strip()
                if not api_key.startswith("sk-") or len(api_key) < 20:
                    self.send_json(400, {"error": "올바른 OpenAI API 키 형식이 아닙니다."})
                    return
                RUNTIME_API_KEY = api_key
                self.send_json(200, {"success": True})
            except Exception:
                self.send_json(400, {"error": "API 키를 처리하지 못했습니다."})
            return
        if self.path != "/api/recognize-receipt":
            self.send_error(404)
            return
        try:
            length = int(self.headers.get("Content-Length", 0))
            body = json.loads(self.rfile.read(length))
            image = body.get("imageBase64", "")
            if not image.startswith("data:image/"):
                raise ValueError("유효한 영수증 이미지가 필요합니다.")
            api_key = RUNTIME_API_KEY or os.getenv("OPENAI_API_KEY")
            if not api_key:
                self.send_json(503, {"error": "OPENAI_API_KEY가 설정되지 않았습니다. 프로젝트의 .env 파일에 키를 설정한 뒤 서버를 다시 시작해주세요."})
                return
            payload = {
                "model": os.getenv("OPENAI_MODEL", "gpt-5.4-mini"),
                "input": [{"role": "user", "content": [
                    {"type": "input_text", "text": PROMPT},
                    {"type": "input_image", "image_url": image, "detail": "high"}
                ]}],
                "text": {"format": {"type": "json_schema", "name": "receipt", "strict": True, "schema": SCHEMA}}
            }
            request = urllib.request.Request(
                "https://api.openai.com/v1/responses",
                data=json.dumps(payload).encode(),
                headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
            )
            with urllib.request.urlopen(request, timeout=90) as response:
                result = json.loads(response.read())
            output_text = result.get("output_text")
            if not output_text:
                for item in result.get("output", []):
                    for content in item.get("content", []):
                        if content.get("type") == "output_text":
                            output_text = content.get("text")
            extracted = json.loads(output_text)
            self.send_json(200, {"success": True, "extracted": {k: extracted[k] for k in FIELDS}, "confidence": extracted["confidence"], "warnings": extracted["warnings"]})
        except urllib.error.HTTPError as error:
            detail = error.read().decode("utf-8", "replace")
            self.send_json(error.code, {"error": "Vision API 요청에 실패했습니다.", "detail": detail})
        except Exception as error:
            self.send_json(500, {"error": str(error)})

    def send_json(self, status, data):
        encoded = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

if __name__ == "__main__":
    os.chdir(ROOT)
    print("Clearcost running at http://127.0.0.1:8000", flush=True)
    ThreadingHTTPServer(("127.0.0.1", 8000), Handler).serve_forever()
