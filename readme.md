# Simple Redis CE Cluster via Docker Compose

- will start up 6 docker redis containers with custom ports and internal IPs
- allows you to setup 3 masters with replication
- creates a python docker container on the same network with a source file you can edit and run

## running nodes
It's just using docker-compose... so do your own magic if you know it.

### IMPORTANT: do this first

Copy the `env-orig` to `.env`...

```sh
cp env-orig .env
```

### Changing version

By default the version is the 'latest' container.  The docker-compose config is getting this from an environment variable: `REDIS_VER` which is coming from the `.env` file you just created previously.

**using .env file**  
You can change the version by simply commenting/uncommenting the version you wish to use.

**using export**  
You can also override the default or .env by using export to set the version.

```
export REDIS_VER=4
```

then run docker-compose... to revert

```
unset REDIS_VER
```

### foreground (will include logs)

**start**

```sh
docker-compose up
```

**stop**

ctl-c in running console

then to completely reset:

```sh
docker-compose down
```

### background (detached mode)

**start**

```sh
docker-compose up --detach
```

**logs** 

```sh
docker-compose logs -f
```

**stop**

```sh
docker-compose down
```

## create cluster

Use this command to create the cluster:

```sh
docker exec -it redis-1 redis-cli -p 7001 --cluster create 10.0.0.11:7001 10.0.0.12:7002 10.0.0.13:7003 10.0.0.14:7004 10.0.0.15:7005 10.0.0.16:7006 --cluster-replicas 1 --cluster-yes
```


There will be a prompt to confirm you wish to *set this configuration* which you need to confirm by entering **yes** ... see example below.


**docker compose vs docker-compose**

If you start things up using `docker compose up -d` things will start up but the IPv4 IPs don't seem to get set.

Toby came up with this work around which dynamically pulls the IPs from docker inspect and uses them on the cluster creation.

```
docker exec -it redis-1 redis-cli -p 7001 --cluster create $(for i in {1..6}; do docker inspect redis-$i --format '{{ $network := index .NetworkSettings.Networks "dockerized-redis-cluster_redisclusternet"}}{{$network.IPAddress}}'; echo 700$i;  done | paste -d : - -) --cluster-replicas 1 --cluster-yes
```

**example**

```sh
❯ docker exec -it redis-1 redis-cli -p 7001 --cluster create 10.0.0.11:7001 10.0.0.12:7002 10.0.0.13:7003 10.0.0.14:7004 10.0.0.15:7005 10.0.0.16:7006 --cluster-replicas 1
>>> Performing hash slots allocation on 6 nodes...
Master[0] -> Slots 0 - 5460
Master[1] -> Slots 5461 - 10922
Master[2] -> Slots 10923 - 16383
Adding replica 10.0.0.15:7005 to 10.0.0.11:7001
Adding replica 10.0.0.16:7006 to 10.0.0.12:7002
Adding replica 10.0.0.14:7004 to 10.0.0.13:7003
M: f0ab4bc5127688e5486f83f4feec56ebbcfa190e 10.0.0.11:7001
   slots:[0-5460] (5461 slots) master
M: 8d8382932ef8ab5ee2b679744bb64aad35ff6462 10.0.0.12:7002
   slots:[5461-10922] (5462 slots) master
M: 623736d0b41e9814331df6efbf7bb7aedafca5e3 10.0.0.13:7003
   slots:[10923-16383] (5461 slots) master
S: 18ff1e20e902b0cd54e24d86a163c3636b02a5c3 10.0.0.14:7004
   replicates 623736d0b41e9814331df6efbf7bb7aedafca5e3
S: d74891990280d81b5917094cf3556045fdd7d767 10.0.0.15:7005
   replicates f0ab4bc5127688e5486f83f4feec56ebbcfa190e
S: 1ce3615135775193d123b85f709986d99ef7fdcc 10.0.0.16:7006
   replicates 8d8382932ef8ab5ee2b679744bb64aad35ff6462
Can I set the above configuration? (type 'yes' to accept): yes
>>> Nodes configuration updated
>>> Assign a different config epoch to each node
>>> Sending CLUSTER MEET messages to join the cluster
Waiting for the cluster to join
...
>>> Performing Cluster Check (using node 10.0.0.11:7001)
M: f0ab4bc5127688e5486f83f4feec56ebbcfa190e 10.0.0.11:7001
   slots:[0-5460] (5461 slots) master
   1 additional replica(s)
S: 1ce3615135775193d123b85f709986d99ef7fdcc 10.0.0.16:7006
   slots: (0 slots) slave
   replicates 8d8382932ef8ab5ee2b679744bb64aad35ff6462
S: d74891990280d81b5917094cf3556045fdd7d767 10.0.0.15:7005
   slots: (0 slots) slave
   replicates f0ab4bc5127688e5486f83f4feec56ebbcfa190e
M: 623736d0b41e9814331df6efbf7bb7aedafca5e3 10.0.0.13:7003
   slots:[10923-16383] (5461 slots) master
   1 additional replica(s)
S: 18ff1e20e902b0cd54e24d86a163c3636b02a5c3 10.0.0.14:7004
   slots: (0 slots) slave
   replicates 623736d0b41e9814331df6efbf7bb7aedafca5e3
M: 8d8382932ef8ab5ee2b679744bb64aad35ff6462 10.0.0.12:7002
   slots:[5461-10922] (5462 slots) master
   1 additional replica(s)
[OK] All nodes agree about slots configuration.
>>> Check for open slots...
>>> Check slots coverage...
[OK] All 16384 slots covered.
```

