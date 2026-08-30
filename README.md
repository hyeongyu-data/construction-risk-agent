# Construction Risk Agent

공사 리스크 기반 추가비용 산정 AI 에이전트. 건설 현장의 기상 악화·공정 지연·추가 물량·자재 단가
변화·장비 대기 등의 리스크를 분석해, 추가비용과 산정 근거를 공무용 리포트로 제공합니다.

**Stack** — FastAPI · LangGraph · AWS Bedrock(Claude / Titan) · PostgreSQL + pgvector · React + TypeScript

## Team & My Role

SK플래닛 생성형 AI 활용 데이터 엔지니어 부트캠프 · 5인 팀 프로젝트

**담당 — 최현규**

* **라우터 파이프라인 전담 설계·구현** (`agents/router/` — `router.py`, `graph.py`,
  `nodes/router_node.py`, `state.py`) — 초기 골격부터 작성. 플래너 기반 동적 라우팅: A/B 고정
  분기를 제거하고, 라우터가 질문을 분류하며 계획(`needs_weather`, `target_agents`)을 세운 뒤
  `Command`/`Send`로 필요한 노드만 호출. 직전 대화 맥락을 분류 입력에 포함해 후속 답변("B로 해줘")도
  올바르게 분류
* **synthesize 노드 전담 설계·구현** (`agents/router/nodes/synthesize_node.py`,
  `agents/router/synthesis_examples.py`) — `answer_type`별 최종 답변 형태 결정, `structured_response`
  카드 데이터 생성, 복잡한 비용 리포트용 few-shot 예시 세트 큐레이션
* **장비 대기비 에이전트 신규 구축** — `agents/equipment_cost/` 폴더 전체 최초 작성
  (tool 로직·테스트), 장비명 정규화 → 규격 매칭 → 일대여료 조회 → 대기율·대기일수 반영.
  장비 단가 DB 스키마·초기 적재(`db/equipment_cost/init_db.py`), 공종별 장비 데이터셋
  (`data/raw/equipment_cost/equipment_by_work_type.csv`) 구축 포함
* **후반 하드닝** — 팀 리드와 상의하며 라우팅 정확도·되묻기 처리·병합 유실 분기 복구 등 다수

**팀원 담당** — FastAPI 백엔드 · 인증/프로젝트/대화 API · `common/security.py` 인젝션 방어 ·
weather / material / labor_cost 노드 · 표준품셈·노임단가 데이터 · 자재단가 배치 DAG · React 프론트엔드

## 개요

현장 공무·구매·조달·원가관리 담당자가 자연어로 질문하면, 필요한 DB·RAG·외부 API를 조회해
추가비용 산정 리포트를 생성합니다. 단순 Q&A가 아니라 회계·구매·건설 관점을 결합한 의사결정 보조 도구.

```text
우레탄 방수 물량이 200㎡ 추가됐습니다. 계약단가 8,000원/㎡, 고정단가 계약입니다. 자재비를 계산해 주세요.
서울 문래동 콘크리트 타설이 비로 1일 지연될 경우, 펌프카 25m³ 장비 대기비를 산정해 주세요.
```

## 아키텍처 & 워크플로우

```text
React Frontend ── HTTP ──▶ FastAPI ── graph.stream() ──▶ LangGraph Workflow
                                                              │
   router_node ─ 분류 + 계획 + 보안 게이트 ─┬─ 인젝션/도메인 이탈  → BLOCKED
                                            ├─ CHAT / RAG_QA      → synthesize
                                            └─ COST/RISK_REPORT
                                                 ├─ needs_weather → weather_node ─(실패)─▶ synthesize
                                                 │                              └(성공)─┐
                                                 └─────────────────────────────────────┤
                                                    target_agents 병렬: equipment / material / labor_cost
                                                                          │
                                                                    synthesize_node ─▶ 자연어 리포트 + structured_response
```

* 그래프 정의: `agents/router/graph.py`. 라우터가 `Command`/`Send`로 직접 라우팅하므로
  `conditional_edges` 없음. 노드는 공용 `state`(`agents/router/state.py`)로만 통신
* `answer_type`: `CHAT | RAG_QA | COST_REPORT | RISK_REPORT | MISSING_INFO`
* LLM은 분류·추출·설명에, 실제 금액 계산은 도메인 tool 계층에서 (deterministic)
* 각 비용 노드는 리뷰·재시도·환각 검증 게이트 통과, 부족 정보는 답변 끝 "확인이 필요한 사항"으로 표면화

## 비용 산정

| 도메인 | 데이터 | 방식 |
| --- | --- | --- |
| Material | `material_prices` | 추가 물량 × 계약단가. 고정단가 계약이면 현재단가 차액은 참고값 분리 |
| Labor | `labor_cost.labor_cost` + 표준품셈 RAG | 투입 인원·일수 있으면 직접 계산, 없으면 RAG 단위품량 추정 |
| Equipment | `equipment_cost.equipment_rental` | 장비명 정규화 → 규격 매칭 → 일대여료 × 대기율 × 대기일수 |

## RAG

표준품셈 PDF와 사내 문서(PDF/Excel/Word)를 pdfplumber로 추출 → 항목/조항 단위 chunking →
Titan Embeddings(`amazon.titan-embed-text-v2:0`) → pgvector → similarity search.
`rag/labor_cost/`(단위품량 fallback·근거), `rag/company_docs/`(사내 문서). 자재 단가는 RAG가 아닌 테이블 조회.

## API

`api/main.py` 진입점, 문서 `http://localhost:8000/docs`.

| 라우터 | 엔드포인트 |
| --- | --- |
| `auth` | `POST /auth/register`, `POST /auth/login`, `GET /auth/me` (JWT) |
| `projects` | 프로젝트 CRUD + 멤버 관리 (role 기반) |
| `conversations` / `messages` | 대화 목록·생성·편집·삭제, 메시지 히스토리 |
| `chat` | `POST /conversations/{id}/chat` — LangGraph 실행 (핵심) |

모든 데이터 엔드포인트는 인증 + 대화 작성자/프로젝트 멤버 권한 체크. 인젝션 방어(`common/security.py`)는
유니코드 정규화 + 위험 패턴 검사로 라우터·주요 노드 진입 전 공통 적용.

## Directory

```text
agents/router/        LangGraph workflow · router · nodes · state · 보안 게이트
agents/{material,labor,equipment}_cost/   비용 계산 tool
agents/weather_risk/  KMA API client · parser · risk rule engine
api/  common/  db/(마이그레이션 001~006)  dags/  rag/  frontend/client/
```

## 실행

```bash
# Backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env          # KMA_API_KEY · DB_* · AWS_BEDROCK_REGION · MODEL_ID · JWT_SECRET_KEY
python db/run_migrations.py
uvicorn api.main:app --reload --port 8000

# Frontend
cd frontend/client && npm install && npm start   # :3000, API :8000 프록시

# CLI (그래프만 대화형)
cd agents/router && python chat.py
```

테스트: `python agents/router/test.py`, `python agents/{labor,equipment}_cost/test_agent.py`

## Notes

포트폴리오 공개용으로 정리한 버전입니다. 실제 API Key·DB 접속 정보·원본 계약 문서·민감 데이터는
포함하지 않습니다. 산정 결과는 의사결정 보조용이며, 실제 변경계약에는 발주처 기준·계약 조항 검토가
필요합니다.
