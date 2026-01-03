"""shared/task_runner.py

A small, shared subprocess runner that:
- redirects stdout/stderr to a log file
- tails that log file on a background thread (LogWatcher)
- exposes a killable handle (terminate/kill/stop)

This is designed so UIs can depend on *logs* as the single source of truth
for console output, and refresh their console panes independently.
"""

from __future__ import annotations

import os
import subprocess
import threading
import time
from dataclasses import dataclass, field
from typing import BinaryIO, Callable, List, Optional

from .log_watcher import LogWatcher


@dataclass
class KillableTask:
	argv: List[str]
	cwd: str
	log_file: str
	process: subprocess.Popen
	started_at: float

	_log_fh: Optional[BinaryIO] = None
	_watcher: Optional[LogWatcher] = None
	_done: threading.Event = field(default_factory=threading.Event)
	exit_code: Optional[int] = None

	def is_running(self) -> bool:
		return self.process.poll() is None

	def wait(self, timeout: Optional[float] = None) -> Optional[int]:
		"""Wait for the subprocess to exit; returns exit code if known."""
		try:
			self.process.wait(timeout=timeout)
		except subprocess.TimeoutExpired:
			return None
		return self.process.returncode

	def terminate(self) -> None:
		"""Request graceful termination."""
		try:
			self.process.terminate()
		except Exception:
			pass

	def kill(self) -> None:
		"""Force kill."""
		try:
			self.process.kill()
		except Exception:
			pass

	def stop(self, grace: float = 1.0) -> None:
		"""Terminate, then kill after a grace period."""
		if not self.is_running():
			return
		self.terminate()
		try:
			self.process.wait(timeout=grace)
		except Exception:
			self.kill()

	def done(self) -> bool:
		return self._done.is_set()

	def close(self) -> None:
		"""Stop watcher and close file handle (safe to call multiple times)."""
		if self._watcher:
			try:
				self._watcher.stop()
			except Exception:
				pass
			self._watcher = None

		if self._log_fh:
			try:
				self._log_fh.flush()
			except Exception:
				pass
			try:
				self._log_fh.close()
			except Exception:
				pass
			self._log_fh = None


def _default_log_dir(base_dir: str) -> str:
	return os.path.join(base_dir, ".logs")


def start_subprocess_to_log(
	argv: List[str],
	*,
	cwd: str,
	log_dir: Optional[str] = None,
	log_prefix: str = "task",
	env: Optional[dict] = None,
	threads: Optional[int] = None,
	on_line: Optional[Callable[[str], None]] = None,
	poll_interval: float = 0.05,
) -> KillableTask:
	"""Start a subprocess with stdout/stderr redirected to a log file.

	Returns a KillableTask handle immediately.

	Notes:
	- The subprocess output is the log file; consumers should read from it.
	- A LogWatcher runs on a daemon thread and can invoke `on_line`.
	"""

	if log_dir is None:
		log_dir = _default_log_dir(cwd)

	os.makedirs(log_dir, exist_ok=True)

	ts = int(time.time())
	pid = os.getpid()
	log_file = os.path.join(log_dir, f"{log_prefix}_{ts}_{pid}.log")

	# Create environment with unbuffered Python output where possible.
	merged_env = os.environ.copy()
	if env:
		merged_env.update(env)
	merged_env.setdefault("PYTHONUNBUFFERED", "1")
	merged_env["TOOLBOX_LOG_FILE"] = log_file

	# Optional thread count propagation for multithreaded tools/libraries.
	# Only set defaults if the caller didn't already specify them.
	if threads is not None:
		t = str(max(1, int(threads)))
		merged_env.setdefault("TOOLBOX_THREADS", t)
		merged_env.setdefault("OMP_NUM_THREADS", t)
		merged_env.setdefault("OPENBLAS_NUM_THREADS", t)
		merged_env.setdefault("MKL_NUM_THREADS", t)
		merged_env.setdefault("NUMEXPR_NUM_THREADS", t)
		merged_env.setdefault("VECLIB_MAXIMUM_THREADS", t)
		merged_env.setdefault("BLIS_NUM_THREADS", t)
		merged_env.setdefault("RAYON_NUM_THREADS", t)

	# Keep the file handle open for the entire subprocess lifetime.
	# Use binary to avoid encoding issues; LogWatcher reads as text with replacement.
	log_fh = open(log_file, "ab", buffering=0)

	proc = subprocess.Popen(
		argv,
		cwd=cwd,
		stdout=log_fh,
		stderr=subprocess.STDOUT,
		env=merged_env,
	)

	task = KillableTask(
		argv=list(argv),
		cwd=cwd,
		log_file=log_file,
		process=proc,
		started_at=time.time(),
		_log_fh=log_fh,
	)

	watcher = LogWatcher(log_file, poll_interval=poll_interval, on_line=on_line)
	watcher.start()
	task._watcher = watcher

	def _waiter():
		try:
			proc.wait()
			task.exit_code = proc.returncode
		finally:
			task._done.set()
			task.close()

	threading.Thread(target=_waiter, daemon=True).start()

	return task
