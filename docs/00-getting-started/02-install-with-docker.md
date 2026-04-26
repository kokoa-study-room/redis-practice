# 02. Docker로 Redis + RedisInsight 띄우기

> **학습 목표**: docker compose 한 번으로 Redis 8.6과 RedisInsight를 띄우고, 양쪽이 통신하는지 확인할 수 있다.
> **사전 지식**: 도커 기본 (이미지/컨테이너 차이), 셸 사용
> **예상 소요**: 10분

---

## 1. 개념 (Concept)

이 프로젝트는 두 컨테이너를 함께 띄운다.

```
┌────────────────────────────┐         ┌──────────────────────────────┐
│  redis-learning            │         │  redisinsight-learning       │
│  image: redis:8.6-alpine   │◀──6379──▶  image: redis/redisinsight  │
│  port: 6379                │         │  port: 5540 → 호스트 5540    │
│  data: ./redis/data        │         │  data: redisinsight-data 볼륨│
└────────────────────────────┘         └──────────────────────────────┘
            ▲                                       ▲
            │                                       │
       redis-cli                               웹 브라우저
       (호스트 또는 컨테이너 내부)              http://localhost:5540
```

두 컨테이너는 같은 사용자 정의 브리지 네트워크(`redis-net`)에 속하므로 **호스트명으로 서로 통신**한다 (RedisInsight 입장에서 Redis 호스트는 `redis`).

---

## 2. 기동 (redis-cli)

프로젝트 루트에서:

```bash
docker compose -f docker/docker-compose.yml up -d
```

기대 출력 (대략):

```
[+] Running 4/4
 ✔ Network redis-learning_redis-net          Created
 ✔ Volume "redis-learning_redisinsight-data" Created
 ✔ Container redis-learning                  Healthy
 ✔ Container redisinsight-learning           Started
```

상태 확인:

```bash
docker compose -f docker/docker-compose.yml ps
```

```
NAME                       IMAGE                       STATUS
redis-learning             redis:8.6-alpine            Up (healthy)
redisinsight-learning      redis/redisinsight:latest   Up
```

> `(healthy)` 가 떠야 한다. 헬스체크 정의는 docker-compose.yml의 `healthcheck` 블록 참고 (`redis-cli ping` → `PONG`).

---

## 3. 연결 확인

### 3.1 컨테이너 내부 redis-cli

```bash
docker compose -f docker/docker-compose.yml exec redis redis-cli
127.0.0.1:6379> PING
PONG
127.0.0.1:6379> SET hello "안녕"
OK
127.0.0.1:6379> GET hello
"\xec\x95\x88\xeb\x85\x95"        # 한글이 바이트로 보임
127.0.0.1:6379> exit
```

> 한글이 깨진 것처럼 보이는 이유는 redis-cli의 raw 출력 모드 때문이다. 예쁘게 보려면 `redis-cli --no-raw` 또는 클라이언트 라이브러리에서 `decode_responses=True` 옵션 사용.

### 3.2 호스트의 redis-cli (선택)

호스트에 redis-cli가 설치돼 있다면:

```bash
redis-cli -h 127.0.0.1 -p 6379 PING
# PONG
```

설치가 안 돼 있고 macOS라면 `brew install redis` (서버는 안 띄움, CLI 도구만 사용).

### 3.3 RedisInsight (브라우저)

```bash
open http://localhost:5540        # macOS
xdg-open http://localhost:5540    # Linux
start http://localhost:5540       # Windows
```

처음 접속하면 EULA 동의 화면 → 그 다음 데이터베이스 목록.
docker-compose에 `RI_REDIS_HOST=redis` 환경변수가 있으므로 **자동으로 "redis-learning (compose)" 데이터베이스가 등록**돼 있어야 한다.

> 자동 등록이 안 보이면: "Add Database" → Host: `redis`, Port: `6379`, Database alias: 임의.
> 출처: <https://hub.docker.com/r/redis/redisinsight> "Preconfigure database connections using environment variables"

---

## 4. 종료

```bash
# 컨테이너만 종료 (데이터/볼륨 유지)
docker compose -f docker/docker-compose.yml down

# 볼륨까지 삭제 (학습 환경 완전 초기화)
docker compose -f docker/docker-compose.yml down -v

# 컨테이너 + 호스트 데이터 디렉토리 정리
docker compose -f docker/docker-compose.yml down -v
rm -rf docker/redis/data/* docker/redis/data/appendonlydir
```

---

## 5. 흔한 함정 (Pitfalls)

| 증상 | 원인 | 해결 |
|---|---|---|
| `port is already allocated` | 호스트의 6379가 이미 사용 중 | `lsof -i:6379` (macOS/Linux) 로 확인 후 종료, 또는 docker-compose의 호스트 포트 변경: `"127.0.0.1:6380:6379"` |
| 헬스체크가 unhealthy | conf 파일 마운트 실패 | `docker compose logs redis` 확인 |
| RedisInsight 자동 등록 안 됨 | 이전 볼륨 잔존 | `docker compose down -v` 후 재기동 |
| Apple Silicon에서 이미지 풀 실패 | platform 미지정 | docker-compose에 `platform: linux/amd64` 임시 추가 |

---

## 6. RedisInsight에서 확인하기

`docker compose exec redis redis-cli SET foo bar` 실행 후 RedisInsight에서:

1. 좌측 사이드바 → **Browser** 클릭
2. 키 검색창에 `foo` 입력 → `string` 자료형 키가 보임
3. 클릭 → 값 `bar` 확인

---

## 7. 직접 해보기

1. `docker compose up -d` 후 `docker compose logs redis | head -50` 으로 시작 로고 확인.
2. `redis-cli INFO server` 로 `redis_version` 이 `8.6.x` 인지 확인.
3. RedisInsight에서 `SET counter 0` 후 `INCR counter` 를 5번 실행하고, Browser 탭에서 값이 `5`로 보이는지 확인.

---

## 8. 참고 자료 (References)

- **[공식 문서] Get started with Redis using Docker — redis.io**
  - URL: <https://redis.io/docs/latest/operate/oss_and_stack/install/install-stack/docker/>
  - 참고 부분: 공식 docker 사용 예 — 본 문서의 명령 형식 표준 근거

- **[Docker Hub] redis Official Image**
  - URL: <https://hub.docker.com/_/redis>
  - 참고 부분: 태그 목록(`8.6-alpine` 등) — 이미지 선택 근거

- **[Docker Hub] redis/redisinsight**
  - URL: <https://hub.docker.com/r/redis/redisinsight>
  - 참고 부분: "Run Redis Insight on Docker" 섹션의 `5540` 포트 — 본 문서 §3.3 포트 정보 근거
