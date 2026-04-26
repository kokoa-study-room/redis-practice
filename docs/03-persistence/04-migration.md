# 04. Migration & Upgrade — 데이터 이전과 버전 업그레이드

> **학습 목표**: DUMP / RESTORE / MIGRATE / 외부 스크립트로 키 단위 / DB 단위 / 인스턴스 단위 데이터 이전, 버전 업그레이드 / 다운그레이드의 한계, 무중단 절차를 익힌다.
> **예상 소요**: 25분

---

## 1. 시나리오

| 시나리오 | 적합한 방법 |
|---|---|
| 단일 키 / 작은 셋 이전 | `DUMP` + `RESTORE` |
| 인스턴스 → 다른 인스턴스 (한 번에) | `MIGRATE` |
| 전체 DB 이전 | RDB 파일 복사 또는 replication 임시 |
| 버전 업그레이드 (8.4 → 8.6) | replication based 무중단 절차 |
| Cluster 노드 추가 / 제거 | `--cluster reshard` |
| 데이터 다운그레이드 | 일반적으로 불가 (RDB 호환성 단방향) |

---

## 2. DUMP / RESTORE — 단일 키 직렬화

### 2.1 DUMP
```
DUMP <key>
"\x00\x05hello\x0c\x00..."        # 직렬화된 binary
```
- Redis 가 RDB 형식으로 키 값을 직렬화
- 결과는 binary (printable 안 됨)

### 2.2 RESTORE
```
RESTORE <key> <ttl_ms> <serialized> [REPLACE] [ABSTTL] [IDLETIME ms] [FREQ freq]
```
- `<ttl_ms>` : 0 = TTL 없음. 양수 = 그 만큼 후 만료
- `REPLACE` : 키 이미 있으면 덮어쓰기
- `ABSTTL` : ttl 을 절대 unix time ms 로 해석

### 2.3 사용 예 (다른 인스턴스로)
```python
import redis

src = redis.Redis(host="src-host", port=6379)
dst = redis.Redis(host="dst-host", port=6379)

data = src.dump("user:1001")
ttl = src.pttl("user:1001")
ttl = ttl if ttl > 0 else 0

dst.restore("user:1001", ttl, data, replace=True)
```

### 2.4 호환성 주의
- RDB 형식 버전이 매우 다른 두 Redis 간엔 RESTORE 실패.
- 보통 **같은 메이저 / 인접 메이저** 는 호환. (예: 7.x ↔ 7.x, 7.x → 8.x).
- **8.x → 7.x 같은 다운그레이드는 불가** (8.x 가 추가한 자료형 표현이 7.x 에 없음).

---

## 3. MIGRATE — 한 번에 여러 키 + 원자적

```
MIGRATE <host> <port> <key> <destination-db> <timeout-ms> [COPY] [REPLACE] [AUTH pwd] [AUTH2 user pwd] [KEYS k1 k2 ...]
```

```
MIGRATE dst-host 6379 user:1 0 5000 REPLACE
MIGRATE dst-host 6379 "" 0 5000 REPLACE KEYS user:1 user:2 user:3
```

내부 동작:
1. SRC 가 DUMP 로 직렬화
2. SRC → DST 새 connection 으로 RESTORE
3. 성공 시 SRC 에서 키 삭제 (COPY 옵션 없으면)
4. 실패 시 SRC 그대로

장점: 원자적 (네트워크 끊겨도 둘 다 갖거나 둘 다 없음).
단점: 동기 명령 — 그동안 SRC 멈춤. 큰 키는 위험.

---

## 4. 전체 인스턴스 이전 — RDB 파일 복사

```bash
# 1) SRC 에서 BGSAVE
redis-cli -h src BGSAVE
# LASTSAVE 로 완료 확인
redis-cli -h src LASTSAVE

# 2) RDB 파일 가져오기 (방법 A: 호스트에서 redis-cli --rdb)
redis-cli -h src --rdb /tmp/snap.rdb

# 또는 (방법 B: Docker 호스트의 dir/dbfilename 위치에서)
scp src-host:/data/dump.rdb /tmp/snap.rdb

# 3) DST 에 복사 + 시작
scp /tmp/snap.rdb dst-host:/data/dump.rdb
ssh dst-host "redis-server /etc/redis/redis.conf"
```

DST 가 시작될 때 dump.rdb 가 있으면 자동 로딩.

---

## 5. Replication 기반 무중단 업그레이드

가장 안전한 패턴 (Redis 공식 권장):

```
1) 같은 호스트에 새 버전 Redis 인스턴스 (다른 포트) 시작
2) REPLICAOF 로 기존 master 의 replica 로 등록
3) 초기 동기화 완료 대기 (INFO replication | grep master_link_status:up)
4) 키 수 / 샘플 검증 (DBSIZE 일치)
5) replica 에 write 허용 (CONFIG SET slave-read-only no, 임시)
6) 클라이언트 traffic을 새 인스턴스로 점진 전환
7) (선택) CLIENT PAUSE 로 옛 master 잠시 정지
8) REPLICAOF NO ONE 으로 새 인스턴스를 master 로 승격
9) 옛 인스턴스 종료
```

> 출처: <https://redis.io/docs/latest/operate/oss_and_stack/management/admin/#upgrading-or-restarting-a-redis-instance-without-downtime>

---

## 6. Sentinel / Cluster 환경 업그레이드

