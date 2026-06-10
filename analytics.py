from fastapi import APIRouter, HTTPException, status
from typing import List
from schemas import EliminationMatchModel, RECFScoringModel, AllianceSelectionModel

router = APIRouter()

# Safely reference the initialized application context from the main entrypoint
from main import app


# ==========================================
# --- TEAM STATISTICS ENDPOINT ---
# ==========================================
@router.get("/api/teams/{team_number}/stats", tags=["Teams"])
def get_team_statistics(team_number: str):
    db = app.state.db
    if not db.teams.find_one({"team_number": team_number}):
        raise HTTPException(status_code=404, detail="Team profile not found in roster.")

    pipeline = [
        {
            "$match": {
                "scored": True,
                "round": "Qualification",
                "$or": [
                    {"red_alliance": team_number},
                    {"blue_alliance": team_number}
                ]
            }
        },
        {
            "$project": {
                "team_score": {
                    "$cond": [
                        {"$in": [team_number, "$red_alliance"]},
                        "$scores.red_score",
                        "$scores.blue_score"
                    ]
                }
            }
        },
        {
            "$group": {
                "_id": None,
                "matches_played": {"$sum": 1},
                "average_score": {"$avg": "$team_score"},
                "highest_score": {"$max": "$team_score"}
            }
        }
    ]

    stats_result = list(db.matches.aggregate(pipeline))
    if not stats_result:
        return {
            "team_number": team_number,
            "matches_played": 0,
            "average_score": 0.0,
            "highest_score": 0
        }
        
    stats = stats_result[0]
    return {
        "team_number": team_number,
        "matches_played": stats["matches_played"],
        "average_score": round(stats["average_score"], 2),
        "highest_score": stats["highest_score"]
    }


# ==========================================
# --- SKILLS LEADERBOARD ENDPOINT ---
# ==========================================
@router.get("/api/skills/leaderboard", tags=["Skills"])
def get_skills_leaderboard():
    pipeline = [
        {
            "$group": {
                "_id": {"team_number": "$team_number", "type": "$type"},
                "max_score": {"$max": "$score"}
            }
        },
        {
            "$group": {
                "_id": "$_id.team_number",
                "programming_score": {
                    "$max": {
                        "$cond": [{"$eq": ["$_id.type", "Programming"]}, "$max_score", 0]
                    }
                },
                "driver_score": {
                    "$max": {
                        "$cond": [{"$eq": ["$_id.type", "Driver"]}, "$max_score", 0]
                    }
                }
            }
        },
        {
            "$project": {
                "team_number": "$_id",
                "_id": 0,
                "programming_score": 1,
                "driver_score": 1,
                "total_score": {"$add": ["$programming_score", "$driver_score"]}
            }
        },
        {
            "$sort": {
                "total_score": -1,
                "programming_score": -1
            }
        }
    ]
    return list(app.state.db.skills.aggregate(pipeline))


# ==========================================
# --- ELIMINATION BRACKET ENDPOINTS ---
# ==========================================
@router.post("/api/eliminations/alliance-selection", status_code=status.HTTP_201_CREATED, tags=["Eliminations"])
def finalize_alliance_selection(payload: AllianceSelectionModel):
    db = app.state.db
    if not payload.alliances:
        raise HTTPException(status_code=400, detail="Alliance choices cannot be empty.")
        
    seed_map = {a.seed_number: a for a in payload.alliances}
    bracket_pairings = [
        {"match_num": 1, "red_seed": 1, "blue_seed": 8},
        {"match_num": 2, "red_seed": 4, "blue_seed": 5},
        {"match_num": 3, "red_seed": 2, "blue_seed": 7},
        {"match_num": 4, "red_seed": 3, "blue_seed": 6}
    ]
    
    elim_documents = []
    for pairing in bracket_pairings:
        m_num = pairing["match_num"]
        r_seed = pairing["red_seed"]
        b_seed = pairing["blue_seed"]
        
        red_team_1 = seed_map[r_seed].team_one if r_seed in seed_map else f"Seed {r_seed} Captain"
        red_team_2 = seed_map[r_seed].team_two if r_seed in seed_map else f"Seed {r_seed} Partner"
        blue_team_1 = seed_map[b_seed].team_one if b_seed in seed_map else f"Seed {b_seed} Captain"
        blue_team_2 = seed_map[b_seed].team_two if b_seed in seed_map else f"Seed {b_seed} Partner"
        
        for instance in range(1, 4):
            match_id = f"QF-{m_num}-{instance}"
            db.eliminations.delete_one({"match_id": match_id})
            
            elim_documents.append({
                "match_id": match_id,
                "round": "Quarterfinals",
                "match_number": m_num,
                "instance_number": instance,
                "red_alliance": [red_team_1, red_team_2],
                "blue_alliance": [blue_team_1, blue_team_2],
                "scored": False,
                "scores": None
            })
            
    db.eliminations.insert_many(elim_documents)
    return {"message": "Alliance selection completed. Best-of-3 Quarterfinal matches initialized successfully."}
