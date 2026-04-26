# 05. Troubleshooting Playbook — Latency Spike 분석

> **학습 목표**: "프로덕션 Redis가 갑자기 느려졌다" 상황에서 무엇부터 봐야 하는지 단계별 체크리스트, latency spike 원인별 진단법, kernel/OS 레벨 튜닝까지 다룬다.
> **예상 소요**: 35분

---

## 1. 5분 안 분류 — 무엇부터?

```
체크 1) redis-cli ping         # 살아있나?
체크 2) redis-cli --latency    # baseline latency? (1ms 이상이면 이상)
체크 3) SLOWLOG GET 10         # 느린 명령 있었나?
체크 4) INFO commandstats      # 어떤 명령이 평소보다 느려졌나?
체크 5) INFO memory            # 메모리 가득 / fragmentation?
체크 6) INFO persistence       # BGSAVE / AOF rewrite 중?
체크 7) CLIENT LIST            # 비정상 connection 수?
체크 8) LATENCY DOCTOR         # 사람 읽기 좋은 진단 + 권고
```

> 출처: <https://redis.io/docs/latest/operate/oss_and_stack/management/optimization/latency/>

---

## 2. Latency Baseline — 환경 자체 latency 측정

```bash
# 서버 호스트에서 (Redis 안 거치고 OS 자체 측정)
redis-cli --intrinsic-latency 100
Max latency so far: 1 microseconds.
Max latency so far: 16 microseconds.
...
Max latency so far: 115 microseconds.    # 0.115ms
```

→ **이 값이 baseline**. Redis 가 이보다 빨라질 수 없다.

| 환경 | 일반적 intrinsic latency |
|---|---|
| 물리 서버 | < 0.5ms |
| 좋은 VM | < 1ms |
| Linode/노이즈 많은 VM | 1~10ms (이상치) |
| 도커 데스크톱 (Mac) | 0.5~5ms |

intrinsic 이 너무 크면 **호스트 / VM / 하이퍼바이저 문제**. Redis 튜닝으로 해결 안 됨.

---

## 3. 원인 분류 매트릭스

| 증상 | 가장 흔한 원인 | 진단 명령 | 해결 |
|---|---|---|---|
| 모든 명령이 느림 (μs → ms) | Slow command 실행 중 | SLOWLOG GET 10 | 그 명령 제거 / 다른 자료형 |
| 주기적 latency spike (수 초마다) | BGSAVE fork() | INFO persistence + latency-monitor | save 정책 완화 / diskless |
| AOF 켰을 때만 spike | fdatasync 지연 | strace -p $(pidof redis-server) -e trace=fdatasync | appendfsync everysec / SSD |
| 갑자기 모든 명령 0~수 초 멈춤 | swap 사용 | /proc/$(pidof redis-server)/smaps + vmstat | maxmemory + RAM 확보 |
| BGSAVE 후 메모리 폭증 + 느림 | Transparent Huge Pages | grep AnonHugePages /proc/.../smaps | THP 비활성 |
| connection refused / Cannot allocate | maxclients 도달 / OOM | INFO clients + dmesg | maxclients 증가 / RAM |
| 일정 키만 느림 | hot key (한 키에 부하 집중) | redis-cli --hotkeys 또는 8.6 HOTKEYS | sharding / cache |
| 일정 키만 무거움 | big key | redis-cli --bigkeys + MEMORY USAGE | 분할 / UNLINK |
| Cluster 일부 노드만 느림 | 슬롯 불균형 / hot slot | CLUSTER SLOT-STATS | rebalance / hashtag |

---

## 4. 원인별 깊이 — Fork latency

### 4.1 왜 발생?
BGSAVE / BGREWRITEAOF 시 fork() 호출 → 페이지 테이블 복제. 메모리 클수록 오래 걸림.

페이지 테이블 크기 ≈ 메모리 / 4KB × 8 bytes
→ 24GB Redis = 48MB 페이지 테이블 복제

| 환경 | fork 시간 (per GB) |
|---|---|
| 물리 / 모던 hypervisor | ~10ms/GB |
| KVM | ~20ms/GB |
| EC2 HVM (모던) | ~10ms/GB |
| EC2 PV (옛 인스턴스) | ~240ms/GB |
| Linode (Xen) | ~400ms/GB |

> 출처: <https://redis.io/docs/latest/operate/oss_and_stack/management/optimization/latency/#fork-time-in-different-systems>

### 4.2 진단
```
INFO persistence | grep latest_fork_usec
latest_fork_usec:128345        # 128ms — 8.6GB 인스턴스에서 적당
```

