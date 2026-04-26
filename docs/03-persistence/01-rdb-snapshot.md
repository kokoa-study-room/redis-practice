# 01. RDB 스냅샷

> **학습 목표**: BGSAVE 가 fork() + CoW 로 동작하는 원리, save 정책 / 메모리 사용량의 관계, 안전한 스냅샷 정책을 설계할 수 있다.
> **예상 소요**: 25분

---

## 1. 개념

> **RDB (Redis Database File)**: 메모리 전체를 .rdb 파일에 직렬화한 스냅샷.

용도:
- **백업** (정기 주기로 .rdb 파일을 다른 곳에 복사)
- **빠른 재시작** (AOF replay보다 훨씬 빠름)
- **복제 초기화** (master → replica 전체 동기화 시 RDB 사용)

---

## 2. SAVE vs BGSAVE

| 명령 | 동작 |
|---|---|
| `SAVE` | **메인 스레드** 가 직접 dump. 그동안 다른 명령 멈춤. **운영 금지**. |
| `BGSAVE` | `fork()` 로 자식 프로세스 만들어 백그라운드 dump. 부모는 정상 서비스. |

```
127.0.0.1:6379> BGSAVE
Background saving started
127.0.0.1:6379> LASTSAVE
(integer) 1714056789      # 마지막 BGSAVE 성공 unix timestamp
127.0.0.1:6379> INFO persistence
# Persistence
loading:0
rdb_changes_since_last_save:0
rdb_bgsave_in_progress:0
rdb_last_save_time:1714056789
rdb_last_bgsave_status:ok
rdb_last_bgsave_time_sec:1
...
```

---

## 3. fork() + Copy-on-Write

`BGSAVE` 직후:
1. `fork()` → 자식 프로세스 생성 (메모리 페이지를 부모와 **공유**, 실제 복제 없음).
2. 자식이 .rdb 파일 작성 (느려도 OK, 부모는 신경 안 씀).
3. 부모가 어떤 페이지를 **수정** 하면 → OS 가 그 페이지만 복제 (Copy-on-Write).
4. 자식은 fork 시점의 메모리 스냅샷을 그대로 보고 dump.

```
[부모 메모리] ← fork 시점에 자식과 공유
                 │
                 │ 부모가 페이지 P를 수정
                 ▼
[페이지 P 복제]   ← OS가 P만 따로 복사
                 │
                 ▼
[자식 메모리] = fork 시점의 P + 다른 모든 페이지 (공유)
```

### CoW의 함정

`BGSAVE` 동안 부모가 메모리 절반을 수정하면 → **메모리 사용량이 거의 두 배** 가 될 수 있다.
**peak memory** 추정 시 RDB-in-progress 까지 고려해야 함.

> 출처: <https://redis.io/docs/latest/operate/oss_and_stack/management/persistence/#snapshotting>
> 참고 부분: "fork" + "COW" 단락 — 본 절 근거

---

## 4. save 정책

`redis.conf`:
```
save 3600 1 300 100 60 10000
```

해석:
- **3600초(1시간)** 동안 **1개 이상** 변경되면 BGSAVE
- **300초(5분)** 동안 **100개 이상** 변경되면 BGSAVE
- **60초** 동안 **10000개 이상** 변경되면 BGSAVE

조건 중 **하나라도** 충족되면 트리거.

비활성화:
```
save ""
```

---

## 5. 디스크 동작

```
dir /data
dbfilename dump.rdb
rdbcompression yes      # LZF 압축 (CPU 약간 쓰지만 디스크/네트워크 절약)
rdbchecksum yes         # CRC64 체크섬 (loading 시 검증)
```

작성 절차:
1. 자식이 `temp-<pid>.rdb` 에 작성
2. 완료 후 `rename(temp, dump.rdb)` — atomic.
3. 부모가 손상된 .rdb 를 보지 않음.

---

## 6. 디스크 가득 / IO 에러 정책

```
stop-writes-on-bgsave-error yes
```

- `yes` (기본): BGSAVE 실패 시 모든 쓰기 명령 거부 (안전).
- `no`: 실패해도 계속 쓰기 (데이터 손실 위험; 학습용 redis.conf는 `no`).

운영에서는 `yes` + 알람 설정 권장.

---

## 7. 디버깅 / 점검 명령

```
DEBUG RELOAD             # 메모리 → RDB → 다시 메모리 로딩 (검증)
DEBUG CHANGE-REPL-ID     # 복제 ID 변경 (실험용)
INFO persistence         # RDB / AOF 모든 통계
LASTSAVE                 # 마지막 BGSAVE timestamp
```

---

## 8. 흔한 함정

| 함정 | 설명 |
|---|---|
| **`SAVE` 명령** | 운영에서 절대 금지. 단일 스레드 멈춤. |
| **save 정책 너무 자주** | 대용량 DB에서 fork 자체가 무거움. 너무 자주면 부담. |
| **save 정책 너무 드물게** | 손실 가능 데이터 시간 ↑. 백업 빈도와 일치. |
| **CoW 메모리 버스트** | `maxmemory` 의 절반 정도로 잡지 않으면 BGSAVE 중 OOM 가능. |
| **공유 디스크에 .rdb** | NFS 등에서 atomic rename 보장 안 될 수 있음. 로컬 디스크 권장. |

---

## 9. 직접 해보기

1. `BGSAVE` 실행 → `INFO persistence` 에서 `rdb_last_bgsave_time_sec` 확인.
2. seed-data.sh 실행 후 BGSAVE → `docker compose exec redis ls -lh /data/dump.rdb`.
3. `docker compose down` 후 `docker compose up -d` → 키가 살아 있는지.
4. `save ""` 적용 후 변경 → `LASTSAVE` 가 안 변하는지.
5. `redis-cli --rdb /tmp/snapshot.rdb` 로 호스트로 RDB 파일 가져오기.

---

## 10. 참고 자료

- **[공식 문서] Redis Persistence**
  - URL: <https://redis.io/docs/latest/operate/oss_and_stack/management/persistence/>
  - 참고 부분: Snapshotting 섹션 + "RDB advantages/disadvantages" — §1, §3 근거

- **[공식 문서] BGSAVE / SAVE / LASTSAVE**
  - URL: <https://redis.io/docs/latest/commands/bgsave/>
  - 참고 부분: 동작 정의 — §2 근거

- **[GitHub] redis/redis — src/rdb.c (8.6)**
  - URL: <https://github.com/redis/redis/blob/8.6/src/rdb.c>
  - 참고 부분: `rdbSaveBackground`, `rdbSave` 함수 — §3 fork + atomic rename 근거
