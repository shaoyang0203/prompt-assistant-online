"""Preview task records only; no preference learning or legacy imports."""
import copy
import json
import os
import re
from contextlib import contextmanager
from pathlib import Path
from uuid import uuid4
from contracts import ROOT, ContractError, encode, read_json, require

# 运行数据只允许落在技能源码之外；这里只保护包自身，不假设任何本机目录结构。
PROTECTED = [ROOT]

class Store:
    def __init__(self, root):
        self.root = Path(root).expanduser().resolve()
        require(not any(self.root == p.resolve() or self.root.is_relative_to(p.resolve())
                        for p in PROTECTED), "运行数据不得写入源码或受保护目录")

    def folder(self, task_id):
        require(type(task_id) is str and re.fullmatch(r"[A-Za-z0-9_-]{1,80}", task_id), "任务 ID 无效")
        return self.root / "tasks" / task_id

    @contextmanager
    def lock(self):
        self.root.mkdir(parents=True, exist_ok=True)
        path = self.root / ".writer.lock"
        try:
            handle = path.open("x", encoding="utf-8")
        except FileExistsError as exc:
            raise ContractError("数据目录正在写入或有遗留锁；核实进程后处理，不自动抢锁") from exc
        try:
            with handle:
                handle.write(str(os.getpid()))
            yield
        finally:
            path.unlink()

    def exists(self, task_id):
        return (self.folder(task_id) / "CURRENT").exists()

    def load(self, task_id):
        folder = self.folder(task_id)
        pointer = (folder / "CURRENT").read_text(encoding="utf-8").strip()
        require(re.fullmatch("[0-9a-f]{32}", pointer), "CURRENT 损坏")
        state = read_json(folder / "snapshots" / (pointer + ".json"))
        require(state.get("data_version") == 1 and state.get("task_id") == task_id, "任务数据版本或 ID 无效")
        return state

    def _publish(self, task_id, state):
        folder = self.folder(task_id)
        snapshots = folder / "snapshots"
        snapshots.mkdir(parents=True, exist_ok=True)
        token = uuid4().hex
        target = snapshots / (token + ".json")
        with target.open("xb") as handle:
            handle.write(encode(state))
            handle.flush()
            os.fsync(handle.fileno())
        require(read_json(target) == state, "新快照写后核验失败")
        pointer = folder / ("pointer-" + token + ".tmp")
        with pointer.open("xb") as handle:
            handle.write(token.encode("ascii"))
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(pointer, folder / "CURRENT")
        # Publication is the commit point; do not report a later cosmetic check as failed save.

    def create(self, task_id, state):
        with self.lock():
            require(not self.exists(task_id), "任务已存在，不覆盖")
            folder = self.folder(task_id)
            require(not folder.exists() or not any(folder.iterdir()), "存在未完成创建的任务目录，需检查恢复")
            self._publish(task_id, copy.deepcopy(state))
        return {"saved": True, "task_id": task_id}

    def update(self, task_id, action):
        with self.lock():
            original = self.load(task_id)
            state = copy.deepcopy(original)
            result = action(state)
            if state != original:
                self._publish(task_id, state)
        return result