### 4.3 해결
- **diskless replication**: `repl-diskless-sync yes`
- **save 정책 완화**: 너무 자주 BGSAVE 하지 말기
- **EC2 모던 인스턴스** (HVM, m3+/m5+ 등)
- **메모리 제한** (한 인스턴스 너무 크게 안 쓰기 → 샤딩)

---

## 5. 원인별 깊이 — Transparent Huge Pages (THP)

### 5.1 왜 문제?
fork() 후 부모가 일부 페이지 수정 → CoW 가 발생하는데, **THP 켜져 있으면 2MB 단위로 복제**. 작은 변경에도 큰 메모리 / latency 비용.

### 5.2 비활성

```bash
# 임시
echo never > /sys/kernel/mm/transparent_hugepage/enabled

# 영구 (sysctl 또는 systemd 서비스)
# /etc/rc.local 또는 systemd unit 으로 부팅 시 적용
```

확인:
```bash
cat /sys/kernel/mm/transparent_hugepage/enabled
always madvise [never]      # never가 [] 안에 있으면 OK
```

> 출처: <https://redis.io/docs/latest/operate/oss_and_stack/management/optimization/latency/#latency-induced-by-transparent-huge-pages>

---

## 6. 원인별 깊이 — Swap

### 6.1 진단

Redis 의 PID:
```bash
$ redis-cli info server | grep process_id
process_id:5454
```

smaps 에서 swap 사용량:
```bash
$ cat /proc/5454/smaps | grep '^Swap:' | awk '{sum += $2} END {print sum, "kB"}'
```

vmstat 에서 swap 활동:
```bash
$ vmstat 1
... si  so ...                      # 0 0 이 정상
```

### 6.2 해결
- `maxmemory` 명시 + `maxmemory-policy` 설정
- **호스트 RAM 늘리기** / Redis 인스턴스 크기 줄이기
- 같은 호스트에서 다른 메모리 사용 큰 프로세스 제거
- swap 자체는 켜둘 것 (OOM kill 방지). 단 자주 사용되면 문제.

> 출처: <https://redis.io/docs/latest/operate/oss_and_stack/management/optimization/latency/#latency-induced-by-swapping-operating-system-paging>

---

## 7. 원인별 깊이 — AOF + Disk I/O

### 7.1 진단

```bash
# 메인 스레드 fdatasync 호출 확인 (대부분은 백그라운드 스레드라 안 보여야 함)
sudo strace -p $(pidof redis-server) -T -e trace=fdatasync

# 모든 스레드 포함
sudo strace -f -p $(pidof redis-server) -T -e trace=fdatasync,write 2>&1 | grep -v '0.0'
```

### 7.2 해결
- `appendfsync everysec` (대부분 권장). always 는 매우 느림.
- `no-appendfsync-on-rewrite yes` — rewrite 중에는 fsync 안 함
- **SSD** 디스크 사용
- 다른 I/O 무거운 프로세스 분리

---

## 8. 원인별 깊이 — Active Expires

### 8.1 동작
Redis 는 100ms 마다 active expire 사이클 → 20개 샘플링, 25% 이상 만료면 반복.

→ **많은 키가 같은 시점에 만료** 되면 Redis 가 그 사이클에서 길게 머물러 다른 명령 지연.

### 8.2 해결
- 만료 시각에 **jitter 추가** (예: 1시간 ± 5분 무작위)
- TTL 분포 모니터링 (`redis_db_keys_expiring`)

---

## 9. Kernel / OS 튜닝 (Production)

### 9.1 vm.overcommit_memory = 1 (필수)

```bash
echo "vm.overcommit_memory = 1" >> /etc/sysctl.conf
sysctl vm.overcommit_memory=1
```

이유: BGSAVE 시 fork() 가 메모리 두 배 commit 시도 → 0(default) 면 거부될 수 있음.

> 출처: <https://redis.io/docs/latest/operate/oss_and_stack/management/admin/#memory>

### 9.2 net.core.somaxconn

```bash
echo 65535 > /proc/sys/net/core/somaxconn
```

Redis 의 `tcp-backlog` 가 커널 한계보다 작아야 의미 있음.

### 9.3 transparent_hugepage = never
(위 §5)

### 9.4 swap 활성

> swap 안 쓰면 OOM kill 가능. swap 자체는 활성하되 많이 쓰는지 모니터링.

### 9.5 file descriptor 제한

```bash
ulimit -n 100000
```

또는 systemd unit 의 `LimitNOFILE`. Redis maxclients 가 이를 초과하면 안 됨.

---

## 10. Capacity Planning — 메모리 사이징

### 10.1 키당 메모리 추정

```
> MEMORY USAGE my:key
(integer) 56
```