@router.post("/api/eliminations", status_code=status.HTTP_201_CREATED, tags=["Eliminations"])
def create_elimination_match(match: EliminationMatchModel):
    db = app.state.db
    match_id = f"{match.round[:2].upper()}-{match.match_number}-{match.instance_number}"
    if db.eliminations.find_one({"match_id": match_id}):
        raise HTTPException(status_code=400, detail=f"Elimination slot {match_id} already exists.")
    
    elim_data = match.model_dump()
    elim_data["round"] = match.round.capitalize()
    elim_data["match_id"] = match_id
    db.eliminations.insert_one(elim_data)
    return {"message": f"Elimination Match {match_id} scheduled."}


@router.put("/api/eliminations/{match_id}/score", tags=["Eliminations"])
def score_elimination_match(match_id: str, scores: RECFScoringModel):
    db = app.state.db
    target_id = match_id.upper()
    match = db.eliminations.find_one({"match_id": target_id})
    
    # --- ELIMINATION INTEGRITY CHECKER ---
    if not match:
        raise HTTPException(status_code=404, detail=f"Integrity Error: Elimination match {target_id} not found.")

    if scores.autonomous_winner not in ["None", "Red", "Blue", "Tie"]:
        raise HTTPException(status_code=422, detail="Integrity Error: Invalid autonomous state winner declared.")

    if scores.red_score == scores.blue_score:
        raise HTTPException(
            status_code=422,
            detail="Integrity Error: Elimination matches cannot end in a tie score. Another instance match must be run."
        )

    db.eliminations.update_one(
        {"match_id": target_id}, 
        {"$set": {"scored": True, "scores": scores.model_dump()}}
    )
    return {"message": f"Elimination Match {target_id} results verified and finalized."}


@router.get("/api/eliminations", response_model=List[EliminationMatchModel], tags=["Eliminations"])
def get_elimination_bracket():
    return list(app.state.db.eliminations.find({}, {"_id": 0}))


