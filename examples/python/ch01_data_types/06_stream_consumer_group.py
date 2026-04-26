"""Reference: docs/01-data-types/06-stream.md, docs/04-pubsub-streams/03-streams-consumer-group.md

Stream + Consumer Group. 두 컨슈머가 메시지를 분배 받아 처리.
"""
import sys, threading, time
from pathlib import Path

import redis  # noqa: F401

sys.path.insert(0, str(Path(__file__).parent.parent))
from _common import get_client, section  # noqa: E402

STREAM = "demo:tasks"
GROUP = "workers"


def consume(consumer_name: str, max_msgs: int = 5):
    r = get_client()
    consumed = 0
    while consumed < max_msgs:
        resp = r.xreadgroup(
            groupname=GROUP, consumername=consumer_name,
            streams={STREAM: ">"}, count=1, block=2000,
        )
        if not resp:
            break
        for _stream, entries in resp:
            for entry_id, fields in entries:
                print(f"[{consumer_name}] got {entry_id} :: {fields}")
                r.xack(STREAM, GROUP, entry_id)
                consumed += 1
    print(f"[{consumer_name}] consumed {consumed} done")


def main():
    r = get_client()
    r.delete(STREAM)

    try:
        r.xgroup_create(STREAM, GROUP, id="0", mkstream=True)
    except redis.exceptions.ResponseError:
        pass

    with section("프로듀서가 10개 메시지 추가"):
        for i in range(10):
            r.xadd(STREAM, {"task": f"job-{i}"})
        print("XLEN =", r.xlen(STREAM))

    with section("두 컨슈머 동시 실행 — 메시지 분배"):
        t1 = threading.Thread(target=consume, args=("worker-A", 5), daemon=True)
        t2 = threading.Thread(target=consume, args=("worker-B", 5), daemon=True)
        t1.start(); t2.start()
        t1.join(timeout=10); t2.join(timeout=10)

    with section("그룹 상태"):
        info = r.xinfo_groups(STREAM)
        for g in info:
            print(g)

    with section("정리"):
        r.delete(STREAM)
        print("done.")


if __name__ == "__main__":
    main()
