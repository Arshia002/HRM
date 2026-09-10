from __future__ import annotations

import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
INNO_SCRIPT = ROOT / "build" / "windows" / "HRM.iss"


class InnoPascalDeclarationOrderTests(unittest.TestCase):
    def test_internal_helpers_are_declared_before_first_use(self) -> None:
        lines = INNO_SCRIPT.read_text(encoding="utf-8").splitlines()

        implementations: dict[str, int] = {}
        forward_declarations: dict[str, list[int]] = {}

        declaration_re = re.compile(
            r"\s*(?:procedure|function)\s+([A-Za-z_][A-Za-z0-9_]*)\b",
            re.IGNORECASE,
        )

        for line_no, line in enumerate(lines, 1):
            match = declaration_re.match(line)
            if not match:
                continue
            name = match.group(1)
            if "forward;" in line.lower():
                forward_declarations.setdefault(name, []).append(line_no)
            else:
                implementations.setdefault(name, line_no)

        unresolved: list[str] = []
        for name, implementation_line in implementations.items():
            call_re = re.compile(r"\b" + re.escape(name) + r"\s*\(", re.IGNORECASE)
            first_call = None

            for line_no, line in enumerate(lines[: implementation_line - 1], 1):
                if declaration_re.match(line):
                    continue
                if call_re.search(line):
                    first_call = line_no
                    break

            if first_call is None:
                continue

            declarations = forward_declarations.get(name, [])
            if not any(line_no < first_call for line_no in declarations):
                unresolved.append(
                    f"{name}: first_call={first_call}, implementation={implementation_line}"
                )

        self.assertEqual(
            [],
            unresolved,
            "Inno Pascal helper(s) are used before declaration: " + "; ".join(unresolved),
        )


if __name__ == "__main__":
    unittest.main()
