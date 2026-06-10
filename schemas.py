from typing import List, Optional
from pydantic import BaseModel, Field, ConfigDict, BeforeValidator
from typing_extensions import Annotated

# Handle incoming MongoDB ObjectIds seamlessly as JSON strings
PyObjectId = Annotated[str, BeforeValidator(str)]

class TeamModel(BaseModel):
    team_number: str = Field(..., description="Unique RECF Team Number (e.g., 12188A)")
    team_name: str = Field(..., description="Registered Organization/Team Name")
    location: Optional[str] = "Unknown"

    model_config = ConfigDict(
        populate_by_name=True,
        json_schema_extra={
            "example": {
                "team_number": "12188A",
                "team_name": "Robo Rogues",
                "location": "Sulphur, Louisiana"
            }
        }
    )

class RECFScoringModel(BaseModel):
    autonomous_winner: str = Field("None", description="Winner of Auto Bonus: Red, Blue, or Tie")
    autonomous_awp_red: bool = Field(False, description="Red Alliance Autonomous Win Point")
    autonomous_awp_blue: bool = Field(False, description="Blue Alliance Autonomous Win Point")
    red_score: int = Field(0, ge=0)
    blue_score: int = Field(0, ge=0)

class MatchModel(BaseModel):
    match_number: int = Field(..., description="Sequential index of the match sequence")
    round: str = Field("Qualification", description="Qualification, Quarterfinals, Semifinals, Finals")
    red_alliance: List[str] = Field(..., max_items=2, description="List of two team numbers")
    blue_alliance: List[str] = Field(..., max_items=2, description="List of two team numbers")
    scored: bool = Field(False, description="Flag indicating if match results are finalized")
    scores: Optional[RECFScoringModel] = None

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "match_number": 1,
                "round": "Qualification",
                "red_alliance": ["12188A", "1111A"],
                "blue_alliance": ["2222B", "3333C"],
                "scored": False
            }
        }
    )

class SkillsModel(BaseModel):
    team_number: str = Field(..., description="Unique RECF Team Number")
    type: str = Field(..., description="Driver or Programming")
    score: int = Field(0, ge=0)

class EliminationMatchModel(BaseModel):
    match_id: str = Field(..., description="Unique elimination identifier (e.g., QF-1-1, SF-2-1, F-1-1)")
    round: str = Field(..., description="Round type: Quarterfinals, Semifinals, Finals")
    match_number: int = Field(..., description="The sequence number within that specific round")
    instance_number: int = Field(..., description="For best-of-3 series: 1, 2, or 3")
    red_alliance: List[str] = Field(..., max_items=2, description="Red team numbers")
    blue_alliance: List[str] = Field(..., max_items=2, description="Blue team numbers")
    scored: bool = Field(False, description="Flag indicating if elimination match is completed")
    scores: Optional[RECFScoringModel] = None

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "match_id": "QF-1-1",
                "round": "Quarterfinals",
                "match_number": 1,
                "instance_number": 1,
                "red_alliance": ["12188A", "1111A"],
                "blue_alliance": ["2222B", "3333C"],
                "scored": False
            }
        }
    )
class BulkMatchImportModel(BaseModel):
    matches: List[MatchModel] = Field(..., description="An array containing individual match layout objects")

class AllianceSeedPair(BaseModel):
    seed_number: int = Field(..., ge=1, le=8, description="Alliance seeding position (1 through 8)")
    team_one: str = Field(..., description="The captain team number")
    team_two: str = Field(..., description="The selected alliance partner team number")

class AllianceSelectionModel(BaseModel):
    alliances: List[AllianceSeedPair] = Field(..., max_items=8, description="Array of up to 8 finalized elimination alliance pairings")
class InspectionChecklistModel(BaseModel):
    team_number: str = Field(..., description="Target team identifier")
    size_inspection_passed: bool = Field(False, description="True if team satisfies 18x18x18 inch robot limit")
    safety_inspection_passed: bool = Field(False, description="True if team satisfies voltage and mechanical structural safety requirements")
    passed_overall: bool = Field(False, description="True if team is officially cleared to play in matches")

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "team_number": "12188A",
                "size_inspection_passed": True,
                "safety_inspection_passed": True,
                "passed_overall": True
            }
        }
    )
