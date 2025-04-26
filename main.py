from fastapi import FastAPI, HTTPException, Response
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any
import logging
import math

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(
    title="Posture & Desk Setup Assistant API",
    description="Provides posture analysis feedback based on calculated metrics/issues.",
    version="1.3.0" # Version updated
)

# --- Constants for Scoring & Analysis ---
# Consistent thresholds used for scoring and assessment generation
THRESHOLDS = {
    'shoulder_angle_warning': 5.0,
    'shoulder_angle_significant': 10.0,
    'head_forward_ratio_warning': 0.1,
    'head_forward_ratio_significant': 0.15,
    'torso_angle_warning': 15.0, # Deviation from vertical
    'torso_angle_significant': 20.0, # Deviation from vertical
    'spine_offset_ratio_warning': 0.15,
    'spine_offset_ratio_significant': 0.20
}

# Consistent penalties for scoring
PENALTIES = {
    'significant': 22,
    'warning': 14,
    'missing_data_low': 5,
    'visibility_issue': 6
}
# --- End Constants ---


# CORS Configuration
origins = [
    "null", "http://localhost", "http://localhost:8080", "http://127.0.0.1",
    "http://127.0.0.1:8080", "http://127.0.0.1:5500", "http://127.0.0.1:5501",
]
logger.info(f"Allowed CORS origins: {origins}")

app.add_middleware(
    CORSMiddleware, allow_origins=origins, allow_credentials=True,
    allow_methods=["*"], allow_headers=["*"]
)

# --- Pydantic Models ---
class PostureMetricsInput(BaseModel):
    metrics: Optional[Dict[str, Any]] = Field(default_factory=dict, description="Raw metrics from client (angles, ratios).")
    issues: Optional[List[str]] = Field(default_factory=list, description="Client-reported issues (mostly visibility).")

class PostureFeedback(BaseModel):
    score: Optional[int] = Field(None, description="Backend calculated score (0-100).")
    assessment: Optional[str] = Field(None, description="Textual analysis summary.")
    recommendations: List[str] = Field(default_factory=list, description="Improvement tips.")
    maintenance_tips: List[str] = Field(default_factory=list, description="General posture habits.")
    benefits: Optional[str] = Field(None, description="Benefits of good posture.")

class DeskSetupTips(BaseModel):
    tips: List[str] = Field(default_factory=list)

# --- Helper: Score Calculation (Now used by endpoint) ---
def calculate_overall_score(metrics: Dict[str, Any], issues: List[str]) -> Optional[int]:
    """Calculates posture score based on metrics and visibility issues."""
    if not metrics and (not issues or all("visibility" in i.lower() or "waiting" in i.lower() for i in issues)):
        logger.info("Cannot calculate score: Insufficient data.")
        return None

    score = 100
    has_visibility_issue = any("visibility" in i.lower() for i in issues)
    metrics = metrics or {} # Ensure metrics is a dict

    # Shoulder Angle
    shoulder_angle = metrics.get('shoulderAngle')
    if shoulder_angle is not None:
        abs_angle = abs(shoulder_angle)
        if abs_angle > THRESHOLDS['shoulder_angle_significant']: score -= PENALTIES['significant']
        elif abs_angle > THRESHOLDS['shoulder_angle_warning']: score -= PENALTIES['warning']
    elif not has_visibility_issue: score -= PENALTIES['missing_data_low'] # Penalize if missing w/o visibility issue

    # Torso Angle (Slouch/Lean Fwd/Back)
    torso_angle = metrics.get('torsoAngleFromVertical')
    if torso_angle is not None:
        abs_angle = abs(torso_angle) # Deviation from vertical
        if abs_angle > THRESHOLDS['torso_angle_significant']: score -= PENALTIES['significant']
        elif abs_angle > THRESHOLDS['torso_angle_warning']: score -= PENALTIES['warning']
    elif not has_visibility_issue: score -= PENALTIES['missing_data_low']

    # Spine Horizontal Offset (Sideways Lean)
    spine_offset = metrics.get('spineHorizontalOffsetRatio')
    if spine_offset is not None:
        if spine_offset > THRESHOLDS['spine_offset_ratio_significant']: score -= PENALTIES['significant']
        elif spine_offset > THRESHOLDS['spine_offset_ratio_warning']: score -= PENALTIES['warning']
    elif not has_visibility_issue: score -= PENALTIES['missing_data_low']

    # Head Forward Ratio
    head_forward = metrics.get('headForwardRatio')
    if head_forward is not None:
        # Note: head_forward > 0 means head is forward (left on mirrored screen)
        if head_forward > THRESHOLDS['head_forward_ratio_significant']: score -= PENALTIES['significant']
        elif head_forward > THRESHOLDS['head_forward_ratio_warning']: score -= PENALTIES['warning']
    elif not has_visibility_issue: score -= PENALTIES['missing_data_low']

    # Visibility Penalty
    if has_visibility_issue: score -= PENALTIES['visibility_issue']

    final_score = max(0, min(100, round(score)))
    logger.info(f"Calculated score: {final_score}")
    return final_score


