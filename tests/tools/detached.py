"""Start an application outside this session's process tree, so stopping the session cannot stop it.

The problem: a program launched from here is a descendant of the shell that launched it, and Windows tears down a
process tree with its root. Interrupting a task therefore closed the application being driven -- which makes driving a
long-starting application impossible, because the wait is longer than a task is allowed to run.

`start` and a background job do not fix this. A child is still a child, and the tree is still the unit that gets killed.

What does fix it: hand the launch to the Task Scheduler, which is a Windows service running in its own session. A task
started there has no parent in this process tree at all, so nothing that happens here -- a timeout, an interrupt, the
whole session ending -- reaches it. The task is removed once it has run, so nothing accumulates.
"""
from __future__ import annotations

import os
import subprocess
import time
import uuid


def launch_detached(executable: str, arguments: str = '', working_directory: str = '') -> int:
    """Start a program under the Task Scheduler and return its process id, or 0.

    The process id is found by looking for the executable afterwards rather than from the task, because the scheduler
    does not report it and a task can finish its own launch before the program has finished starting.
    """
    name = 'lineweight-launch-%s' % uuid.uuid4().hex[:10]
    before = _running(executable)
    command = '"%s"' % executable if not arguments else '"%s" %s' % (executable, arguments)
    made = subprocess.run(['schtasks', '/Create', '/TN', name, '/TR', command,
                           '/SC', 'ONCE', '/ST', '00:00', '/F'],
                          capture_output=True, text=True, errors='replace')
    if made.returncode != 0:
        return 0
    try:
        subprocess.run(['schtasks', '/Run', '/TN', name], capture_output=True, text=True, errors='replace')
        # the task is only needed for the launch itself
        for _ in range(20):
            time.sleep(1)
            now = _running(executable)
            fresh = now - before
            if fresh:
                return sorted(fresh)[0]
    finally:
        subprocess.run(['schtasks', '/Delete', '/TN', name, '/F'], capture_output=True, text=True, errors='replace')
    return 0


def _running(executable: str) -> set[int]:
    image = os.path.basename(executable)
    got = subprocess.run(['tasklist', '/FI', 'IMAGENAME eq %s' % image, '/FO', 'CSV', '/NH'],
                         capture_output=True, text=True, errors='replace')
    pids = set()
    for line in (got.stdout or '').splitlines():
        parts = line.split(',')
        if len(parts) > 1 and image.lower() in parts[0].lower():
            try:
                pids.add(int(parts[1].strip('"')))
            except ValueError:
                continue
    return pids


def kill_all(executable: str) -> int:
    """Stop every instance, by image name, so a stale one cannot be mistaken for a fresh launch."""
    image = os.path.basename(executable)
    subprocess.run(['taskkill', '/F', '/IM', image], capture_output=True, text=True, errors='replace')
    time.sleep(2)
    return len(_running(executable))
