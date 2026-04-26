# 03. 핵심 메트릭 해석법

> **학습 목표**: redis_exporter가 노출하는 메트릭 중 운영에서 가장 자주 보는 12가지를 의미·정상 범위·경고 임계와 함께 정리한다.
> **예상 소요**: 25분

---

## 1. 가용성 / 기본

### `redis_up`
- 의미: redis_exporter가 대상 Redis에 연결할 수 있는가? (1 / 0)
- 알람: `redis_up == 0` for 1m → critical

### `redis_uptime_in_seconds`
- 의미: 마지막 시작 후 초.
- 알람: 갑자기 0 또는 작아짐 → 재시작 발생.

---

## 2. 메모리

### `redis_memory_used_bytes`
- 의미: 데이터 + 오버헤드 메모리 사용 (jemalloc 기준).
- 정상: 안정적이고 점진적 증가 / 정점에서 평탄.
- 알람: `> 0.9 * maxmemory` for 5m → warning.

### `redis_memory_max_bytes`
- 의미: maxmemory 옵션 값 (0이면 미설정).
- 0이면 시스템 메모리 한계까지 사용 가능 → eviction 정책 확인 필수.

### `redis_memory_fragmentation_ratio`
- 의미: rss / used (메모리 단편화).
- 정상: 1.0 ~ 1.5
- 큰 값: 단편화 심각 → `activedefrag yes` 검토.
- 1.0 미만 (<1.0): 메모리가 swap 으로 밀려나거나 OS 페이지 압박. 위험.

### eviction 관련

```promql
rate(redis_evicted_keys_total[5m])
```
- > 0 이면 maxmemory에 도달해서 키가 쫓겨나는 중.
- "예상치 못한 eviction" 이면 `maxmemory` 늘리거나 TTL 다듬기.

---

## 3. 클라이언트

### `redis_connected_clients`
- 의미: 현재 연결 수.
- 알람: `maxclients` (기본 10000) 의 80% 초과 → warning.

### `redis_blocked_clients`
- 의미: BLPOP/BRPOP/XREAD BLOCK/WAIT 등으로 대기 중인 클라이언트 수.
- 정상: 큐 컨슈머 수와 비슷.
- 알람: 갑자기 폭증 → 처리 지연.

---

## 4. 처리량 / 명령

### `redis_commands_processed_total`
- 의미: 누적 명령 수.
- 사용: `rate(redis_commands_processed_total[1m])` 로 RPS 도출.

### `redis_commands_total{cmd="..."}` (또는 `redis_commands_duration_seconds_total`)
- 의미: 명령별 호출 수 / 누적 실행 시간.
- 사용: 어떤 명령이 가장 부하 큰지.
```promql
topk(5, rate(redis_commands_total[5m]))
```

### `redis_slowlog_length`
- 의미: SLOWLOG에 기록된 항목 수.
- 변화 추세 → 느린 명령이 늘어나고 있는지.

> Redis 8.6+ 부터 `redis_slowlog_commands_count`, `slowlog_commands_time_ms_*` 같은 더 풍부한 메트릭이 추가됨 (8.8 M02 release notes). redis_exporter v1.82.0이 이를 인식한다면 자동 노출.

---

## 5. 캐시 효율

### `redis_keyspace_hits_total` / `redis_keyspace_misses_total`
- 의미: GET 류 명령에서 키가 있었나 / 없었나 누적.
- 사용:
```promql
rate(redis_keyspace_hits_total[5m]) /
clamp_min(rate(redis_keyspace_hits_total[5m]) + rate(redis_keyspace_misses_total[5m]), 1)
```
- 정상: 캐시 워크로드 → 0.9+ 권장. 0.5 미만이면 캐시 효율 문제 (TTL 짧음, key 패턴 잘못, cache stampede 등).

---

## 6. 키스페이스

### `redis_db_keys{db="db0"}`
- 의미: DB별 키 개수.
- 사용: 누적 추이로 누수 감지 / TTL 미설정 키 발견.

### `redis_db_keys_expiring{db="db0"}`
- 의미: TTL 있는 키 개수.
- 비율 (`expiring / keys`) 이 너무 낮으면 → 캐시 키에 TTL 빠짐 점검.

### `redis_expired_keys_total`
- 의미: TTL로 만료된 키 누적.
- `rate(...) > 0` 면 만료가 일어나고 있음.

