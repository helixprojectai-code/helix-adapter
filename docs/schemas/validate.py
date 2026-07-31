#!/usr/bin/env python3
"""
Helix Element Schema Validator
Validates MD/JSON isomorphism and schema conformance.
"""

import json
import re
import sys
from pathlib import Path
from datetime import datetime
from typing import Tuple, List, Dict, Any

import yaml


class SchemaValidator:
    def __init__(self, schema_path: str = None):
        """Load the canonical schema."""
        if schema_path is None:
            schema_path = Path(__file__).parent / "schema.json"

        with open(schema_path) as f:
            self.schema = json.load(f)

        self.required_fields = self.schema.get("required", [])
        self.properties = self.schema.get("properties", {})
        self.errors = []
        self.warnings = []

    def validate_file(self, filepath: Path) -> Tuple[bool, List[str], List[str]]:
        """
        Validate a single MD file.
        Returns: (is_valid, errors, warnings)
        """
        self.errors = []
        self.warnings = []

        if not filepath.exists():
            self.errors.append(f"File not found: {filepath}")
            return False, self.errors, self.warnings

        # Parse MD
        try:
            metadata, body = self._parse_md(filepath)
        except Exception as e:
            self.errors.append(f"Failed to parse MD: {e}")
            return False, self.errors, self.warnings

        # If no metadata (markdown-only file), flag for migration
        if not metadata:
            self.warnings.append("Needs migration: no YAML frontmatter present")
            # Skip further validation for non-conformant files
            return False, self.errors, self.warnings

        # Check if this is a legacy document
        is_legacy = metadata.get("legacy", False)

        # Check required fields (skip if legacy)
        if not is_legacy:
            for field in self.required_fields:
                if field not in metadata:
                    self.errors.append(f"Missing required field: {field}")
        else:
            # For legacy docs, track what's missing but don't fail
            missing = []
            for field in self.required_fields:
                if field not in metadata:
                    missing.append(field)
            if missing:
                self.warnings.append(f"Legacy document missing fields: {', '.join(missing)}")

        # Validate field types and enums
        for field, value in metadata.items():
            if field not in self.properties:
                self.warnings.append(f"Unknown field: {field}")
                continue

            prop_schema = self.properties[field]

            # Check enum constraints
            if "enum" in prop_schema:
                if value not in prop_schema["enum"]:
                    self.errors.append(
                        f"Invalid value for {field}: {value}. "
                        f"Must be one of: {prop_schema['enum']}"
                    )

            # Check type (skip for timestamp/date which have special handling)
            if field not in ["timestamp", "date"]:
                expected_type = prop_schema.get("type")
                if expected_type:
                    if not self._check_type(value, expected_type):
                        self.errors.append(
                            f"Wrong type for {field}: expected {expected_type}, got {type(value).__name__}"
                        )

            # Check format constraints
            if field == "timestamp":
                # YAML auto-parses ISO 8601 strings as datetime objects; accept both
                from datetime import datetime as dt
                if isinstance(value, str):
                    if not self._is_iso8601(value):
                        self.errors.append(f"Invalid ISO 8601 timestamp: {value}")
                elif not isinstance(value, dt):
                    self.errors.append(f"Timestamp must be ISO 8601 string or datetime object, got {type(value).__name__}")
            elif field == "date":
                # YAML auto-parses YYYY-MM-DD as date objects; accept both
                from datetime import date as dt_date
                if isinstance(value, str):
                    if not self._is_date(value):
                        self.errors.append(f"Invalid date format (YYYY-MM-DD): {value}")
                elif not isinstance(value, dt_date):
                    self.errors.append(f"Date must be YYYY-MM-DD string or date object, got {type(value).__name__}")
            elif field == "schema_version":
                if not re.match(r"^v\d+\.\d+\.\d+$", value):
                    self.errors.append(f"Invalid schema_version format: {value}")
            elif field == "id":
                if not re.match(r"^[a-zA-Z0-9_-]+$", value):
                    self.errors.append(f"Invalid ID format: {value}")

        # Check epistemic framing
        if "epistemic_frame" in metadata:
            self._validate_epistemic_frame(metadata["epistemic_frame"])

        # Check isomorphism
        self._check_isomorphism(filepath, metadata, body)

        return len(self.errors) == 0, self.errors, self.warnings

    def _parse_md(self, filepath: Path) -> Tuple[Dict[str, Any], str]:
        """Parse MD file into metadata and body."""
        content = filepath.read_text()

        # Check if file has YAML frontmatter
        if not content.startswith("---"):
            # Current state: markdown-only (no frontmatter yet)
            # Flag as migration-needed, return minimal metadata
            self.warnings.append("No YAML frontmatter — file needs migration to canonical schema")
            return {}, content

        # Future state: has YAML frontmatter
        # Split on ---
        parts = content.split("---", 2)  # Split on first two --- only
        if len(parts) < 3:
            raise ValueError("Invalid MD format: missing frontmatter delimiters")

        frontmatter = parts[1].strip()
        body = parts[2].strip()

        # Parse YAML frontmatter
        try:
            metadata = yaml.safe_load(frontmatter) or {}
        except yaml.YAMLError as e:
            raise ValueError(f"Invalid YAML frontmatter: {e}")

        # Add body if not already present
        if "body" not in metadata and body:
            metadata["body"] = body

        return metadata, body

    def _check_type(self, value: Any, expected_type: str) -> bool:
        """Check if value matches expected type."""
        type_map = {
            "string": str,
            "integer": int,
            "boolean": bool,
            "array": list,
            "object": dict,
        }
        expected = type_map.get(expected_type)
        return isinstance(value, expected) if expected else True

    def _is_iso8601(self, value: str) -> bool:
        """Check if value is valid ISO 8601 timestamp."""
        try:
            datetime.fromisoformat(value.replace("Z", "+00:00"))
            return True
        except (ValueError, AttributeError):
            return False

    def _is_date(self, value: str) -> bool:
        """Check if value is valid YYYY-MM-DD date."""
        try:
            datetime.strptime(value, "%Y-%m-%d")
            return True
        except ValueError:
            return False

    def _validate_epistemic_frame(self, frame: List[Dict]) -> None:
        """Validate epistemic frame entries."""
        if not isinstance(frame, list):
            self.errors.append("epistemic_frame must be an array")
            return

        for i, entry in enumerate(frame):
            if not isinstance(entry, dict):
                self.errors.append(f"epistemic_frame[{i}] must be an object")
                continue

            if "claim" not in entry:
                self.errors.append(f"epistemic_frame[{i}] missing 'claim' field")

            if "frame" not in entry:
                self.errors.append(f"epistemic_frame[{i}] missing 'frame' field")
            elif entry["frame"] not in ["FACT", "HYPOTHESIS", "ASSUMPTION"]:
                self.errors.append(
                    f"epistemic_frame[{i}]['frame'] invalid: {entry['frame']}. "
                    "Must be FACT, HYPOTHESIS, or ASSUMPTION"
                )

    def _check_isomorphism(self, filepath: Path, metadata: Dict, body: str) -> None:
        """Verify MD → JSON → MD round-trip consistency."""
        try:
            # Serialize to JSON
            json_str = json.dumps(metadata, indent=2, default=str)
            reparsed = json.loads(json_str)

            # Check key preservation
            if set(reparsed.keys()) != set(metadata.keys()):
                self.warnings.append("Isomorphism warning: key set changed during JSON round-trip")

            # Check body preservation
            if "body" in metadata and body:
                # Body might have leading/trailing whitespace variations
                original_body = metadata.get("body", "").strip()
                if original_body and original_body not in body:
                    self.warnings.append("Isomorphism warning: body content may not round-trip cleanly")

        except Exception as e:
            self.errors.append(f"Isomorphism check failed: {e}")

    def validate_directory(self, dirpath: Path, pattern: str = "*.md") -> Dict[str, Tuple[bool, List, List]]:
        """Validate all files matching pattern in directory."""
        results = {}
        for filepath in sorted(dirpath.glob(pattern)):
            is_valid, errors, warnings = self.validate_file(filepath)
            results[str(filepath.relative_to(dirpath))] = (is_valid, errors, warnings)
        return results


