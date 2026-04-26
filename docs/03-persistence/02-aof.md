# 02. AOF (Append-Only File)

> **학습 목표**: AOF가 모든 쓰기 명령을 로그로 남기는 방식, `appendfsync` 정책 3가지의 트레이드오프, AOF 재작성(rewrite)이 왜 필요한지, Redis 7+ multi-part AOF 의 구조를 이해한다.
> **예상 소요**: 30분

---

## 1. 개념

> **모든 쓰기 명령을 디스크 로그에 append.** 재시작 시 로그를 처음부터 replay.

장점:
- **데이터 안전성** (RDB보다 손실 적음, 정책에 따라 0~1초)
- 명령 단위 → 복구 시 부분 손상도 잘라내고 복구 가능

단점:
- 파일 크기 큼 (텍스트 명령)
- 재시작 시간 길음 (replay)

---

## 2. 활성화

`redis.conf`:
```
appendonly yes
appendfsync everysec       # always | everysec | no
appenddirname appendonlydir
```

확인:
```
CONFIG GET appendonly
INFO persistence
# aof_enabled:1
# aof_rewrite_in_progress:0
# aof_last_write_status:ok
# aof_current_size:1024
```

---

## 3. appendfsync 3가지 정책

| 정책 | fsync 시점 | 손실 가능 | 성능 |
|---|---|---|---|
| `always` | 매 쓰기 명령마다 | ~0 | 가장 느림 |
| `everysec` (기본) | 1초마다 별도 스레드가 fsync | 최대 1초 | 균형 |
| `no` | OS에 위임 | OS 정책 따라 (수십 초) | 가장 빠름 |

**대부분 `everysec` 권장.**

> 출처: <https://redis.io/docs/latest/operate/oss_and_stack/management/persistence/#append-only-file>

---

## 4. AOF 재작성 (Rewrite)

문제: 같은 키에 SET 1만 번 → AOF에 1만 줄. 사실 마지막 한 줄만 의미 있음.

해결: **AOF rewrite** — 현재 메모리 상태를 새 AOF로 다시 씀 (압축 효과).

```
BGREWRITEAOF             # 수동 트리거
```

자동 트리거:
```
auto-aof-rewrite-percentage 100      # 마지막 rewrite 후 100% 증가하면
auto-aof-rewrite-min-size 64mb       # AOF 최소 크기 (이보다 작으면 트리거 안 함)
```

---

## 5. Redis 7+ Multi-part AOF

7.0 이전: `appendonly.aof` 단일 파일.
7.0+ : `appendonlydir/` 디렉토리에 여러 파일:

```
appendonlydir/
├── appendonly.aof.1.base.aof     # 베이스 (RDB 형식 가능)
├── appendonly.aof.1.incr.aof     # 베이스 이후 증분
├── appendonly.aof.2.incr.aof
└── appendonly.aof.manifest        # 인덱스
```

장점:
- rewrite 동안 신규 명령은 새 incr 파일에 누적 (중복 작성 없음)
- 베이스를 RDB 형식으로 저장 가능 (`aof-use-rdb-preamble yes`) → 빠른 복구

> 출처: <https://github.com/redis/redis/blob/8.6/src/aof.c>
> 참고 부분: `aofManifest`, `serverManifest` 관련 코드

---

## 6. AOF 손상 복구

전원 손실 등으로 AOF 끝부분이 잘림 → 재시작 시 에러.

```
redis-check-aof --fix appendonlydir/appendonly.aof.X.incr.aof
```

옵션:
- 잘린 명령(손상된 마지막 명령)은 잘라냄
- 복구 후 약간의 데이터 손실 (마지막 명령들).

---

## 7. AOF + RDB 혼합 (aof-use-rdb-preamble)

```
aof-use-rdb-preamble yes    # 기본 yes
```

rewrite 시 베이스 .aof 를 **RDB 바이너리 형식**으로 작성. 그 위에 incr는 평소처럼 텍스트 명령.

장점:
- 베이스 로딩이 텍스트 replay보다 훨씬 빠름.
- 복구 = RDB 로딩 + 마지막 incr replay.

---

## 8. 흔한 함정

| 함정 | 설명 |
|---|---|
| `appendfsync always` 운영 | 매 명령마다 fsync → throughput 절반 이하. 정말 필요한 케이스인지 재검토. |
| AOF rewrite 안 함 | 파일 크기 증가 → 디스크 / 재시작 시간 ↑. auto rewrite 옵션 확인. |
| BGREWRITEAOF + BGSAVE 동시 | fork 중복 → 메모리 부담. Redis가 자동 회피하지만 모니터링 필요. |
| `appendonly.aof` 단일 파일 가정 | 7+에서는 디렉토리 + manifest. 백업/모니터링 스크립트 갱신 필요. |
| AOF만 켜고 RDB 끔 | 가능하지만 백업 / disaster recovery에는 RDB 권장. |

---

## 9. 실습

학습용 별도 conf 만들어서:
```bash
cp docker/redis/conf/redis.conf docker/redis/conf/redis-aof.conf
# redis-aof.conf 의 appendonly 를 yes로 변경

# 새 compose에서 마운트하거나, 동일 파일을 일시 수정
```

또는 즉시:
```
CONFIG SET appendonly yes
SET k1 v1
SET k2 v2
INFO persistence | grep aof_current_size

BGREWRITEAOF
```

`docker compose exec redis ls -lh /data/appendonlydir/`

---

## 10. 직접 해보기

1. `appendonly` 켜고 100개 SET → `aof_current_size` 확인.
2. `BGREWRITEAOF` 후 크기 변화.
3. 컨테이너 강제 종료(`docker compose kill redis`) 후 재시작 → 데이터 살아있는지.
4. `appendfsync` 를 `always` 로 바꾸고 `redis-benchmark -t set` → throughput 차이.

---

## 11. 참고 자료

- **[공식 문서] Redis Persistence — Append-only file**
  - URL: <https://redis.io/docs/latest/operate/oss_and_stack/management/persistence/>
  - 참고 부분: AOF + appendfsync 정책 — §3 근거

- **[공식 문서] BGREWRITEAOF**
  - URL: <https://redis.io/docs/latest/commands/bgrewriteaof/>
  - 참고 부분: 동작 정의 — §4 근거

- **[GitHub] redis/redis — src/aof.c (8.6)**
  - URL: <https://github.com/redis/redis/blob/8.6/src/aof.c>
  - 참고 부분: multi-part AOF, manifest — §5 근거
