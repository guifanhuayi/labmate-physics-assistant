from copy import deepcopy
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.auth.errors import AuthError
from app.db.models import ExperimentTemplate, TemplateVersion


ALLOWED_FUNCTIONS = {
    "SUM",
    "MEAN",
    "STD",
    "ABS",
    "SQRT",
    "POW",
    "LINEAR_SLOPE",
    "LINEAR_INTERCEPT",
    "R_SQUARED",
}
ALLOWED_FIELD_TYPES = {"number", "integer", "text"}
ALLOWED_CHARTS = {"scatter", "line"}
ALLOWED_ARTIFACTS = {"data_image", "charts", "excel", "conclusion"}


class TemplateService:
    """Owns schema validation and immutable version publication."""

    @staticmethod
    def validate(schema: dict[str, Any]) -> list[dict[str, str]]:
        issues: list[dict[str, str]] = []
        title = schema.get("title")
        if not isinstance(title, str) or not title.strip():
            issues.append({"path": "title", "message": "实验名称不能为空。"})

        steps = schema.get("steps", [])
        step_table_refs: list[tuple[str, str]] = []
        if not isinstance(steps, list):
            issues.append({"path": "steps", "message": "实验步骤必须是列表。"})
        else:
            step_ids: set[str] = set()
            for step_index, step in enumerate(steps):
                path = f"steps[{step_index}]"
                if not isinstance(step, dict):
                    issues.append({"path": path, "message": "实验步骤格式不正确。"})
                    continue
                step_id = step.get("id")
                if not isinstance(step_id, str) or not step_id.isidentifier() or step_id in step_ids:
                    issues.append({"path": f"{path}.id", "message": "步骤标识必须合法且不能重复。"})
                else:
                    step_ids.add(step_id)
                if not str(step.get("title", "")).strip() or not str(step.get("instruction", "")).strip():
                    issues.append({"path": path, "message": "步骤名称和操作说明不能为空。"})
                table_ref = step.get("tableId")
                if isinstance(table_ref, str) and table_ref:
                    step_table_refs.append((f"{path}.tableId", table_ref))

        tables = schema.get("tables")
        if not isinstance(tables, list) or not tables:
            return [{"path": "tables", "message": "至少需要一个数据表。"}]
        fields: dict[str, dict[str, Any]] = {}
        table_ids: set[str] = set()
        for table_index, table in enumerate(tables):
            path = f"tables[{table_index}]"
            table_id = table.get("id")
            if not isinstance(table_id, str) or not table_id.isidentifier() or table_id in table_ids:
                issues.append({"path": f"{path}.id", "message": "数据表标识必须合法且不能重复。"})
            else:
                table_ids.add(table_id)
            if not str(table.get("title", "")).strip():
                issues.append({"path": f"{path}.title", "message": "数据表名称不能为空。"})
            minimum = table.get("minimumRows")
            maximum = table.get("maximumRows")
            if not isinstance(minimum, int) or minimum < 1:
                issues.append({"path": f"{path}.minimumRows", "message": "最少行数必须是正整数。"})
            if not isinstance(maximum, int) or maximum < (minimum or 1) or maximum > 200:
                issues.append({"path": f"{path}.maximumRows", "message": "最多行数必须不小于最少行数且不超过 200。"})
            table_fields = table.get("fields")
            if not isinstance(table_fields, list) or not table_fields:
                issues.append({"path": f"{path}.fields", "message": "数据表至少需要一个字段。"})
                continue
            table_field_keys: set[str] = set()
            for field_index, field in enumerate(table_fields):
                field_path = f"{path}.fields[{field_index}]"
                key = field.get("key")
                if not isinstance(key, str) or not key.isidentifier():
                    issues.append({"path": f"{field_path}.key", "message": "字段键必须是合法标识符。"})
                    continue
                if key in fields:
                    issues.append({"path": f"{field_path}.key", "message": "字段键不能重复。"})
                fields[key] = field
                table_field_keys.add(key)
                if field.get("type") not in ALLOWED_FIELD_TYPES:
                    issues.append({"path": f"{field_path}.type", "message": "字段类型仅支持数值、整数或文本。"})
                if not field.get("label"):
                    issues.append({"path": f"{field_path}.label", "message": "字段名称不能为空。"})
                if field.get("type") in {"number", "integer"} and not field.get("unit"):
                    issues.append({"path": f"{field_path}.unit", "message": "数值字段的单位不能为空。"})
                precision = field.get("precision", 0)
                if not isinstance(precision, int) or precision < 0 or precision > 8:
                    issues.append({"path": f"{field_path}.precision", "message": "小数位数必须是 0 到 8 的整数。"})
                if field.get("min") is not None and field.get("max") is not None and field["min"] >= field["max"]:
                    issues.append({"path": field_path, "message": "字段最大值必须大于最小值。"})

            grid = table.get("grid")
            if grid is not None:
                grid_path = f"{path}.grid"
                rows = grid.get("rows") if isinstance(grid, dict) else None
                columns = grid.get("columns") if isinstance(grid, dict) else None
                cells = grid.get("cells") if isinstance(grid, dict) else None
                if not isinstance(rows, int) or rows < 2 or rows > 201:
                    issues.append({"path": f"{grid_path}.rows", "message": "表格总行数必须为 2 到 201。"})
                if not isinstance(columns, int) or columns < 1 or columns > 30:
                    issues.append({"path": f"{grid_path}.columns", "message": "表格总列数必须为 1 到 30。"})
                if not isinstance(cells, list):
                    issues.append({"path": f"{grid_path}.cells", "message": "表格单元格格式不正确。"})
                elif isinstance(rows, int) and 2 <= rows <= 201 and isinstance(columns, int) and 1 <= columns <= 30:
                    occupied: set[tuple[int, int]] = set()
                    for cell_index, cell in enumerate(cells):
                        cell_path = f"{grid_path}.cells[{cell_index}]"
                        if not isinstance(cell, dict):
                            issues.append({"path": cell_path, "message": "单元格格式不正确。"})
                            continue
                        row = cell.get("row")
                        column = cell.get("column")
                        row_span = cell.get("rowSpan", 1)
                        col_span = cell.get("colSpan", 1)
                        if not all(isinstance(value, int) for value in (row, column, row_span, col_span)):
                            issues.append({"path": cell_path, "message": "单元格位置和跨度必须是整数。"})
                            continue
                        if row < 0 or column < 0 or row_span < 1 or col_span < 1 or row + row_span > rows or column + col_span > columns:
                            issues.append({"path": cell_path, "message": "单元格超出表格边界。"})
                            continue
                        kind = cell.get("kind")
                        if kind not in {"label", "field"}:
                            issues.append({"path": f"{cell_path}.kind", "message": "单元格用途不受支持。"})
                        if kind == "field" and cell.get("fieldKey") not in table_field_keys:
                            issues.append({"path": f"{cell_path}.fieldKey", "message": "数据输入格必须绑定本表字段。"})
                        if kind == "field" and (row_span > 1 or col_span > 1):
                            issues.append({"path": cell_path, "message": "数据输入单元格不能合并。"})
                        for grid_row in range(row, row + row_span):
                            for grid_column in range(column, column + col_span):
                                coordinate = (grid_row, grid_column)
                                if coordinate in occupied:
                                    issues.append({"path": cell_path, "message": "单元格区域发生重叠。"})
                                occupied.add(coordinate)
                    if len(occupied) != rows * columns:
                        issues.append({"path": f"{grid_path}.cells", "message": "表格存在未定义的空洞区域。"})
                    if isinstance(minimum, int) and isinstance(maximum, int) and not minimum <= rows - 1 <= maximum:
                        issues.append({"path": f"{grid_path}.rows", "message": "表格数据行数必须处于最少和最多行数范围内。"})

        for path, table_ref in step_table_refs:
            if table_ref not in table_ids:
                issues.append({"path": path, "message": "步骤关联的数据表不存在。"})

        calculation_keys: set[str] = set()
        known_values = set(fields)
        for index, calculation in enumerate(schema.get("calculations", [])):
            path = f"calculations[{index}]"
            key = calculation.get("key")
            function = calculation.get("function")
            args = calculation.get("args", [])
            if not isinstance(key, str) or not key.isidentifier() or key in calculation_keys:
                issues.append({"path": f"{path}.key", "message": "计算键必须合法且不能重复。"})
            calculation_keys.add(key)
            if function not in ALLOWED_FUNCTIONS:
                issues.append({"path": f"{path}.function", "message": "计算函数不在白名单中。"})
            if not isinstance(args, list) or not args or any(arg not in known_values for arg in args):
                issues.append({"path": f"{path}.args", "message": "计算参数必须引用已定义字段或前序计算。"})
            elif any(arg in fields and fields[arg].get("type") == "text" for arg in args):
                issues.append({"path": f"{path}.args", "message": "文本字段不能参与数值计算。"})
            if function == "POW":
                parameters = calculation.get("parameters")
                if not isinstance(parameters, list) or len(parameters) != 1 or not isinstance(parameters[0], (int, float)):
                    issues.append({"path": f"{path}.parameters", "message": "幂运算必须配置一个数值指数。"})
            if isinstance(key, str) and key.isidentifier():
                known_values.add(key)

        for index, chart in enumerate(schema.get("charts", [])):
            path = f"charts[{index}]"
            if chart.get("type") not in ALLOWED_CHARTS:
                issues.append({"path": f"{path}.type", "message": "首期图表仅支持散点图。"})
            if chart.get("x") not in known_values or chart.get("y") not in known_values:
                issues.append({"path": path, "message": "图表坐标轴必须引用已定义字段或计算结果。"})
            if chart.get("fit") not in (None, "linear"):
                issues.append({"path": f"{path}.fit", "message": "首期仅支持线性拟合。"})

        for index, check in enumerate(schema.get("checks", [])):
            if check.get("type") not in {"minimum_rows", "range", "r_squared_below"}:
                issues.append({"path": f"checks[{index}].type", "message": "校验规则不受支持。"})
        artifacts = schema.get("requiredArtifacts", [])
        if not isinstance(artifacts, list) or any(item not in ALLOWED_ARTIFACTS for item in artifacts):
            issues.append({"path": "requiredArtifacts", "message": "提交要求包含不受支持的类型。"})
        return issues

    def publish(self, db: Session, template: ExperimentTemplate) -> TemplateVersion:
        issues = self.validate(template.draft_schema_json)
        if issues:
            raise AuthError("invalid_template", "模板验证未通过，不能发布。", 422)
        current = db.scalar(
            select(func.max(TemplateVersion.version_number)).where(TemplateVersion.template_id == template.id)
        )
        version = TemplateVersion(
            template_id=template.id,
            version_number=int(current or 0) + 1,
            schema_json=deepcopy(template.draft_schema_json),
            published_at=datetime.now(UTC),
        )
        template.status = "published"
        template.updated_at = version.published_at
        db.add(version)
        db.commit()
        db.refresh(version)
        return version
