"""Time-budget guard shared by crawl.py, discover.py and professors.py.

GitHub stops a job after its timeout and throws away everything that was not yet committed. A single hung
network request can also keep a thread pool alive forever. This guard
  * saves a checkpoint every `every` seconds, and
  * once the budget (+ a short grace period) is over, saves and ends the program cleanly (exit code 0),
so the "publish" step of the workflow always has fresh data to commit.
"""
import os, threading, time


def start(deadline_ts, save, grace=300, every=900):
    def watchdog():
        while True:
            time.sleep(20)
            if time.time() > deadline_ts + grace:
                print('WATCHDOG: time budget used up - saving and stopping', flush=True)
                try:
                    save()
                except Exception as ex:
                    print('final save failed:', ex, flush=True)
                os._exit(0)

    def periodic():
        while True:
            time.sleep(every)
            try:
                save()
                print('checkpoint saved', flush=True)
            except Exception as ex:
                print('checkpoint failed:', ex, flush=True)

    for f in (watchdog, periodic):
        threading.Thread(target=f, daemon=True).start()


def snapshot(obj):
    """json-safe copy of a dict that other threads may be changing"""
    import copy
    for _ in range(20):
        try:
            return copy.deepcopy(obj)
        except RuntimeError:
            time.sleep(0.05)
    return dict(obj)
