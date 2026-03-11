# Platform Evolution Roadmap

> 2026-03-11 작성 | 3개 트랙 병렬 진행

---

## Track 1: Security & Authentication

### 현재 상태 (Critical)

| 문제 | 위치 | 심각도 |
|------|------|--------|
| DB 비밀번호 하드코딩 | `core/database.py:5` — `password1234` 직접 노출 | CRITICAL |
| 인증 미구현 | `chat/router.py:86-94` — `_get_optional_user()` 항상 None | CRITICAL |
| role 쿼리 파라미터 위조 가능 | `project_router.py:67`, `settings_router.py:73` — `?role=admin`으로 우회 | CRITICAL |
| API Key 평문 DB 저장 | `core/models.py:146` — `SolverSettingDB.api_key` 암호화 없음 | HIGH |
| CORS 전체 허용 | `main.py:44-51` — `allow_methods=["*"]`, `allow_headers=["*"]` | HIGH |
| 프론트엔드 토큰 미검증 | `ChatInterface.tsx:179` — Bearer 토큰 전송하지만 백엔드 무시 | MEDIUM |

### Phase S1: 긴급 시크릿 정리 (1일)

**WHY**: 하드코딩된 비밀번호와 API 키가 소스에 노출 — 즉시 수정 필요

#### S1-1: DB 연결 환경변수화
```
변경 파일: core/database.py
현재: SQLALCHEMY_DATABASE_URL = "postgresql://postgres:password1234@..."
변경: SQLALCHEMY_DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://...")
```

#### S1-2: .env.example 생성
```
변경 파일: .env.example (신규)
내용:
  DATABASE_URL=postgresql://postgres:changeme@localhost:5432/quantum_db
  GOOGLE_API_KEY=your-key-here
  DWAVE_API_TOKEN=your-token-here
  JWT_SECRET_KEY=generate-random-secret
  CORS_ORIGINS=http://localhost:5173
```

#### S1-3: API 키 로테이션
- Google Gemini API 키 재발급
- D-Wave API 토큰 재발급
- git history에서 .env 제거 (BFG Repo-Cleaner)

### Phase S2: JWT 인증 구현 (3~5일)

**WHY**: 모든 API가 무인증 — 누구나 모든 프로젝트 접근/삭제 가능

#### S2-1: 의존성 추가
```
패키지: python-jose[cryptography], passlib[bcrypt]
```

#### S2-2: 인증 모듈 생성
```
신규 파일: core/auth.py
구현:
  - create_access_token(user_id, role) -> JWT
  - verify_token(token) -> UserPayload
  - get_current_user = Depends() 미들웨어
  - hash_password() / verify_password()
```

#### S2-3: User 모델 + 테이블
```
신규: core/models.py에 UserDB 추가
  - id, username, hashed_password, role, created_at
  - schema: core.users
```

#### S2-4: Auth 라우터
```
신규 파일: core/auth_router.py
  POST /api/auth/login  -> JWT 발급
  POST /api/auth/register -> 계정 생성 (admin only)
  GET  /api/auth/me -> 현재 사용자 정보
```

#### S2-5: 기존 라우터 마이그레이션
```
변경 파일: chat/router.py, project_router.py, settings_router.py
변경 내용:
  - Query param role/user 제거
  - Depends(get_current_user) 주입
  - 권한 검사: user.role == "admin" (서버사이드)
```

#### S2-6: 프론트엔드 연동
```
변경 파일: AuthContext.tsx, ChatInterface.tsx
변경 내용:
  - LoginScreen → POST /api/auth/login → JWT 저장
  - 모든 fetch에 Authorization: Bearer {token} 헤더
  - 401 응답 시 로그인 화면 리다이렉트
```

### Phase S3: API 보안 강화 (2~3일)

#### S3-1: CORS 제한
```python
# main.py
allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
allow_headers=["Authorization", "Content-Type"],
```

#### S3-2: Rate Limiting
```
패키지: slowapi
적용: /api/chat/message (분당 30), /api/upload (분당 10), /api/solve (분당 5)
```