---

## 7. 영속성

### `redis_rdb_last_bgsave_status` (1=ok, 0=fail)
- 0이면 즉시 알람.

### `redis_rdb_last_bgsave_duration_sec`
- 의미: 마지막 BGSAVE 소요 시간.
- 매우 길면 디스크/CPU 부담 점검.

### `redis_rdb_changes_since_last_save`
- 의미: 마지막 save 이후 변경 수.
- 자주 save 정책 평가에 사용.

### `redis_aof_rewrite_in_progress` (1=진행 중)
### `redis_aof_last_rewrite_duration_sec`

---

## 8. 복제 (사용 시)

### `redis_connected_slaves`
- 의미: 연결된 replica 수.
- 알람: 기대값 미만 → replica 끊김.

### `redis_replication_backlog_bytes`
- 의미: replication backlog 사용량.
- 평소 작아야 정상. 커지면 partial sync 실패 → full sync 위험.

### `redis_master_repl_offset` (master) / `redis_slave_repl_offset` (replica)
- 차이 = lag (offset 단위). 너무 크면 복제 지연.

---

## 9. 네트워크

### `redis_net_input_bytes_total` / `redis_net_output_bytes_total`
- 사용: `rate(...)` 으로 throughput.
- 큰 응답이 자주 → 어떤 명령이 큰 응답을 만드는지 SLOWLOG와 결합 분석.

---

## 10. 한눈에 보는 운영 알람 매트릭스

| 알람 | 임계 | severity |
|---|---|---|
| `redis_up == 0` | 1m | critical |
| `redis_memory_used_bytes / redis_memory_max_bytes > 0.9` | 5m | warning |
| `rate(redis_evicted_keys_total[5m]) > 100` | 10m | warning |
| `redis_rdb_last_bgsave_status == 0` | 즉시 | critical |
| `redis_connected_clients > maxclients * 0.8` | 5m | warning |
| `hit_ratio < 0.5` | 10m | warning (캐시용) |
| `redis_blocked_clients > 50` | 5m | warning (큐 컨슈머 수에 따라 조정) |
| replica lag (`master - slave offset`) > 10MB | 5m | warning |

---

## 11. 흔한 오해

| 오해 | 실제 |
|---|---|
| `redis_memory_fragmentation_ratio` 1 미만 = 좋은 것 | 아니다. swap 으로 밀려난 위험 신호 |
| eviction 발생 = 무조건 나쁨 | 캐시 정책으론 정상. 단 데이터 저장 용도면 위험 |
| connected_clients 가 0이면 | exporter 자기 자신 빼고 0. exporter는 항상 1 연결 |
| commands_total = QPS | 아님. rate() 적용해야 RPS |
| hit ratio 100% | 너무 좋은 값. 모든 read 가 캐시 → DB 안 친다는 뜻. cache miss 도 어느 정도 자연스럽다 |

---

## 12. 직접 해보기

1. `DEBUG POPULATE 100000` → `redis_db_keys` 그래프에서 변화 확인.
2. seed-data.sh 후 `rate(redis_commands_processed_total[1m])` 으로 RPS.
3. `maxmemory 100mb` + 더 큰 데이터 적재 → eviction 메트릭 발생.
4. 두 컨슈머가 BLPOP 잡고 있을 때 → `redis_blocked_clients == 2` 확인.
5. 일부 캐시 miss 시뮬 (없는 키 GET) → hit ratio 그래프 변화.

---

## 13. 참고 자료

- **[GitHub] oliver006/redis_exporter — Whats exported**
  - URL: <https://github.com/oliver006/redis_exporter#whats-exported>
  - 참고 부분: 메트릭 이름·라벨 — §2~§9 근거

- **[공식 문서] INFO command sections**
  - URL: <https://redis.io/docs/latest/commands/info/>
  - 참고 부분: server / clients / memory / replication 섹션 — 메트릭 의미 근거

- **[공식 문서] Memory optimization**
  - URL: <https://redis.io/docs/latest/operate/oss_and_stack/management/optimization/memory-optimization/>
  - 참고 부분: 단편화 / activedefrag — §2 근거

- **[GitHub] redis 8.8-M02 release notes**
  - URL: <https://github.com/redis/redis/releases/tag/8.8-m02>
  - 참고 부분: slowlog metrics 추가 — §4 근거
