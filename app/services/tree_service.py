"""Casos de uso del árbol: creación, cascada, archivo y objetivos."""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timedelta
from typing import Iterable

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.core.exceptions import NotFoundError, ValidationError
from app.domain.enums import ModuleType, Priority, RoutineCategory, TaskTag
from app.domain.logical_date import (
    get_logical_date,
    iso_to_logical_date,
    parse_logical_date,
)
from app.models.achievement import Achievement
from app.models.objective import Objective
from app.models.schedule import DailyScheduleSlot
from app.models.task_node import TaskNode
from app.models.timer import TimerSession
from app.models.user import User
from app.models.workspace import Workspace
from app.repositories.achievements import AchievementRepository
from app.repositories.nodes import NodeRepository
from app.repositories.objectives import ObjectiveRepository
from app.repositories.schedules import ScheduleRepository
from app.repositories.timers import TimerRepository
from app.repositories.workspaces import WorkspaceRepository
from app.schemas.node import NodeCreate, NodeOut, NodeUpdate
from app.schemas.objective import LinkedItemOut, ObjectiveOut


def logical_today(user: User) -> str:
    return get_logical_date(cutoff_hour=user.logical_cutoff_hour)


def weekday_js(logical_date: str) -> int:
    """Domingo=0 … Sábado=6 (igual que JavaScript)."""

    return (parse_logical_date(logical_date).weekday() + 1) % 7


def get_current_workspace(db: Session, user: User) -> Workspace:
    workspaces = WorkspaceRepository.list_for_user(db, user.id)
    if not workspaces:
        workspace = WorkspaceRepository.create(
            db, user_id=user.id, name="General", is_default=True
        )
        workspaces = [workspace]
    preferences = user.preferences
    if preferences and preferences.current_workspace_id:
        for workspace in workspaces:
            if workspace.id == preferences.current_workspace_id:
                return workspace
    return workspaces[0]


def get_workspace(db: Session, user: User, workspace_id: str | None) -> Workspace:
    if workspace_id:
        workspace = WorkspaceRepository.get(db, user.id, workspace_id)
        if workspace is None:
            raise NotFoundError("El espacio de trabajo no existe o no te pertenece.")
        return workspace
    return get_current_workspace(db, user)


def node_schedule_active(node: TaskNode, logical_date: str) -> bool:
    day = parse_logical_date(logical_date)
    if node.period_start and day < node.period_start:
        return False
    if node.period_end and day > node.period_end:
        return False
    days = node.schedule_days or []
    if days and weekday_js(logical_date) not in days:
        return False
    return True


def _children_map(nodes: Iterable[TaskNode]) -> dict[str | None, list[TaskNode]]:
    mapping: dict[str | None, list[TaskNode]] = defaultdict(list)
    for node in nodes:
        mapping[node.parent_id].append(node)
    for children in mapping.values():
        children.sort(key=lambda n: (n.sort_order, n.created_at, n.title.lower()))
    return mapping


def build_forest(nodes: list[TaskNode], module_type: ModuleType | None = None) -> list[TaskNode]:
    """Construye raíces activas; un nodo archivado oculta todo su subárbol."""

    filtered = [n for n in nodes if module_type is None or n.module_type == module_type]
    by_id = {n.id: n for n in filtered}
    children = _children_map(filtered)
    roots = [n for n in filtered if not n.parent_id or n.parent_id not in by_id]
    roots.sort(key=lambda n: (n.sort_order, n.created_at, n.title.lower()))

    def include(node: TaskNode) -> bool:
        if node.is_archived:
            return False
        return all(include(child) for child in children.get(node.id, []))

    # Un padre archivado ya oculta a sus hijos; no es necesario que el hijo esté
    # marcado como archivado (el reset solo archiva raíces de Backlog).
    return [root for root in roots if not root.is_archived]


def subtree_ids(node: TaskNode, children: dict[str | None, list[TaskNode]]) -> list[str]:
    result = [node.id]
    for child in children.get(node.id, []):
        result.extend(subtree_ids(child, children))
    return result


