"""Reference: docs/04-pubsub-streams/01-pubsub.md

Pub/Sub: subscribe / publish 별도 connection.
"""
import sys, threading, time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from _common import get_client, section  # noqa: E402


def listener(channel: str, n_msgs: int):
    r = get_client()
    ps = r.pubsub()
    ps.subscribe(channel)
    seen = 0
    for msg in ps.listen():
        if msg["type"] == "subscribe":
            print(f"[sub] subscribed to {msg['channel']}")
            continue
        if msg["type"] == "message":
            print(f"[sub] got: {msg['data']}")
            seen += 1
            if seen >= n_msgs:
                ps.unsubscribe(channel)
                break


def main():
    r = get_client()

    with section("Pub/Sub — 5개 메시지"):
        t = threading.Thread(target=listener, args=("news", 5), daemon=True)
        t.start()
        time.sleep(0.3)  # subscriber가 준비될 시간
        for i in range(5):
            count = r.publish("news", f"breaking-{i}")
            print(f"[pub] sent (received by {count} subscriber)")
            time.sleep(0.2)
        t.join(timeout=3)

    with section("PUBSUB 진단 명령"):
        # 별도 연결로 (기존 listener는 종료됨)
        print("CHANNELS:", r.pubsub_channels())
        print("NUMSUB news:", r.pubsub_numsub("news"))


if __name__ == "__main__":
    main()
