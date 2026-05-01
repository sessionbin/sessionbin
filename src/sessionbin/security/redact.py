import json
import subprocess
import tempfile
from pathlib import Path


class RedactionError(Exception):
    pass


def redact_secrets(raw: bytes) -> bytes:
    """Run gitleaks on raw bytes, return bytes with all secrets replaced
    by <REDACTED>. Raises RedactionError on subprocess failure or timeout."""
    with tempfile.TemporaryDirectory() as tmpdir:
        input_path = Path(tmpdir) / "input.txt"
        report_path = Path(tmpdir) / "findings.json"
        input_path.write_bytes(raw)

        try:
            result = subprocess.run(
                [
                    "gitleaks",
                    "detect",
                    "--no-git",
                    "--no-banner",
                    "--report-format=json",
                    f"--report-path={report_path}",
                    f"--source={tmpdir}",
                ],
                capture_output=True,
                timeout=30,
            )
        except FileNotFoundError as exc:
            raise RedactionError("gitleaks is not installed") from exc
        except subprocess.TimeoutExpired as exc:
            raise RedactionError("gitleaks timed out") from exc

        if result.returncode == 0:
            return raw
        if result.returncode != 1:
            stderr = result.stderr.decode(errors="replace")
            raise RedactionError(f"gitleaks exited with code {result.returncode}: {stderr}")

        findings = json.loads(report_path.read_text())
        secrets = sorted(
            {f["Secret"] for f in findings if f.get("Secret")},
            key=len,
            reverse=True,
        )
        out = raw
        for secret in secrets:
            out = out.replace(secret.encode(), b"<REDACTED>")
        return out