#### S3-3: Solver API Key 암호화
```
방법: Fernet 대칭 암호화 (cryptography 패키지)
저장: 암호화된 값 → DB, 복호화 키 → 환경변수
변경: SolverSettingDB.api_key → encrypted_api_key
```

---

## Track 2: Data Management & Scalability

### 현재 상태

| 문제 | 위치 | 심각도 |
|------|------|--------|
| 프로젝트 삭제 시 파일 미정리 | `project_router.py:75-116` — DB만 삭제, uploads/ 잔류 | HIGH |
| 솔버 실행 HTTP 차단 | `chat/router.py:636-758` — 최대 3600초 동기 대기 | CRITICAL |
| Celery 구성만 존재, 미사용 | `core/celery_app.py` 존재, /solve에서 미호출 | MEDIUM |
| 세션 캐시 무한 증가 | `session.py:_sessions` — 제거 정책 없음 | HIGH |
| 마이그레이션 체계 없음 | `main.py:60-95` — 수동 ALTER TABLE | MEDIUM |

### Phase D1: 파일 생명주기 관리 (1~2일)

**WHY**: 프로젝트 삭제 시 uploads/ 파일이 영구 잔류 — 디스크 누수

#### D1-1: 프로젝트 삭제 시 파일 정리
```python
# core/project_router.py DELETE 엔드포인트에 추가
import shutil
upload_dir = Path("uploads") / str(project_id)
if upload_dir.exists():
    shutil.rmtree(upload_dir)
```

#### D1-2: 고아 파일 정리 스크립트
```
신규 파일: scripts/cleanup_orphan_uploads.py
로직: uploads/ 내 폴더 중 DB에 없는 project_id → 삭제 후보 리포트
실행: cron 또는 수동 (--dry-run 옵션)
```

### Phase D2: 비동기 솔버 실행 (3~5일)

**WHY**: `/solve` 엔드포인트가 최대 1시간 HTTP 차단 — 타임아웃, UX 저하

#### D2-1: Job 기반 비동기 실행
```
기존 활용: core/celery_app.py + engine/hybrid_orchestrator.py (이미 정의됨)

변경 파일: chat/router.py /solve 엔드포인트
현재: await _pipeline.run() → 동기 대기 → 응답
변경:
  1. JobDB 레코드 생성 (status=PENDING)
  2. celery_app.send_task("execute_solver_job", args=[job_id, ...])
  3. 즉시 응답: {"job_id": 123, "status": "PENDING"}
```

#### D2-2: Job 상태 조회 API
```
신규 엔드포인트: GET /api/jobs/{job_id}/status
응답: {"status": "RUNNING|COMPLETE|FAILED", "progress": 0.7, "result": ...}
```

#### D2-3: 프론트엔드 폴링
```
변경 파일: SolverView.tsx
로직:
  1. POST /solve → job_id 수신
  2. setInterval(3초) → GET /api/jobs/{job_id}/status
  3. COMPLETE → 결과 표시
  4. FAILED → 에러 표시
향후: WebSocket 전환 (Phase D4)
```

#### D2-4: Celery Worker 실행 가이드
```
# 별도 터미널
celery -A core.celery_app worker --loglevel=info --pool=solo
# 필수: Redis 서버 실행 중이어야 함
```

### Phase D3: 세션 캐시 관리 (1일)

**WHY**: `_sessions` dict가 무한 증가 — 장기 운영 시 메모리 부족

#### D3-1: LRU 캐시 + TTL 적용
```python
# core/platform/session.py
from collections import OrderedDict
import time

_MAX_SESSIONS = 100
_SESSION_TTL_SEC = 3600  # 1시간 미사용 시 제거

class _SessionCache:
    """LRU + TTL 세션 캐시"""
    def __init__(self, max_size=_MAX_SESSIONS):
        self._cache: OrderedDict[str, tuple[CrewSession, float]] = OrderedDict()
        self._max_size = max_size

    def get(self, key: str) -> Optional[CrewSession]:
        if key in self._cache:
            session, ts = self._cache[key]
            if time.time() - ts > _SESSION_TTL_SEC:
                # TTL 만료 → DB에 저장 후 제거
                save_session_state(key, session.state)
                del self._cache[key]
                return None
            # LRU: 최근 사용으로 이동
            self._cache.move_to_end(key)
            self._cache[key] = (session, time.time())
            return session
        return None

    def put(self, key: str, session: CrewSession):
        if len(self._cache) >= self._max_size:
            # 가장 오래된 항목 제거 (DB에 저장 후)
            old_key, (old_session, _) = self._cache.popitem(last=False)
            save_session_state(old_key, old_session.state)
        self._cache[key] = (session, time.time())

_sessions = _SessionCache()
```