# --- BRACKET ADVANCEMENT GENERATOR ---
@router.post("/api/eliminations/advance-round", status_code=status.HTTP_200_OK, tags=["Eliminations"])
def advance_elimination_round():
    db = app.state.db
    all_elim_matches = list(db.eliminations.find({}))
    
    def determine_series_winner(round_name, match_number):
        series_matches = [m for m in all_elim_matches if m["round"] == round_name and m["match_number"] == match_number]
        red_wins, blue_wins = 0, 0
        red_alliance_teams, blue_alliance_teams = [], []
        
        for m in series_matches:
            if not m["scored"] or not m["scores"]:
                continue
            red_alliance_teams = m["red_alliance"]
            blue_alliance_teams = m["blue_alliance"]
            if m["scores"]["red_score"] > m["scores"]["blue_score"]:
                red_wins += 1
            elif m["scores"]["blue_score"] > m["scores"]["red_score"]:
                blue_wins += 1
                
        if red_wins >= 2:
            return red_alliance_teams
        elif blue_wins >= 2:
            return blue_alliance_teams
        return None

    qf1_winner = determine_series_winner("Quarterfinals", 1)
    qf2_winner = determine_series_winner("Quarterfinals", 2)
    qf3_winner = determine_series_winner("Quarterfinals", 3)
    qf4_winner = determine_series_winner("Quarterfinals", 4)
    
    sf_documents = []
    if qf1_winner or qf2_winner:
        red_sf1 = qf1_winner if qf1_winner else ["TBD (QF1 Winner)", "TBD"]
        blue_sf1 = qf2_winner if qf2_winner else ["TBD (QF2 Winner)", "TBD"]
        for instance in range(1, 4):
            match_id = f"SF-1-{instance}"
            db.eliminations.delete_one({"match_id": match_id})
            sf_documents.append({
                "match_id": match_id, "round": "Semifinals", "match_number": 1, "instance_number": instance,
                "red_alliance": red_sf1, "blue_alliance": blue_sf1, "scored": False, "scores": None
            })
            
    if qf3_winner or qf4_winner:
        red_sf2 = qf3_winner if qf3_winner else ["TBD (QF3 Winner)", "TBD"]
        blue_sf2 = qf4_winner if qf4_winner else ["TBD (QF4 Winner)", "TBD"]
        for instance in range(1, 4):
            match_id = f"SF-2-{instance}"
            db.eliminations.delete_one({"match_id": match_id})
            sf_documents.append({
                "match_id": match_id, "round": "Semifinals", "match_number": 2, "instance_number": instance,
                "red_alliance": red_sf2, "blue_alliance": blue_sf2, "scored": False, "scores": None
            })
            
    if sf_documents:
        db.eliminations.insert_many(sf_documents)
        
    all_elim_matches = list(db.eliminations.find({}))
    sf1_winner = determine_series_winner("Semifinals", 1)
    sf2_winner = determine_series_winner("Semifinals", 2)
    
    f_documents = []
    if sf1_winner or sf2_winner:
        red_f = sf1_winner if sf1_winner else ["TBD (SF1 Winner)", "TBD"]
        blue_f = sf2_winner if sf2_winner else ["TBD (SF2 Winner)", "TBD"]
        for instance in range(1, 4):
            match_id = f"F-1-{instance}"
            db.eliminations.delete_one({"match_id": match_id})
            f_documents.append({
                "match_id": match_id, "round": "Finals", "match_number": 1, "instance_number": instance,
                "red_alliance": red_f, "blue_alliance": blue_f, "scored": False, "scores": None
            })
            
    if f_documents:
        db.eliminations.insert_many(f_documents)
        
    return {
        "status": "Success",
        "message": "Elimination brackets evaluated. Winners promoted to upcoming rounds.",
        "quarterfinal_status": {"QF1_winner": qf1_winner, "QF2_winner": qf2_winner, "QF3_winner": qf3_winner, "QF4_winner": qf4_winner},
        "semifinal_status": {"SF1_winner": sf1_winner, "SF2_winner": sf2_winner}
    }


# --- RECF QUALIFICATION RANKINGS ---
@router.get("/api/rankings", tags=["Rankings"])
def calculate_RECF_rankings():
    db = app.state.db
    teams = list(db.teams.find({}, {"_id": 0}))
    rankings = {t["team_number"]: {"team_number": t["team_number"], "wp": 0, "ap": 0, "sp": 0, "record": {"w": 0, "l": 0, "t": 0}} for t in teams}
    
    for m in db.matches.find({"scored": True}):
        s = m["scores"]
        r_teams, b_teams = m["red_alliance"], m["blue_alliance"]
        r_score, b_score = s["red_score"], s["blue_score"]

        r_wp, b_wp, match_sp = (2, 0, b_score) if r_score > b_score else ((0, 2, r_score) if b_score > r_score else (1, 1, r_score))
        r_ap, b_ap = (8, 0) if s["autonomous_winner"] == "Red" else ((0, 8) if s["autonomous_winner"] == "Blue" else (4, 4))
        r_wp += 2 if s["autonomous_winner"] == "Red" else (2 if s["autonomous_winner"] == "Blue" else 1)
        b_wp += 2 if s["autonomous_winner"] == "Blue" else (2 if s["autonomous_winner"] == "Red" else 1)

        if s.get("autonomous_awp_red"): r_wp += 1
        if s.get("autonomous_awp_blue"): b_wp += 1

        for r_team in r_teams:
            if r_team in rankings:
                rankings[r_team]["wp"] += r_wp; rankings[r_team]["ap"] += r_ap; rankings[r_team]["sp"] += match_sp
                rankings[r_team]["record"]["w" if r_score > b_score else ("l" if b_score > r_score else "t")] += 1

        for b_team in b_teams:
            if b_team in rankings:
                rankings[b_team]["wp"] += b_wp; rankings[b_team]["ap"] += b_ap; rankings[b_team]["sp"] += match_sp
                rankings[b_team]["record"]["w" if b_score > r_score else ("l" if r_score > b_score else "t")] += 1

    return sorted(rankings.values(), key=lambda x: (x["wp"], x["ap"], x["sp"]), reverse=True)
