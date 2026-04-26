"""Reference: docs/01-data-types/05-sorted-set.md, docs/09-patterns/04-leaderboard.md

ZSET 으로 게임 리더보드. TOP-N, 순위, 주변 ±N명, sliding window.
"""
import sys, time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from _common import get_client, section  # noqa: E402

KEY = "lb:demo"


def main():
    r = get_client()
    r.delete(KEY)

    with section("ZADD — 점수 추가"):
        r.zadd(KEY, {
            "alice": 1500,
            "bob": 2300,
            "carol": 980,
            "dave": 1875,
            "eve": 2750,
        })
        print("ZCARD =", r.zcard(KEY))

    with section("TOP 3 (내림차순)"):
        for rank, (player, score) in enumerate(
            r.zrange(KEY, 0, 2, desc=True, withscores=True), start=1
        ):
            print(f"{rank}. {player:>6} : {int(score):>5}")

    with section("alice 순위 + 주변 ±2명"):
        rank = r.zrevrank(KEY, "alice")
        print("alice 등수:", rank + 1)
        neighbors = r.zrange(KEY, max(0, rank - 2), rank + 2, desc=True, withscores=True)
        for r_, (p, s) in enumerate(neighbors, start=max(0, rank - 2) + 1):
            arrow = " ← me" if p == "alice" else ""
            print(f"{r_}. {p:>6} : {int(s):>5}{arrow}")

    with section("ZINCRBY — alice 점수 +500"):
        r.zincrby(KEY, 500, "alice")
        print("alice score:", r.zscore(KEY, "alice"))
        print("새 등수:", r.zrevrank(KEY, "alice") + 1)

    with section("ZADD GT — 새 점수가 더 클 때만"):
        r.zadd(KEY, {"bob": 100}, gt=True)
        print("bob score (변화 없어야 함):", r.zscore(KEY, "bob"))

    with section("TOP-N 자동 유지 — 상위 3만 남기기"):
        # 하위(0~카드-N-1) 제거
        r.zremrangebyrank(KEY, 0, -4)
        print("남은 멤버:", r.zrange(KEY, 0, -1, desc=True, withscores=True))

    with section("Sliding window 카운터 (rate limit 패턴)"):
        win_key = "rl:user:1"
        r.delete(win_key)
        now = time.time()
        for i in range(5):
            r.zadd(win_key, {f"req-{i}-{now+i*0.1}": now + i * 0.1})
        # 60초 윈도 안의 요청 수
        r.zremrangebyscore(win_key, 0, now - 60)
        print("최근 60초 요청 수:", r.zcard(win_key))
        r.delete(win_key)

    with section("정리"):
        r.delete(KEY)
        print("done.")


if __name__ == "__main__":
    main()
