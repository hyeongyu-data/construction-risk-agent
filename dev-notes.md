# Civil.ai 개발 노트 (개인용)

> 깃허브 비공개 / 팀원 공유 X

---

## 프로젝트 개요

- **서비스명**: Civil.ai
- **시나리오**: 건설 공사 자재비/노무비/장비비 리스크 계산 AI 에이전트
- **현재 고객사 샘플**: 대성물산 (단일 테넌트 기준으로 개발 중)
- **LLM**: AWS Bedrock (Claude Haiku)
- **임베딩**: Amazon Titan Embed Text V2 (1024dim)
- **에이전트 프레임워크**: LangGraph ReAct

---

## 기술적 결정 사항

### SQLite → PostgreSQL (RDS) 전환
- **이유**: SQLite는 로컬 파일 기반이라 EC2 배포 시 공유 불가. RDS로 전환해 여러 서버에서 동일 DB 접근 가능하게
- **RDS 인스턴스**: `construction-risk-db` (db.t3.micro, PostgreSQL 18.3)
- **DB명**: `material_cost`
- **스키마 분리**: 자재(`public`), 장비(`equipment_cost`), RAG(`rag`) 스키마로 분리

### ChromaDB → pgvector 마이그레이션
- **이유**: ChromaDB는 별도 서버 필요. pgvector는 기존 RDS에 extension 추가만 하면 돼서 인프라 단순화
- **임베딩 차원**: 1024 (Amazon Titan Embed Text V2 기본값)
- **유사도**: cosine similarity
- **적재 완료**:
  - `rag.company_docs`: 사내 문서 5개 → 37청크
  - `rag.standard_spec`: 표준품셈 PDF → 83청크 (철근콘크리트/철골/방수 챕터)

### 에이전트 구조 결정 (라우터 → 병렬 노드)
- **구조**: `START → router → [weather / equipment / material / labor_cost] → END`
- **라우터 분류 기준**:
  - A타입: 기상 리스크 분석 (비용 산정 의도 없음)
  - B타입: 비용 산정 (장비/자재/인건비)
- **병렬 처리**: B타입은 equipment + material + labor_cost 동시 실행
- **Command 패턴**: router_node가 LangGraph Command로 직접 핸드오프 (conditional_edges 불사용)

---

## 트러블슈팅

### common.security 모듈 의존성 문제
- **현상**: `labor_cost` 브랜치의 `labor_cost_node.py`가 `common.security`를 import하는데 main에 없어서 실행 불가
- **해결**: `labor_cost` 브랜치에서 `common/` 폴더만 cherry-pick해서 main에 추가
- **커밋**: `28732060 feat: add common security module`
- **현재 상태**: main에 `common/security.py` 있음. router/nodes/labor_cost_node.py는 아직 stub

### equipment_node tools import 오류
- **현상**: equipment_node가 `construction_risk_agent-equipment_standby` 외부 폴더 참조하는데 경로 못 찾는 문제
- **해결**: `sys.path.insert`로 절대경로 동적 추가
- **커밋**: `d090bf1b Fix: handle missing equipment tools in equipment_node (#5)`

### feature/company-rag 브랜치 머지 지연
- **현상**: pgvector 마이그레이션 코드가 별도 브랜치에만 있어서 main에서 RAG 검색 안 됨
- **해결**: 여러 차례 머지 반복 (`bc382019`, `28bc5d3f`)
- **현재 상태**: main에 머지 완료

---

## 현재 구현 상태

### 완료
| 항목 | 내용 |
|------|------|
| DB 적재 | 자재/노무/장비/RAG 전부 RDS 완료 |
| 라우터 에이전트 | A/B 분류 + LangGraph 그래프 |
| 장비 노드 | ReAct 에이전트, 규격/대기일수 추론 로직 포함 |
| FastAPI 백엔드 | 프로젝트/대화/메시지/채팅 엔드포인트 |
| 프론트엔드 | 채팅 UI, 사이드바, 프로젝트 관리 (React + TypeScript) |
| common/security | 프롬프트 인젝션 탐지 모듈 |

### stub (미구현)
| 항목 | 내용 |
|------|------|
| router/nodes/labor_cost_node.py | stub만 있음. agents/labor_cost/ 실제 구현 연결 필요 |
| router/nodes/material_node.py | stub만 있음. agents/material_cost/ 실제 구현 연결 필요 |

### 남은 인프라
- EC2 배포 (소스코드 + API 서버)
- RDS 보안 그룹: EC2 SG에서 5432 포트 인바운드 허용 필요
- 프론트엔드 → 백엔드 API 연결

---

## 프론트엔드 구성 현황

```
frontend/client/src/
├── App.tsx          # 레이아웃, 상태 관리
├── api.ts           # REST API 호출 (프로젝트/대화/메시지/채팅)
├── types.ts         # Message, Project, Conversation 타입
└── components/
    ├── Sidebar.tsx  # Civil.AI 로고, 프로젝트 관리, 대화 목록
    └── ChatArea.tsx # 채팅 UI, 마크다운 렌더링, 로딩 애니메이션
```

**기획 중인 추가 기능**: 로그인/인증 (백엔드/DB 담당자 협의 필요)
- 필요: users 테이블, JWT 발급 API, 프론트 토큰 처리

---

## 인프라 메모

- **예산**: 월 20만원 이내
- **RDS**: db.t3.micro (프리티어 종료 후 과금 주의)
- **EC2-RDS 연결**: 같은 VPC면 보안 그룹 SG ID로 인바운드 허용 (IP 방식 쓰지 말 것 — 재시작 시 IP 변경됨)

---

## 환경변수 체크리스트

```
DB_HOST=
DB_PORT=5432
DB_NAME=material_cost
DB_USER=
DB_PASSWORD=
AWS_ACCESS_KEY_ID=
AWS_SECRET_ACCESS_KEY=
AWS_BEDROCK_REGION=us-east-1
MODEL_ID=us.anthropic.claude-haiku-4-5-20251001-v1:0
```
