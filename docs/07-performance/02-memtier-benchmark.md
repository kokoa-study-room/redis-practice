# 02. memtier_benchmark

> **학습 목표**: Redis Inc. 의 `memtier_benchmark` 가 redis-benchmark보다 풍부한 부하 시나리오를 어떻게 표현하는지, ratio / key-pattern 옵션 활용.
> **예상 소요**: 20분

---

## 1. 왜 추가 도구가 필요한가?

`redis-benchmark` 은 단순. 실제 부하는 **혼합 명령 (read 8 : write 2)**, **다양한 키/값 분포**, **장시간** 등 복합적.

`memtier_benchmark` (Redis Inc. 공식):
- read/write ratio
- 여러 데이터 유형 동시
- key/value pattern (sequential / random / Gaussian)
- TLS / Cluster / Sentinel 지원
- 멀티 스레드

---

## 2. 설치 (Docker)

```bash
docker pull redislabs/memtier_benchmark:latest

# 실행
docker run --rm --network host redislabs/memtier_benchmark \
  -s 127.0.0.1 -p 6379 \
  --ratio=1:10 --key-maximum=1000000 \
  -t 4 -c 10 --test-time=30
```

또는 Cluster compose 같은 네트워크에서:
```bash
docker run --rm --network redis-cluster-learning_cluster-net \
  redislabs/memtier_benchmark \
  -s cluster-node-1 -p 7001 --cluster-mode -t 4 -c 10
```

---

## 3. 핵심 옵션

| 옵션 | 의미 | 예 |
|---|---|---|
| `-t` | thread 수 | `-t 4` |
| `-c` | thread당 connection | `-c 10` |
| `--ratio=set:get` | write:read 비율 | `--ratio=1:10` (1 write : 10 read) |
| `--key-maximum` | 사용할 키 범위 | `--key-maximum=1000000` |
| `--key-pattern` | 키 분포 (R=random, S=sequential, G=Gaussian) | `--key-pattern=R:R` |
| `--data-size` | 값 크기 | `--data-size=1024` |
| `--data-size-range` | 범위 | `--data-size-range=64-512` |
| `--test-time` | 시간 (초) | `--test-time=60` |
| `--requests` | 총 명령 수 | `--requests=1000000` |
| `--cluster-mode` | Cluster | |
| `--print-percentiles` | latency 분포 | `--print-percentiles=50,95,99,99.9` |

> 출처: <https://github.com/RedisLabs/memtier_benchmark>

---

## 4. 시나리오 예

### 4.1 캐시 워크로드 (read 95%)

```bash
docker run --rm --network host redislabs/memtier_benchmark \
  -s 127.0.0.1 -p 6379 \
  --ratio=1:19 \
  --data-size=512 \
  --key-maximum=10000000 \
  --key-pattern=R:R \
  -t 4 -c 25 \
  --test-time=60 \
  --print-percentiles=50,95,99,99.9
```

### 4.2 큐 워크로드 (write 위주)

```bash
docker run --rm --network host redislabs/memtier_benchmark \
  -s 127.0.0.1 -p 6379 \
  --ratio=10:1 \
  --data-size=200 \
  -t 4 -c 25 \
  --test-time=30
```

### 4.3 Cluster 부하

```bash
docker run --rm --network host redislabs/memtier_benchmark \
  -s 127.0.0.1 -p 7001 --cluster-mode \
  --ratio=1:10 -t 4 -c 25 --test-time=60
```

---

## 5. 결과 해석

```
Type      Ops/sec   Hits/sec   Misses/sec   Avg.Lat(msec)   p50.Lat   p99.Lat   KB/sec
Sets      10,234    -          -            0.245           0.190     0.610     5,120
Gets      102,678   95,134     7,544        0.232           0.180     0.580     51,344
Totals    112,912   ...        ...          ...             ...       ...       ...
```

- **Hits/sec vs Misses/sec** : 캐시 히트율 (실제 키가 있는 비율)
- **p50 / p99** : 지연 분포
- **KB/sec** : 네트워크 throughput

---

## 6. redis-benchmark vs memtier 비교

| 항목 | redis-benchmark | memtier_benchmark |
|---|---|---|
| 설치 | Redis 패키지에 포함 | 별도 (Docker 권장) |
| 혼합 ratio | -t 로 명령 셋만 | `--ratio` 정밀 |
| 키 분포 | 단순 random | sequential/random/Gaussian |
| Cluster | 일부 지원 | 잘 됨 |
| 결과 | 텍스트 / CSV | 자세한 표 / 통계 |
| 학습 곡선 | 짧음 | 중간 |

---

## 7. 흔한 함정

| 함정 | 설명 |
|---|---|
| key-maximum 너무 작음 | 모든 부하가 같은 키에 집중 → cache hit 비현실적 |
| 클라이언트 호스트 부하 한계 | benchmark가 CPU 한계에 도달하면 Redis 부하가 측정 안 됨. 다른 호스트에서 실행 |
| Cluster mode 빠뜨림 | MOVED 리다이렉트 처리 못해 결과 왜곡 |
| `--test-time` 너무 짧음 | warmup 끝나기도 전에 종료. 60초+ 권장 |

---

## 8. 직접 해보기

1. ratio=1:10, 1:1, 10:1 세 가지로 같은 시간 → throughput 차이.
2. `--data-size` 64 / 1024 / 8192 → 큰 값일수록 throughput 떨어지는지.
3. Cluster compose 띄운 후 `--cluster-mode` 부하 → 단일 노드 대비 throughput.
4. `--print-percentiles` 결과의 p99.9 vs p50 비율 (안정성 지표).

---

## 9. 참고 자료

- **[GitHub] RedisLabs/memtier_benchmark**
  - URL: <https://github.com/RedisLabs/memtier_benchmark>
  - 참고 부분: README의 옵션 설명 — §3 근거

- **[공식 블로그] Performance benchmarking using memtier**
  - URL: <https://redis.io/blog/redis-benchmarking-tools-comparison/>
  - 참고 부분: redis-benchmark 와의 비교 — §6 근거 (없으면 RedisLabs/memtier_benchmark README의 비교 단락 참고)