def active_scheduled_node_ids(
    db: Session,
    user: User,
    logical_date: str,
    *,
    workspace_id: str | None = None,
    nodes_by_id: dict[str, TaskNode] | None = None,
) -> set[str]:
    """IDs con una asignación visible hoy (respeta skip, recurrencia y días)."""

    slots = ScheduleRepository.list_for_user(db, user.id)
    skipped = ScheduleRepository.skipped_node_ids(db, user.id, logical_date)
    if nodes_by_id is None:
        nodes_by_id = {
            node.id: node
            for node in NodeRepository.list_all(db, user.id, include_archived=True)
        }
    result: set[str] = set()
    day = weekday_js(logical_date)
    for slot in slots:
        node = nodes_by_id.get(slot.node_id)
        if node is None:
            continue
        if workspace_id and node.workspace_id != workspace_id:
            continue
        if slot.skip_logical_date == logical_date or node.id in skipped:
            continue
        if slot.recurring:
            days = slot.schedule_days or node.schedule_days or []
            if days and day not in days:
                continue
            result.add(node.id)
        elif slot.assigned_logical_date == logical_date:
            result.add(node.id)
    return result


def _timer_totals(
    nodes: list[TaskNode], sessions: list[TimerSession]
) -> dict[str, tuple[int, bool]]:
    """Suma recursiva de segundos y uso de timer por nodo."""

    by_node: dict[str, list[TimerSession]] = defaultdict(list)
    for session in sessions:
        by_node[session.node_id].append(session)
    children = _children_map(nodes)
    result: dict[str, tuple[int, bool]] = {}

    def walk(node: TaskNode) -> tuple[int, bool]:
        total = sum(int(s.focus_secs or 0) for s in by_node.get(node.id, []))
        used = any(bool(s.used_timer) for s in by_node.get(node.id, []))
        for child in children.get(node.id, []):
            child_secs, child_used = walk(child)
            total += child_secs
            used = used or child_used
        result[node.id] = (total, used)
        return total, used

    for node in nodes:
        if not node.parent_id:
            walk(node)
    for node in nodes:
        if node.id not in result:
            walk(node)
    return result


def serialize_forest(
    db: Session,
    user: User,
    *,
    logical_date: str | None = None,
    workspace_id: str | None = None,
    module_type: ModuleType | None = None,
    nodes: list[TaskNode] | None = None,
) -> list[NodeOut]:
    today = logical_date or logical_today(user)
    if nodes is None:
        nodes = NodeRepository.list_all(
            db,
            user.id,
            workspace_id=workspace_id,
            module_type=module_type,
            include_archived=True,
        )
    else:
        nodes = [
            n
            for n in nodes
            if (workspace_id is None or n.workspace_id == workspace_id)
            and (module_type is None or n.module_type == module_type)
        ]
    by_id = {n.id: n for n in nodes}
    children = _children_map(nodes)
    sessions = TimerRepository.list_for_nodes_date(
        db, user.id, list(by_id.keys()), today
    )
    timer_totals = _timer_totals(nodes, sessions)
    scheduled = active_scheduled_node_ids(
        db, user, today, workspace_id=workspace_id, nodes_by_id=by_id
    )
    roots = [n for n in nodes if not n.parent_id or n.parent_id not in by_id]
    roots.sort(key=lambda n: (n.sort_order, n.created_at, n.title.lower()))

    def activity_today(node: TaskNode) -> bool:
        completed_today = (
            node.completed_at is not None
            and iso_to_logical_date(node.completed_at, user.logical_cutoff_hour) == today
        )
        secs, used = timer_totals.get(node.id, (0, False))
        scheduled_here = node.id in scheduled
        if completed_today or used or secs > 0 or scheduled_here:
            return True
        return any(activity_today(child) for child in children.get(node.id, []))

    def serialize(node: TaskNode) -> NodeOut:
        child_nodes = [child for child in children.get(node.id, []) if not child.is_archived]
        child_out = [serialize(child) for child in child_nodes]
        secs, used = timer_totals.get(node.id, (0, False))
        activity = activity_today(node)
        if node.module_type in (ModuleType.HABITS, ModuleType.ROUTINES):
            active = activity or node_schedule_active(node, today)
        else:
            active = activity
        return NodeOut(
            id=node.id,
            user_id=node.user_id,
            workspace_id=node.workspace_id,
            parent_id=node.parent_id,
            module_type=node.module_type,
            title=node.title,
            completed=node.completed,
            completed_at=node.completed_at,
            expanded=node.expanded,
            is_archived=node.is_archived,
            routine_category=node.routine_category,
            priority=node.priority,
            tag=node.tag,
            schedule_days=list(node.schedule_days or []),
            period_start=node.period_start,
            period_end=node.period_end,
            objective_id=node.objective_id,
            sort_order=node.sort_order,
            created_at=node.created_at,
            updated_at=node.updated_at,
            has_children=bool(child_nodes),
            timer_secs_today=secs,
            used_timer_today=used,
            focus_mins_today=round(secs / 60),
            active_today=active,
            children=child_out,
        )

    return [serialize(root) for root in roots if not root.is_archived]


