from copy import deepcopy
from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy import select

from app.db.models import LabClass, TemplateVersion


VALID_SCHEMA = {
    "title": "伏安法测电阻",
    "tables": [
        {
            "id": "measurements",
            "title": "电压电流测量数据",
            "minimumRows": 5,
            "maximumRows": 30,
            "fields": [
                {"key": "voltage", "label": "电压", "type": "number", "unit": "V", "required": True, "min": 0, "max": 12},
                {"key": "current", "label": "电流", "type": "number", "unit": "A", "required": True, "min": 0.001, "max": 1},
            ],
        }
    ],
    "calculations": [
        {"key": "slope", "function": "LINEAR_SLOPE", "args": ["current", "voltage"], "unit": "ohm"},
        {"key": "fit", "function": "R_SQUARED", "args": ["current", "voltage"]},
    ],
    "charts": [{"type": "scatter", "x": "current", "y": "voltage", "fit": "linear"}],
    "checks": [{"type": "minimum_rows", "value": 5}, {"type": "r_squared_below", "value": 0.95}],
}


def login(client):
    return client.post("/api/auth/login", json={"account": "t0001", "password": "InitialPass2026"})


def create_template(client):
    return client.post("/api/templates", json={"name": "伏安法测电阻", "description": "测量电阻并进行 U-I 线性拟合"})


def test_template_must_validate_before_publish(client, seed_user) -> None:
    seed_user(role="teacher", account="t0001")
    assert login(client).status_code == 200
    template_id = create_template(client).json()["id"]
    invalid = deepcopy(VALID_SCHEMA)
    invalid["calculations"][0]["function"] = "EVAL"
    assert client.put(
        f"/api/templates/{template_id}/draft",
        json={"name": "伏安法测电阻", "description": "", "schema": invalid},
    ).status_code == 200

    validation = client.post(f"/api/templates/{template_id}/validate")
    assert validation.status_code == 200
    assert validation.json()["valid"] is False
    assert client.post(f"/api/templates/{template_id}/publish").status_code == 422


def test_published_version_is_snapshot_and_assignment_references_it(client, seed_user, db) -> None:
    teacher = seed_user(role="teacher", account="t0001")
    assert login(client).status_code == 200
    template_id = create_template(client).json()["id"]
    saved = client.put(
        f"/api/templates/{template_id}/draft",
        json={"name": "伏安法测电阻", "description": "首个真实实验", "schema": VALID_SCHEMA},
    )
    assert saved.status_code == 200
    published = client.post(f"/api/templates/{template_id}/publish")
    assert published.status_code == 201
    version_id = published.json()["id"]

    changed = deepcopy(VALID_SCHEMA)
    changed["title"] = "修改后的草稿"
    assert client.put(
        f"/api/templates/{template_id}/draft",
        json={"name": "伏安法测电阻", "description": "", "schema": changed},
    ).status_code == 200
    db.expire_all()
    version = db.get(TemplateVersion, UUID(version_id))
    assert version.schema_json["title"] == "伏安法测电阻"

    lab_class = LabClass(
        class_code="PHY2401",
        class_name="物理2401",
        semester="2026秋",
        teacher_id=teacher.id,
        created_at=datetime.now(UTC),
    )
    db.add(lab_class)
    db.commit()
    start = datetime.now(UTC)
    assignment = client.post(
        "/api/assignments",
        json={
            "templateVersionId": version_id,
            "classId": str(lab_class.id),
            "title": "实验一：伏安法测电阻",
            "startAt": start.isoformat(),
            "dueAt": (start + timedelta(days=7)).isoformat(),
            "status": "open",
        },
    )
    assert assignment.status_code == 201
    assert assignment.json()["templateVersionId"] == version_id


