"""Reference: docs/09-patterns/03-distributed-lock-redlock.md

분산 락 — SET NX EX + Lua 안전 해제. 두 워커가 같은 락을 잡으려 할 때.
"""
import sys, threading, time, uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from _common import get_client, section  # noqa: E402

RELEASE = """
if redis.call('GET', KEYS[1]) == ARGV[1] then
    return redis.call('DEL', KEYS[1])
else
    return 0
end
"""


def acquire(r, name, ttl=5):
    token = str(uuid.uuid4())
    if r.set(f"lock:{name}", token, nx=True, ex=ttl):
        return token
    return None


def release(r, name, token):
    return r.eval(RELEASE, 1, f"lock:{name}", token)


def worker(name, hold_sec):
    r = get_client()
    print(f"[{name}] acquire 시도")
    token = acquire(r, "shared-resource", ttl=10)
    if not token:
        print(f"[{name}] FAIL — 누군가 잡고 있음")
        return
    print(f"[{name}] OK — {hold_sec}초 hold")
    time.sleep(hold_sec)
    released = release(r, "shared-resource", token)
    print(f"[{name}] release returned {released}")


def main():
    r = get_client()
    r.delete("lock:shared-resource")

    with section("두 워커가 동시에 같은 락 잡으려 시도"):
        t1 = threading.Thread(target=worker, args=("worker-A", 1), daemon=True)
        t2 = threading.Thread(target=worker, args=("worker-B", 1), daemon=True)
        t1.start()
        time.sleep(0.05)
        t2.start()
        t1.join()
        t2.join()

    with section("순차 실행 — 첫 락 해제 후 두 번째 성공"):
        t1 = threading.Thread(target=worker, args=("worker-A", 0.3), daemon=True)
        t1.start()
        t1.join()
        worker("worker-B", 0.3)

    r.delete("lock:shared-resource")


if __name__ == "__main__":
    main()
