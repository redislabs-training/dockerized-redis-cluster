#!/usr/bin/env python3
"""
Redis Cluster Downtime Monitor (Key-based)

This script monitors a Redis cluster for downtime events by reading keys
from each hash slot range (shard), measuring the duration from first failure 
to successful reconnection.

FEATURES:
- Creates and reads keys for each shard in the cluster
- Tracks downtime per shard rather than per individual slot
- Records precise failure timestamps and durations
- Continuous monitoring with detailed reporting
"""

import time
import signal
import sys
import uuid
from datetime import datetime, timedelta
from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any, Set, Tuple
from redis.cluster import RedisCluster, ClusterNode
from redis.client import Redis
from redis.exceptions import RedisError, ConnectionError, TimeoutError, ClusterDownError

# Configuration
STARTUP_NODES = [
    ClusterNode("10.0.0.11", 7001)
]

# Operation settings
CHECK_INTERVAL = 0.1        # seconds between key checks
RETRY_INTERVAL = 0.05       # seconds between retry attempts during downtime
CONNECTION_TIMEOUT = 0.5    # seconds to wait for Redis operations
MAX_RETRIES = 3             # retries per operation before considering it failed
KEYS_PER_SHARD = 1          # number of keys to create per shard
STATUS_UPDATE_INTERVAL = 10  # seconds between full status updates

