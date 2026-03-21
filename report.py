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

OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4.1-mini")

RAW_JSON_FILE = "linkedin_raw.json"
SUMMARY_JSON_FILE = "linkedin_summary.json"
REPORT_JSON_FILE = "linkedin_report.json"

# Internal canonical keys -> display labels
COMPANY_KEY_TO_LABEL = {
    "leumitech": "LeumiTech",
    "poalim-hi-tech": "Poalim Hi-Tech",
    "discountech": "DiscountTech",
}

# Display labels -> internal canonical keys
LABEL_TO_COMPANY_KEY = {v: k for k, v in COMPANY_KEY_TO_LABEL.items()}


def load_text(path: str) -> str:
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def load_json(path: str):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def save_json(path: str, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def run_apify_task() -> str:
    url = f"https://api.apify.com/v2/actor-tasks/{APIFY_TASK_ID}/runs?token={APIFY_TOKEN}"
    print("Starting Apify task...")
    response = requests.post(url, timeout=60)
    response.raise_for_status()
    run_id = response.json()["data"]["id"]
    print("Apify run started:", run_id)
    return run_id


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
    print("Downloading dataset...")
    response = requests.get(url, timeout=120)
    response.raise_for_status()
    data = response.json()

    save_json(RAW_JSON_FILE, data)
    print(f"Downloaded {len(data)} dataset items")

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
        "artificial intelligence": "AI",
        "innovation": "Innovation",
        "israel": "Israeli Tech Ecosystem",
        "bank": "Banking / Financial Services",
        "fintech": "Fintech",
    }

    for keyword, label in mapping.items():
        if keyword in text and label not in hints:
            hints.append(label)

    return hints[:5]


def get_company_key(item: dict) -> str:
    """
    Returns a stable internal company key.
    Prefer LinkedIn universalName / URL slug over display name because
    display names may differ, e.g. 'Poalim Tech' vs slug 'poalim-hi-tech'.
    """
    author = item.get("author", {}) or {}
    query = item.get("query", {}) or {}

    universal_name = (author.get("universalName") or "").strip().lower()
    if universal_name:
        if universal_name in COMPANY_KEY_TO_LABEL:
            return universal_name

    target_url = (query.get("targetUrl") or "").strip().lower()
    if target_url:
        for key in COMPANY_KEY_TO_LABEL:
            if key in target_url:
                return key

    linkedin_url = (item.get("linkedinUrl") or "").strip().lower()
    if linkedin_url:
        for key in COMPANY_KEY_TO_LABEL:
            if key in linkedin_url:
                return key

    raw_name = (author.get("name") or "").strip().lower()

    # Explicit aliases
    if raw_name in {"poalim tech", "poalim hi-tech"}:
        return "poalim-hi-tech"
    if raw_name == "leumitech":
        return "leumitech"
    if raw_name == "discounttech":
        return "discountech"

    return raw_name.replace(" ", "-")


def normalize_post(item: dict) -> dict:
    author = item.get("author", {}) or {}
    posted_at = item.get("postedAt", {}) or {}
    engagement = item.get("engagement", {}) or {}

    company_key = get_company_key(item)
    company_label = COMPANY_KEY_TO_LABEL.get(
        company_key,
        author.get("name", "Unknown")
    )

    likes = int(engagement.get("likes", 0) or 0)
    comments = int(engagement.get("comments", 0) or 0)
    shares = int(engagement.get("shares", 0) or 0)

    content = (item.get("content") or "").strip()
    excerpt = content[:300] + ("..." if len(content) > 300 else "")

    return {
        "company_key": company_key,
        "company": company_label,
        "post_date": posted_at.get("date", ""),
        "post_url": item.get("linkedinUrl", ""),
        "content_excerpt": excerpt,
        "likes": likes,
        "comments": comments,
        "shares": shares,
        "total_engagement": likes + comments + shares,
        "theme_hints": extract_theme_hints(content),
    }


