#!/usr/bin/env python3
"""
Example module demonstrating various Python patterns.
This should be classified as HEALTHY since it's legitimate code.
"""

import os
import sys
from typing import List, Optional, Dict, Any
from dataclasses import dataclass
from enum import Enum, auto


class Status(Enum):
    """Enumeration of possible processing states."""
    PENDING = auto()
    RUNNING = auto()
    COMPLETED = auto()
    FAILED = auto()


@dataclass
class Task:
    """Represents a processing task with metadata."""
    task_id: str
    name: str
    status: Status = Status.PENDING
    result: Optional[Any] = None
    
    def complete(self, result: Any) -> None:
        """Mark task as completed with result."""
        self.status = Status.COMPLETED
        self.result = result
    
    def fail(self, error: str) -> None:
        """Mark task as failed with error message."""
        self.status = Status.FAILED
        self.result = {"error": error}


class TaskProcessor:
    """Processes tasks in a queue-based system."""
    
    def __init__(self, max_workers: int = 4):
        self.max_workers = max_workers
        self.tasks: Dict[str, Task] = {}
        self._counter = 0
    
    def submit(self, name: str) -> str:
        """Submit a new task and return its ID."""
        self._counter += 1
        task_id = f"task_{self._counter:06d}"
        self.tasks[task_id] = Task(task_id=task_id, name=name)
        return task_id
    
    def get_status(self, task_id: str) -> Optional[Status]:
        """Get current status of a task."""
        task = self.tasks.get(task_id)
        return task.status if task else None
    
    def process_all(self) -> List[str]:
        """Process all pending tasks and return completed IDs."""
        completed = []
        for task_id, task in self.tasks.items():
            if task.status == Status.PENDING:
                try:
                    result = self._execute(task)
                    task.complete(result)
                    completed.append(task_id)
                except Exception as e:
                    task.fail(str(e))
        return completed
    
    def _execute(self, task: Task) -> Any:
        """Execute a single task. Override in subclasses."""
        return {"processed": task.name}


def main():
    """Main entry point for demonstration."""
    processor = TaskProcessor(max_workers=2)
    
    # Submit some tasks
    ids = [
        processor.submit("analyze_data"),
        processor.submit("generate_report"),
        processor.submit("send_notification"),
    ]
    
    # Process and display results
    completed = processor.process_all()
    
    for task_id in ids:
        task = processor.tasks[task_id]
        print(f"{task_id}: {task.status.name} -> {task.result}")


if __name__ == "__main__":
    main()
