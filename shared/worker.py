"""
shared/worker.py
----------------

Base worker class for threaded operations with progress tracking.
Provides a common pattern for all tool workers.

Usage:
    from shared import BaseWorker, WorkerState

    class MyWorker(BaseWorker):
        def do_work(self):
            items = self.collect_items()
            for i, item in enumerate(items):
                if self.should_stop():
                    break
                self.process_item(item)
                self.emit_progress((i + 1) / len(items), f"Processing {item}")
            
            self.emit_done({"processed": len(items)})
"""

import os
import threading
from queue import Queue
from enum import Enum, auto
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import (
    Any, 
    Callable, 
    Dict, 
    Iterator, 
    List, 
    Optional, 
    Tuple, 
    TypeVar,
    Generic,
)
from dataclasses import dataclass, field

from .scanner import (
    iter_files_chunked,
    collect_files_chunked,
    DEFAULT_CHUNK_SIZE,
)


# ------------------------------------------------------------
# Worker State Enum
# ------------------------------------------------------------
class WorkerState(Enum):
    """Possible states of a worker thread."""
    IDLE = auto()
    SCANNING = auto()
    PROCESSING = auto()
    STOPPING = auto()
    DONE = auto()
    ERROR = auto()


# ------------------------------------------------------------
# Progress Info Dataclass
# ------------------------------------------------------------
@dataclass
class ProgressInfo:
    """Container for progress information."""
    fraction: float = 0.0
    message: str = ""
    current: int = 0
    total: int = 0
    phase: str = ""
    extra: Dict[str, Any] = field(default_factory=dict)


# ------------------------------------------------------------
# Base Worker Thread
# ------------------------------------------------------------
T = TypeVar('T')  # Type for work items