### Phase D4: Alembic 마이그레이션 도입 (2일)

**WHY**: 수동 ALTER TABLE은 추적 불가, 롤백 불가, 협업 시 충돌 위험

#### D4-1: Alembic 초기화
```bash
pip install alembic
alembic init migrations
# alembic.ini에 sqlalchemy.url = env:DATABASE_URL 설정
```

#### D4-2: 기존 스키마 기준 초기 마이그레이션
```bash
alembic revision --autogenerate -m "initial schema from existing tables"
alembic stamp head  # 현재 DB를 최신으로 마킹
```

#### D4-3: main.py 자동 마이그레이션 제거
```
삭제: main.py의 _migrate_solver_settings(), _migrate_session_states()
대체: alembic upgrade head (startup 또는 CI/CD)
```

---

## Track 3: Multi-Agent Architecture

### 현재 상태 → 목표 상태

```
현재: Single Agent (CrewAgent._run_inner 200줄 모놀리식)
      ↓ 키워드 분류 → 하드코딩 분기 → 1턴 1스킬 → 동기 실행

목표: Multi-Agent Supervisor 패턴
      ↓ Supervisor 계획 → Agent 위임 → 자체 검증 → 병렬 실행
```

### Phase M1: Agent 인터페이스 표준화 (2~3일)

**WHY**: 현재 스킬이 함수 — Agent로 전환하려면 공통 인터페이스 필요

#### M1-1: 기반 클래스 정의
```
신규 파일: core/agents/base.py

@dataclass
class AgentTask:
    intent: str              # "analyze_data", "generate_model" 등
    message: str             # 사용자 원본 메시지
    parameters: Dict         # LLM이 추출한 파라미터
    priority: str = "normal" # "high", "normal", "low"

@dataclass
class AgentContext:
    project_id: str
    domain: Optional[str]
    pipeline_phase: str
    data: Dict               # 필요한 데이터만 (전체 SessionState 아님)
    history: List[Dict]      # 최근 대화 (최대 10턴)

@dataclass
class AgentResult:
    success: bool
    response: Dict           # 프론트엔드 응답 (type, text, data, options)
    state_updates: Dict      # SessionState 변경 사항 (부분 업데이트)
    next_agent: Optional[str]  # 다음 추천 에이전트
    artifacts: Dict = field(default_factory=dict)  # 중간 산출물

class BaseAgent(ABC):
    agent_id: str
    description: str
    required_context: List[str]  # 필요한 SessionState 필드 목록

    @abstractmethod
    async def execute(self, task: AgentTask, ctx: AgentContext) -> AgentResult:
        ...

    def build_context(self, state: SessionState) -> AgentContext:
        """SessionState에서 필요한 필드만 추출"""
        data = {f: getattr(state, f) for f in self.required_context}
        return AgentContext(
            project_id=state.project_id,
            domain=state.detected_domain,
            pipeline_phase=self._detect_phase(state),
            data=data,
            history=[],
        )
```

#### M1-2: 에이전트 레지스트리
```
신규 파일: core/agents/registry.py

class AgentRegistry:
    _agents: Dict[str, BaseAgent] = {}

    def register(self, agent: BaseAgent):
        self._agents[agent.agent_id] = agent

    def get(self, agent_id: str) -> BaseAgent:
        return self._agents[agent_id]

    def list_agents(self) -> List[Dict]:
        return [{"id": a.agent_id, "desc": a.description} for a in self._agents.values()]
```

