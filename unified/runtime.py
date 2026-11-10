"""Own module lifecycles and bounded IPC calls from the single web listener."""
import concurrent.futures
import multiprocessing
import itertools
import threading
import time
from pathlib import Path

from .registry import ROOT, SYSTEMS
from .worker import worker_main


class ModuleBusy(Exception):
    pass


class ModuleWorker:
    def __init__(self, system, app_root, origin, log_root, isolated):
        self.system = system
        self.args = (system, str(app_root), str(ROOT.parent / system["directory"]), origin,
                     str(log_root / f"{system['id']}.log"), isolated)
        self.lock = threading.Lock()
        self.pending_lock = threading.Lock()
        self.pending = {}
        self.sequence = itertools.count(1)
        self.slots = threading.BoundedSemaphore(8)
        self.process = None
        self.connection = None
        self.ready = False
        self.closed = False
        self.failures = 0
        self.last_start = 0.0

    def fail_pending(self, connection=None):
        with self.pending_lock:
            if connection is not None and self.connection is not connection:
                return
            self.ready = False
            pending, self.pending = self.pending, {}
        for future in pending.values():
            future.set_exception(ModuleBusy("Module exited; request was not replayed"))

    def start(self):
        if self.closed:
            raise RuntimeError("Application is stopping")
        if self.process and self.process.is_alive():
            return
        if self.failures and time.monotonic() - self.last_start < 5:
            raise ModuleBusy("Module restart backoff")
        if self.connection:
            self.fail_pending(self.connection)
            self.connection.close()
        context = multiprocessing.get_context("spawn")
        parent, child = context.Pipe()
        self.connection = parent
        self.process = context.Process(target=worker_main, args=(child, *self.args), name=f"myinvest-{self.system['id']}", daemon=True)
        self.ready = False
        self.last_start = time.monotonic()
        self.process.start()
        child.close()

    def receive_responses(self, connection):
        try:
            while True:
                request_id, result = connection.recv()
                with self.pending_lock:
                    future = self.pending.pop(request_id, None)
                if future:
                    future.set_result(result)
        except (EOFError, OSError):
            self.fail_pending(connection)

    def call(self, request):
        if not self.slots.acquire(timeout=8):
            raise ModuleBusy("Module is handling another request")
        try:
            with self.lock:
                self.start()
                if not self.ready:
                    if not self.connection.poll(45):
                        raise ModuleBusy("Module is still starting")
                    if self.connection.recv()[0] != "ready":
                        raise RuntimeError("Invalid startup handshake")
                    self.ready = True
                    threading.Thread(target=self.receive_responses, args=(self.connection,), daemon=True).start()
                future = concurrent.futures.Future()
                request_id = next(self.sequence)
                with self.pending_lock:
                    self.pending[request_id] = future
                try:
                    self.connection.send((request_id, request))
                except (EOFError, OSError):
                    self.fail_pending(self.connection)
                    if self.process.is_alive():
                        self.process.terminate()
                        self.process.join(timeout=5)
                    raise
            return future.result()
        except (EOFError, BrokenPipeError, OSError):
            self.ready = False
            self.failures += 1
            raise ModuleBusy("Module exited; the next request will restart it") from None
        finally:
            self.slots.release()

    def close(self):
        self.closed = True
        self.fail_pending()
        if not self.process:
            return
        if self.lock.acquire(timeout=1):
            try:
                if self.process.is_alive():
                    self.connection.send(None)
            except (OSError, EOFError):
                pass
            finally:
                self.lock.release()
        self.process.join(timeout=5)
        if self.process.is_alive():
            self.process.terminate()
            self.process.join(timeout=5)
        self.connection.close()


class ApplicationRuntime:
    def __init__(self, origin, source_root=None, isolated=False):
        self.isolated = isolated
        self.log_root = ROOT / "temp/unified" / time.strftime("%Y%m%d_%H%M%S")
        self.log_root.mkdir(parents=True, exist_ok=True)
        base = Path(source_root) if source_root else ROOT / "apps"
        self.workers = {s["id"]: ModuleWorker(s, base / s["directory"], origin, self.log_root, isolated) for s in SYSTEMS}
        self.executor = concurrent.futures.ThreadPoolExecutor(max_workers=2 * len(SYSTEMS), thread_name_prefix="module-ipc")
        self.capacity = threading.BoundedSemaphore(3 * len(SYSTEMS))
        self.closed = False

    def request(self, system_id, request, timeout=55):
        if self.closed or not self.capacity.acquire(blocking=False):
            raise ModuleBusy("Application request capacity reached")
        future = self.executor.submit(self.workers[system_id].call, request)
        future.add_done_callback(lambda _: self.capacity.release())
        # A timeout does not replay or interrupt a potentially mutating request.
        return future.result(timeout=timeout)

    def status(self):
        return {key: {"alive": bool(w.process and w.process.is_alive()), "ready": w.ready,
                      "pid": w.process.pid if w.process else None, "transport": "pipe"}
                for key, w in self.workers.items()}

    def warmup(self):
        def warm(system):
            try:
                self.request(system["id"], ("GET", system["health"], [("Host", f"{system['id']}.okbbc.com")], b""))
            except Exception:
                pass
        for system in SYSTEMS:
            threading.Thread(target=warm, args=(system,), daemon=True).start()

    def close(self):
        self.closed = True
        for worker in self.workers.values():
            worker.close()
        self.executor.shutdown(wait=True, cancel_futures=True)
