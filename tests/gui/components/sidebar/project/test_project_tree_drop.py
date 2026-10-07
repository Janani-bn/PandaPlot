from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from PySide6.QtCore import QMimeData, QPointF, Qt
from PySide6.QtGui import QDropEvent
from PySide6.QtWidgets import QTreeWidgetItem

from pandaplot.gui.components.sidebar.project.project_tree import ProjectTreeWidget
from pandaplot.models.project import Project
from pandaplot.models.project.items import Folder, Note


@pytest.mark.parametrize("edge", ["above", "below"])
def test_drop_beside_top_level_folder_moves_nested_folder_to_root(qtbot, edge):
    project = Project(name="Root move")
    outer = Folder(name="Outer")
    nested = Folder(name="Nested")
    child = Note(name="Keep me")
    project.add_item(outer)
    project.add_item(nested, outer.id)
    project.add_item(child, nested.id)
    state = SimpleNamespace(has_project=True, current_project=project, event_bus=Mock())
    context = Mock()
    context.get_app_state.return_value = state
    executor = context.get_command_executor.return_value
    executor.execute_command.side_effect = lambda command: command.execute()
    tree = ProjectTreeWidget(SimpleNamespace(app_state=state, app_context=context))
    qtbot.addWidget(tree)
    root_row = QTreeWidgetItem(["Project"])
    root_row.setData(0, Qt.ItemDataRole.UserRole, {"type": "project", "id": "root"})
    tree.addTopLevelItem(root_row)
    outer_row = QTreeWidgetItem([outer.name])
    outer_row.setData(0, Qt.ItemDataRole.UserRole, {"type": "folder", "id": outer.id, "data": outer})
    root_row.addChild(outer_row)
    nested_row = QTreeWidgetItem([nested.name])
    nested_row.setData(0, Qt.ItemDataRole.UserRole, {"type": "folder", "id": nested.id, "data": nested})
    outer_row.addChild(nested_row)
    root_row.setExpanded(True)
    outer_row.setExpanded(True)
    tree.resize(500, 400)
    tree.show()
    tree.setCurrentItem(nested_row)
    rectangle = tree.visualItemRect(outer_row)
    y = rectangle.top() + 1 if edge == "above" else rectangle.bottom() - 1
    event = QDropEvent(QPointF(rectangle.center().x(), y), Qt.DropAction.MoveAction, QMimeData(), Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier)
    tree.dropEvent(event)
    assert nested.parent_id == project.root.id
    assert nested in project.root.get_items()
    assert child in nested.get_items()
    command = executor.execute_command.call_args.args[0]
    assert command.undo().value == "success"
    assert nested.parent_id == outer.id
    assert command.redo().value == "success"
    assert nested.parent_id == project.root.id


@pytest.mark.parametrize("target", ["folder_center", "folder_edge", "root", "empty"])
@pytest.mark.parametrize("has_child", [False, True])
def test_folder_drop_destinations(qtbot, target, has_child):
    project = Project(name="Drop targets")
    outer = Folder(name="Outer")
    source = Folder(name="Source")
    sibling = Folder(name="Sibling")
    project.add_item(outer)
    project.add_item(source, outer.id)
    project.add_item(sibling, outer.id)
    child = Note(name="Keep child")
    if has_child:
        project.add_item(child, source.id)
    state = SimpleNamespace(has_project=True, current_project=project, event_bus=Mock())
    context = Mock()
    context.get_app_state.return_value = state
    executor = context.get_command_executor.return_value
    executor.execute_command.side_effect = lambda command: command.execute()
    tree = ProjectTreeWidget(SimpleNamespace(app_state=state, app_context=context))
    qtbot.addWidget(tree)
    root_row = QTreeWidgetItem(["Project"])
    root_row.setData(0, Qt.ItemDataRole.UserRole, {"type": "project", "id": "root"})
    tree.addTopLevelItem(root_row)
    rows = {}
    for item, parent_row in ((outer, root_row), (source, None), (sibling, None)):
        row = QTreeWidgetItem([item.name])
        row.setData(0, Qt.ItemDataRole.UserRole, {"type": "folder", "id": item.id, "data": item})
        (parent_row if parent_row is not None else rows[outer.id]).addChild(row)
        rows[item.id] = row
        row.setExpanded(True)
    root_row.setExpanded(True)
    tree.resize(500, 400)
    tree.show()
    tree.setCurrentItem(rows[source.id])
    qtbot.wait(10)
    if target == "empty":
        point = QPointF(200, 300)
    elif target == "root":
        point = QPointF(tree.visualItemRect(root_row).center())
    else:
        rectangle = tree.visualItemRect(rows[sibling.id])
        point = QPointF(rectangle.center()) if target == "folder_center" else QPointF(rectangle.center().x(), rectangle.top() + 1)
    event = QDropEvent(point, Qt.DropAction.MoveAction, QMimeData(), Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier)
    tree.dropEvent(event)
    expected_parent = sibling.id if target == "folder_center" else outer.id if target == "folder_edge" else project.root.id
    assert source.parent_id == expected_parent
    if has_child:
        assert child in source.get_items()
    if target != "folder_edge":
        command = executor.execute_command.call_args.args[0]
        assert command.undo().value == "success"
        assert source.parent_id == outer.id
        assert command.redo().value == "success"
        assert source.parent_id == expected_parent
