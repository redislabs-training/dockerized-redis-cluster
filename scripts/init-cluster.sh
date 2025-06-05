#!/bin/sh
set -e

echo "🚀 Starting Redis Cluster initialization..."

# Default values
CLUSTER_NODES=${CLUSTER_NODES:-"10.0.0.11:7001 10.0.0.12:7002 10.0.0.13:7003 10.0.0.14:7004 10.0.0.15:7005 10.0.0.16:7006"}
REPLICAS_PER_MASTER=${REPLICAS_PER_MASTER:-1}
MAX_RETRIES=30
RETRY_INTERVAL=2

echo "📋 Configuration:"
echo "   Cluster nodes: $CLUSTER_NODES"
echo "   Replicas per master: $REPLICAS_PER_MASTER"
echo ""

# Function to check if a Redis node is ready
check_redis_ready() {
    local host_port=$1
    local host=$(echo $host_port | cut -d: -f1)
    local port=$(echo $host_port | cut -d: -f2)
    
    redis-cli -h $host -p $port ping > /dev/null 2>&1
    return $?
}

# Function to check if cluster is already initialized
check_cluster_exists() {
    local first_node=$(echo $CLUSTER_NODES | awk '{print $1}')
    local host=$(echo $first_node | cut -d: -f1)
    local port=$(echo $first_node | cut -d: -f2)
    
    # Check if cluster is already configured
    local cluster_info=$(redis-cli -h $host -p $port cluster info 2>/dev/null || echo "")
    
    if echo "$cluster_info" | grep -q "cluster_state:ok"; then
        echo "✅ Cluster is already initialized and healthy!"
        return 0
    fi
    
    return 1
}

# Wait for all Redis nodes to be ready
echo "⏳ Waiting for Redis nodes to be ready..."
for node in $CLUSTER_NODES; do
    echo "   Checking $node..."
    retries=0
    while [ $retries -lt $MAX_RETRIES ]; do
        if check_redis_ready $node; then
            echo "   ✅ $node is ready"
            break
        else
            echo "   ⏳ $node not ready, retrying in ${RETRY_INTERVAL}s... ($((retries+1))/$MAX_RETRIES)"
            sleep $RETRY_INTERVAL
            retries=$((retries+1))
        fi
    done
    
    if [ $retries -eq $MAX_RETRIES ]; then
        echo "   ❌ $node failed to become ready after $MAX_RETRIES attempts"
        exit 1
    fi
done

echo ""
echo "🔍 Checking if cluster already exists..."

if check_cluster_exists; then
    echo "🎉 Cluster initialization complete (already existed)!"
    exit 0
fi

echo "🔧 Creating Redis cluster..."

# Build the cluster create command
FIRST_NODE=$(echo $CLUSTER_NODES | awk '{print $1}')
HOST=$(echo $FIRST_NODE | cut -d: -f1)
PORT=$(echo $FIRST_NODE | cut -d: -f2)

# Create cluster
echo "   Running: redis-cli -h $HOST -p $PORT --cluster create $CLUSTER_NODES --cluster-replicas $REPLICAS_PER_MASTER --cluster-yes"
redis-cli -h $HOST -p $PORT --cluster create $CLUSTER_NODES --cluster-replicas $REPLICAS_PER_MASTER --cluster-yes

# Verify cluster creation with retries
echo ""
echo "🔍 Verifying cluster setup..."

# Wait for cluster to stabilize with retries
verification_retries=0
max_verification_retries=10
while [ $verification_retries -lt $max_verification_retries ]; do
    sleep 2
    verification_retries=$((verification_retries+1))
    
    if check_cluster_exists; then
        echo "✅ Cluster created successfully!"
        
        # Show cluster info
        echo ""
        echo "📊 Cluster Information:"
        redis-cli -h $HOST -p $PORT cluster info | grep -E "(cluster_state|cluster_slots_assigned|cluster_known_nodes)"
        
        echo ""
        echo "🗂️  Cluster Nodes:"
        redis-cli -h $HOST -p $PORT cluster nodes | while read line; do
            node_id=$(echo $line | awk '{print $1}' | cut -c1-8)
            node_addr=$(echo $line | awk '{print $2}')
            node_role=$(echo $line | awk '{print $3}' | cut -d, -f1)
            echo "   $node_id... | $node_addr | $node_role"
        done
        
        echo ""
        echo "🎉 Redis Cluster is ready for use!"
        exit 0
    else
        echo "   ⏳ Cluster not fully ready yet, retrying... ($verification_retries/$max_verification_retries)"
    fi
done

echo "❌ Cluster verification failed after $max_verification_retries attempts!"
echo "   The cluster may have been created but isn't reporting as ready."
echo "   Try checking manually: docker-compose exec redis-1 redis-cli -p 7001 cluster info"
exit 1 