# 03. redis-cli 기초

> **학습 목표**: redis-cli로 연결, 기본 명령 실행, `HELP` 활용, 자주 쓰는 옵션을 사용할 수 있다.
> **사전 지식**: 02-install-with-docker.md 까지 마침
> **예상 소요**: 20분

---

## 1. 연결 (Connect)

| 환경 | 명령 |
|---|---|
| 컨테이너 내부 | `docker compose exec redis redis-cli` |
| 호스트 → 도커 | `redis-cli -h 127.0.0.1 -p 6379` |
| 인증 있는 경우 | `redis-cli -a <password>` 또는 `--user <name> --pass <password>` (ACL) |
| RESP3 사용 | `redis-cli -3` (Redis 7+) |
| 다른 DB 선택 | `redis-cli -n 1` (DB 1번) |

연결 후 프롬프트:

```
127.0.0.1:6379>
```

종료: `exit` 또는 Ctrl-D.

---

## 2. 가장 먼저 외울 명령

```
PING                       # → PONG (생존 확인)
SET <key> <value>          # 문자열 저장
GET <key>                  # 조회
DEL <key> [<key> ...]      # 삭제 (지운 개수 반환)
EXISTS <key> [<key> ...]   # 존재 개수 반환
TYPE <key>                 # 자료형 (string/list/hash/...)
OBJECT ENCODING <key>      # 내부 인코딩 (embstr/listpack/...)
TTL <key>                  # 남은 만료 시간 (초). -1: 만료 없음, -2: 키 없음
EXPIRE <key> <seconds>     # 만료 설정
KEYS *                     # 모든 키 (학습용으로만; 운영 절대 금지)
SCAN 0 [MATCH pat] [COUNT n]   # cursor 기반 안전 순회
DBSIZE                     # 키 개수
FLUSHDB                    # 현재 DB 비우기 (위험)
INFO [section]             # 서버 통계
HELP <command>             # 명령 도움말
```

---

## 3. 실습 흐름

```
127.0.0.1:6379> SET city Seoul
OK
127.0.0.1:6379> GET city
"Seoul"
127.0.0.1:6379> TYPE city
string
127.0.0.1:6379> OBJECT ENCODING city
"embstr"
127.0.0.1:6379> EXPIRE city 60
(integer) 1
127.0.0.1:6379> TTL city
(integer) 58
127.0.0.1:6379> APPEND city "-Korea"
(integer) 11
127.0.0.1:6379> GET city
"Seoul-Korea"
127.0.0.1:6379> OBJECT ENCODING city
"embstr"            # 짧은 문자열은 여전히 embstr
127.0.0.1:6379> DEL city
(integer) 1
127.0.0.1:6379> EXISTS city
(integer) 0
```

> `OBJECT ENCODING` 은 02-internals 챕터에서 핵심적으로 다룬다. 지금은 "내부 표현이 따로 있다"는 사실만 받아들이자.

---

## 4. 자주 쓰는 redis-cli 옵션

| 옵션 | 의미 | 예 |
|---|---|---|
| `--no-raw` | 바이트가 아니라 사람 읽기 좋은 형식으로 출력 | 한글 깨짐 방지 |
| `--csv` | 결과를 CSV로 (벤치마크/테스트 자동화) | `redis-cli --csv ZRANGE k 0 -1 WITHSCORES` |
| `--scan --pattern PAT` | SCAN 루프를 자동으로 돌려 키 나열 | `redis-cli --scan --pattern 'demo:*'` |
| `--latency` | 지연 시간 모니터링 | `redis-cli --latency` |
| `--latency-history` | 1초 윈도 단위로 latency 분포 | `redis-cli --latency-history` |
| `--bigkeys` | 자료형별 큰 키 샘플링 | `redis-cli --bigkeys` |
| `--memkeys` | 메모리 사용 큰 키 샘플링 | `redis-cli --memkeys` |
| `--hotkeys` | 핫키 샘플링 (최근 LFU 기반) | `redis-cli --hotkeys` (Redis 4+, 8.6에서 동명의 `HOTKEYS` 명령 추가) |
| `--stat` | 1초마다 키 수/메모리 통계 | `redis-cli --stat` |
| `MONITOR` | 들어오는 모든 명령 실시간 출력 (디버깅용) | `redis-cli MONITOR` |

> `MONITOR`는 운영 환경에서 켜면 성능에 영향이 크다. 학습 환경에서만 짧게 사용.

---

## 5. HELP의 두 단계

