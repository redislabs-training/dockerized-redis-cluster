#!/usr/bin/env python3
"""
Redis Cluster Downtime Monitor

This script continuously monitors a Redis cluster for downtime events,
measuring the duration from first failure to successful reconnection.

ROBUST FAILURE HANDLING:
- Monitors ANY failure as downtime (configurable via STRICT_DOWNTIME_MODE)
- Tests multiple keys across different hash slots for cluster-wide availability
- Continues monitoring even during complete cluster failures
- Comprehensive exception handling prevents script from stopping
- Detailed error type tracking and consecutive failure counting
- Connection retry logic with multiple error type handling

COMPREHENSIVE TESTING:
- Tests writes, reads, list operations, and cluster info per cycle
- Uses UUID-based keys to ensure hash slot distribution
- Verifies all write operations by reading back values
- Configurable key expiration and operation frequency
"""

import time
import random
import string
import threading
import signal
import sys
import uuid
from datetime import datetime, timedelta
from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any
from redis.cluster import RedisCluster, ClusterNode
from redis.exceptions import RedisError, ConnectionError, TimeoutError, ClusterDownError

# Configuration
STARTUP_NODES = [
    ClusterNode("10.0.0.11", 7001),
    ClusterNode("10.0.0.12", 7002),  
    ClusterNode("10.0.0.13", 7003)
]

# Operation settings
OPERATION_INTERVAL = 0.1  # seconds between operations during normal monitoring
RETRY_INTERVAL = 0.1      # seconds between retry attempts during downtime
CONNECTION_TIMEOUT = 2.0  # seconds to wait for Redis operations
MAX_RETRIES = 100          # retries per operation before considering it failed
KEY_EXPIRATION = 300      # seconds (5 minutes) for key expiration
KEYS_PER_OPERATION = 5    # number of keys to test per operation cycle
STRICT_DOWNTIME_MODE = True  # if True, ANY failure = downtime; if False, majority failure = downtime

@dataclass
class DowntimeEvent:
    """Represents a single downtime event"""
    start_time: datetime
    end_time: Optional[datetime] = None
    duration: Optional[timedelta] = None
    failure_type: str = "unknown"
    operations_failed: List[str] = field(default_factory=list)
    recovery_operations: List[str] = field(default_factory=list)
    
    def complete(self, recovery_time: datetime):
        """Mark the downtime event as complete"""
        self.end_time = recovery_time
        self.duration = recovery_time - self.start_time

@dataclass 
class MonitoringStats:
    """Overall monitoring statistics"""
    total_runtime: timedelta = timedelta()
    total_downtime: timedelta = timedelta()
    downtime_events: List[DowntimeEvent] = field(default_factory=list)
    total_operations: int = 0
    failed_operations: int = 0
    
    @property
    def uptime_percentage(self) -> float:
        """Calculate uptime percentage"""
        if self.total_runtime.total_seconds() == 0:
            return 100.0
        uptime = self.total_runtime - self.total_downtime
        return (uptime.total_seconds() / self.total_runtime.total_seconds()) * 100
    
    @property
    def average_downtime(self) -> timedelta:
        """Calculate average downtime per incident"""
        if not self.downtime_events:
            return timedelta()
        completed_events = [e for e in self.downtime_events if e.duration]
        if not completed_events:
            return timedelta()
        total_seconds = sum(e.duration.total_seconds() for e in completed_events)
        return timedelta(seconds=total_seconds / len(completed_events))