class BaseWorker(threading.Thread, Generic[T]):
    """
    Base class for threaded workers with progress reporting.
    
    Subclasses should override:
        - do_work(): Main work logic
        
    Progress is emitted via queue messages:
        ("state", WorkerState)
        ("progress", ProgressInfo)
        ("scan_progress", (chunk_count, total_files))
        ("log", message)
        ("done", result_dict)
        ("error", error_message)
    """
    
    def __init__(
        self,
        settings: Dict[str, Any],
        queue: Optional[Queue] = None,
        logger: Optional[Any] = None,
    ):
        super().__init__()
        self.settings = settings
        self.queue = queue
        self.logger = logger
        
        self.state = WorkerState.IDLE
        self._stop_requested = threading.Event()
        self._progress_lock = threading.Lock()
        
        # Stats tracking
        self.stats: Dict[str, Any] = {}
        
        # Thread pool settings
        self.thread_count = settings.get("THREAD_COUNT", os.cpu_count() or 4)
        self.chunk_size = settings.get("CHUNK_SIZE", DEFAULT_CHUNK_SIZE)
    
    # --------------------------------------------------------
    # Stop Control
    # --------------------------------------------------------
    def request_stop(self):
        """Request the worker to stop gracefully."""
        self._stop_requested.set()
        self._set_state(WorkerState.STOPPING)
    
    def should_stop(self) -> bool:
        """Check if stop has been requested."""
        return self._stop_requested.is_set()
    
    # --------------------------------------------------------
    # State Management
    # --------------------------------------------------------
    def _set_state(self, state: WorkerState):
        """Update worker state and emit to queue."""
        self.state = state
        self.emit("state", state)
    
    # --------------------------------------------------------
    # Queue Communication
    # --------------------------------------------------------
    def emit(self, kind: str, payload: Any):
        """Emit a message to the queue."""
        if self.queue:
            self.queue.put((kind, payload))
    
    def emit_progress(
        self,
        fraction: float,
        message: str = "",
        current: int = 0,
        total: int = 0,
        phase: str = "",
        **extra,
    ):
        """Emit progress update."""
        info = ProgressInfo(
            fraction=fraction,
            message=message,
            current=current,
            total=total,
            phase=phase,
            extra=extra,
        )
        self.emit("progress", info)
    
    def emit_log(self, message: str):
        """Emit log message and optionally write to logger."""
        self.emit("log", message)
        if self.logger:
            self.logger.log(message)
    
    def emit_done(self, result: Optional[Dict[str, Any]] = None):
        """Emit completion with results."""
        self._set_state(WorkerState.DONE)
        self.emit("done", result or self.stats)
    
    def emit_error(self, error: str):
        """Emit error message."""
        self._set_state(WorkerState.ERROR)
        self.emit("error", error)
        if self.logger:
            self.logger.log(f"ERROR: {error}")
    
    # --------------------------------------------------------
    # Scanning Helpers
    # --------------------------------------------------------
    def scan_directory(
        self,
        root: str,
        as_path: bool = True,
    ) -> List[Any]:
        """
        Scan directory with chunked collection and progress updates.
        
        Args:
            root: Directory to scan
            as_path: If True, return Path objects; if False, return strings
            
        Returns:
            List of all file paths
        """
        self._set_state(WorkerState.SCANNING)
        self.emit_log(f"Scanning directory: {root}")
        
        def on_chunk(chunk, total_so_far):
            self.emit("scan_progress", (len(chunk), total_so_far))
            self.emit_progress(
                fraction=0.0,  # Unknown total during scan
                message=f"Scanning... found {total_so_far} files",
                current=total_so_far,
                total=0,
                phase="scan",
            )
        
        files = collect_files_chunked(
            root,
            chunk_size=self.chunk_size,
            callback=on_chunk,
            as_path=as_path,
        )
        
        self.emit_log(f"Found {len(files)} files")
        return files
    
    def iter_directory_chunked(
        self,
        root: str,
        as_path: bool = True,
    ) -> Iterator[List[Any]]:
        """
        Iterator for chunked directory scanning.
        Useful for streaming processing without holding all paths in memory.
        
        Args:
            root: Directory to scan
            as_path: If True, yield Path objects; if False, yield strings
            
        Yields:
            Chunks of file paths
        """
        self._set_state(WorkerState.SCANNING)
        self.emit_log(f"Scanning directory: {root}")
        
        total = 0
        for chunk in iter_files_chunked(root, self.chunk_size, as_path=as_path):
            total += len(chunk)
            self.emit("scan_progress", (len(chunk), total))
            yield chunk
    
    # --------------------------------------------------------
    # Parallel Processing Helpers
    # --------------------------------------------------------
    def process_parallel(
        self,
        items: List[T],
        process_func: Callable[[T], Any],
        description: str = "Processing",
    ) -> List[Tuple[T, Any, Optional[Exception]]]:
        """
        Process items in parallel using ThreadPoolExecutor.
        
        Args:
            items: List of items to process
            process_func: Function to call for each item
            description: Description for progress messages
            
        Returns:
            List of (item, result, exception) tuples
        """
        self._set_state(WorkerState.PROCESSING)
        total = len(items)
        results = []
        processed = 0
        
        with ThreadPoolExecutor(max_workers=self.thread_count) as executor:
            futures = {executor.submit(process_func, item): item for item in items}
            
            for future in as_completed(futures):
                if self.should_stop():
                    executor.shutdown(wait=False, cancel_futures=True)
                    break
                
                item = futures[future]
                processed += 1
                
                try:
                    result = future.result()
                    results.append((item, result, None))
                except Exception as e:
                    results.append((item, None, e))
                    self.emit_log(f"Error processing {item}: {e}")
                
                with self._progress_lock:
                    self.emit_progress(
                        fraction=processed / total,
                        message=f"{description} {processed}/{total}",
                        current=processed,
                        total=total,
                        phase="process",
                    )
        
        return results
    
    def process_parallel_chunked(
        self,
        items: List[T],
        process_func: Callable[[T], Any],
        batch_callback: Optional[Callable[[List[Tuple[T, Any]]], None]] = None,
        batch_size: int = 100,
        description: str = "Processing",
    ) -> List[Tuple[T, Any, Optional[Exception]]]:
        """
        Process items in parallel with batch callbacks.
        Useful for periodic database commits or other batch operations.
        
        Args:
            items: List of items to process
            process_func: Function to call for each item
            batch_callback: Called with successful results every batch_size items
            batch_size: Number of items per batch callback
            description: Description for progress messages
            
        Returns:
            List of (item, result, exception) tuples
        """
        self._set_state(WorkerState.PROCESSING)
        total = len(items)
        all_results = []
        batch_results = []
        processed = 0
        
        with ThreadPoolExecutor(max_workers=self.thread_count) as executor:
            futures = {executor.submit(process_func, item): item for item in items}
            
            for future in as_completed(futures):
                if self.should_stop():
                    executor.shutdown(wait=False, cancel_futures=True)
                    break
                
                item = futures[future]
                processed += 1
                
                try:
                    result = future.result()
                    all_results.append((item, result, None))
                    batch_results.append((item, result))
                except Exception as e:
                    all_results.append((item, None, e))
                    self.emit_log(f"Error processing {item}: {e}")
                
                # Batch callback
                if batch_callback and len(batch_results) >= batch_size:
                    batch_callback(batch_results)
                    batch_results = []
                
                with self._progress_lock:
                    self.emit_progress(
                        fraction=processed / total,
                        message=f"{description} {processed}/{total}",
                        current=processed,
                        total=total,
                        phase="process",
                    )
            
            # Final batch
            if batch_callback and batch_results:
                batch_callback(batch_results)
        
        return all_results
    
    # --------------------------------------------------------
    # Thread Entry Point
    # --------------------------------------------------------
    def run(self):
        """Thread entry point. Override do_work() instead of this."""
        try:
            self._set_state(WorkerState.PROCESSING)
            self.do_work()
            if self.state != WorkerState.ERROR:
                self.emit_done()
        except Exception as e:
            self.emit_error(str(e))
    
    def do_work(self):
        """
        Override this method with your work logic.
        
        Use helpers:
            - self.scan_directory(root) - scan with progress
            - self.process_parallel(items, func) - parallel processing
            - self.emit_progress(...) - update progress
            - self.emit_log(...) - log messages
            - self.should_stop() - check for stop request
        """
        raise NotImplementedError("Subclasses must implement do_work()")


# ------------------------------------------------------------
# Simple Function-Based Worker
# ------------------------------------------------------------
class FunctionWorker(BaseWorker):
    """
    Worker that executes a provided function.
    Useful for simple one-off operations.
    
    Usage:
        def my_task(worker):
            files = worker.scan_directory("/path")
            for f in files:
                worker.emit_log(f"Processing {f}")
            return {"count": len(files)}
        
        worker = FunctionWorker(
            settings={},
            queue=my_queue,
            work_func=my_task,
        )
        worker.start()
    """
    
    def __init__(
        self,
        settings: Dict[str, Any],
        queue: Optional[Queue] = None,
        logger: Optional[Any] = None,
        work_func: Optional[Callable[['FunctionWorker'], Any]] = None,
    ):
        super().__init__(settings, queue, logger)
        self.work_func = work_func
        self.result = None
    
    def do_work(self):
        if self.work_func:
            self.result = self.work_func(self)
            if isinstance(self.result, dict):
                self.stats.update(self.result)
