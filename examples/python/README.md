# Python 예제 (redis-py)

> **클라이언트**: [redis-py 7.4.0](https://pypi.org/project/redis/7.4.0/) (2026-03-24)
> **Python 요구**: 3.10+
> **참고 문서**: <https://redis.readthedocs.io/en/stable/>

본 디렉토리는 [docs/](../../docs) 하위 챕터의 redis-cli 예제를 Python으로 재현한 것이다.
챕터 번호와 파일명을 매칭한다 (예: `docs/01-data-types/01-string.md` → `ch01_data_types/string_basics.py`).

---

## 1. 환경 준비

### 옵션 A: 표준 venv (가장 단순)

```bash
cd examples/python
python -m venv .venv
source .venv/bin/activate         # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

### 옵션 B: uv (최근 권장, 빠름)

```bash
cd examples/python
uv venv
source .venv/bin/activate
uv pip install -r requirements.txt
```

### 옵션 C: editable install (모듈로 import 하고 싶을 때)

```bash
cd examples/python
pip install -e .
```

---

## 2. Redis 연결 확인

먼저 [docker/](../../docker)에서 Redis가 떠 있어야 한다.

```bash
# 프로젝트 루트에서
docker compose -f docker/docker-compose.yml up -d

# 연결 테스트 (호스트에서)
python -c "import redis; print(redis.Redis(host='127.0.0.1', port=6379).ping())"
# 기대 결과: True
```

---

## 3. 디렉토리 구조 (실제 작성된 파일)

```
examples/python/
├── pyproject.toml
├── requirements.txt
├── README.md (본 문서)
├── .env.example                  # 환경변수 템플릿
├── _common.py                    # get_client() / section() 공통 헬퍼
├── ch00_getting_started/
│   └── 01_ping_and_set.py
├── ch01_data_types/
│   ├── 01_string_basics.py
│   ├── 02_list_queue.py
│   ├── 03_hash_with_field_ttl.py
│   ├── 05_sorted_set_leaderboard.py
│   └── 06_stream_consumer_group.py
├── ch04_pubsub_streams/
│   └── 01_pubsub.py
├── ch05_transactions_scripting/
│   └── 01_lua_token_bucket.py
├── ch07_performance/
│   └── 01_pipeline_demo.py
└── ch09_patterns/
    ├── 01_cache_aside.py
    └── 03_distributed_lock.py
```

> 핵심 자료형 5개 (String/List/Hash/ZSet/Stream) + 주요 패턴(캐시·분산락) + Pub/Sub + Lua Rate Limiter + Pipeline 측정 = 10개 단독 실행 파일.
> 다른 자료형(Set / Bitmap / HyperLogLog / Geospatial / Vector Set)은 `docs/01-data-types/` 본문의 코드 스니펫을 그대로 복사하면 동일하게 동작한다.

각 파일은:
1. 첫 줄 docstring에 매칭 문서 경로 명시 (`# Reference: docs/01-data-types/01-string.md`)
2. `python ch01_data_types/01_string_basics.py` 식으로 단독 실행 가능
3. `_common.py` 의 `get_client()` 사용 (`.env` 자동 로딩)
4. 실행 후 자동으로 자기가 만든 키를 정리

---

## 4. 실행 예

```bash
# 환경 활성화
source .venv/bin/activate

# Hello World
python ch00_getting_started/01_ping_and_set.py

# String 자료형 + encoding 전환
python ch01_data_types/01_string_basics.py

# Stream + Consumer Group (두 컨슈머가 분배 처리)
python ch01_data_types/06_stream_consumer_group.py

# Pipeline 효과 측정 (1000개 SET, 세 가지 방법 비교)
python ch07_performance/01_pipeline_demo.py

# Cache-aside + negative caching
python ch09_patterns/01_cache_aside.py

# 분산 락 — 두 워커 동시 시도
python ch09_patterns/03_distributed_lock.py
```

---

## 5. 비동기 예제 (asyncio)

```python
import asyncio
import redis.asyncio as redis

async def main():
    r = redis.Redis(host="127.0.0.1", port=6379, decode_responses=True)
    await r.set("async_greeting", "비동기 Redis")
    print(await r.get("async_greeting"))
    await r.aclose()

asyncio.run(main())
```

> redis-py 5.0+ 부터 `redis.asyncio` 가 표준이며 `aclose()` 를 호출해야 자원이 정리된다.
> 참고: <https://redis.readthedocs.io/en/stable/examples/asyncio_examples.html>

---

## 6. RESP3 프로토콜

Redis 7+ / redis-py 5.0+ 에서 RESP3가 정식 지원된다.
일부 명령(`CLIENT INFO`, `HELLO 3`, push notifications 등)은 RESP3에서만 정확한 구조를 받는다.

```python
import redis
r = redis.Redis(host="127.0.0.1", port=6379, db=0, protocol=3)
```

> 참고: <https://github.com/redis/redis-specifications/blob/master/protocol/RESP3.md>

---

## 7. 코드 스타일

- 라인 길이 100자
- f-string 사용
- async 예제는 `redis.asyncio` 모듈만 사용 (deprecated `aredis` 금지)
- 모든 connection은 `with` 또는 명시적 `close()`/`aclose()` 로 정리

---

## 8. 참고 자료 (References)

- **[공식 문서] redis-py Documentation** — <https://redis.readthedocs.io/en/stable/>
  - 참고 부분: "Basic Example" 단락 — 본 README의 빠른 예시는 이 코드를 한국어 출력으로 살짝 변형
- **[GitHub] redis/redis-py releases** — <https://github.com/redis/redis-py/releases>
  - 참고 부분: 7.4.0 릴리즈 노트(2026-03-24) — 의존성 버전 결정 근거
- **[공식 명세] RESP3** — <https://github.com/redis/redis-specifications/blob/master/protocol/RESP3.md>
  - 참고 부분: "RESP3 overview" — protocol=3 옵션 의미 설명
