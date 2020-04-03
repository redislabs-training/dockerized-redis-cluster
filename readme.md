# Simple Redis OSS Cluster via Docker Compose

- will start up 6 docker redis containers with custom ports and internal IPs
- allows you to setup 3 masters with replication

## versions

```sh
git checkout version/5.0.8
```

If you want to setup a different version not represented already...just create a new branch for it: version/(redis-version) 

```sh
git checkout -b version/6.0-rc3
```

update the docker-compose.yml `image` reference for all the redis-1,2,3,etc services (make sure all 6 are updated)...e.g.

```yaml
...
  redis1:
    container_name: redis-1
    image: redis:6.0-rc3
    ports: 
      - 7001:7001
...
```

then commit and push...

```sh
git commit -m 'adding new version: 6.0-rc3' .

git push origin version/6.0-rc3
```

### Changes to readme across versions
If changes need to be made to the readme... start with the master branch, make the changes and then checkout each branch, run git fetch and update the specific file.

example, after readme.md in master has been updated:

```sh
git commit -m 'updated readme' .
git push origin master
```

then switch branches

```sh
git checkout version/6.0-rc3
git fetch
git checkout origin/master -- readme.md
git commit -m 'update readme' .
git push origin version/6.0-rc3
```


## running nodes
It's just using docker-compose... so do your own magic if you know it.

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

```sh
docker exec -it redis-1 redis-cli -p 7001 --cluster create 10.0.0.11:7001 10.0.0.12:7002 10.0.0.13:7003 10.0.0.14:7004 10.0.0.15:7005 10.0.0.16:7006 --cluster-replicas 1 
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
❯ redis-cli -p 7001 -h 0.0.0.0
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
   2) (integer) 16383
   3) 1) "10.0.0.13"
      2) (integer) 7003
      3) "623736d0b41e9814331df6efbf7bb7aedafca5e3"
   4) 1) "10.0.0.14"
      2) (integer) 7004
      3) "18ff1e20e902b0cd54e24d86a163c3636b02a5c3"
2) 1) (integer) 5461
   2) (integer) 10922
   3) 1) "10.0.0.12"
      2) (integer) 7002
      3) "8d8382932ef8ab5ee2b679744bb64aad35ff6462"
   4) 1) "10.0.0.16"
      2) (integer) 7006
      3) "1ce3615135775193d123b85f709986d99ef7fdcc"
3) 1) (integer) 0
   2) (integer) 5460
   3) 1) "10.0.0.11"
      2) (integer) 7001
      3) "f0ab4bc5127688e5486f83f4feec56ebbcfa190e"
   4) 1) "10.0.0.15"
      2) (integer) 7005
      3) "d74891990280d81b5917094cf3556045fdd7d767"
```

## References (aka stole from...) 
- https://itsmetommy.com/2018/05/24/docker-compose-redis-cluster/
- https://redis.io/topics/cluster-tutorial


