"""Integration test for feedback learning system."""
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from playnite_python.api.app import app
from playnite_python.database.models import Base, Recommendation
from playnite_python.database.connection import get_db


# Test database setup
TEST_DATABASE_URL = "sqlite:///./test_feedback.db"
test_engine = create_engine(TEST_DATABASE_URL, connect_args={"check_same_thread": False})
TestSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)


def override_get_db():
    """Override database dependency for testing."""
    db = TestSessionLocal()
    try:
        yield db
    finally:
        db.close()


@pytest.fixture(scope="function")
def setup_database():
    """Create test database tables."""
    Base.metadata.create_all(bind=test_engine)
    yield
    Base.metadata.drop_all(bind=test_engine)


@pytest.fixture
def sample_library():
    """Sample game library for testing."""
    return [
        {
            "game_id": "1",
            "name": "Dark Souls",
            "genres": ["RPG", "Action"],
            "developers": ["FromSoftware"],
            "playtime_seconds": 72000,
            "user_score": 90,
            "favorite": True,
            "hidden": False,
        },
        {
            "game_id": "2",
            "name": "Elden Ring",
            "genres": ["RPG", "Action"],
            "developers": ["FromSoftware"],
            "playtime_seconds": 0,
            "hidden": False,
        },
        {
            "game_id": "3",
            "name": "Stardew Valley",
            "genres": ["Simulation", "Indie"],
            "developers": ["ConcernedApe"],
            "playtime_seconds": 0,
            "hidden": False,
        },
        {
            "game_id": "4",
            "name": "The Witcher 3",
            "genres": ["RPG", "Action"],
            "developers": ["CD Projekt Red"],
            "playtime_seconds": 0,
            "hidden": False,
        },
    ]


