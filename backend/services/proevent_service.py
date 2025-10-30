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
    Gets all proevents for a building, enriched with their reactive state.
    """
    try:
        devices = device_service.get_devices(
            building_id=building_id, search=search, limit=limit, offset=offset
        )
        if not devices:
            return []
        
        proevent_ids = [d["id"] for d in devices]
        proevent_states = proserver_service.get_proevent_reactive_state(proevent_ids)

        for device in devices:
            # Per your logic: 0=Reactive, 1=Non-Reactive
            # Default to 1 (Non-Reactive) if state is unknown
            device["reactive_state"] = proevent_states.get(device["id"], 1) 
        
        return devices
    except Exception as e:
        logger.error(f"Error getting proevents for building {building_id}: {e}")
        return []

def set_proevent_reactive_for_building(building_id: int, reactive: int, ignore_ids: list[int] | None = None) -> int:
    """
    Sets the reactive state for all proevents in a building,
    skipping any IDs in the ignore_ids list.
    
    NOTE: This function is still used by the old '/devices/action' route,
    but not by our new scheduler logic.
    """
    if ignore_ids is None:
        ignore_ids = []
    
    logger.info(f"Setting reactive state to {reactive} for building {building_id}, ignoring {len(ignore_ids)} IDs.")
    
    try:
        devices = device_service.get_devices(building_id=building_id, limit=1000)
        if not devices:
            logger.warning(f"No devices found for building {building_id}, nothing to update.")
            return 0
            
        proevent_ids_to_update = [
            d["id"] for d in devices if d["id"] not in ignore_ids
        ]

        if not proevent_ids_to_update:
            logger.info(f"All devices in building {building_id} were on the ignore list. No updates sent.")
            return 0

        # This function sends a single state to a list of IDs
        success = proserver_service.set_proevent_reactive_state(
            proevent_ids_to_update, reactive
        )
        return len(proevent_ids_to_update) if success else 0
        
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
        # --- THIS IS THE UPDATED LINE ---
        tz = pytz.timezone('Asia/Kolkata')
        # --- END OF UPDATE ---
        
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
    Loops through all buildings.
    - If DISARMED, it runs the snapshot logic.
    - If ARMED, it checks if an alarm needs to be sent.
    """
    logger.info("Scheduler running: Checking all building states...")
    
    try:
        # 1. Get a single snapshot of ALL building live arm states
        live_building_arm_states = proserver_service.get_all_live_building_arm_states()

        # 2. Get the LAST KNOWN schedule states from our cache
        # This is used to detect the *start* of the schedule
        cached_states = cache_service.get_cache_value("building_schedule_states")
        if cached_states is None:
            cached_states = {}  # Initialize if cache is empty

        new_cached_states = cached_states.copy()

        # 3. Get the list of all buildings
        all_buildings = device_service.get_distinct_buildings()
        if not all_buildings:
            logger.info("No buildings found in device list.")
            return

        # 4. Loop, COMPARE, and act
        for building in all_buildings:
            building_id = building['id']
            
            # --- Get ALL facts for this building ---
            
            # Get live armed state (default to Armed per your rule)
            live_state_is_armed = live_building_arm_states.get(building_id, True)
            
            # Get live schedule state
            schedule = sqlite_config.get_building_time(building_id)
            is_inside_schedule = is_time_between(schedule.get('start_time'), schedule.get('end_time')) if schedule else False
            
            # Get cached schedule state (with safe default for first-ever run)
            was_in_schedule = cached_states.get(str(building_id), False)

            # --- This is the new, simplified Decision Tree ---

            if live_state_is_armed:
                # --- The building is ARMED ---
                
                # Check for the ALARM condition:
                # The panel is ARMED, AND the schedule just started (it is now
                # inside the schedule, but last cycle it was not).
                if is_inside_schedule and not was_in_schedule:
                    logger.info(f"[Building {building_id}]: ALARM! Schedule started but panel is still ARMED. Sending AXE message.")
                    proserver_service.send_armed_axe_message(building_id)
                
                # In all other "ARMED" cases (e.g., armed and outside schedule,
                # or armed and already inside schedule), we do nothing.
                else:
                    logger.info(f"[Building {building_id}]: Panel is ARMED. No action needed.")

                # Safety Cleanup: If we are ARMED, always clear any old snapshot
                if sqlite_config.get_snapshot(building_id) is not None:
                    logger.warning(f"[Building {building_id}]: Panel is ARMED. Clearing leftover snapshot.")
                    sqlite_config.clear_snapshot(building_id)
            
            else:
                # --- The building is DISARMED ---
                logger.info(f"[Building {building_id}]: Panel is DISARMED. Running snapshot/revert logic.")
                
                # Run the snapshot logic (this is safe to run every minute)
                _evaluate_building_state(building_id)
            
            # Update the cache for the *next* run with the schedule state
            new_cached_states[str(building_id)] = is_inside_schedule
        
        # 5. Save the new schedule states back to the cache file
        # We rename the cache key to be more accurate
        cache_service.set_cache_value("building_schedule_states", new_cached_states)
            
    except Exception as e:
        logger.error(f"Error in scheduled check_and_manage_scheduled_states: {e}")