def create_node(db: Session, user: User, data: NodeCreate) -> TaskNode:
    title = data.title.strip()
    if not title:
        raise ValidationError("El título no puede estar vacío.")

    parent: TaskNode | None = None
    if data.parent_id:
        parent = NodeRepository.get(db, user.id, data.parent_id)
        if parent is None:
            raise NotFoundError("La tarea padre no existe o no te pertenece.")
        if parent.module_type != data.module_type:
            raise ValidationError("La subtarea debe pertenecer al mismo módulo que el padre.")
        workspace = WorkspaceRepository.get(db, user.id, parent.workspace_id)
        if workspace is None:
            raise NotFoundError("El espacio de trabajo de la tarea padre no existe.")
    else:
        workspace = get_workspace(db, user, data.workspace_id)

    if parent is not None:
        sibling_filter = [n for n in NodeRepository.children(db, user.id, parent.id)]
    else:
        sibling_filter = [
            n
            for n in NodeRepository.list_all(
                db, user.id, workspace_id=workspace.id, module_type=data.module_type
            )
            if n.parent_id is None
        ]
    sort_order = (
        data.sort_order
        if data.sort_order is not None
        else (max((n.sort_order for n in sibling_filter), default=-1) + 1)
    )

    routine_category = data.routine_category
    priority = data.priority
    tag = data.tag
    if data.module_type == ModuleType.ROUTINES and routine_category is None:
        routine_category = RoutineCategory.COMER
    if data.module_type == ModuleType.BACKLOG:
        priority = priority or Priority.BAJA
        tag = tag or TaskTag.PERSONAL
    if data.module_type != ModuleType.ROUTINES:
        routine_category = None
    if data.module_type != ModuleType.BACKLOG:
        priority = None
        tag = None

    node = TaskNode(
        user_id=user.id,
        workspace_id=workspace.id,
        parent_id=parent.id if parent else None,
        module_type=data.module_type,
        title=title,
        completed=False,
        expanded=data.expanded,
        routine_category=routine_category,
        priority=priority,
        tag=tag,
        schedule_days=data.schedule_days,
        period_start=data.period_start,
        period_end=data.period_end,
        sort_order=sort_order,
    )
    NodeRepository.create(db, node)

    if parent is not None:
        parent.expanded = True
        if parent.completed:
            parent.completed = False
            parent.completed_at = None
            remove_achievements_for_node(db, user.id, parent.id)
        recalculate_cascade(db, user, parent.module_type)
    else:
        recalculate_cascade(db, user, data.module_type)

    if data.objective_id:
        objective = ObjectiveRepository.get(db, user.id, data.objective_id)
        if objective is None:
            raise NotFoundError("El objetivo no existe o no te pertenece.")
        link_node_to_objective(db, user, node, data.objective_id)
    return node


def update_node(db: Session, user: User, node: TaskNode, data: NodeUpdate) -> TaskNode:
    if data.title is not None:
        title = data.title.strip()
        if not title:
            raise ValidationError("El título no puede estar vacío.")
        node.title = title
    if data.expanded is not None:
        node.expanded = data.expanded
    if data.schedule_days is not None:
        node.schedule_days = data.schedule_days
    if "period_start" in data.model_fields_set:
        node.period_start = data.period_start
    if "period_end" in data.model_fields_set:
        node.period_end = data.period_end
    if node.period_start and node.period_end and node.period_end < node.period_start:
        raise ValidationError("La fecha final del periodo es anterior a la inicial.")
    if "routine_category" in data.model_fields_set:
        node.routine_category = data.routine_category
    if "priority" in data.model_fields_set:
        node.priority = data.priority
    if "tag" in data.model_fields_set:
        node.tag = data.tag
    if data.sort_order is not None:
        node.sort_order = data.sort_order
    if "objective_id" in data.model_fields_set:
        link_node_to_objective(db, user, node, data.objective_id)
    db.flush()
    return node


