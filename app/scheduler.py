from datetime import datetime, timedelta
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from app.core.tasks import sync_invoices, sync_credit_notes

scheduler = AsyncIOScheduler(timezone="UTC")


async def daily_sync_job():
    """Daily synchronization: Mon-Sat at 22:00 UTC (fetches today's records)."""
    today_str = datetime.now().strftime("%Y-%m-%d")
    print(f"Executing scheduled daily synchronization for {today_str}...")
    await sync_invoices(start_date=today_str, end_date=today_str)
    await sync_credit_notes(start_date=today_str, end_date=today_str)


async def weekly_sync_job():
    """Weekly synchronization: Sun at 23:00 UTC (fetches last 7 days)."""
    today = datetime.now()
    seven_days_ago = today - timedelta(days=7)
    start_date_str = seven_days_ago.strftime("%Y-%m-%d")
    end_date_str = today.strftime("%Y-%m-%d")
    print(f"Executing scheduled weekly synchronization ({start_date_str} to {end_date_str})...")
    await sync_invoices(start_date=start_date_str, end_date=end_date_str)
    await sync_credit_notes(start_date=start_date_str, end_date=end_date_str)


async def monthly_audit_job():
    """Monthly audit: Last day of month at 23:30 UTC (audits current month)."""
    today = datetime.now()
    first_day_current_month = today.replace(day=1).strftime("%Y-%m-%d")
    today_str = today.strftime("%Y-%m-%d")
    print(f"Executing scheduled monthly audit ({first_day_current_month} to {today_str})...")
    await sync_invoices(start_date=first_day_current_month, end_date=today_str)
    await sync_credit_notes(start_date=first_day_current_month, end_date=today_str)


def setup_scheduler() -> AsyncIOScheduler:
    """Configures and returns the AsyncIOScheduler with hybrid sync cron jobs."""
    # Daily Sync: Mon-Sat at 22:00
    scheduler.add_job(daily_sync_job, "cron", day_of_week="mon-sat", hour=22, minute=0, id="daily_sync")

    # Weekly Sync: Sun at 23:00
    scheduler.add_job(weekly_sync_job, "cron", day_of_week="sun", hour=23, minute=0, id="weekly_sync")

    # Monthly Audit: Last day of month at 23:30
    scheduler.add_job(monthly_audit_job, "cron", day="last", hour=23, minute=30, id="monthly_audit")

    return scheduler
