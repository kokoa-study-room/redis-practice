# Redis 학습 프로젝트 (Redis Learning Project)

> **대상**: Redis를 처음부터 체계적으로 학습하려는 주니어 개발자
> **방식**: docker compose 한 번으로 환경 준비 + redis-cli·GUI·코드로 같은 기능을 세 번 보기
> **기준 시점**: 2026-04 (Redis Open Source 8.6.x 기반)
> **언어 정책**: 한국어 본문 + 영어 용어 병기

---

## 0. 한 줄 요약 (TL;DR)

```bash
# 1. 클론 후 환경 기동
docker compose -f docker/docker-compose.yml up -d

# 2. CLI 접속
docker compose -f docker/docker-compose.yml exec redis redis-cli

# 3. GUI 접속
open http://localhost:5540

# 4. 학습 시작
open docs/00-getting-started/README.md
```

---

## 1. 왜 이 프로젝트인가? (Why)

Redis 튜토리얼은 많지만 대부분 다음 중 하나에 속한다.

- "명령어만 줄줄 나열" → 외우긴 했는데 **왜 빠른지** 설명 못 함
- "이론만 빽빽" → 실제로 키를 넣어 보지 못함
- "운영팁만 잔뜩" → 기초 자료형부터 막막함

이 저장소는 **"명령어 → 내부 동작 → 함정 → 실전 패턴"** 을 한 챕터에서 모두 보고,
같은 동작을 **redis-cli / RedisInsight GUI / Python·Node 코드** 로 세 번 확인하도록 설계했다.

성공 기준은 학습 완료 후 다음 5개 질문에 답할 수 있는 것.

1. Redis는 왜 빠른가? (단일 스레드 이벤트 루프, 인메모리, 효율적 자료구조)
2. 외부 자료형(String/List/...) 과 내부 인코딩(listpack/quicklist/...) 은 어떤 관계인가?
3. 영속성·복제·고가용성을 어떻게 보장하는가?
4. 캐시·세션·랭킹·분산 락 같은 실전 패턴을 어떻게 구현하는가?
5. 성능을 어떻게 측정하고 개선하는가?

---

## 2. 기술 스택 (Tech Stack, 2026-04 검증)

| 구분 | 선택 | 출처 |
|---|---|---|
| Redis 엔진 | **Redis Open Source 8.6.2** | <https://github.com/redis/redis/releases/tag/8.6.2> (Latest 표시) |
| Docker 이미지 | `redis:8.6-alpine` (32.85 MB amd64) | <https://hub.docker.com/_/redis/tags?name=8.6-alpine> |
| GUI | **RedisInsight latest** (port 5540) | <https://hub.docker.com/r/redis/redisinsight> |
| Python 클라이언트 | **redis-py 7.4.0** (Python ≥3.10) | <https://pypi.org/project/redis/7.4.0/> |
| Node 클라이언트 (주) | **node-redis 5.12.0** (Redis 8.6 명시 지원) | <https://github.com/redis/node-redis/releases/tag/redis%405.12.0> |
| Node 클라이언트 (비교) | **ioredis 5.10.1** | <https://github.com/redis/ioredis/releases/tag/v5.10.1> |
| 비교용 OSS 포크 | Valkey (10-ecosystem 챕터에서 다룸) | <https://valkey.io/> |
| 벤치마크 | redis-benchmark (built-in), memtier_benchmark | docs/07-performance/ |

> **버전 결정 원칙**: 모든 사실/수치/명령은 위 출처 URL의 특정 단락에 근거한다. 추측 금지.

---

## 3. 학습 순서 (Learning Path)

> **권장**: 위에서 아래 순서대로. 각 챕터의 마지막 "직접 해보기" 과제를 풀고 다음 챕터로 넘어가면 누적 학습이 된다.

| 순서 | 챕터 | 핵심 질문 | 소요 |
|---|---|---|---|
| 1 | [00-getting-started](docs/00-getting-started/) | Redis가 뭐고, 왜 빠르고, 어떻게 띄우나? | 1시간 |
| 2 | [01-data-types](docs/01-data-types/) | 어떤 자료형이 있고 각자 무엇에 좋은가? | 4-6시간 |
| 3 | [02-internals](docs/02-internals/) | 같은 자료형이 내부적으로 어떻게 다르게 저장되는가? | 3-4시간 |
| 4 | [03-persistence](docs/03-persistence/) | RDB와 AOF 중 무엇을 써야 하는가? | 2시간 |
| 5 | [04-pubsub-streams](docs/04-pubsub-streams/) | 메시지·이벤트를 어떻게 다루는가? | 3시간 |
| 6 | [05-transactions-scripting](docs/05-transactions-scripting/) | 원자성을 어떻게 보장하는가? | 2시간 |
| 7 | [06-replication-ha](docs/06-replication-ha/) | 죽지 않는 Redis는 어떻게 만드는가? | 4시간 |
| 8 | [07-performance](docs/07-performance/) | 얼마나 빠른지 어떻게 측정하는가? | 2시간 |
| 9 | [08-clients](docs/08-clients/) | Python/Node에서 어떻게 효율적으로 쓰는가? | 2시간 |
| 10 | [09-patterns](docs/09-patterns/) | 캐시·랭킹·분산 락을 어떻게 구현하는가? | 4-5시간 |
| 11 | [10-ecosystem](docs/10-ecosystem/) | Valkey·Redis Stack·모듈은 무엇인가? | 1시간 |
| 12 | [11-monitoring](docs/11-monitoring/) (선택) | Prometheus + Grafana 로 어떻게 들여다보는가? | 1-2시간 |
| 13 | [12-security](docs/12-security/) ⚠️ | ACL·TLS·위험 명령 제한 — production 필수 | 2-3시간 |
| 14 | [13-ai-patterns](docs/13-ai-patterns/) 🤖 | RAG·Semantic Cache·Agent Memory | 3-4시간 |