def _children_of_node(db: Session, user_id: str, node_id: str) -> list[TaskNode]:
    return NodeRepository.children(db, user_id, node_id)


def remove_achievements_for_node(db: Session, user_id: str, node_id: str) -> int:
    return AchievementRepository.delete_for_node_sources(db, user_id, node_id)


def recalculate_cascade(
    db: Session, user: User, module_type: ModuleType, *, nodes: list[TaskNode] | None = None
) -> list[TaskNode]:
    """Recalcula padres de abajo hacia arriba y estampa/limpia completed_at."""

    if nodes is None:
        nodes = NodeRepository.list_all(
            db, user.id, module_type=module_type, include_archived=True
        )
    by_id = {n.id: n for n in nodes}
    children: dict[str | None, list[TaskNode]] = defaultdict(list)
    for node in nodes:
        children[node.parent_id].append(node)
    changed: list[TaskNode] = []
    visited: set[str] = set()

    def walk(node: TaskNode) -> bool:
        if node.id in visited:
            return node.completed
        visited.add(node.id)
        child_nodes = children.get(node.id, [])
        if not child_nodes:
            return node.completed
        all_done = all(walk(child) for child in child_nodes)
        was_completed = node.completed
        node.completed = all_done
        if all_done and not was_completed:
            node.completed_at = datetime.now()
            changed.append(node)
        elif not all_done and was_completed:
            node.completed_at = None
            remove_achievements_for_node(db, user.id, node.id)
            changed.append(node)
        return node.completed

    for node in list(nodes):
        walk(node)
    # Asegura que los padres cuyo hijo cambió fuera de ``nodes`` se recalculen.
    for node in nodes:
        if node.parent_id and node.parent_id in by_id:
            walk(by_id[node.parent_id])
    db.flush()
    return changed


def toggle_node(db: Session, user: User, node: TaskNode, completed: bool) -> TaskNode:
    child_nodes = _children_of_node(db, user.id, node.id)
    if child_nodes:
        raise ValidationError(
            "Este nodo tiene subtareas: completa o desmarca sus dependencias."
        )
    if node.completed == completed:
        return node
    node.completed = completed
    today = logical_today(user)
    if completed:
        node.completed_at = datetime.now()
        if TimerRepository.get_session(db, user.id, node.id, today, True) is None:
            TimerRepository.record(
                db,
                user_id=user.id,
                node_id=node.id,
                logical_date=today,
                seconds=0,
                cycles=0,
                used_timer=False,
            )
    else:
        node.completed_at = None
        unused = TimerRepository.get_session(db, user.id, node.id, today, False)
        if unused is not None:
            db.delete(unused)
            db.flush()
        remove_achievements_for_node(db, user.id, node.id)
    db.flush()
    recalculate_cascade(db, user, node.module_type)
    return node


def archive_node(
    db: Session,
    user: User,
    node: TaskNode,
    *,
    all_nodes: list[TaskNode] | None = None,
    logical_date: str | None = None,
    mark_archived: bool = True,
) -> Achievement | None:
    """Archiva un nodo completado de forma idempotente."""

    if not node.completed:
        return None
    if all_nodes is None:
        all_nodes = NodeRepository.list_all(db, user.id, include_archived=True)
    children = _children_map(all_nodes)
    ids = subtree_ids(node, children)
    sessions = TimerRepository.list_for_nodes(db, user.id, ids)
    total_secs = sum(int(session.focus_secs or 0) for session in sessions)
    today = logical_date or logical_today(user)
    completed_logical = (
        iso_to_logical_date(node.completed_at, user.logical_cutoff_hour)
        if node.completed_at
        else today
    )
    if node.module_type == ModuleType.BACKLOG:
        source_id = node.id
    else:
        source_id = f"{node.id}_{completed_logical or today}"
    existing = AchievementRepository.get_by_source(db, user.id, source_id)
    if existing is not None:
        return existing
    achievement = Achievement(
        user_id=user.id,
        workspace_id=node.workspace_id,
        node_id=node.id,
        source_id=source_id,
        module_type=node.module_type,
        title=node.title,
        completed_at=node.completed_at or datetime.now(),
        timer_mins=round(total_secs / 60),
        objective_id=node.objective_id,
    )
    if mark_archived:
        node.is_archived = True
    return AchievementRepository.create(db, achievement)


