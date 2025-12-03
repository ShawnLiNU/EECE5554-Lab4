#!/usr/bin/env python3
"""
Lab 4 Autograder - Complete Implementation
Checks all 40 driver points according to lab requirements
"""

import subprocess
import time
import os
import sys
import signal
import json
import atexit
import re
import xml.etree.ElementTree as ET
from pathlib import Path
import select

# Global process tracking
EMU_PROC = None
DRIVER_PROC = None

def cleanup():
    """Cleanup all processes"""
    global EMU_PROC, DRIVER_PROC
    
    print("\n" + "="*60)
    print("[CLEANUP] Stopping all processes...")
    print("="*60)
    
    if DRIVER_PROC:
        print("[CLEANUP] Stopping student driver...")
        try:
            os.killpg(os.getpgid(DRIVER_PROC.pid), signal.SIGTERM)
            DRIVER_PROC.wait(timeout=2)
            print("[CLEANUP] ✓ Driver stopped")
        except:
            try:
                DRIVER_PROC.kill()
                print("[CLEANUP] ✓ Driver killed")
            except:
                print("[CLEANUP] Driver already stopped")
    
    if EMU_PROC:
        print("[CLEANUP] Stopping emulator...")
        try:
            os.killpg(os.getpgid(EMU_PROC.pid), signal.SIGTERM)
            EMU_PROC.wait(timeout=2)
            print("[CLEANUP] ✓ Emulator stopped")
        except:
            try:
                EMU_PROC.kill()
                print("[CLEANUP] ✓ Emulator killed")
            except:
                print("[CLEANUP] Emulator already stopped")
    
    print("[CLEANUP] Done\n")

atexit.register(cleanup)
signal.signal(signal.SIGINT, lambda s, f: sys.exit(0))
signal.signal(signal.SIGTERM, lambda s, f: sys.exit(0))

def log(msg):
    print(f"[AUTOGRADER] {msg}")

def find_msg_file(ws_path):
    """
    Find a custom .msg file ANYWHERE in the workspace
    Prefers files in 'msg/' directories but will find any .msg file
    """
    ws_path = Path(ws_path)

    # Collect ALL .msg files
    all_msg_files = list(ws_path.rglob('**/*.msg'))
    
    if not all_msg_files:
        return None
    
    print(f"  Found {len(all_msg_files)} .msg file(s) in workspace:")
    for f in all_msg_files:
        print(f"    - {f.relative_to(ws_path)}")

    def is_in_msg_dir(p: Path) -> bool:
        """Check if file is in a directory named 'msg'"""
        return 'msg' in [part.lower() for part in p.parts]

    def matches_expected_fields(p: Path) -> bool:
        """Check if .msg file has required fields"""
        try:
            content = p.read_text(encoding='utf-8', errors='ignore')
        except Exception:
            return False

        has_header = re.search(r'(?:std_msgs/)?Header\s+\w+', content, re.IGNORECASE) is not None
        has_imu = re.search(r'sensor_msgs/Imu\s+\w+', content) is not None
        has_mag = re.search(r'sensor_msgs/MagneticField\s+\w+', content) is not None
        has_string = re.search(r'string\s+\w+', content) is not None
        return has_header and has_imu and has_mag and has_string

    # 1) Prefer files in 'msg/' directories that match expected fields
    in_msg_dir = [p for p in all_msg_files if is_in_msg_dir(p)]
    for p in in_msg_dir:
        if matches_expected_fields(p):
            return p

    # 2) Any file that matches expected fields (even if not in msg/)
    for p in all_msg_files:
        if matches_expected_fields(p):
            # Warn if not in proper msg/ directory
            if not is_in_msg_dir(p):
                print(f"  ⚠ WARNING: {p.name} is not in a 'msg/' directory!")
                print(f"    ROS2 expects messages in: src/<package>/msg/")
                print(f"    Found in: {p.parent.name}/")
                print(f"    This may cause build/import failures!")
            return p

    # 3) Fallback to first file in msg/ directory
    if in_msg_dir:
        return in_msg_dir[0]

    # 4) Last resort: any .msg file
    print(f"  ⚠ WARNING: No .msg files found in standard 'msg/' directories")
    return all_msg_files[0]

