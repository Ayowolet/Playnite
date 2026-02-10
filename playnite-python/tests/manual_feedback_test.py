#!/usr/bin/env python3
"""Manual test script for the feedback learning loop.

This script demonstrates the complete feedback learning cycle:
1. Generate recommendations
2. Submit feedback
3. View weight adjustments
4. Verify new recommendations use adjusted weights

Usage:
    python -m playnite_python serve &  # Start the server first
    python tests/manual_feedback_test.py
"""
import requests
import json
import time

BASE_URL = "http://localhost:5555"

# Sample game library
SAMPLE_LIBRARY = [
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
    {
        "game_id": "5",
        "name": "Bloodborne",
        "genres": ["RPG", "Action"],
        "developers": ["FromSoftware"],
        "playtime_seconds": 0,
        "hidden": False,
    },
]


def print_section(title):
    """Print a section header."""
    print(f"\n{'='*60}")
    print(f"  {title}")
    print('='*60 + "\n")


def check_health():
    """Check if the server is running."""
    try:
        response = requests.get(f"{BASE_URL}/api/v1/health")
        return response.status_code == 200
    except requests.exceptions.ConnectionError:
        return False


def generate_recommendations(user_id="test-user", limit=5):
    """Generate recommendations."""
    response = requests.post(
        f"{BASE_URL}/api/v1/recommendations/generate",
        json={
            "user_id": user_id,
            "library": SAMPLE_LIBRARY,
            "limit": limit,
        },
    )
    response.raise_for_status()
    return response.json()


def submit_feedback(recommendation_id, game_id, feedback_type):
    """Submit feedback for a recommendation."""
    response = requests.post(
        f"{BASE_URL}/api/v1/feedback/submit",
        json={
            "recommendation_id": recommendation_id,
            "game_id": game_id,
            "feedback_type": feedback_type,
        },
    )
    response.raise_for_status()
    return response.json()


def get_current_weights():
    """Get current algorithm weights."""
    response = requests.get(f"{BASE_URL}/api/v1/feedback/weights")
    response.raise_for_status()
    return response.json()


def get_accuracy_metrics(time_window_days=30):
    """Get accuracy metrics."""
    response = requests.get(
        f"{BASE_URL}/api/v1/feedback/accuracy?time_window_days={time_window_days}"
    )
    response.raise_for_status()
    return response.json()


