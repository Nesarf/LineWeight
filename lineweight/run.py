"""Running a generated script in the application, and proving it ran.

**The hard part is not the launch, it is the honesty.** A drawing application opens a window, runs the script, and
then sits there; "the process started" therefore says nothing about whether the drawing was built. So the generated
script writes a completion sentinel as its last act, and this module waits for the sentinel rather than for the
process. A script that throws halfway writes no sentinel, and the failure surfaces as a timeout with the report
beside it -- not as a cheerful success, which is the mistake this library has made often enough to write down.

**It will not close an application the user already had open.** Illustrator holds unsaved work, and a tool that kills
it to read its own exit code is a tool that loses somebody's drawing. Whether an instance existed is recorded before
launching, and only an instance this module started is closed afterwards. If an instance was already running, the
script is handed to that one and left alone.
"""
from __future__ import annotations

import os
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path as FsPath

# Where the application lives on this machine, and how to ask for a different one. The environment variable wins,
# because a path baked into a library is a path that is wrong on the next machine -- including this one, after an
# upgrade moves 2024 to 2025.
ILLUSTRATOR_ENV = 'LINEWEIGHT_ILLUSTRATOR'
ILLUSTRATOR_DEFAULT = r'D:\Ai\Adobe Illustrator 2024\Support Files\Contents\Windows\Illustrator.exe'
ANIMATE_ENV = 'LINEWEIGHT_ANIMATE'
ANIMATE_DEFAULT = r'D:\Anmt\Adobe Animate 2024\Animate.exe'

# Illustrator takes ~10-20s to become ready on this machine; the drawing itself is instant by comparison.
DEFAULT_TIMEOUT = 180.0


def illustrator_path() -> str:
    return os.environ.get(ILLUSTRATOR_ENV) or ILLUSTRATOR_DEFAULT


def animate_path() -> str:
    return os.environ.get(ANIMATE_ENV) or ANIMATE_DEFAULT


def _tasklist(exe_name: str) -> list[int]:
    """PIDs of a running image, by name. `tasklist` rather than a library, for the same reason the rest of this
    project draws with the standard library: it is one call, and it works on the machine that exists.

    **`errors='replace'` is not decoration.** `tasklist` writes its output in the console codepage, which on this
    machine is a Chinese codepage: decoding it as UTF-8 raises inside the reader thread and leaves `stdout` as `None`,
    so the failure arrives as `'NoneType' has no attribute 'splitlines'` -- an error about Python, in a place whose
    job is to ask Windows a question about a process. The bytes are irrelevant here; only the PIDs matter.
    """
    try:
        out = subprocess.run(['tasklist', '/fi', 'IMAGENAME eq %s' % exe_name, '/fo', 'csv', '/nh'],
                             capture_output=True, text=True, errors='replace', timeout=30)
    except (OSError, subprocess.SubprocessError):
        return []
    if not out.stdout:
        return []
    pids: list[int] = []
    for line in out.stdout.splitlines():
        parts = [p.strip('"') for p in line.split('","')]
        if len(parts) >= 2 and parts[0].lower() == exe_name.lower():
            try:
                pids.append(int(parts[1]))
            except ValueError:
                continue
    return pids


@dataclass
class RunResult:
    """What happened, in enough detail to decide whether to believe it."""
    ok: bool
    returncode: int | None = None
    seconds: float = 0.0
    report: str = ''
    sentinel_seen: bool = False
    spawned: bool = False
    closed: bool = False
    message: str = ''
    artifacts: list[str] = field(default_factory=list)

    def describe(self) -> str:
        head = 'ok' if self.ok else 'FAILED'
        return '%s in %.1fs%s%s' % (
            head, self.seconds,
            ' (report follows)' if self.report else '',
            '' if self.ok else ' -- %s' % self.message if self.message else '')