def main():
    """CLI entry point."""
    import argparse

    parser = argparse.ArgumentParser(description="Validate Helix elements")
    parser.add_argument("path", help="File or directory to validate")
    parser.add_argument("--schema", help="Path to schema.json")
    parser.add_argument("--show-warnings", action="store_true", help="Show warnings")

    args = parser.parse_args()

    validator = SchemaValidator(args.schema)
    path = Path(args.path)

    if path.is_file():
        is_valid, errors, warnings = validator.validate_file(path)
        if errors:
            print(f"❌ {path}")
            for err in errors:
                print(f"  ERROR: {err}")
        if warnings and args.show_warnings:
            for warn in warnings:
                print(f"  WARN: {warn}")
        if is_valid:
            print(f"✅ {path}")
        sys.exit(0 if is_valid else 1)

    elif path.is_dir():
        results = validator.validate_directory(path)

        total = len(results)
        valid = sum(1 for v, _, _ in results.values() if v)

        print(f"\n📊 Validation Report: {valid}/{total} valid")
        print("=" * 60)

        for filepath, (is_valid, errors, warnings) in sorted(results.items()):
            status = "✅" if is_valid else "❌"
            print(f"{status} {filepath}")

            for err in errors:
                print(f"   ERROR: {err}")

            if args.show_warnings:
                for warn in warnings:
                    print(f"   WARN: {warn}")

        print("=" * 60)
        sys.exit(0 if valid == total else 1)


if __name__ == "__main__":
    main()
