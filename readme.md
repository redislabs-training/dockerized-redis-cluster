# Redis OSS Cluster via Docker Compose 🚀

**Fully automated Redis cluster setup with modern Docker Compose practices**

This repository provides a complete Redis cluster testing environment that eliminates manual setup steps and provides comprehensive testing tools for learning and experimenting with Redis OSS clustering.

## ✨ Features

- 🔄 **Fully automated cluster initialization** - No manual `redis-cli` commands needed
- 🏥 **Health checks & dependencies** - Services wait for dependencies to be ready  
- 🎯 **Profile-based deployment** - Easy switching between different configurations
- 🧪 **Comprehensive testing suite** - Extensive tests for cluster functionality
- 🐍 **Python test environment** - Ready-to-use testing container
- 🖥️ **Optional Web GUI** - Redis Insight for visual cluster management
- ⚡ **Modern practices** - Latest Redis and Docker Compose features

## 🚀 Quick Start

```bash
# Start full 6-node cluster with automatic initialization and testing environment
COMPOSE_PROFILES=full,init,app docker-compose up -d

# Test the cluster (runs automatically after initialization)
docker-compose exec app python simple_test.py

# Run comprehensive test suite
docker-compose exec app python connection.py
```

That's it! The cluster is automatically created and ready for testing.

## 🎯 Configuration Options

### Deployment Profiles

Choose the setup that fits your needs:

**🔧 Development (3 masters only)**
```bash
COMPOSE_PROFILES=minimal,init,app docker-compose up -d
```

**🏭 Production-like (6 nodes: 3 masters + 3 replicas)**
```bash
COMPOSE_PROFILES=full,init,app docker-compose up -d
```

**🖥️ With Redis Insight Web GUI**
```bash
COMPOSE_PROFILES=full,init,app,insight docker-compose up -d
# Access Redis Insight at http://localhost:8001
```

### Environment Configuration

Copy the starter environment to `.env`:
```bash
cp env-starter .env
```

The environment file contains configuration options:

```bash
# Redis version
REDIS_VERSION=7-alpine

# Python version for test container  
PYTHON_VERSION=3.11-alpine

# Cluster configuration
REPLICAS_PER_MASTER=1
CLUSTER_NODES=10.0.0.11:7001 10.0.0.12:7002 10.0.0.13:7003 10.0.0.14:7004 10.0.0.15:7005 10.0.0.16:7006

# Active profiles
COMPOSE_PROFILES=full,init,app
```

## 🧪 Testing

### Available Test Scripts

The testing environment includes comprehensive Redis cluster tests:

**Quick Connectivity Check**
```bash
docker-compose exec app python simple_test.py
```
- Verifies cluster connection
- Basic health check
- Returns success/failure status

**Comprehensive Test Suite**
```bash
docker-compose exec app python connection.py
```
- Key distribution across shards
- Cluster information and node status  
- Hash tag functionality (keys with same tag → same shard)
- Performance testing (1000 operations)
- Different Redis data types (strings, lists, sets, hashes)
- Key expiration testing
- Pattern matching operations
- Automatic cleanup

### Interactive Testing

Access the test container for manual testing:
```bash
docker-compose exec app sh
cd /usr/local/cluster-tester
python  # Start Python interpreter with redis available
```

## 📋 Management Commands

### Monitoring

**Check cluster status**
```bash
docker-compose exec redis-1 redis-cli -p 7001 cluster info
docker-compose exec redis-1 redis-cli -p 7001 cluster nodes
```

**View logs**
```bash
# All services
docker-compose logs -f

# Specific services
docker-compose logs -f cluster-init  # Initialization logs
docker-compose logs -f app           # Test container logs
docker-compose logs -f redis-1       # Individual Redis node
```

**Service status**
```bash
docker-compose ps
```

### Lifecycle Management

**Stop cluster**
```bash
docker-compose down
```

**Complete cleanup** (removes data and logs)
```bash
docker-compose down -v
rm -rf logs/
```

**Restart services**
```bash
docker-compose restart app           # Restart test container
docker-compose restart redis-1       # Restart specific Redis node
```

## 🎯 What Makes This Setup Better

### Before vs After

**Old Manual Workflow:**
1. Start containers manually
2. Wait and guess when they're ready
3. Run complex `redis-cli` cluster creation commands
4. Manually manage dependencies and errors
5. No standardized testing

**Current Automated Workflow:**
1. Single command: `COMPOSE_PROFILES=full,init,app docker-compose up -d`  
2. Everything ready automatically with health checks
3. Comprehensive testing tools included

### Key Benefits

