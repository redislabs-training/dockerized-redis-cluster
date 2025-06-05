# Redis Cluster Testing Guide

📖 **For complete documentation, see the main [README.md](../README.md)**

## Quick Reference

### Start Cluster
```bash
COMPOSE_PROFILES=full,init,app docker-compose up -d
```

### Test Scripts
```bash
# Quick connectivity check
docker-compose exec app python simple_test.py

# Comprehensive test suite  
docker-compose exec app python connection.py
```

### Available Tests

- **`simple_test.py`** - Quick connectivity validation and health check
- **`connection.py`** - Comprehensive test suite covering:
  - Key distribution across shards
  - Cluster information and node status
  - Hash tag functionality 
  - Performance testing
  - Different Redis data types
  - Key expiration
  - Pattern matching
  - Automatic cleanup

### Interactive Testing
```bash
docker-compose exec app sh
python  # Start Python with redis available
```

## 📚 Full Documentation

See [README.md](../README.md) for:
- Complete setup instructions
- Configuration options
- Troubleshooting guide
- Management commands
- Advanced usage 