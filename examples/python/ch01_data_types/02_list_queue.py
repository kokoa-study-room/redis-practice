"""Reference: docs/01-data-types/02-list.md

List를 양방향 큐로 사용. RPUSH/LPOP, BLPOP 블로킹, LTRIM 으로 길이 제한, LMOVE 신뢰성 큐.
"""
import sys, threading, time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from _common import get_client, section  # noqa: E402


def main():
    r = get_client()

    with section("RPUSH / LPOP — FIFO 큐"):
        r.delete("jobs")
        r.rpush("jobs", "task-1", "task-2", "task-3")
        print("LLEN =", r.llen("jobs"))
        while True:
            job = r.lpop("jobs")
            if not job:
                break
            print("처리:", job)

    with section("LPUSH / LRANGE — 최근 N개 로그"):
        r.delete("log")
        for i in range(20):
            r.lpush("log", f"event-{i}")
        r.ltrim("log", 0, 9)
        print("최근 10개:", r.lrange("log", 0, -1))

    with section("BLPOP — 블로킹 (다른 스레드가 push 할 때까지 대기)"):
        r.delete("waitq")

        def producer():
            time.sleep(0.5)
            r.rpush("waitq", "delayed-task")

        threading.Thread(target=producer, daemon=True).start()
        result = r.blpop("waitq", timeout=3)
        print("BLPOP returned:", result)

    with section("LMOVE — 신뢰성 큐 (src → dst, 양쪽 atomic 이동)"):
        r.delete("src", "processing")
        r.rpush("src", "a", "b", "c")
        item = r.lmove("src", "processing", "LEFT", "RIGHT")
        print("이동:", item, "| processing =", r.lrange("processing", 0, -1))
        # 처리 후 ack: LREM 으로 1개 제거
        r.lrem("processing", 1, item)
        print("ack 후 processing =", r.lrange("processing", 0, -1))

    with section("정리"):
        r.delete("jobs", "log", "waitq", "src", "processing")
        print("done.")


if __name__ == "__main__":
    main()
