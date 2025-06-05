#!/bin/bash

MASTERS=$1
REPLICAS_PER_MASTER=$2
TOTAL_REPLICAS=$((MASTERS*REPLICAS_PER_MASTER))
TOTAL_INSTANCES=$((MASTERS+TOTAL_REPLICAS))
DOCKER_NETWORK=redisclusternet

echo "close down docker-compose in case"
docker-compose down --remove-orphans

echo "Clear old logs:"
rm -rf logs

echo "Remove redis instances:"
for i in $(seq 1 $TOTAL_INSTANCES);
do
    docker rm -f redis-$i
done

echo "Remove network:"
docker network rm $DOCKER_NETWORK
sleep 2
