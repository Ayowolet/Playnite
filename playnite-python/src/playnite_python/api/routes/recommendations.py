"""API routes for game recommendations."""
from datetime import datetime, timezone
from fastapi import APIRouter, HTTPException, Depends
from loguru import logger
from sqlalchemy.orm import Session

from ..models.recommendation import (
    RecommendationRequest,
    RecommendationResponse,
    RecommendationListResponse,
)
from ...recommendations.engine import RecommendationEngine
from ...database.connection import get_db
from ...database.models import Recommendation

router = APIRouter()
engine = RecommendationEngine()


@router.post("/generate", response_model=RecommendationListResponse)
async def generate_recommendations(
    request: RecommendationRequest, db: Session = Depends(get_db)
):
    """
    Generate personalized game recommendations.

    Takes a user's game library and optional context to generate recommendations
    using content-based filtering, collaborative filtering, and contextual adjustments.

    Recommendations are stored in the database to enable feedback tracking.
    """
    try:
        logger.info(f"Generating recommendations for user {request.user_id}")

        # Convert Pydantic models to dicts
        library_dicts = [game.model_dump() for game in request.library]
        context_dict = request.context.model_dump() if request.context else None
        filters_dict = request.filters.model_dump() if request.filters else None

        # Generate recommendations
        recommendations = engine.generate(
            user_id=request.user_id,
            library=library_dicts,
            play_histories=[],  # TODO: Fetch from database
            context=context_dict,
            filters=filters_dict,
            limit=request.limit,
        )

        # Store recommendations in database and build response
        response_recs = []
        for rec in recommendations:
            # Create database record
            db_recommendation = Recommendation(
                user_id=request.user_id,
                game_id=rec["game_id"],
                score=rec["score"],
                reason=rec["reason"],
                factors=rec["factors"],
                sources=rec.get("sources", []),
            )
            db.add(db_recommendation)
            db.flush()  # Get the ID without committing

            # Build response with recommendation ID
            response_recs.append(
                RecommendationResponse(
                    recommendation_id=db_recommendation.id,
                    game_id=rec["game_id"],
                    game_name=rec.get("game_name"),
                    score=rec["score"],
                    reason=rec["reason"],
                    factors=rec["factors"],
                    sources=rec.get("sources", []),
                )
            )

        # Commit all recommendations
        db.commit()

        logger.info(
            f"Stored {len(response_recs)} recommendations in database for user {request.user_id}"
        )

        return RecommendationListResponse(
            recommendations=response_recs,
            count=len(response_recs),
            generated_at=datetime.now(timezone.utc).isoformat(),
            model_version="1.0.0",
        )

    except Exception as e:
        db.rollback()
        logger.error(f"Failed to generate recommendations: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/test")
async def test_recommendations(db: Session = Depends(get_db)):
    """
    Test endpoint with sample data.

    Useful for verifying the recommendation engine works without Playnite integration.
    """
    # Sample game library
    sample_library = [
        {
            "game_id": "1",
            "name": "Dark Souls",
            "genres": ["RPG", "Action"],
            "developers": ["FromSoftware"],
            "playtime_seconds": 72000,
            "user_score": 90,
            "favorite": True,
        },
        {
            "game_id": "2",
            "name": "Elden Ring",
            "genres": ["RPG", "Action"],
            "developers": ["FromSoftware"],
            "playtime_seconds": 0,
        },
        {
            "game_id": "3",
            "name": "Stardew Valley",
            "genres": ["Simulation", "Indie"],
            "developers": ["ConcernedApe"],
            "playtime_seconds": 0,
        },
        {
            "game_id": "4",
            "name": "The Witcher 3",
            "genres": ["RPG", "Action"],
            "developers": ["CD Projekt Red"],
            "playtime_seconds": 0,
        },
    ]

    recommendations = engine.generate(
        user_id="test-user",
        library=sample_library,
        play_histories=[],
        context=None,
        limit=3,
    )

    # Store test recommendations
    stored_recs = []
    for rec in recommendations:
        db_recommendation = Recommendation(
            user_id="test-user",
            game_id=rec["game_id"],
            score=rec["score"],
            reason=rec["reason"],
            factors=rec["factors"],
            sources=rec.get("sources", []),
        )
        db.add(db_recommendation)
        db.flush()
        stored_recs.append({**rec, "recommendation_id": db_recommendation.id})

    db.commit()

    return {
        "message": "Test recommendations generated successfully",
        "recommendations": stored_recs,
    }
