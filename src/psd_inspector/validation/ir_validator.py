"""JSON Schema validation for Design IR documents."""

from pathlib import Path
from typing import Any, Dict, List, Optional
import json
import os


def default_schema_path() -> Optional[Path]:
    """Locate the bundled schema without assuming a specific install layout."""
    override = os.environ.get("PSD_INSPECTOR_SCHEMA")
    if override:
        candidate = Path(override)
        return candidate if candidate.is_file() else None

    candidates = [
        Path(__file__).resolve().parents[3] / "schemas" / "design-ir.schema.json",
        Path.cwd() / "schemas" / "design-ir.schema.json",
    ]
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    return None


def validate_design_ir(
    ir: Dict[str, Any], schema_path: Optional[Path] = None
) -> Dict[str, Any]:
    """Validate an IR payload against ``design-ir.schema.json``.

    Returns a report with ``status`` set to ``valid``, ``invalid`` or
    ``unavailable``. A missing schema or missing ``jsonschema`` dependency
    degrades to ``unavailable`` instead of failing the run.
    """
    path = Path(schema_path) if schema_path else default_schema_path()
    if path is None or not path.is_file():
        return {
            "status": "unavailable",
            "schemaPath": None,
            "errors": [],
            "warning": "schemas/design-ir.schema.json was not found; validation was skipped.",
        }

    try:
        from jsonschema import Draft7Validator
    except ImportError:
        return {
            "status": "unavailable",
            "schemaPath": str(path),
            "errors": [],
            "warning": "jsonschema is not installed; validation was skipped.",
        }

    try:
        with open(path, "r", encoding="utf-8") as handle:
            schema = json.load(handle)
        validator = Draft7Validator(schema)
        errors = sorted(
            validator.iter_errors(ir),
            key=lambda error: (list(error.absolute_path), error.message),
        )
    except (OSError, ValueError) as error:
        return {
            "status": "unavailable",
            "schemaPath": str(path),
            "errors": [],
            "warning": f"Schema could not be loaded: {error}",
        }

    return {
        "status": "valid" if not errors else "invalid",
        "schemaPath": str(path),
        "errors": [_format_error(error) for error in errors],
        "warning": None,
    }


def _format_error(error: Any) -> Dict[str, Any]:
    path = "$"
    for part in error.absolute_path:
        path += f"[{part}]" if isinstance(part, int) else f".{part}"
    result = {
        "path": path,
        "message": error.message,
        "validator": error.validator,
    }
    if error.validator_value is not None:
        result["validatorValue"] = error.validator_value
    return result


def validation_results(report: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Project a validation report into ``diagnostics.validationResults``."""
    if report["status"] == "valid":
        return []
    if report["status"] == "unavailable":
        return [{"level": "warning", "message": report.get("warning", "Validation unavailable.")}]
    return [{"level": "error", **error} for error in report["errors"]]
