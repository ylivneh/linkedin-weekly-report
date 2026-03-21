#!/usr/bin/env python3
"""
Test script to preview the new email format without running the full workflow.
Generates sample data and renders the HTML email.
"""

import html

def render_html_email(report: dict) -> str:
    """Copied from report.py - renders HTML email matching template format"""
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
    body.append("<tr><th>חברה</th><th>פוסטים</th><th>סך הערכת</th><th>ממוצע לפוסט</th><th>הערה</th></tr>")

    for company, posts in companies_data.items():
        posts_count = len(posts)
        total_engagement = sum(p['likes'] + p['comments'] + p['shares'] for p in posts)
        avg_engagement = round(total_engagement / posts_count, 2) if posts_count else 0

        # Extract positioning takeaway if available
        takeaway = ""
        for theme_item in report.get("theme_analysis", []):
            if theme_item.get("company") == company:
                takeaway = f"נושאים: {', '.join(theme_item.get('themes', []))}"
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
    body.append(f"<p>{html.escape(report['executive_summary'])}</p>")

    html_template = """<html>
  <body style="font-family: Arial, Helvetica, sans-serif; color: #222; line-height: 1.5;">
    {{BODY}}
  </body>
</html>"""

    return html_template.replace("{{BODY}}", "".join(body))

# Sample report data matching the new schema
sample_report = {
    "email_subject": "דוח LinkedIn תחרותי שבועי - 21 במרץ 2026",
    "executive_summary": "LeumiTech שמר על היתרון התחרותי עם 11 פוסטים וסך של 48 הערכות. Poalim Hi-Tech הגביר את הפעילות עם 8 פוסטים ו-47 הערכות, במיוחד בתוכן הקשור ל-AI ו-fintech. DiscountTech הוא פחות פעיל עם 5 פוסטים בלבד.",
    "competitive_snapshot": [
        {
            "company": "LeumiTech",
            "post_date": "2026-03-20",
            "content_summary": "כשות פתרונות בנקאי חדשניים עבור הגזעים הישראליים ההגדולים",
            "likes": 48,
            "comments": 3,
            "shares": 0,
            "total_engagement": 51,
            "url": "https://linkedin.com/feed/update/urn:li:activity:123456"
        },
        {
            "company": "Poalim Hi-Tech",
            "post_date": "2026-03-19",
            "content_summary": "הכרזה על שיתוף פעולה עם MindTheTech לפתרונות ניהול כספים",
            "likes": 47,
            "comments": 6,
            "shares": 3,
            "total_engagement": 56,
            "url": "https://linkedin.com/feed/update/urn:li:activity:123457"
        },
        {
            "company": "LeumiTech",
            "post_date": "2026-03-18",
            "content_summary": "סדנה על עתיד הטכנולוגיה בשירותים פיננסיים",
            "likes": 36,
            "comments": 7,
            "shares": 0,
            "total_engagement": 43,
            "url": "https://linkedin.com/feed/update/urn:li:activity:123458"
        },
        {
            "company": "DiscountTech",
            "post_date": "2026-03-17",
            "content_summary": "אנו גאים להכריז על התחדשות פלטפורמת הביטוח הדיגיטלית",
            "likes": 36,
            "comments": 0,
            "shares": 1,
            "total_engagement": 37,
            "url": "https://linkedin.com/feed/update/urn:li:activity:123459"
        },
        {
            "company": "Poalim Hi-Tech",
            "post_date": "2026-03-16",
            "content_summary": "MoneyTalks הרצאה חיה על עתיד ה-AI בפיננסים",
            "likes": 42,
            "comments": 1,
            "shares": 10,
            "total_engagement": 53,
            "url": "https://linkedin.com/feed/update/urn:li:activity:123460"
        }
    ],
    "theme_analysis": [
        {
            "company": "LeumiTech",
            "themes": ["Fintech", "Banking / Financial Services", "Innovation"]
        },
        {
            "company": "Poalim Hi-Tech",
            "themes": ["AI", "Fintech", "VC / Venture"]
        },
        {
            "company": "DiscountTech",
            "themes": ["Insurance Tech", "Innovation"]
        }
    ]
}

def main():
    print("=" * 80)
    print("EMAIL FORMAT PREVIEW - New Yael Changes Format")
    print("=" * 80)
    print()

    # Render HTML
    html_output = render_html_email(sample_report)

    # Save to file
    output_file = "/Users/i031851/Documents/git-repos/private/linkedin-weekly-report/test_email_preview.html"
    with open(output_file, "w", encoding="utf-8") as f:
        f.write(html_output)

    print(f"✅ HTML email preview saved to: {output_file}")
    print()
    print("HTML Output:")
    print("-" * 80)
    print(html_output)
    print("-" * 80)
    print()

    # Print plain text version
    print("PLAIN TEXT VERSION:")
    print("-" * 80)

    # Get unique companies in order they appear
    companies_data = {}
    for post in sample_report["competitive_snapshot"]:
        company = post["company"]
        if company not in companies_data:
            companies_data[company] = []
        companies_data[company].append(post)

    plain_lines = [
        sample_report["email_subject"],
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
        themes = ""
        for theme_item in sample_report.get("theme_analysis", []):
            if theme_item.get("company") == company:
                themes = f"נושאים: {', '.join(theme_item.get('themes', []))}"
                break
        plain_lines.append(
            f"{company}: {posts_count} פוסטים, סך הערכת {total_engagement}, "
            f"ממוצע {avg_engagement} - {themes}"
        )
    plain_lines.append("")

    plain_lines.extend([
        "סיכום שבועי",
        sample_report["executive_summary"],
    ])

    plain_text = "\n".join(plain_lines)

    print(plain_text)
    print("-" * 80)
    print()
    print("✅ You can open the HTML file in a browser to see the formatted email")
    print()

if __name__ == "__main__":
    main()