@dataclass
class ShardStatus:
    """Status of a single shard (hash slot range)"""
    shard_id: str
    slot_range: Tuple[int, int]
    key: str
    master_address: str
    is_up: bool = True
    last_check: datetime = field(default_factory=datetime.now)
    last_value: str = ""
    downtime_start: Optional[datetime] = None
    current_downtime: timedelta = timedelta(0)
    total_downtime: timedelta = timedelta(0)
    downtime_events: List[Tuple[datetime, datetime, timedelta]] = field(default_factory=list)
    
    @property
    def slot_count(self) -> int:
        """Number of slots in this range"""
        return self.slot_range[1] - self.slot_range[0] + 1
    
    @property
    def current_total_downtime(self) -> timedelta:
        """Calculate total downtime including any ongoing downtime"""
        if self.is_up or not self.downtime_start:
            return self.total_downtime
        else:
            # Add current ongoing downtime to the total
            current_downtime = datetime.now() - self.downtime_start
            return self.total_downtime + current_downtime
    
    def mark_down(self, timestamp: datetime = None):
        if timestamp is None:
            timestamp = datetime.now()
        if self.is_up:
            self.is_up = False
            self.downtime_start = timestamp
            print(f"\n🔴 SHARD DOWN: {self.shard_id} (slots {self.slot_range[0]}-{self.slot_range[1]}) at {timestamp.strftime('%H:%M:%S.%f')[:-3]}")
            print(f"   Master: {self.master_address}")
    
    def mark_up(self, timestamp: datetime = None):
        if timestamp is None:
            timestamp = datetime.now()
        if not self.is_up and self.downtime_start:
            self.is_up = True
            downtime_duration = timestamp - self.downtime_start
            self.current_downtime = downtime_duration
            self.total_downtime += downtime_duration
            self.downtime_events.append((self.downtime_start, timestamp, downtime_duration))
            
            # Format the downtime duration with simple string formatting
            hours = int(downtime_duration.total_seconds() // 3600)
            minutes = int((downtime_duration.total_seconds() % 3600) // 60)
            seconds = downtime_duration.total_seconds() % 60
            formatted_duration = f"{hours:d}:{minutes:02d}:{seconds:.2f}"
            
            print(f"\n🟢 SHARD RECOVERED: {self.shard_id} (slots {self.slot_range[0]}-{self.slot_range[1]}) at {timestamp.strftime('%H:%M:%S.%f')[:-3]}")
            print(f"   Downtime duration: {formatted_duration}")
            self.downtime_start = None

@dataclass 
class ClusterStatus:
    """Overall cluster monitoring statistics"""
    start_time: datetime = field(default_factory=datetime.now)
    shards: Dict[str, ShardStatus] = field(default_factory=dict)
    topology_changes: int = 0
    last_topology_check: datetime = field(default_factory=datetime.now)
    
    @property
    def total_runtime(self) -> timedelta:
        return datetime.now() - self.start_time
    
    @property
    def uptime_percentage(self) -> float:
        """Calculate cluster-wide uptime percentage based on shard availability"""
        if not self.shards:
            return 100.0
        
        total_slots = 16384  # Total slots in Redis Cluster
        total_slot_downtime = 0.0
        
        for shard in self.shards.values():
            # Use current_total_downtime which includes ongoing downtime
            slot_downtime = shard.current_total_downtime.total_seconds() * shard.slot_count
            total_slot_downtime += slot_downtime
        
        total_possible_uptime = self.total_runtime.total_seconds() * total_slots
        
        if total_possible_uptime == 0:
            return 100.0
        
        uptime_percentage = 100 - (total_slot_downtime / total_possible_uptime * 100)
        return max(0, min(100, uptime_percentage))  # Clamp between 0-100

class RedisKeyMonitor:
    """Monitors Redis cluster using keys in each shard"""
    
    def __init__(self):
        self.cluster: Optional[RedisCluster] = None
        self.status = ClusterStatus()
        self.running = True
        self.heartbeat_counter = 0
        self.shard_keys = {}  # Maps shard_id to key name
    
    def format_timedelta(self, td):
        """Format a timedelta with only 2 decimal places for seconds"""
        # Get total seconds
        total_seconds = td.total_seconds()
        
        # Extract hours, minutes, seconds
        hours = int(total_seconds // 3600)
        minutes = int((total_seconds % 3600) // 60)
        seconds = total_seconds % 60
        
        # Format with only 2 decimal places for seconds
        return f"{hours:d}:{minutes:02d}:{seconds:.2f}"
    
    def connect_to_cluster(self) -> bool:
        """Connect to the Redis cluster"""
        try:
            self.cluster = RedisCluster(
                startup_nodes=STARTUP_NODES,
                decode_responses=True,
                skip_full_coverage_check=True,
                socket_timeout=CONNECTION_TIMEOUT,
                socket_connect_timeout=CONNECTION_TIMEOUT,
                retry_on_timeout=False,
                retry=0
            )
            self.cluster.ping()
            return True
        except Exception as e:
            print(f"Cluster connection error: {type(e).__name__}: {e}")
            return False
    
    def generate_key_for_slot_range(self, slot_range: Tuple[int, int]) -> str:
        """Generate a key that will hash to a slot within the given range"""
        start_slot, end_slot = slot_range
        
        # Try to find a key that hashes to a slot in this range
        # Start with the middle slot as it's most likely to be in this range
        target_slots = [
            (start_slot + end_slot) // 2,  # Middle slot
            start_slot,                    # Start slot
            end_slot,                      # End slot
            start_slot + (end_slot - start_slot) // 3,  # 1/3 through the range
            start_slot + 2 * (end_slot - start_slot) // 3  # 2/3 through the range
        ]
        
        # Try each target slot
        for target_slot in target_slots:
            # Try different key patterns
            patterns = [
                f"monitor:slot:{target_slot}",
                f"monitor:{{slot_{target_slot}}}",
                f"monitor:test:{target_slot}:{uuid.uuid4()}"
            ]
            
            for pattern in patterns:
                actual_slot = self.cluster.cluster_keyslot(pattern)
                if start_slot <= actual_slot <= end_slot:
                    return pattern
        
        # If we still can't find a key, try random keys
        for _ in range(50):
            random_key = f"monitor:{uuid.uuid4()}"
            actual_slot = self.cluster.cluster_keyslot(random_key)
            if start_slot <= actual_slot <= end_slot:
                return random_key
        
        # Last resort: try to use hash tags with the slot number
        # This is a bit of a hack but might work
        for i in range(10):
            for slot in range(start_slot, end_slot + 1, max(1, (end_slot - start_slot) // 10)):
                key = f"monitor:{{slot_{slot}_{i}}}"
                actual_slot = self.cluster.cluster_keyslot(key)
                if start_slot <= actual_slot <= end_slot:
                    return key
        
        # If all else fails, return a key with the range info
        # This will likely not hash to the correct slot, but it's better than failing
        fallback_key = f"monitor:range:{start_slot}-{end_slot}:{uuid.uuid4()}"
        print(f"  Warning: Could not generate key for slot range {start_slot}-{end_slot}. Using fallback key.")
        return fallback_key
    
    def get_cluster_shards(self) -> Dict[str, Dict]:
        """Get information about all shards in the cluster"""
        shards = {}
        
        # Get cluster slots information
        try:
            slots_info = self.cluster.cluster_slots()
            
            # Process the slots information
            for slot_range, nodes in slots_info.items():
                start_slot, end_slot = slot_range
                
                # Get primary node info
                primary_info = nodes.get('primary')
                if primary_info and isinstance(primary_info, tuple) and len(primary_info) >= 2:
                    host, port = primary_info[0], primary_info[1]
                    node_id = f"{host}:{port}"
                    
                    # Create shard entry
                    shard_id = f"shard-{start_slot}-{end_slot}"
                    shards[shard_id] = {
                        'slot_range': (start_slot, end_slot),
                        'master_address': node_id,
                        'slot_count': end_slot - start_slot + 1
                    }
            
            return shards
        except Exception as e:
            print(f"Error getting cluster shards: {e}")
            return {}
    
    def flush_all_shards(self):
        """Flush all primary shards in the cluster"""
        print("🧹 Flushing all primary shards...")
        
        # Get shard information
        shards = self.get_cluster_shards()
        if not shards:
            print("❌ Failed to get shard information")
            return
        
        # Track unique master nodes to avoid duplicate flushes
        flushed_masters = set()
        
        # Flush each primary shard
        for shard_id, shard_info in shards.items():
            master_address = shard_info['master_address']
            
            # Skip if we've already flushed this master
            if master_address in flushed_masters:
                continue
            
            try:
                # Parse host and port
                host, port = master_address.split(':')
                port = int(port)
                
                # Connect directly to the master node
                redis_node = Redis(
                    host=host,
                    port=port,
                    socket_timeout=CONNECTION_TIMEOUT,
                    socket_connect_timeout=CONNECTION_TIMEOUT,
                    decode_responses=True
                )
                
                # Flush the database
                redis_node.flushdb(asynchronous=False)
                flushed_masters.add(master_address)
                
                print(f"  Flushed shard {shard_id} at {master_address}")
                
                # Close connection
                redis_node.close()
                
            except Exception as e:
                print(f"  Error flushing shard {shard_id} at {master_address}: {e}")
        
        print(f"✅ Flushed {len(flushed_masters)} primary shards")
    
    def initialize_shard_keys(self):
        """Create keys for each shard we want to monitor"""
        print("🔑 Initializing keys for cluster shards...")
        
        # Get shard information
        shards = self.get_cluster_shards()
        if not shards:
            print("❌ Failed to get shard information")
            return
        
        print(f"Found {len(shards)} shards in the cluster")
        
        # Create keys for each shard
        for shard_id, shard_info in shards.items():
            try:
                # Get the slot range for this shard
                slot_range = shard_info['slot_range']
                
                # Generate a key that hashes to a slot in this range
                key = self.generate_key_for_slot_range(slot_range)
                
                # Verify the key actually maps to a slot in this range
                actual_slot = self.cluster.cluster_keyslot(key)
                if actual_slot < slot_range[0] or actual_slot > slot_range[1]:
                    print(f"  Warning: Generated key '{key}' maps to slot {actual_slot}, " 
                          f"which is outside the expected range {slot_range[0]}-{slot_range[1]}")
                    # Try one more time with a different approach
                    key = f"monitor:fallback:{uuid.uuid4()}"
                    actual_slot = self.cluster.cluster_keyslot(key)
                    print(f"  Fallback key '{key}' maps to slot {actual_slot}")
                
                # Set initial value with timestamp
                timestamp = datetime.now().isoformat()
                self.cluster.set(key, timestamp)
                self.shard_keys[shard_id] = key
                
                # Create shard status
                self.status.shards[shard_id] = ShardStatus(
                    shard_id=shard_id,
                    slot_range=slot_range,
                    key=key,
                    master_address=shard_info['master_address'],
                    last_value=timestamp
                )
                
                print(f"  Created key '{key}' for shard {shard_id} (slots {slot_range[0]}-{slot_range[1]}, key maps to slot {actual_slot})")
            except Exception as e:
                print(f"\nError creating key for shard {shard_id}: {e}")
        
        print(f"\n✅ Created {len(self.shard_keys)} keys across {len(shards)} shards")
    
    def check_shard(self, shard_id: str) -> bool:
        """Check if a shard is available by reading its key"""
        shard_status = self.status.shards.get(shard_id)
        if not shard_status:
            return False
        
        key = self.shard_keys.get(shard_id)
        if not key:
            return False
        
        try:
            # Try to read the key
            print(f"GET {key}")
            value = self.cluster.get(key)
            print(f"  → \"{value[:20]}...\"")
            
            # Update the key with current timestamp
            new_value = datetime.now().isoformat()
            print(f"SET {key} \"{new_value[:20]}...\"")
            self.cluster.set(key, new_value)
            print(f"  → OK")
            
            # Key is accessible
            if not shard_status.is_up:
                # Shard recovered
                shard_status.mark_up()
                shard_status.last_value = new_value
            return True
        except Exception as e:
            # Shard is down
            if shard_status.is_up:
                # Shard just went down
                shard_status.mark_down()
                print(f"   Error: {type(e).__name__}: {e}")
            return False
    
    def check_all_shards(self):
        """Check all monitored shards"""
        # Clear the current line
        print("\r" + " " * 100 + "\r", end="", flush=True)
        
        # Track successful and failed operations
        success_count = 0
        failed_count = 0
        
        # Check each shard
        for shard_id, shard_status in self.status.shards.items():
            key = self.shard_keys.get(shard_id)
            if not key:
                continue
            
            # Show current operation
            short_key = key[:25] + "..." if len(key) > 28 else key
            print(f"\rChecking shard {shard_id}: GET {short_key}", end="", flush=True)
            
            try:
                # Try to read the key
                value = self.cluster.get(key)
                
                # Update the key with current timestamp
                new_value = datetime.now().isoformat()
                
                # Show SET operation
                print(f"\rChecking shard {shard_id}: SET {short_key}", end="", flush=True)
                
                self.cluster.set(key, new_value)
                
                # Key is accessible
                if not shard_status.is_up:
                    # Shard recovered - this is important, so print a full line
                    shard_status.mark_up()
                    # The mark_up method will print the recovery message
                
                shard_status.last_value = new_value
                success_count += 1
                
            except Exception as e:
                # Shard is down
                if shard_status.is_up:
                    # Shard just went down - this is important, so print a full line
                    shard_status.mark_down()
                    print(f"\n   Error: {type(e).__name__}: {e}")
                
                failed_count += 1
        
        # Show summary of operations
        self.heartbeat_counter += 1
        if self.heartbeat_counter % 10 == 0:
            heartbeat_symbols = ["💚", "💙", "💜", "🤍"]
            symbol = heartbeat_symbols[(self.heartbeat_counter // 10) % len(heartbeat_symbols)]
            status_msg = f"{symbol} Monitoring active - {success_count}/{len(self.status.shards)} shards OK"
            print(f"\r{status_msg}", end="", flush=True)

    def print_status(self):
        """Print current cluster status"""
        print("\n" + "=" * 80)
        print(f"📊 REDIS CLUSTER KEY MONITOR STATUS - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print("=" * 80)
        
        # Overall statistics
        runtime = self.status.total_runtime
        uptime = self.status.uptime_percentage
        print(f"Runtime: {self.format_timedelta(runtime)}")
        #print(f"Cluster uptime: {uptime:.2f}%")
        print(f"Topology changes: {self.status.topology_changes}")
        print(f"Monitoring {len(self.status.shards)} shards")
        
        # Count current down shards
        down_shards = sum(1 for shard in self.status.shards.values() if not shard.is_up)
        if down_shards > 0:
            print(f"⚠️ {down_shards} shards currently unavailable!")
        
        # Define column widths
        col_widths = {
            "shard_id": 17,
            "slot_range": 15,
            "key": 18,
            "master": 15,
            "status": 6,
            "downtime": 18,
            "total": 13,
            "events": 6
        }
        
        # Show shard status with fixed-width columns
        print("\nShard Status:")
        header = (
            f"{'Shard ID':{col_widths['shard_id']}} | "
            f"{'Slot Range':{col_widths['slot_range']}} | "
            f"{'Key':{col_widths['key']}} | "
            f"{'Master':{col_widths['master']}} | "
            f"{'Status':{col_widths['status']}} | "
            f"{'Downtime':{col_widths['downtime']}} | "
            f"{'Total Downtime':{col_widths['total']}} | "
            f"{'Events':{col_widths['events']}}"
        )
        print(header)
        
        # Print separator line with correct spacing
        separator = "-" * col_widths["shard_id"] + "-|-" + \
                    "-" * col_widths["slot_range"] + "-|-" + \
                    "-" * col_widths["key"] + "-|-" + \
                    "-" * col_widths["master"] + "-|-" + \
                    "-" * col_widths["status"] + "-|-" + \
                    "-" * col_widths["downtime"] + "-|-" + \
                    "-" * col_widths["total"] + "-|-" + \
                    "-" * col_widths["events"]
        print(separator)
        
        # Sort shards by slot range start
        for shard in sorted(self.status.shards.values(), key=lambda s: s.slot_range[0]):
            status = "UP" if shard.is_up else "DOWN"
            
            # Calculate current downtime for display
            if not shard.is_up and shard.downtime_start:
                current_downtime = datetime.now() - shard.downtime_start
                current = self.format_timedelta(current_downtime)
            else:
                current = "-"
            
            # Use the current_total_downtime property which includes ongoing downtime
            total = self.format_timedelta(shard.current_total_downtime)
            events = str(len(shard.downtime_events))
            
            # Truncate key for display
            key_display = shard.key
            if len(key_display) > col_widths["key"]:
                key_display = key_display[:col_widths["key"]-2] + ".."
            
            # Format slot range
            slot_range = f"{shard.slot_range[0]}-{shard.slot_range[1]}"
            
            # Build the row with fixed-width columns
            row = (
                f"{shard.shard_id:{col_widths['shard_id']}} | "
                f"{slot_range:{col_widths['slot_range']}} | "
                f"{key_display:{col_widths['key']}} | "
                f"{shard.master_address:{col_widths['master']}} | "
                f"{status:{col_widths['status']}} | "
                f"{current:{col_widths['downtime']}} | "
                f"{total:{col_widths['total']}} | "
                f"{events:{col_widths['events']}}"
            )
            print(row)
    
    def run(self):
        """Main monitoring loop"""
        print("🚀 Starting Redis Cluster Key Monitor")
        print(f"Startup nodes: {[f'{node.host}:{node.port}' for node in STARTUP_NODES]}")
        print(f"Check interval: {CHECK_INTERVAL}s")
        print(f"Connection timeout: {CONNECTION_TIMEOUT}s")
        print("Press Ctrl+C to stop\n")
        
        # Initial connection
        if not self.connect_to_cluster():
            print("❌ Failed to connect to cluster. Retrying...")
            time.sleep(RETRY_INTERVAL)
            if not self.connect_to_cluster():
                print("❌ Could not connect to cluster. Exiting.")
                return
        
        # Flush all primary shards
        self.flush_all_shards()
        
        # Initialize keys for each shard
        self.initialize_shard_keys()
        
        last_status_update = time.time()
        
        print("\nStarting monitoring loop...")
        print(f"(Status updates will be shown every {STATUS_UPDATE_INTERVAL} seconds)")
        
        while self.running:
            try:
                current_time = time.time()
                
                # Check all shards
                self.check_all_shards()
                
                # Print status at the configured interval
                if current_time - last_status_update >= STATUS_UPDATE_INTERVAL:
                    # Print a newline to ensure status appears on its own line
                    print()
                    self.print_status()
                    last_status_update = current_time
                    print("\nMonitoring continues...")
                
                # Show heartbeat
                self.heartbeat_counter += 1
                if self.heartbeat_counter % 50 == 0:
                    heartbeat_symbols = ["💚", "💙", "💜", "🤍"]
                    symbol = heartbeat_symbols[(self.heartbeat_counter // 50) % len(heartbeat_symbols)]
                    print(f"{symbol} Monitoring active - {self.heartbeat_counter} cycles", end="\r", flush=True)
                
                time.sleep(CHECK_INTERVAL)
                
            except KeyboardInterrupt:
                print("\n⚠️ Interrupt received, shutting down gracefully...")
                break
            except Exception as e:
                print(f"Error in main loop: {e}")
                time.sleep(RETRY_INTERVAL)
        
        self.shutdown()
    
    def shutdown(self):
        """Clean up resources and print final status"""
        print("\n🛑 Shutting down Redis Cluster Key Monitor")
        self.running = False
        
        # Print final status
        self.print_status()
        
        # Clean up keys if needed
        try:
            if self.cluster:
                print("\nCleaning up monitoring keys...")
                for key in self.shard_keys.values():
                    try:
                        self.cluster.delete(key)
                    except:
                        pass
        except:
            pass
        
        print("\n👋 Goodbye!")

def signal_handler(signum, frame):
    """Handle Ctrl+C gracefully"""
    print("\nReceived interrupt signal...")
    sys.exit(0)

if __name__ == "__main__":
    # Register signal handler
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    # Start monitoring
    monitor = RedisKeyMonitor()
    monitor.run()

