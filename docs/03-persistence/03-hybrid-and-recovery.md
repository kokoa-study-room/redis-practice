# 03. 혼합 모드 + 복구 시나리오

> **학습 목표**: RDB + AOF 둘 다 켰을 때 어떻게 동작하는지, 재시작 시 우선순위, 흔한 복구 시나리오 4가지를 처리할 수 있다.
> **예상 소요**: 20분

---

## 1. 둘 다 켰을 때

```
appendonly yes
save 3600 1 300 100 60 10000
aof-use-rdb-preamble yes
```

- 평상 시: 두 가지 동시에 디스크 작성.
- AOF rewrite 시: 베이스에 RDB 형식 사용 (preamble) + 그 후 incr는 일반 명령.

### 재시작 시 우선순위

> **AOF가 켜져 있고 AOF 파일이 존재하면, AOF로 복구한다 (RDB 무시).**

이유: AOF가 더 최신 (손실 적음).

> 출처: <https://redis.io/docs/latest/operate/oss_and_stack/management/persistence/#interactions-between-aof-and-rdb-persistence>
> 참고 부분: "If both are enabled, only the AOF will be loaded" 단락

---

## 2. 시나리오 1 — 의도적 재시작

```bash
docker compose down
# 이 시점에 dump.rdb / appendonlydir 모두 디스크에 있음
docker compose up -d
# AOF 켜져 있으면 AOF replay → 모든 키 복원
```

**소요**: AOF 크기 + multi-part 베이스 RDB 부분 디코드 시간.

---

## 3. 시나리오 2 — 비정상 종료 (kill -9 / 정전)

```bash
docker compose kill redis      # SIGKILL
# 일부 명령이 fsync 안 된 상태로 잘릴 수 있음
docker compose up -d
```

가능한 결과:
- `appendfsync everysec`: 최대 1초 분량 손실 가능.
- `appendfsync always`: 거의 0초.
- AOF 마지막 명령이 잘려서 형식 오류 → 재시작 실패.

복구:
```
redis-check-aof --fix appendonlydir/appendonly.aof.X.incr.aof
```

---

## 4. 시나리오 3 — RDB만 살아있을 때

AOF 파일이 손상돼서 복구 불가능 / 의도적으로 AOF 비활성:
```
appendonly no
```
이 상태로 재시작 → `dump.rdb` 로 복구.
**손실 가능 시간**: 마지막 BGSAVE 이후 변경.

---

## 5. 시나리오 4 — 다른 인스턴스로 데이터 옮기기

```bash
# 1) 소스에서 BGSAVE
redis-cli BGSAVE
redis-cli LASTSAVE   # 완료 확인

# 2) dump.rdb 복사
scp /data/dump.rdb dest:/data/dump.rdb

# 3) 대상 인스턴스에 dump.rdb 두고 시작
# (AOF는 비워둠 또는 same dir 비움)
docker compose up -d
```

또는 호스트 redis-cli로 추출:
```bash
redis-cli -h source --rdb /tmp/snap.rdb
```

---

## 6. 데이터 마이그레이션 — 단일 키

```
DUMP key                 # 직렬화된 binary 반환
RESTORE key 0 "<binary>" # 다른 곳에 복원
```

```python
data = src.dump("user:1001")
dst.restore("user:1001", 0, data)
```

---

## 7. 백업 정책 권장

| 시나리오 | 정책 |
|---|---|
| 캐시 (손실 OK) | RDB만, save 빈도 적게 |
| 일반 앱 | RDB + AOF everysec |
| 금융 / 결제 직접 | AOF always (성능 비용 감수) — 그래도 RDBMS와 병행 권장 |
| 비용 민감 | RDB만 + 외부 백업 schedule (S3 등) |

---

## 8. 흔한 함정

| 함정 | 설명 |
|---|---|
| AOF가 살아있는데 RDB만 복원 시도 | Redis는 AOF를 먼저 봄. AOF 파일을 비우거나 appendonly no 변경. |
| `dump.rdb` 만 복사하고 `appendonlydir` 안 비움 | AOF가 빈 상태라 정상 / AOF가 옛 데이터면 충돌 |
| Apple Silicon ↔ x86 RDB 호환 | RDB는 architecture-independent (자체 직렬화). 호환됨. |
| `redis-check-rdb` 무시 | 로딩 실패 시 `--check-rdb` 또는 `redis-check-rdb` 로 진단. |

---

## 9. 직접 해보기

1. seed-data.sh 후 BGSAVE → `dump.rdb` 크기.
2. `docker compose down` → 호스트 `docker/redis/data/` 디렉토리 살펴보기.
3. AOF 켜고 50개 SET → `appendonlydir/` 안의 파일들 (manifest, base, incr).
4. `BGREWRITEAOF` 후 파일 변화 (새 base 생성).
5. (모험) AOF 끝 5바이트 임의 잘라내기 → 재시작 실패 → `redis-check-aof --fix` 로 복구.

---

## 10. 참고 자료

- **[공식 문서] Persistence — Interactions between AOF and RDB**
  - URL: <https://redis.io/docs/latest/operate/oss_and_stack/management/persistence/>
  - 참고 부분: "If both are enabled, only the AOF will be loaded" — §1 근거

- **[공식 문서] DUMP / RESTORE**
  - URL: <https://redis.io/docs/latest/commands/dump/>, `/restore/`
  - 참고 부분: 직렬화 형식 호환성 — §6 근거

- **[GitHub] redis/redis — src/rdb.c, src/aof.c**
  - URL: <https://github.com/redis/redis/tree/8.6/src>
  - 참고 부분: 로딩 우선순위 코드 — §1 근거
