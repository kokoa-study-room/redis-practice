#!/usr/bin/env bash
# ==============================================================================
# Redis 학습용 초기 데이터 적재 스크립트
# ------------------------------------------------------------------------------
# 사용법:
#   ./scripts/seed-data.sh              # 호스트 redis-cli로 접속 (127.0.0.1:6379)
#   REDIS_HOST=redis ./scripts/seed-data.sh   # 다른 호스트 사용
#
# 또는 docker compose 환경에서:
#   docker compose exec redis sh -c "$(cat scripts/seed-data.sh)"
#
# 적재 데이터:
#   - String   : user:1:name, counter:visits
#   - List     : queue:tasks (5개 항목)
#   - Hash     : product:1001 (name, price, stock)
#   - Set      : tags:python (5 태그)
#   - SortedSet: leaderboard:weekly (5명, 점수)
#   - Stream   : events:signup (3 entry)
#
# 모든 키에 prefix "demo:" 를 붙여 reset.sh 에서 일괄 삭제 가능하게 한다.
# ==============================================================================

set -euo pipefail

REDIS_HOST="${REDIS_HOST:-127.0.0.1}"
REDIS_PORT="${REDIS_PORT:-6379}"

CLI="redis-cli -h ${REDIS_HOST} -p ${REDIS_PORT}"

echo "==> seed: ${REDIS_HOST}:${REDIS_PORT}"

# 연결 확인
if ! ${CLI} PING > /dev/null 2>&1; then
    echo "ERROR: cannot reach Redis at ${REDIS_HOST}:${REDIS_PORT}" >&2
    echo "Hint: 'docker compose -f docker/docker-compose.yml up -d' 먼저 실행했나요?" >&2
    exit 1
fi

# ---- String ----
${CLI} SET demo:user:1:name "김철수"
${CLI} SET demo:counter:visits 0
${CLI} INCRBY demo:counter:visits 42

# ---- List ----
${CLI} DEL demo:queue:tasks > /dev/null
${CLI} RPUSH demo:queue:tasks "task-1" "task-2" "task-3" "task-4" "task-5"

# ---- Hash ----
${CLI} DEL demo:product:1001 > /dev/null
${CLI} HSET demo:product:1001 \
    name "기계식 키보드" \
    price 159000 \
    stock 24

# ---- Set ----
${CLI} DEL demo:tags:python > /dev/null
${CLI} SADD demo:tags:python "asyncio" "redis" "fastapi" "uv" "ruff"

# ---- Sorted Set (leaderboard) ----
${CLI} DEL demo:leaderboard:weekly > /dev/null
${CLI} ZADD demo:leaderboard:weekly \
    1500 "alice" \
    2300 "bob" \
    980  "carol" \
    1875 "dave" \
    2750 "eve"

# ---- Stream ----
${CLI} DEL demo:events:signup > /dev/null
${CLI} XADD demo:events:signup '*' user_id 100 plan free
${CLI} XADD demo:events:signup '*' user_id 101 plan pro
${CLI} XADD demo:events:signup '*' user_id 102 plan free

echo "==> done. 키 개수:"
${CLI} --scan --pattern 'demo:*' | wc -l
echo "==> RedisInsight (http://localhost:5540) 에서 'demo:' prefix로 필터링해 확인 가능."