def run_jsx(jsx: str, script_path: str | FsPath, report_path: str | FsPath | None = None,
            sentinel_path: str | FsPath | None = None, app_path: str | None = None,
            timeout: float = DEFAULT_TIMEOUT, close_when_done: bool = True) -> RunResult:
    """Writes `jsx` to `script_path` and runs it in Illustrator, waiting for the sentinel rather than the process.

    The script is written before launching because the application reads it from disk as a file argument; there is no
    pipe to feed it through, and pretending otherwise would produce a bridge that works only in a test.
    """
    script = FsPath(script_path)
    script.parent.mkdir(parents=True, exist_ok=True)
    script.write_text(jsx, encoding='utf-8', newline='\n')

    exe = app_path or illustrator_path()
    if not FsPath(exe).exists():
        return RunResult(ok=False, message='application not found: %s' % exe)

    sentinel = FsPath(sentinel_path) if sentinel_path else None
    if sentinel and sentinel.exists():
        sentinel.unlink()

    exe_name = FsPath(exe).name
    already = _tasklist(exe_name)
    started = time.time()
    try:
        process = subprocess.Popen([exe, str(script)], close_fds=True)
    except OSError as exc:
        return RunResult(ok=False, message='could not start %s: %s' % (exe, exc))

    result = RunResult(ok=False, spawned=not already)
    result.message = 'launched %s (pid %d); %d instance(s) already running' % (exe_name, process.pid, len(already))
    # **An instance that was already running may swallow the script instead of running it.** Measured: with a stale
    # Illustrator left behind by an earlier run, the launch hands the file to that instance and nothing executes --
    # the report is never written and the wait runs to its full timeout, which reads as "the script is broken" when
    # the truth is "the application was already open". Saying so at the start costs nothing and saves the timeout.
    if already:
        result.message += (' -- warning: an existing instance may not run the script; close it for a reliable run')
    seen = False
    try:
        while time.time() - started < timeout:
            if sentinel is None:
                if process.poll() is not None:
                    seen = True
                    break
            elif sentinel.exists():
                seen = True
                break
            time.sleep(0.5)
        result.seconds = time.time() - started
        result.sentinel_seen = seen
        result.returncode = process.poll()
        if report_path and FsPath(report_path).exists():
            result.report = FsPath(report_path).read_text(encoding='utf-8', errors='replace')
        result.ok = seen and 'ALL_OK' in result.report
        if not result.ok:
            alive = process.poll() is None
            if not seen:
                result.message = ('no completion sentinel in %.0fs; %s process %s; report file %s'
                                  % (timeout, exe_name,
                                     'still running' if alive else 'exited with %s' % result.returncode,
                                     '%d bytes' % len(result.report) if result.report else 'never written'))
            elif 'error=' in result.report:
                result.message = 'script reported an error: %s' % _error_line(result.report)
            else:
                result.message = 'script finished without confirming ALL_OK'
    finally:
        # Only an instance this module started may be closed. One that was already running belongs to somebody.
        if result.spawned and close_when_done:
            try:
                process.kill()
                result.closed = True
            except OSError:
                pass
            result.spawned = False
    return result


