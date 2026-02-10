# Playnite Python Integration

Python-based plugin system for Playnite game library manager providing intelligent game recommendations and comprehensive media capture capabilities.

> **📋 Implementation Status:** All core features complete (92-95%). See [IMPLEMENTATION_SUMMARY.md](IMPLEMENTATION_SUMMARY.md) for detailed completion report.

## Features

### 🎯 Intelligent Game Recommendation Engine
- **Content-Based Filtering**: Recommendations based on game attributes (genres, developers, themes)
- **Collaborative Filtering**: Suggestions based on similar user profiles
- **Context-Aware**: Mood-based and temporal recommendations
- **Learning System**: Improves from user feedback over time
- **Explanation Engine**: Clear reasoning for each recommendation

#### How Recommendations Work

The engine uses a **hybrid approach** combining multiple algorithms:

1. **Content-Based Filtering (60% weight)**
   - Analyzes game attributes (genres, developers, tags, features)
   - Uses TF-IDF vectorization to create game "fingerprints"
   - Calculates similarity between games using cosine similarity
   - Recommends unplayed games similar to ones you enjoyed

2. **Collaborative Filtering (40% weight)**
   - Uses community scores and popularity data
   - Identifies trending and highly-rated games
   - Future: Multi-user collaborative filtering with matrix factorization

3. **Contextual Boosting**
   - Mood-based adjustments (relaxing, challenging, story-driven)
   - Time-of-day preferences (quick games for morning, deep games for evening)
   - Session length considerations (short 15min vs. long 2hr+ sessions)

4. **Adaptive Learning**
   - Tracks user feedback (liked, played, dismissed)
   - Automatically adjusts algorithm weights based on accuracy
   - Continuously improves recommendations over time

**Example**: If you enjoyed Dark Souls (60 hours played), the system will:
- Find similar games (Elden Ring, Bloodborne) via content analysis
- Boost challenging games if you selected "challenging" mood
- Weight recommendations by community ratings
- Learn from your feedback to improve future suggestions

For detailed algorithm documentation, see [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md#recommendation-algorithm).

### 📸 Screenshot & Video Capture System
- **Automatic Detection**: Enables capture when games are running
- **Flexible Capture**: Screenshots, video recording, instant replay
- **Multiple Backends**: Direct capture, OBS Studio, Windows Game Bar
- **Smart Organization**: Automatically organized by game in library structure
- **Media Processing**: Basic editing, highlight detection, montage generation
- **Storage Management**: Automatic cleanup policies and format optimization

## Architecture

```
Playnite (C#/.NET)
  └─ PythonBridge Plugin
      ↓ HTTP REST (localhost:5555)
Python Service (Python 3.8+)
  ├─ Recommendation Engine (scikit-learn, pandas)
  └─ Capture System (opencv, ffmpeg, OBS integration)
```

## Installation

### Prerequisites
- Python 3.8 or higher
- Playnite (with PythonBridge plugin installed)

### Quick Start

1. **Clone the repository**
   ```bash
   git clone https://github.com/yourusername/playnite-python.git
   cd playnite-python
   ```

2. **Create virtual environment**
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```

3. **Install dependencies**
   ```bash
   pip install -e .
   ```

4. **Configure environment**
   ```bash
   cp .env.example .env
   # Edit .env file as needed
   ```

5. **Start the service**
   ```bash
   python -m playnite_python serve
   ```

## CLI Usage

### Start the Service
```bash
python -m playnite_python serve --host 127.0.0.1 --port 5555
```

### Generate Recommendations
```bash
# From library JSON file
python -m playnite_python recommend generate \
    --user-id=my-user \
    --library-file=library.json \
    --output=json \
    --limit=10
```

### Test Capture System
```bash
# Start capture session
python -m playnite_python capture start \
    --game-id=test-game \
    --game-name="Test Game" \
    --backend=direct
```

## API Documentation

Once the service is running, visit:
- API Documentation: http://localhost:5555/docs
- Alternative Docs: http://localhost:5555/redoc

### Key Endpoints

#### Health Check
```http
GET /api/v1/health
```

#### Generate Recommendations
```http
POST /api/v1/recommendations/generate
Content-Type: application/json

{
  "user_id": "user-guid",
  "library": [...],
  "context": {"mood": "challenging"},
  "limit": 10
}
```

#### Start Capture Session
```http
POST /api/v1/capture/start
Content-Type: application/json

{
  "game_id": "game-guid",
  "game_name": "Dark Souls",
  "process_id": 1234,
  "settings": {
    "screenshot_hotkey": "f8",
    "video_hotkey": "f9"
  }
}
```

## Development

### Running Tests
```bash
# Run all tests
pytest

# Run with coverage
pytest --cov=src/playnite_python --cov-report=html

# Run specific test file
pytest tests/unit/test_recommendations.py -v
```

### Code Quality
```bash
# Format code
black src/ tests/

# Sort imports
isort src/ tests/

# Type checking (if mypy installed)
mypy src/
```

## Configuration

See `.env.example` for all available configuration options.

Key settings:
- `HOST` / `PORT`: Service binding address
- `CAPTURE_BASE_PATH`: Where captures are stored
- `DATABASE_URL`: SQLite or PostgreSQL connection
- `LOG_LEVEL`: Logging verbosity

## Troubleshooting

### Service won't start
- Check if port 5555 is already in use
- Verify Python version (3.8+)
- Check all dependencies are installed

### Recommendations not working
- Ensure library data is properly formatted
- Check logs for errors
- Verify ML dependencies (scikit-learn, pandas) are installed

### Capture not working
- Check hotkey permissions
- Verify game process is detected
- Ensure capture directory is writable
- Try different capture backend

## Contributing

Contributions are welcome! Please:
1. Fork the repository
2. Create a feature branch
3. Make your changes with tests
4. Submit a pull request

## License

MIT License - see LICENSE file for details

## Support

- GitHub Issues: https://github.com/yourusername/playnite-python/issues
- Documentation: https://github.com/yourusername/playnite-python/wiki

## Roadmap

- [ ] Deep learning recommendation models
- [ ] Cloud sync for recommendations
- [ ] Advanced highlight detection
- [ ] Multi-user collaborative filtering
- [ ] Integration with streaming platforms
- [ ] Mobile companion app
