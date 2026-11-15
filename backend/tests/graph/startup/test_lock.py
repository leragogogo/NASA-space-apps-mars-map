import os
import socket
import subprocess
import sys
import threading
import time

import pytest

from app.graph.startup.lock import graph_lock


def test_the_lock_exists_only_while_held(tmp_path):
    path = tmp_path / "graph" / "graph.npz"
    with graph_lock(path) as lock:
        assert lock.is_file() and lock.name == "graph.npz.lock"
        assert lock.read_text().split()[:2] == [str(os.getpid()), socket.gethostname()]
    assert not lock.exists()


def test_the_lock_is_released_when_the_body_fails(tmp_path):
    path = tmp_path / "graph.npz"
    with pytest.raises(RuntimeError):
        with graph_lock(path):
            raise RuntimeError("build failed")
    with graph_lock(path):  # and can be taken again
        pass


def test_a_second_process_waits_until_the_first_is_done(tmp_path):
    path, order = tmp_path / "graph.npz", []

    def second():
        with graph_lock(path, poll_s=0.01):
            order.append("second")

    with graph_lock(path):
        thread = threading.Thread(target=second)
        thread.start()
        time.sleep(0.15)
        assert order == []  # still waiting
        order.append("first done")
    thread.join(5)
    assert order == ["first done", "second"]


def test_only_one_of_many_holds_it_at_a_time(tmp_path):
    path, inside, worst = tmp_path / "graph.npz", [0], [0]

    def work():
        with graph_lock(path, poll_s=0.005):
            inside[0] += 1
            worst[0] = max(worst[0], inside[0])
            time.sleep(0.01)
            inside[0] -= 1

    threads = [threading.Thread(target=work) for _ in range(8)]
    [t.start() for t in threads]
    [t.join(10) for t in threads]
    assert worst[0] == 1 and not (tmp_path / "graph.npz.lock").exists()


def test_a_lock_left_by_a_crashed_process_is_taken_over(tmp_path):
    path = tmp_path / "graph.npz"
    stale = tmp_path / "graph.npz.lock"
    stale.write_text("1 elsewhere 0\n")  # another machine: judged by age only
    old = time.time() - 4000
    os.utime(stale, (old, old))
    with graph_lock(path, timeout_s=5, poll_s=0.01, stale_after_s=1800):
        pass  # did not wait for the dead owner


def test_waiting_too_long_gives_up(tmp_path):
    path = tmp_path / "graph.npz"
    with graph_lock(path):
        with pytest.raises(TimeoutError, match="gave up waiting"):
            with graph_lock(path, timeout_s=0.1, poll_s=0.02):
                pass


def test_a_short_wait_never_steals_the_lock_of_a_live_builder(tmp_path):
    path = tmp_path / "graph.npz"
    with graph_lock(path) as lock:
        before = lock.read_text()
        with pytest.raises(TimeoutError):
            with graph_lock(path, timeout_s=0.1, poll_s=0.02, stale_after_s=1800):
                pass
        assert lock.read_text() == before  # still the original owner's lock


def _dead_pid() -> int:
    proc = subprocess.Popen([sys.executable, "-c", "pass"])
    proc.wait()
    return proc.pid  # a process that has exited: no longer running


def test_a_lock_whose_owner_was_killed_is_taken_over_at_once(tmp_path):
    path = tmp_path / "graph.npz"
    (tmp_path / "graph.npz.lock").write_text(f"{_dead_pid()} {socket.gethostname()} {time.time():.0f}\n")  # fresh, but dead
    start = time.monotonic()
    with graph_lock(path, timeout_s=5, poll_s=0.01, stale_after_s=1800):
        pass
    assert time.monotonic() - start < 2  # did not wait for the age limit


def test_a_lock_of_a_live_process_is_respected(tmp_path):
    path = tmp_path / "graph.npz"
    (tmp_path / "graph.npz.lock").write_text(f"{os.getpid()} {socket.gethostname()} {time.time():.0f}\n")
    with pytest.raises(TimeoutError):
        with graph_lock(path, timeout_s=0.1, poll_s=0.02):
            pass


def test_a_lock_from_another_machine_is_not_judged_by_its_pid(tmp_path):
    path = tmp_path / "graph.npz"
    (tmp_path / "graph.npz.lock").write_text(f"{_dead_pid()} some-other-host {time.time():.0f}\n")
    with pytest.raises(TimeoutError):  # the pid means nothing here, so it counts as held until it is old
        with graph_lock(path, timeout_s=0.1, poll_s=0.02):
            pass


def test_an_unreadable_lock_is_treated_as_held(tmp_path):
    path = tmp_path / "graph.npz"
    (tmp_path / "graph.npz.lock").write_text("garbage")
    with pytest.raises(TimeoutError):
        with graph_lock(path, timeout_s=0.1, poll_s=0.02):
            pass
