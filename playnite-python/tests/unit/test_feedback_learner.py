"""Unit tests for FeedbackLearner."""
import pytest
from src.playnite_python.recommendations.feedback_learner import FeedbackLearner


@pytest.fixture
def learner():
    """Create a FeedbackLearner instance for testing."""
    return FeedbackLearner()


def test_initial_weights(learner):
    """Test that learner starts with correct initial weights."""
    weights = learner.get_current_weights()

    assert weights["content"] == 0.6
    assert weights["collaborative"] == 0.4
    assert sum(weights.values()) == pytest.approx(1.0)


def test_reward_sources(learner):
    """Test that rewarding sources increases weights."""
    initial_content = learner.algorithm_weights["content"]

    # Reward content-based source
    result = learner._reward_sources(["content"])

    assert result["action"] == "reward"
    assert "content" in result["adjustments"]
    assert learner.algorithm_weights["content"] > initial_content


def test_penalize_sources(learner):
    """Test that penalizing sources decreases weights."""
    initial_collab = learner.algorithm_weights["collaborative"]

    # Penalize collaborative source
    result = learner._penalize_sources(["collaborative"])

    assert result["action"] == "penalize"
    assert "collaborative" in result["adjustments"]
    assert learner.algorithm_weights["collaborative"] < initial_collab


def test_weight_normalization(learner):
    """Test that weights always sum to 1.0 after adjustments."""
    # Reward one source multiple times
    for _ in range(5):
        learner._reward_sources(["content"])

    weights = learner.get_current_weights()
    assert sum(weights.values()) == pytest.approx(1.0)


def test_weight_bounds(learner):
    """Test that weights respect min/max bounds."""
    # Try to exceed max weight
    for _ in range(100):
        learner._reward_sources(["content"])

    weights = learner.get_current_weights()
    assert all(w <= learner.max_weight for w in weights.values())
    assert all(w >= learner.min_weight for w in weights.values())


def test_process_feedback_positive(learner):
    """Test processing positive feedback."""
    rec_data = {
        "sources": ["content", "collaborative"],
        "factors": {"similarity": 0.8}
    }

    result = learner.process_feedback(
        recommendation_id=1,
        game_id="game_1",
        feedback_type="liked",
        recommendation_data=rec_data
    )

    assert result["action"] == "reward"
    assert "content" in result["adjustments"]
    assert "collaborative" in result["adjustments"]


def test_process_feedback_negative(learner):
    """Test processing negative feedback."""
    rec_data = {
        "sources": ["content"],
        "factors": {}
    }

    result = learner.process_feedback(
        recommendation_id=1,
        game_id="game_1",
        feedback_type="dismissed",
        recommendation_data=rec_data
    )

    assert result["action"] == "penalize"
    assert "content" in result["adjustments"]


def test_calculate_accuracy_metrics_empty(learner):
    """Test accuracy metrics with no data."""
    metrics = learner.calculate_accuracy_metrics([], time_window_days=30)

    assert metrics["total_recommendations"] == 0
    assert metrics["accuracy"] == 0.0
    assert metrics["by_algorithm"] == {}


def test_calculate_accuracy_metrics_with_data(learner):
    """Test accuracy metrics calculation."""
    from datetime import datetime, timezone

    recommendations = [
        {
            "recommendation_id": 1,
            "game_id": "game_1",
            "user_feedback": "liked",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "sources": ["content"],
            "score": 0.8
        },
        {
            "recommendation_id": 2,
            "game_id": "game_2",
            "user_feedback": "dismissed",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "sources": ["content"],
            "score": 0.6
        },
        {
            "recommendation_id": 3,
            "game_id": "game_3",
            "user_feedback": "played",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "sources": ["collaborative"],
            "score": 0.7
        }
    ]

    metrics = learner.calculate_accuracy_metrics(recommendations, time_window_days=30)

    assert metrics["total_recommendations"] == 3  # 3 recommendations provided
    assert 0.0 <= metrics["accuracy"] <= 1.0
    assert "content" in metrics["by_algorithm"]
    assert "collaborative" in metrics["by_algorithm"]


def test_auto_tune_weights_no_data(learner):
    """Test auto-tuning with no data."""
    metrics = {"by_algorithm": {}}

    result = learner.auto_tune_weights(metrics)

    assert result["status"] == "no_data"


def test_auto_tune_weights_high_accuracy(learner):
    """Test auto-tuning increases weight for high-performing algorithms."""
    metrics = {
        "by_algorithm": {
            "content": {
                "accuracy": 0.85,  # High accuracy
                "total": 20,
                "positive": 17
            }
        }
    }

    initial_weight = learner.algorithm_weights["content"]
    result = learner.auto_tune_weights(metrics)

    assert result["status"] == "tuned"
    assert learner.algorithm_weights["content"] > initial_weight


def test_auto_tune_weights_low_accuracy(learner):
    """Test auto-tuning decreases weight for low-performing algorithms."""
    metrics = {
        "by_algorithm": {
            "collaborative": {
                "accuracy": 0.2,  # Low accuracy
                "total": 20,
                "positive": 4
            }
        }
    }

    initial_weight = learner.algorithm_weights["collaborative"]
    result = learner.auto_tune_weights(metrics)

    assert result["status"] == "tuned"
    assert learner.algorithm_weights["collaborative"] < initial_weight
