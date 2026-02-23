"""
Job Agent - Sends daily job digest emails with tailored CVs and networking suggestions.
"""

import os
import json
import time
import smtplib
import logging
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
import anthropic
import requests
from dotenv import load_dotenv

load_dotenv()
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

# ── Config ────────────────────────────────────────────────────────────────────
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")
RAPIDAPI_KEY      = os.getenv("RAPIDAPI_KEY")
SMTP_HOST         = os.getenv("SMTP_HOST", "smtp.gmail.com")
SMTP_PORT         = int(os.getenv("SMTP_PORT", 587))
SMTP_USER         = os.getenv("SMTP_USER")
SMTP_PASSWORD     = os.getenv("SMTP_PASSWORD")
FROM_EMAIL        = os.getenv("FROM_EMAIL", SMTP_USER)
TO_EMAIL          = os.getenv("TO_EMAIL")
CV_PATH           = os.getenv("CV_PATH", "cv.txt")
PREFERENCES_PATH  = os.getenv("PREFERENCES_PATH", "preferences.txt")

client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)


# ── CV & Preferences ──────────────────────────────────────────────────────────
def load_file(path: str) -> str:
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


# ── LinkedIn Job Search ───────────────────────────────────────────────────────
def fetch_linkedin_jobs(keywords: str, location: str, limit: int = 15) -> list:
    url = "https://jsearch.p.rapidapi.com/search"
    headers = {
        "X-RapidAPI-Key": RAPIDAPI_KEY,
        "X-RapidAPI-Host": "jsearch.p.rapidapi.com",
    }
    for date_posted in ["3days", "week"]:
        params = {
            "query": f"{keywords} jobs",
            "page": "1",
            "num_pages": "2",
            "date_posted": date_posted,
            "employment_types": "FULLTIME,PARTTIME,CONTRACTOR",
            "location": location,
            "radius": "100",
        }
        try:
            r = requests.get(url, headers=headers, params=params, timeout=40)
            r.raise_for_status()
            data = r.json()
            jobs = data.get("data", [])[:limit]
            if jobs:
                return jobs
        except Exception as e:
            log.error(f"Job fetch error: {e}")
            return []
    return []


def parse_jobs(raw_jobs: list) -> list:
    jobs = []
    for j in raw_jobs:
        jobs.append({
            "title":       j.get("job_title") or "Unknown",
            "company":     j.get("employer_name") or "Unknown",
            "location":    (j.get("job_city") or "") + ", " + (j.get("job_country") or ""),
            "url":         j.get("job_apply_link") or j.get("job_google_link") or "",
            "description": (j.get("job_description") or "")[:3000],
            "posted":      j.get("job_posted_at_datetime_utc") or "",
        })
    return jobs


# ── Claude: Score & Select Top 10 ────────────────────────────────────────────
def select_top_jobs(jobs: list, cv: str, preferences: str) -> list:
    if not jobs:
        return []

    job_list = "\n\n".join(
        f"[JOB {i+1}]\nTitle: {j['title']}\nCompany: {j['company']}\n"
        f"Location: {j['location']}\nURL: {j['url']}\nDescription: {j['description']}"
        for i, j in enumerate(jobs)
    )

    prompt = f"""You are a career advisor. Based on the CV and job preferences below,
select and rank the TOP 10 most relevant jobs from the list.
Return ONLY a JSON array of objects with keys: index (1-based from the list), score (0-100), reason (1 sentence).

CV:
{cv}

PREFERENCES:
{preferences}

JOBS:
{job_list}

Return ONLY valid JSON, no other text."""

    msg = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=1000,
        messages=[{"role": "user", "content": prompt}],
    )
    text = msg.content[0].text.strip()
    if text.startswith("```"):
        text = text.split("```")[1]
        if text.startswith("json"):
            text = text[4:]
    rankings = json.loads(text)
    top = sorted(rankings, key=lambda x: x["score"], reverse=True)[:10]
    return [{"job": jobs[r["index"] - 1], "score": r["score"], "reason": r["reason"]} for r in top]


# ── Claude: Tailor CV ─────────────────────────────────────────────────────────
def tailor_cv(cv: str, job: dict) -> str:
    prompt = f"""You are an expert CV writer. Rewrite the candidate's CV to better match the job description below.
Keep the same structure but:
- Reorder and emphasise relevant experience and skills
- Use keywords from the job description naturally
- Keep it truthful — do not invent experience
- Output clean plain text, ready to copy-paste

JOB TITLE: {job['title']} at {job['company']}
JOB DESCRIPTION:
{job['description']}

ORIGINAL CV:
{cv}

Output the tailored CV only."""

    msg = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=1500,
        messages=[{"role": "user", "content": prompt}],
    )
    return msg.content[0].text.strip()


# ── Claude: Networking Suggestions ───────────────────────────────────────────
def suggest_contacts(job: dict, preferences: str) -> list:
    prompt = f"""For the job below, suggest 2 types of LinkedIn profiles the candidate should message
to get a referral or warm intro. For each, provide:
- profile_type: their likely job title
- why: 1 sentence on why they're valuable to contact
- search_tip: a LinkedIn search query to find them
- message_template: a 2-sentence outreach message template

JOB: {job['title']} at {job['company']} ({job['location']})
CANDIDATE PREFERENCES: {preferences}

Return ONLY valid JSON array with 2 objects."""

    msg = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=600,
        messages=[{"role": "user", "content": prompt}],
    )
    text = msg.content[0].text.strip()
    if text.startswith("```"):
        text = text.split("```")[1]
        if text.startswith("json"):
            text = text[4:]
    return json.loads(text)