def check_message_structure(ws_path):
    """Check message structure (8 points) - finds any .msg file"""
    print("\n[STATIC CHECK 1/2] Checking message structure...")
    
    msg_file = find_msg_file(ws_path)
    
    if not msg_file:
        print("  ✗ No .msg file found in workspace")
        return 0, "✗ No .msg file found (0/8)"
    
    print(f"  Found: {msg_file.name} at {msg_file}")
    
    with open(msg_file, 'r') as f:
        content = f.read()
    
    score = 0
    
    if re.search(r'Header\s+header', content, re.IGNORECASE):
        score += 2
        print("  ✓ Header field found")
    else:
        print("  ✗ Header field missing")
    
    if re.search(r'sensor_msgs/Imu\s+\w+', content):
        score += 2
        print("  ✓ sensor_msgs/Imu field found")
    else:
        print("  ✗ sensor_msgs/Imu field missing")
    
    if re.search(r'sensor_msgs/MagneticField\s+\w+', content):
        score += 2
        print("  ✓ sensor_msgs/MagneticField field found")
    else:
        print("  ✗ sensor_msgs/MagneticField field missing")
    
    if re.search(r'string\s+\w+', content):
        score += 2
        print("  ✓ String field found")
    else:
        print("  ✗ String field missing")
    
    return score, f"Message structure: {score}/8 pts"

def find_launch_file(ws_path):
    """Find any Python launch file in the workspace.

    Preference order:
    1) Files under any `launch/` directory with 'launch' in filename.
    2) Any file with 'launch' in filename.
    """
    ws_path = Path(ws_path)

    candidates = list(ws_path.rglob('**/launch/*launch*.py'))
    if not candidates:
        candidates = list(ws_path.rglob('**/*launch*.py'))

    candidates = [f for f in candidates if f.suffix == '.py']
    return candidates[0] if candidates else None

def derive_package_name_from_path(path: Path) -> str:
    """Derive ROS 2 package name by locating nearest package.xml and reading <name>.
    Fallback to directory name above `launch/` if parsing fails.
    """
    if not isinstance(path, Path):
        path = Path(path)

    # Walk up to find package.xml
    for parent in [path] + list(path.parents):
        pkg_xml = parent / 'package.xml'
        if pkg_xml.exists():
            try:
                tree = ET.parse(str(pkg_xml))
                root = tree.getroot()
                name_elem = root.find('name')
                if name_elem is not None and name_elem.text:
                    return name_elem.text.strip()
            except Exception:
                pass

    # Heuristic: if path is .../<pkg>/launch/<file>.py, take <pkg>
    try:
        if path.parent.name == 'launch':
            return path.parent.parent.name
    except Exception:
        pass

    # Last resort: use immediate parent directory name
    return path.parent.name

def check_launch_file(ws_path):
    """Check launch file (10 points) - finds any file with 'launch' in name"""
    print("\n[STATIC CHECK 2/2] Checking launch file...")
    
    launch_file = find_launch_file(ws_path)
    
    if not launch_file:
        print("  ✗ No launch file found in workspace")
        return 0, "Launch file: 0/10 pts", None
    
    score = 0
    print(f"  ✓ Launch file found: {launch_file.name}")
    score += 5
    
    with open(launch_file, 'r', encoding='utf-8', errors='ignore') as f:
        content = f.read()
    
    if 'port' in content.lower():
        print("  ✓ Port parameter found")
        score += 5
    else:
        print("  ✗ Port parameter missing")
    
    return score, f"Launch file: {score}/10 pts", launch_file

def build_workspace(ws_path):
    """Build student workspace"""
    print("\n" + "="*60)
    print("[BUILD] Building workspace...")
    print("="*60)
    
    cmd = f"""
    source /opt/ros/jazzy/setup.bash &&
    cd {ws_path} &&
    colcon build --symlink-install 2>&1
    """
    
    result = subprocess.run(
        cmd, shell=True, executable='/bin/bash',
        capture_output=True, text=True, timeout=180
    )
    
    if result.returncode == 0:
        print("✓ Build successful\n")
        return True
    else:
        print("✗ Build failed:")
        print(result.stdout[-1000:])
        if result.stderr:
            print(result.stderr[-1000:])
        return False

