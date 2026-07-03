"""Background SFTP worker: a sequential job queue running over the SSH transport."""
from __future__ import annotations

import queue
import stat
import threading
from dataclasses import dataclass
from typing import Callable, List, Optional

import paramiko
from PyQt6.QtCore import QThread, pyqtSignal


@dataclass
class SftpEntry:
    name: str
    size: int
    mtime: float
    is_dir: bool
    is_link: bool
    mode: int


class SftpWorker(QThread):
    listed = pyqtSignal(str, list)             # path, List[SftpEntry]
    error = pyqtSignal(str)
    transfer_started = pyqtSignal(str)
    transfer_progress = pyqtSignal(str, int, int)  # label, transferred, total
    transfer_finished = pyqtSignal(str)
    operation_done = pyqtSignal()               # mkdir/rename/delete completed -> refresh

    def __init__(self, transport_provider: Callable[[], paramiko.Transport], parent=None) -> None:
        super().__init__(parent)
        self._transport_provider = transport_provider
        self._queue: "queue.Queue[Optional[tuple]]" = queue.Queue()
        self._stop = threading.Event()
        self._sftp: Optional[paramiko.SFTPClient] = None

    def run(self) -> None:
        try:
            transport = self._transport_provider()
            self._sftp = paramiko.SFTPClient.from_transport(transport)
        except Exception as exc:  # noqa: BLE001
            self.error.emit(f"Could not open SFTP session: {exc}")
            return

        while not self._stop.is_set():
            try:
                job = self._queue.get(timeout=0.3)
            except queue.Empty:
                continue
            if job is None:
                break
            func, args = job
            try:
                func(*args)
            except Exception as exc:  # noqa: BLE001
                self.error.emit(str(exc))

        try:
            self._sftp.close()
        except Exception:
            pass

    def stop(self) -> None:
        self._stop.set()
        self._queue.put(None)

    def _submit(self, func: Callable, *args) -> None:
        self._queue.put((func, args))

    # -- public job API (called from the GUI thread) ----------------------
    def list_dir(self, path: str) -> None:
        self._submit(self._job_list, path)

    def download(self, remote_path: str, local_path: str) -> None:
        self._submit(self._job_download, remote_path, local_path)

    def upload(self, local_path: str, remote_path: str) -> None:
        self._submit(self._job_upload, local_path, remote_path)

    def mkdir(self, path: str) -> None:
        self._submit(self._job_mkdir, path)

    def delete(self, path: str, is_dir: bool) -> None:
        self._submit(self._job_delete, path, is_dir)

    def rename(self, old_path: str, new_path: str) -> None:
        self._submit(self._job_rename, old_path, new_path)

    # -- jobs (run on the worker thread) -----------------------------------
    def _job_list(self, path: str) -> None:
        entries: List[SftpEntry] = []
        for attr in self._sftp.listdir_attr(path):
            mode = attr.st_mode or 0
            entries.append(SftpEntry(
                name=attr.filename,
                size=attr.st_size or 0,
                mtime=attr.st_mtime or 0,
                is_dir=stat.S_ISDIR(mode),
                is_link=stat.S_ISLNK(mode),
                mode=mode,
            ))
        entries.sort(key=lambda e: (not e.is_dir, e.name.lower()))
        self.listed.emit(path, entries)

    def _job_download(self, remote_path: str, local_path: str) -> None:
        self.transfer_started.emit(remote_path)
        self._sftp.get(remote_path, local_path,
                        callback=lambda done, total: self.transfer_progress.emit(remote_path, done, total))
        self.transfer_finished.emit(remote_path)

    def _job_upload(self, local_path: str, remote_path: str) -> None:
        self.transfer_started.emit(local_path)
        self._sftp.put(local_path, remote_path,
                        callback=lambda done, total: self.transfer_progress.emit(local_path, done, total))
        self.transfer_finished.emit(local_path)
        self.operation_done.emit()

    def _job_mkdir(self, path: str) -> None:
        self._sftp.mkdir(path)
        self.operation_done.emit()

    def _job_delete(self, path: str, is_dir: bool) -> None:
        if is_dir:
            self._sftp.rmdir(path)
        else:
            self._sftp.remove(path)
        self.operation_done.emit()

    def _job_rename(self, old_path: str, new_path: str) -> None:
        self._sftp.rename(old_path, new_path)
        self.operation_done.emit()
