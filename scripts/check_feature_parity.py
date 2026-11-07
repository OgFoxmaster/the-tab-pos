"""Static release gate for the shared web/Android feature matrix.

This intentionally checks for implementation markers, not test completion. A human or
integration test must still prove a feature works on both clients before changing its
status in FEATURE_PARITY.md.
"""
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
CHECKS = {
    "web API client": ROOT / "web/src/api.js",
    "web application": ROOT / "web/src/main.jsx",
    "Flutter application": ROOT / "mobile/lib/pos_app.dart",
    "FastAPI backend": ROOT / "backend/app/main.py",
}
REQUIRED_MARKERS = {
    "web API client": ["/login", "/products", "/sales", "/inventory", "/users"],
    "web application": ["function Login", "function PointOfSale", "function Inventory", "function Reports", "function Users"],
    "Flutter application": ["class LoginPage", "class HomePage", "class _PosView", "class _InventoryView"],
    "FastAPI backend": ["/login", "/products", "/sales", "/inventory", "/company", "tenant_filter"],
}


def main() -> int:
    failures = []
    for name, path in CHECKS.items():
        if not path.exists():
            failures.append(f"{name}: missing {path.relative_to(ROOT)}")
            continue
        content = path.read_text(encoding="utf-8")
        for marker in REQUIRED_MARKERS[name]:
            if marker not in content:
                failures.append(f"{name}: missing marker {marker!r}")

    matrix = ROOT / "FEATURE_PARITY.md"
    if not matrix.exists():
        failures.append("FEATURE_PARITY.md is missing")
    else:
        content = matrix.read_text(encoding="utf-8")
        if "Both tested" not in content:
            failures.append("FEATURE_PARITY.md must define the Both tested release gate")
        if not re.search(r"\| Feature \| Web \| Android APK \| Both tested", content):
            failures.append("FEATURE_PARITY.md has no release matrix")

    if failures:
        print("Feature parity check failed:")
        print("\n".join(f"- {failure}" for failure in failures))
        return 1

    print("Feature parity contract is present.")
    print("Note: this static check does not claim that unchecked features are implemented or tested.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