> **단축 코스 (총 8시간)**: 1 → 2(String/List/Hash/Sorted Set만) → 4 → 9(캐시) → 10
> **딥다이브 코스 (총 35시간+)**: 위 표 그대로 + 모든 "직접 해보기" 과제 + 11(모니터링) + 12(보안) + 13(AI)
> **Production 코스 (총 18시간)**: 1 → 2(핵심) → 4 → 7(replication/HA) → 8(performance) → **12(보안 필수)** → 11(모니터링)
> **AI 엔지니어 코스 (총 12시간)**: 1 → 2(Vector Set/Stream/Hash) → 9(cache-aside) → **13(AI patterns)**

---

## 4. 디렉토리 구조 (Layout)

```
011-redis/
├── README.md                          # 이 문서
├── .gitignore
├── docker/
│   ├── docker-compose.yml             # 기본 (redis + redisinsight)
│   ├── docker-compose.cluster.yml     # 클러스터 6노드 (Phase 8에서 사용)
│   ├── docker-compose.sentinel.yml    # Sentinel (Phase 8에서 사용)
│   ├── docker-compose.monitoring.yml  # Prometheus + Grafana + redis_exporter
│   ├── prometheus/prometheus.yml      # scrape 설정
│   ├── grafana/
│   │   ├── provisioning/              # datasource + dashboard 자동 등록
│   │   └── dashboards/redis.json      # 미니 대시보드
│   └── redis/
│       ├── conf/
│       │   ├── redis.conf             # 학습 친화 주석 포함 설정
│       │   └── redis-aof.conf         # AOF 실습 전용 변형
│       └── data/                      # 호스트 바인드 마운트 (RDB/AOF 저장)
├── docs/
│   ├── 00-getting-started/            # 시작하기 (4 + README)
│   ├── 01-data-types/                 # 외부 자료형 (10 + README)
│   ├── 02-internals/                  # 내부 인코딩 (7 + README)
│   ├── 03-persistence/                # RDB/AOF (3 + README)
│   ├── 04-pubsub-streams/             # 메시징 (3 + README)
│   ├── 05-transactions-scripting/     # 원자성 (3 + README)
│   ├── 06-replication-ha/             # 복제/HA (3 + README)
│   ├── 07-performance/                # 성능 (4 + README)
│   ├── 08-clients/                    # 클라이언트 (3 + README)
│   ├── 09-patterns/                   # 실전 패턴 (6 + README)
│   ├── 10-ecosystem/                  # 생태계 (2 + README)
│   ├── 11-monitoring/                 # 모니터링 (3 + README, 선택)
│   ├── 12-security/                   # 보안 — ACL/TLS/위험명령 (4 + README, ⚠️ production 필수)
│   └── 13-ai-patterns/                # AI 패턴 — RAG/Semantic Cache/Agent Memory (3 + README)
├── examples/
│   ├── python/                        # redis-py 7.4.0 + 챕터별 실행 코드
│   │   ├── ch00_getting_started/      # ping_and_set
│   │   ├── ch01_data_types/           # string / list / hash / zset / stream
│   │   ├── ch04_pubsub_streams/       # pubsub
│   │   ├── ch05_transactions_scripting/ # lua_token_bucket
│   │   ├── ch07_performance/          # pipeline_demo
│   │   └── ch09_patterns/             # cache_aside / distributed_lock
│   └── nodejs/                        # node-redis 5.12.0 + 챕터별 실행 코드 (Python과 동일 구조)
├── scripts/
    ├── seed-data.sh                   # 실습용 demo:* 데이터 적재
    ├── reset.sh                       # demo:* 또는 전체 초기화
    └── benchmark.sh                   # redis-benchmark 일괄 실행
```

---

## 5. 환경 준비 (Setup)

### 5.1 사전 요구

| 도구 | 최소 버전 | 확인 명령 |
|---|---|---|
| Docker Desktop / Engine | 26.0+ (Compose v2 포함) | `docker --version && docker compose version` |
| (선택) Python | 3.10+ | `python --version` |
| (선택) Node.js | 20.x LTS+ | `node --version` |
| (선택) redis-cli | 8.x | `redis-cli --version` |

### 5.2 기본 환경 기동