def open_in_animate(path: str | FsPath, app_path: str | None = None, wait: float = 45.0,
                    expect_title: bool = True) -> RunResult:
    """Opens a drawing in Animate. No script, because Animate has no scriptable entry point.

    This is the whole Animate bridge: Animate opens a generated XFL and presents it as a document. It is deliberately
    *not* a fake automation layer over a menu that cannot be driven -- the measured state of Animate on this machine is
    that JSFL cannot be launched, COM refuses out-of-process creation, the UI Automation tree is empty, a background
    process cannot take focus, and it opens the home screen for an SVG. Anything that looked like driving Animate
    would be a lie with a click hidden inside it.

    **Point it at the marker file, not the folder.** An XFL is a folder with a file inside it named after the project
    and containing `PROXY-CS5`; handing Animate the folder gets the home screen, and handing it that file gets the
    document. This was established by controlled experiment against a document Animate saved itself, after sixteen
    hand-written skeletons had failed for reasons that turned out to be two layers of the same mistake.

    **Process hygiene is part of the function, not the caller's problem.** Measured: killing Animate with a hard
    process kill leaves it in a state where the *next* launch silently ignores its file argument -- which made an
    earlier sweep report a known-good file as un-openable and sent the search for a fault into the wrong layer for two
    rounds. So the wait here is for the window title to actually change, and a caller that has an instance open is
    told rather than silently left with a stale window.
    """
    target = FsPath(path)
    if target.is_dir():
        # a folder was given: the document is the marker file inside it, named after the folder
        marker = target / (target.name if target.name.lower().endswith('.xfl') else target.name + '.xfl')
        if not marker.exists():
            return RunResult(ok=False, message='no marker file in %s -- an XFL is a folder plus this file' % target)
        target = marker
    if not target.exists():
        return RunResult(ok=False, message='nothing to open: %s' % target)
    exe = app_path or animate_path()
    if not FsPath(exe).exists():
        return RunResult(ok=False, message='application not found: %s' % exe)

    already = _tasklist('Animate.exe')
    # **Record what the window says before launching, or a stale document reports itself as this run's success.**
    # Measured: with an earlier document still open, this returned `ok` after 0.3 seconds because the title already
    # matched -- a bridge that lies in exactly the way this project keeps being caught by.
    title_before = _window_title('Animate.exe')
    started = time.time()
    try:
        subprocess.Popen([exe, str(target)], close_fds=True)
    except OSError as exc:
        return RunResult(ok=False, message='could not start %s: %s' % (exe, exc))

    wanted = target.name.lower()
    deadline = time.time() + wait
    title = ''
    while time.time() < deadline:
        time.sleep(1.0)
        title = _window_title('Animate.exe')
        if not title:
            continue
        if title.lower() == (title_before or '').lower():
            continue                      # unchanged from before the launch: not evidence of anything
        if not expect_title or wanted in title.lower():
            break
    result = RunResult(ok=bool(title and title.lower() != (title_before or '').lower()
                               and (not expect_title or wanted in title.lower())),
                       seconds=time.time() - started, spawned=not already)
    result.artifacts = [str(target)]
    if result.ok:
        result.message = 'opened in Animate as "%s"' % title
    elif title and title.lower() == (title_before or '').lower():
        result.message = ('the window still says %r, which is what it said before the launch: the document did not '
                          'open' % title)
    else:
        result.message = ('Animate window title stayed %r after %.0fs, so the document did not open'
                          % (title or '(none)', wait))
    return result


def _window_title(exe_name: str) -> str:
    """The main window title of a running image, which is how a document-open is confirmed without a screenshot.

    `tasklist` cannot report a window title, so this asks through PowerShell's process view. The cost is a process
    launch per poll, which is why the poll interval is a second rather than a millisecond.
    """
    script = ("Get-Process %s -ErrorAction SilentlyContinue | Where-Object { $_.MainWindowHandle -ne 0 } | "
              "Select-Object -First 1 -ExpandProperty MainWindowTitle" % FsPath(exe_name).stem)
    try:
        out = subprocess.run(['powershell', '-NoProfile', '-Command', script],
                             capture_output=True, text=True, errors='replace', timeout=30)
    except (OSError, subprocess.SubprocessError):
        return ''
    return (out.stdout or '').strip()


def _error_line(report: str) -> str:
    for line in report.splitlines():
        if 'error=' in line:
            return line.strip()
    return report.strip().splitlines()[-1] if report.strip() else '(no report)'


def run_jsfl_manual(jsfl: str, script_path: str | FsPath) -> tuple[str, str]:
    """Animate cannot be driven from a command line, so the honest interface is a prepared script and instructions.

    Verified, rather than assumed: `Animate.exe script.jsfl` opens the file as a document instead of running it, the
    registered `FlashFactory` refuses out-of-process creation, and a JSFL in `Configuration/Commands` does not run
    when a document opens. What remains is Animate's own Commands menu, which is a user's click -- so the script is
    written where Animate will list it, and the caller is told where that is.
    """
    target = FsPath(script_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(jsfl, encoding='utf-8', newline='\n')
    note = ('Animate has no scriptable entry point. Open Animate and run this from the Commands menu: %s'
            % target)
    return str(target), note