def start_emulator():
    """Start emulator with looping"""
    global EMU_PROC
    
    print("\n" + "="*60)
    print("[RUNTIME] Starting emulator...")
    print("="*60)
    
    cmd = [
        'python3', '-u', '/emulator/serial_emulator.py',
        '-f', '/emulator/imu_data.txt',
        '-dev', 'imu',
        '-l', 'yes'
    ]
    
    print(f"Command: {' '.join(cmd)}")
    
    EMU_PROC = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
        preexec_fn=os.setsid
    )
    
    print("Waiting for emulator to initialize...")
    
    port = None
    timeout = 10
    start = time.time()
    
    while time.time() - start < timeout:
        if EMU_PROC.poll() is not None:
            print("✗ Emulator process died!")
            return None

        rlist, _, _ = select.select([EMU_PROC.stdout], [], [], 0.2)
        if not rlist:
            continue

        line = EMU_PROC.stdout.readline()
        if not line:
            continue

        print(f"  [EMU] {line.strip()}")

        if 'The Pseudo device address:' in line:
            port = line.strip().split(':', 1)[1].strip()
            break
    
    if port:
        print(f"✓ Emulator running on {port}")
        time.sleep(1)
        if EMU_PROC.poll() is None:
            print("✓ Emulator is running\n")
            return port
    
    return None

def start_driver(ws_path, port, launch_file):
    """Start student driver with discovered launch file"""
    global DRIVER_PROC
    
    print("\n" + "="*60)
    print("[RUNTIME] Starting student driver...")
    print("="*60)
    print(f"Port: {port}")
    print(f"Launch file: {launch_file.name}")
    
    # Get the package name and launch file name dynamically
    # launch_file is a Path object like: /path/to/ws/src/<pkg>/launch/<file>.py
    launch_filename = launch_file.stem
    package_name = derive_package_name_from_path(launch_file)

    cmd = f"""
    source /opt/ros/jazzy/setup.bash &&
    source {ws_path}/install/setup.bash &&
    ros2 launch {package_name} {launch_filename}.py port:={port} 2>&1
    """

    print(f"Command: ros2 launch {package_name} {launch_filename}.py port:={port}")
    
    DRIVER_PROC = subprocess.Popen(
        cmd, shell=True, executable='/bin/bash',
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        preexec_fn=os.setsid
    )
    
    print("Waiting for driver to start...")
    time.sleep(4)
    
    if DRIVER_PROC.poll() is None:
        print(f"✓ Driver running (PID: {DRIVER_PROC.pid})")
        
        print("\nDriver output:")
        shown = 0
        start = time.time()
        while shown < 5 and (time.time() - start) < 2:
            rlist, _, _ = select.select([DRIVER_PROC.stdout], [], [], 0.2)
            if not rlist:
                continue
            line = DRIVER_PROC.stdout.readline()
            if line:
                print(f"  [DRIVER] {line.strip()}")
                shown += 1
        
        print()
        return True
    else:
        print("✗ Driver failed to start")
        output = DRIVER_PROC.stdout.read() if DRIVER_PROC.stdout else ""
        print("Output:", output[-500:])
        DRIVER_PROC = None
        return False

def run_grader(ws_path):
    """Run grader subscriber for runtime checks"""
    print("\n" + "="*60)
    print("[RUNTIME] Running grader subscriber...")
    print("="*60)
    
    # CRITICAL: Must source student workspace to import their message!
    cmd = f"""
    source /opt/ros/jazzy/setup.bash &&
    source {ws_path}/install/setup.bash &&
    timeout 25 python3 /workspace/test_subscriber.py
    """
    
    print("Listening for messages on /imu topic...")
    print("Measuring sample rate and validating data...\n")
    
    try:
        result = subprocess.run(
            cmd, shell=True, executable='/bin/bash',
            capture_output=True, text=True, timeout=30
        )
        
        print(result.stdout)
        if result.stderr:
            print("Warnings:", result.stderr)
        
        # Load results
        try:
            with open('/tmp/grading_results.json', 'r') as f:
                return json.load(f)
        except FileNotFoundError:
            print("⚠ No grading results file found")
            return {'sample_rate': 0, 'parsing': 0, 'total': 0}
        except json.JSONDecodeError as e:
            print(f"⚠ Could not parse grading results: {e}")
            return {'sample_rate': 0, 'parsing': 0, 'total': 0}
            
    except subprocess.TimeoutExpired:
        print("⚠ Grader timeout - no messages received")
        return {'sample_rate': 0, 'parsing': 0, 'total': 0}

