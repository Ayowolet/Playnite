#!/bin/bash
# Integration test script for Playnite Python service

set -e  # Exit on error

echo "========================================="
echo "Playnite Python Integration Tests"
echo "========================================="
echo ""

# Colors
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Test counter
TESTS_PASSED=0
TESTS_FAILED=0

# Function to run test
run_test() {
    local test_name=$1
    local test_command=$2

    echo -n "Testing: $test_name... "

    if eval "$test_command" > /dev/null 2>&1; then
        echo -e "${GREEN}✓ PASS${NC}"
        TESTS_PASSED=$((TESTS_PASSED + 1))
    else
        echo -e "${RED}✗ FAIL${NC}"
        TESTS_FAILED=$((TESTS_FAILED + 1))
    fi
}

# Check if virtual environment is activated
if [ -z "$VIRTUAL_ENV" ]; then
    echo -e "${YELLOW}Warning: Virtual environment not activated${NC}"
    echo "Activating virtual environment..."

    if [ -f "venv/bin/activate" ]; then
        source venv/bin/activate
    elif [ -f "venv/Scripts/activate" ]; then
        source venv/Scripts/activate
    else
        echo -e "${RED}Error: Virtual environment not found${NC}"
        echo "Please run: python -m venv venv && source venv/bin/activate"
        exit 1
    fi
fi

echo "[1] Starting Python service in background..."
python -m playnite_python serve > /dev/null 2>&1 &
SERVICE_PID=$!
echo "Service PID: $SERVICE_PID"

# Wait for service to start
echo "Waiting for service to start..."
sleep 3

# Test 1: Health check
run_test "Health check endpoint" \
    "curl -s http://localhost:5555/api/v1/health | grep -q 'healthy'"

# Test 2: Root endpoint
run_test "Root endpoint" \
    "curl -s http://localhost:5555/ | grep -q 'Playnite Python'"

# Test 3: Test recommendations endpoint
run_test "Test recommendations endpoint" \
    "curl -s http://localhost:5555/api/v1/recommendations/test | grep -q 'recommendations'"

# Test 4: CLI recommendation generation
run_test "CLI recommendation generation" \
    "python -m playnite_python recommend generate \
        --user-id=test-user \
        --library-file=tests/fixtures/sample_game_library.json \
        --output=json | grep -q 'game_id'"

# Test 5: CLI capture storage command
run_test "CLI capture storage command" \
    "python -m playnite_python capture storage"

# Test 6: Generate recommendations via API
run_test "Generate recommendations via API" \
    "curl -s -X POST http://localhost:5555/api/v1/recommendations/generate \
        -H 'Content-Type: application/json' \
        -d @tests/fixtures/sample_game_library_api.json | grep -q 'recommendations'"

# Test 7: Start capture session (will fail without proper setup, but tests API)
echo -n "Testing: Start capture session API... "
CAPTURE_RESPONSE=$(curl -s -X POST http://localhost:5555/api/v1/capture/start \
    -H 'Content-Type: application/json' \
    -d '{"game_id":"test","game_name":"Test","process_id":12345}' || echo "failed")

if echo "$CAPTURE_RESPONSE" | grep -q "session_id"; then
    echo -e "${GREEN}✓ PASS${NC}"
    TESTS_PASSED=$((TESTS_PASSED + 1))
    SESSION_ID=$(echo "$CAPTURE_RESPONSE" | grep -o '"session_id":"[^"]*"' | cut -d'"' -f4)
    echo "  Session ID: $SESSION_ID"

    # Test 8: Stop capture session
    run_test "Stop capture session" \
        "curl -s -X POST http://localhost:5555/api/v1/capture/stop/$SESSION_ID | grep -q 'stopped'"
else
    echo -e "${RED}✗ FAIL${NC}"
    TESTS_FAILED=$((TESTS_FAILED + 1))
fi

# Test 9: Storage usage endpoint
run_test "Storage usage endpoint" \
    "curl -s http://localhost:5555/api/v1/storage/usage | grep -q 'total_size_bytes'"

# Test 10: List active sessions
run_test "List active capture sessions" \
    "curl -s http://localhost:5555/api/v1/capture/sessions | grep -q 'sessions'"

# Cleanup
echo ""
echo "Cleaning up..."
kill $SERVICE_PID 2>/dev/null || true
sleep 1

# Summary
echo ""
echo "========================================="
echo "Test Results"
echo "========================================="
echo -e "Passed: ${GREEN}$TESTS_PASSED${NC}"
echo -e "Failed: ${RED}$TESTS_FAILED${NC}"
echo "Total:  $((TESTS_PASSED + TESTS_FAILED))"

if [ $TESTS_FAILED -eq 0 ]; then
    echo ""
    echo -e "${GREEN}All tests passed! ✓${NC}"
    exit 0
else
    echo ""
    echo -e "${RED}Some tests failed ✗${NC}"
    exit 1
fi
