import os
import requests
import time
import smtplib
from datetime import datetime, timedelta
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

# -----------------------------
# CONFIGURATION
# -----------------------------

PROFILES = [
    "https://www.linkedin.com/company/leumitech",
    "https://www.linkedin.com/company/profile2",
    "https://www.linkedin.com/company/profile3"
]

APIFY_TOKEN = os.environ["APIFY_TOKEN"]
ACTOR_ID = "WI0tj4Ieb5Kq458gB"

GMAIL_USER = os.environ["GMAIL_USER"]
GMAIL_APP_PASSWORD = os.environ["GMAIL_APP_PASSWORD"]


# -----------------------------
# APIFY SCRAPER
# -----------------------------

def fetch_posts(profile_url):

    print(f"Triggering Apify actor for {profile_url}")

    run_url = f"https://api.apify.com/v2/acts/{ACTOR_ID}/runs?token={APIFY_TOKEN}"

    actor_input = {
        "profileUrl": profile_url,
        "maxPosts": 20
    }

    run = requests.post(run_url, json=actor_input).json()
    run_id = run["data"]["id"]

    print("Waiting for actor to finish...")

    status = "RUNNING"

    while status in ["RUNNING", "READY"]:
        time.sleep(10)

        status_url = f"https://api.apify.com/v2/actor-runs/{run_id}?token={APIFY_TOKEN}"
        status_resp = requests.get(status_url).json()

        status = status_resp["data"]["status"]
        print("Actor status:", status)

    dataset_id = status_resp["data"]["defaultDatasetId"]

    dataset_url = f"https://api.apify.com/v2/datasets/{dataset_id}/items?clean=1"

    posts = requests.get(dataset_url).json()

    return posts


# -----------------------------
# FILTER LAST WEEK
# -----------------------------

def filter_last_week(posts):

    one_week_ago = datetime.utcnow() - timedelta(days=7)
    filtered = []

    for post in posts:

        date_str = post.get("postedAt")
        if not date_str:
            continue

        try:
            post_date = datetime.fromisoformat(date_str.replace("Z", ""))
        except:
            continue

        if post_date > one_week_ago:
            filtered.append(post)

    return filtered


# -----------------------------
# REPORT GENERATION
# -----------------------------

def generate_report(profile_posts):

    report = "Weekly LinkedIn Activity Report\n\n"

    global_top_post = None
    global_top_profile = None

    for profile, posts in profile_posts.items():

        total_posts = len(posts)

        total_likes = sum(p.get("reactionsCount", 0) for p in posts)
        total_comments = sum(p.get("commentsCount", 0) for p in posts)
        total_reposts = sum(p.get("sharesCount", 0) for p in posts)

        report += f"Profile: {profile}\n"
        report += f"Posts this week: {total_posts}\n\n"

        report += "Total Engagement\n"
        report += f"Likes: {total_likes}\n"
        report += f"Comments: {total_comments}\n"
        report += f"Reposts: {total_reposts}\n\n"

        if posts:

            top_post = max(posts, key=lambda p: p.get("reactionsCount", 0))

            report += "Top Post\n"
            report += f"Likes: {top_post.get('reactionsCount',0)} | "
            report += f"Comments: {top_post.get('commentsCount',0)} | "
            report += f"Reposts: {top_post.get('sharesCount',0)}\n"

            report += "\n"

            if not global_top_post or top_post.get("reactionsCount",0) > global_top_post.get("reactionsCount",0):
                global_top_post = top_post
                global_top_profile = profile

        report += "-----------------------------\n\n"

    if global_top_post:

        report += "🏆 Top Post Across All Profiles\n"
        report += f"Profile: {global_top_profile}\n"
        report += f"Likes: {global_top_post.get('reactionsCount',0)}\n"
        report += f"Comments: {global_top_post.get('commentsCount',0)}\n"
        report += f"Reposts: {global_top_post.get('sharesCount',0)}\n"

    return report


# -----------------------------
# EMAIL
# -----------------------------

def send_email(report_text):

    msg = MIMEMultipart()

    msg["From"] = GMAIL_USER
    msg["To"] = GMAIL_USER
    msg["Subject"] = "Weekly LinkedIn Activity Report"

    msg.attach(MIMEText(report_text, "plain"))

    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:

        server.login(GMAIL_USER, GMAIL_APP_PASSWORD)
        server.send_message(msg)

    print("Email sent")


# -----------------------------
# MAIN
# -----------------------------

def main():

    profile_posts = {}

    for profile in PROFILES:

        print(f"Fetching posts for {profile}")

        posts = fetch_posts(profile)

        posts = filter_last_week(posts)

        profile_posts[profile] = posts

    print("Generating report")

    report_text = generate_report(profile_posts)

    print(report_text)

    print("Sending email")

    send_email(report_text)


if __name__ == "__main__":
    main()
