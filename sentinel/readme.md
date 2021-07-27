# Add Sentinel to OSS cluster

I added this so you could add sentinel to a simple Redis OSS cluster and see how they would interact.

## Build docker image

```
docker build -t sentinel .
```

NOTE: I was just dynamically running containers without pre-building but with sentinel there are config re-writes that happen so this was getting sketchy with different instances mapping the same config in.

## Start OSS cluster

First create a three node cluster using the create cluster script.  This will create and use a 'redisclusternet' docker network that will also use when running sentinel.

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

# Clean up

Delete the sentinels first..

```
docker rm -f sentinel-1 sentinel-2 sentinel-3
```

Delete the cluster

```
./delete_cluster.sh 3 1
```