#### M1-3: 기존 스킬 → Agent 래핑 (동작 변경 없음)
```
신규 파일: core/agents/data_agent.py

class DataAgent(BaseAgent):
    agent_id = "data_agent"
    description = "데이터 분석, 프로파일링, 정규화"
    required_context = ["file_uploaded", "uploaded_files", "csv_summary",
                        "analysis_completed", "last_analysis_report",
                        "data_facts", "data_profile", "detected_domain"]

    async def execute(self, task, ctx):
        # 기존 skill_analyze() 호출 — 래핑만
        if task.intent == "analyze":
            result = await skill_analyze(self.model, session, ...)
            return AgentResult(
                success=True,
                response=result,
                state_updates={"analysis_completed": True, ...},
            )
```

```
래핑 대상 (5개 Agent):
  DataAgent       ← skill_analyze + skill_structural_normalization + skill_data_normalization
  ModelingAgent   ← skill_problem_definition + skill_math_model + math_model_generator
  SolverAgent     ← skill_pre_decision + skill_start_optimization + solver_pipeline
  DomainExpert    ← domain_loader + knowledge YAML 조회
  GeneralAgent    ← skill_general + skill_answer
```

### Phase M2: Supervisor Agent 도입 (3~5일)

**WHY**: `_run_inner()` 200줄 분기를 LLM 기반 동적 계획으로 전환

#### M2-1: Supervisor 구현
```
신규 파일: core/agents/supervisor.py

class SupervisorAgent:
    """의도 파악 → 계획 수립 → 에이전트 위임 → 결과 종합"""

    async def run(self, message, session, ...):
        # Fast-path: 키워드 분류 (기존 quick_classify 유지 — 비용 절감)
        intent = self.classifier.quick_classify(message)
        if intent:
            agent = self.registry.get(self._intent_to_agent[intent])
            task = AgentTask(intent=intent, message=message, parameters={})
            ctx = agent.build_context(session.state)
            result = await agent.execute(task, ctx)
            self._apply_state_updates(session.state, result.state_updates)
            return result.response

        # Slow-path: LLM 계획 수립
        plan = await self._plan(message, session)
        results = []
        for step in plan.steps:
            agent = self.registry.get(step.agent_id)
            task = AgentTask(intent=step.intent, message=message, parameters=step.params)
            ctx = agent.build_context(session.state)
            result = await agent.execute(task, ctx)
            self._apply_state_updates(session.state, result.state_updates)
            results.append(result)

            # 중간 검토: 사용자 입력 필요?
            if result.next_agent == "ask_user":
                break

        return self._synthesize(results)
```

#### M2-2: 계획 수립 프롬프트
```
신규 파일: prompts/supervisor_plan.md

당신은 최적화 플랫폼의 감독 에이전트입니다.
사용자 메시지와 현재 상태를 분석하여 실행 계획을 수립하세요.

[사용 가능한 에이전트]
- data_agent: 데이터 분석, 프로파일링, 정규화
- modeling_agent: 문제 정의, 수학 모델 생성
- solver_agent: 솔버 추천, 최적화 실행
- domain_expert: 도메인 지식 조회
- general_agent: 일반 질문 응답

[현재 상태]
{state_block}

[사용자 메시지]
{message}

JSON으로 응답:
{"steps": [{"agent_id": "...", "intent": "...", "params": {...}}]}
```

#### M2-3: agent.py 전환
```
변경 파일: domains/crew/agent.py
변경 내용:
  - _run_inner() → SupervisorAgent.run()으로 위임
  - 기존 하드코딩 분기 제거
  - CrewAgent는 SupervisorAgent의 thin wrapper로 유지 (호환성)
```

### Phase M3: LLM 모델 분리 (1~2일)

**WHY**: 수학 모델 생성에 flash-lite 사용 → 복잡한 제약조건 누락 빈도 높음

#### M3-1: Agent별 모델 설정
```
변경 파일: core/config.py

class Settings:
    # Routing (빠른 분류) - 경량 모델
    MODEL_ROUTER = os.getenv("MODEL_ROUTER", "gemini-2.5-flash-lite")
    # Analysis (데이터 분석) - 중간 모델
    MODEL_ANALYSIS = os.getenv("MODEL_ANALYSIS", "gemini-2.5-flash")
    # Modeling (수학 모델) - 고성능 모델
    MODEL_MODELING = os.getenv("MODEL_MODELING", "gemini-2.5-pro")
    # Review (검증) - 고성능 모델 (cross-check)
    MODEL_REVIEW = os.getenv("MODEL_REVIEW", "gemini-2.5-pro")
    # Chat (일반 대화) - 경량 모델
    MODEL_CHAT = os.getenv("MODEL_CHAT", "gemini-2.5-flash-lite")
```