**verify**


```sh
❯ docker exec -it redis-1 redis-cli -p 7001
0.0.0.0:7001> cluster nodes
1ce3615135775193d123b85f709986d99ef7fdcc 10.0.0.16:7006@17006 slave 8d8382932ef8ab5ee2b679744bb64aad35ff6462 0 1585947900522 6 connected
d74891990280d81b5917094cf3556045fdd7d767 10.0.0.15:7005@17005 slave f0ab4bc5127688e5486f83f4feec56ebbcfa190e 0 1585947901135 5 connected
623736d0b41e9814331df6efbf7bb7aedafca5e3 10.0.0.13:7003@17003 master - 0 1585947900109 3 connected 10923-16383
18ff1e20e902b0cd54e24d86a163c3636b02a5c3 10.0.0.14:7004@17004 slave 623736d0b41e9814331df6efbf7bb7aedafca5e3 0 1585947900522 4 connected
8d8382932ef8ab5ee2b679744bb64aad35ff6462 10.0.0.12:7002@17002 master - 0 1585947899067 2 connected 5461-10922
f0ab4bc5127688e5486f83f4feec56ebbcfa190e 10.0.0.11:7001@17001 myself,master - 0 1585947900000 1 connected 0-5460
0.0.0.0:7001>
0.0.0.0:7001> cluster slots
1) 1) (integer) 10923
   1) (integer) 16383
   2) 1) "10.0.0.13"
      1) (integer) 7003
      2) "623736d0b41e9814331df6efbf7bb7aedafca5e3"
   3) 1) "10.0.0.14"
      1) (integer) 7004
      2) "18ff1e20e902b0cd54e24d86a163c3636b02a5c3"
2) 1) (integer) 5461
   1) (integer) 10922
   2) 1) "10.0.0.12"
      1) (integer) 7002
      2) "8d8382932ef8ab5ee2b679744bb64aad35ff6462"
   3) 1) "10.0.0.16"
      1) (integer) 7006
      2) "1ce3615135775193d123b85f709986d99ef7fdcc"
3) 1) (integer) 0
   1) (integer) 5460
   2) 1) "10.0.0.11"
      1) (integer) 7001
      2) "f0ab4bc5127688e5486f83f4feec56ebbcfa190e"
   3) 1) "10.0.0.15"
      1) (integer) 7005
      2) "d74891990280d81b5917094cf3556045fdd7d767"
```
## Python Client Test Container

This is provided to be able to try out redis cluster from within an application and what it would look like.


Since the cluster is within the docker network to properly test you will need to be able to have a client connect within that network.  There is one additional container started that is part of that same network with a source file mapped in to be able to run tests.

NOTE: You must run the command to create the cluster first before using the python client.

**source**:
You can put your own python code in *app* or just extend the basic exmaple already included:
`app/test.py`

**testing**  
The *app* directory is mapped to */usr/local/cluster-tester* to run the test.py script you execute:

```
docker-compose exec app python /usr/local/cluster-tester/test.py
```

To get a shell prompt in the test container...

```
docker-compose exec app sh
```

**other languages**  
If you don't want to use python... you could start up another container with your source and language of choice.  Just make sure it's on the same docker network: *redis--cluster_redisclusternet* and you are connecting your client to the 10. IP like the test.py does.

**memtier**
There is a memtier service commented out in the docker-compose if you would like to run that uncomment it.


## Clusters of Various Sizes

The TE team wanted to research different failure and failover scenarios with cluster. So, included in this repo is a script to create docker Redis instances and a cluster.  If you are good with the docker compose stuff you don't need this.

The create script takes in the number of masters and the number of replicas per master, starts a docker network, runs redis docker instances with unique IPs and ports on the docker network, and then creates a cluster with replicas.  This command will create 3 masters and 3 replicas (1 replica for each master)... so 6 shards (redis docker containers in total).

```
./create_cluster.sh 3 1
```

This is not docker-compose so it will attempt to close down any existing docker-compose runs as well as clear up any previous runs of the script.

There is also a delete script which takes the same parameters and removes containers and networks.

```
./delete_cluster.sh 3 1
```

** Connect the app or memtier **

If you wanted to pair the Redis cluster with another container, like the docker-compose has, to run python... or memtier you just need to run the container in the same network.

After running `create_cluster.sh` start your container...

Python App:

```
docker run --network redisclusternet -d --volumes $(pwd)/app:/usr/local/cluster-tester --entrypoint /usr/local/cluster-tester/docker-entrypoint.sh python:3.8-alpine3.10
```

Memtier (default settings pointing to redis-1 IP and port for starters)

```
docker run --network redisclusternet redislabs/memtier_benchmark:latest --cluster-mode -s 10.0.0.1 -p 7001
```

## References (aka stole from...) 

- https://itsmetommy.com/2018/05/24/docker-compose-redis-cluster/
- https://redis.io/topics/cluster-tutorial