def test_teacher_cannot_assign_another_teachers_class(client, seed_user, db) -> None:
    teacher = seed_user(role="teacher", account="t0001")
    other = seed_user(role="teacher", account="t0002")
    assert login(client).status_code == 200
    template_id = create_template(client).json()["id"]
    client.put(
        f"/api/templates/{template_id}/draft",
        json={"name": "伏安法测电阻", "description": "", "schema": VALID_SCHEMA},
    )
    version_id = client.post(f"/api/templates/{template_id}/publish").json()["id"]
    lab_class = LabClass(
        class_code="PHY2402",
        class_name="物理2402",
        semester="2026秋",
        teacher_id=other.id,
        created_at=datetime.now(UTC),
    )
    db.add(lab_class)
    db.commit()
    start = datetime.now(UTC)
    response = client.post(
        "/api/assignments",
        json={
            "templateVersionId": version_id,
            "classId": str(lab_class.id),
            "title": "越权任务",
            "startAt": start.isoformat(),
            "dueAt": (start + timedelta(days=1)).isoformat(),
        },
    )
    assert response.status_code == 404


def test_document_derived_template_supports_steps_calculation_dependencies_and_line_charts(client, seed_user) -> None:
    seed_user(role="teacher", account="t0001")
    assert login(client).status_code == 200
    template_id = create_template(client).json()["id"]
    schema = {
        "title": "力学综合实验",
        "steps": [
            {"id": "measure_period", "title": "测量周期", "instruction": "改变质量并重复测量周期。", "tableId": "mass_periods"}
        ],
        "tables": [
            {
                "id": "mass_periods",
                "title": "不同质量下的振子周期",
                "minimumRows": 5,
                "maximumRows": 8,
                "fields": [
                    {"key": "mass_g", "label": "振子质量", "type": "number", "unit": "g", "precision": 1, "required": True},
                    {"key": "period_1_s", "label": "周期 1", "type": "number", "unit": "s", "precision": 3, "required": True},
                    {"key": "period_2_s", "label": "周期 2", "type": "number", "unit": "s", "precision": 3, "required": True},
                ],
            }
        ],
        "calculations": [
            {"key": "mean_period_s", "function": "MEAN", "args": ["period_1_s", "period_2_s"], "unit": "s"},
            {"key": "period_squared_s2", "function": "POW", "args": ["mean_period_s"], "parameters": [2], "unit": "s²"},
        ],
        "charts": [{"title": "周期平方与质量关系", "type": "line", "x": "mass_g", "y": "period_squared_s2", "fit": "linear"}],
        "checks": [{"type": "minimum_rows", "tableId": "mass_periods", "value": 5}],
        "requiredArtifacts": ["data_image", "charts", "excel", "conclusion"],
    }
    field_keys = [field["key"] for field in schema["tables"][0]["fields"]]
    schema["tables"][0]["grid"] = {
        "rows": 6,
        "columns": 3,
        "cells": [
            {"id": "r1c1", "row": 0, "column": 0, "rowSpan": 1, "colSpan": 3, "kind": "label", "text": "不同质量下的振子周期"},
            *[
                {
                    "id": f"r{row + 1}c{column + 1}",
                    "row": row,
                    "column": column,
                    "rowSpan": 1,
                    "colSpan": 1,
                    "kind": "field",
                    "text": "",
                    "fieldKey": field_keys[column],
                }
                for row in range(1, 6)
                for column in range(3)
            ],
        ],
    }
    assert client.put(
        f"/api/templates/{template_id}/draft",
        json={"name": "力学综合实验", "description": "", "schema": schema},
    ).status_code == 200

    validation = client.post(f"/api/templates/{template_id}/validate")

    assert validation.status_code == 200
    assert validation.json() == {"valid": True, "issues": []}


