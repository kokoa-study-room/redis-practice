# 01. Replication (복제)

> **학습 목표**: master-replica 구성, REPLICAOF / SYNC 흐름, full sync vs partial sync 의 차이, replica를 read 부하 분산에 쓸 때 일관성 유의점.
> **예상 소요**: 25분

---

## 1. 개념

> **Master 의 모든 쓰기를 Replica 가 비동기로 복제.**

```
[Master]
  │ writes
  ▼
write 명령 → AOF / RDB 영속
write 명령 → replication backlog buffer
                      │
                      ▼ (replica 연결)
                  [Replica 1] (read 가능)
                  [Replica 2] (read 가능)
                  ...
```

용도:
- **읽기 부하 분산**
- **백업 노드** (replica에서 BGSAVE → master 부담 없음)
- **HA 의 기반** (Sentinel/Cluster 필수)
- **데이터센터 분산**

---

## 2. 설정 — REPLICAOF

### Replica 쪽 (시작 시 또는 동적)

```
# redis.conf
replicaof <master-host> <master-port>
masterauth <password>          # master에 requirepass 있으면

# 또는 동적
REPLICAOF 192.168.1.10 6379
REPLICAOF NO ONE               # 복제 중단 → 독립 master로 승격
```

확인:
```
INFO replication
# Role:slave
# master_host:192.168.1.10
# master_port:6379
# master_link_status:up
# master_last_io_seconds_ago:1
# master_sync_in_progress:0
# slave_repl_offset:1234567
```

---

## 3. 동기화 — Full vs Partial

### 3.1 Full Sync (처음 또는 완전 단절)

```
1. replica → master: PSYNC ? -1
2. master:
   - BGSAVE → .rdb 생성
   - 그 동안의 새 명령은 buffer에 보관
3. master → replica: .rdb 파일 전송
4. replica:
   - 메모리 비우고 .rdb 로드
5. master → replica: buffer에 쌓인 명령 전송
6. 이후 평상시 명령 stream
```

비용: master가 fork()해서 .rdb 만들고, 큰 .rdb를 네트워크로 전송. 큰 DB일수록 무거움.

### 3.2 Partial Sync (잠깐 단절 후 재연결)

```
1. replica → master: PSYNC <repl-id> <last-offset>
2. master: backlog buffer에 그 offset 부터 데이터가 있음? Yes.
3. master → replica: buffer 의 일부만 전송
```

조건: `repl-backlog-size` (기본 1MB) 안에 단절 시간 동안의 변경분이 다 들어가야 함. 안 들어가면 full sync로 fallback.

**튜닝**: 자주 끊겼다 붙는 환경이면 `repl-backlog-size` 키우기.

> 출처: <https://redis.io/docs/latest/operate/oss_and_stack/management/replication/>

### 3.3 Diskless Replication (Redis 6+)

```
repl-diskless-sync yes        # 기본 yes
repl-diskless-sync-delay 5
```

master가 .rdb를 디스크에 안 쓰고 **메모리 → 네트워크 직접 스트리밍**. 디스크 IO 부담 없음 (대신 네트워크 1회만 사용 가능).

---

## 4. Replica 옵션

```
replica-read-only yes                  # replica에 write 막음 (기본)
replica-priority 100                   # Sentinel failover 시 우선순위 (낮을수록 우선)
replica-serve-stale-data yes           # master 끊겼을 때도 replica가 응답
                                       # no면 SYNC IN PROGRESS 에러
```

---

## 5. Eventual Consistency (replica의 함정)

```
client → master: SET k 100
client → replica: GET k         # 응답: 99 (아직 복제 안 됨!)
```

비동기 복제 → **read-after-write 일관성 깨짐**.
해결:
- 같은 클라이언트의 write 후 즉시 read 는 master로 (sticky)
- `WAIT N timeout` — N개 replica가 받을 때까지 master가 대기 (성능 비용 큼)

---

## 6. 실습 — 단일 호스트에 master + replica

```yaml
# docker/docker-compose.replica.yml (참고용)
services:
  redis-master:
    image: redis:8.6-alpine
    command: redis-server --port 6379
    ports: ["127.0.0.1:6379:6379"]
  redis-replica-1:
    image: redis:8.6-alpine
    command: redis-server --port 6380 --replicaof redis-master 6379
    ports: ["127.0.0.1:6380:6380"]
  redis-replica-2:
    image: redis:8.6-alpine
    command: redis-server --port 6381 --replicaof redis-master 6379
    ports: ["127.0.0.1:6381:6381"]
```

또는 한 컨테이너에서 실험:
```bash
docker compose exec redis redis-cli REPLICAOF 192.168.1.50 6379
```

---

## 7. 흔한 함정

| 함정 | 설명 |
|---|---|
| Replica에 write | `READONLY You can't write against a read only replica.` 에러. `replica-read-only no` 로 가능하지만 데이터 분기 위험. |
| 큰 DB의 잦은 full sync | 네트워크/디스크 부담. backlog 늘리기 또는 diskless. |
| `WAIT` 남발 | 동기 복제 비슷해짐 → 처리량 떨어짐. |
| master 죽으면 자동 failover 안 됨 | replication만으로는 HA 아님. **Sentinel 또는 Cluster 필요**. |
| replica 시계 안 맞음 | `replica-serve-stale-data no` 권장 (TTL 잘못 보낼 수 있음). |

---

## 8. 직접 해보기

1. 위 compose로 master + replica 띄우고 master에서 SET → replica에서 GET 즉시 확인.
2. `INFO replication` 양쪽에서.
3. master에 1만 SET → `slave_repl_offset` 진행 확인.
4. master 일시 종료 → replica에서 `master_link_status:down` 확인 → 재시작 시 partial sync인지 full sync인지.
5. `WAIT 1 1000` 테스트.

---

## 9. 참고 자료

- **[공식 문서] Replication**
  - URL: <https://redis.io/docs/latest/operate/oss_and_stack/management/replication/>
  - 참고 부분: PSYNC, repl-backlog, diskless — §3 근거

- **[공식 문서] REPLICAOF / WAIT**
  - URL: <https://redis.io/docs/latest/commands/replicaof/>, `/wait/`
  - 참고 부분: 명령 정의 — §2, §5 근거

- **[GitHub] redis/redis — src/replication.c (8.6)**
  - URL: <https://github.com/redis/redis/blob/8.6/src/replication.c>
  - 참고 부분: PSYNC 구현 — §3 근거
