import os
import time
import json
import csv
import requests
import smtplib
from email.message import EmailMessage

# --------------------------
# CONFIGURATION
# --------------------------
APIFY_TOKEN = os.environ.get("APIFY_TOKEN")
ACTOR_ID = "WI0tj4Ieb5Kq458gB"  
OUTPUT_FILE_JSON = "linkedin_data.json"
OUTPUT_FILE_CSV = "linkedin_report.csv"

SENDER_EMAIL = "ylivneh@gmail.com"        # your Gmail address
SENDER_APP_PASSWORD = os.environ.get("GMAIL_APP_PASSWORD")
RECIPIENT_EMAIL = "ylivneh@gmail.com"     # same as your email

# --------------------------
# 1. RUN ACTOR
# --------------------------
def run_actor():
    url = f"https://api.apify.com/v2/actors/{ACTOR_ID}/runs?token={APIFY_TOKEN}"
    # If you want to pass input, you can include it as JSON here
    data = {}  # leave empty if using default actor configuration
    response = requests.post(url, json=data)
    response.raise_for_status()
    run_data = response.json()
    run_id = run_data["data"]["id"]
    print(f"Actor run started: {run_id}")
    return run_id

# --------------------------
# 2. WAIT FOR ACTOR TO FINISH
# --------------------------
def wait_for_completion(run_id):
    url = f"https://api.apify.com/v2/actor-runs/{run_id}"
    headers = {"Authorization": f"Bearer {APIFY_TOKEN}"}
    print("Waiting for actor to finish...")
    while True:
        resp = requests.get(url, headers=headers)
        resp.raise_for_status()
        run_info = resp.json()["data"]
        status = run_info["status"]
        if status in ["SUCCEEDED", "FAILED", "ABORTED"]:
            print(f"Actor finished with status: {status}")
            if status != "SUCCEEDED":
                raise RuntimeError(f"Actor run did not succeed: {status}")
            break
        time.sleep(10)

# --------------------------
# 3. DOWNLOAD DATASET
# --------------------------
def download_dataset(run_id, output_json=OUTPUT_FILE_JSON):
    url = f"https://api.apify.com/v2/actor-runs/{run_id}/dataset/items?format=json"
    headers = {"Authorization": f"Bearer {APIFY_TOKEN}"}
    response = requests.get(url, headers=headers)
    response.raise_for_status()
    data = response.json()
    with open(output_json, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"Dataset saved to {output_json}")
    return data

# --------------------------
# 4. GENERATE CSV REPORT
# --------------------------
def generate_csv_report(data, output_csv=OUTPUT_FILE_CSV):
    rows = []
    for item in data:
        row = {
            "postUrl": item.get("postUrl"),
            "author": item.get("authorName"),
            "date": item.get("postedAt"),
            "reactionsCount": item.get("reactionsCount", 0),
            "commentsCount": item.get("commentsCount", 0),
            "content": item.get("content", "").replace("\n", " ")
        }
        rows.append(row)
    with open(output_csv, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=rows[0].keys())
        writer.writeheader()
        writer.writerows(rows)
    print(f"CSV report generated: {output_csv}")
    return output_csv

# --------------------------
# 5. SEND EMAIL
# --------------------------
def send_email(file_path, subject="Weekly LinkedIn Report"):
    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = SENDER_EMAIL
    msg["To"] = RECIPIENT_EMAIL
    msg.set_content("Attached is this week's LinkedIn posts report.")
    with open(file_path, "rb") as f:
        file_data = f.read()
        file_name = os.path.basename(file_path)
    msg.add_attachment(file_data, maintype="application", subtype="octet-stream", filename=file_name)
    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as smtp:
        smtp.login(SENDER_EMAIL, SENDER_APP_PASSWORD)
        smtp.send_message(msg)
    print(f"Email sent to {RECIPIENT_EMAIL}")

# --------------------------
# MAIN FLOW
# --------------------------
if __name__ == "__main__":
    run_id = run_actor()
    wait_for_completion(run_id)
    data = download_dataset(run_id)
    csv_file = generate_csv_report(data)
    send_email(csv_file)
