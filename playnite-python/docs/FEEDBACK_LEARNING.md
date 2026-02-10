# Feedback Learning System

The feedback learning system enables the recommendation engine to improve over time by learning from user interactions. It tracks which recommendations users accept or dismiss and automatically adjusts algorithm weights to optimize future suggestions.

## Overview

The system implements a reinforcement learning approach where:
- **Positive feedback** (liked, played) increases weights for algorithms that generated good recommendations
- **Negative feedback** (dismissed, hidden) decreases weights for algorithms that generated poor recommendations
- **Weights are normalized** to sum to 1.0 after each adjustment
- **Learning rate** controls how quickly the system adapts (default: 0.05)

## Feedback Types

| Type | Meaning | Effect |
|------|---------|--------|
| `liked` | User explicitly liked the recommendation | Reward contributing algorithms |
| `played` | User played the recommended game | Reward contributing algorithms |
| `dismissed` | User dismissed the recommendation | Penalize contributing algorithms |
| `hidden` | User hid the game | Penalize contributing algorithms |

## API Endpoints

### Submit Feedback

Submit user feedback on a recommendation:

```http
POST /api/v1/feedback/submit
Content-Type: application/json

{
  "recommendation_id": 123,
  "game_id": "game-uuid",
  "feedback_type": "liked"
}
```

**Response:**
```json
{
  "status": "success",
  "recommendation_id": 123,
  "feedback_type": "liked",
  "learning_update": {
    "action": "reward",
    "adjustments": {
      "content": {
        "old": 0.600,
        "new": 0.630,
        "change": 0.030
      }
    },
    "current_weights": {
      "content": 0.630,
      "collaborative": 0.370
    }
  }
}
```

### Get Current Weights

View current algorithm weights:

```http
GET /api/v1/feedback/weights
```

**Response:**
```json
{
  "weights": {
    "content": 0.600,
    "collaborative": 0.400
  },
  "description": {
    "content": "Weight for content-based filtering (game attributes)",
    "collaborative": "Weight for collaborative filtering (popularity)"
  }
}
```

### Get Accuracy Metrics

Calculate recommendation accuracy over a time window:

```http
GET /api/v1/feedback/accuracy?time_window_days=30
```

**Response:**
```json
{
  "total_recommendations": 45,
  "accuracy": 0.756,
  "by_algorithm": {
    "content": {
      "accuracy": 0.800,
      "total": 30,
      "positive": 24
    },
    "collaborative": {
      "accuracy": 0.667,
      "total": 15,
      "positive": 10
    }
  },
  "time_window_days": 30,
  "cutoff_date": "2025-12-10T00:00:00+00:00",
  "current_weights": {
    "content": 0.600,
    "collaborative": 0.400
  }
}
```

### Auto-Tune Weights

Automatically adjust weights based on accuracy metrics:

```http
POST /api/v1/feedback/tune-weights?time_window_days=30
```

The auto-tuning algorithm:
- Increases weight if accuracy > 70% (performing well)
- Decreases weight if accuracy < 30% (performing poorly)
- Makes minor adjustments for accuracy between 30-70%

**Response:**
```json
{
  "status": "tuned",
  "metrics": { /* same as accuracy endpoint */ },
  "tuning": {
    "status": "tuned",
    "adjustments": {
      "content": {
        "old": 0.600,
        "new": 0.650,
        "accuracy": 0.800
      },
      "collaborative": {
        "old": 0.400,
        "new": 0.350,
        "accuracy": 0.667
      }
    },
    "new_weights": {
      "content": 0.650,
      "collaborative": 0.350
    }
  }
}
```

### Reset Weights

Reset algorithm weights to defaults:

```http
POST /api/v1/feedback/reset-weights
```

**Response:**
```json
{
  "status": "success",
  "weights": {
    "content": 0.600,
    "collaborative": 0.400
  }
}
```

## How It Works

### 1. Recommendation Generation

When recommendations are generated, they are stored in the database with:
- User ID
- Game ID
- Score
- Reason
- Contributing algorithms (sources)
- Scoring factors

```python
# Recommendations are automatically stored
response = requests.post(
    "http://localhost:5555/api/v1/recommendations/generate",
    json={
        "user_id": "user-123",
        "library": game_library,
        "limit": 10
    }
)

# Each recommendation includes an ID for feedback
recommendations = response.json()["recommendations"]
for rec in recommendations:
    print(f"{rec['game_name']}: ID {rec['recommendation_id']}")
```

### 2. Feedback Submission

Users submit feedback using the recommendation ID:

```python
# User liked a recommendation
requests.post(
    "http://localhost:5555/api/v1/feedback/submit",
    json={
        "recommendation_id": 123,
        "game_id": "game-uuid",
        "feedback_type": "liked"
    }
)
```

### 3. Weight Adjustment

The system adjusts weights based on which algorithms contributed:

