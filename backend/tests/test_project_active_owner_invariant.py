from app.core.enums import ProjectStatus
from app.models.project import Project


def test_project_status_has_only_active_and_disabled() -> None:
    assert [status.value for status in ProjectStatus] == ["ACTIVE", "DISABLED"]


def test_project_owner_uniqueness_is_partial_active_only() -> None:
    table = Project.__table__
    assert all(
        constraint.name != "uq_aquaponics_systems_owner_user_id"
        for constraint in table.constraints
    )

    index = next(
        index
        for index in table.indexes
        if index.name == "uq_aquaponics_systems_one_active_owner"
    )
    assert index.unique is True
    assert [column.name for column in index.columns] == ["owner_user_id"]
    predicate = str(index.dialect_options["postgresql"]["where"])
    assert "status = 'ACTIVE'" in predicate
    assert "is_deleted = false" in predicate
