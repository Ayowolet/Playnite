"""API routes for recommendation feedback and learning."""
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from loguru import logger
from sqlalchemy.orm import Session

from ...database.connection import get_db
from ...database.models import Recommendation
from ...recommendations.feedback_learner import FeedbackLearner

router = APIRouter()

# Global feedback learner instance
feedback_learner = FeedbackLearner()


class FeedbackRequest(BaseModel):
    """Request to submit feedback on a recommendation."""

    recommendation_id: int
    game_id: str
    feedback_type: str  # 'liked', 'played', 'dismissed', 'hidden'


class FeedbackResponse(BaseModel):
    """Response after submitting feedback."""

    status: str
    recommendation_id: int
    feedback_type: str
    learning_update: dict


@router.post("/submit", response_model=FeedbackResponse)
async def submit_feedback(request: FeedbackRequest, db: Session = Depends(get_db)):
    """
    Submit user feedback on a recommendation.

    Feedback types:
    - 'liked': User explicitly liked this recommendation
    - 'played': User played the recommended game
    - 'dismissed': User dismissed this recommendation
    - 'hidden': User hid this game

    The system learns from feedback to improve future recommendations.
    """
    try:
        # Validate feedback type
        valid_types = ['liked', 'played', 'dismissed', 'hidden']
        if request.feedback_type not in valid_types:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid feedback_type. Must be one of: {valid_types}"
            )

        # Find the recommendation in database
        recommendation = db.query(Recommendation).filter(
            Recommendation.id == request.recommendation_id
        ).first()

        if not recommendation:
            raise HTTPException(
                status_code=404,
                detail=f"Recommendation {request.recommendation_id} not found"
            )

        # Update recommendation with feedback
        recommendation.user_feedback = request.feedback_type

        # Prepare recommendation data for learning
        rec_data = {
            'sources': recommendation.factors.get('sources', []) if recommendation.factors else [],
            'factors': recommendation.factors or {}
        }

        # Process feedback through learning system
        learning_update = feedback_learner.process_feedback(
            recommendation_id=request.recommendation_id,
            game_id=request.game_id,
            feedback_type=request.feedback_type,
            recommendation_data=rec_data
        )

        db.commit()

        logger.info(
            f"Feedback submitted: {request.feedback_type} for recommendation "
            f"{request.recommendation_id} (game: {request.game_id})"
        )

        return FeedbackResponse(
            status="success",
            recommendation_id=request.recommendation_id,
            feedback_type=request.feedback_type,
            learning_update=learning_update
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to submit feedback: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/accuracy")
async def get_accuracy_metrics(
    time_window_days: int = 30,
    db: Session = Depends(get_db)
):
    """
    Get recommendation accuracy metrics.

    Shows how accurate recommendations have been over the specified time period.
    """
    try:
        # Fetch recommendations with feedback
        recommendations = db.query(Recommendation).filter(
            Recommendation.user_feedback.isnot(None)
        ).all()

        # Convert to dicts
        recs_with_feedback = []
        for rec in recommendations:
            recs_with_feedback.append({
                'recommendation_id': rec.id,
                'game_id': rec.game_id,
                'user_feedback': rec.user_feedback,
                'generated_at': rec.generated_at.isoformat() if rec.generated_at else None,
                'sources': rec.factors.get('sources', []) if rec.factors else [],
                'score': rec.score
            })

        # Calculate metrics
        metrics = feedback_learner.calculate_accuracy_metrics(
            recs_with_feedback,
            time_window_days
        )

        return {
            **metrics,
            'current_weights': feedback_learner.get_current_weights()
        }

    except Exception as e:
        logger.error(f"Failed to calculate accuracy metrics: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/tune-weights")
async def tune_weights(
    time_window_days: int = 30,
    db: Session = Depends(get_db)
):
    """
    Auto-tune algorithm weights based on accuracy metrics.

    Analyzes which algorithms perform best and adjusts their weights accordingly.
    """
    try:
        # Get accuracy metrics
        recommendations = db.query(Recommendation).filter(
            Recommendation.user_feedback.isnot(None)
        ).all()

        recs_with_feedback = []
        for rec in recommendations:
            recs_with_feedback.append({
                'recommendation_id': rec.id,
                'game_id': rec.game_id,
                'user_feedback': rec.user_feedback,
                'generated_at': rec.generated_at.isoformat() if rec.generated_at else None,
                'sources': rec.factors.get('sources', []) if rec.factors else [],
            })

        metrics = feedback_learner.calculate_accuracy_metrics(
            recs_with_feedback,
            time_window_days
        )

        # Auto-tune weights
        tuning_result = feedback_learner.auto_tune_weights(metrics)

        return {
            'status': 'success',
            'metrics': metrics,
            'tuning': tuning_result
        }

    except Exception as e:
        logger.error(f"Failed to tune weights: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/weights")
async def get_current_weights():
    """
    Get current algorithm weights.

    Shows how much each algorithm contributes to final recommendations.
    """
    return {
        'weights': feedback_learner.get_current_weights(),
        'description': {
            'content': 'Weight for content-based filtering (game attributes)',
            'collaborative': 'Weight for collaborative filtering (popularity)',
        }
    }


@router.post("/reset-weights")
async def reset_weights():
    """
    Reset algorithm weights to defaults.

    Useful for testing or if learning has gone off track.
    """
    feedback_learner.algorithm_weights = {
        'content': 0.6,
        'collaborative': 0.4,
    }

    logger.info("Algorithm weights reset to defaults")

    return {
        'status': 'success',
        'weights': feedback_learner.get_current_weights()
    }
