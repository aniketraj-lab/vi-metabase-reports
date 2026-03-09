#!/usr/bin/env python3
import os
import requests
import tempfile
import zipfile
import smtplib
import ssl
from email.message import EmailMessage
from datetime import datetime
import re

# ---------- Environment ----------
METABASE_SITE = os.getenv("METABASE_SITE").rstrip("/")
METABASE_API_KEY = os.getenv("METABASE_API_KEY")

SMTP_HOST = os.getenv("SMTP_HOST")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_USER = os.getenv("SMTP_USER")
SMTP_PASS = os.getenv("SMTP_PASS")
FROM_EMAIL = os.getenv("FROM_EMAIL")
TO_EMAIL = os.getenv("TO_EMAIL")
CC_EMAIL = os.getenv("CC_EMAIL", "")

CARD_IDS = [8964, 8965]
CARD_PARAMS = {}
VERIFY_SSL = True

# ---------- Helpers ----------
def clean_filename(name):
    return re.sub(r'[^A-Za-z0-9]+', '_', name).strip('_')

def make_session():
    s = requests.Session()
    s.headers.update({"x-api-key": METABASE_API_KEY})
    return s

def get_card_name(session, card_id):
    url = f"{METABASE_SITE}/api/card/{card_id}"
    r = session.get(url, verify=VERIFY_SSL, timeout=30)
    r.raise_for_status()
    return r.json().get("name", f"Card_{card_id}")

def build_params(params_dict):
    params = []
    for k, v in (params_dict or {}).items():
        params.append({
            "type": "category",
            "target": ["variable", "template-tag", k],
            "value": v
        })
    return params

def download_card_csv(session, card_id, out_path, params=None):
    url = f"{METABASE_SITE}/api/card/{card_id}/query/csv"
    payload = {}
    if params:
        payload["parameters"] = build_params(params)
    r = session.post(url, json=payload, verify=VERIFY_SSL, timeout=60)
    r.raise_for_status()
    with open(out_path, "wb") as f:
        f.write(r.content)

def make_zip(files, zip_path):
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as z:
        for p in files:
            z.write(p, arcname=os.path.basename(p))

# ---------- Email ----------
def send_email(zip_path):
    subject = "VI Daily Reports (D-1), Yesterday"

    body = (
        "Hi Team,\n\n"
        "Please find Immediate Callback Report & Disposition History Report "
        "for yesterday's campaigns attached below.\n\n"
        "Thank You\n"
    )

    # Parse recipients
    to_list = [e.strip() for e in TO_EMAIL.split(",") if e.strip()]
    cc_list = [e.strip() for e in CC_EMAIL.split(",") if e.strip()]

    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = FROM_EMAIL
    msg["To"] = ", ".join(to_list)
    if cc_list:
        msg["Cc"] = ", ".join(cc_list)
    msg.set_content(body)

    # Attach zip
    with open(zip_path, "rb") as f:
        msg.add_attachment(
            f.read(),
            maintype="application",
            subtype="zip",
            filename=os.path.basename(zip_path)
        )

    # Final recipient list
    recipients = to_list + cc_list

    context = ssl.create_default_context()
    with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as smtp:
        smtp.starttls(context=context)
        smtp.login(SMTP_USER, SMTP_PASS)
        smtp.send_message(msg, from_addr=FROM_EMAIL, to_addrs=recipients)

# ---------- Main ----------
def main():
    session = make_session()
    tmpdir = tempfile.mkdtemp(prefix="metabase_export_")
    csv_paths = []

    try:
        # Download each card
        for cid in CARD_IDS:
            card_name = get_card_name(session, cid)
            clean_name = clean_filename(card_name)
            csv_path = os.path.join(tmpdir, f"{clean_name}.csv")

            print(f"Downloading: {card_name} → {csv_path}")

            params = CARD_PARAMS.get(str(cid)) or CARD_PARAMS.get(cid) or None
            download_card_csv(session, cid, csv_path, params=params)
            csv_paths.append(csv_path)

        # Create zip
        zip_path = os.path.join(
            tmpdir,
            f"VI_Daily_Reports_{datetime.now().strftime('%Y%m%d')}.zip"
        )
        make_zip(csv_paths, zip_path)

        print("Sending email...")
        send_email(zip_path)
        print("Email sent!")

    finally:
        # Clean up
        for f in csv_paths:
            try: os.remove(f)
            except: pass
        try: os.remove(zip_path)
        except: pass

if __name__ == "__main__":
    main()