#### M3-2: Agent 초기화 시 모델 주입
```python
# core/agents/registry.py 등록 시
registry.register(DataAgent(model=get_model(settings.MODEL_ANALYSIS)))
registry.register(ModelingAgent(model=get_model(settings.MODEL_MODELING)))
registry.register(SolverAgent(model=None))  # LLM 불필요
registry.register(GeneralAgent(model=get_model(settings.MODEL_CHAT)))
```

### Phase M4: QA Reviewer Agent + Self-Reflection (3~5일)

**WHY**: 수학 모델 생성 → 즉시 사용자 전달 — 자체 검증 없이 오류 전파

#### M4-1: Reviewer Agent 구현
```
신규 파일: core/agents/reviewer_agent.py

class ReviewerAgent(BaseAgent):
    agent_id = "reviewer"
    description = "생성 결과 품질 검증, 개선 제안"

    async def execute(self, task, ctx):
        if task.intent == "review_math_model":
            model_json = ctx.data["math_model"]
            domain_knowledge = load_domain_knowledge(ctx.domain)

            # 1. 구조 검증 (기존 Gate2)
            gate_result = gate2_validate(model_json)

            # 2. 의미 검증 (LLM — 생성 모델과 다른 모델 사용)
            review_prompt = self._build_review_prompt(model_json, domain_knowledge)
            review = await self.model.generate_content(review_prompt)

            # 3. 결과
            if gate_result.has_errors or review.has_issues:
                return AgentResult(
                    success=False,
                    next_agent="modeling_agent",  # 재생성 요청
                    artifacts={"review_feedback": review.suggestions},
                )
            return AgentResult(success=True, ...)
```

#### M4-2: Supervisor에 검증 루프 통합
```python
# core/agents/supervisor.py
async def _plan_with_review(self, ...):
    plan = [
        Step("modeling_agent", "generate_model"),
        Step("reviewer", "review_math_model"),  # 자동 검증
    ]
    # 검증 실패 시 최대 2회 재생성
    for attempt in range(3):
        model_result = await self.execute_step(plan[0])
        review_result = await self.execute_step(plan[1])
        if review_result.success:
            break
        # 피드백 포함 재생성
        plan[0].params["feedback"] = review_result.artifacts["review_feedback"]
```

### Phase M5: 병렬 실행 & 복합 요청 (2~3일)

**WHY**: "데이터 분석하고 문제 정의해줘" → 현재 1개만 실행

#### M5-1: 병렬 실행 지원
```python
# core/agents/supervisor.py
async def _execute_parallel(self, steps: List[Step], session):
    """독립적인 스텝은 병렬 실행"""
    # 의존성 분석
    independent = [s for s in steps if not s.depends_on]
    dependent = [s for s in steps if s.depends_on]

    # 독립 스텝 병렬
    results = await asyncio.gather(*[
        self._execute_step(s, session) for s in independent
    ])

    # 의존 스텝 순차
    for step in dependent:
        result = await self._execute_step(step, session)
        results.append(result)

    return results
```

#### M5-2: 복합 요청 해석
```
Supervisor 프롬프트에 추가:
  - 복합 요청 감지: "분석하고 모델 생성해줘" → 2개 스텝
  - 의존성 명시: data_agent → modeling_agent (순차)
  - 독립 명시: data_agent + domain_expert (병렬 가능)
```

---

## 실행 일정 (권장)

```
Week 1:  S1 (시크릿 정리) + D1 (파일 정리) + M1 (인터페이스 표준화)
         ─── 기존 동작 변경 없이 기반 구축 ───

Week 2:  S2 (JWT 인증) + D3 (세션 캐시)
         ─── 보안 기본 확보 ───

Week 3:  D2 (비동기 솔버) + M2 (Supervisor 도입)
         ─── 핵심 아키텍처 전환 ───

Week 4:  M3 (모델 분리) + S3 (API 보안 강화)
         ─── 품질 + 보안 강화 ───

Week 5:  D4 (Alembic) + M4 (QA Reviewer)
         ─── 운영 안정성 ───

Week 6:  M5 (병렬 실행) + 통합 테스트
         ─── Multi-Agent 완성 ───
```

