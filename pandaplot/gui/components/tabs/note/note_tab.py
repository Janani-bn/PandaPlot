"""
Note tab widget for displaying and editing notes in the main tab container.
"""

from typing import override

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QVBoxLayout,
    QWidget,
)

from pandaplot.commands.project.current_project import get_current_project
from pandaplot.gui.components.tabs.note.note_editor import NoteEditorWidget
from pandaplot.gui.core.widget_extension import PWidget
from pandaplot.models.events import NoteEvents
from pandaplot.models.events.event_types import ProjectEvents
from pandaplot.models.project.items.note import Note
from pandaplot.models.state.app_context import AppContext
from pandaplot.services.config import ConfigManager
from pandaplot.services.data_managers.project_manager import ProjectManager


class NoteTab(PWidget):
    """
    A tab widget for displaying and editing notes.
    """

    tab_close_requested = Signal()

    def __init__(self, app_context: AppContext, note: Note, parent: QWidget):
        super().__init__(app_context=app_context, parent=parent)
        self.app_context = app_context
        self.note = note

        self._initialize()
        self.setup_connections()
        self.register_unsaved_changes_source()

    @override
    def _init_ui(self):
        """Set up the user interface."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        # Create note editor
        self.note_editor = NoteEditorWidget(self.app_context, self.note, self)
        layout.addWidget(self.note_editor)

    @override
    def _apply_theme(self):
        pass

    def setup_connections(self):
        """Set up event subscriptions instead of Qt rename signal."""
        self.subscribe_to_event(ProjectEvents.PROJECT_ITEM_RENAMED, self.on_note_renamed_event)
        self.subscribe_to_event(NoteEvents.NOTE_CONTENT_CHANGED, self.on_note_content_changed_event)

    def on_note_renamed_event(self, event_data: dict):
        """Update the tab title when the underlying note item is renamed."""
        if event_data.get("item_id") == self.note.id:
            self.refresh_tab_title()

    def on_note_content_changed_event(self, event_data: dict):
        if event_data.get("note_id") == self.note.id:
            self.refresh_tab_title()

    def refresh_tab_title(self):
        """Helper to update the tab title via parent tab widget."""
        parent_container = self.parent()
        # Climb up if needed
        while parent_container is not None and not hasattr(parent_container, "update_tab_title"):
            parent_container = parent_container.parent()
        if parent_container:
            update_fn = getattr(parent_container, "update_tab_title", None)
            if callable(update_fn):
                new_title = self.get_tab_title()
                try:
                    update_fn(self, new_title)
                except Exception:
                    self.logger.debug("Failed to update tab title on parent container", exc_info=True)

    def get_tab_title(self) -> str:
        """Get the title for this tab."""
        modified_indicator = " *" if self.note_editor.has_unsaved_changes() else ""
        return f"📝 {self.note.name}{modified_indicator}"

    def get_tab_data(self) -> dict:
        """Identify this tab to TabContainer for session/event bookkeeping."""
        return {"type": "note", "id": self.note.id}

    def can_close(self) -> bool:
        """Prompt on user-close when auto-save is disabled, otherwise flush.

        This hook is for a user closing one tab/window. Project teardown and
        item removal bypass it and follow their respective lifecycle rules.
        """
        if not self.note_editor.has_unsaved_changes():
            return True

        autosave_enabled = self.app_context.get_manager(ConfigManager).config.auto_save.enabled
        if autosave_enabled:
            return self._flush_and_save_project(track_undo=False)

        choice = self.app_context.get_ui_controller().show_save_discard_cancel("Unsaved Note", f"Save changes to '{self.note.name}' before closing?")
        if choice == "discard":
            return True
        if choice != "save":
            return False
        return self._flush_and_save_project(track_undo=True)

    def _flush_and_save_project(self, *, track_undo: bool) -> bool:
        """Commit the editor value, then persist the current project file."""
        app_state = self.app_context.get_app_state()
        project = get_current_project(self.app_context)
        ui_controller = self.app_context.get_ui_controller()
        if project is None or not app_state.project_file_path:
            ui_controller.show_error_message("Save Failed", "This project has no save path. Use Save As before closing this note.")
            return False
        if app_state.is_saving:
            ui_controller.show_error_message("Save In Progress", "The project is already being saved. Wait for it to finish, then close the note.")
            return False

        try:
            saved_note = self.note_editor.save_content(track_undo=track_undo)
        except Exception:  # noqa: BLE001 - a user close must leave the tab open on failure
            saved_note = False
        if not saved_note:
            ui_controller.show_error_message("Save Failed", "The note edit could not be applied; the tab will stay open.")
            return False

        try:
            self.app_context.get_manager(ProjectManager).save_project(project, app_state.project_file_path)
        except Exception as error:  # noqa: BLE001 - keep the tab open and report persistence failures
            self.note_editor.is_modified = True
            ui_controller.show_error_message("Save Failed", f"The note could not be saved:\n{error}")
            return False
        app_state.mark_saved()
        return True

    def save(self) -> bool:
        """Save the note for UnsavedChangesRegistry's flush. Returns whether
        the save actually committed (see NoteEditorWidget.save_content) --
        False means the note is still dirty and must not be treated as
        safely persisted.

        Commits without occupying an undo slot (track_undo=False) -- this
        is a forced, infrastructure-triggered commit (a project-lifecycle
        guard, or another command's own undo()/redo() swapping the current
        project out from under this note), not a user-initiated Save
        action, so it must not interleave with a command that already
        occupies a stack slot for an operation that hasn't finished yet
        (see PR #352 review)."""
        try:
            return self.note_editor.save_content(track_undo=False)
        except Exception:  # noqa: BLE001 -- GUI event-handler safety net -- an unexpected error here must not crash the UI
            return False

    def has_unsaved_changes(self) -> bool:
        """Whether this tab's note editor has an edit not yet committed to the
        project model (see NoteEditorWidget.has_unsaved_changes)."""
        return self.note_editor.has_unsaved_changes()

    def get_note(self) -> Note:
        """Get the note associated with this tab."""
        return self.note
