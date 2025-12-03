#!/bin/bash
# grade.sh - Automated grader with auto-build
# Builds Docker image if needed, then runs autograder

set -e

# Check if workspace path is provided
if [ $# -eq 0 ]; then
    echo "Usage: ./grade.sh <student_workspace_path>"
    echo ""
    echo "Example:"
    echo "  ./grade.sh ~/Desktop/lab4/lab4_ws"
    echo "  ./grade.sh /path/to/workspace"
    exit 1
fi

STUDENT_WS=$1

# Check if workspace exists
if [ ! -d "$STUDENT_WS" ]; then
    echo "Error: Workspace directory not found: $STUDENT_WS"
    exit 1
fi

# Resolve absolute paths
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
STUDENT_WS_ABS="$(cd "$STUDENT_WS" && pwd)"

# Check if we need sudo for docker
DOCKER_CMD="docker"
if ! docker ps >/dev/null 2>&1; then
    echo "Using sudo for docker commands"
    DOCKER_CMD="sudo docker"
fi

# Clean build artifacts (handling permission issues)
echo "============================================================"
echo "Cleaning workspace..."
echo "============================================================"

CLEANED=false

# Try to remove directories
for dir in build install log; do
    if [ -d "$STUDENT_WS_ABS/$dir" ]; then
        echo "Removing $dir/"
        
        # Try normal removal first
        if rm -rf "$STUDENT_WS_ABS/$dir" 2>/dev/null; then
            CLEANED=true
        else
            # If permission denied, use sudo
            echo "  (using sudo for $dir/)"
            sudo rm -rf "$STUDENT_WS_ABS/$dir"
            CLEANED=true
        fi
    fi
done

if [ "$CLEANED" = true ]; then
    echo "✓ Workspace cleaned"
else
    echo "✓ No build artifacts to clean"
fi
echo ""

echo "============================================================"
echo "Lab 4 Autograder"
echo "============================================================"
echo "Student workspace: $STUDENT_WS_ABS"
echo ""

# Check if custom image exists, build if needed
if $DOCKER_CMD image inspect lab4-grader >/dev/null 2>&1; then
    echo "✓ Using existing lab4-grader image"
    IMAGE="lab4-grader"
    INSTALL_CMD=""
else
    echo "lab4-grader image not found"
    
    # Check if Dockerfile exists
    if [ -f "$SCRIPT_DIR/Dockerfile" ]; then
        echo "Building lab4-grader image..."
        echo ""
        
        $DOCKER_CMD build -t lab4-grader "$SCRIPT_DIR"
        
        if [ $? -eq 0 ]; then
            echo ""
            echo "✓ Build complete!"
            echo ""
            IMAGE="lab4-grader"
            INSTALL_CMD=""
        else
            echo ""
            echo "✗ Build failed, falling back to base image"
            IMAGE="ros:jazzy-ros-base"
            INSTALL_CMD="apt-get update -qq > /dev/null 2>&1 && apt-get install -y python3-serial -qq > /dev/null 2>&1 &&"
        fi
    else
        echo "No Dockerfile found, using ros:jazzy-ros-base"
        IMAGE="ros:jazzy-ros-base"
        INSTALL_CMD="apt-get update -qq > /dev/null 2>&1 && apt-get install -y python3-serial -qq > /dev/null 2>&1 &&"
    fi
fi

echo "Using image: $IMAGE"
echo ""

# Cleanup function
cleanup() {
    echo ""
    echo "Cleaning up Docker containers..."
    $DOCKER_CMD ps -q --filter "ancestor=$IMAGE" | xargs -r $DOCKER_CMD kill 2>/dev/null || true
}

trap cleanup EXIT INT TERM

# Run autograder
echo "Starting autograder..."
echo ""

$DOCKER_CMD run --rm \
  -v "$STUDENT_WS_ABS:/workspace/student" \
  -v "$SCRIPT_DIR/autograder.py:/workspace/autograder.py:ro" \
  -v "$SCRIPT_DIR/test_subscriber.py:/workspace/test_subscriber.py:ro" \
  -v "$SCRIPT_DIR/sensor_emulator:/emulator:ro" \
  -v "$SCRIPT_DIR:/output" \
  "$IMAGE" \
  bash -c "
    $INSTALL_CMD
    python3 /workspace/autograder.py /workspace/student
  "

echo ""
echo "============================================================"
if [ -f "$SCRIPT_DIR/grading_report.json" ]; then
  echo "Grading Report:"
  cat "$SCRIPT_DIR/grading_report.json"
else
  echo "⚠ No report generated"
fi
echo "============================================================"
```

**Key changes:**

1. **Added smart cleanup** - Tries regular `rm` first, falls back to `sudo` if needed
2. **Shows what's being cleaned** - Indicates when sudo is used
3. **Handles permission errors** - No more "Permission denied" failures

**Output:**
```
============================================================
Cleaning workspace...
============================================================
Removing build/
  (using sudo for build/)
Removing install/
  (using sudo for install/)
Removing log/
✓ Workspace cleaned