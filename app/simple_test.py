#!/usr/bin/env python3
"""
Simple Redis Cluster connectivity test
Run this to quickly verify your cluster is working
"""

from redis.cluster import RedisCluster
from redis.cluster import ClusterNode
import sys

def test_connection():
    startup_nodes = [
        ClusterNode("10.0.0.11", 7001),
        ClusterNode("10.0.0.12", 7002),
        ClusterNode("10.0.0.13", 7003)
    ]
    
    try:
        print("🔌 Connecting to Redis Cluster...")
        rc = RedisCluster(startup_nodes=startup_nodes, decode_responses=True, skip_full_coverage_check=True)
        
        print("✅ Connection successful!")
        
        # Quick health check
        print("🏥 Checking cluster health...")
        info = rc.cluster_info()
        print(f"   Cluster state: {info.get('cluster_state', 'unknown')}")
        print(f"   Nodes: {info.get('cluster_known_nodes', 'unknown')}")
        
        # Simple read/write test
        print("📝 Testing read/write...")
        rc.set("health_check", "OK")
        result = rc.get("health_check")
        
        if result == "OK":
            print("✅ Read/write test passed!")
            rc.delete("health_check")  # cleanup
            return True
        else:
            print("❌ Read/write test failed!")
            return False
            
    except Exception as e:
        print(f"❌ Connection failed: {e}")
        return False

if __name__ == "__main__":
    success = test_connection()
    sys.exit(0 if success else 1) 