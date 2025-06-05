#!/bin/bash

MASTERS=$1
REPLICAS_PER_MASTER=$2
REDIS_VER=latest
TOTAL_REPLICAS=$((MASTERS*REPLICAS_PER_MASTER))
TOTAL_INSTANCES=$((MASTERS+TOTAL_REPLICAS))
DOCKER_NETWORK=redisclusternet

if [ $((MASTERS%2)) -eq 0 ] || [ "$1" -le 2 ]; then
    echo "ERROR - Redis cluster requires a quorum of masters."
    set -e;
else
    echo "Creating a Redis cluster with ${MASTERS} masters and ${TOTAL_REPLICAS} replicas for a total of ${TOTAL_INSTANCES} 'nodes' or shards."
fi

echo "Going to try to clean up everything from previous runs, but... can only do so much.  You may need to clean things up yourself and re-run."

echo "close down docker-compose in case"
docker-compose down --remove-orphans

echo "Clear old logs:"
rm -rf logs

echo "Remove old containers ... can only guess how many:"
for i in $(seq 1 $TOTAL_INSTANCES);
do
    docker rm -f redis-$i
done

echo "Remove previous network:"
docker network rm $DOCKER_NETWORK
sleep 2

echo "Create new network: ${DOCKER_NETWORK}"
docker network create --driver=bridge --subnet=10.0.0.0/24 --gateway=10.0.0.254 $DOCKER_NETWORK

echo "Run redis instances:"

for i in $(seq 1 $TOTAL_INSTANCES);
do
    echo redis-$i
    if [ "${#i}" -lt 2 ]; then
        PORT=700$i
    else
        PORT=70$i
    fi
	#docker run -d --name redis-$i --network $DOCKER_NETWORK \
    #--ip 10.0.0.$i \
    #-p $PORT:$PORT \
    #--env REDIS_PORT=$PORT \
    #--volume $(pwd)/logs/:/var/log/redis/ \
    #--volume $(pwd)/configs/redis-template.conf:/etc/redis/redis.conf \
    #redis:$REDIS_VER \
    #redis-server /etc/redis/redis.conf --port $PORT --logfile "/var/log/redis/redis-${i}.log"

	#docker run -d --name redis-$i --network $DOCKER_NETWORK \
    #--ip 10.0.0.$i \
    #-p $PORT:$PORT \
    #--env REDIS_PORT=$PORT \
    #--volume $(pwd)/logs/:/var/log/redis/ \
    #redis:$REDIS_VER \
    #redis-server \
    #--port $PORT \
    #--logfile  "/var/log/redis/redis-${i}.log" \
    #--cluster-enabled yes \
    #--cluster-config-file nodes.conf \
    #--cluster-node-timeout 5000 \
    #--appendonly yes \
    #--loglevel debug \
    #--cluster-replica-no-failover yes

	docker run -d --name redis-$i --network $DOCKER_NETWORK \
    --ip 10.0.0.$i \
    -p $PORT:$PORT \
    --env REDIS_PORT=$PORT \
    --volume $(pwd)/logs/:/var/log/redis/ \
    redis:$REDIS_VER \
    redis-server \
    --port $PORT \
    --logfile  "/var/log/redis/redis-${i}.log" \
    --cluster-enabled yes \
    --cluster-config-file nodes.conf \
    --cluster-node-timeout 5000 \
    --appendonly yes \
    --loglevel debug


done

echo "Containers started!"

docker ps

echo "Now let's create the Redis cluster:"

docker exec -it redis-1 redis-cli -p 7001 --cluster create $(for i in $(seq 1 $TOTAL_INSTANCES); do docker inspect redis-$i --format '{{ $network := index .NetworkSettings.Networks "redisclusternet"}}{{$network.IPAddress}}'; if [ "${#i}" -lt 2 ]; then echo 700${i}; else echo 70${i}; fi  done | paste -d : - -) --cluster-replicas $REPLICAS_PER_MASTER --cluster-yes

echo "peace!"