def test_teacher_can_list_published_assignments(client, seed_user, db) -> None:
    teacher = seed_user(role="teacher", account="t0001")
    assert login(client).status_code == 200
    template_id = create_template(client).json()["id"]
    client.put(
        f"/api/templates/{template_id}/draft",
        json={"name": "伏安法测电阻", "description": "", "schema": VALID_SCHEMA},
    )
    version_id = client.post(f"/api/templates/{template_id}/publish").json()["id"]
    lab_class = LabClass(
        class_code="PHY2501",
        class_name="物理2501",
        semester="2026秋",
        teacher_id=teacher.id,
        created_at=datetime.now(UTC),
    )
    db.add(lab_class)
    db.commit()
    start = datetime.now(UTC)
    client.post(
        "/api/assignments",
        json={
            "templateVersionId": version_id,
            "classId": str(lab_class.id),
            "title": "实验一：伏安法测电阻",
            "startAt": start.isoformat(),
            "dueAt": (start + timedelta(days=7)).isoformat(),
        },
    )

    response = client.get("/api/assignments")

    assert response.status_code == 200
    assert response.json()[0]["classCode"] == "PHY2501"
    assert response.json()[0]["templateName"] == "伏安法测电阻"
    assert response.json()[0]["versionNumber"] == 1


def test_template_accepts_shared_fields_extended_input_types_and_grid_layout(client, seed_user) -> None:
    seed_user(role="teacher", account="t0001")
    assert login(client).status_code == 200
    template_id = create_template(client).json()["id"]
    schema = deepcopy(VALID_SCHEMA)
    schema["tables"][0]["fields"][0]["scope"] = "group"
    schema["tables"][0]["fields"].extend(
        [
            {"key": "condition", "label": "实验条件", "type": "enum", "options": ["常温", "低温"], "unit": "", "precision": 0, "required": True, "scope": "individual"},
            {"key": "observed_at", "label": "观测时间", "type": "time", "unit": "", "precision": 0, "required": True, "scope": "individual"},
            {"key": "evidence", "label": "读数照片", "type": "image", "unit": "", "precision": 0, "required": False, "scope": "individual"},
        ]
    )
    schema["tables"][0]["grid"] = {
        "rows": 6,
        "columns": 4,
        "columnWidths": [140, 180, 160, 220],
        "frozenRows": 1,
        "cells": [
            {"id": f"r{row + 1}c{column + 1}", "row": row, "column": column, "rowSpan": 1, "colSpan": 1, "kind": "label" if row == 0 else "field", "text": "", **({"fieldKey": schema["tables"][0]["fields"][column]["key"]} if row > 0 else {})}
            for row in range(6)
            for column in range(4)
        ],
    }
    assert client.put(
        f"/api/templates/{template_id}/draft",
        json={"name": "扩展字段模板", "description": "", "schema": schema},
    ).status_code == 200

    validation = client.post(f"/api/templates/{template_id}/validate")

    assert validation.json() == {"valid": True, "issues": []}


def test_template_rejects_invalid_grid_width_and_field_scope(client, seed_user) -> None:
    seed_user(role="teacher", account="t0001")
    assert login(client).status_code == 200
    template_id = create_template(client).json()["id"]
    schema = deepcopy(VALID_SCHEMA)
    schema["tables"][0]["fields"][0]["scope"] = "class"
    schema["tables"][0]["grid"] = {
        "rows": 6,
        "columns": 2,
        "columnWidths": [20],
        "frozenRows": 7,
        "cells": [
            {"id": f"r{row + 1}c{column + 1}", "row": row, "column": column, "rowSpan": 1, "colSpan": 1, "kind": "label" if row == 0 else "field", "text": "", **({"fieldKey": schema["tables"][0]["fields"][column]["key"]} if row > 0 else {})}
            for row in range(6)
            for column in range(2)
        ],
    }
    client.put(
        f"/api/templates/{template_id}/draft",
        json={"name": "无效布局", "description": "", "schema": schema},
    )

    validation = client.post(f"/api/templates/{template_id}/validate").json()

    assert validation["valid"] is False
    paths = {issue["path"] for issue in validation["issues"]}
    assert "tables[0].fields[0].scope" in paths
    assert "tables[0].grid.columnWidths" in paths
    assert "tables[0].grid.frozenRows" in paths