class RedisClusterMonitor:
    """Monitors Redis cluster for downtime events"""
    
    def __init__(self):
        self.rc: Optional[RedisCluster] = None
        self.running = True
        self.stats = MonitoringStats()
        self.current_downtime: Optional[DowntimeEvent] = None
        self.start_time = datetime.now()
        self.consecutive_failures = 0
        self.last_error_types = []
        self.heartbeat_counter = 0
        
    def connect_to_cluster(self) -> bool:
        """Attempt to connect to Redis cluster with robust error handling"""
        try:
            # Clear any existing connection
            self.rc = None
            
            self.rc = RedisCluster(
                startup_nodes=STARTUP_NODES,
                decode_responses=True,
                skip_full_coverage_check=True,
                socket_timeout=CONNECTION_TIMEOUT,
                socket_connect_timeout=CONNECTION_TIMEOUT,
                retry_on_timeout=True,
                retry_on_error=[ConnectionError, TimeoutError, ClusterDownError]
            )
            # Test the connection with a simple operation
            self.rc.ping()
            
            # Verify cluster is functional
            info = self.rc.cluster_info()
            if info.get('cluster_state') != 'ok':
                raise Exception(f"Cluster state is not OK: {info.get('cluster_state')}")
            
            return True
            
        except (ConnectionError, TimeoutError, ClusterDownError) as e:
            print(f"Redis connection error: {type(e).__name__}: {e}")
            self.rc = None
            return False
        except Exception as e:
            print(f"Unexpected connection error: {type(e).__name__}: {e}")
            self.rc = None
            return False
    
    def show_key_distribution_sample(self):
        """Show a sample of how keys distribute across cluster nodes"""
        if not self.rc:
            return
        
        try:
            print("\n🔍 Testing key distribution across cluster nodes:")
            sample_keys = []
            node_counts = {}
            
            # Generate sample keys and see which nodes they hit
            for i in range(10):
                unique_id = str(uuid.uuid4())
                key = f"distribution_test:{unique_id}"
                try:
                    node = self.rc.get_node_from_key(key)
                    node_addr = f"{node.host}:{node.port}"
                    node_counts[node_addr] = node_counts.get(node_addr, 0) + 1
                    sample_keys.append((key[:30] + "..." if len(key) > 30 else key, node_addr))
                except Exception as e:
                    print(f"   Error getting node for key {key}: {e}")
            
            # Show distribution
            for key, node in sample_keys[:5]:  # Show first 5
                print(f"   {key} -> {node}")
            
            print(f"\n   Node distribution across {len(sample_keys)} sample keys:")
            for node, count in node_counts.items():
                percentage = (count / len(sample_keys)) * 100 if sample_keys else 0
                print(f"   {node}: {count} keys ({percentage:.1f}%)")
                
        except Exception as e:
            print(f"   Could not analyze key distribution: {e}")
    
    def perform_operation(self, operation_type: str) -> bool:
        """Perform a Redis operation with retry logic across multiple keys/hash slots"""
        if not self.rc:
            print(f"No Redis connection for {operation_type}")
            return False
            
        for attempt in range(MAX_RETRIES):
            try:
                if operation_type == "write":
                    # Test multiple keys to hit different hash slots
                    keys_values = {}
                    for i in range(KEYS_PER_OPERATION):
                        unique_id = str(uuid.uuid4())
                        key = f"monitor:write:{unique_id}"
                        value = f"val_{int(time.time())}_{i}_{uuid.uuid4().hex[:8]}"
                        keys_values[key] = value
                        self.rc.setex(key, KEY_EXPIRATION, value)
                    
                    # Verify all keys were written by reading them back
                    for key, expected_value in keys_values.items():
                        actual_value = self.rc.get(key)
                        if actual_value != expected_value:
                            raise Exception(f"Write verification failed for key {key}")
                            
                elif operation_type == "read":
                    # Generate and test multiple read keys across hash slots  
                    read_results = []
                    for i in range(KEYS_PER_OPERATION):
                        unique_id = str(uuid.uuid4())
                        key = f"monitor:read:{unique_id}"
                        value = f"read_val_{int(time.time())}_{i}_{uuid.uuid4().hex[:8]}"
                        
                        # Set the key first, then read it back
                        self.rc.setex(key, KEY_EXPIRATION, value)
                        result = self.rc.get(key)
                        
                        if result != value:
                            raise Exception(f"Read verification failed for key {key}")
                        read_results.append(result)
                    
                    # Ensure we got all expected results
                    if len(read_results) != KEYS_PER_OPERATION:
                        raise Exception(f"Expected {KEYS_PER_OPERATION} read results, got {len(read_results)}")
                        
                elif operation_type == "list_op":
                    # Test list operations across multiple keys/hash slots
                    for i in range(KEYS_PER_OPERATION):
                        unique_id = str(uuid.uuid4())
                        list_key = f"monitor:list:{unique_id}"
                        item_value = f"item_{int(time.time())}_{i}_{uuid.uuid4().hex[:8]}"
                        
                        # Push item to list
                        self.rc.lpush(list_key, item_value)
                        # Set expiration on the list
                        self.rc.expire(list_key, KEY_EXPIRATION)
                        
                        # Verify the item was added
                        list_items = self.rc.lrange(list_key, 0, 0)
                        if not list_items or list_items[0] != item_value:
                            raise Exception(f"List operation verification failed for key {list_key}")
                        
                        # Keep lists small
                        self.rc.ltrim(list_key, 0, 9)  # Keep only 10 items
                        
                elif operation_type == "cluster_info":
                    # Test cluster-level operations
                    cluster_info = self.rc.cluster_info()
                    if not cluster_info or cluster_info.get('cluster_state') != 'ok':
                        raise Exception(f"Cluster state not OK: {cluster_info.get('cluster_state', 'unknown')}")
                    
                    # Also test that we can get node information
                    nodes = self.rc.cluster_nodes()
                    if not nodes:
                        raise Exception("No cluster nodes information available")
                
                self.stats.total_operations += 1
                return True
                
            except (ConnectionError, TimeoutError, ClusterDownError) as e:
                if attempt == MAX_RETRIES - 1:
                    self.stats.failed_operations += 1
                    return False
                time.sleep(0.1)  # Brief pause between retries
            except Exception as e:
                if attempt == MAX_RETRIES - 1:
                    print(f"Operation {operation_type} failed after {MAX_RETRIES} attempts: {e}")
                    self.stats.failed_operations += 1
                    return False
                time.sleep(0.1)  # Brief pause between retries
        
        return False
    
    def detect_downtime_start(self) -> bool:
        """Check if cluster is experiencing downtime"""
        operations = ["write", "read", "list_op", "cluster_info"]
        failed_ops = []
        error_details = []
        
        for op in operations:
            try:
                if not self.perform_operation(op):
                    failed_ops.append(op)
                    error_details.append(f"{op}:operation_failed")
            except Exception as e:
                print(f"Exception during {op} operation: {type(e).__name__}: {e}")
                failed_ops.append(op)
                error_details.append(f"{op}:{type(e).__name__}")
        
        # Determine if this constitutes downtime based on configuration
        is_downtime = False
        if STRICT_DOWNTIME_MODE:
            # ANY failure = downtime
            is_downtime = len(failed_ops) > 0
        else:
            # Majority failure = downtime  
            is_downtime = len(failed_ops) >= len(operations) // 2 + 1
        
        if is_downtime:
            self.consecutive_failures += 1
            self.last_error_types = error_details
            
            if not self.current_downtime:
                self.current_downtime = DowntimeEvent(
                    start_time=datetime.now(),
                    failure_type="operation_failure",
                    operations_failed=failed_ops.copy()
                )
                mode_desc = "ANY failure" if STRICT_DOWNTIME_MODE else "majority failure"
                print(f"\n🔴 DOWNTIME DETECTED at {self.current_downtime.start_time.strftime('%H:%M:%S.%f')[:-3]}")
                print(f"Failed: {', '.join(failed_ops)} ({mode_desc} mode)")
                print(f"Error types: {', '.join(error_details)}")
                print(f"Consecutive failures: {self.consecutive_failures}")
            else:
                # Update ongoing downtime with additional failed operations
                for op in failed_ops:
                    if op not in self.current_downtime.operations_failed:
                        self.current_downtime.operations_failed.append(op)
            return True
        else:
            # Reset consecutive failures on success
            if self.consecutive_failures > 0:
                print(f"✅ Operations successful after {self.consecutive_failures} consecutive failures")
            self.consecutive_failures = 0
            self.last_error_types = []
        
        return False
    
    def attempt_recovery(self) -> bool:
        """Attempt to recover from downtime - ALL operations must succeed"""
        print("🔄 Attempting recovery...", end="", flush=True)
        
        # First try to reconnect
        try:
            if not self.connect_to_cluster():
                print(" connection failed")
                return False
        except Exception as e:
            print(f" connection exception: {e}")
            return False
        
        # Then test operations - ALL must succeed for recovery
        recovery_ops = []
        failed_ops = []
        operations = ["write", "read", "list_op", "cluster_info"]
        
        for op in operations:
            try:
                if self.perform_operation(op):
                    recovery_ops.append(op)
                else:
                    failed_ops.append(op)
            except Exception as e:
                print(f" exception in {op}: {e}")
                failed_ops.append(op)
        
        # Consider recovered ONLY if ALL operations succeed (changed from "most")
        if len(recovery_ops) == len(operations) and not failed_ops:
            if self.current_downtime:
                recovery_time = datetime.now()
                self.current_downtime.complete(recovery_time)
                self.current_downtime.recovery_operations = recovery_ops
                self.stats.downtime_events.append(self.current_downtime)
                self.stats.total_downtime += self.current_downtime.duration
                
                print(f"\n🟢 FULL RECOVERY at {recovery_time.strftime('%H:%M:%S')}")
                print(f"Downtime duration: {self.current_downtime.duration}")
                print(f"All operations recovered: {', '.join(recovery_ops)}")
                
                self.current_downtime = None
            return True
        
        if failed_ops:
            print(f" still failing: {', '.join(failed_ops)}")
        else:
            print(" partial success, retrying...")
        return False
    
    def print_status_update(self):
        """Print periodic status updates"""
        now = datetime.now()
        runtime = now - self.start_time
        
        print(f"\n📊 Status Update - {now.strftime('%H:%M:%S')}")
        print(f"Runtime: {runtime}")
        print(f"Monitoring mode: {'STRICT (ANY failure = downtime)' if STRICT_DOWNTIME_MODE else 'STANDARD (majority failure = downtime)'}")
        print(f"Total operations: {self.stats.total_operations} (testing {KEYS_PER_OPERATION} keys per operation)")
        print(f"Failed operations: {self.stats.failed_operations}")
        print(f"Keys tested: ~{self.stats.total_operations * KEYS_PER_OPERATION * 4}")  # 4 operation types
        print(f"Downtime events: {len(self.stats.downtime_events)}")
        print(f"Total downtime: {self.stats.total_downtime}")
        print(f"Uptime: {self.stats.uptime_percentage:.2f}%")
        
        if self.consecutive_failures > 0:
            print(f"⚠️ Consecutive failures: {self.consecutive_failures}")
            if self.last_error_types:
                print(f"Recent error types: {', '.join(self.last_error_types[-5:])}")  # Last 5 errors
        
        if self.stats.downtime_events:
            print(f"Average downtime per incident: {self.stats.average_downtime}")
            print("Recent downtime events:")
            for i, event in enumerate(self.stats.downtime_events[-3:]):
                print(f"  {i+1}. {event.start_time.strftime('%H:%M:%S')} - "
                      f"{event.end_time.strftime('%H:%M:%S') if event.end_time else 'ongoing'} "
                      f"({event.duration or 'ongoing'})")
        
        if self.current_downtime:
            current_downtime_duration = now - self.current_downtime.start_time
            print(f"🔴 CURRENT DOWNTIME: {current_downtime_duration}")
            print(f"   Failed operations: {', '.join(self.current_downtime.operations_failed)}")
            print(f"   Consecutive failures: {self.consecutive_failures}")
    
    def run(self):
        """Main monitoring loop"""
        print("🚀 Starting Redis Cluster Downtime Monitor")
        print(f"Cluster nodes: {[f'{node.host}:{node.port}' for node in STARTUP_NODES]}")
        print(f"Operation interval: {OPERATION_INTERVAL}s")
        print(f"Retry interval: {RETRY_INTERVAL}s")
        print(f"Keys per operation cycle: {KEYS_PER_OPERATION}")
        print(f"Key expiration: {KEY_EXPIRATION}s ({KEY_EXPIRATION//60} minutes)")
        print(f"Downtime detection: {'STRICT (ANY failure = downtime)' if STRICT_DOWNTIME_MODE else 'STANDARD (majority failure = downtime)'}")
        print(f"Max retries per operation: {MAX_RETRIES}")
        print("Press Ctrl+C to stop\n")
        
        # Initial connection
        if not self.connect_to_cluster():
            print("❌ Failed to establish initial connection. Entering recovery mode...")
            self.current_downtime = DowntimeEvent(
                start_time=datetime.now(),
                failure_type="initial_connection_failure"
            )
        else:
            print("✅ Initial connection successful")
            # Show key distribution to demonstrate cluster-wide testing
            self.show_key_distribution_sample()
        
        last_status_update = time.time()
        
        while self.running:
            try:
                current_time = time.time()
                
                # Print status every 30 seconds - ALWAYS, even during failures
                if current_time - last_status_update >= 30:
                    try:
                        self.print_status_update()
                        last_status_update = current_time
                    except Exception as e:
                        print(f"Error printing status: {e}")
                        last_status_update = current_time
                
                if self.current_downtime:
                    # In downtime - attempt recovery
                    try:
                        if self.attempt_recovery():
                            time.sleep(OPERATION_INTERVAL)
                        else:
                            time.sleep(RETRY_INTERVAL)
                    except Exception as e:
                        print(f"Error during recovery attempt: {e}")
                        time.sleep(RETRY_INTERVAL)
                else:
                    # Normal monitoring - check for downtime
                    try:
                        if self.detect_downtime_start():
                            continue  # Skip sleep, immediately try recovery
                        
                        # Show heartbeat during normal operation
                        self.heartbeat_counter += 1
                        if self.heartbeat_counter % 50 == 0:  # Every 50 cycles
                            heartbeat_symbols = ["💚", "💙", "💜", "🤍"]
                            symbol = heartbeat_symbols[(self.heartbeat_counter // 50) % len(heartbeat_symbols)]
                            print(f"{symbol} Monitoring active - {self.heartbeat_counter} cycles completed", end="\r", flush=True)
                        
                        time.sleep(OPERATION_INTERVAL)
                    except Exception as e:
                        print(f"Error during downtime detection: {e}")
                        # Assume downtime if we can't even detect properly
                        if not self.current_downtime:
                            self.current_downtime = DowntimeEvent(
                                start_time=datetime.now(),
                                failure_type="detection_failure",
                                operations_failed=["all"]
                            )
                            print(f"\n🔴 CRITICAL ERROR - Assuming downtime: {e}")
                        time.sleep(RETRY_INTERVAL)
                    
            except KeyboardInterrupt:
                print("\n⚠️ Interrupt received, shutting down gracefully...")
                break
            except Exception as e:
                print(f"CRITICAL error in main loop: {e}")
                print("Continuing monitoring despite error...")
                time.sleep(RETRY_INTERVAL)
        
        self.shutdown()
    
    def shutdown(self):
        """Clean shutdown with final statistics"""
        print("\n🛑 Shutting down monitor...")
        self.running = False
        
        # Update final stats
        self.stats.total_runtime = datetime.now() - self.start_time
        
        # Complete any ongoing downtime
        if self.current_downtime:
            self.current_downtime.complete(datetime.now())
            self.stats.downtime_events.append(self.current_downtime)
            self.stats.total_downtime += self.current_downtime.duration
        
        print("\n" + "="*60)
        print("FINAL DOWNTIME REPORT")
        print("="*60)
        print(f"Total monitoring time: {self.stats.total_runtime}")
        print(f"Total operations performed: {self.stats.total_operations}")
        print(f"Keys tested per operation: {KEYS_PER_OPERATION}")
        print(f"Total keys tested: ~{self.stats.total_operations * KEYS_PER_OPERATION * 4}")  # 4 operation types
        print(f"Key expiration time: {KEY_EXPIRATION}s ({KEY_EXPIRATION//60} minutes)")
        print(f"Failed operations: {self.stats.failed_operations}")
        print(f"Success rate: {((self.stats.total_operations - self.stats.failed_operations) / max(1, self.stats.total_operations) * 100):.2f}%")
        print(f"Total downtime events: {len(self.stats.downtime_events)}")
        print(f"Total downtime: {self.stats.total_downtime}")
        print(f"Uptime percentage: {self.stats.uptime_percentage:.4f}%")
        
        if self.stats.downtime_events:
            print(f"Average downtime per incident: {self.stats.average_downtime}")
            print(f"Longest downtime: {max(e.duration for e in self.stats.downtime_events if e.duration)}")
            print(f"Shortest downtime: {min(e.duration for e in self.stats.downtime_events if e.duration)}")
            
            print("\nDowntime Events Detail:")
            for i, event in enumerate(self.stats.downtime_events, 1):
                print(f"  {i}. Start: {event.start_time.strftime('%H:%M:%S.%f')[:-3]}")
                print(f"     End: {event.end_time.strftime('%H:%M:%S.%f')[:-3] if event.end_time else 'N/A'}")
                print(f"     Duration: {event.duration}")
                print(f"     Failed ops: {', '.join(event.operations_failed)}")
                print(f"     Recovery ops: {', '.join(event.recovery_operations)}")
                print()

def signal_handler(signum, frame):
    """Handle Ctrl+C gracefully"""
    print("\nReceived interrupt signal...")
    sys.exit(0)

def main():
    """Main entry point"""
    signal.signal(signal.SIGINT, signal_handler)
    
    monitor = RedisClusterMonitor()
    try:
        monitor.run()
    except KeyboardInterrupt:
        monitor.shutdown()

if __name__ == "__main__":
    main()
