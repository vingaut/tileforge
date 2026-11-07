"""Pile d'annulation (undo/redo) fondée sur des instantanés du projet."""

from __future__ import annotations


class History:
    """Historique d'annulation par instantanés.

    Chaque action appelle :meth:`begin` avant de modifier le projet puis
    :meth:`commit` après.  Un instantané n'est empilé que si l'état a
    réellement changé, ce qui évite les entrées vides.
    """

    def __init__(self, project_getter, on_change=None, limit: int = 200):
        self._get = project_getter
        self._on_change = on_change
        self._limit = limit
        self.undo_stack: list[tuple[str, dict]] = []
        self.redo_stack: list[tuple[str, dict]] = []
        self._pending: dict | None = None
        self._pending_label = ""

    # -- cycle d'une action -------------------------------------------------

    def begin(self, label: str = "") -> None:
        project = self._get()
        if project is None:
            return
        if self._pending is not None:
            return          # une action est déjà en cours
        self._pending = project.snapshot()
        self._pending_label = label

    def commit(self, label: str = "") -> None:
        project = self._get()
        if project is None or self._pending is None:
            return
        current = project.snapshot()
        if current != self._pending:
            self.undo_stack.append((label or self._pending_label or "action",
                                    self._pending))
            if len(self.undo_stack) > self._limit:
                self.undo_stack.pop(0)
            self.redo_stack.clear()
        self._pending = None
        self._pending_label = ""
        self._notify()

    def cancel(self) -> None:
        self._pending = None

    # -- navigation ---------------------------------------------------------

    def can_undo(self) -> bool:
        return bool(self.undo_stack)

    def can_redo(self) -> bool:
        return bool(self.redo_stack)

    def undo(self) -> bool:
        project = self._get()
        if project is None or not self.undo_stack:
            return False
        label, snap = self.undo_stack.pop()
        self.redo_stack.append((label, project.snapshot()))
        project.restore(snap)
        self._notify()
        return True

    def redo(self) -> bool:
        project = self._get()
        if project is None or not self.redo_stack:
            return False
        label, snap = self.redo_stack.pop()
        self.undo_stack.append((label, project.snapshot()))
        project.restore(snap)
        self._notify()
        return True

    def clear(self) -> None:
        self.undo_stack.clear()
        self.redo_stack.clear()
        self._pending = None
        self._notify()

    def last_label(self) -> str:
        return self.undo_stack[-1][0] if self.undo_stack else ""

    def _notify(self) -> None:
        if self._on_change:
            self._on_change()
