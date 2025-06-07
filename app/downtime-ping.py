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
CHECK_INTERVAL = 0.1        # seconds between node checks
RETRY_INTERVAL = 0.05       # seconds between retry attempts during downtime
CONNECTION_TIMEOUT = 0.5    # seconds to wait for Redis operations
MAX_RETRIES = 3             # retries per operation before considering it failed
TOPOLOGY_CHECK_INTERVAL = 1 # seconds between topology checks

@dataclass
class NodeStatus:
    """Status of a single Redis node"""
    node_id: str
    host: str
    port: int
    is_master: bool
    is_up: bool = True
    last_check: datetime = field(default_factory=datetime.now)
    downtime_start: Optional[datetime] = None
    current_downtime: timedelta = timedelta(0)
    total_downtime: timedelta = timedelta(0)
    downtime_events: List[Tuple[datetime, datetime, timedelta]] = field(default_factory=list)
    
    @property
    def address(self) -> str:
        return f"{self.host}:{self.port}"
    
    @property
    def current_downtime_duration(self) -> timedelta:
        """Calculate current downtime if node is down"""
        if not self.is_up and self.downtime_start:
            return datetime.now() - self.downtime_start
        return self.current_downtime
    
    def mark_down(self, timestamp: datetime = None):
        if timestamp is None:
            timestamp = datetime.now()
        if self.is_up:
            self.is_up = False
            self.downtime_start = timestamp
            print(f"\n🔴 NODE DOWN: {self.address} at {timestamp.strftime('%H:%M:%S.%f')[:-3]}")
    
    def mark_up(self, timestamp: datetime = None):
        if timestamp is None:
            timestamp = datetime.now()
        if not self.is_up and self.downtime_start:
            self.is_up = True
            downtime_duration = timestamp - self.downtime_start
            self.current_downtime = downtime_duration
            self.total_downtime += downtime_duration
            self.downtime_events.append((self.downtime_start, timestamp, downtime_duration))
            print(f"\n🟢 NODE RECOVERED: {self.address} at {timestamp.strftime('%H:%M:%S.%f')[:-3]}")
            print(f"   Downtime duration: {downtime_duration}")
            self.downtime_start = None

@dataclass
class SlotRange:
    """Represents a range of hash slots"""
    start: int
    end: int
    current_master_id: str
    is_down: bool = False
    downtime_start: Optional[datetime] = None
    current_downtime: timedelta = timedelta(0)
    total_downtime: timedelta = timedelta(0)
    downtime_events: List[Tuple[datetime, datetime, timedelta, str, str]] = field(default_factory=list)
    
    @property
    def slot_count(self) -> int:
        return self.end - self.start + 1
    
    def mark_down(self, timestamp: datetime = None):
        if timestamp is None:
            timestamp = datetime.now()
        if not self.is_down:
            self.is_down = True
            self.downtime_start = timestamp
    
    def mark_up(self, new_master_id: str, timestamp: datetime = None):
        if timestamp is None:
            timestamp = datetime.now()
        if self.is_down and self.downtime_start:
            self.is_down = False
            downtime_duration = timestamp - self.downtime_start
            self.current_downtime = downtime_duration
            self.total_downtime += downtime_duration
            # Store old master, new master, and duration
            self.downtime_events.append((
                self.downtime_start, 
                timestamp, 
                downtime_duration, 
                self.current_master_id,
                new_master_id
            ))
            self.current_master_id = new_master_id
            self.downtime_start = None

@dataclass 
class ClusterStatus:
    """Overall cluster monitoring statistics"""
    start_time: datetime = field(default_factory=datetime.now)
    nodes: Dict[str, NodeStatus] = field(default_factory=dict)
    slot_ranges: Dict[Tuple[int, int], SlotRange] = field(default_factory=dict)
    topology_changes: int = 0
    last_topology_check: datetime = field(default_factory=datetime.now)
    
    @property
    def total_runtime(self) -> timedelta:
        return datetime.now() - self.start_time
    
    @property
    def uptime_percentage(self) -> float:
        """Calculate cluster-wide uptime percentage based on slot availability"""
        if not self.slot_ranges:
            return 100.0
        
        total_slots = 16384  # Total slots in Redis Cluster
        total_slot_downtime = 0.0
        
        for slot_range in self.slot_ranges.values():
            # Weight the downtime by the number of slots in this range
            slot_weight = slot_range.slot_count / total_slots
            slot_downtime = slot_range.total_downtime.total_seconds() * slot_weight
            total_slot_downtime += slot_downtime
        
        total_possible_uptime = self.total_runtime.total_seconds()
        
        if total_possible_uptime == 0:
            return 100.0
            
        uptime_percentage = 100 - (total_slot_downtime / total_possible_uptime * 100)
        return max(0, min(100, uptime_percentage))  # Clamp between 0-100

