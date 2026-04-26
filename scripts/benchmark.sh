#!/usr/bin/env bash
# ==============================================================================
# redis-benchmark 일괄 실행 스크립트
# ------------------------------------------------------------------------------
# 가장 자주 다뤄지는 명령들에 대해 처리량(RPS)을 측정한다.
# 결과는 stdout으로 출력되며, 학습용으로 적당한 -n / -c 값을 사용한다.
#
# 사용법:
#   ./scripts/benchmark.sh                # 기본 (n=100000, c=50)
#   N=500000 C=100 ./scripts/benchmark.sh # 더 큰 부하
#   PIPELINE=10 ./scripts/benchmark.sh    # 파이프라이닝 활성화
#
# 참고:
#   - https://redis.io/docs/latest/operate/oss_and_stack/management/optimization/benchmarks/
#   - 결과의 PCL(percentile latency) 해석법은 docs/07-performance/01-redis-benchmark.md 참고
# ==============================================================================

set -euo pipefail

REDIS_HOST="${REDIS_HOST:-127.0.0.1}"
REDIS_PORT="${REDIS_PORT:-6379}"
N="${N:-100000}"
C="${C:-50}"
PIPELINE="${PIPELINE:-1}"

# redis-benchmark 설치 확인
if ! command -v redis-benchmark > /dev/null 2>&1; then
    echo "redis-benchmark가 설치돼 있지 않습니다." >&2
    echo "Hint: docker compose exec redis redis-benchmark ... 형태로 컨테이너 안에서 실행하세요." >&2
    exit 1
fi

COMMON_OPTS="-h ${REDIS_HOST} -p ${REDIS_PORT} -n ${N} -c ${C} -P ${PIPELINE} --csv"

echo "==> Benchmark with n=${N} c=${C} pipeline=${PIPELINE}"
echo

# --csv 모드는 결과를 CSV 한 줄씩 출력하므로 사후 가공이 쉽다.
# -t 옵션으로 측정할 명령을 명시 (전체 명령 셋은 길어서 학습용으로 핵심만)
redis-benchmark ${COMMON_OPTS} -t PING,SET,GET,INCR,LPUSH,LPOP,SADD,HSET,SPOP,ZADD,LRANGE_100
