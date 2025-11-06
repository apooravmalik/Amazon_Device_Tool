# backend/services/proevent_service.py

from logger import get_logger
from services import proserver_service, device_service, cache_service
import sqlite_config
import pytz
from datetime import datetime

logger = get_logger(__name__)

# --- UNCHANGED EXISTING FUNCTIONS ---

def get_all_proevents_for_building(building_id: int, search: str | None = None, limit: int = 100, offset: int = 0) -> list[dict]:
    """
    Gets all proevents for a building from the ProServer DB.
    """
    try:
        all_devices = proserver_service.get_proevents_for_building_from_db(building_id)
        
        devices_out = []
        for dev in all_devices:
            devices_out.append({
                "id": dev["id"],
                "name": dev["name"],
                "reactive_state": dev["state"] # 0=Reactive, 1=Non-Reactive
            })
        
        # TODO: Add server-side search/limit/offset if needed
        return devices_out
        
    except Exception as e:
        logger.error(f"Error getting proevents for building {building_id}: {e}")
        return []

def set_proevent_reactive_for_building(building_id: int, reactive: int, ignore_ids: list[int] | None = None) -> int:
    """
    Sets the reactive state for all proevents in a building,
    skipping any IDs in the ignore_ids list.
    """
    if ignore_ids is None:
        ignore_ids = []
    
    logger.info(f"Setting reactive state to {reactive} for building {building_id}, ignoring {len(ignore_ids)} IDs.")
    
    try:
        all_devices = proserver_service.get_proevents_for_building_from_db(building_id)
        if not all_devices:
            logger.warning(f"No devices found for building {building_id}, nothing to update.")
            return 0
        
        target_states = []
        for dev in all_devices:
            if dev['id'] in ignore_ids:
                target_states.append({"id": dev['id'], "state": dev['state']})
            else:
                target_states.append({"id": dev['id'], "state": reactive})

        success = proserver_service.set_proevent_reactive_state_bulk(target_states)
        
        return (len(target_states) - len(ignore_ids)) if success else 0
        
    except Exception as e:
        logger.error(f"Error in set_proevent_reactive_for_building (Building {building_id}): {e}")
        return 0

def is_time_between(start_time_str: str, end_time_str: str | None) -> bool:
    """
    Checks if the current time is between two H:M string times in 'Asia/Kolkata' (IST).
    """
    if not start_time_str or not end_time_str:
        return False
    
    try:
        tz = pytz.timezone('Asia/Kolkata')
        now = datetime.now(tz).time()
        start_time = datetime.strptime(start_time_str, '%H:%M').time()
        end_time = datetime.strptime(end_time_str, '%H:%M').time()

        if start_time <= end_time:
            return start_time <= now <= end_time
        else: # Handles overnight schedules (e.g., 22:00 to 06:00)
            return start_time <= now or now <= end_time
    except Exception as e:
        logger.error(f"Error checking time {start_time_str}-{end_time_str}: {e}")
        return False


# --- MODIFICATION: NEW SCHEDULER LOGIC ---

def check_and_manage_scheduled_states():
    """
    Job function for the scheduler.
    NEW LOGIC:
    Checks if a building is DISARMED at a single specific time
    and sends an alert.
    """
    logger.info("Scheduler running: Checking all building alert times...")
    
    try:
        # Get live armed status for all buildings
        live_building_arm_states = proserver_service.get_all_live_building_arm_states()

        # Get cache of which buildings were "at their alert time" last cycle
        # This prevents sending the alert every second *during* the alert minute
        cache_key = "building_alert_status"
        cached_states = cache_service.get_cache_value(cache_key)
        if cached_states is None:
            cached_states = {}

        new_cached_states = cached_states.copy()
        all_buildings = device_service.get_distinct_buildings()

        # Get current time in H:M format (e.g., "22:30")
        tz = pytz.timezone('Asia/Kolkata')
        current_time_str = datetime.now(tz).strftime('%H:%M')
        logger.info(f"Current check time: {current_time_str}")

        for building in all_buildings:
            building_id = building['id']
            
            # 1. Get this building's live ARMED/DISARMED status
            # Default to ARMED (True) if not found in the map
            live_state_is_armed = live_building_arm_states.get(building_id, True)
            
            # 2. Get this building's single alert time from SQLite
            schedule = sqlite_config.get_building_time(building_id)
            if not schedule or not schedule.get('start_time'):
                # This building has no alert time set, so we skip it
                new_cached_states[str(building_id)] = False # Ensure it's marked as not in alert
                continue 

            alert_time = schedule['start_time'] # We re-purpose start_time
            
            # 3. Check if we are AT the alert time
            is_at_alert_time = (current_time_str == alert_time)
            
            # 4. Get the cached "at alert time" status from the last run
            was_at_alert_time = cached_states.get(str(building_id), False)

            # --- This is the new logic ---
            
            # Only run the logic if the panel is DISARMED
            if not live_state_is_armed:
                
                # Check if it's the exact time AND we haven't sent the alert yet
                if is_at_alert_time and not was_at_alert_time:
                    # This is the one-time trigger!
                    logger.info(f"[Building {building_id}]: Panel is DISARMED at the alert time ({alert_time}). Sending alert.")
                    # Send the new alert message
                    proserver_service.send_disarmed_alert(building_id)
            
            elif is_at_alert_time:
                 logger.info(f"[Building {building_id}]: Panel is ARMED at alert time ({alert_time}). No action taken.")
            
            # Update the cache for the next cycle
            new_cached_states[str(building_id)] = is_at_alert_time
        
        # 5. Save the new states back to the cache file
        cache_service.set_cache_value(cache_key, new_cached_states)
            
    except Exception as e:
        logger.error(f"Error in scheduled check_and_manage_scheduled_states: {e}")