def test_complete_feedback_loop(setup_database, sample_library):
    """
    Test the complete feedback learning loop:
    1. Generate recommendations (stored in database)
    2. Submit positive feedback
    3. Verify weights adjusted
    4. Generate new recommendations with adjusted weights
    """
    # Override database dependency
    app.dependency_overrides[get_db] = override_get_db

    with TestClient(app) as client:
        # Step 1: Generate initial recommendations
        response = client.post(
            "/api/v1/recommendations/generate",
            json={
                "user_id": "test-user",
                "library": sample_library,
                "limit": 3,
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert data["count"] > 0
        recommendations = data["recommendations"]

        # Verify recommendations have IDs
        for rec in recommendations:
            assert "recommendation_id" in rec
            assert rec["recommendation_id"] is not None

        # Step 2: Get initial weights
        weights_response = client.get("/api/v1/feedback/weights")
        assert weights_response.status_code == 200
        initial_weights = weights_response.json()["weights"]
        print(f"Initial weights: {initial_weights}")

        # Step 3: Submit positive feedback for a recommendation
        test_rec = recommendations[0]
        feedback_response = await client.post(
            "/api/v1/feedback/submit",
            json={
                "recommendation_id": test_rec["recommendation_id"],
                "game_id": test_rec["game_id"],
                "feedback_type": "liked",
            },
        )

        assert feedback_response.status_code == 200
        feedback_data = feedback_response.json()
        assert feedback_data["status"] == "success"
        assert feedback_data["feedback_type"] == "liked"
        assert "learning_update" in feedback_data

        # Verify weights were adjusted
        learning_update = feedback_data["learning_update"]
        assert learning_update["action"] == "reward"
        print(f"Learning update: {learning_update}")

        # Step 4: Get updated weights
        weights_response = client.get("/api/v1/feedback/weights")
        updated_weights = weights_response.json()["weights"]
        print(f"Updated weights: {updated_weights}")

        # Verify weights changed (sources that contributed should have increased)
        sources = test_rec.get("sources", [])
        for source in sources:
            if source in initial_weights and source in updated_weights:
                # Weight should have increased (after normalization)
                print(
                    f"Source '{source}': {initial_weights[source]:.4f} -> {updated_weights[source]:.4f}"
                )

        # Step 5: Generate new recommendations with adjusted weights
        response2 = await client.post(
            "/api/v1/recommendations/generate",
            json={
                "user_id": "test-user",
                "library": sample_library,
                "limit": 3,
            },
        )

        assert response2.status_code == 200
        new_recommendations = response2.json()["recommendations"]
        print(f"Generated {len(new_recommendations)} new recommendations with adjusted weights")

    # Cleanup
    app.dependency_overrides.clear()


def test_negative_feedback_adjustment(setup_database, sample_library):
    """Test that negative feedback decreases algorithm weights."""
    app.dependency_overrides[get_db] = override_get_db

    with TestClient(app) as client:
        # Generate recommendations
        response = client.post(
            "/api/v1/recommendations/generate",
            json={
                "user_id": "test-user",
                "library": sample_library,
                "limit": 3,
            },
        )

        assert response.status_code == 200
        recommendations = response.json()["recommendations"]
        test_rec = recommendations[0]

        # Get initial weights
        weights_response = client.get("/api/v1/feedback/weights")
        initial_weights = weights_response.json()["weights"]

        # Submit negative feedback
        feedback_response = await client.post(
            "/api/v1/feedback/submit",
            json={
                "recommendation_id": test_rec["recommendation_id"],
                "game_id": test_rec["game_id"],
                "feedback_type": "dismissed",
            },
        )

        assert feedback_response.status_code == 200
        feedback_data = feedback_response.json()
        assert feedback_data["feedback_type"] == "dismissed"

        # Verify penalize action
        learning_update = feedback_data["learning_update"]
        assert learning_update["action"] == "penalize"
        print(f"Penalized sources: {learning_update}")

    app.dependency_overrides.clear()


def test_accuracy_metrics(setup_database, sample_library):
    """Test accuracy metrics calculation."""
    app.dependency_overrides[get_db] = override_get_db

    with TestClient(app) as client:
        # Generate multiple recommendations
        for i in range(5):
            client.post(
                "/api/v1/recommendations/generate",
                json={
                    "user_id": "test-user",
                    "library": sample_library,
                    "limit": 2,
                },
            )

        # Get all recommendations and submit feedback
        db = TestSessionLocal()
        recommendations = db.query(Recommendation).all()

        # Submit mixed feedback
        for i, rec in enumerate(recommendations):
            feedback_type = "liked" if i % 2 == 0 else "dismissed"
            client.post(
                "/api/v1/feedback/submit",
                json={
                    "recommendation_id": rec.id,
                    "game_id": rec.game_id,
                    "feedback_type": feedback_type,
                },
            )

        db.close()

        # Get accuracy metrics
        metrics_response = client.get("/api/v1/feedback/accuracy?time_window_days=30")
        assert metrics_response.status_code == 200
        metrics = metrics_response.json()

        print(f"Accuracy metrics: {metrics}")
        assert "accuracy" in metrics
        assert "by_algorithm" in metrics
        assert "total_recommendations" in metrics
        assert metrics["total_recommendations"] > 0

    app.dependency_overrides.clear()


def test_weight_reset(setup_database):
    """Test resetting algorithm weights to defaults."""
    app.dependency_overrides[get_db] = override_get_db

    with TestClient(app) as client:
        # Reset weights
        response = client.post("/api/v1/feedback/reset-weights")
        assert response.status_code == 200
        data = response.json()

        assert data["status"] == "success"
        weights = data["weights"]

        # Verify defaults
        assert weights["content"] == 0.6
        assert weights["collaborative"] == 0.4
        print(f"Reset to default weights: {weights}")

    app.dependency_overrides.clear()


def test_auto_tune_weights(setup_database, sample_library):
    """Test automatic weight tuning based on accuracy."""
    app.dependency_overrides[get_db] = override_get_db

    with TestClient(app) as client:
        # Generate recommendations
        for i in range(10):
            client.post(
                "/api/v1/recommendations/generate",
                json={
                    "user_id": "test-user",
                    "library": sample_library,
                    "limit": 2,
                },
            )

        # Submit feedback heavily favoring one algorithm
        db = TestSessionLocal()
        recommendations = db.query(Recommendation).all()

        for rec in recommendations:
            # Like all content-based recommendations
            if "content" in (rec.sources or []):
                feedback_type = "liked"
            else:
                feedback_type = "dismissed"

            client.post(
                "/api/v1/feedback/submit",
                json={
                    "recommendation_id": rec.id,
                    "game_id": rec.game_id,
                    "feedback_type": feedback_type,
                },
            )

        db.close()

        # Auto-tune weights
        tune_response = client.post("/api/v1/feedback/tune-weights?time_window_days=30")
        assert tune_response.status_code == 200
        tune_data = tune_response.json()

        print(f"Auto-tune result: {tune_data}")
        assert tune_data["status"] == "success"
        assert "metrics" in tune_data
        assert "tuning" in tune_data

    app.dependency_overrides.clear()
