#!/usr/bin/env python3
"""
Runtime grader - validates student's IMU driver
Implements ground truth conversion and compares with student's output
"""

import rclpy
from rclpy.node import Node
import json
import sys
import math
import time
import importlib
import subprocess
import re

class GraderSubscriber(Node):
    def __init__(self):
        super().__init__('grader_subscriber')
        
        self.results = {
            'sample_rate': 0,
            'parsing': 0,
            'total': 0,
            'details': []
        }
        
        self.messages_received = 0
        self.max_messages = 50
        self.test_data = []
        self.timestamps = []
        
        # Discover and import message
        self.msg_type = self.discover_and_import_message()
        if self.msg_type is None:
            self.get_logger().error("Could not import message")
            self.save_and_exit()
            return
        
        # Subscribe
        self.subscription = self.create_subscription(
            self.msg_type,
            '/imu',
            self.listener_callback,
            10
        )
        
        self.get_logger().info("Grader subscriber started...")
        self.get_logger().info(f"Will collect {self.max_messages} messages...")
        
        self.timer = self.create_timer(2.0, self.check_completion)
        self.start_time = time.time()
    
    def discover_and_import_message(self):
        """Discover and import custom message"""
        
        # Strategy 1: Query /imu topic (MOST RELIABLE)
        self.get_logger().info("Strategy 1: Querying /imu topic...")
        msg_type = self.discover_from_topic()
        if msg_type:
            return msg_type
        
        # Strategy 2: Search ros2 interface list
        self.get_logger().info("Strategy 2: Searching ros2 interface list...")
        msg_type = self.discover_from_ros2_interfaces()
        if msg_type:
            return msg_type
        
        # Strategy 3: Try common packages
        self.get_logger().info("Strategy 3: Trying common packages...")
        msg_type = self.try_common_packages()
        if msg_type:
            return msg_type
        
        self.get_logger().error("Failed to discover message")
        return None
    
    def discover_from_topic(self):
        """Query /imu topic to see what it's using"""
        try:
            result = subprocess.run(
                ['ros2', 'topic', 'info', '/imu', '-v'],
                capture_output=True, text=True, timeout=5
            )
            if result.returncode == 0:
                for line in result.stdout.split('\n'):
                    if 'Type:' in line:
                        msg_type_str = line.split('Type:')[1].strip()
                        self.get_logger().info(f"Topic uses: {msg_type_str}")
                        return self.import_from_interface_name(msg_type_str)
        except Exception as e:
            self.get_logger().debug(f"Topic query error: {e}")
        return None
    
    def discover_from_ros2_interfaces(self):
        """Query ros2 interface list for custom messages"""
        try:
            result = subprocess.run(
                ['ros2', 'interface', 'list'],
                capture_output=True, text=True, timeout=5
            )
            
            if result.returncode != 0:
                return None
            
            all_interfaces = result.stdout.strip().split('\n')
            
            # Skip standard ROS packages
            skip_packages = {
                'std_msgs', 'sensor_msgs', 'geometry_msgs', 'nav_msgs',
                'diagnostic_msgs', 'builtin_interfaces', 'action_msgs',
                'rcl_interfaces', 'lifecycle_msgs', 'tf2_msgs'
            }
            
            # Try each non-standard message
            for interface in all_interfaces:
                if not interface or '/' not in interface:
                    continue
                
                package = interface.split('/')[0]
                
                # Skip standard packages and services/actions
                if package in skip_packages:
                    continue
                if '/srv/' in interface or '/action/' in interface:
                    continue
                
                # Try to import
                self.get_logger().debug(f"Trying: {interface}")
                msg_class = self.import_from_interface_name(interface)
                if msg_class:
                    self.get_logger().info(f"✓ Using: {interface}")
                    return msg_class
            
            return None
            
        except Exception as e:
            self.get_logger().debug(f"Interface query error: {e}")
            return None
    
    def try_common_packages(self):
        """Try common package patterns"""
        packages = [
            'vn_driver.msg',
            'vn_driver.asdmsg',  # Handle non-standard directory
            'vn_driver_msgs.msg',
            'custom_msgs.msg',
            'vectornav_msgs.msg',
            'imu_msgs.msg'
        ]
        
        for pkg in packages:
            try:
                self.get_logger().debug(f"Trying package: {pkg}")
                module = importlib.import_module(pkg)
                
                # Find message class in module
                msg_class = self.find_message_in_module(module, pkg)
                if msg_class:
                    return msg_class
                    
            except ImportError:
                continue
        
        return None
    
    def find_message_in_module(self, module, module_name):
        """Find valid message class in module"""
        for attr_name in dir(module):
            if attr_name.startswith('_'):
                continue
            if attr_name in ['Metaclass', 'TYPE_CHECKING']:
                continue
                
            try:
                attr = getattr(module, attr_name)
                if isinstance(attr, type) and hasattr(attr, 'get_fields_and_field_types'):
                    if self.validate_message_structure(attr):
                        self.get_logger().info(f"✓ Found: {attr_name} in {module_name}")
                        self.results['details'].append(f"✓ Message: {module_name}.{attr_name}")
                        return attr
            except:
                continue
        
        return None
    
    def import_from_interface_name(self, interface_name):
        """
        Import from interface name - handles ANY directory name
        Examples:
          - vn_driver/msg/Vectornav → vn_driver.msg.Vectornav
          - vn_driver/asdmsg/Vectornav → vn_driver.asdmsg.Vectornav
        """
        try:
            parts = interface_name.split('/')
            
            if len(parts) == 3:
                package_name = parts[0]
                msg_directory = parts[1]
                msg_name = parts[2]
                
                module_name = f"{package_name}.{msg_directory}"
                
                self.get_logger().debug(f"Importing: {module_name}.{msg_name}")
                
                try:
                    module = importlib.import_module(module_name)
                    if hasattr(module, msg_name):
                        msg_class = getattr(module, msg_name)
                        
                        if self.validate_message_structure(msg_class):
                            self.get_logger().info(f"✓ Imported {msg_name} from {module_name}")
                            self.results['details'].append(f"✓ Message: {interface_name}")
                            return msg_class
                        
                except ImportError as e:
                    self.get_logger().debug(f"Import error: {e}")
                    
        except Exception as e:
            self.get_logger().debug(f"Parse error: {e}")
        
        return None
    
    def validate_message_structure(self, msg_class):
        """Validate message has required fields"""
        try:
            if not hasattr(msg_class, 'get_fields_and_field_types'):
                return False
            
            fields = msg_class.get_fields_and_field_types()
            
            has_header = 'header' in fields
            has_imu = 'imu' in fields
            has_mag = 'mag_field' in fields
            
            return has_header and has_imu and has_mag
            
        except:
            return False
    
    def listener_callback(self, msg):
        """Receive messages"""
        self.messages_received += 1
        
        if self.messages_received <= self.max_messages:
            self.test_data.append(msg)
            timestamp = msg.header.stamp.sec + msg.header.stamp.nanosec * 1e-9
            self.timestamps.append(timestamp)
            
            if self.messages_received % 10 == 0:
                self.get_logger().info(f"Received {self.messages_received}/{self.max_messages}")
    
    def check_completion(self):
        """Check if enough data collected"""
        elapsed = time.time() - self.start_time
        
        if self.messages_received >= self.max_messages:
            self.evaluate_and_exit()
        elif self.messages_received == 0 and elapsed > 10:
            self.results['details'].append("✗ No messages")
            self.save_and_exit()
        elif elapsed > 20:
            if self.messages_received >= 20:
                self.evaluate_and_exit()
            else:
                self.save_and_exit()
    
    def evaluate_and_exit(self):
        """Evaluate all tests"""
        if len(self.test_data) == 0:
            self.save_and_exit()
            return
        
        self.results['sample_rate'] = self.test_sample_rate()
        self.results['parsing'] = self.test_parsing_and_units()
        self.results['total'] = self.results['sample_rate'] + self.results['parsing']
        
        self.save_and_exit()
    
    def test_sample_rate(self):
        """Test sample rate (8 points)"""
        print("\n" + "="*60)
        print("[TEST 1/2] SAMPLE RATE")
        print("="*60)
        
        if len(self.timestamps) < 10:
            print("  ✗ Insufficient data")
            return 0
        
        time_diffs = [self.timestamps[i] - self.timestamps[i-1] 
                      for i in range(1, len(self.timestamps)) 
                      if self.timestamps[i] - self.timestamps[i-1] > 0]
        
        if not time_diffs:
            return 0
        
        avg_period = sum(time_diffs) / len(time_diffs)
        measured_freq = 1.0 / avg_period
        
        print(f"  Measured: {measured_freq:.2f} Hz")
        print(f"  Target: 40 Hz (acceptable: 35-45 Hz)")
        
        if 38.0 <= measured_freq <= 42.0:
            score = 8
            print(f"  ✓ EXCELLENT (8/8)")
        elif 36.0 <= measured_freq <= 44.0:
            score = 7
            print(f"  ✓ GOOD (7/8)")
        elif 35.0 <= measured_freq <= 45.0:
            score = 6
            print(f"  ✓ ACCEPTABLE (6/8)")
        else:
            score = 4 if 32 <= measured_freq <= 48 else 0
            print(f"  ⚠ Score: {score}/8")
        
        self.results['details'].append(f"Sample rate: {score}/8 ({measured_freq:.1f} Hz)")
        return score
    
    def test_parsing_and_units(self):
        """Test parsing and unit conversion (16 points)"""
        print("\n" + "="*60)
        print("[TEST 2/2] PARSING & UNIT CONVERSION")
        print("="*60)
        
        msg = self.test_data[0]
        total_score = 0
        
        # Get raw sentence
        try:
            raw_sentence = msg.raw_sentence
            if not raw_sentence or '$VNYMR' not in raw_sentence:
                print("  ✗ No valid raw_sentence")
                self.results['details'].append("✗ Parsing: 0/16")
                return 0
            
            print(f"\n  Raw: {raw_sentence[:70]}...")
            
        except AttributeError:
            print("  ✗ raw_sentence field missing")
            self.results['details'].append("✗ Parsing: 0/16")
            return 0
        
        # Parse with ground truth
        ground_truth = self.parse_vnymr_ground_truth(raw_sentence)
        if ground_truth is None:
            print("  ✗ Parse error")
            return 0
        
        print("\n" + "-"*60)
        print("  GROUND TRUTH:")
        print("-"*60)
        self.print_ground_truth(ground_truth)
        
        print("\n" + "-"*60)
        print("  STUDENT VALUES:")
        print("-"*60)
        self.print_student_values(msg)
        
        print("\n" + "-"*60)
        print("  COMPARISON:")
        print("-"*60)
        
        total_score += self.compare_gyro(ground_truth, msg)
        total_score += self.compare_accel(ground_truth, msg)
        total_score += self.compare_magnetometer(ground_truth, msg)
        total_score += self.compare_orientation(ground_truth, msg)
        
        print(f"\n  {'='*56}")
        print(f"  TOTAL: {total_score}/16")
        print(f"  {'='*56}")
        
        self.results['details'].append(f"Parsing & Units: {total_score}/16")
        return total_score
    
    def parse_vnymr_ground_truth(self, raw_sentence):
        """Ground truth parser"""
        try:
            data_str = raw_sentence.split('$VNYMR,')[1].split('*')[0]
            fields = [float(f) for f in data_str.split(',')]
            
            if len(fields) != 12:
                return None
            
            return {
                'yaw_deg': fields[0],
                'pitch_deg': fields[1],
                'roll_deg': fields[2],
                'mag_x_gauss': fields[3],
                'mag_y_gauss': fields[4],
                'mag_z_gauss': fields[5],
                'mag_x_tesla': fields[3] * 1e-4,
                'mag_y_tesla': fields[4] * 1e-4,
                'mag_z_tesla': fields[5] * 1e-4,
                'accel_x': fields[6],
                'accel_y': fields[7],
                'accel_z': fields[8],
                'gyro_x': fields[9],
                'gyro_y': fields[10],
                'gyro_z': fields[11],
                'quaternion': self.euler_to_quaternion(
                    math.radians(fields[2]),
                    math.radians(fields[1]),
                    math.radians(fields[0])
                )
            }
        except:
            return None
    
    def euler_to_quaternion(self, roll, pitch, yaw):
        """Convert Euler to quaternion"""
        cy = math.cos(yaw * 0.5)
        sy = math.sin(yaw * 0.5)
        cp = math.cos(pitch * 0.5)
        sp = math.sin(pitch * 0.5)
        cr = math.cos(roll * 0.5)
        sr = math.sin(roll * 0.5)
        
        w = cr * cp * cy + sr * sp * sy
        x = sr * cp * cy - cr * sp * sy
        y = cr * sp * cy + sr * cp * sy
        z = cr * cp * sy - sr * sp * cy
        
        return {'x': x, 'y': y, 'z': z, 'w': w}
    
    def print_ground_truth(self, gt):
        """Print ground truth"""
        q = gt['quaternion']
        print(f"  Euler: Y={gt['yaw_deg']:.3f}° P={gt['pitch_deg']:.3f}° R={gt['roll_deg']:.3f}°")
        print(f"  Quat: x={q['x']:.5f} y={q['y']:.5f} z={q['z']:.5f} w={q['w']:.5f}")
        print(f"  Mag: x={gt['mag_x_tesla']:.6e} y={gt['mag_y_tesla']:.6e} z={gt['mag_z_tesla']:.6e} T")
        print(f"  Accel: x={gt['accel_x']:.3f} y={gt['accel_y']:.3f} z={gt['accel_z']:.3f} m/s²")
        print(f"  Gyro: x={gt['gyro_x']:.6f} y={gt['gyro_y']:.6f} z={gt['gyro_z']:.6f} rad/s")
    
    def print_student_values(self, msg):
        """Print student values"""
        try:
            print(f"  Quat: x={msg.imu.orientation.x:.5f} y={msg.imu.orientation.y:.5f} z={msg.imu.orientation.z:.5f} w={msg.imu.orientation.w:.5f}")
            print(f"  Mag: x={msg.mag_field.magnetic_field.x:.6e} y={msg.mag_field.magnetic_field.y:.6e} z={msg.mag_field.magnetic_field.z:.6e}")
            print(f"  Accel: x={msg.imu.linear_acceleration.x:.3f} y={msg.imu.linear_acceleration.y:.3f} z={msg.imu.linear_acceleration.z:.3f}")
            print(f"  Gyro: x={msg.imu.angular_velocity.x:.6f} y={msg.imu.angular_velocity.y:.6f} z={msg.imu.angular_velocity.z:.6f}")
        except Exception as e:
            print(f"  Error: {e}")
    
    def compare_gyro(self, gt, msg):
        """Compare gyro (3 pts)"""
        print(f"\n  [1/4] Gyroscope:")
        try:
            sx, sy, sz = msg.imu.angular_velocity.x, msg.imu.angular_velocity.y, msg.imu.angular_velocity.z
            ex, ey, ez = abs(gt['gyro_x']-sx), abs(gt['gyro_y']-sy), abs(gt['gyro_z']-sz)
            matches = sum([ex<0.001, ey<0.001, ez<0.001])
            print(f"    Errors: X={ex:.6f} Y={ey:.6f} Z={ez:.6f}")
            score = 3 if matches==3 else (2 if matches==2 else (1 if matches==1 else 0))
            print(f"    Score: {score}/3")
            return score
        except:
            return 0
    
    def compare_accel(self, gt, msg):
        """Compare accel (3 pts)"""
        print(f"\n  [2/4] Acceleration:")
        try:
            sx, sy, sz = msg.imu.linear_acceleration.x, msg.imu.linear_acceleration.y, msg.imu.linear_acceleration.z
            ex, ey, ez = abs(gt['accel_x']-sx), abs(gt['accel_y']-sy), abs(gt['accel_z']-sz)
            matches = sum([ex<0.01, ey<0.01, ez<0.01])
            print(f"    Errors: X={ex:.3f} Y={ey:.3f} Z={ez:.3f}")
            score = 3 if matches==3 else (2 if matches==2 else (1 if matches==1 else 0))
            print(f"    Score: {score}/3")
            return score
        except:
            return 0
    
    def compare_magnetometer(self, gt, msg):
        """Compare mag (5 pts)"""
        print(f"\n  [3/4] Magnetometer:")
        try:
            sx, sy, sz = msg.mag_field.magnetic_field.x, msg.mag_field.magnetic_field.y, msg.mag_field.magnetic_field.z
            ex, ey, ez = abs(gt['mag_x_tesla']-sx), abs(gt['mag_y_tesla']-sy), abs(gt['mag_z_tesla']-sz)
            
            matches = sum([ex<1e-7, ey<1e-7, ez<1e-7])
            still_gauss = abs(gt['mag_x_gauss']-sx)<0.001
            
            print(f"    Errors: X={ex:.2e} Y={ey:.2e} Z={ez:.2e}")
            
            if matches == 3:
                score = 5
                print(f"    ✓ Converted to Tesla (5/5)")
            elif still_gauss:
                score = 0
                print(f"    ✗ Still in Gauss! (0/5)")
            else:
                score = 3 if matches>=2 else 0
                print(f"    Score: {score}/5")
            
            return score
        except:
            return 0
    
    def compare_orientation(self, gt, msg):
        """Compare orientation (5 pts)"""
        print(f"\n  [4/4] Orientation:")
        try:
            sq = msg.imu.orientation
            gq = gt['quaternion']
            
            ex = abs(gq['x']-sq.x)
            ey = abs(gq['y']-sq.y)
            ez = abs(gq['z']-sq.z)
            ew = abs(gq['w']-sq.w)
            
            norm = math.sqrt(sq.x**2 + sq.y**2 + sq.z**2 + sq.w**2)
            all_match = ex<0.01 and ey<0.01 and ez<0.01 and ew<0.01
            
            print(f"    Errors: X={ex:.5f} Y={ey:.5f} Z={ez:.5f} W={ew:.5f}")
            print(f"    Norm: {norm:.4f}")
            
            if all_match and 0.99<norm<1.01:
                score = 5
                print(f"    ✓ Quaternion correct (5/5)")
            elif norm > 10:
                score = 0
                print(f"    ✗ Still Euler angles! (0/5)")
            elif 0.99<norm<1.01:
                score = 3
                print(f"    ⚠ Valid quat, wrong values (3/5)")
            else:
                score = 0
                print(f"    ✗ Invalid (0/5)")
            
            return score
        except:
            return 0
    
    def save_and_exit(self):
        """Save and exit"""
        print("\n" + "="*60)
        print("RUNTIME RESULTS")
        print("="*60)
        print(f"Sample Rate: {self.results['sample_rate']}/8")
        print(f"Parsing:     {self.results['parsing']}/16")
        print(f"Total:       {self.results['total']}/24")
        print("="*60)
        
        with open('/tmp/grading_results.json', 'w') as f:
            json.dump(self.results, f, indent=2)
        
        print("\n✓ Saved\n")
        
        self.destroy_node()
        rclpy.shutdown()
        sys.exit(0)

def main():
    rclpy.init()
    try:
        grader = GraderSubscriber()
        rclpy.spin(grader)
    except KeyboardInterrupt:
        pass
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()
    finally:
        if rclpy.ok():
            rclpy.shutdown()

if __name__ == '__main__':
    main()