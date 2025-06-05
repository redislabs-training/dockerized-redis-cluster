#!/bin/sh

echo "🐍 Installing Python dependencies..."
pip install -r /usr/local/cluster-tester/requirements.txt

# Set working directory
cd /usr/local/cluster-tester

echo "🚀 Redis Cluster Test Environment Ready!"
echo ""
echo "Current directory: $(pwd)"
echo "Available files:"
ls -la
echo ""
echo "Available test scripts:"
echo "  - python simple_test.py       (Quick connectivity check)"
echo "  - python connection.py        (Comprehensive tests)"
echo ""
echo "You can also run: docker exec -it <container> /bin/sh"
echo ""

# Keep container running
tail -f /dev/null