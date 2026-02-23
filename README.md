# 💼 Daily Job Agent

Sends your girlfriend a daily email every weekday at 8 AM with:
- ✅ Top 10 LinkedIn jobs from the last 24h, matched to her CV & preferences
- 📄 A tailored version of her CV for each job
- 👥 2 LinkedIn networking contacts to approach per job

---

## 🚀 Setup (15 minutes)

### 1. Clone and install
```bash
git clone <your-repo>
cd job-agent
pip install -r requirements.txt
```

### 2. Get your API keys

| Service | What for | Free tier |
|---------|----------|-----------|
| [Anthropic](https://console.anthropic.com) | CV tailoring + job scoring | Pay per use (~$0.10/day) |
| [RapidAPI JSearch](https://rapidapi.com/letscrape-6bRBa3QguO5/api/jsearch) | LinkedIn job search | 200 req/month free |
| Gmail App Password | Sending emails | Free |

### 3. Configure
```bash
cp .env.example .env
# Edit .env with your keys and emails
```

### 4. Add CV and preferences
Edit `cv.txt` with her real CV (plain text).  
Edit `preferences.txt` with her job preferences (location, roles, salary, etc.)

### 5. Test it
```bash
python agent.py   # runs immediately, sends one email
```

### 6. Start the scheduler
```bash
# Option A: Keep running in background
nohup python scheduler.py &

# Option B: Use cron (more reliable)
crontab -e
# Add: 0 8 * * 1-5 cd /path/to/job-agent && python agent.py
```

---

## ☁️ Deploy to the cloud (recommended)

### Railway (easiest)
1. Push to GitHub
2. Connect repo on [railway.app](https://railway.app)
3. Set env vars in Railway dashboard
4. Add a cron trigger: `0 8 * * 1-5`

### Render
1. Create a Background Worker
2. Set start command: `python scheduler.py`
3. Add env vars

---

## 📧 Email preview
Each job card in the email contains:
- Job title, company, location, match score
- "Apply on LinkedIn" button
- Expandable tailored CV section
- 2 LinkedIn contact suggestions with outreach message templates

---

## 💰 Cost estimate
~$0.05–0.15/day in Anthropic API costs (10 jobs × CV tailoring + contact suggestions).
RapidAPI JSearch free tier: 200 requests/month → ~6 requests/day = fine.

---

## 🛠 Customisation

- **Change search depth**: Edit `limit=30` in `fetch_linkedin_jobs()`
- **Change time zone**: scheduler uses local server time; adjust `"08:00"` accordingly
- **Add more regions**: Run multiple keyword/location combos and merge results
- **Multiple CVs**: Pass different `cv.txt` paths per job category