# ── Email Builder ─────────────────────────────────────────────────────────────
def build_email(top_jobs: list, cv: str, preferences: str) -> str:
    today = datetime.now().strftime("%A, %B %d %Y")
    sections = []

    for i, entry in enumerate(top_jobs, 1):
        job = entry["job"]
        log.info(f"Tailoring CV for job {i}/{len(top_jobs)}: {job['title']} @ {job['company']}")
        tailored = tailor_cv(cv, job)
        log.info(f"Getting contacts for job {i}/{len(top_jobs)}")
        contacts = suggest_contacts(job, preferences)

        contact_html = ""
        for c in contacts:
            contact_html += f"""
            <div style="background:#f0f7ff;border-left:3px solid #0077b5;padding:10px;margin:8px 0;border-radius:4px;">
              <strong>🔗 {c['profile_type']}</strong><br>
              <em>Why:</em> {c['why']}<br>
              <em>Find them:</em> LinkedIn search → <code>{c['search_tip']}</code><br>
              <em>Message:</em> "{c['message_template']}"
            </div>"""

        cv_escaped = tailored.replace("<", "&lt;").replace(">", "&gt;").replace("\n", "<br>")
        sections.append(f"""
        <div style="border:1px solid #ddd;border-radius:8px;padding:20px;margin:20px 0;font-family:Arial,sans-serif;">
          <div style="display:flex;justify-content:space-between;align-items:center;">
            <h2 style="color:#0077b5;margin:0">#{i} {job['title']}</h2>
            <span style="background:#0077b5;color:#fff;border-radius:20px;padding:4px 12px;font-size:12px;">
              Match: {entry['score']}/100
            </span>
          </div>
          <p style="margin:4px 0;color:#555;font-size:14px;">🏢 {job['company']} &nbsp;|&nbsp; 📍 {job['location']}</p>
          <p style="color:#333;font-size:13px;margin:6px 0">{entry['reason']}</p>
          <a href="{job['url']}" style="display:inline-block;background:#0077b5;color:#fff;padding:8px 18px;
             border-radius:5px;text-decoration:none;font-size:14px;margin:8px 0;">Apply on LinkedIn →</a>

          <details style="margin-top:16px;">
            <summary style="cursor:pointer;font-weight:bold;color:#333;">📄 Tailored CV for this role</summary>
            <div style="background:#f9f9f9;padding:14px;border-radius:6px;margin-top:8px;
                        font-size:13px;line-height:1.6;white-space:pre-wrap;">{cv_escaped}</div>
          </details>

          <div style="margin-top:16px;">
            <strong>👥 Who to contact on LinkedIn</strong>
            {contact_html}
          </div>
        </div>""")

    body_html = f"""
<!DOCTYPE html>
<html>
<head><meta charset="utf-8"></head>
<body style="font-family:Arial,sans-serif;max-width:800px;margin:auto;padding:20px;color:#222;">
  <h1 style="color:#0077b5">🔍 Daily Job Digest — {today}</h1>
  <p>Here are the <strong>top {len(top_jobs)} jobs</strong> posted in the last few days, tailored just for you.
  Click any "Tailored CV" to expand it.</p>
  {''.join(sections)}
  <hr style="margin-top:40px">
  <p style="color:#999;font-size:12px;text-align:center">
    Powered by your personal Job Agent 🤖 &nbsp;|&nbsp; Good luck today! 💪
  </p>
</body>
</html>"""
    return body_html


# ── Email Sender ──────────────────────────────────────────────────────────────
def send_email(html_body: str):
    today = datetime.now().strftime("%B %d")
    msg = MIMEMultipart("alternative")
    msg["Subject"] = f"🔍 Your Top Jobs Today — {today}"
    msg["From"]    = FROM_EMAIL
    msg["To"]      = TO_EMAIL
    msg.attach(MIMEText(html_body, "html"))

    with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as server:
        server.starttls()
        server.login(SMTP_USER, SMTP_PASSWORD)
        server.sendmail(FROM_EMAIL, TO_EMAIL, msg.as_string())
    log.info(f"Email sent to {TO_EMAIL}")


# ── Main ──────────────────────────────────────────────────────────────────────
def run():
    log.info("Job agent starting…")
    cv          = load_file(CV_PATH)
    preferences = load_file(PREFERENCES_PATH)

    searches = [
        ("HR People Operations Marketing", "Milan Italy"),
        ("Talent Acquisition Content",     "Milan Italy"),
        ("HR Marketing remote",            "Europe"),
    ]

    all_raw  = []
    seen_ids = set()
    for keywords, location in searches:
        log.info(f"Searching: '{keywords}' in '{location}'")
        results = fetch_linkedin_jobs(keywords, location, limit=15)
        for job in results:
            job_id = job.get("job_id") or job.get("job_apply_link", "")
            if job_id not in seen_ids:
                seen_ids.add(job_id)
                all_raw.append(job)
        time.sleep(5)

    log.info(f"Fetched {len(all_raw)} unique raw jobs across all searches")
    jobs = parse_jobs(all_raw)

    top_jobs = select_top_jobs(jobs, cv, preferences)
    log.info(f"Selected {len(top_jobs)} top jobs")

    if not top_jobs:
        log.warning("No matching jobs found today. Skipping email.")
        return

    html = build_email(top_jobs, cv, preferences)
    send_email(html)
    log.info("Done ✅")


if __name__ == "__main__":
    run()
