import os
import requests
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import openai

# -------------------------------
# CONFIG
# -------------------------------
# Profiles to report
PROFILES = [
    "https://www.linkedin.com/company/leumitech",
    "https://www.linkedin.com/company/profile2",
    "https://www.linkedin.com/company/profile3"
]

# Apify actor dataset URL pattern (replace with your actor's dataset URL)
DATASET_URL_PATTERN = "https://api.apify.com/v2/datasets/Wd6zOMJVOvC75PB9D/items?format=json&clean=true"

# Email config from GitHub Secrets
GMAIL_USER = os.environ["GMAIL_USER"]
GMAIL_APP_PASSWORD = os.environ["GMAIL_APP_PASSWORD"]

# OpenAI config
openai.api_key = os.environ["OPENAI_API_KEY"]

# -------------------------------
# FUNCTIONS
# -------------------------------

def fetch_posts(profile_url):
    """Fetch posts for a given LinkedIn profile from Apify dataset"""
    url = DATASET_URL_PATTERN.format(profile=profile_url)
    resp = requests.get(url)
    resp.raise_for_status()
    data = resp.json()
    return data

def summarize_posts(data):
    """Aggregate posts, reactions, comments, reposts"""
    total_posts = len(data)
    summary = []
    for post in data:
        summary.append({
            "text": post.get("text", ""),
            "likes": post.get("reactionsCount", 0),
            "comments": post.get("commentsCount", 0),
            "reposts": post.get("sharesCount", 0)
        })
    return total_posts, summary

def generate_gpt_report(profile_summaries):
    """Use GPT to create a human-readable weekly report"""
    prompt = "Create a concise weekly LinkedIn activity report:\n\n"
    for profile, (total_posts, summary) in profile_summaries.items():
        prompt += f"Profile: {profile}\nTotal Posts: {total_posts}\n"
        for i, post in enumerate(summary, 1):
            prompt += f"Post {i}: Likes={post['likes']}, Comments={post['comments']}, Reposts={post['reposts']}\n"
        prompt += "\n"
    
    response = openai.ChatCompletion.create(
        model="gpt-4",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.5
    )
    
    report_text = response.choices[0].message.content
    return report_text

def send_email(report_text):
    """Send the report via Gmail"""
    msg = MIMEMultipart()
    msg["From"] = GMAIL_USER
    msg["To"] = GMAIL_USER
    msg["Subject"] = "Weekly LinkedIn Activity Report"
    
    msg.attach(MIMEText(report_text, "plain"))
    
    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
        server.login(GMAIL_USER, GMAIL_APP_PASSWORD)
        server.send_message(msg)

# -------------------------------
# MAIN
# -------------------------------
def main():
    profile_summaries = {}
    for profile in PROFILES:
        print(f"Fetching posts for {profile} ...")
        try:
            data = fetch_posts(profile)
            total_posts, summary = summarize_posts(data)
            profile_summaries[profile] = (total_posts, summary)
        except Exception as e:
            print(f"Error fetching posts for {profile}: {e}")
    
    print("Generating report via GPT...")
    report_text = generate_gpt_report(profile_summaries)
    
    print("Sending email...")
    send_email(report_text)
    print("Report sent successfully!")

if __name__ == "__main__":
    main()