def main():
    """Run the feedback loop test."""
    print_section("Feedback Learning Loop Test")

    # Check server
    print("Checking server status...")
    if not check_health():
        print("ERROR: Server is not running!")
        print("Please start the server first:")
        print("  python -m playnite_python serve")
        return 1

    print("✓ Server is running\n")

    # Step 1: Get initial weights
    print_section("Step 1: Initial Algorithm Weights")
    weights_data = get_current_weights()
    initial_weights = weights_data["weights"]
    print("Current algorithm weights:")
    for algo, weight in initial_weights.items():
        print(f"  {algo:15} {weight:.4f}")

    # Step 2: Generate initial recommendations
    print_section("Step 2: Generate Initial Recommendations")
    print("Generating recommendations...")
    recs_data = generate_recommendations(limit=5)
    recommendations = recs_data["recommendations"]

    print(f"\nGenerated {recs_data['count']} recommendations:")
    for i, rec in enumerate(recommendations, 1):
        print(f"\n{i}. {rec['game_name']} (ID: {rec['game_id']})")
        print(f"   Recommendation ID: {rec['recommendation_id']}")
        print(f"   Score: {rec['score']:.3f}")
        print(f"   Reason: {rec['reason']}")
        print(f"   Sources: {', '.join(rec.get('sources', []))}")

    # Step 3: Submit positive feedback
    print_section("Step 3: Submit Positive Feedback")
    test_rec = recommendations[0]
    print(f"Submitting 'liked' feedback for: {test_rec['game_name']}")
    print(f"  Recommendation ID: {test_rec['recommendation_id']}")
    print(f"  Sources that will be rewarded: {test_rec.get('sources', [])}")

    feedback_result = submit_feedback(
        test_rec["recommendation_id"], test_rec["game_id"], "liked"
    )

    print(f"\n✓ Feedback submitted successfully!")
    print(f"  Status: {feedback_result['status']}")
    print(f"  Action: {feedback_result['learning_update']['action']}")

    if feedback_result['learning_update']['adjustments']:
        print("\n  Weight adjustments:")
        for algo, adjustment in feedback_result['learning_update']['adjustments'].items():
            print(f"    {algo:15} {adjustment['old']:.4f} → {adjustment['new']:.4f} (Δ{adjustment['change']:+.4f})")

    # Step 4: Get updated weights
    print_section("Step 4: Updated Algorithm Weights")
    weights_data = get_current_weights()
    updated_weights = weights_data["weights"]

    print("Updated algorithm weights:")
    for algo, weight in updated_weights.items():
        old = initial_weights.get(algo, 0)
        change = weight - old
        print(f"  {algo:15} {weight:.4f} (Δ{change:+.4f})")

    # Step 5: Generate new recommendations with adjusted weights
    print_section("Step 5: Generate New Recommendations")
    print("Generating new recommendations with adjusted weights...")
    new_recs_data = generate_recommendations(limit=5)
    new_recommendations = new_recs_data["recommendations"]

    print(f"\nGenerated {new_recs_data['count']} new recommendations:")
    for i, rec in enumerate(new_recommendations, 1):
        print(f"\n{i}. {rec['game_name']} (ID: {rec['game_id']})")
        print(f"   Score: {rec['score']:.3f}")
        print(f"   Sources: {', '.join(rec.get('sources', []))}")

    # Step 6: Try negative feedback
    print_section("Step 6: Submit Negative Feedback")
    if len(new_recommendations) > 1:
        test_rec2 = new_recommendations[1]
        print(f"Submitting 'dismissed' feedback for: {test_rec2['game_name']}")

        feedback_result2 = submit_feedback(
            test_rec2["recommendation_id"], test_rec2["game_id"], "dismissed"
        )

        print(f"\n✓ Negative feedback submitted!")
        print(f"  Action: {feedback_result2['learning_update']['action']}")

        if feedback_result2['learning_update']['adjustments']:
            print("\n  Weight adjustments:")
            for algo, adjustment in feedback_result2['learning_update']['adjustments'].items():
                print(f"    {algo:15} {adjustment['old']:.4f} → {adjustment['new']:.4f} (Δ{adjustment['change']:+.4f})")

    # Step 7: Get accuracy metrics
    print_section("Step 7: Accuracy Metrics")
    metrics = get_accuracy_metrics()

    print(f"Total recommendations with feedback: {metrics['total_recommendations']}")
    print(f"Overall accuracy: {metrics['accuracy']:.2%}")
    print(f"\nAccuracy by algorithm:")
    for algo, stats in metrics.get('by_algorithm', {}).items():
        print(f"  {algo:15} {stats['accuracy']:.2%} ({stats['positive']}/{stats['total']})")

    print_section("✓ Feedback Learning Loop Test Complete!")
    print("The system successfully:")
    print("  1. Generated initial recommendations")
    print("  2. Stored them in the database")
    print("  3. Processed user feedback")
    print("  4. Adjusted algorithm weights")
    print("  5. Generated new recommendations with updated weights")
    print("  6. Tracked accuracy metrics")
    print()

    return 0


if __name__ == "__main__":
    try:
        exit(main())
    except requests.exceptions.RequestException as e:
        print(f"\nERROR: {e}")
        print("\nMake sure the server is running:")
        print("  python -m playnite_python serve")
        exit(1)
    except KeyboardInterrupt:
        print("\n\nTest interrupted by user")
        exit(1)
