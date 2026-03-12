# report.py
import os
import requests
from datetime import datetime, timedelta
import openai
import smtplib
from email.mime.text import MIMEText

# -----------------------------
# 1️⃣ Configuration
# -----------------------------
APIFY_DATASET_URL = "https://api.apify.com/v2/datasets/XXXXXXXX/items?format=json"  # <-- replace with your dataset URL

# GitHub Actions secrets
openai.api_key = os.environ["OPENAI_API_KEY"]
GMAIL_USER = os.environ["GMAIL_USER"]
GMAIL_APP_PASSWORD = os.environ["GMAIL_APP_PASSWORD"]
TO_EMAIL = GMAIL_USER  # send to yourself; can change to other email if needed

# -----------------------------
# 2️⃣ Fetch data from Apify
# -----------------------------
response = requests.get(APIFY_DATASET_URL)
if response.status_code != 200:
    raise Exception(f"Failed to fetch dataset: {response.status_code}")
data = response.json()

# -----------------------------
# 3️⃣ Filter posts from last 7 days
# -----------------------------
seven_days_ago = datetime.utcnow() - timedelta(days=7)
recent_posts = [
    p for p in data
    if "timestamp" in p and datetime.fromisoformat(p["timestamp"][:-1]) >= seven_days_ago
]

if not recent_posts:
    report_text = "No LinkedIn posts found in the last 7 days."
else:
    # -----------------------------
    # 4️⃣ Aggregate metrics per profile
    # -----------------------------
    report_data = {}
    for post in recent_posts:
        profile = post.get("profileName") or post.get("companyName") or "Unknown"
        if profile not in report_data:
            report_data[profile] = {"posts": 0, "likes": 0, "comments": 0, "reposts": 0, "top_post": None}
        report_data[profile]["posts"] += 1
        report_data[profile]["likes"] += post.get("reactions", 0)
        report_data[profile]["comments"] += post.get("comments", 0)
        report_data[profile]["reposts"] += post.get("reposts", 0)

        # track top post by likes
        if (report_data[profile]["top_post"] is None or
            post.get("reactions", 0) > report_data[profile]["top_post"].get("reactions", 0)):
            report_data[profile]["top_post"] = post

    # -----------------------------
    # 5️⃣ Prepare prompt for GPT
    # -----------------------------
    gpt_prompt = "Generate a human-readable weekly LinkedIn engagement report:\n\n"
    for profile, metrics in report_data.items():
        gpt_prompt += f"Profile: {profile}\n"
        gpt_prompt += f"Posts: {metrics['posts']}\n"
        gpt_prompt += f"Likes: {metrics['likes']}\n"
        gpt_prompt += f"Comments: {metrics['comments']}\n"
        gpt_prompt += f"Reposts: {metrics['reposts']}\n"
        top = metrics["top_post"]
        if top:
            snippet = top.get('postText','')[:100].replace('\n',' ')
            gpt_prompt += f"Top post snippet: \"{snippet}...\" with {top.get('reactions',0)} likes\n"
        gpt_prompt += "\n"

    # -----------------------------
    # 6️⃣ Ask GPT to make it human-readable
    # -----------------------------
    completion = openai.ChatCompletion.create(
        model="gpt-4",
        messages=[{"role": "user", "content": gpt_prompt}]
    )
    report_text = completion.choices[0].message.content

# -----------------------------
# 7️⃣ Send email via Gmail
# -----------------------------
msg = MIMEText(report_text)
msg['Subject'] = f"Weekly LinkedIn Report - {datetime.utcnow().date()}"
msg['From'] = GMAIL_USER
msg['To'] = TO_EMAIL

with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
    server.login(GMAIL_USER, GMAIL_APP_PASSWORD)
    server.send_message(msg)

print("Weekly LinkedIn report sent successfully!")
