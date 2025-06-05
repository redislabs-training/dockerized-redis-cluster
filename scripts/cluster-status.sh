#!/bin/sh

echo "🔍 Redis Cluster Status Check"
echo "=============================="

# Default connection
REDIS_HOST=${REDIS_HOST:-10.0.0.11}
REDIS_PORT=${REDIS_PORT:-7001}

# Check if cluster is reachable
if ! redis-cli -h $REDIS_HOST -p $REDIS_PORT ping > /dev/null 2>&1; then
    echo "❌ Cannot connect to Redis cluster at $REDIS_HOST:$REDIS_PORT"
    exit 1
fi

echo "✅ Connected to Redis cluster at $REDIS_HOST:$REDIS_PORT"
echo ""

# Cluster info
echo "📊 Cluster Information:"
redis-cli -h $REDIS_HOST -p $REDIS_PORT cluster info | grep -E "(cluster_state|cluster_slots_assigned|cluster_known_nodes|cluster_size)"

echo ""

# Node information  
echo "🗂️  Cluster Nodes:"
echo "Node ID      | Address        | Role   | Status | Slots"
echo "-------------|----------------|--------|--------|-------"
redis-cli -h $REDIS_HOST -p $REDIS_PORT cluster nodes | while read line; do
    node_id=$(echo $line | awk '{print $1}' | cut -c1-12)
    node_addr=$(echo $line | awk '{print $2}' | cut -d@ -f1)
    node_flags=$(echo $line | awk '{print $3}')
    node_role=$(echo $node_flags | cut -d, -f1)
    node_status="connected"
    
    # Check if this line contains slot information
    slots=""
    if echo $line | grep -q "\["; then
        slots=$(echo $line | grep -o '\[[^]]*\]' | head -1)
    fi
    
    printf "%-12s | %-14s | %-6s | %-6s | %s\n" "$node_id" "$node_addr" "$node_role" "$node_status" "$slots"
done

echo ""

# Check cluster health
echo "🏥 Health Check:"
cluster_state=$(redis-cli -h $REDIS_HOST -p $REDIS_PORT cluster info | grep cluster_state | cut -d: -f2 | tr -d '\r')

if [ "$cluster_state" = "ok" ]; then
    echo "✅ Cluster is healthy!"
else
    echo "⚠️  Cluster state: $cluster_state"
fi

# Check key distribution (sample)
echo ""
echo "🔑 Key Distribution Test:"
total_keys=0
for port in 7001 7002 7003 7004 7005 7006; do
    if redis-cli -h 10.0.0.1$((port-7000)) -p $port ping > /dev/null 2>&1; then
        keys=$(redis-cli -h 10.0.0.1$((port-7000)) -p $port dbsize 2>/dev/null || echo "0")
        echo "   Node $port: $keys keys"
        total_keys=$((total_keys + keys))
    fi
done
echo "   Total keys: $total_keys"

echo ""
echo "✅ Status check complete!" 