from rediscluster import RedisCluster

startup_nodes = [{"host":"10.0.0.1", "port":"7001"}]

rc = RedisCluster(startup_nodes=startup_nodes, decode_responses=True)

rc.set("test1","val1")
rc.set("test2","val2")
rc.set("test3","val3")

print(rc.get("test1"))
print(rc.get("test2"))
print(rc.get("test3"))