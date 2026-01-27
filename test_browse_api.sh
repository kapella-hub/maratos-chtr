#!/bin/bash
# Test script to verify the browse API endpoint

echo "Testing /api/workspace/browse endpoint..."
echo ""

# Test 1: Browse root (empty path)
echo "Test 1: Browse root directories"
curl -s "http://localhost:8000/api/workspace/browse" | python3 -m json.tool
echo ""
echo "---"
echo ""

# Test 2: Browse home directory
echo "Test 2: Browse home directory"
curl -s "http://localhost:8000/api/workspace/browse?path=$HOME" | python3 -m json.tool
echo ""
echo "---"
echo ""

# Test 3: Browse Projects directory
echo "Test 3: Browse Projects directory"
curl -s "http://localhost:8000/api/workspace/browse?path=$HOME/Projects" | python3 -m json.tool
echo ""
echo "---"
echo ""

# Test 4: Test error handling - non-existent path
echo "Test 4: Test error handling (non-existent path)"
curl -s "http://localhost:8000/api/workspace/browse?path=/nonexistent/path" | python3 -m json.tool
echo ""