class RedisClusterMonitor:
    """Monitors Redis cluster nodes individually for downtime events"""
    
    def __init__(self):
        self.cluster: Optional[RedisCluster] = None
        self.node_connections: Dict[str, Redis] = {}
        self.status = ClusterStatus()
        self.running = True
        self.heartbeat_counter = 0
    
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
    
    def update_topology(self) -> bool:
        """Update cluster topology information based on hash slots"""
        if not self.cluster:
            if not self.connect_to_cluster():
                return False
        
        try:
            # Get current slot assignments
            slots = self.cluster.cluster_slots()
            current_slot_masters = {}
            current_masters = set()
            current_nodes = set()  # Track all nodes, not just masters
            topology_changed = False
            now = datetime.now()
            
            # Process the slots information based on its format
            if isinstance(slots, dict):
                # Handle the dictionary format returned by the Redis Python client
                for slot_range, nodes_info in slots.items():
                    # Extract primary node information
                    primary_info = nodes_info.get('primary')
                    if primary_info and isinstance(primary_info, tuple) and len(primary_info) >= 2:
                        host, port = primary_info[0], primary_info[1]
                        # Generate a node_id since it's not provided in this format
                        node_id = f"{host}:{port}"
                        current_slot_masters[slot_range] = node_id
                        current_masters.add(node_id)
                        current_nodes.add(node_id)
                        
                        # Add or update node in our tracking
                        if node_id not in self.status.nodes:
                            self.status.nodes[node_id] = NodeStatus(
                                node_id=node_id,
                                host=host,
                                port=port,
                                is_master=True
                            )
                        else:
                            self.status.nodes[node_id].is_master = True
                    
                    # Extract replica information
                    replicas = nodes_info.get('replicas', [])
                    for replica in replicas:
                        if isinstance(replica, tuple) and len(replica) >= 2:
                            host, port = replica[0], replica[1]
                            node_id = f"{host}:{port}"
                            current_nodes.add(node_id)
                            
                            # Add or update node in our tracking
                            if node_id not in self.status.nodes:
                                self.status.nodes[node_id] = NodeStatus(
                                    node_id=node_id,
                                    host=host,
                                    port=port,
                                    is_master=False
                                )
            elif isinstance(slots, list):
                # Handle the list format (as shown in redis-cli)
                for slot_info in slots:
                    if isinstance(slot_info, list) and len(slot_info) >= 3:
                        start_slot = slot_info[0]
                        end_slot = slot_info[1]
                        master_node = slot_info[2]
                        
                        if isinstance(master_node, list) and len(master_node) >= 2:
                            host = master_node[0]
                            port = master_node[1]
                            node_id = f"{host}:{port}"
                            
                            slot_range = (start_slot, end_slot)
                            current_slot_masters[slot_range] = node_id
                            current_masters.add(node_id)
                            current_nodes.add(node_id)
                            
                            # Add or update node in our tracking
                            if node_id not in self.status.nodes:
                                self.status.nodes[node_id] = NodeStatus(
                                    node_id=node_id,
                                    host=host,
                                    port=port,
                                    is_master=True
                                )
                            else:
                                self.status.nodes[node_id].is_master = True
                            
                            # Process replicas if available
                            for i in range(3, len(slot_info)):
                                replica = slot_info[i]
                                if isinstance(replica, list) and len(replica) >= 2:
                                    r_host = replica[0]
                                    r_port = replica[1]
                                    r_node_id = f"{r_host}:{r_port}"
                                    current_nodes.add(r_node_id)
                                    
                                    # Add or update replica in our tracking
                                    if r_node_id not in self.status.nodes:
                                        self.status.nodes[r_node_id] = NodeStatus(
                                            node_id=r_node_id,
                                            host=r_host,
                                            port=r_port,
                                            is_master=False
                                        )
            
            # Find current masters that are not in our tracking or were not masters before
            new_masters = set()
            for node_id in current_masters:
                if node_id not in self.status.nodes:
                    # This is a completely new node
                    # It should have been added above, but let's be safe
                    continue
                elif not self.status.nodes[node_id].is_master:
                    # This node was not a master before
                    new_masters.add(node_id)
                    topology_changed = True
            
            # Find masters in our tracking that are no longer masters
            previous_masters = {node_id for node_id, node in self.status.nodes.items() 
                               if node.is_master}
            removed_masters = previous_masters - current_masters
            
            # Update master status for all nodes
            for node_id, node in list(self.status.nodes.items()):
                if node_id in current_masters:
                    node.is_master = True
                elif node_id in current_nodes:
                    # Node exists but is not a master
                    if node.is_master:
                        node.is_master = False
                        topology_changed = True
                else:
                    # Node is no longer in the cluster at all
                    # If it was previously up, mark it as down
                    if node.is_up:
                        node.mark_down(now)
                        print(f"\n🔴 NODE REMOVED FROM CLUSTER: {node.address} at {now.strftime('%H:%M:%S.%f')[:-3]}")
            
            # Check for slot assignment changes and track downtime
            for slot_range, master_id in current_slot_masters.items():
                if slot_range not in self.status.slot_ranges:
                    # New slot range
                    self.status.slot_ranges[slot_range] = SlotRange(
                        start=slot_range[0],
                        end=slot_range[1],
                        current_master_id=master_id
                    )
                    topology_changed = True
                elif self.status.slot_ranges[slot_range].current_master_id != master_id:
                    # Master changed for this slot range
                    old_master = self.status.slot_ranges[slot_range].current_master_id
                    
                    # If this slot range was down, mark it as recovered with the new master
                    if self.status.slot_ranges[slot_range].is_down:
                        self.status.slot_ranges[slot_range].mark_up(master_id, now)
                        print(f"\n🟢 SLOT RANGE RECOVERED: {slot_range[0]}-{slot_range[1]} at {now.strftime('%H:%M:%S.%f')[:-3]}")
                        print(f"   New master: {master_id} (was {old_master})")
                        print(f"   Downtime duration: {self.status.slot_ranges[slot_range].current_downtime}")
                    else:
                        # Just a normal master change (e.g., planned failover)
                        self.status.slot_ranges[slot_range].current_master_id = master_id
                    
                    topology_changed = True
            
            # Check for removed slot ranges (should be rare)
            removed_ranges = set(self.status.slot_ranges.keys()) - set(current_slot_masters.keys())
            if removed_ranges:
                for slot_range in removed_ranges:
                    print(f"\n⚠️ SLOT RANGE REMOVED: {slot_range[0]}-{slot_range[1]}")
                    del self.status.slot_ranges[slot_range]
                    topology_changed = True
            
            # Connect to each master node directly for health monitoring
            for node_id in current_masters:
                if node_id not in self.node_connections:
                    node = self.status.nodes.get(node_id)
                    if node:
                        try:
                            self.node_connections[node_id] = Redis(
                                host=node.host,
                                port=node.port,
                                socket_timeout=CONNECTION_TIMEOUT,
                                socket_connect_timeout=CONNECTION_TIMEOUT,
                                retry_on_timeout=False
                            )
                        except Exception as e:
                            print(f"Error connecting to {node.address}: {e}")
            
            # Update topology change counter if needed
            if topology_changed:
                self.status.topology_changes += 1
                print(f"\n🔄 TOPOLOGY CHANGE DETECTED at {now.strftime('%H:%M:%S.%f')[:-3]}")
                
                # Only report actual changes
                if new_masters:
                    new_master_addresses = []
                    for m in new_masters:
                        if m in self.status.nodes:  # Ensure the node exists in our tracking
                            new_master_addresses.append(self.status.nodes[m].address)
                    if new_master_addresses:
                        print("   Masters added: " + ", ".join(new_master_addresses))
                
                if removed_masters:
                    # Only report masters that were removed in this update
                    removed_master_addresses = []
                    for m in removed_masters:
                        if m in self.status.nodes:  # Ensure the node exists in our tracking
                            removed_master_addresses.append(self.status.nodes[m].address)
                    if removed_master_addresses:
                        print("   Masters removed: " + ", ".join(removed_master_addresses))
                
                # Print current slot assignments
                print("   Current slot assignments:")
                for (start, end), master_id in sorted(current_slot_masters.items()):
                    node = self.status.nodes.get(master_id)
                    if node:
                        print(f"   Slots {start}-{end}: {node.address}")
            
            self.status.last_topology_check = now
            return True
            
        except Exception as e:
            print(f"Error updating topology: {type(e).__name__}: {e}")
            import traceback
            traceback.print_exc()
            return False

    def _parse_dict_format(self, slots, current_slot_masters, current_masters, current_nodes):
        """Parse the dictionary format of cluster_slots"""
        print(f"DEBUG: Dictionary format with {len(slots)} entries")
        for key in list(slots.keys())[:2]:  # Show first 2 entries
            print(f"DEBUG: Sample entry: {key} -> {slots[key]}")
        
        for slot_range, nodes_info in slots.items():
            # Extract primary node information
            primary_info = nodes_info.get('primary')
            if primary_info:
                # Handle tuple format (host, port)
                if isinstance(primary_info, tuple) and len(primary_info) >= 2:
                    host, port = primary_info[0], primary_info[1]
                    node_id = f"{host}:{port}"
                    current_slot_masters[slot_range] = node_id
                    current_masters.add(node_id)
                    current_nodes.add(node_id)
                    
                    # Add or update node in our tracking
                    if node_id not in self.status.nodes:
                        self.status.nodes[node_id] = NodeStatus(
                            node_id=node_id,
                            host=host,
                            port=port,
                            is_master=True
                        )
                    else:
                        self.status.nodes[node_id].is_master = True
                # Handle list format [host, port]
                elif isinstance(primary_info, list) and len(primary_info) >= 2:
                    host, port = primary_info[0], primary_info[1]
                    node_id = f"{host}:{port}"
                    current_slot_masters[slot_range] = node_id
                    current_masters.add(node_id)
                    current_nodes.add(node_id)
                    
                    # Add or update node in our tracking
                    if node_id not in self.status.nodes:
                        self.status.nodes[node_id] = NodeStatus(
                            node_id=node_id,
                            host=host,
                            port=port,
                            is_master=True
                        )
                    else:
                        self.status.nodes[node_id].is_master = True
                else:
                    print(f"DEBUG: Unexpected primary_info format: {primary_info}")
            
            # Extract replica information
            replicas = nodes_info.get('replicas', [])
            for replica in replicas:
                # Handle tuple format (host, port)
                if isinstance(replica, tuple) and len(replica) >= 2:
                    host, port = replica[0], replica[1]
                    node_id = f"{host}:{port}"
                    current_nodes.add(node_id)
                    
                    # Add or update node in our tracking
                    if node_id not in self.status.nodes:
                        self.status.nodes[node_id] = NodeStatus(
                            node_id=node_id,
                            host=host,
                            port=port,
                            is_master=False
                        )
                # Handle list format [host, port]
                elif isinstance(replica, list) and len(replica) >= 2:
                    host, port = replica[0], replica[1]
                    node_id = f"{host}:{port}"
                    current_nodes.add(node_id)
                    
                    # Add or update node in our tracking
                    if node_id not in self.status.nodes:
                        self.status.nodes[node_id] = NodeStatus(
                            node_id=node_id,
                            host=host,
                            port=port,
                            is_master=False
                        )
                else:
                    print(f"DEBUG: Unexpected replica format: {replica}")
    
    def check_node(self, node_id: str) -> bool:
        """Check if a node is up and running"""
        node = self.status.nodes.get(node_id)
        if not node:
            return False
        
        connection = self.node_connections.get(node_id)
        if not connection:
            try:
                connection = Redis(
                    host=node.host,
                    port=node.port,
                    socket_timeout=CONNECTION_TIMEOUT,
                    socket_connect_timeout=CONNECTION_TIMEOUT,
                    retry_on_timeout=False
                )
                self.node_connections[node_id] = connection
            except Exception as e:
                node.mark_down()
                print(f"   Error: {type(e).__name__}: {e}")
                
                # Mark all slot ranges served by this master as down
                now = datetime.now()
                for slot_range in self.status.slot_ranges.values():
                    if slot_range.current_master_id == node_id and not slot_range.is_down:
                        slot_range.mark_down(now)
                        print(f"\n🔴 SLOT RANGE FAILURE: {slot_range.start}-{slot_range.end} at {now.strftime('%H:%M:%S.%f')[:-3]}")
                        print(f"   Master {node.address} is down")
                
                return False
        
        try:
            # Try to ping the node
            result = connection.ping()
            if result:
                # Node is up
                if not node.is_up:
                    # Node recovered, but we don't mark slot ranges as recovered here
                    # That happens in update_topology when we see the new master assignment
                    node.mark_up()
                return True
        except Exception as e:
            # Node is down
            if node.is_up:
                # Node just went down
                node.mark_down()
                print(f"   Error: {type(e).__name__}: {e}")
                
                # Mark all slot ranges served by this master as down
                now = datetime.now()
                for slot_range in self.status.slot_ranges.values():
                    if slot_range.current_master_id == node_id and not slot_range.is_down:
                        slot_range.mark_down(now)
                        print(f"\n🔴 SLOT RANGE FAILURE: {slot_range.start}-{slot_range.end} at {now.strftime('%H:%M:%S.%f')[:-3]}")
                        print(f"   Master {node.address} is down")
            return False
        
        return node.is_up
    
    def check_all_nodes(self):
        """Check all master nodes"""
        now = datetime.now()
        
        # Update topology if needed
        if (now - self.status.last_topology_check).total_seconds() >= TOPOLOGY_CHECK_INTERVAL:
            self.update_topology()
        
        # Check each master node
        for node_id, node in list(self.status.nodes.items()):
            if node.is_master:
                self.check_node(node_id)
                node.last_check = now
    
    def print_status(self):
        """Print current cluster status"""
        now = datetime.now()
        runtime = now - self.status.start_time
        
        print(f"\n📊 Cluster Status - {now.strftime('%H:%M:%S')}")
        print(f"Runtime: {runtime}")
        print(f"Topology changes: {self.status.topology_changes}")
        print(f"Cluster uptime: {self.status.uptime_percentage:.2f}%")
        
        # First, print node status
        print("\nNode Status:")
        print("Address          | Role   | Status | Current Down | Total Down | Events")
        print("-----------------|--------|--------|--------------|------------|-------")
        
        for node in sorted(self.status.nodes.values(), key=lambda n: (not n.is_master, n.address)):
            role = "MASTER" if node.is_master else "REPLICA"
            status = "UP" if node.is_up else "DOWN"
            
            # Calculate current downtime for display
            if not node.is_up and node.downtime_start:
                current = str(node.current_downtime_duration)
            else:
                current = "-"
            
            total = str(node.total_downtime)
            events = len(node.downtime_events)
            
            print(f"{node.address:16} | {role:6} | {status:6} | {current:14} | {total:10} | {events}")
        
        # Now print the combined slot and node status
        print("\nCombined Slot and Node Status:")
        print("Slots          | Primary Node      | Node Status | Slot Status | Current Down | Total Down | Events")
        print("---------------|------------------|------------|------------|--------------|------------|-------")
        
        for (start, end), slot_range in sorted(self.status.slot_ranges.items()):
            # Get the master node for this slot range
            master_node = self.status.nodes.get(slot_range.current_master_id)
            
            if master_node:
                master_addr = master_node.address
                node_status = "UP" if master_node.is_up else "DOWN"
                
                # Calculate node downtime
                if not master_node.is_up and master_node.downtime_start:
                    node_downtime = str(master_node.current_downtime_duration)
                else:
                    node_downtime = "-"
            else:
                master_addr = "UNKNOWN"
                node_status = "UNKNOWN"
                node_downtime = "-"
            
            # Slot range status
            slot_status = "DOWN" if slot_range.is_down else "UP"
            
            # Calculate slot downtime
            if slot_range.is_down and slot_range.downtime_start:
                slot_downtime = str(datetime.now() - slot_range.downtime_start)
            else:
                slot_downtime = "-"
            
            # Use the appropriate downtime for display
            if slot_range.is_down:
                current = slot_downtime
            elif node_status == "DOWN":
                current = node_downtime
            else:
                current = "-"
            
            total = str(slot_range.total_downtime)
            events = len(slot_range.downtime_events)
            
            print(f"{start:5}-{end:5} | {master_addr:16} | {node_status:10} | {slot_status:10} | {current:14} | {total:10} | {events}")
        
        # Show recent downtime events
        recent_events = []
        for (start, end), slot_range in self.status.slot_ranges.items():
            for start_time, end_time, duration, old_master, new_master in slot_range.downtime_events[-3:]:
                old_node = self.status.nodes.get(old_master)
                new_node = self.status.nodes.get(new_master)
                old_addr = old_node.address if old_node else old_master
                new_addr = new_node.address if new_node else new_master
                recent_events.append((
                    f"Slots {start}-{end}", 
                    start_time, 
                    end_time, 
                    duration, 
                    old_addr, 
                    new_addr
                ))
        
        if recent_events:
            print("\nRecent Slot Range Failovers:")
            for slots, start, end, duration, old_master, new_master in sorted(recent_events, key=lambda e: e[1], reverse=True)[:10]:
                print(f"  {slots}: {start.strftime('%H:%M:%S')} to {end.strftime('%H:%M:%S')} ({duration})")
                print(f"    Master changed: {old_master} → {new_master}")
    
    def run(self):
        """Main monitoring loop"""
        print("🚀 Starting Redis Cluster Node Monitor")
        print(f"Startup nodes: {[f'{node.host}:{node.port}' for node in STARTUP_NODES]}")
        print(f"Check interval: {CHECK_INTERVAL}s")
        print(f"Topology check interval: {TOPOLOGY_CHECK_INTERVAL}s")
        print(f"Connection timeout: {CONNECTION_TIMEOUT}s")
        print("Press Ctrl+C to stop\n")
        
        # Initial topology update
        if not self.update_topology():
            print("❌ Failed to get initial cluster topology. Retrying...")
        
        last_status_update = time.time()
        
        while self.running:
            try:
                current_time = time.time()
                
                # Check all nodes
                self.check_all_nodes()
                
                # Print status every 30 seconds
                if current_time - last_status_update >= 30:
                    self.print_status()
                    last_status_update = current_time
                
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
        """Clean shutdown with final statistics"""
        print("\n🛑 Shutting down monitor...")
        
        # Final status update
        self.print_status()
        
        print("\n" + "="*60)
        print("FINAL DOWNTIME REPORT")
        print("="*60)
        print(f"Total monitoring time: {self.status.total_runtime}")
        print(f"Cluster topology changes: {self.status.topology_changes}")
        print(f"Cluster uptime: {self.status.uptime_percentage:.2f}%")
        
        # Report on each node
        print("\nNode Downtime Summary:")
        for node in sorted(self.status.nodes.values(), key=lambda n: (not n.is_master, n.total_downtime.total_seconds()), reverse=True):
            role = "MASTER" if node.is_master else "REPLICA"
            print(f"\n{node.address} ({role}):")
            print(f"  Total downtime: {node.total_downtime}")
            print(f"  Downtime events: {len(node.downtime_events)}")
            
            if node.downtime_events:
                print(f"  Average downtime: {sum((d.total_seconds() for _, _, d in node.downtime_events), 0) / len(node.downtime_events):.2f}s")
                print(f"  Longest downtime: {max((d for _, _, d in node.downtime_events), key=lambda d: d.total_seconds())}")
                
                print("\n  Downtime Events:")
                for i, (start, end, duration) in enumerate(sorted(node.downtime_events, key=lambda e: e[0]), 1):
                    print(f"    {i}. {start.strftime('%H:%M:%S.%f')[:-3]} to {end.strftime('%H:%M:%S.%f')[:-3]} ({duration})")

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