def archive_completed_achievements(
    db: Session, user: User, *, logical_date: str | None = None
) -> int:
    nodes = NodeRepository.list_all(db, user.id, include_archived=True)
    created = 0
    for node in nodes:
        if node.completed:
            before = AchievementRepository.get_by_source(
                db,
                user.id,
                node.id
                if node.module_type == ModuleType.BACKLOG
                else f"{node.id}_"
                f"{iso_to_logical_date(node.completed_at, user.logical_cutoff_hour) or (logical_date or logical_today(user))}",
            )
            if before is None:
                result = archive_node(
                    db,
                    user,
                    node,
                    all_nodes=nodes,
                    logical_date=logical_date,
                    mark_archived=False,
                )
                if result is not None:
                    created += 1
    return created


def reset_habit_routine_trees(db: Session, user: User) -> int:
    nodes = NodeRepository.list_all(db, user.id, include_archived=False)
    count = 0
    for node in nodes:
        if node.module_type in (ModuleType.HABITS, ModuleType.ROUTINES):
            if node.completed or node.completed_at is not None:
                count += 1
            node.completed = False
            node.completed_at = None
    db.flush()
    return count


def archive_and_purge_backlog(db: Session, user: User) -> list[str]:
    """Archiva raíces de Backlog completadas y limpia su horario."""

    nodes = NodeRepository.list_all(db, user.id, include_archived=True)
    children = _children_map(nodes)
    roots = [
        n
        for n in nodes
        if n.module_type == ModuleType.BACKLOG
        and n.parent_id is None
        and n.completed
        and not n.is_archived
    ]
    purged_ids: list[str] = []
    for root in roots:
        ids = subtree_ids(root, children)
        purged_ids.extend(ids)
        root.is_archived = True
    if purged_ids:
        ScheduleRepository.delete_for_nodes(db, user.id, purged_ids)
    db.flush()
    return purged_ids


def prune_old_timer_sessions(db: Session, user: User, days: int = 30) -> int:
    cutoff = (datetime.now() - timedelta(days=days)).date().isoformat()
    node_ids = list(
        db.scalars(
            select(TaskNode.id).where(
                TaskNode.user_id == user.id,
                TaskNode.module_type.in_([ModuleType.HABITS, ModuleType.ROUTINES]),
            )
        )
    )
    if not node_ids:
        return 0
    result = db.execute(
        delete(TimerSession).where(
            TimerSession.user_id == user.id,
            TimerSession.node_id.in_(node_ids),
            TimerSession.logical_date < cutoff,
        )
    )
    return int(result.rowcount or 0)


def delete_node(db: Session, user: User, node: TaskNode) -> list[str]:
    nodes = NodeRepository.list_all(db, user.id, include_archived=True)
    children = _children_map(nodes)
    ids = subtree_ids(node, children)
    for candidate in nodes:
        if candidate.id in ids and candidate.completed:
            archive_node(db, user, candidate, all_nodes=nodes)
    ScheduleRepository.delete_for_nodes(db, user.id, ids)
    ObjectiveRepository.delete_links_for_node(db, user.id, node.id)
    module = node.module_type
    db.delete(node)
    db.flush()
    recalculate_cascade(db, user, module)
    return ids


def find_node(db: Session, user: User, node_id: str) -> TaskNode:
    node = NodeRepository.get(db, user.id, node_id)
    if node is None:
        raise NotFoundError("La tarea no existe o no te pertenece.")
    return node