```python
class FeedbackLearner:
    def __init__(self):
        self.algorithm_weights = {
            "content": 0.6,
            "collaborative": 0.4
        }
        self.learning_rate = 0.05  # How fast to learn
        self.min_weight = 0.1      # Minimum weight
        self.max_weight = 0.9      # Maximum weight

    def process_feedback(self, feedback_type, sources):
        if feedback_type in ['liked', 'played']:
            # Reward contributing algorithms
            for source in sources:
                self.algorithm_weights[source] += self.learning_rate
        else:
            # Penalize contributing algorithms
            for source in sources:
                self.algorithm_weights[source] -= self.learning_rate

        # Normalize weights to sum to 1.0
        self._normalize_weights()
```

### 4. Updated Recommendations

Future recommendations use the adjusted weights:

```python
# Content-based recommendations
content_score = 0.85
weighted_score = content_score * current_weights["content"]

# Collaborative recommendations
collab_score = 0.70
weighted_score = collab_score * current_weights["collaborative"]

# Final score is weighted sum
final_score = (content_score * 0.63) + (collab_score * 0.37)
```

## Integration with Playnite

### C# Plugin Integration

```csharp
// When showing recommendations to user
public async Task ShowRecommendations()
{
    var recommendations = await pythonService.GetRecommendationsAsync(userId);

    // Store recommendation IDs for feedback
    foreach (var rec in recommendations)
    {
        recommendationCache[rec.GameId] = rec.RecommendationId;
    }

    // Show UI...
}

// When user likes a game
public async Task OnGameLiked(string gameId)
{
    if (recommendationCache.TryGetValue(gameId, out int recId))
    {
        await pythonService.SubmitFeedbackAsync(recId, gameId, "liked");
    }
}

// When user dismisses a recommendation
public async Task OnRecommendationDismissed(string gameId)
{
    if (recommendationCache.TryGetValue(gameId, out int recId))
    {
        await pythonService.SubmitFeedbackAsync(recId, gameId, "dismissed");
    }
}
```

## Testing

### Manual Test

Run the manual test script to verify the complete feedback loop:

```bash
# Start the server
python -m playnite_python serve &

# Run the test
python tests/manual_feedback_test.py
```

The test will:
1. Generate initial recommendations
2. Submit positive feedback
3. Show weight adjustments
4. Generate new recommendations with updated weights
5. Display accuracy metrics

### Automated Tests

Run the pytest integration tests:

```bash
pytest tests/integration/test_feedback_learning.py -v
```

## Configuration

### Learning Rate

Control how quickly the system adapts:

```python
# In feedback_learner.py
self.learning_rate = 0.05  # Default: 5% adjustment per feedback

# Lower learning rate (0.01-0.03): Slow, stable learning
# Higher learning rate (0.10-0.20): Fast, aggressive learning
```

### Weight Bounds

Prevent any algorithm from dominating:

```python
self.min_weight = 0.1  # Minimum 10% contribution
self.max_weight = 0.9  # Maximum 90% contribution
```

## Best Practices

### 1. Collect Sufficient Feedback

- Wait for at least 20-30 feedback samples before auto-tuning
- Consider different user behaviors (some like, some dismiss)
- Track feedback over multiple days/weeks

### 2. Periodic Auto-Tuning

Set up a scheduled task to auto-tune weights:

```python
# Weekly auto-tuning
import schedule

def auto_tune():
    requests.post(
        "http://localhost:5555/api/v1/feedback/tune-weights",
        params={"time_window_days": 30}
    )

schedule.every().monday.at("02:00").do(auto_tune)
```

### 3. Monitor Accuracy Metrics

Track accuracy trends over time:

```python
# Check weekly metrics
metrics = requests.get(
    "http://localhost:5555/api/v1/feedback/accuracy",
    params={"time_window_days": 7}
).json()

if metrics["accuracy"] < 0.5:
    # Consider resetting weights or reviewing algorithms
    print("Warning: Low recommendation accuracy!")
```

### 4. Reset When Needed

Reset weights if learning goes off track:

```python
# Reset to defaults
requests.post("http://localhost:5555/api/v1/feedback/reset-weights")
```

## Troubleshooting

### Weights Not Changing

- Verify recommendations are stored in database (check recommendation_id is returned)
- Ensure feedback submission includes correct recommendation_id
- Check database has recommendations with feedback

### Accuracy Always Low

- Review feedback types (are they correctly categorized?)
- Check if library has sufficient variety
- Consider resetting weights and recalibrating

### One Algorithm Dominating

- Lower the learning rate
- Adjust min/max weight bounds
- Manually reset weights

## Future Enhancements

Potential improvements to the learning system:

1. **User-specific weights**: Learn individual preferences per user
2. **Time decay**: Give more weight to recent feedback
3. **Context-aware learning**: Adjust weights based on mood/time
4. **Multi-armed bandit**: Explore/exploit tradeoff for recommendations
5. **A/B testing**: Compare different weight configurations

## See Also

- [API Documentation](API.md) - Complete API reference
- [Architecture](ARCHITECTURE.md) - System architecture overview
- [Recommendation Engine](RECOMMENDATIONS.md) - How recommendations work
