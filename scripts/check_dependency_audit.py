"""CI gate: distinguish completed findings from unavailable/broken scans."""
import json
import sys
from pathlib import Path


def check(kind, content, exit_code):
    if kind == "pip":
        report = json.loads(content)
        dependencies = report.get("dependencies")
        if not isinstance(dependencies, list) or not dependencies:
            raise ValueError("Backend dependency report missing/empty")
        if any("skip_reason" in dep or not isinstance(dep.get("vulns"), list) for dep in dependencies):
            raise ValueError("Some backend dependencies could not be audited")
        findings = sum(len(dep["vulns"]) for dep in dependencies)
        if exit_code not in (0, 1) or bool(findings) != bool(exit_code):
            raise ValueError("Backend scan exit status disagrees with report")
        return findings == 0, f"Backend: {findings} bilinen bağımlılık açığı."
    if kind == "yarn":
        events = [json.loads(line) for line in content.splitlines() if line.strip()]
        if any(event.get("type") == "error" for event in events):
            raise ValueError("Frontend dependency scanner returned an error")
        summaries = [e["data"] for e in events if e.get("type") == "auditSummary"]
        if len(summaries) != 1 or exit_code < 0 or exit_code > 31:
            raise ValueError("Frontend scan did not finish with a valid summary")
        counts = summaries[0].get("vulnerabilities", {})
        keys = ("info", "low", "moderate", "high", "critical")
        if any(not isinstance(counts.get(k), int) or counts[k] < 0 for k in keys):
            raise ValueError("Frontend severity counts missing")
        expected = sum(1 << i for i, k in enumerate(keys) if counts[k])
        if expected != exit_code:
            raise ValueError("Frontend scan exit status disagrees with report")
        severe = counts["high"] + counts["critical"]
        return severe == 0, f"Frontend: {counts['high']} yüksek, {counts['critical']} kritik; {counts['low'] + counts['moderate']} düşük/orta."
    raise ValueError("Unknown scanner")


if __name__ == "__main__":
    try:
        ok, message = check(sys.argv[1], Path(sys.argv[2]).read_text(), int(sys.argv[3]))
    except (OSError, ValueError, KeyError, TypeError, IndexError) as exc:
        print(f"Tarama doğrulanamadı — temiz kabul edilmedi: {exc}")
        sys.exit(2)
    print(message)
    sys.exit(0 if ok else 1)