자료형별 대략:
- 작은 String (10 chars): ~56 bytes (overhead 포함)
- listpack Hash 5 필드: ~100 bytes
- hashtable Hash 100 필드: ~5 KB
- ZSET 1000 멤버 (skiplist): ~80 KB

### 10.2 1000만 키 = ?

```
key 평균 100 bytes (overhead 포함) → 1GB
키 자체 (string) + 자료형 + 엔트리 메타 + dict 오버헤드
```

대략 50% 안전 마진 권장 → **1.5GB**.

### 10.3 fork CoW 마진

BGSAVE 중 부모가 50% 페이지 수정 → 메모리 사용 1.5x. **maxmemory 는 시스템 RAM 의 60% 정도** 권장.

---

## 11. LATENCY DOCTOR — 친절한 진단

```
> LATENCY DOCTOR
Dave, I have observed the system for some time.
I'm sorry but I'm unable to find the source of latency.

Maybe you should follow these advices:

- I detected a non-zero amount of anonymous huge pages used by your process.
  ...
```

선결 조건: `latency-monitor-threshold 100` (ms) 같은 임계 설정.

```
CONFIG SET latency-monitor-threshold 100
LATENCY LATEST                     # 카테고리별 최근 spike
LATENCY HISTORY <event>            # 시간순
LATENCY GRAPH <event>              # ASCII 그래프
LATENCY RESET
```

---

## 12. RAM 자체가 손상됐는지 의심

```bash
redis-server --test-memory 4096    # 4GB 테스트
```

또는 부팅 후 [memtest86](http://memtest86.com).

> Redis 가 이상한 크래시 / 데이터 깨짐 → 종종 RAM 불량.

---

## 13. CRASH 분석

크래시 시 stderr 에 stack trace + state dump 가 찍힘.
`logfile` 설정으로 영구 저장.

```
DEBUG SEGFAULT      # 학습용으로 일부러 크래시 (운영 절대 금지)
```

이슈 리포트 시:
- `redis-cli INFO server` 출력
- 크래시 로그 전체
- `INFO commandstats`
- 가능하면 core dump

> 출처: <https://redis.io/docs/latest/operate/oss_and_stack/management/debugging/>

---

## 14. 흔한 함정

| 함정 | 설명 |
|---|---|
| latency 봤더니 RTT 만 측정 | --intrinsic-latency 로 환경 baseline 도 같이. |
| THP 비활성 안 함 | BGSAVE 시 메모리 + latency 폭증. 운영 필수. |
| swap off | OOM kill 가능. 활성 + 모니터링이 정답. |
| maxmemory 미설정 | 무제한 → swap → 큰 latency. |
| `--bigkeys` 운영에서 자주 | SCAN + 추정. 가벼우나 너무 자주 X. |
| latency-monitor-threshold 0 (꺼짐) | LATENCY 명령 안 됨. 100~200ms 권장. |

---

## 15. 직접 해보기

1. `redis-cli --intrinsic-latency 30` → 본인 환경 baseline.
2. `DEBUG SLEEP 0.5` → SLOWLOG / LATENCY 양쪽에서 spike 보임.
3. `latency-monitor-threshold 50` 후 `LATENCY DOCTOR` 출력.
4. seed-data.sh 적재 후 `redis-cli --bigkeys` / `--memkeys` / `--hotkeys`.
5. 도커 호스트에서 `cat /sys/kernel/mm/transparent_hugepage/enabled` 확인.

---

## 16. 참고 자료

- **[공식 문서] Diagnosing latency issues** — <https://redis.io/docs/latest/operate/oss_and_stack/management/optimization/latency/>
  - 참고 부분: 체크리스트, fork 시간 표, swap 진단 절차 — §1, §4, §6 근거

- **[공식 문서] Latency monitoring** — <https://redis.io/docs/latest/operate/oss_and_stack/management/optimization/latency-monitor/>
  - 참고 부분: LATENCY 명령군 + threshold — §11 근거

- **[공식 문서] Administration tips** — <https://redis.io/docs/latest/operate/oss_and_stack/management/admin/>
  - 참고 부분: vm.overcommit_memory / THP / swap / maxmemory — §9, §10 근거

- **[공식 문서] Troubleshooting** — <https://redis.io/docs/latest/operate/oss_and_stack/management/troubleshooting/>
  - 참고 부분: --test-memory, debugging guide — §12, §13 근거

- **[공식 문서] Debugging Redis** — <https://redis.io/docs/latest/operate/oss_and_stack/management/debugging/>
  - 참고 부분: crash dumps / DEBUG SEGFAULT — §13 근거

- **[공식 문서] CPU profiling** — <https://redis.io/docs/latest/operate/oss_and_stack/management/optimization/cpu-profiling/>
  - 참고 부분: 단일 스레드 모델 / perf — §1 보강