```bash
# 프로젝트 루트에서
docker compose -f docker/docker-compose.yml up -d

# 헬스체크 통과 대기 (보통 5초)
docker compose -f docker/docker-compose.yml ps

# 연결 확인
docker compose -f docker/docker-compose.yml exec redis redis-cli ping
# 기대 결과: PONG
```

### 5.3 RedisInsight (GUI) 접속

브라우저에서 <http://localhost:5540> 열기.
docker-compose에 `RI_REDIS_HOST=redis`, `RI_REDIS_PORT=6379` 환경변수가 주어져 있어
첫 화면에서 자동으로 "redis-learning (compose)" 데이터베이스가 등록돼 있어야 한다.
(자동 등록이 안 되면 Add Database → Host: `redis`, Port: `6379`)

> 출처: <https://hub.docker.com/r/redis/redisinsight> "Preconfigure database connections" 섹션

### 5.4 실습 데이터 적재 (선택)

```bash
./scripts/seed-data.sh
# 모든 키는 demo:* prefix
```

### 5.5 Python / Node 환경

각각 [examples/python/README.md](examples/python/README.md) 와 [examples/nodejs/README.md](examples/nodejs/README.md) 참고.

### 5.6 모니터링 스택 (선택, 11장에서 사용)

```bash
docker compose -f docker/docker-compose.monitoring.yml up -d

# Grafana 접속 (admin/admin)
open http://localhost:3000

# Prometheus
open http://localhost:9090
```

기본 환경과 별도 인스턴스 (`redis-mon:6390`)를 사용하므로 충돌하지 않는다.
자세한 내용은 [docs/11-monitoring/](docs/11-monitoring/) 참고.

---

## 6. 학습 자료 인용 정책 (Citation Policy)

본 프로젝트는 **모든 사실 진술에 출처를 명시**한다. 각 문서의 마지막 "참고 자료" 섹션에서:

```markdown
- **[공식 문서] OBJECT ENCODING — Redis Docs**
  - URL: https://redis.io/docs/latest/commands/object-encoding
  - 참고 부분: "Sets can be encoded as: hashtable, intset, listpack" — 본 문서의 "Set 인코딩 표"는 이 단락을 근거로 작성됨
```

위 형식으로 출처와 "어떤 문장을 참고했는지" 를 같이 적는다.
공식 문서(redis.io / github.com/redis/redis / valkey.io) 우선이며, 블로그·서드파티는 보조 출처로만 사용한다.

---

## 7. 자주 만나는 문제 (Troubleshooting)

| 증상 | 원인 후보 | 해결 |
|---|---|---|
| `Cannot connect to the Docker daemon` | Docker가 안 떠있음 | Docker Desktop 실행 확인 |
| `port is already allocated` (6379) | 호스트의 다른 Redis가 6379 점유 | `lsof -i:6379` 로 확인 후 종료, 또는 docker-compose의 호스트 포트 변경 |
| RedisInsight에서 자동 연결이 안 됨 | RI_REDIS_HOST 환경변수 미반영 | `docker compose down -v && docker compose up -d` 로 볼륨까지 초기화 |
| `redis-cli: command not found` (호스트) | redis-cli 미설치 | `docker compose exec redis redis-cli` 로 컨테이너 내부에서 실행 |
| `(error) NOAUTH Authentication required` | requirepass가 켜져 있는데 인증 안 함 | docs/05-transactions-scripting 의 ACL 챕터 참고 |
| Apple Silicon에서 일부 이미지가 안 뜸 | platform 미지정 | docker-compose에 `platform: linux/amd64` 추가 |

---

## 8. 기여 / 학습 메모 추가 가이드

본 저장소는 학습 노트가 함께 자라는 것을 환영한다.

- 새 챕터 추가 시 [.sisyphus/plans/redis-learning-roadmap.md](.sisyphus/plans/redis-learning-roadmap.md) 의 표준 8섹션 구조를 따른다.
- 출처 없는 사실 단언은 PR 거절 사유다.
- redis-cli 출력 예시는 가능하면 실제로 실행해서 가져온다 (가짜 출력 금지).

---

## 9. 라이선스

본 학습 자료는 MIT 라이선스로 배포된다. (단, 공식 문서·OSS 인용 부분은 각 출처의 라이선스를 따른다.)

---

## 10. 관련 링크 (External References)

- [Redis 공식 문서](https://redis.io/docs/) — 1차 출처
- [Redis GitHub (8.6 branch)](https://github.com/redis/redis/tree/8.6) — 소스 코드
- [Redis 블로그 8.6 발표](https://redis.io/blog/announcing-redis-86-performance-improvements-streams/) — 8.6 신기능 개관
- [Valkey](https://valkey.io/) — Redis OSS 포크
- [RedisInsight GitHub](https://github.com/RedisInsight/RedisInsight) — GUI 소스/이슈
- [redis-py Documentation](https://redis.readthedocs.io/en/stable/) — Python 클라이언트
- [node-redis GitHub](https://github.com/redis/node-redis) — Node.js 공식 클라이언트
