from __future__ import annotations

import io
import math
import time
from datetime import datetime, timedelta
from typing import List, Tuple, Dict

import boto3
import pandas as pd
from fastapi import HTTPException

from .config import get_settings
from .models import OptimizeRequest, OptimizeResponse, TruckSummary, LineAssignment, WeightConfig
from .utils import canonical_rename, normalize
from .constants import REQUIRED_COLUMNS


def _load_excel_from_s3(s3_key: str, sheet_name: str | None) -> pd.DataFrame:
    settings = get_settings()
    if not settings.aws_s3_bucket_uploads:
        raise HTTPException(
            status_code=503, detail="AWS_S3_BUCKET_UPLOADS not configured")
    s3 = boto3.client("s3", region_name=settings.aws_region)
    try:
        obj = s3.get_object(Bucket=settings.aws_s3_bucket_uploads, Key=s3_key)
        data = obj["Body"].read()
        excel = pd.ExcelFile(io.BytesIO(data))
        df = excel.parse(sheet_name) if sheet_name else excel.parse(
            excel.sheet_names[0])
        return df
    except Exception as e:
        raise HTTPException(
            status_code=400, detail=f"Failed to read Excel from S3: {e}")


def _ensure_required_columns(df: pd.DataFrame):
    missing = [c for c in REQUIRED_COLUMNS if c not in df.columns]
    if missing:
        raise HTTPException(
            status_code=400, detail=f"Missing required columns: {missing}")


def _parse_dates(df: pd.DataFrame):
    for col in ["Earliest Due", "Latest Due"]:
        if col in df.columns:
            df[col] = pd.to_datetime(df[col], errors="coerce")


def _assign_priority_buckets(df: pd.DataFrame, today: datetime) -> pd.DataFrame:
    # Buckets: Late, NearDue (<=3 days out), WithinWindow, NotDue
    def bucket(row):
        latest = row.get("Latest Due")
        if pd.isna(latest):
            return "NotDue"
        if latest < today:
            return "Late"
        if latest <= today + timedelta(days=3):
            return "NearDue"
        return "WithinWindow"

    df["priorityBucket"] = df.apply(bucket, axis=1)
    df["priorityRank"] = df["priorityBucket"].map(
        {"Late": 0, "NearDue": 1, "WithinWindow": 2, "NotDue": 3})
    return df


def _is_shippable(row, ship_date: datetime):
    ed = row.get("Earliest Due")
    ld = row.get("Latest Due")
    # If dates missing, treat as NotDue (not shippable for cross-bucket into Late)
    if pd.isna(ed) or pd.isna(ld):
        return False
    return ed <= ship_date <= ld


def _weight_limits_for_state(state: str, cfg: WeightConfig) -> Tuple[int, int]:
    if (state or "").strip().upper() == "TX":
        return cfg.texas_min, cfg.texas_max
    return cfg.other_min, cfg.other_max


def _calc_weight_per_piece(row) -> float:
    rw = float(row.get("Ready Weight", 0) or 0)
    rpcs = int(row.get("RPcs", 0) or 0)
    if rpcs <= 0:
        return 0.0
    return rw / rpcs


def _sort_for_packing(group_df: pd.DataFrame) -> pd.DataFrame:
    # Prefer overwidth together and heavier items first
    df = group_df.copy()
    if "Width" not in df.columns:
        df["Width"] = 0
    df["isOverwidth"] = df["Width"].astype(float) > 96
    df["Weight Per Piece Calc"] = df.apply(_calc_weight_per_piece, axis=1)
    # Sort by: priorityRank, overwidth desc, weight per piece desc, Ready Weight desc
    df = df.sort_values(by=["priorityRank", "isOverwidth", "Weight Per Piece Calc",
                        "Ready Weight"], ascending=[True, False, False, False])
    return df


