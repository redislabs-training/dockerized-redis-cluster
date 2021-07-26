# Add Sentinel to OSS cluster

I added this so you could add sentinel to a simple Redis OSS cluster and see how they would interact.

## Build docker image

```
docker build -t sentinel .
```

## OSS cluster

First create a three node cluster either by following the docker-compose instructions or using the shell script provided in the root of the repo.  Both are documented in the repo's readme.

```
./create_cluster.sh 3 1
```

Basically, the sentinel config you build into the docker image will look for a master on 10.0.0.1, 10.0.0.2, 10.0.0.3.  You can look at this config if you desire to extend... just rebuild after you extend.

## Run sentinel instances

I guess this could be scripted, but it's not too bad to run manually.

```
docker run --name sentinel-1 -d --network redisclusternet -p 7701:6379 --volume $(pwd)/logs/:/var/log/redis/ sentinel redis-server /etc/redis/sentinel.conf --logfile "/var/log/redis/sentinel-1.log" --sentinel
```

```
docker run --name sentinel-2 -d --network redisclusternet -p 7702:6379 --volume $(pwd)/logs/:/var/log/redis/ sentinel redis-server /etc/redis/sentinel.conf --logfile "/var/log/redis/sentinel-2.log" --sentinel
```

```
docker run --name sentinel-3 -d --network redisclusternet -p 7703:6379 --volume $(pwd)/logs/:/var/log/redis/ sentinel redis-server /etc/redis/sentinel.conf --logfile "/var/log/redis/sentinel-3.log" --sentinel
```