# --- API Endpoints ---

@app.get('/favicon.ico', include_in_schema=False)
async def favicon(): return Response(status_code=204)

@app.post("/analyze_posture", response_model=PostureFeedback)
async def analyze_posture_endpoint(data: PostureMetricsInput):
    """Analyzes posture metrics, calculates score, generates feedback."""
    logger.info(f"Received POST /analyze_posture: Metrics={data.metrics}, Issues={data.issues}")
    try:
        metrics = data.metrics if isinstance(data.metrics, dict) else {}
        frontend_issues = data.issues if isinstance(data.issues, list) else []

        assessment_parts = []
        recommendations = []
        maintenance_tips = [
            "Take brief breaks every 30 mins to stretch/move.",
            "Ensure feet flat, knees ~90°, back supported.",
            "Keep elbows near 90° while typing, close to body.",
            "Monitor top roughly at eye level, arm's length away.",
            "Use lumbar support for spine's natural curve."
        ]
        benefits = "Good posture reduces pain (back, neck, shoulders), improves breathing & focus, and prevents long-term spinal issues."

        # --- Generate Assessment & Recommendations based SOLELY on backend metrics/thresholds ---
        try:
            # Shoulder Balance
            shoulder_angle = metrics.get('shoulderAngle')
            if shoulder_angle is not None:
                abs_angle = abs(shoulder_angle)
                if abs_angle > THRESHOLDS['shoulder_angle_significant']:
                    assessment_parts.append("Shoulders significantly uneven.")
                    recommendations.extend(["Sit evenly, relax shoulders.", "Check armrest height/usage."])
                elif abs_angle > THRESHOLDS['shoulder_angle_warning']:
                    assessment_parts.append("Shoulders slightly uneven.")
                    recommendations.append("Be mindful of keeping shoulders level.")

            # Torso Lean (Sideways)
            spine_offset = metrics.get('spineHorizontalOffsetRatio')
            if spine_offset is not None:
                 if spine_offset > THRESHOLDS['spine_offset_ratio_significant']:
                    assessment_parts.append("Significant sideways lean.")
                    recommendations.extend(["Engage core, sit centered.", "Avoid leaning heavily on one armrest."])
                 elif spine_offset > THRESHOLDS['spine_offset_ratio_warning']:
                    assessment_parts.append("Slight sideways lean.")
                    recommendations.append("Check if leaning towards monitor or on armrest.")

            # Torso Slouch / Lean Fwd/Back (Vertical Angle)
            torso_angle = metrics.get('torsoAngleFromVertical')
            if torso_angle is not None:
                 abs_angle = abs(torso_angle) # Deviation from vertical
                 if abs_angle > THRESHOLDS['torso_angle_significant']:
                    assessment_parts.append("Significant slouch or backward lean.")
                    recommendations.extend(["Sit tall, chest up.", "Use lumbar support actively.", "Stretch chest/back during breaks."])
                 elif abs_angle > THRESHOLDS['torso_angle_warning']:
                    assessment_parts.append("Slight slouch or backward lean.")
                    recommendations.append("Gently pull shoulder blades back/down. Imagine head pulled up.")

            # Forward Head
            head_forward = metrics.get('headForwardRatio')
            if head_forward is not None:
                if head_forward > THRESHOLDS['head_forward_ratio_significant']:
                    assessment_parts.append("Significant forward head posture.")
                    recommendations.extend(["Gently tuck chin (ears over shoulders).", "Ensure monitor at eye level & arm's length."])
                elif head_forward > THRESHOLDS['head_forward_ratio_warning']:
                    assessment_parts.append("Slight forward head posture.")
                    recommendations.append("Perform chin tucks periodically. Check monitor distance.")

        except Exception as metric_error:
            logger.error(f"Metric processing error: {metric_error}", exc_info=True)
            assessment_parts.append("Error during metric analysis.")

        # --- Calculate Score ---
        final_score = calculate_overall_score(metrics, frontend_issues)

        # --- Compile Final Assessment String ---
        has_specific_posture_issue = bool(assessment_parts)
        has_visibility_issue = any("visibility" in p.lower() or "unclear" in p.lower() for p in frontend_issues)
        is_waiting = any("waiting" in p.lower() for p in frontend_issues)

        if not assessment_parts and not has_visibility_issue and not is_waiting:
            final_assessment = "Posture analysis indicates good alignment."
        elif has_visibility_issue and not assessment_parts:
            final_assessment = "Could not analyze clearly due to visibility. Adjust position/lighting."
        elif is_waiting and not assessment_parts:
            final_assessment = "Waiting for clearer pose data."
        else: # Has specific issues, possibly with visibility too
            unique_parts = list(dict.fromkeys(assessment_parts)) # Remove duplicates
            final_assessment = ". ".join(unique_parts) + "."
            if has_visibility_issue: final_assessment += " Visibility may affect accuracy."

        final_assessment = final_assessment.replace("..", ".").strip()

        # Determine if extra tips should be shown
        show_extras = False
        if final_score is not None and final_score >= 85 and not has_specific_posture_issue and not has_visibility_issue:
             final_assessment = "Posture looks great! Keep it up."
             show_extras = True # Show tips for maintenance
        elif has_specific_posture_issue: # Show tips if specific recommendations were made
             show_extras = True
        # Don't show extras if only visibility issues or waiting

        unique_recommendations = list(dict.fromkeys([rec for rec in recommendations if rec]))

        # Override if only visibility/waiting
        if (has_visibility_issue or is_waiting) and not has_specific_posture_issue:
            unique_recommendations = []
            show_extras = False

        logger.info(f"Response: Score={final_score}, Assessment='{final_assessment}', Recs={len(unique_recommendations)}, Extras={show_extras}")
        return PostureFeedback(
            score=final_score, assessment=final_assessment, recommendations=unique_recommendations,
            maintenance_tips=maintenance_tips if show_extras else [],
            benefits=benefits if show_extras else None
        )

    except Exception as e:
        logger.error(f"Internal Server Error in /analyze_posture: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal error during analysis: {str(e)}")


@app.get("/desk_setup", response_model=DeskSetupTips)
async def get_desk_setup_tips_endpoint():
    """Provides general ergonomic desk setup tips."""
    logger.info("GET /desk_setup")
    tips = [
        "**Monitor:** Top edge at/below eye level, arm's length away.",
        "**Chair:** Feet flat (use footrest if needed), knees ~level with hips, proper back support.",
        "**Keyboard/Mouse:** Close to body, elbows ~90°, straight wrists.",
        "**Desk Height:** Adjust chair first, then desk for parallel forearms.",
        "**Lighting:** Avoid screen glare; use task lighting if needed.",
        "**Breaks:** Stand, stretch, walk around every 30-60 mins.",
        "**Accessories:** Consider document holder, headset for calls."
    ]
    return DeskSetupTips(tips=tips)

@app.get("/")
async def root():
    logger.info("GET /")
    return {"message": "Posture Assistant API is running!"}

# Run: uvicorn main:app --reload --host 127.0.0.1 --port 8000