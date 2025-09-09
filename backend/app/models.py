from __future__ import annotations

from typing import List, Optional
from pydantic import BaseModel, Field


class WeightConfig(BaseModel):
    texas_max: int = Field(52000, ge=40000, le=100000)
    texas_min: int = Field(47000, ge=40000, le=100000)
    other_max: int = Field(48000, ge=40000, le=100000)
    other_min: int = Field(44000, ge=40000, le=100000)
    load_target_pct: float = Field(0.98, ge=0.8, le=1.0)


class OptimizeRequest(BaseModel):
    s3_key: str
    planning_whse: str = "ZAC"
    weight_config: Optional[WeightConfig] = None
    allow_multi_stop: bool = False  # per answer: initially off
    sheet_name: Optional[str] = None


class TruckSummary(BaseModel):
    truckNumber: int
    customerName: str
    customerCity: str
    customerState: str
    zone: Optional[str] = None
    route: Optional[str] = None
    totalWeight: float
    minWeight: int
    maxWeight: int
    totalOrders: int
    totalLines: int
    totalPieces: int
    maxWidth: float
    percentOverwidth: float
    containsLate: bool
    priorityBucket: str


class LineAssignment(BaseModel):
    truckNumber: int
    so: str
    line: str
    customerName: str
    customerCity: str
    customerState: str
    piecesOnTransport: int
    totalReadyPieces: int
    weightPerPiece: float
    totalWeight: float
    width: float
    isOverwidth: bool
    isLate: bool
    earliestDue: Optional[str] = None
    latestDue: Optional[str] = None
    isPartial: bool
    isRemainder: bool
    parentLine: Optional[str] = None
    remainingPieces: Optional[int] = None


class OptimizeResponse(BaseModel):
    trucks: List[TruckSummary]
    assignments: List[LineAssignment]
    sections: dict
    metrics: dict
