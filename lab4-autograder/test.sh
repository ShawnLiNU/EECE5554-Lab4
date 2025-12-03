#!/bin/bash
# test.sh - Test with sudo support

DOCKER_CMD="docker"
if ! docker ps >/dev/null 2>&1; then
    DOCKER_CMD="sudo docker"
fi

echo "Lab 3 Component Tests"
echo "====================="

echo ""
echo "[Test 1] Testing emulator..."
timeout 5 $DOCKER_CMD run --rm \
  -v "$(pwd)/sensor_emulator:/emulator:ro" \
  ros:jazzy-ros-base \
  bash -c "
    apt-get update -qq > /dev/null 2>&1
    apt-get install -y python3-serial -qq > /dev/null 2>&1
    python3 /emulator/serial_emulator.py \
      -f /emulator/imu_data.txt \
      -dev imu \
      -l no
  " &

sleep 3
if kill -0 $! 2>/dev/null; then
    echo "✓ Emulator works"
    kill $! 2>/dev/null || true
else
    echo "✗ Emulator failed"
fi

echo ""
echo "Tests complete!"