### 우선순위 매트릭스

```
                    긴급
                     │
         S1(시크릿)  │  D2(비동기솔버)
         S2(JWT)    │  M2(Supervisor)
                     │
    ─────────────────┼─────────────────
                     │
         D4(Alembic) │  M3(모델분리)
         D1(파일정리)│  M4(Reviewer)
                     │  M5(병렬실행)
        비긴급       │
                  낮은영향 ────────── 높은영향
```

---

## 테스트 전략

### 각 Phase별 필수 테스트

| Phase | 테스트 항목 | 방법 |
|-------|-----------|------|
| S1 | .env 없이 시작 시 에러 발생 확인 | pytest |
| S2 | JWT 발급/검증, 권한 거부, 토큰 만료 | pytest + httpx |
| D1 | 프로젝트 삭제 후 uploads/ 정리 확인 | pytest (임시 디렉토리) |
| D2 | Job 생성→폴링→완료 흐름 | pytest + Celery test mode |
| D3 | 세션 100개 초과 시 LRU 동작 | pytest |
| M1 | AgentTask/Context/Result 직렬화 | pytest |
| M2 | Supervisor fast-path + slow-path | pytest (mock LLM) |
| M3 | Agent별 다른 모델 사용 확인 | pytest (mock) |
| M4 | 검증 실패 → 재생성 루프 (최대 3회) | pytest (mock) |
| M5 | 병렬 실행 시 상태 충돌 없음 | pytest + asyncio |

### 회귀 테스트
```
기존 93개 테스트가 모든 Phase에서 통과해야 함
신규 테스트는 tests/test_{phase}.py로 분리
```

---

## 의존성 추가 요약

| 패키지 | Phase | 용도 |
|--------|-------|------|
| `python-jose[cryptography]` | S2 | JWT 토큰 |
| `passlib[bcrypt]` | S2 | 비밀번호 해싱 |
| `slowapi` | S3 | Rate limiting |
| `cryptography` | S3 | API Key 암호화 |
| `alembic` | D4 | DB 마이그레이션 |
| `redis` | D2 | Celery broker (이미 celery_app.py에 정의) |

---

## 아키텍처 목표 상태 (Week 6 이후)

```
사용자 요청
    ↓
┌──────────────────────────────────────────────────────┐
│  Auth Middleware (JWT 검증)                            │
└────────────┬─────────────────────────────────────────┘
             ↓
┌──────────────────────────────────────────────────────┐
│  Supervisor Agent                                     │
│  ├─ Fast-path: 키워드 분류 (비용 0)                    │
│  ├─ Slow-path: LLM 계획 수립 (Pro 모델)               │
│  └─ 결과 종합 + 상태 업데이트                           │
│                                                        │
│  도구: delegate(), ask_user(), update_plan()          │
└──┬──────────┬──────────┬──────────┬───────────────────┘
   │          │          │          │
┌──▼───┐ ┌───▼────┐ ┌──▼───┐ ┌───▼─────┐ ┌──────────┐
│ Data │ │Modeling│ │Solver│ │ Domain  │ │ Reviewer │
│Agent │ │ Agent  │ │Agent │ │ Expert  │ │  Agent   │
│flash │ │ pro    │ │(no   │ │ flash   │ │  pro     │
│      │ │        │ │ LLM) │ │         │ │(검증전용)│
└──┬───┘ └───┬────┘ └──┬───┘ └───┬─────┘ └──────────┘
   │         │         │         │
   └────┬────┴────┬────┴────┬────┘
        ↓         ↓         ↓
  ┌──────────────────────────────┐
  │  Shared State (SessionState)  │
  │  LRU Cache + DB Persistence   │
  └──────────────────────────────┘
        ↓
  ┌──────────────────────────────┐
  │  Celery Workers (비동기 솔버)  │
  │  Redis Broker                 │
  └──────────────────────────────┘
```