def main():
    if len(sys.argv) < 2:
        print("Usage: python3 autograder.py <workspace_path>")
        sys.exit(1)
    
    ws_path = sys.argv[1]
    
    print("="*60)
    print("LAB 4 AUTOGRADER - DRIVER EVALUATION (40 points)")
    print("="*60)
    print(f"Workspace: {ws_path}\n")
    
    results = {
        'message_structure': {'score': 0, 'max': 8},
        'launch_file': {'score': 0, 'max': 10},
        'sample_rate': {'score': 0, 'max': 8},
        'parsing': {'score': 0, 'max': 16}
    }
    
    launch_file_path = None
    
    try:
        # STATIC CHECKS (18 points)
        print("\n" + "="*60)
        print("STATIC CODE ANALYSIS")
        print("="*60)
        
        # 1. Message structure (8 pts)
        msg_score, msg_detail = check_message_structure(ws_path)
        results['message_structure']['score'] = msg_score
        
        # 2. Launch file (10 pts)
        launch_score, launch_detail, launch_file_path = check_launch_file(ws_path)
        results['launch_file']['score'] = launch_score
        
        static_total = msg_score + launch_score
        print(f"\n{'='*60}")
        print(f"STATIC TOTAL: {static_total}/18 points")
        print(f"{'='*60}")
        
        # BUILD
        if not build_workspace(ws_path):
            log("Build failed - cannot run runtime tests")
            runtime_results = {'sample_rate': 0, 'parsing': 0, 'total': 0}
        else:
            # RUNTIME CHECKS (24 points)
            print("\n" + "="*60)
            print("RUNTIME TESTING")
            print("="*60)
            
            port = start_emulator()
            if not port:
                log("Emulator failed - cannot run runtime tests")
                runtime_results = {'sample_rate': 0, 'parsing': 0, 'total': 0}
            elif not launch_file_path:
                log("No launch file found - cannot start driver")
                runtime_results = {'sample_rate': 0, 'parsing': 0, 'total': 0}
            else:
                if not start_driver(ws_path, port, launch_file_path):
                    log("Driver failed to start - no runtime points")
                    runtime_results = {'sample_rate': 0, 'parsing': 0, 'total': 0}
                else:
                    # Run grader WITH STUDENT WORKSPACE SOURCED
                    runtime_results = run_grader(ws_path)
        
        results['sample_rate']['score'] = runtime_results.get('sample_rate', 0)
        results['parsing']['score'] = runtime_results.get('parsing', 0)
        
    except Exception as e:
        print(f"\n✗ Autograder error: {e}")
        import traceback
        traceback.print_exc()
    
    finally:
        pass
    
    # FINAL REPORT
    print("\n" + "="*60)
    print("FINAL GRADING REPORT")
    print("="*60)
    
    print("\n📋 BREAKDOWN BY CATEGORY:\n")
    
    print("STATIC CHECKS:")
    print(f"  1. Message Structure:     {results['message_structure']['score']:2d}/8  pts")
    print(f"  2. Launch File:           {results['launch_file']['score']:2d}/10 pts")
    static_total = results['message_structure']['score'] + results['launch_file']['score']
    print(f"  {'─'*40}")
    print(f"  Static Subtotal:          {static_total:2d}/18 pts")
    
    print("\nRUNTIME CHECKS:")
    print(f"  3. Sample Rate (40 Hz):   {results['sample_rate']['score']:2d}/8  pts")
    print(f"  4. Parsing & Units:       {results['parsing']['score']:2d}/16 pts")
    runtime_total = results['sample_rate']['score'] + results['parsing']['score']
    print(f"  {'─'*40}")
    print(f"  Runtime Subtotal:         {runtime_total:2d}/24 pts")
    
    total = static_total + runtime_total
    print(f"\n{'='*60}")
    print(f"TOTAL SCORE: {total}/42 points")
    print(f"{'='*60}\n")
    
    report = {
        'breakdown': results,
        'static_total': static_total,
        'runtime_total': runtime_total,
        'total': total,
        'max': 42
    }
    
    with open('/output/grading_report.json', 'w') as f:
        json.dump(report, f, indent=2)
    
    print("✓ Report saved to grading_report.json\n")

if __name__ == '__main__':
    main()
