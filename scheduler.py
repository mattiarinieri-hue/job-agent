"""
scheduler.py - Runs the job agent every weekday at 8:00 AM local time.
Run with: python scheduler.py
Keep alive with: nohup python scheduler.py &  (or use systemd/Railway/Render cron)
"""

import schedule
import time
import logging
from agent import run

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

def job():
    try:
        run()
    except Exception as e:
        logging.error(f"Agent failed: {e}", exc_info=True)

# Schedule Mon–Fri at 08:00
schedule.every().monday.at("08:00").do(job)
schedule.every().tuesday.at("08:00").do(job)
schedule.every().wednesday.at("08:00").do(job)
schedule.every().thursday.at("08:00").do(job)
schedule.every().friday.at("08:00").do(job)

logging.info("Scheduler started. Waiting for 8 AM on weekdays…")
while True:
    schedule.run_pending()
    time.sleep(30)
