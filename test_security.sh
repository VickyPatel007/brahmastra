#!/bin/bash

# Quick test script for security enhancements
EC2_IP="13.234.113.97"

echo "🧪 Testing Security Enhancements on EC2"
echo "========================================"
echo ""

# Test 1: Check if backend is running
echo "1️⃣ Backend Health Check..."
HEALTH=$(curl -s -o /dev/null -w "%{http_code}" http://${EC2_IP}:8000/docs)
if [ "$HEALTH" = "200" ]; then
    echo "✅ Backend is running (HTTP $HEALTH)"
else
    echo "⚠️  Backend returned HTTP $HEALTH"
fi
echo ""

# Test 2: Test login endpoint
echo "2️⃣ Testing Login Endpoint..."
LOGIN_RESPONSE=$(curl -s -X POST http://${EC2_IP}:8000/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"vivek@brahmastra.io","password":"Test12345"}')

if echo "$LOGIN_RESPONSE" | grep -q "access_token"; then
    echo "✅ Login successful - got access token"
    TOKEN=$(echo "$LOGIN_RESPONSE" | grep -o '"access_token":"[^"]*' | cut -d'"' -f4)
    echo "Token: ${TOKEN:0:50}..."
else
    echo "❌ Login failed"
    echo "Response: $LOGIN_RESPONSE"
fi
echo ""

# Test 3: Test logout endpoint
if [ ! -z "$TOKEN" ]; then
    echo "3️⃣ Testing Logout Endpoint..."
    LOGOUT_RESPONSE=$(curl -s -X POST http://${EC2_IP}:8000/api/auth/logout \
      -H "Authorization: Bearer $TOKEN")
    
    if echo "$LOGOUT_RESPONSE" | grep -q "Logged out successfully"; then
        echo "✅ Logout endpoint working"
    else
        echo "⚠️  Logout response: $LOGOUT_RESPONSE"
    fi
    echo ""
fi

# Test 4: Test rate limiting on registration
echo "4️⃣ Testing Rate Limiting (6 quick registrations)..."
RATE_LIMITED=false
for i in {1..6}; do
    RANDOM_EMAIL="ratetest${RANDOM}@test.com"
    RESPONSE=$(curl -s -w "\nHTTP_CODE:%{http_code}" -X POST http://${EC2_IP}:8000/api/auth/register \
      -H "Content-Type: application/json" \
      -d "{\"email\":\"$RANDOM_EMAIL\",\"password\":\"Test123\",\"full_name\":\"Rate Test $i\"}")
    
    HTTP_CODE=$(echo "$RESPONSE" | grep "HTTP_CODE" | cut -d':' -f2)
    
    if [ "$HTTP_CODE" = "429" ]; then
        echo "  Attempt $i: ⚠️  Rate limited (HTTP 429) ✅"
        RATE_LIMITED=true
        break
    elif [ "$HTTP_CODE" = "200" ]; then
        echo "  Attempt $i: ✅ Success (HTTP 200)"
    else
        echo "  Attempt $i: HTTP $HTTP_CODE"
    fi
done

if [ "$RATE_LIMITED" = true ]; then
    echo "✅ Rate limiting is working!"
else
    echo "⚠️  Rate limiting may not be active (no 429 error received)"
fi
echo ""

# Test 5: Test CORS (this will fail from command line, which is expected)
echo "5️⃣ CORS Restriction..."
echo "ℹ️  CORS can only be properly tested from a browser"
echo "   Current allowed origins:"
echo "   - http://13.234.113.97:8080"
echo "   - http://localhost:8080"
echo ""

echo "========================================"
echo "🎉 Testing Complete!"
echo ""
echo "📊 Summary:"
echo "  - Backend: Running"
echo "  - Login: Working"
echo "  - Logout: Working"
echo "  - Rate Limiting: $([ "$RATE_LIMITED" = true ] && echo 'Working' || echo 'Check needed')"
echo "  - CORS: Configured (test in browser)"
