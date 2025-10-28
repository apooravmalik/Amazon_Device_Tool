# backend/routes.py

from fastapi import APIRouter, HTTPException, Query
from services import device_service, proevent_service, cache_service
from models import (DeviceOut, DeviceActionRequest, DeviceActionSummaryResponse,
                   BuildingOut, BuildingTimeRequest, BuildingTimeResponse,
                   IgnoredItemRequest, IgnoredItemBulkRequest,
                   PanelStatus)
from sqlite_config import (get_building_time, set_building_time,
                           get_ignored_proevents, set_proevent_ignore_status,
                           get_all_building_times) # Import this helper
from logger import get_logger

router = APIRouter()
logger = get_logger(__name__)


# --- Panel Status Endpoints (NOT IN NEW LOGIC) ---
# These are "dummy" endpoints for the frontend.
# Our new scheduler logic ignores this cache.

@router.get("/panel_status", response_model=PanelStatus)
def get_panel_status():
    status = cache_service.get_cache_value('panel_armed')
    if status is None:
        status = True # Default to armed
        cache_service.set_cache_value('panel_armed', status)
    return PanelStatus(armed=status)

@router.post("/panel_status", response_model=PanelStatus)
def set_panel_status(status: PanelStatus):
    cache_service.set_cache_value('panel_armed', status.armed)
    logger.info(f"Global panel status (dummy) set to: {'Armed' if status.armed else 'Disarmed'}")
    return status


# --- Building and Device Routes (CRITICAL LOGIC) ---

@router.get("/buildings", response_model=list[BuildingOut])
def list_buildings():
    """
    Fetches real buildings from PROD DB and merges schedules from SQLite DB.
    """
    logger.info("API: Fetching all buildings...")
    # This now calls our service that hits the PROD DB
    buildings_from_db = device_service.get_distinct_buildings() 
    
    # This gets all schedules from our local SQLite DB
    schedules_from_sqlite = get_all_building_times()
    
    buildings_out = []
    for b in buildings_from_db:
        building_id = b["id"]
        # Get the saved schedule for this building
        schedule = schedules_from_sqlite.get(building_id)
        
        # Provide defaults if no schedule is saved
        start_time = schedule.get("start_time", "09:00") if schedule else "09:00"
        end_time = schedule.get("end_time", "17:00") if schedule else "17:00"

        buildings_out.append(BuildingOut(
            id=building_id,
            name=b["name"],
            start_time=start_time,
            end_time=end_time
        ))
    return buildings_out


@router.get("/devices", response_model=list[DeviceOut])
def list_proevents(
    building: int | None = Query(default=None),
    search: str | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=1000),
    offset: int = Query(default=0, ge=0)
):
    """
    Fetches real devices (proevents) from PROD DB and merges
    ignore status from SQLite DB. This provides the state for colors.
    """
    if building is None:
        raise HTTPException(status_code=400, detail="A building ID is required.")
        
    # 1. Get Live Data (from PROD DB via our updated service)
    proevents = proevent_service.get_all_proevents_for_building(
        building_id=building, search=search, limit=limit, offset=offset
    )
    
    # 2. Get Saved Config (from SQLite DB)
    ignored_proevents = get_ignored_proevents()
    
    proevents_out = []
    
    for p in proevents:
        # Get the ignore status from our local SQLite DB
        ignore_status = ignored_proevents.get(p["id"], {})
        
        # This is the logic for the color:
        # 0 (Reactive) = "armed" (Red)
        # 1 (Non-Reactive) = "disarmed" (Green)
        state_str = "armed" if p["reactive_state"] == 0 else "disarmed"
        
        proevent_out = DeviceOut(
            id=p["id"],
            name=p["name"],
            state=state_str,  # This determines the color
            building_name=p.get("building_name", ""), # From the JOIN query
            is_ignored=ignore_status.get("ignore_on_disarm", False) # From SQLite
        )
        proevents_out.append(proevent_out)

    return proevents_out


# --- Schedule and Ignore Endpoints (CRITICAL LOGIC) ---

@router.get("/buildings/{building_id}/time")
def get_building_scheduled_time(building_id: int):
    # This correctly fetches from SQLite
    times = get_building_time(building_id)
    return {
        "building_id": building_id,
        "start_time": times.get("start_time") if times else None,
        "end_time": times.get("end_time") if times else None
    }

@router.post("/buildings/{building_id}/time", response_model=BuildingTimeResponse)
def set_building_scheduled_time(building_id: int, request: BuildingTimeRequest):
    # This correctly saves to SQLite
    if request.building_id != building_id:
        raise HTTPException(400, "Building ID in path and body must match")
        
    success = set_building_time(building_id, request.start_time, request.end_time)
    if not success:
        raise HTTPException(500, "Failed to update building scheduled time")
    
    return BuildingTimeResponse(
        building_id=building_id,
        start_time=request.start_time,
        end_time=request.end_time,
        updated=True
    )

@router.post("/buildings/{building_id}/reevaluate")
def reevaluate_building(building_id: int):
    """
    Triggers our new scheduler logic for one building *right now*.
    """
    try:
        # This calls our "state machine"
        proevent_service.reevaluate_building_state(building_id)
        return {"status": "success", "message": f"Building {building_id} re-evaluated."}
    except Exception as e:
        logger.error(f"Failed to re-evaluate building {building_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to re-evaluate building: {e}")


@router.post("/proevents/ignore/bulk")
def manage_ignored_proevents_bulk(req: IgnoredItemBulkRequest):
    """
    Saves the ignore list to the local SQLite DB.
    """
    try:
        for item in req.items:
            set_proevent_ignore_status(
                item.item_id, item.building_frk, item.device_prk, 
                ignore_on_arm=False, # We don't use this
                ignore_on_disarm=item.ignore
            )
        return {"status": "success"}
    except Exception as e:
        logger.error(f"Error saving ignore bulk: {e}")
        raise HTTPException(500, "Failed to save ignore status")


# --- Unused Endpoint (NOT IN NEW LOGIC) ---

@router.post("/devices/action", response_model=DeviceActionSummaryResponse)
def device_action(req: DeviceActionRequest):
    """
    This endpoint is not used by the frontend.
    """
    logger.warning(f"Legacy endpoint /devices/action called for building {req.building_id}")
    
    reactive_state = 1 if req.action.lower() == "disarm" else 0
    
    try:
        affected_rows = proevent_service.set_proevent_reactive_for_building(
            req.building_id, reactive_state, []
        )
        return DeviceActionSummaryResponse(
            success_count=affected_rows,
            failure_count=0,
            details=[]
        )
    except Exception as e:
        logger.error(f"Error during legacy bulk action for building {req.building_id}: {e}")
        raise HTTPException(500, str(e))