# 01. redis-benchmark

> **학습 목표**: 내장 `redis-benchmark` 으로 RPS / latency를 측정하고 옵션의 의미를 안다. 파이프라이닝, 명령별 비교, CSV 출력으로 자동화.
> **예상 소요**: 20분

---

## 1. 가장 단순한 사용

```bash
redis-benchmark
```

기본값: `-h 127.0.0.1 -p 6379 -n 100000 -c 50 -P 1`
- `-n 100000` : 명령 횟수
- `-c 50`     : 동시 클라이언트 수
- `-P 1`      : 파이프라이닝 (1 = off)

출력 (요약):
```
SET: 105263.16 requests per second, p50=0.247 msec
GET: 109649.12 requests per second, p50=0.231 msec
INCR: ...
```

---

## 2. 자주 쓰는 옵션

```
-t SET,GET,INCR       # 측정할 명령 한정 (기본은 많은 명령 다 돌림)
-n 1000000            # 명령 100만
-c 100                # 동시 100
-P 16                 # 파이프라이닝 16
-d 100                # 페이로드 크기 (byte) — 큰 값 SET 시
-r 1000000            # 키를 1~1M 무작위로 (캐시 효과 분산)
--csv                 # 결과를 CSV로
-q                    # quiet 모드 (요약만)
-l                    # loop (무한)
--threads 4           # benchmark 자체를 멀티스레드로 (Redis 6+)
```

---

## 3. 파이프라이닝 효과 측정

```bash
redis-benchmark -t SET -n 200000 -c 50 -P 1 -q
# SET: 105000 requests per second

redis-benchmark -t SET -n 200000 -c 50 -P 16 -q
# SET: 1500000 requests per second   ← 10배+
```

이유: RTT 1번에 16개 명령 → 네트워크 왕복 비용이 거의 사라짐.

---

## 4. 페이로드 크기의 영향

```bash
for d in 16 64 256 1024 4096 16384; do
  redis-benchmark -t SET -d $d -n 100000 -q
done
```

큰 값일수록 throughput 떨어지지만 latency는 천천히 증가.

---

## 5. CSV로 결과 모으기

```bash
redis-benchmark -t SET,GET,INCR -n 100000 -c 50 -P 1 --csv > result.csv
cat result.csv
# "SET","105000.00"
# "GET","109000.00"
# "INCR","108000.00"
```

CI에서 회귀 감지에 좋다.

---

## 6. Latency 분포

```bash
redis-benchmark -t SET -n 100000 -q --precision 3
```

각 명령 결과에 `p50, p95, p99` 가 포함:
```
SET: 105263.16 requests per second, p50=0.247 msec p95=0.512 msec p99=1.023 msec
```

대부분의 운영 SLO는 p99 기준이므로 p50보다 p99에 주목.

---

## 7. 컨테이너 안에서 실행

호스트에 redis-cli/redis-benchmark가 없으면:
```bash
docker compose exec redis redis-benchmark -t SET,GET -n 100000 -q
```

또는 본 프로젝트의 `scripts/benchmark.sh`:
```bash
N=200000 C=100 PIPELINE=16 ./scripts/benchmark.sh
```

---

## 8. 흔한 함정

| 함정 | 설명 |
|---|---|
| 같은 키만 SET → cache hit 100% | `-r 1000000` 으로 키 분산 |
| -P 너무 큰 값 | latency 상승, 처리량은 더 안 올라감 (꺽이는 지점 찾기) |
| 클라이언트 한 대로 측정 | 실제 production은 여러 호스트. memtier_benchmark 권장 |
| Docker for Mac 의 네트워크 오버헤드 | 결과를 production 수치로 일반화하지 말 것 |
| CPU 다 안 씀 | `--threads 4` 또는 멀티 클라이언트 |

---

## 9. 직접 해보기

1. `-P 1` vs `-P 16` 으로 SET 측정 → 차이 비율.
2. `-d 16, 256, 4096` 으로 페이로드 영향 측정.
3. `--csv` 로 결과 저장 → 셸 스크립트로 RPS 차이 자동 계산.
4. seed-data.sh 후 GET 측정 (실제 데이터 있는 상태).

---

## 10. 참고 자료

- **[공식 문서] redis-benchmark**
  - URL: <https://redis.io/docs/latest/operate/oss_and_stack/management/optimization/benchmarks/>
  - 참고 부분: 옵션 표 — §2 근거

- **[공식 문서] Pipelining**
  - URL: <https://redis.io/docs/latest/develop/use/pipelining/>
  - 참고 부분: RTT 절약 설명 — §3 근거
