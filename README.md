# Clearcost 영수증 비용 등록 MVP

영수증 이미지 업로드 → AI 인식(Mock) → 결과 수정 → 프로젝트/아티스트 연결 → 정산 미리보기까지 이어지는 설치 없는 프론트엔드 프로토타입입니다.

## 실행

실제 Vision 인식을 위해 `.env.example`을 `.env`로 복사하고 `OPENAI_API_KEY`를 입력한 후 다음을 실행하세요.

```powershell
python server.py
```

그 후 `http://localhost:8000`에 접속합니다.

## 구현 범위

- 이미지 선택 및 드래그앤드롭, 미리보기
- 원본 고해상도 Vision 인식 및 JSON Schema 기반 구조화 결과
- 인식 결과 수정과 정확도 표시
- 프로젝트, 아티스트, 비용 항목, 사용 목적 등록
- 필수값 검증 및 localStorage 저장
- 정산 미리보기 합계와 영수증 보관함
- 모바일 반응형 화면

API 키는 브라우저에 노출하지 않고 로컬 서버에서만 읽습니다.

## Vercel 배포

`api/recognize-receipt.py`가 Vercel 서버리스 함수로 동작합니다. Vercel 프로젝트 설정의 Environment Variables에 `OPENAI_API_KEY`와 선택적으로 `OPENAI_MODEL`을 등록해야 합니다. API 키는 브라우저나 Git 저장소로 전달되지 않습니다.
