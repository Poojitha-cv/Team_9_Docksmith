#!/bin/bash
set -e

echo "=============================="
echo "1. Cold Build (Expect CACHE MISS)"
echo "=============================="
python3 docksmith.py build -t myapp:latest .

echo ""
echo "=============================="
echo "Manifest JSON"
echo "=============================="
cat ~/.docksmith/images/myapp_latest.json

echo ""
echo "=============================="
echo "Layer Files"
echo "=============================="
ls ~/.docksmith/layers/

echo ""
echo "=============================="
echo "2. Warm Build (Expect CACHE HIT)"
echo "=============================="
python3 docksmith.py build -t myapp:latest .

echo ""
echo "=============================="
echo "3. Modify Source → Cache Invalidation"
echo "=============================="
echo "# change" >> docksmith.py

python3 docksmith.py build -t myapp:latest .

echo ""
echo "=============================="
echo "4. List Images"
echo "=============================="
python3 docksmith.py images

echo ""
echo "=============================="
echo "5. Run Container (Default CMD)"
echo "=============================="
python3 docksmith.py run myapp:latest

echo ""
echo "=============================="
echo "6. Run with ENV Override"
echo "=============================="
python3 docksmith.py run -e NAME=OVERRIDE myapp:latest

echo ""
echo "=============================="
echo "7. Isolation Test"
echo "=============================="
python3 docksmith.py run myapp:latest sh -c "echo hello > /tmp/testfile"

echo "Checking host..."
if [ -f /tmp/testfile ]; then
    echo "❌ FAIL: Isolation broken"
else
    echo "✅ PASS: Isolation working"
fi

echo ""
echo "=============================="
echo "8. Remove Image"
echo "=============================="
python3 docksmith.py rmi myapp:latest

echo ""
echo "=============================="
echo "DEMO COMPLETE"
echo "=============================="