### Sentinel
- 한 replica 씩 새 버전으로 교체 → 동기화 → 다음 replica.
- 마지막에 master 수동 failover 로 새 버전 replica 가 master 로.

### Cluster
- 한 노드씩 (replica 부터) 새 버전으로 교체.
- master 노드는 수동 failover 후 교체.
- 4.0 ↔ 3.2 등 cluster bus 프로토콜 호환성 변화는 mass restart 필요.

---

## 7. Cluster 재샤딩 — 노드 추가 / 제거

### 7.1 노드 추가
```bash
docker exec node-1 redis-cli --cluster add-node new-node:7007 node-1:7001

# replica 로 추가
docker exec node-1 redis-cli --cluster add-node new-replica:7008 node-1:7001 \
  --cluster-slave --cluster-master-id <master-id>
```

### 7.2 슬롯 이동 (rebalance)
```bash
docker exec node-1 redis-cli --cluster rebalance node-1:7001
```

자동으로 슬롯을 새 노드로 이동.

### 7.3 노드 제거
```bash
# 슬롯 비운 후
docker exec node-1 redis-cli --cluster del-node node-1:7001 <node-id>
```

### 7.4 Atomic slot migration (Redis 8.x)
8.x 부터 SMIGRATING / SMIGRATED / SFLUSH 를 사용한 더 효율적 / atomic 슬롯 이전 기능 추가.

---

## 8. 백업 / 복구

### 8.1 정기 백업
```bash
# 1시간마다 BGSAVE 후 dump.rdb 를 S3 에
0 * * * * redis-cli BGSAVE && \
  sleep 30 && \
  aws s3 cp /data/dump.rdb s3://backup/redis/$(date +\%Y\%m\%d_\%H).rdb
```

### 8.2 복구
1. Redis 정지
2. `dump.rdb` 를 dir 에 복사 (또는 `appendonlydir/` 통째)
3. Redis 시작 → 자동 로딩

> AOF 가 켜져 있고 파일 존재하면 RDB 무시. AOF 디렉토리도 같이 비우거나 `appendonly no`.

---

## 9. Valkey ↔ Redis 마이그레이션

Valkey 7.2 ~ 8 은 Redis 7.2 ~ 8 과 RDB / AOF 호환.
- 같은 메이저 버전이면 dump.rdb 직접 복사 가능.
- Vector Set 같은 Redis 8 신규 자료형은 Valkey 가 지원 안 하면 손실.

---

## 10. 흔한 함정

| 함정 | 설명 |
|---|---|
| 8.x → 7.x 다운그레이드 | RDB 형식 호환 안 됨. 미리 백업 필요. |
| MIGRATE 큰 키 | 동기 명령이라 그동안 SRC 정지. 키 분할 후 이전. |
| RESTORE TTL 0 줬는데 만료 기대 | 0 = no TTL. 명시적 ttl_ms 필요. |
| Cluster 새 master 추가만 하고 reshard 안 함 | 슬롯 0개라 트래픽 안 받음. rebalance 필수. |
| Replica 동기화 중 BGSAVE 무시 | replica 가 처음 sync 시 master 가 BGSAVE → CoW 메모리 폭증. 시점 주의. |
| dump.rdb 복사 후 그대로 시작 | aof 디렉토리에 옛 데이터 있으면 RDB 무시. cleanup 필요. |
| 두 인스턴스 같은 dir 공유 | 혼란 / 데이터 손상. 절대 금지. |
| 무중단 업그레이드 시 client 캐시 안 바꿈 | sentinel / 동적 발견 클라이언트 사용. |

---

## 11. 직접 해보기

1. `DUMP user:1001` 결과를 다른 인스턴스에 RESTORE → 데이터 / TTL 보존 확인.
2. 100개 키를 MIGRATE KEYS 로 한 번에 이전.
3. compose 로 두 redis 띄우고 replication 기반 무중단 업그레이드 시뮬.
4. cluster compose 의 노드 1개 추가 → reshard.
5. RDB 파일 복사로 다른 인스턴스 복원.

---

## 12. 참고 자료

- **[공식 문서] DUMP** — <https://redis.io/docs/latest/commands/dump/>
  - 참고 부분: 직렬화 형식 — §2 근거

- **[공식 문서] RESTORE** — <https://redis.io/docs/latest/commands/restore/>
  - 참고 부분: 옵션 (REPLACE / ABSTTL / IDLETIME / FREQ) — §2.2 근거

- **[공식 문서] MIGRATE** — <https://redis.io/docs/latest/commands/migrate/>
  - 참고 부분: 원자성 / KEYS 옵션 — §3 근거

- **[공식 문서] Administration — Upgrading without downtime** — <https://redis.io/docs/latest/operate/oss_and_stack/management/admin/#upgrading-or-restarting-a-redis-instance-without-downtime>
  - 참고 부분: replication 기반 절차 — §5 근거

- **[공식 문서] Cluster Tutorial — reshard / add-node / del-node** — <https://redis.io/docs/latest/operate/oss_and_stack/scaling/>
  - 참고 부분: 명령 사용법 — §7 근거

- **[Redis 8.6 release notes — atomic slot migration]** — <https://github.com/redis/redis/releases/tag/8.6.0>
  - 참고 부분: SMIGRATING / SMIGRATED / SFLUSH — §7.4 근거
