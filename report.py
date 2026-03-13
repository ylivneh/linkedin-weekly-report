import os
import time
import json
import csv
import requests
import smtplib
from email.message import EmailMessage

# --------------------------
# CONFIG
# --------------------------

APIFY_TOKEN = os.environ["APIFY_TOKEN"]
ACTOR_ID = "WI0tj4Ieb5Kq458gB"

SENDER_EMAIL = "ylivneh@gmail.com"
SENDER_APP_PASSWORD = os.environ["GMAIL_APP_PASSWORD"]
RECIPIENT_EMAIL = "ylivneh@gmail.com"

OUTPUT_JSON = "linkedin_data.json"
OUTPUT_CSV = "linkedin_report.csv"

# --------------------------
# RUN ACTOR
# --------------------------

def run_actor():

    url = f"https://api.apify.com/v2/actors/{ACTOR_ID}/runs?token={APIFY_TOKEN}"

    print("Starting Apify actor...")

    response = requests.post(url)

    response.raise_for_status()

    run = response.json()["data"]

    run_id = run["id"]

    print("Actor run started:", run_id)

    return run_id


# --------------------------
# WAIT FOR FINISH
# --------------------------

def wait_for_actor(run_id):

    url = f"https://api.apify.com/v2/actor-runs/{run_id}?token={APIFY_TOKEN}"

    print("Waiting for actor to finish...")

    while True:

        r = requests.get(url)

        r.raise_for_status()

        data = r.json()["data"]

        status = data["status"]

        print("Status:", status)

        if status in ["SUCCEEDED", "FAILED", "ABORTED"]:

            if status != "SUCCEEDED":

                raise Exception("Actor failed")

            dataset_id = data["defaultDatasetId"]

            return dataset_id

        time.sleep(10)


# --------------------------
# DOWNLOAD DATASET
# --------------------------

def download_dataset(dataset_id):

    url = f"https://api.apify.com/v2/datasets/{dataset_id}/items?token={APIFY_TOKEN}"

    r = requests.get(url)

    r.raise_for_status()

    data = r.json()

    with open(OUTPUT_JSON, "w") as f:

        json.dump(data, f, indent=2)

    print("Dataset downloaded:", len(data), "posts")

    return data


# --------------------------
# CREATE CSV REPORT
# --------------------------

def create_csv(data):

    rows = []

    for item in data:

        rows.append({

            "Company": item.get("companyName"),

            "Post Date": item.get("postedAt"),

            "Reactions": item.get("reactionsCount", 0),

            "Comments": item.get("commentsCount", 0),

            "Post URL": item.get("postUrl"),

            "Text": item.get("text", "").replace("\n"," ")

        })

    with open(OUTPUT_CSV, "w", newline="", encoding="utf-8") as f:

        writer = csv.DictWriter(f, fieldnames=rows[0].keys())

        writer.writeheader()

        writer.writerows(rows)

    print("CSV report created")

    return OUTPUT_CSV


# --------------------------
# SEND EMAIL
# --------------------------

def send_email(file):

    msg = EmailMessage()

    msg["Subject"] = "Weekly LinkedIn Activity Report"

    msg["From"] = SENDER_EMAIL

    msg["To"] = RECIPIENT_EMAIL

    msg.set_content("Attached is the weekly LinkedIn posts report.")

    with open(file, "rb") as f:

        msg.add_attachment(

            f.read(),

            maintype="application",

            subtype="csv",

            filename=file

        )

    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as smtp:

        smtp.login(SENDER_EMAIL, SENDER_APP_PASSWORD)

        smtp.send_message(msg)

    print("Email sent")


# --------------------------
# MAIN
# --------------------------

def main():

    run_id = run_actor()

    dataset_id = wait_for_actor(run_id)

    data = download_dataset(dataset_id)

    csv_file = create_csv(data)

    send_email(csv_file)


if __name__ == "__main__":

    main()