def reevaluate_building_state(building_id: int):
    """
    Triggers an immediate re-evaluation of a single building's state.
    This is called by the API.
    """
    try:
        is_panel_armed = cache_service.get_cache_value('panel_armed')
        if is_panel_armed:
            logger.warning(f"Manual re-evaluation for building {building_id} skipped: Panel is ARMED.")
            return

        logger.info(f"Manual re-evaluation triggered for building {building_id}.")
        _evaluate_building_state(building_id)
    except Exception as e:
        logger.error(f"Error in reevaluate_building_state (Building {building_id}): {e}")
        raise

# --- NEW PRIVATE FUNCTION WITH CORE LOGIC ---

def _evaluate_building_state(building_id: int):
    """
    This is the new "state machine" logic for a single building.
    It decides whether to snapshot, revert, or do nothing.
    """
    schedule = sqlite_config.get_building_time(building_id)
    if not schedule:
        # This building has no schedule, so we do nothing.
        return

    is_inside_schedule = is_time_between(schedule['start_time'], schedule['end_time'])
    snapshot = sqlite_config.get_snapshot(building_id)
    snapshot_exists = (snapshot is not None)

    # Case A: Schedule just started.
    if is_inside_schedule and not snapshot_exists:
        logger.info(f"[Building {building_id}]: Schedule just started. Taking snapshot...")
        take_snapshot_and_apply_schedule(building_id)

    # Case B: Schedule is active and snapshot is already taken.
    elif is_inside_schedule and snapshot_exists:
        logger.info(f"[Building {building_id}]: Schedule is active. No action needed.")
        # This is the line that solves your problem. We do nothing.
        pass

    # Case C: Schedule just ended.
    elif not is_inside_schedule and snapshot_exists:
        logger.info(f"[Building {building_id}]: Schedule just ended. Reverting snapshot...")
        revert_snapshot(building_id, snapshot)

    # Case D: Outside schedule, no snapshot. Normal operation.
    elif not is_inside_schedule and not snapshot_exists:
        # This is normal. We can log it if we want, but pass is fine.
        pass

# --- NEW HELPER FUNCTIONS ---

def take_snapshot_and_apply_schedule(building_id: int):
    """
    1. Gets all device states FOR THAT BUILDING from the ProServer DB.
    2. Saves them to the local snapshot DB.
    3. Applies the NEW scheduled state (Ignored=1, Rest=0).
    """
    try:
        # 1. Get snapshot of *all* devices from the ProServer DB
        all_devices_from_db = proserver_service.get_proevents_for_building_from_db(building_id)
        
        if not all_devices_from_db:
            logger.warning(f"Building {building_id}: No devices found in ProServer DB to snapshot.")
            return

        snapshot_data = [
            {"id": dev["id"], "state": dev["state"]} 
            for dev in all_devices_from_db
        ]
        
        # 2. Save snapshot to our local SQLite DB
        sqlite_config.save_snapshot(building_id, snapshot_data)
        
        # 3. Apply scheduled state (NEW LOGIC)
        ignored_map = sqlite_config.get_ignored_proevents()
        ignored_ids = {
            pid for pid, data in ignored_map.items()
            if data.get("building_frk") == building_id and data.get("ignore_on_disarm")
        }
        
        target_states = []
        for device in snapshot_data:
            device_id = device['id']
            
            # --- THIS IS THE NEW LOGIC ---
            if device_id in ignored_ids:
                # Set IGNORED devices to 1 (Non-Reactive)
                target_states.append({"id": device_id, "state": 1}) 
            else:
                # Set ALL OTHER devices to 0 (Reactive)
                target_states.append({"id": device_id, "state": 0})
            # --- END OF NEW LOGIC ---

        logger.info(f"[Building {building_id}]: Snapshot taken. Setting {len(ignored_ids)} devices to Non-Reactive (1) and {len(target_states) - len(ignored_ids)} to Reactive (0).")
        
        proserver_service.set_proevent_reactive_state_bulk(target_states)

    except Exception as e:
        logger.error(f"Failed to take snapshot for building {building_id}: {e}")

def revert_snapshot(building_id: int, snapshot_data: list[dict]):
    """
    1. Pushes the snapshot data back to the proserver.
    2. Clears the snapshot from the DB.
    """
    try:
        logger.info(f"[Building {building_id}]: Reverting {len(snapshot_data)} devices to their original states.")
        
        # 1. Apply snapshot
        # The data from get_snapshot() is already in the correct format
        proserver_service.set_proevent_reactive_state_bulk(snapshot_data)
        
        # 2. Clean up
        sqlite_config.clear_snapshot(building_id)

    except Exception as e:
        logger.error(f"Failed to revert snapshot for building {building_id}: {e}")