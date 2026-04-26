# 03. MONITOR / SLOWLOG / --latency

> **학습 목표**: 실행 중 Redis의 진단 도구 3가지를 사용해서 "지금 무엇이 느린가" 를 즉시 파악한다.
> **예상 소요**: 25분

---

## 1. MONITOR — 모든 명령 실시간 출력

```
redis-cli MONITOR
```

```
1714056789.123456 [0 127.0.0.1:54321] "SET" "k1" "v1"
1714056789.124567 [0 127.0.0.1:54322] "GET" "k1"
1714056789.125000 [0 127.0.0.1:54323] "LPUSH" "queue" "task"
```

용도:
- "어떤 클라이언트가 어떤 명령을 보내는지" 한눈에
- 로컬 디버깅

**경고**: 운영에서 사용하면 throughput 50% 이상 떨어질 수 있다.

> 출처: <https://redis.io/docs/latest/commands/monitor/>

---

## 2. SLOWLOG — 임계 초과 명령 로그

`redis.conf`:
```
slowlog-log-slower-than 1000      # 1000 μs (= 1ms) 초과 시 기록
slowlog-max-len 128
```

조회:
```
SLOWLOG GET 10            # 최근 10개
SLOWLOG GET 10 | head -50

SLOWLOG LEN               # 현재 보관 개수
SLOWLOG RESET             # 비움
SLOWLOG HELP
```

각 항목:
```
1) 1) (integer) 47          # ID
   2) (integer) 1714056789  # unix timestamp
   3) (integer) 5234        # 실행 시간 (μs)
   4) 1) "DEBUG"            # 명령 + args
      2) "SLEEP"
      3) "0.005"
   5) "127.0.0.1:54321"     # 클라이언트
   6) "client-name"
```

**해석**:
- 5234 μs = 5.234 ms 걸림
- 단일 스레드라 그동안 다른 명령 모두 대기

### Redis 8.6 신규: SLOWLOG metrics

`INFO STATS` 에 추가된 글로벌 메트릭 (8.6+):
```
slowlog_commands_count
slowlog_commands_time_ms_sum
slowlog_commands_time_ms_max
```

`INFO COMMANDSTATS` 의 per-command:
```
slowlog_count
slowlog_time_ms_sum
slowlog_time_ms_max
```

> 출처: <https://github.com/redis/redis/releases/tag/8.8-m02> "INFO STATS - global stats for slowlog metrics" (PR #14896, Redis 8.8 M02)
> 8.6에 들어왔는지 8.8에 들어왔는지는 redis_version 으로 직접 확인.

---

## 3. --latency — 지속 측정

### 단순 모드

```bash
redis-cli --latency
min: 0, max: 5, avg: 0.13 (4521 samples)
```

매 초 PING 보내고 응답 시간 측정. Ctrl+C로 종료.

### 히스토리 모드 (1초 간격 통계)

```bash
redis-cli --latency-history
min: 0, max: 1, avg: 0.10 (147 samples) -- 1.00 seconds range
min: 0, max: 2, avg: 0.11 (145 samples) -- 1.00 seconds range
```

### 분포 모드

```bash
redis-cli --latency-dist
```

ASCII 그래프로 latency 분포를 실시간 표시.

### Intrinsic 지연 (서버 자체)

```bash
redis-cli --intrinsic-latency 30
Max latency so far: 1 microseconds.
Max latency so far: 2 microseconds.
...
30 seconds in total.
```

서버 내부 루프의 최대 latency. **이 값이 크면 OS / 하드웨어 / VM 문제**.

> 출처: <https://redis.io/docs/latest/operate/oss_and_stack/management/optimization/latency-monitor/>

---

## 4. LATENCY 명령군 (활성화 필요)

```
CONFIG SET latency-monitor-threshold 100   # 100ms 이상 이벤트 기록
LATENCY LATEST                              # 카테고리별 가장 최근 spike
LATENCY HISTORY <event>                     # 시간순 spike 목록
LATENCY GRAPH <event>                       # ASCII 그래프
LATENCY DOCTOR                              # 사람 읽기 좋은 분석 + 권장 사항
LATENCY RESET                               # 비움
```

`DOCTOR` 출력 예:
```
Dave, I have observed the system for some time.
I'm sorry but I'm unable to find the source of latency.

Maybe you should follow these advices:

- I detected a non-zero amount of anonymous huge pages used by your process.
  ...
```

운영자 친화적.

---

## 5. INFO commandstats — 명령별 통계

```
INFO commandstats
```

```
cmdstat_set: calls=12345, usec=45678, usec_per_call=3.7
cmdstat_get: calls=98765, usec=87654, usec_per_call=0.89
...
```

- `calls` : 호출 횟수
- `usec_per_call` : 평균 실행 시간

특정 명령이 갑자기 느려지면 여기서 보임.

---

## 6. 흔한 함정

| 함정 | 설명 |
|---|---|
| MONITOR 운영에서 켜둠 | throughput 절반 이하. 짧게만. |
| SLOWLOG 임계가 너무 높음 | 작은 spike 안 보임. 학습용은 1000μs(=1ms) 권장. |
| `--latency` 만 보고 결론 | PING 만 측정. 실제 명령은 다를 수 있음. memtier로 mixed workload 측정 병행. |
| LATENCY MONITOR 비활성 상태에서 LATEST | 빈 결과. `latency-monitor-threshold` 설정 먼저. |

---

## 7. 직접 해보기

1. `redis-cli --latency` 백그라운드, `redis-benchmark` 다른 터미널에서 실행 → latency 변화.
2. `DEBUG SLEEP 0.5` 실행 후 `SLOWLOG GET 1` 확인.
3. `LATENCY DOCTOR` 출력 그대로 적용해보기.
4. `INFO commandstats` 출력 → seed-data.sh 후 어떤 명령이 가장 많이 호출됐는지.
5. `--intrinsic-latency 30` → max latency 가 1ms 이상이면 호스트 문제.

---

## 8. 참고 자료

- **[공식 문서] Latency monitoring**
  - URL: <https://redis.io/docs/latest/operate/oss_and_stack/management/optimization/latency-monitor/>
  - 참고 부분: latency-monitor-threshold, LATENCY 명령 — §4 근거

- **[공식 문서] SLOWLOG**
  - URL: <https://redis.io/docs/latest/commands/slowlog/>
  - 참고 부분: 정의 — §2 근거

- **[공식 문서] MONITOR**
  - URL: <https://redis.io/docs/latest/commands/monitor/>
  - 참고 부분: 성능 영향 경고 — §1 근거

- **[GitHub] redis/redis 8.8-M02 release notes**
  - URL: <https://github.com/redis/redis/releases/tag/8.8-m02>
  - 참고 부분: slowlog metrics 추가 (#14896) — §2 신규 사항 근거