def _pack_trucks_for_group(group_df: pd.DataFrame, cfg: WeightConfig, allow_multi_stop: bool, ship_date: datetime) -> Tuple[List[TruckSummary], List[LineAssignment], List[int]]:
    # With allow_multi_stop False, only same customer on truck.
    # Cross-bucket fill allowed within exact destination (zone, route, customer, city, state) and shippable rule.
    trucks: List[TruckSummary] = []
    assignments: List[LineAssignment] = []
    section_numbers: Dict[str, List[int]] = {
        "Late": [], "NearDue": [], "WithinWindow": [], "NotDue": []}

    df = _sort_for_packing(group_df)
    if df.empty:
        return trucks, assignments, []

    # Determine state limits from any row (same destination/customer assumed in group)
    state = str(df.iloc[0]["shipping_state"]).strip().upper()
    min_w, max_w = _weight_limits_for_state(state, cfg)
    target = int(max_w * cfg.load_target_pct)

    # Prepare list of rows with piece-level info
    rows = []
    for _, r in df.iterrows():
        wpp = _calc_weight_per_piece(r)
        rows.append({
            "row": r,
            "wpp": wpp,
            "remaining_pieces": int(r.get("RPcs", 0) or 0),
        })

    truck_no_offset = 0
    next_truck_number = 1

    while True:
        # Stop if nothing left
        if all(it["remaining_pieces"] <= 0 for it in rows):
            break

        current_weight = 0.0
        current_pieces = 0
        current_lines = []  # list of assignment dicts
        contains_late = False
        max_width = 0.0
        orders_set = set()

        # First pass: take Late items first
        for prio in ["Late", "NearDue", "WithinWindow", "NotDue"]:
            for it in rows:
                if it["remaining_pieces"] <= 0:
                    continue
                r = it["row"]
                if r["priorityBucket"] != prio:
                    continue
                # Cross-bucket constraint for Late: only pull shippable orders
                if prio != "Late" and contains_late:
                    if not _is_shippable(r, ship_date):
                        continue
                # Determine how many pieces we can take
                wpp = float(it["wpp"]) or 0.0
                if wpp <= 0:
                    continue
                remaining_capacity = max_w - current_weight
                max_pieces_fit = int(remaining_capacity // wpp)
                if max_pieces_fit <= 0 and current_weight == 0:
                    # If even one piece doesn't fit in an empty truck, cap by target but still allow one piece
                    max_pieces_fit = 1
                take = min(it["remaining_pieces"], max_pieces_fit)
                if take <= 0:
                    continue
                # Assign pieces
                take_weight = take * wpp
                current_weight += take_weight
                current_pieces += take
                it["remaining_pieces"] -= take
                is_partial = take < int(r.get("RPcs", 0) or 0)
                is_remainder = is_partial or it["remaining_pieces"] > 0
                width_val = float(r.get("Width", 0) or 0)
                max_width = max(max_width, width_val)
                contains_late = contains_late or (
                    r["priorityBucket"] == "Late")
                orders_set.add((str(r.get("SO")),))

                current_lines.append({
                    "so": str(r.get("SO")),
                    "line": str(r.get("Line")),
                    "customer": str(r.get("Customer")),
                    "city": str(r.get("shipping_city")),
                    "state": str(r.get("shipping_state")),
                    "pieces": take,
                    "total_ready_pieces": int(r.get("RPcs", 0) or 0),
                    "wpp": wpp,
                    "tw": take_weight,
                    "width": width_val,
                    "is_overwidth": width_val > 96,
                    "is_late": r["priorityBucket"] == "Late",
                    "earliest": r.get("Earliest Due"),
                    "latest": r.get("Latest Due"),
                    "is_partial": is_partial,
                    "is_remainder": is_remainder,
                    "parent_line": str(r.get("Line")) if is_remainder else None,
                    "remaining_pieces": it["remaining_pieces"],
                })

                # Stop if we reached target (but don’t exceed max)
                if current_weight >= target:
                    break
            if current_weight >= target:
                break

        # If nothing was assigned (e.g., wpp too large), break to avoid infinite loop
        if not current_lines:
            break

        # Create truck summary
        first = current_lines[0]
        state = first["state"].upper()
        min_w, max_w = _weight_limits_for_state(state, cfg)
        truck_summary = TruckSummary(
            truckNumber=next_truck_number,
            customerName=first["customer"],
            customerCity=first["city"],
            customerState=state,
            zone=str(group_df.iloc[0].get("Zone")
                     ) if "Zone" in group_df.columns else None,
            route=str(group_df.iloc[0].get("Route")
                      ) if "Route" in group_df.columns else None,
            totalWeight=current_weight,
            minWeight=min_w,
            maxWeight=max_w,
            totalOrders=len({c[0] for c in orders_set}),
            totalLines=len(current_lines),
            totalPieces=current_pieces,
            maxWidth=max_width,
            percentOverwidth=(sum(
                1 for cl in current_lines if cl["is_overwidth"]) / max(1, len(current_lines))) * 100.0,
            containsLate=contains_late,
            priorityBucket="Late" if contains_late else min([group_df.iloc[0]["priorityBucket"]] + [
                                                            "NearDue", "WithinWindow", "NotDue"], key=lambda x: {"Late": 0, "NearDue": 1, "WithinWindow": 2, "NotDue": 3}.get(x, 3)),
        )
        trucks.append(truck_summary)

        for cl in current_lines:
            assignments.append(LineAssignment(
                truckNumber=truck_summary.truckNumber,
                so=cl["so"],
                line=cl["line"],
                customerName=cl["customer"],
                customerCity=cl["city"],
                customerState=cl["state"],
                piecesOnTransport=int(cl["pieces"]),
                totalReadyPieces=int(cl["total_ready_pieces"]),
                weightPerPiece=float(cl["wpp"]),
                totalWeight=float(cl["tw"]),
                width=float(cl["width"]),
                isOverwidth=bool(cl["is_overwidth"]),
                isLate=bool(cl["is_late"]),
                earliestDue=cl["earliest"].date().isoformat(
                ) if pd.notna(cl["earliest"]) else None,
                latestDue=cl["latest"].date().isoformat(
                ) if pd.notna(cl["latest"]) else None,
                isPartial=bool(cl["is_partial"]),
                isRemainder=bool(cl["is_remainder"]),
                parentLine=cl["parent_line"],
                remainingPieces=int(
                    cl["remaining_pieces"]) if cl["remaining_pieces"] is not None else None,
            ))

        # Record section index by priority
        section_numbers[truck_summary.priorityBucket].append(
            truck_summary.truckNumber)

        next_truck_number += 1

    # Return section listing in consistent order
    ordered_sections = [
        *section_numbers.get("Late", []),
        *section_numbers.get("NearDue", []),
        *section_numbers.get("WithinWindow", []),
        *section_numbers.get("NotDue", []),
    ]

    return trucks, assignments, ordered_sections


def optimize(req: OptimizeRequest) -> OptimizeResponse:
    start = time.time()
    df = _load_excel_from_s3(req.s3_key, req.sheet_name)
    df = canonical_rename(df)
    _ensure_required_columns(df)
    _parse_dates(df)

    # Filter Planning Whse (case-insensitive)
    whse_col = "Planning Whse"
    if whse_col not in df.columns:
        raise HTTPException(
            status_code=400, detail="Planning Whse column is required")
    df_filtered = df[df[whse_col].astype(str).str.lower() == str(
        req.planning_whse).strip().lower()].copy()

    # Apply defaults
    weight_cfg = req.weight_config or WeightConfig(
        texas_max=52000,
        texas_min=47000,
        other_max=48000,
        other_min=44000,
        load_target_pct=0.98,
    )

    # Assign priorities
    today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    # per clarification: pairing for shipments going out tomorrow
    ship_date = today + timedelta(days=1)
    df_b = _assign_priority_buckets(df_filtered, today)

    # Sorting per PRD primary order
    sort_cols = ["priorityRank"]
    if "Zone" in df_b.columns:
        sort_cols.append("Zone")
    if "Route" in df_b.columns:
        sort_cols.append("Route")
    sort_cols += ["Customer", "shipping_state", "shipping_city"]
    df_b = df_b.sort_values(by=sort_cols, kind="mergesort")

    # Grouping by zone/route/customer/destination
    group_keys = []
    if "Zone" in df_b.columns:
        group_keys.append("Zone")
    if "Route" in df_b.columns:
        group_keys.append("Route")
    group_keys += ["Customer", "shipping_state", "shipping_city"]

    all_trucks: List[TruckSummary] = []
    all_assignments: List[LineAssignment] = []
    sections_map: Dict[str, List[int]] = {
        "Late": [], "NearDue": [], "WithinWindow": [], "NotDue": []}

    truck_counter = 1
    for _, gdf in df_b.groupby(group_keys, dropna=False):
        trucks, assigns, ordered_sections = _pack_trucks_for_group(
            gdf, weight_cfg, req.allow_multi_stop, ship_date)
        # Map old -> new numbers
        num_map: Dict[int, int] = {}
        for t in trucks:
            old = t.truckNumber
            new = truck_counter
            num_map[old] = new
            t.truckNumber = new
            all_trucks.append(t)
            sections_map[t.priorityBucket].append(new)
            truck_counter += 1
        # Update assignments with new truck numbers
        for a in assigns:
            if a.truckNumber in num_map:
                a.truckNumber = num_map[a.truckNumber]
            all_assignments.append(a)

    metrics = {
        "rows": int(len(df_filtered)),
        "duration_ms": int((time.time() - start) * 1000),
    }

    return OptimizeResponse(
        trucks=all_trucks,
        assignments=all_assignments,
        sections={k: v for k, v in sections_map.items()},
        metrics=metrics,
    )
