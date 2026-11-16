"""Verify graceful shutdown kills child CLI processes leaving 0 orphans."""
import os
import subprocess
import sys
import time

import psutil


def main():
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    py = sys.executable

    # Spawn a child site_crawler process directly with a long timeout
    proc = subprocess.Popen(
        [py, os.path.join(root, "cli", "site_crawler.py"), "--url", "https://example.com", "--max-pages", "10", "--timeout", "60"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    pid = proc.pid
    print(f"Spawned test child CLI process PID={pid}")
    time.sleep(0.5)

    assert psutil.pid_exists(pid), f"Process {pid} should exist"
    p = psutil.Process(pid)
    children = p.children(recursive=True)
    all_pids = [pid] + [c.pid for c in children]
    print(f"Tracking process tree PIDs: {all_pids}")

    # Import and run _kill_tree from runner
    sys.path.insert(0, os.path.join(root, "backend"))
    from app.runner import _kill_tree
    print(f"Sending termination via _kill_tree to PID {pid}...")
    _kill_tree(pid)

    # Check whether any process in all_pids is still alive
    time.sleep(1.0)
    alive = [p_id for p_id in all_pids if psutil.pid_exists(p_id)]
    print(f"Still alive PIDs: {alive}")
    if alive:
        print(f"FAIL: Orphan processes remaining: {alive}")
        sys.exit(1)
    else:
        print("PASS: 0 orphan processes remain. All child processes successfully killed.")

if __name__ == "__main__":
    main()