### 5.1 `HELP` 만 입력 → 명령 카테고리

```
127.0.0.1:6379> HELP
redis-cli 8.6.x
To get help about Redis commands type:
      "help @<group>"  to get a list of commands in <group>
      "help <command>" for help on <command>
      ...
```

### 5.2 `HELP @string`, `HELP SET` 등

```
127.0.0.1:6379> HELP SET

  SET key value [EX seconds | PX milliseconds | EXAT unix-time | PXAT unix-ms |
                 KEEPTTL] [NX | XX] [IDLE seconds] [GET]
  summary: Set the string value of a key
  since: 1.0.0
  group: string
```

> Redis 8.x 기준의 모든 명령은 <https://redis.io/commands> 에서도 같은 정보를 볼 수 있지만, 오프라인에서 즉시 확인하는 데는 `HELP` 가 빠르다.

---

## 6. SCAN을 KEYS 대신 써야 하는 이유

```
# WRONG (운영 금지)
127.0.0.1:6379> KEYS user:*
1) "user:1"
2) "user:2"
...
```

`KEYS *` 는 키가 1억 개면 1억 개를 한 번에 본다. 단일 스레드 Redis는 그동안 다른 명령을 못 처리한다.

```
# CORRECT
127.0.0.1:6379> SCAN 0 MATCH user:* COUNT 100
1) "12345"          # 다음 cursor (0이 되면 끝)
2) 1) "user:1"
   2) "user:2"
   ...
127.0.0.1:6379> SCAN 12345 MATCH user:* COUNT 100
...
```

> 출처: <https://redis.io/docs/latest/commands/scan/>
> 참고 부분: "SCAN, SSCAN, HSCAN and ZSCAN are cursor based iterators." 단락

cli 자동화:

```bash
redis-cli --scan --pattern 'user:*' | head
```

---

## 7. 흔한 함정 (Pitfalls)

| 함정 | 설명 |
|---|---|
| 한글이 `\xec\x95\x88` 으로 보임 | raw 출력 모드. `--no-raw` 또는 클라이언트에서 `decode_responses=True` |
| `(error) MOVED 12182 ...` | 클러스터 모드인데 단일 노드에 명령. `redis-cli -c` 사용 |
| `(error) NOAUTH ...` | requirepass/ACL 적용. `-a <pw>` 또는 `--user/--pass` |
| `EXPIRE` 가 `0` 반환 | 키가 없거나 이미 지움 |
| `OBJECT ENCODING` 이 `(nil)` | 키가 없음 |

---

## 8. RedisInsight에서 확인하기

RedisInsight의 **Workbench** 탭은 redis-cli와 같은 명령을 실행하지만 **결과를 시각화**한다.
- 자동 완성 / 명령 도움말 인라인
- ZSET 결과를 표 형태로
- JSON / Stream 결과를 트리 형태로

같은 명령을 cli와 Workbench 양쪽에서 실행해 보고 차이를 느껴보자.

---

## 9. 직접 해보기

1. `INFO server` 출력에서 `tcp_port`, `process_id`, `uptime_in_seconds` 위치 찾기.
2. `CLIENT LIST` 출력에서 자기 자신 연결을 식별 (addr 컬럼).
3. `--latency` 를 5초간 실행해서 평균 latency 확인 (Mac/Linux 기준 ms 단위).
4. `--bigkeys` 실행. 어떤 자료형이 가장 큰 키였는가? (실습 데이터를 seed-data.sh로 적재 후)

---

## 10. 참고 자료 (References)

- **[공식 문서] redis-cli — Redis CLI utility**
  - URL: <https://redis.io/docs/latest/develop/tools/cli/>
  - 참고 부분: 옵션 표 (`--scan`, `--latency`, `--bigkeys` 등) — 본 문서 §4의 옵션 표 근거

- **[공식 문서] SCAN command**
  - URL: <https://redis.io/docs/latest/commands/scan/>
  - 참고 부분: "cursor based iterators" 단락 — §6 SCAN 사용 근거

- **[공식 문서] HELP — Built-in help in redis-cli**
  - URL: <https://redis.io/docs/latest/commands/?group=server>
  - 참고 부분: 명령 그룹 분류 — §5의 `@string` 등 그룹 사용법 근거

- **[공식 명세] Redis 8.6 HOTKEYS command**
  - URL: <https://github.com/redis/redis/releases/tag/8.6.0>
  - 참고 부분: "Hot keys detection and reporting; new command: HOTKEYS" — §4의 hotkeys 8.6 신규 사항 근거
