#!/usr/bin/env bash
# ==============================================================================
# Redis 학습 데이터 초기화 스크립트
# ------------------------------------------------------------------------------
# 안전을 위해 두 가지 모드를 지원한다:
#
#   1) 기본 (안전): demo:* 키만 삭제
#      ./scripts/reset.sh
#
#   2) 전체 초기화 (위험!): 현재 DB의 모든 키 삭제 (FLUSHDB)
#      ./scripts/reset.sh --all
#
#   3) 모든 DB 초기화 (가장 위험): FLUSHALL
#      ./scripts/reset.sh --everything
#
# 학습 환경 외에서는 절대 사용하지 말 것.
# ==============================================================================

set -euo pipefail

REDIS_HOST="${REDIS_HOST:-127.0.0.1}"
REDIS_PORT="${REDIS_PORT:-6379}"
CLI="redis-cli -h ${REDIS_HOST} -p ${REDIS_PORT}"

MODE="${1:-pattern}"

# 연결 확인
if ! ${CLI} PING > /dev/null 2>&1; then
    echo "ERROR: cannot reach Redis at ${REDIS_HOST}:${REDIS_PORT}" >&2
    exit 1
fi

case "${MODE}" in
    "" | "pattern")
        echo "==> demo:* 키 삭제 중..."
        # SCAN + DEL 조합 (KEYS 명령은 운영에선 절대 쓰지 말 것)
        # --scan은 cursor 기반으로 안전하게 순회한다.
        COUNT=$(${CLI} --scan --pattern 'demo:*' | wc -l | tr -d ' ')
        if [ "${COUNT}" -gt 0 ]; then
            ${CLI} --scan --pattern 'demo:*' | xargs -L 100 ${CLI} DEL > /dev/null
        fi
        echo "==> ${COUNT} 개 키 삭제 완료."
        ;;
    "--all")
        echo "WARNING: 현재 DB의 모든 키를 삭제합니다. 5초 안에 Ctrl+C 로 취소하세요."
        sleep 5
        ${CLI} FLUSHDB
        echo "==> FLUSHDB 완료."
        ;;
    "--everything")
        echo "WARNING: 모든 DB(0~15)의 모든 키를 삭제합니다. 5초 안에 Ctrl+C 로 취소하세요."
        sleep 5
        ${CLI} FLUSHALL
        echo "==> FLUSHALL 완료."
        ;;
    *)
        echo "Usage: $0 [pattern|--all|--everything]" >&2
        exit 2
        ;;
esac