def link_node_to_objective(
    db: Session, user: User, node: TaskNode, objective_id: str | None
) -> Objective | None:
    """Vínculo único: una tarea pertenece a un solo objetivo a la vez."""

    old_objective = (
        ObjectiveRepository.get(db, user.id, node.objective_id)
        if node.objective_id
        else None
    )
    if objective_id is None:
        existing = ObjectiveRepository.get_link_for_node(db, user.id, node.id)
        if existing is not None:
            ObjectiveRepository.delete_link(db, existing)
        node.objective_id = None
        db.flush()
        if old_objective is not None:
            snapshot_objective_progress(db, user, old_objective)
        return None

    objective = ObjectiveRepository.get(db, user.id, objective_id)
    if objective is None:
        raise NotFoundError("El objetivo no existe o no te pertenece.")
    existing = ObjectiveRepository.get_link_for_node(db, user.id, node.id)
    if existing is not None and existing.objective_id == objective.id:
        node.objective_id = objective.id
        db.flush()
        return objective
    if existing is not None:
        ObjectiveRepository.delete_link(db, existing)
    from app.models.objective import ObjectiveTaskLink

    ObjectiveRepository.create_link(
        db,
        ObjectiveTaskLink(
            user_id=user.id,
            objective_id=objective.id,
            node_id=node.id,
            module_type=node.module_type,
        ),
    )
    node.objective_id = objective.id
    db.flush()
    if old_objective is not None and old_objective.id != objective.id:
        snapshot_objective_progress(db, user, old_objective)
    snapshot_objective_progress(db, user, objective)
    return objective


def compute_objective_progress(
    db: Session, user: User, objective: Objective
) -> ObjectiveOut:
    links = ObjectiveRepository.list_links(db, user.id, objective.id)
    linked_items: list[LinkedItemOut] = []
    total = 0
    done = 0
    for link in links:
        node = NodeRepository.get(db, user.id, link.node_id)
        achievement = AchievementRepository.find_for_node(db, user.id, link.node_id)
        if node is None and achievement is None:
            linked_items.append(
                LinkedItemOut(
                    node_id=link.node_id,
                    title="(eliminada)",
                    module_type=link.module_type,
                    done=False,
                    missing=True,
                )
            )
            continue
        total += 1
        is_done = bool((node and node.completed) or achievement)
        if is_done:
            done += 1
        linked_items.append(
            LinkedItemOut(
                node_id=link.node_id,
                title=node.title if node else (achievement.title if achievement else "(eliminada)"),
                module_type=link.module_type,
                done=is_done,
                archived=bool(node and node.is_archived),
                missing=False,
            )
        )
    pct = 0 if total == 0 else round((done / total) * 100)
    return ObjectiveOut(
        id=objective.id,
        workspace_id=objective.workspace_id,
        title=objective.title,
        description=objective.description,
        horizon=objective.horizon,
        start_date=objective.start_date,
        end_date=objective.end_date,
        created_at=objective.created_at,
        total=total,
        done=done,
        pct=pct,
        links=linked_items,
    )


def snapshot_objective_progress(
    db: Session, user: User, objective: Objective, *, logical_date: str | None = None
) -> None:
    """Guarda un punto solo si el porcentaje cambió o es el primer día."""

    today = logical_date or logical_today(user)
    progress = compute_objective_progress(db, user, objective)
    snapshots = ObjectiveRepository.list_snapshots(db, user.id, objective.id)
    if snapshots:
        last = snapshots[-1]
        if last.logical_date == today:
            ObjectiveRepository.upsert_snapshot(
                db,
                user_id=user.id,
                objective_id=objective.id,
                logical_date=today,
                pct=progress.pct,
                done=progress.done,
                total=progress.total,
            )
            return
        if round(last.pct) == progress.pct:
            return
    ObjectiveRepository.upsert_snapshot(
        db,
        user_id=user.id,
        objective_id=objective.id,
        logical_date=today,
        pct=progress.pct,
        done=progress.done,
        total=progress.total,
    )


def snapshot_all_objectives(db: Session, user: User, *, logical_date: str | None = None) -> None:
    for objective in ObjectiveRepository.list_for_user(db, user.id):
        snapshot_objective_progress(db, user, objective, logical_date=logical_date)
