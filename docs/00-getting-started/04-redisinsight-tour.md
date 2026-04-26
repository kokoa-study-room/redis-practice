# 04. RedisInsight 둘러보기

> **학습 목표**: RedisInsight 주요 화면 5개(Browser/Workbench/Profiler/Slowlog/Analytics)의 용도를 알고, 같은 작업을 redis-cli vs GUI로 양쪽에서 할 수 있다.
> **사전 지식**: 02 챕터로 RedisInsight 자동 등록 확인
> **예상 소요**: 15분

---

## 1. 왜 GUI가 필요한가

CLI만으로 학습하면 다음이 어렵다.

- **자료형의 구조 시각화**: ZSET이 score-member 쌍으로 정렬돼 있다는 사실을 표로 보면 한 번에 이해된다.
- **Stream / Vector Set의 트리 구조**: 텍스트로 보면 머리가 아프다.
- **메모리/지연 분석**: 명령 한 개 결과를 그래프로.

CLI에 익숙해진 후에 GUI를 쓰면 "같은 일을 둘 다로 할 수 있다"는 안정감이 생긴다.

---

## 2. 첫 화면 — Database list

http://localhost:5540 접속 → 자동 등록된 `redis-learning (compose)` 클릭 → 좌측 사이드바에 5개 메뉴.

| 메뉴 | 한국어 | 핵심 용도 |
|---|---|---|
| Browser | 키 브라우저 | 키 목록 / 값 보기 / 편집 |
| Workbench | 워크벤치 | 명령 실행 + 결과 시각화 |
| Profiler | 프로파일러 | 실시간 명령 모니터링 (`MONITOR` 의 GUI 버전) |
| Slow Log | 슬로우 로그 | `SLOWLOG GET` 의 GUI 버전 |
| Analytics | 분석 | 메모리 / 지연 / 데이터베이스 통계 |

---

## 3. Browser — 키 단위로 들여다보기

### 3.1 키 검색
- 좌측 상단 검색창에 패턴 입력 (`demo:*`, `user:*`)
- 자료형 필터 가능 (String / List / Hash / ...)
- 키 클릭 → 우측 패널에 값 / TTL / 메모리 사용량

### 3.2 자료형별 값 편집
| 자료형 | 편집 UI |
|---|---|
| String | 텍스트박스 (JSON / TEXT / BINARY 모드 전환) |
| List | 행 추가/삭제 (Push to head/tail) |
| Hash | field-value 표 |
| Set | 멤버 목록 |
| Sorted Set | score-member 표, 정렬 |
| Stream | 엔트리 트리, Consumer Group 탭 |

### 3.3 실습
1. `SET demo:greeting "안녕"` (cli)
2. RedisInsight Browser에서 `demo:*` 검색 → `demo:greeting` 클릭 → 값이 보이는지 확인
3. GUI에서 값을 `"Hello"` 로 수정 → 저장
4. cli로 `GET demo:greeting` → `"Hello"` 가 나오는지 확인

---

## 4. Workbench — 명령 + 시각화

`SET`, `LRANGE`, `ZRANGEBYSCORE` 같은 명령을 한 줄씩 입력 + 실행.
좌측에 명령 도움말, 우측에 결과 (자료형에 따라 표/트리/JSON 자동 선택).

### 실습
```
ZADD demo:lb 1500 alice 2300 bob 980 carol 1875 dave 2750 eve
ZRANGE demo:lb 0 -1 WITHSCORES
```

→ 결과가 점수 순 정렬된 표로 보인다. (cli는 그냥 줄줄이 텍스트.)

`HOTKEYS START` (Redis 8.6+) 같은 신규 명령도 지원되는지 확인 가능.

---

## 5. Profiler — 명령 흐름 보기

`MONITOR` 명령의 GUI. **"누가 어떤 명령을 보내고 있는가"** 가 실시간으로 흐른다.

### 실습
1. Profiler 탭 → "Start Profiler"
2. 별도 cli에서 `INCR demo:hits` 를 10번 실행
3. Profiler 화면에 `INCR demo:hits` 가 줄줄이 찍히는지 확인
4. "Stop" → 잊지 말 것 (열어두면 부담)

> 운영 환경에서는 Profiler를 짧게만 사용. Redis 인스턴스 throughput에 영향.

---

## 6. Slow Log — 느린 명령 추적

`redis.conf` 의 `slowlog-log-slower-than 1000` (μs) 기준으로 임계 초과 명령이 기록된다 (학습용 redis.conf 기본값).

### 실습
1. cli: `DEBUG SLEEP 0.5` (0.5초 멈춤)
2. RedisInsight Slow Log → 자동으로 새 항목이 보임
3. 클릭 → 명령 / 클라이언트 / duration 확인

> `DEBUG SLEEP` 은 의도적으로 서버를 멈추므로 학습 환경에서만 사용.

---

## 7. Analytics — 한눈에 보기

- **Database Analysis**: 자료형 분포 / 메모리 점유율 / TTL 분포
- **Cluster overview**: 클러스터 모드일 때 슬롯 분포 (Phase 8에서 사용)

---

## 8. 흔한 함정

| 증상 | 원인 | 해결 |
|---|---|---|
| Browser에 키가 안 보임 | 검색 패턴 오타 / 키가 다른 DB에 있음 | DB 0~15 전환 메뉴 확인 |
| Profiler를 켜놓고 잊음 | 성능 저하 | 명시적 Stop |
| Slow Log가 비어 있음 | 임계치보다 빠른 명령만 들어옴 | `slowlog-log-slower-than` 낮추거나 `DEBUG SLEEP` 으로 트리거 |
| Hash field에 한글이 깨짐 | Encoding 자동 감지 실패 | "Format" 드롭다운 → UTF-8 |

---

## 9. cli ↔ GUI 매핑 표

| cli 명령 | GUI 위치 |
|---|---|
| `KEYS pat`, `SCAN` | Browser 검색 |
| `GET/SET/HGETALL/...` | Browser 값 패널 |
| `MONITOR` | Profiler |
| `SLOWLOG GET 10` | Slow Log |
| `INFO memory` | Analytics → Memory |
| `CLUSTER NODES` | Cluster overview (cluster 연결 시) |
| `OBJECT ENCODING <key>` | Browser 키 상세 (Encoding 필드) |

---

## 10. 직접 해보기

1. seed-data.sh 실행 후 Browser에서 `demo:leaderboard:weekly` (ZSET) 를 표 형태로 본다.
2. 같은 데이터를 Workbench에서 `ZRANGE` / `ZRANGEBYSCORE` 두 명령으로 다르게 가져와 본다.
3. Profiler를 켜고 `python -c "import redis; r=redis.Redis(); [r.incr('demo:hits') for _ in range(20)]"` 실행.
4. Analytics → Database Analysis 실행. 자료형 분포 차트가 뜨는지 확인.

---

## 11. 참고 자료 (References)

- **[공식 문서] Redis Insight overview — redis.io**
  - URL: <https://redis.io/docs/latest/operate/redisinsight/>
  - 참고 부분: 5개 주요 기능(Browser/Workbench/Profiler/...) 설명 — 본 문서 §2의 메뉴 매핑 근거

- **[GitHub] RedisInsight/RedisInsight**
  - URL: <https://github.com/RedisInsight/RedisInsight>
  - 참고 부분: README 첫 단락의 기능 요약 — 본 문서 §1의 GUI 필요성 근거

- **[Docker Hub] redis/redisinsight**
  - URL: <https://hub.docker.com/r/redis/redisinsight>
  - 참고 부분: 환경변수 표(`RI_REDIS_HOST` 등) — Browser 자동 등록 동작 근거
