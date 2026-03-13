import os
import json
import time
import html
import smtplib
from collections import defaultdict
from email.message import EmailMessage

import requests

APIFY_TOKEN = os.environ["APIFY_TOKEN"]
APIFY_TASK_ID = os.environ["APIFY_TASK_ID"]
OPENAI_API_KEY = os.environ["OPENAI_API_KEY"]

SENDER_EMAIL = os.environ["SENDER_EMAIL"]
GMAIL_APP_PASSWORD = os.environ["GMAIL_APP_PASSWORD"]
RECIPIENT_EMAIL = os.environ["RECIPIENT_EMAIL"]

OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-5.4")

RAW_JSON_FILE = "linkedin_raw.json"
SUMMARY_JSON_FILE = "linkedin_summary.json"
REPORT_JSON_FILE = "linkedin_report.json"


def load_text(path: str) -> str:
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def load_json(path: str):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def run_apify_task() -> str:
    url = f"https://api.apify.com/v2/actor-tasks/{APIFY_TASK_ID}/runs?token={APIFY_TOKEN}"
    response = requests.post(url, timeout=60)
    response.raise_for_status()
    return response.json()["data"]["id"]


def wait_for_run(run_id: str) -> str:
    url = f"https://api.apify.com/v2/actor-runs/{run_id}?token={APIFY_TOKEN}"

    while True:
        response = requests.get(url, timeout=60)
        response.raise_for_status()
        data = response.json()["data"]
        status = data["status"]

        print("Apify status:", status)

        if status in {"SUCCEEDED", "FAILED", "ABORTED", "TIMED-OUT"}:
            if status != "SUCCEEDED":
                raise RuntimeError(f"Apify run failed with status: {status}")
            return data["defaultDatasetId"]

        time.sleep(10)