def reevaluate_building_state(building_id: int):
    """
    Triggers an immediate re-evaluation of a single building's state.
    This is called by the API.
    
    NOTE: With the new logic, this is less useful, but we can
    leave it to manually trigger the 'check_and_manage_scheduled_states'
    for testing, though it's less direct.
    For now, we'll just log that it was called.
    """
    logger.warning(f"Re-evaluation triggered for building {building_id}, but this function is deprecated by new logic.")
    # try:
    #     check_and_manage_scheduled_states()
    # except Exception as e:
    #     logger.error(f"Error in reevaluate_building_state (Building {building_id}): {e}")
    #     raise
    pass

# --- NEW PRIVATE FUNCTION WITH CORE LOGIC ---

# def _evaluate_building_state(building_id: int):
#     """
#     (COMMENTED OUT)
#     This is the new "state machine" logic for a single building.
#     It decides whether to snapshot, revert, or do nothing.
#     """
#     schedule = sqlite_config.get_building_time(building_id)
#     if not schedule:
#         # This building has no schedule, so we do nothing.
#         return
#
#     is_inside_schedule = is_time_between(schedule['start_time'], schedule['end_time'])
#     snapshot = sqlite_config.get_snapshot(building_id)
#     snapshot_exists = (snapshot is not None)
#
#     # Case A: Schedule just started.
#     if is_inside_schedule and not snapshot_exists:
#         logger.info(f"[Building {building_id}]: Schedule just started. Taking snapshot...")
#         take_snapshot_and_apply_schedule(building_id)
#
#     # Case B: Schedule is active and snapshot is already taken.
#     elif is_inside_schedule and snapshot_exists:
#         logger.info(f"[Building {building_id}]: Schedule is active. No action needed.")
#         # This is the line that solves your problem. We do nothing.
#         pass
#
#     # Case C: Schedule just ended.
#     elif not is_inside_schedule and snapshot_exists:
#         logger.info(f"[Building {building_id}]: Schedule just ended. Reverting snapshot...")
#         revert_snapshot(building_id, snapshot)
#
#     # Case D: Outside schedule, no snapshot. Normal operation.
#     elif not is_inside_schedule and not snapshot_exists:
#         # This is normal. We can log it if we want, but pass is fine.
#         pass

# --- NEW HELPER FUNCTIONS ---

# def take_snapshot_and_apply_schedule(building_id: int):
#     """
#     (COMMENTED OUT)
#     1. Gets all device states FOR THAT BUILDING from the ProServer DB.
#     2. Saves them to the local snapshot DB.
#     3. Applies the scheduled "disarm" state.
#     """
#     try:
#         # 1. Get snapshot of *all* devices from the ProServer DB
#         all_devices_from_db = proserver_service.get_proevents_for_building_from_db(building_id)
#         
#         if not all_devices_from_db:
#             logger.warning(f"Building {building_id}: No devices found in ProServer DB to snapshot.")
#             return
#
#         snapshot_data = [
#             {"id": dev["id"], "state": dev["state"]} 
#             for dev in all_devices_from_db
#         ]
#         
#         # 2. Save snapshot to our local SQLite DB
#         sqlite_config.save_snapshot(building_id, snapshot_data)
#         
#         # 3. Apply scheduled state
#         ignored_map = sqlite_config.get_ignored_proevents()
#         ignored_ids = {
#             pid for pid, data in ignored_map.items()
#             if data.get("building_frk") == building_id and data.get("ignore_on_disarm")
#         }
#         
#         target_states = []
#         for device in snapshot_data:
#             device_id = device['id']
#             if device_id in ignored_ids:
#                 target_states.append({"id": device_id, "state": 1}) # 1 = Non-Reactive
#             else:
#                 target_states.append({"id": device_id, "state": 0}) # 0 = Reactive
#
#         logger.info(f"[Building {building_id}]: Snapshot taken. Setting {len(ignored_ids)} devices to Non-Reactive (1) and {len(target_states) - len(ignored_ids)} to Reactive (0).")
#         
#         proserver_service.set_proevent_reactive_state_bulk(target_states)
#
#     except Exception as e:
#         logger.error(f"Failed to take snapshot for building {building_id}: {e}")

# def revert_snapshot(building_id: int, snapshot_data: list[dict]):
#     """
#     (COMMENTED OUT)
#     1. Pushes the snapshot data back to the proserver.
#     2. Clears the snapshot from the DB.
#     """
#     try:
#         logger.info(f"[Building {building_id}]: Reverting {len(snapshot_data)} devices to their original states.")
#         
#         # 1. Apply snapshot
#         proserver_service.set_proevent_reactive_state_bulk(snapshot_data)
#         
#         # 2. Clean up
#         sqlite_config.clear_snapshot(building_id)
#
#     except Exception as e:
#         logger.error(f"Failed to revert snapshot for building {building_id}: {e}")