✅ **Zero Manual Steps** - Fully automated cluster creation  
✅ **Reliable Startup** - Health checks ensure proper initialization order  
✅ **Flexible Configuration** - Profile-based deployment for different needs  
✅ **Comprehensive Testing** - Ready-made test suite for learning  
✅ **Modern Practices** - Latest Redis and Docker Compose features  
✅ **Production-Ready** - Proper logging, monitoring, and error handling  
✅ **Developer-Friendly** - Clear feedback and simple commands  

## 🔍 Troubleshooting

### Common Issues

**"Connection refused" errors**
```bash
# Check if cluster initialization completed
docker-compose logs cluster-init

# Verify all services are healthy
docker-compose ps
```

**"CLUSTERDOWN Hash slot not served"**
```bash
# Cluster creation didn't complete properly, restart initialization
docker-compose restart cluster-init
docker-compose logs -f cluster-init
```

**Python import errors**
```bash
# Check if dependencies installed correctly
docker-compose logs app
docker-compose exec app pip list | grep redis
```

### Manual Cluster Creation (if needed)

If automatic initialization fails, you can create the cluster manually:
```bash
docker-compose exec redis-1 redis-cli -p 7001 --cluster create 10.0.0.11:7001 10.0.0.12:7002 10.0.0.13:7003 10.0.0.14:7004 10.0.0.15:7005 10.0.0.16:7006 --cluster-replicas 1 --cluster-yes
```

### Reset Everything

For a complete fresh start:
```bash
docker-compose down -v
rm -rf logs/
COMPOSE_PROFILES=full,init,app docker-compose up -d
```
## 📁 Repository Structure

```
├── docker-compose.yml          # Main automated cluster setup
├── .env                       # Environment configuration  
├── app/                       # Python testing environment
│   ├── simple_test.py         # Quick connectivity check
│   ├── connection.py          # Comprehensive test suite  
│   ├── requirements.txt       # Python dependencies
│   └── docker-entrypoint.sh   # Container initialization
├── scripts/                   # Cluster management scripts
│   ├── init-cluster.sh        # Automated cluster initialization
│   └── cluster-status.sh      # Health monitoring
├── logs/                      # Redis logs (created at runtime)
├── legacy/                    # Archived legacy setup files
│   ├── docker-compose.legacy.yml
│   ├── create_cluster.sh
│   ├── delete_cluster.sh
│   └── configs/               # Static config files
└── README.md                  # This documentation
```

## 🔧 Advanced Usage

### Custom Redis Configuration

To modify Redis settings, edit the command parameters in `docker-compose.yml`:

```yaml
command: >
  redis-server
  --port 7001
  --cluster-enabled yes
  --cluster-config-file nodes.conf
  --cluster-node-timeout 5000
  --appendonly yes
  --bind 0.0.0.0
  --protected-mode no
  # Add your custom settings here
```

### Adding More Nodes

To create larger clusters, add more Redis services to the docker-compose.yml following the existing pattern and update the `CLUSTER_NODES` environment variable.

### Different Languages

While the setup includes Python testing tools, you can test with any language:

1. **Connect to the Docker network**: `dockerized-redis-cluster_redis-cluster`
2. **Use cluster node IPs**: `10.0.0.11:7001`, `10.0.0.12:7002`, etc.
3. **Enable cluster mode** in your Redis client library


## 🏛️ Legacy Setup

The original manual setup scripts are preserved in the `legacy/` folder for reference:

- `legacy/create_cluster.sh` - Dynamic cluster creation script  
- `legacy/delete_cluster.sh` - Cluster cleanup script
- `legacy/docker-compose.legacy.yml` - Original Docker Compose file
- `legacy/configs/` - Static Redis configuration files

These tools allowed for creating clusters of various sizes but required manual intervention. The modern automated setup replaces this workflow while maintaining the same core functionality.

## 🙏 Acknowledgments

This project builds upon excellent work from the Redis community:

- **Original inspiration**: [Tommy's Docker Compose Redis Cluster guide](https://itsmetommy.com/2018/05/24/docker-compose-redis-cluster/)
- **Redis documentation**: [Official Redis Cluster Tutorial](https://redis.io/topics/cluster-tutorial)
- **Community contributions**: Various improvements and modernizations from users

## 📄 License

This project is provided as-is for educational and testing purposes. Please refer to Redis OSS licensing for production use.

---

**Happy Redis clustering! 🎉**

*This setup provides a complete learning environment for Redis OSS clustering. Feel free to experiment, break things, and learn how Redis clusters work in a safe, reproducible environment.*
