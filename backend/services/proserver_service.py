import socket
import pyodbc  # Import the DB driver
from logger import get_logger
from contextlib import contextmanager # Import the context manager utility

# Import the connection strings and settings directly from the config file
from config import (PROSERVER_IP, PROSERVER_PORT, 
                    CONNECTION_STRING)

logger = get_logger(__name__)

# --- NEW: Connection Helper ---

@contextmanager
def get_proserver_connection():
    """
    Context manager for ProServer DB connections.
    This handles all the try/except/commit/rollback/close logic.
    """
    conn = None
    try:
        conn = pyodbc.connect(CONNECTION_STRING)
        yield conn
    except Exception as e:
        if conn:
            conn.rollback() # Rollback on error
        logger.error(f"ProServer DB transaction error: {e}")
        raise
    else:
        if conn:
            conn.commit() # Commit on success
    finally:
        if conn:
            conn.close() # Always close the connection

# --- TCP/IP Functions (Unchanged) ---

def send_proserver_notification(building_name: str, device_id: int):
    """
    Sends a unified notification to the ProServer.
    Format: Axe,{building_name}_{device_id}@
    """
    message = f"Axe,{building_name}_{device_id}@"
    logger.info(f"Attempting to send notification to ProServer: {message}")
    
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.connect((PROSERVER_IP, PROSERVER_PORT))
            s.sendall(message.encode())
    except Exception as e:
        logger.error(f"Failed to send notification to ProServer: {e}")

def send_axe_message():
    """
    Sends a generic "Axe" message when the panel is armed.
    """
    message = "Axe,GlobalArmed@"
    logger.info(f"PANEL ARMED. Sending message to ProServer: {message}")
    
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.connect((PROSERVER_IP, PROSERVER_PORT))
            s.sendall(message.encode())
    except Exception as e:
        logger.error(f"Failed to send global armed notification to ProServer: {e}")

# --- UPDATED: REAL DATABASE FUNCTIONS ---
# These functions are now cleaner and use the new helper

def get_proevents_for_building_from_db(building_id: int) -> list[dict]:
    """
    Connects to the ProServer DB and runs your query to get all
    devices, their IDs, their states, and the building name.
    """
    logger.info(f"Connecting to ProServer DB to get proevents for building {building_id}...")
    
    # This is the new, more efficient query you provided
    sql = """
        SELECT
            p.pevReactive_FRK,
            p.ProEvent_PRK,
            p.pevAlias_TXT,
            b.bldBuildingName_TXT
        FROM
            ProEvent_TBL AS p
        LEFT JOIN
            Building_TBL AS b ON p.pevBuilding_FRK = b.Building_PRK
        WHERE
            p.pevBuilding_FRK = ?;
    """
    results = []

    try:
        with get_proserver_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(sql, (building_id,))
            rows = cursor.fetchall()
            
            if not rows:
                logger.warning(f"No proevents found in ProEvent_TBL for building {building_id}")
                return []
                
            for row in rows:
                results.append({
                    "id": row.ProEvent_PRK,
                    "state": row.pevReactive_FRK,  # This is the 0 or 1
                    "name": row.pevAlias_TXT,
                    "building_name": row.bldBuildingName_TXT
                })
        
        logger.info(f"Successfully fetched {len(results)} device states from DB for building {building_id}")
        return results
        
    except Exception as e:
        logger.error(f"Failed to query ProServer DB for proevents: {e}")
        raise

def set_proevent_reactive_state_bulk(target_states: list[dict]) -> bool:
    """
    Connects to the ProServer DB and updates device states in bulk.
    'target_states' is a list: [{'id': 1001, 'state': 0}, {'id': 1002, 'state': 1}, ...]
    """
    if not target_states:
        logger.info("No target states provided to set_proevent_reactive_state_bulk. Skipping.")
        return True

    logger.info(f"Connecting to ProServer DB to set {len(target_states)} device states...")
    
    sql = """
        UPDATE ProEvent_TBL 
        SET pevReactive_FRK = ? 
        WHERE ProEvent_PRK = ?
    """
    
    data_to_update = [
        (item['state'], item['id']) 
        for item in target_states
    ]
    
    try:
        with get_proserver_connection() as conn:
            cursor = conn.cursor()
            cursor.executemany(sql, data_to_update)
            # The commit is handled automatically by the helper
            
        logger.info(f"Successfully updated {len(data_to_update)} device states in ProServer DB.")
        return True
        
    except Exception as e:
        logger.error(f"Failed to bulk update states in ProServer DB: {e}")
        return False
    
def get_all_live_building_arm_states() -> dict[int, bool]:
    """
    Fetches the arm/disarm state for all buildings that have an arming device.
    Returns a dictionary: {building_id: is_armed_status}
    """
    logger.info("Connecting to ProServer DB to get all building arm states...")
    
    # This query finds all arming devices
    sql = """
        SELECT dvcbuilding_FRK, dvcCurrentState_TXT 
        FROM Device_TBL 
        WHERE dvcDeviceType_FRK = 138
    """
    
    # This dictionary will hold the final status: {building_id: is_armed}
    building_states = {}

    try:
        with get_proserver_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(sql)
            rows = cursor.fetchall()
            
            if not rows:
                logger.warning("No arming devices (Type 138) found in Device_TBL.")
                return {}
                
            for row in rows:
                building_id = row.dvcbuilding_FRK
                state_text = row.dvcCurrentState_TXT or ""
                
                # Your logic: 'AreaArmingStates.2' means DISARMED (False)
                if 'AreaArmingStates.2' in state_text:
                    building_states[building_id] = False # Disarmed
                else:
                    building_states[building_id] = True # Armed
        
        logger.info(f"Successfully fetched {len(building_states)} building arm states.")
        return building_states
        
    except Exception as e:
        logger.error(f"Failed to query ProServer DB for building arm states: {e}")
        return {} # Return an empty dict on failure
    
def get_all_distinct_buildings_from_db() -> list[dict]:
    """
    Fetches a list of all unique buildings from the Device_TBL.
    """
    logger.info("Connecting to ProServer DB to get distinct buildings...")
    
    # This query assumes a Device_TBL with building names
    sql = """
        SELECT DISTINCT dvcbuilding_FRK, dvcBuildingName_TXT
        FROM Device_TBL
        WHERE dvcBuildingName_TXT IS NOT NULL
        ORDER BY dvcBuildingName_TXT
    """
    results = []

    try:
        with get_proserver_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(sql)
            rows = cursor.fetchall()
            
            if not rows:
                logger.warning("No buildings found in Device_TBL.")
                return []
                
            for row in rows:
                results.append({
                    "id": row.dvcbuilding_FRK,
                    "name": row.dvcBuildingName_TXT
                })
        
        logger.info(f"Successfully fetched {len(results)} distinct buildings.")
        return results
        
    except Exception as e:
        logger.error(f"Failed to query ProServer DB for distinct buildings: {e}")
        return []