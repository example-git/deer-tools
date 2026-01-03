"""
shared
------

Shared utilities for all toolbox modules.
"""

from .scanner import (
    iter_files,
    iter_files_chunked,
    collect_files,
    collect_files_chunked,
    iter_files_filtered,
    collect_files_filtered,
    count_files,
    DEFAULT_CHUNK_SIZE,
)

from .worker import (
    BaseWorker,
    FunctionWorker,
    WorkerState,
    ProgressInfo,
)

from .log_watcher import (
    LogWatcher,
    TempLogFile,
    watch_subprocess_log,
)

from .task_runner import (
    KillableTask,
    start_subprocess_to_log,
)

from .progress import (
    draw_progress_bar,
    finish_progress,
    cli_progress,
)

from .logger import (
    BufferedLogger,
)

from .path_utils import (
    get_extension,
    ensure_directory,
    normalize_path,
    build_new_name,
    next_nonconflicting_path,
    safe_rename,
    is_zero_byte,
)

from .config import (
    get_config_dir,
    load_persistent_config,
    save_persistent_config,
    merge_settings,
    build_settings,
)

__all__ = [
    # Scanner
    "iter_files",
    "iter_files_chunked", 
    "collect_files",
    "collect_files_chunked",
    "iter_files_filtered",
    "collect_files_filtered",
    "count_files",
    "DEFAULT_CHUNK_SIZE",
    # Worker
    "BaseWorker",
    "FunctionWorker",
    "WorkerState",
    "ProgressInfo",
    # Log Watcher
    "LogWatcher",
    "TempLogFile",
    "watch_subprocess_log",
    # Task Runner
    "KillableTask",
    "start_subprocess_to_log",
    # Progress
    "draw_progress_bar",
    "finish_progress",
    "cli_progress",
    # Logger
    "BufferedLogger",
    # Path Utils
    "get_extension",
    "ensure_directory",
    "normalize_path",
    "build_new_name",
    "next_nonconflicting_path",
    "safe_rename",
    "is_zero_byte",
    # Config
    "get_config_dir",
    "load_persistent_config",
    "save_persistent_config",
    "merge_settings",
    "build_settings",

]
