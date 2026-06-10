import os
from typing import List
from fastapi import APIRouter, HTTPException, status
from schemas import TeamModel, MatchModel, RECFScoringModel, SkillsModel, BulkMatchImportModel

router = APIRouter()

# Safely reference the initialized application context from the main entrypoint
from main import app

# ==========================================
# --- TEAM ENDPOINTS ---
# ==========================================
@router.post("/api/teams", status_code=status.HTTP_201_CREATED, tags=["Teams"])
def register_team(team: TeamModel):
    db = app.state.db
    if db.teams.find_one({"team_number": team.team_number}):
        raise HTTPException(status_code=400, detail=f"Team {team.team_number} already registered.")
    db.teams.insert_one(team.model_dump())
    return {"message": f"Team {team.team_number} registered successfully."}


@router.get("/api/teams", response_model=List[TeamModel], tags=["Teams"])
def list_teams():
    return list(app.state.db.teams.find({}, {"_id": 0}))


# ==========================================
# --- MATCH ENDPOINTS ---
# ==========================================
@router.post("/api/matches", status_code=status.HTTP_201_CREATED, tags=["Matches"])
def create_match(match: MatchModel):
    db = app.state.db
    normalized_round = match.round.capitalize()
    if db.matches.find_one({"match_number": match.match_number, "round": normalized_round}):
        raise HTTPException(status_code=400, detail="Match configuration already exists.")
    
    match_data = match.model_dump()
    match_data["round"] = normalized_round
    db.matches.insert_one(match_data)
    return {"message": f"Match {normalized_round}-{match.match_number} compiled."}


@router.get("/api/matches", response_model=List[MatchModel], tags=["Matches"])
def get_match_schedule():
    return list(app.state.db.matches.find({}, {"_id": 0}))


@router.post("/api/matches/bulk-import", status_code=status.HTTP_201_CREATED, tags=["Matches"])
def bulk_import_matches(payload: BulkMatchImportModel):
    db = app.state.db
    if not payload.matches:
        raise HTTPException(status_code=400, detail="The matches transmission payload list cannot be empty.")
        
    documents = []
    for match in payload.matches:
        normalized_round = match.round.capitalize()
        
        # Check for pre-existing records to prevent duplication index collisions
        if db.matches.find_one({"match_number": match.match_number, "round": normalized_round}):
            raise HTTPException(
                status_code=400, 
                detail=f"Match conflict: {normalized_round} #{match.match_number} already exists in database."
            )
            
        match_data = match.model_dump()
        match_data["round"] = normalized_round
        documents.append(match_data)
        
    # Push all entities down to MongoDB in a single high-speed database transaction step
    result = db.matches.insert_many(documents)
    return {"message": f"Successfully imported {len(result.inserted_ids)} matches into the queue collection."}


@router.put("/api/matches/{match_round}/{match_num}/score", tags=["Matches"])
def post_match_score(match_round: str, match_num: int, scores: RECFScoringModel):
    db = app.state.db
    query = {"match_number": match_num, "round": match_round.capitalize()}
    match = db.matches.find_one(query)
    
    # ---------------------------------------------------------
    # MATCH INTEGRITY CHECKER PIPELINE
    # ---------------------------------------------------------
    # 1. Structural Match Existence Check
    if not match:
        raise HTTPException(
            status_code=404, 
            detail=f"Integrity Error: Match {match_round.capitalize()}-{match_num} does not exist in the schedule."
        )

    # 2. Autonomous State Integrity Check
    valid_auto_winners = ["None", "Red", "Blue", "Tie"]
    if scores.autonomous_winner not in valid_auto_winners:
        raise HTTPException(
            status_code=422,
            detail=f"Integrity Error: Invalid autonomous_winner '{scores.autonomous_winner}'. Must be one of {valid_auto_winners}."
        )

    # 3. Autonomous Win Point (AWP) Contradiction Check
    # By RECF rules, an alliance cannot earn an Autonomous Win Point if they lose the autonomous period.
    if scores.autonomous_winner == "Blue" and scores.autonomous_awp_red:
        raise HTTPException(
            status_code=422,
            detail="Integrity Error: Red Alliance cannot claim Autonomous Win Point (AWP) if Blue Alliance won the autonomous bonus."
        )
    if scores.autonomous_winner == "Red" and scores.autonomous_awp_blue:
        raise HTTPException(
            status_code=422,
            detail="Integrity Error: Blue Alliance cannot claim Autonomous Win Point (AWP) if Red Alliance won the autonomous bonus."
        )

    # 4. Total Score Minimum Boundary Check
    if scores.red_score < 0 or scores.blue_score < 0:
        raise HTTPException(
            status_code=422,
            detail="Integrity Error: Alliance scores cannot be negative numbers."
        )

    # 5. Field Capacity Cap Constraint Verification
    MAX_POSSIBLE_SCORE = 150 
    if scores.red_score > MAX_POSSIBLE_SCORE or scores.blue_score > MAX_POSSIBLE_SCORE:
        raise HTTPException(
            status_code=422,
            detail=f"Integrity Error: Submitted score exceeds the absolute physical field limit cap of {MAX_POSSIBLE_SCORE} points."
        )
    # ---------------------------------------------------------

    # If all integrity checks clear, safely commit the data payload to MongoDB
    db.matches.update_one(query, {"$set": {"scored": True, "scores": scores.model_dump()}})
    return {"message": f"Scores verified and finalized for Match {match_round.capitalize()}-{match_num}."}


# ==========================================
# --- SKILLS ENDPOINTS ---
# ==========================================
@router.post("/api/skills", status_code=status.HTTP_201_CREATED, tags=["Skills"])
def log_skills_run(run: SkillsModel):
    db = app.state.db
    # 1. Verify team exists on the roster
    if not db.teams.find_one({"team_number": run.team_number}):
        raise HTTPException(status_code=404, detail="Team not found in roster.")
        
    # 2. Core Security Integrity Gatekeeper Check
    inspection = db.inspections.find_one({"team_number": run.team_number})
    if not inspection or not inspection.get("passed_overall", False):
        raise HTTPException(
            status_code=403, 
            detail=f"Security Violations Gatekeeper: Team {run.team_number} has not passed official field inspection checkups yet and cannot run skills challenges."
        )
        
    db.skills.insert_one(run.model_dump())
    return {"message": "Skills challenge score verified and uploaded safely."}

@router.post("/api/inspections/status", status_code=status.HTTP_200_OK, tags=["Inspections"])
def record_team_inspection(checklist: InspectionChecklistModel):
    db = app.state.db
    # 1. Verify team is registered on the tournament roster first
    if not db.teams.find_one({"team_number": checklist.team_number}):
        raise HTTPException(status_code=404, detail=f"Inspection Error: Team {checklist.team_number} is not registered on this tournament roster.")

    # 2. Automatically compute overall status if both criteria checkouts are met
    updated_data = checklist.model_dump()
    if updated_data["size_inspection_passed"] and updated_data["safety_inspection_passed"]:
        updated_data["passed_overall"] = True
    else:
        updated_data["passed_overall"] = False

    # 3. Save or overwrite the team's inspection status natively inside MongoDB
    db.inspections.update_one(
        {"team_number": checklist.team_number},
        {"$set": updated_data},
        upsert=True
    )
    return {"message": f"Inspection status securely logged for Team {checklist.team_number}.", "passed_overall": updated_data["passed_overall"]}


@router.get("/api/inspections", response_model=List[InspectionChecklistModel], tags=["Inspections"])
def get_all_inspection_statuses():
    db = app.state.db
    return list(db.inspections.find({}, {"_id": 0}))