def build_summary_payload(raw_data: list) -> dict:
    config = load_json("competitive_agent/competitors.json")
    scoring = load_json("competitive_agent/scoring_rules.json")

    tracked_company_labels = [config["primary_company"]] + config["competitors"]
    tracked_company_keys = [
        LABEL_TO_COMPANY_KEY.get(label, label.strip().lower().replace(" ", "-"))
        for label in tracked_company_labels
    ]

    posts = [normalize_post(x) for x in raw_data if x.get("type") == "post"]

    grouped = defaultdict(list)
    for post in posts:
        grouped[post["company_key"]].append(post)

    companies = []

    for company_key in tracked_company_keys:
        company_label = COMPANY_KEY_TO_LABEL.get(company_key, company_key)
        items = grouped.get(company_key, [])

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
            theme for theme, _count in sorted(
                theme_counts.items(),
                key=lambda kv: (-kv[1], kv[0])
            )[:5]
        ]

        top_posts = sorted(
            items,
            key=lambda x: x["total_engagement"],
            reverse=True
        )[: scoring.get("top_posts_per_company", 2)]

        companies.append({
            "company_key": company_key,
            "company": company_label,
            "posts_count": posts_count,
            "total_likes": total_likes,
            "total_comments": total_comments,
            "total_shares": total_shares,
            "total_engagement": total_engagement,
            "avg_engagement_per_post": avg_engagement,
            "top_themes": top_themes,
            "top_posts": top_posts,
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

    save_json(SUMMARY_JSON_FILE, payload)
    print("Summary payload created")
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
            try:
                err = response.json()
                code = err.get("error", {}).get("code")
            except Exception:
                code = None

            if code == "insufficient_quota":
                print("OpenAI quota exhausted:", response.text)
                raise RuntimeError("OpenAI insufficient_quota")

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
            for item in data.get("output", []):
                if item.get("type") != "message":
                    continue
                for content in item.get("content", []):
                    if content.get("type") == "output_text" and content.get("text"):
                        output_text = content["text"]
                        break
                if output_text:
                    break

        if not output_text:
            print("Unexpected OpenAI response:", json.dumps(data, ensure_ascii=False, indent=2))
            raise RuntimeError("OpenAI response did not include output text")

        report = json.loads(output_text)
        save_json(REPORT_JSON_FILE, report)
        print("OpenAI report generated")
        return report

    raise RuntimeError("OpenAI call failed after retries")

def build_fallback_report(summary_payload: dict) -> dict:
    competitive_snapshot = []
    theme_analysis = []

    for company in summary_payload["companies"]:
        # Generate positioning takeaway from stats
        posts_count = company["posts_count"]
        total_engagement = company["total_engagement"]
        avg_engagement = company["avg_engagement_per_post"]

        if posts_count == 0:
            takeaway = "No activity this week."
        elif avg_engagement > 50:
            takeaway = f"Highly active with strong engagement ({avg_engagement:.1f} avg/post)."
        elif avg_engagement > 30:
            takeaway = f"Moderately active with decent engagement ({avg_engagement:.1f} avg/post)."
        else:
            takeaway = f"Low activity level ({posts_count} posts, {avg_engagement:.1f} avg/post)."

        theme_analysis.append({
            "company": company["company"],
            "themes": company["top_themes"],
            "positioning_takeaway": takeaway
        })

        for p in company["top_posts"]:
            competitive_snapshot.append({
                "company": company["company"],
                "post_date": p["post_date"],
                "content_summary": p["content_excerpt"][:200],
                "likes": p["likes"],
                "comments": p["comments"],
                "shares": p["shares"],
                "total_engagement": p["total_engagement"],
                "url": p["post_url"]
            })

    # Sort by engagement descending
    competitive_snapshot.sort(key=lambda x: x["total_engagement"], reverse=True)

    report = {
        "email_subject": "דוח LinkedIn תחרותי שבועי - סיכום חלופי",
        "executive_summary": [
            "כישלון דור דוח OpenAI, לכן סיכום חלופי זה נוצר מהנתונים המנורמלים.",
            "אנא נסה שוב כשהטוקן מתוקן.",
            "טבלת הפוסטים והנושאים עדיין זמינים למעלה."
        ],
        "competitive_snapshot": competitive_snapshot,
        "theme_analysis": theme_analysis
    }

    save_json(REPORT_JSON_FILE, report)
    print("Fallback report generated")
    return report


def render_html_email(report: dict) -> str:
    body = []

    body.append(f"<h2>{html.escape(report['email_subject'])}</h2>")

    body.append("<h3>תמונת מצב תחרותית</h3>")

    # Get unique companies in order they appear
    companies_data = {}
    for post in report["competitive_snapshot"]:
        company = post["company"]
        if company not in companies_data:
            companies_data[company] = []
        companies_data[company].append(post)

    # Render table for each company
    for company, posts in companies_data.items():
        body.append(f"<h4>{html.escape(company)}</h4>")
        body.append("<table border='1' cellpadding='8' cellspacing='0' style='border-collapse: collapse; direction: rtl;'>")
        body.append("<tr><th>תאריך</th><th>נושא</th><th>לייקים</th><th>תגובות</th><th>שיתופים</th></tr>")

        total_likes = 0
        total_comments = 0
        total_shares = 0

        for post in posts:
            url_link = f" <a href=\"{html.escape(post.get('url', '#'))}\">קישור</a>" if post.get('url') else ""
            body.append(
                "<tr>"
                f"<td>{html.escape(str(post['post_date']))}</td>"
                f"<td>{html.escape(str(post['content_summary']))}{url_link}</td>"
                f"<td>{html.escape(str(post['likes']))}</td>"
                f"<td>{html.escape(str(post['comments']))}</td>"
                f"<td>{html.escape(str(post['shares']))}</td>"
                "</tr>"
            )
            total_likes += post['likes']
            total_comments += post['comments']
            total_shares += post['shares']

        # Add total row
        body.append(
            "<tr style='font-weight: bold;'>"
            f"<td colspan='1'>סה״כ</td>"
            f"<td></td>"
            f"<td>{total_likes}</td>"
            f"<td>{total_comments}</td>"
            f"<td>{total_shares}</td>"
            "</tr>"
        )
        body.append("</table>")
        body.append("<br/>")

    # Add company summary table
    body.append("<h3>סיכום חברות</h3>")
    body.append("<table border='1' cellpadding='8' cellspacing='0' style='border-collapse: collapse; direction: rtl;'>")
    body.append("<tr><th>חברה</th><th>פוסטים</th><th>סך הערכת</th><th>ממוצע לפוסט</th><th>סיכום עמדה</th></tr>")

    for company, posts in companies_data.items():
        posts_count = len(posts)
        total_engagement = sum(p['likes'] + p['comments'] + p['shares'] for p in posts)
        avg_engagement = round(total_engagement / posts_count, 2) if posts_count else 0

        # Extract positioning takeaway from theme_analysis
        takeaway = ""
        for theme_item in report.get("theme_analysis", []):
            if theme_item.get("company") == company:
                takeaway = theme_item.get("positioning_takeaway", "")
                break

        body.append(
            "<tr>"
            f"<td>{html.escape(company)}</td>"
            f"<td>{posts_count}</td>"
            f"<td>{total_engagement}</td>"
            f"<td>{avg_engagement}</td>"
            f"<td>{html.escape(takeaway)}</td>"
            "</tr>"
        )

    body.append("</table>")
    body.append("<br/>")

    body.append("<h3>סיכום שבועי</h3>")
    # Handle both string and list formats for executive_summary
    if isinstance(report.get("executive_summary"), list):
        body.append("<ul>")
        for item in report["executive_summary"]:
            body.append(f"<li>{html.escape(item)}</li>")
        body.append("</ul>")
    else:
        body.append(f"<p>{html.escape(report['executive_summary'])}</p>")

    try:
        template = load_text("competitive_agent/email_template.html")
        return template.replace("{{BODY}}", "".join(body))
    except FileNotFoundError:
        return f"<html><body>{''.join(body)}</body></html>"


def send_email(report: dict):
    msg = EmailMessage()
    msg["Subject"] = report["email_subject"]
    msg["From"] = SENDER_EMAIL
    recipients = [x.strip() for x in RECIPIENT_EMAIL.split(",")]
    msg["To"] = ", ".join(recipients)

    # Build plain text version by company
    companies_data = {}
    for post in report["competitive_snapshot"]:
        company = post["company"]
        if company not in companies_data:
            companies_data[company] = []
        companies_data[company].append(post)

    plain_lines = [
        report["email_subject"],
        "",
        "תמונת מצב תחרותית",
        ""
    ]

    for company, posts in companies_data.items():
        plain_lines.append(company)
        for post in posts:
            plain_lines.append(
                f"  {post['post_date']}: {post['content_summary'][:80]} "
                f"(לייקים: {post['likes']}, תגובות: {post['comments']}, שיתופים: {post['shares']})"
            )
        total_likes = sum(p['likes'] for p in posts)
        total_comments = sum(p['comments'] for p in posts)
        total_shares = sum(p['shares'] for p in posts)
        plain_lines.append(f"  סה״כ: לייקים {total_likes}, תגובות {total_comments}, שיתופים {total_shares}")
        plain_lines.append("")

    # Add company summary
    plain_lines.append("סיכום חברות")
    for company, posts in companies_data.items():
        posts_count = len(posts)
        total_engagement = sum(p['likes'] + p['comments'] + p['shares'] for p in posts)
        avg_engagement = round(total_engagement / posts_count, 2) if posts_count else 0
        takeaway = ""
        for theme_item in report.get("theme_analysis", []):
            if theme_item.get("company") == company:
                takeaway = theme_item.get("positioning_takeaway", "")
                break
        plain_lines.append(
            f"{company}: {posts_count} פוסטים, סך הערכת {total_engagement}, "
            f"ממוצע {avg_engagement} - {takeaway}"
        )
    plain_lines.append("")

    # Add executive summary (handle both list and string)
    plain_lines.append("סיכום שבועי")
    if isinstance(report.get("executive_summary"), list):
        plain_lines.extend([f"• {item}" for item in report["executive_summary"]])
    else:
        plain_lines.append(report.get("executive_summary", ""))

    plain = "\n".join(plain_lines)

    msg.set_content(plain)
    msg.add_alternative(render_html_email(report), subtype="html")

    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as smtp:
        smtp.login(SENDER_EMAIL, GMAIL_APP_PASSWORD)
        smtp.sendmail(SENDER_EMAIL, recipients, msg.as_string())
    print("Email sent")


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