def download_dataset(dataset_id: str):
    url = (
        f"https://api.apify.com/v2/datasets/{dataset_id}/items"
        f"?clean=true&format=json&token={APIFY_TOKEN}"
    )
    response = requests.get(url, timeout=120)
    response.raise_for_status()
    data = response.json()

    with open(RAW_JSON_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    return data


def extract_theme_hints(text: str):
    text = (text or "").lower()
    hints = []

    mapping = {
        "cyber": "Cybersecurity",
        "startup": "Startups",
        "venture": "VC / Venture",
        "fund": "Funding",
        "exit": "M&A / Exit",
        "acquisition": "M&A / Exit",
        "google": "Big Tech / Strategic Partnerships",
        "ai": "AI",
        "innovation": "Innovation",
        "israel": "Israeli Tech Ecosystem",
        "bank": "Banking / Financial Services"
    }

    for keyword, label in mapping.items():
        if keyword in text and label not in hints:
            hints.append(label)

    return hints[:5]


def normalize_post(item: dict) -> dict:
    author = item.get("author", {}) or {}
    posted_at = item.get("postedAt", {}) or {}
    engagement = item.get("engagement", {}) or {}

    likes = int(engagement.get("likes", 0) or 0)
    comments = int(engagement.get("comments", 0) or 0)
    shares = int(engagement.get("shares", 0) or 0)

    content = (item.get("content") or "").strip()
    excerpt = content[:300] + ("..." if len(content) > 300 else "")
    return {
        "company": author.get("name", "Unknown"),
        "post_date": posted_at.get("date", ""),
        "post_url": item.get("linkedinUrl", ""),
        "content_excerpt": excerpt,
        "likes": likes,
        "comments": comments,
        "shares": shares,
        "total_engagement": likes + comments + shares,
        "theme_hints": extract_theme_hints(content)
    }


def build_summary_payload(raw_data: list) -> dict:
    config = load_json("competitive_agent/competitors.json")
    scoring = load_json("competitive_agent/scoring_rules.json")

    tracked_companies = [config["primary_company"]] + config["competitors"]
    posts = [normalize_post(x) for x in raw_data if x.get("type") == "post"]

    grouped = defaultdict(list)
    for post in posts:
        grouped[post["company"]].append(post)

    companies = []

    for company in tracked_companies:
        items = grouped.get(company, [])

        posts_count = len(items)
        total_likes = sum(x["likes"] for x in items)
        total_comments = sum(x["comments"] for x in items)
        total_shares = sum(x["shares"] for x in items)
        total_engagement = sum(x["total_engagement"] for x in items)
        avg_engagement = round(total_engagement / posts_count, 2) if posts_count else 0

        theme_counts = defaultdict(int)
        for item in items:
            for theme in item["theme_hints"]:
                theme_counts[theme] += 1

        top_themes = [
            theme for theme, _ in sorted(
                theme_counts.items(),
                key=lambda kv: (-kv[1], kv[0])
            )[:5]
        ]

        top_posts = sorted(
            items,
            key=lambda x: x["total_engagement"],
            reverse=True
        )[: scoring.get("top_posts_per_company", 3)]

        companies.append({
            "company": company,
            "posts_count": posts_count,
            "total_likes": total_likes,
            "total_comments": total_comments,
            "total_shares": total_shares,
            "total_engagement": total_engagement,
            "avg_engagement_per_post": avg_engagement,
            "top_themes": top_themes,
            "top_posts": top_posts
        })

    payload = {
        "reporting_period": "Last 7 days",
        "audience": "Business Development Manager at LeumiTech",
        "objective": "Track LeumiTech vs main competitors on LinkedIn",
        "companies": companies,
        "notes": [
            "Only post records were analyzed.",
            "Engagement equals likes + comments + shares.",
            "A competitor with zero posts should be considered inactive during the period."
        ]
    }

    with open(SUMMARY_JSON_FILE, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)

    return payload


def call_openai(summary_payload: dict) -> dict:
    instructions = load_text("competitive_agent/instructions.md")
    schema = load_json("competitive_agent/schema.json")
    competitors = load_json("competitive_agent/competitors.json")
    scoring = load_json("competitive_agent/scoring_rules.json")

    prompt = f"""
{instructions}

Tracked companies configuration:
{json.dumps(competitors, ensure_ascii=False)}

Scoring rules:
{json.dumps(scoring, ensure_ascii=False)}

Weekly LinkedIn summary data:
{json.dumps(summary_payload, ensure_ascii=False)}
""".strip()

    payload = {
        "model": OPENAI_MODEL,
        "input": prompt,
        "text": {
            "format": {
                "type": "json_schema",
                "name": "linkedin_competitive_report",
                "strict": True,
                "schema": schema
            }
        }
    }

    headers = {
        "Authorization": f"Bearer {OPENAI_API_KEY}",
        "Content-Type": "application/json"
    }

    max_attempts = 6
    base_delay = 5

    for attempt in range(1, max_attempts + 1):
        response = requests.post(
            "https://api.openai.com/v1/responses",
            headers=headers,
            json=payload,
            timeout=180
        )

        if response.status_code == 429:
            wait_time = base_delay * (2 ** (attempt - 1))
            print(f"OpenAI rate limited (attempt {attempt}/{max_attempts}). Waiting {wait_time}s...")
            if attempt == max_attempts:
                print("OpenAI response body:", response.text)
                response.raise_for_status()
            time.sleep(wait_time)
            continue

        if response.status_code >= 400:
            print("OpenAI error response:", response.text)
            response.raise_for_status()

        data = response.json()

        output_text = data.get("output_text")
        if not output_text:
            print("Unexpected OpenAI response:", json.dumps(data, ensure_ascii=False, indent=2))
            raise RuntimeError("OpenAI response did not include output_text")

        report = json.loads(output_text)

        with open(REPORT_JSON_FILE, "w", encoding="utf-8") as f:
            json.dump(report, f, ensure_ascii=False, indent=2)

        return report

    raise RuntimeError("OpenAI call failed after retries")

def render_html_email(report: dict) -> str:
    body = []

    body.append(f"<h2>{html.escape(report['email_subject'])}</h2>")
    body.append("<h3>Executive Summary</h3>")
    body.append(f"<p>{html.escape(report['executive_summary'])}</p>")

    body.append("<h3>Competitive Snapshot</h3>")
    body.append("<table border='1' cellpadding='8' cellspacing='0' style='border-collapse: collapse;'>")
    body.append("<tr><th>Company</th><th>Posts</th><th>Total Engagement</th><th>Avg/Post</th><th>Takeaway</th></tr>")
    for item in report["competitive_snapshot"]:
        body.append(
            "<tr>"
            f"<td>{html.escape(str(item['company']))}</td>"
            f"<td>{html.escape(str(item['posts_count']))}</td>"
            f"<td>{html.escape(str(item['total_engagement']))}</td>"
            f"<td>{html.escape(str(item['avg_engagement_per_post']))}</td>"
            f"<td>{html.escape(str(item['positioning_takeaway']))}</td>"
            "</tr>"
        )
    body.append("</table>")

    body.append("<h3>Theme Analysis</h3><ul>")
    for item in report["theme_analysis"]:
        body.append(
            f"<li><b>{html.escape(item['company'])}</b>: {html.escape(', '.join(item['themes']))}</li>"
        )
    body.append("</ul>")

    body.append("<h3>Top Posts</h3><ul>")
    for item in report["top_posts"]:
        body.append(
            f"<li><b>{html.escape(item['company'])}</b> — {html.escape(item['post_date'])} — "
            f"Engagement {html.escape(str(item['engagement']))} — "
            f"{html.escape(item['summary'])} — "
            f"<a href=\"{html.escape(item['url'])}\">Open post</a></li>"
        )
    body.append("</ul>")

    body.append("<h3>BD Signals</h3><ul>")
    for item in report["bd_signals"]:
        body.append(f"<li>{html.escape(item)}</li>")
    body.append("</ul>")

    body.append("<h3>Recommended Actions</h3><ul>")
    for item in report["recommended_actions"]:
        body.append(f"<li>{html.escape(item)}</li>")
    body.append("</ul>")

    template = load_text("competitive_agent/email_template.html")
    return template.replace("{{BODY}}", "".join(body))


def send_email(report: dict):
    msg = EmailMessage()
    msg["Subject"] = report["email_subject"]
    msg["From"] = SENDER_EMAIL
    msg["To"] = RECIPIENT_EMAIL

    plain = "\n".join([
        report["email_subject"],
        "",
        "Executive Summary",
        report["executive_summary"],
        "",
        "BD Signals",
        *[f"- {x}" for x in report["bd_signals"]],
        "",
        "Recommended Actions",
        *[f"- {x}" for x in report["recommended_actions"]],
    ])

    msg.set_content(plain)
    msg.add_alternative(render_html_email(report), subtype="html")

    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as smtp:
        smtp.login(SENDER_EMAIL, GMAIL_APP_PASSWORD)
        smtp.send_message(msg)

def build_fallback_report(summary_payload: dict) -> dict:
    snapshot = []
    for company in summary_payload["companies"]:
        snapshot.append(
            f"{company['company']}: {company['posts_count']} posts, "
            f"{company['total_engagement']} total engagement, "
            f"{company['avg_engagement_per_post']} avg/post"
        )

    return {
        "email_subject": "Weekly LinkedIn Competitive Report - Fallback Summary",
        "executive_summary": "OpenAI report generation was rate-limited, so this fallback summary was generated from the normalized data.",
        "competitive_snapshot": [
            {
                "company": c["company"],
                "posts_count": c["posts_count"],
                "total_engagement": c["total_engagement"],
                "avg_engagement_per_post": c["avg_engagement_per_post"],
                "positioning_takeaway": "Fallback summary only."
            }
            for c in summary_payload["companies"]
        ],
        "theme_analysis": [
            {"company": c["company"], "themes": c["top_themes"]}
            for c in summary_payload["companies"]
        ],
        "top_posts": [
            {
                "company": c["company"],
                "post_date": p["post_date"],
                "engagement": p["total_engagement"],
                "summary": p["content_excerpt"][:140],
                "url": p["post_url"]
            }
            for c in summary_payload["companies"]
            for p in c["top_posts"][:1]
        ],
        "bd_signals": snapshot,
        "recommended_actions": [
            "Re-run the workflow once OpenAI rate limits reset.",
            "Reduce payload size or add stronger retry logic."
        ]
    }
    
def main():
    run_id = run_apify_task()
    dataset_id = wait_for_run(run_id)
    raw_data = download_dataset(dataset_id)
    summary_payload = build_summary_payload(raw_data)

    try:
        report = call_openai(summary_payload)
    except Exception as e:
        print("OpenAI report generation failed:", str(e))
        report = build_fallback_report(summary_payload)

    send_email(report)
    print("Done")


if __name__ == "__main__":
    main()
