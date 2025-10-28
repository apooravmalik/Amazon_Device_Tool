# backend/services/scheduler_service.py

import schedule
import time
import threading
from logger import get_logger
from services import proevent_service
import traceback  # Import the traceback module

logger = get_logger(__name__)

def scheduled_job():
    """
    Job function for the scheduler to manage proevent states based on time.
    """
    logger.info("Scheduler running: Managing scheduled states...")
    try:
        proevent_service.check_and_manage_scheduled_states()
    except Exception as e:
        # Log the full traceback to pinpoint the exact line of the error
        tb_str = traceback.format_exc()
        logger.error(f"Error in scheduled proevent check: {e}\n{tb_str}")

def run_scheduler():
    """
    Runs the scheduler in a separate thread.
    """
    schedule.every(1).minutes.do(scheduled_job)

    while True:
        schedule.run_pending()
        time.sleep(1)

def start_scheduler():
    """
    Starts the scheduler in a background thread.
    """
    scheduler_thread = threading.Thread(target=run_scheduler)
    scheduler_thread.daemon = True
    scheduler_thread.start()
    logger.info("Scheduler started.")