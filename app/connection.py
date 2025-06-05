from redis.cluster import RedisCluster, ClusterNode
import time
import random
import string

# Correct startup nodes based on docker-compose configuration
startup_nodes = [
    ClusterNode("10.0.0.11", 7001),
    ClusterNode("10.0.0.12", 7002),
    ClusterNode("10.0.0.13", 7003)
]

print("Connecting to Redis Cluster...")
rc = RedisCluster(startup_nodes=startup_nodes, decode_responses=True, skip_full_coverage_check=True)

print("Testing basic operations...")

# Basic set/get operations
rc.set("test1", "val1")
rc.set("test2", "val2")
rc.set("test3", "val3")

print(f"test1: {rc.get('test1')}")
print(f"test2: {rc.get('test2')}")
print(f"test3: {rc.get('test3')}")

print("\n" + "="*50)
print("COMPREHENSIVE REDIS CLUSTER TESTS")
print("="*50)

# Test 1: Key Distribution Across Shards
print("\n1. Testing key distribution across shards:")
test_keys = []
for i in range(10):
    key = f"shard_test_{i}"
    value = f"value_{i}"
    rc.set(key, value)
    test_keys.append(key)
    
    # Get the node info for this key
    node_info = rc.get_node_from_key(key)
    print(f"Key '{key}' -> Node: {node_info.host}:{node_info.port}")

# Test 2: Cluster Info
print("\n2. Cluster information:")
cluster_info = rc.cluster_info()
print(f"Cluster state: {cluster_info.get('cluster_state', 'unknown')}")
print(f"Cluster slots assigned: {cluster_info.get('cluster_slots_assigned', 'unknown')}")
print(f"Cluster known nodes: {cluster_info.get('cluster_known_nodes', 'unknown')}")

# Test 3: Node Information
print("\n3. Cluster nodes:")
nodes_info = rc.cluster_nodes()
for node_id, node_info in nodes_info.items():
    # Handle both dict and ClusterNode formats
    if hasattr(node_info, 'host'):
        host = node_info.host
        port = node_info.port
        role = getattr(node_info, 'node_role', 'unknown')
    else:
        host = node_info.get('host', 'unknown')
        port = node_info.get('port', 'unknown')
        role = node_info.get('node_role', 'unknown')
    print(f"Node ID: {node_id[:8]}... | {host}:{port} | Role: {role}")

# Test 4: Hash Tag Testing (ensures keys go to same slot)
print("\n4. Testing hash tags (keys with same hash tag go to same shard):")
hash_tag_keys = ["user:{123}:name", "user:{123}:email", "user:{123}:profile"]
for key in hash_tag_keys:
    rc.set(key, f"data_for_{key}")
    node_info = rc.get_node_from_key(key)
    print(f"Key '{key}' -> Node: {node_info.host}:{node_info.port}")

# Test 5: Performance Test
print("\n5. Performance test (1000 operations):")
start_time = time.time()
for i in range(1000):
    key = f"perf_test_{i}"
    value = ''.join(random.choices(string.ascii_letters, k=10))
    rc.set(key, value)
    retrieved = rc.get(key)
    assert retrieved == value

end_time = time.time()
print(f"1000 set/get operations completed in {end_time - start_time:.2f} seconds")

# Test 6: Different Data Types
print("\n6. Testing different Redis data types:")

# Strings
rc.set("string_test", "Hello Redis Cluster!")
print(f"String: {rc.get('string_test')}")

# Lists
rc.lpush("list_test", "item1", "item2", "item3")
list_items = rc.lrange("list_test", 0, -1)
print(f"List: {list_items}")

# Sets
rc.sadd("set_test", "member1", "member2", "member3")
set_members = rc.smembers("set_test")
print(f"Set: {set_members}")

# Hashes
rc.hset("hash_test", mapping={"field1": "value1", "field2": "value2"})
hash_data = rc.hgetall("hash_test")
print(f"Hash: {hash_data}")

# Test 7: Expiration
print("\n7. Testing key expiration:")
rc.setex("expire_test", 3, "This will expire in 3 seconds")
print(f"Key before expiration: {rc.get('expire_test')}")
print("Waiting 4 seconds...")
time.sleep(4)
print(f"Key after expiration: {rc.get('expire_test')}")

# Test 8: Key Pattern Operations
print("\n8. Testing key patterns:")
pattern_keys = ["pattern:user:1", "pattern:user:2", "pattern:product:1"]
for key in pattern_keys:
    rc.set(key, f"data_{key}")

# Note: KEYS command works differently in cluster mode
print("Keys with pattern 'pattern:*':")
try:
    keys = rc.keys("pattern:*")
    print(f"Found keys: {keys}")
except Exception as e:
    print(f"Note: KEYS command in cluster mode: {e}")
    # Alternative: scan keys from each node
    all_keys = []
    for node in rc.get_nodes():
        node_keys = node.keys("pattern:*")
        all_keys.extend(node_keys)
    print(f"Found keys across all nodes: {all_keys}")

print("\n" + "="*50)
print("ALL TESTS COMPLETED!")
print("="*50)

# Cleanup test keys
print("\nCleaning up test keys...")
cleanup_patterns = ["test*", "shard_test_*", "user:*", "perf_test_*", "*_test*", "pattern:*"]
for pattern in cleanup_patterns:
    try:
        for node in rc.get_nodes():
            keys_to_delete = node.keys(pattern)
            if keys_to_delete:
                rc.delete(*keys_to_delete)
    except Exception as e:
        print(f"Cleanup warning for pattern {pattern}: {e}")

print("Cleanup completed!")