#!/usr/bin/env python3
"""
WebSocket Analytics Test
Test WebSocket connection and message broadcasting for analytics dashboard.
"""

import asyncio
import websockets
import json
import requests
import time
import uuid

class WebSocketAnalyticsTester:
    def __init__(self, base_url="http://localhost:8001"):
        self.base_url = base_url
        self.ws_url = f"ws://localhost:8001/api/ws/analytics"
        self.token = None
        self.messages_received = []

    async def test_websocket_connection(self):
        """Test basic WebSocket connection"""
        try:
            print("🔌 Testing WebSocket connection...")
            async with websockets.connect(self.ws_url) as websocket:
                print("✅ WebSocket connected successfully")
                
                # Send ping
                await websocket.send("ping")
                print("📤 Sent: ping")
                
                # Wait for response
                try:
                    response = await asyncio.wait_for(websocket.recv(), timeout=5.0)
                    print(f"📥 Received: {response}")
                    return True
                except asyncio.TimeoutError:
                    print("⏰ No response to ping within 5 seconds")
                    return False
                    
        except Exception as e:
            print(f"❌ WebSocket connection failed: {e}")
            return False

    def get_auth_token(self):
        """Get authentication token"""
        print("🔑 Getting auth token...")
        login_url = f"{self.base_url}/api/auth/login"
        login_data = {
            "email": "aminderpro@gmail.com",
            "password": "Admin@123!"
        }
        
        try:
            response = requests.post(login_url, json=login_data, timeout=10)
            if response.status_code == 200:
                data = response.json()
                self.token = data.get('access_token')
                print("✅ Auth token acquired")
                return True
            else:
                print(f"❌ Login failed: {response.status_code}")
                return False
        except Exception as e:
            print(f"❌ Login error: {e}")
            return False

    async def test_realtime_broadcasts(self):
        """Test if analytics events trigger WebSocket broadcasts"""
        print("\n📡 Testing real-time broadcast functionality...")
        
        try:
            # Connect to WebSocket and listen for messages
            async with websockets.connect(self.ws_url) as websocket:
                print("✅ WebSocket connected for broadcast test")
                
                # Start listening in background
                listen_task = asyncio.create_task(self.listen_for_messages(websocket))
                
                # Wait a moment for connection to stabilize
                await asyncio.sleep(1)
                
                # Trigger some analytics events
                await self.trigger_analytics_events()
                
                # Wait for broadcasts
                await asyncio.sleep(3)
                
                # Cancel listening task
                listen_task.cancel()
                
                # Check results
                if self.messages_received:
                    print(f"✅ Received {len(self.messages_received)} WebSocket messages:")
                    for msg in self.messages_received:
                        print(f"   📨 {msg}")
                    return True
                else:
                    print("⚠️ No broadcast messages received")
                    return False
                    
        except Exception as e:
            print(f"❌ Broadcast test failed: {e}")
            return False

    async def listen_for_messages(self, websocket):
        """Listen for WebSocket messages"""
        try:
            while True:
                message = await websocket.recv()
                try:
                    data = json.loads(message)
                    self.messages_received.append(data)
                    print(f"📥 Broadcast received: {data['type']}")
                except:
                    self.messages_received.append(message)
                    print(f"📥 Raw message: {message}")
        except asyncio.CancelledError:
            pass
        except Exception as e:
            print(f"⚠️ Listening error: {e}")

    async def trigger_analytics_events(self):
        """Trigger analytics events to test broadcasts"""
        print("🎯 Triggering analytics events...")
        
        visitor_id = str(uuid.uuid4())
        session_id = str(uuid.uuid4())
        
        # 1. Start session
        session_data = {
            "visitor_id": visitor_id,
            "landing_page": "/test",
            "referrer": "https://google.com",
            "user_agent": "Test Browser",
            "screen_resolution": "1920x1080"
        }
        
        try:
            # Use asyncio to run HTTP requests
            loop = asyncio.get_event_loop()
            
            # Start session
            start_url = f"{self.base_url}/api/customer-analytics/track/session/start"
            await loop.run_in_executor(None, requests.post, start_url, session_data)
            print("   ✅ Session started")
            
            # Track pageview
            pageview_data = {
                "page_url": "/test",
                "page_title": "Test Page",
                "session_id": session_id,
                "visitor_id": visitor_id
            }
            pageview_url = f"{self.base_url}/api/customer-analytics/track/pageview"
            await loop.run_in_executor(None, lambda: requests.post(pageview_url, json=pageview_data))
            print("   ✅ Pageview tracked")
            
            # Track conversion
            conversion_data = {
                "event_name": "test_conversion",
                "event_category": "test",
                "event_value": 50.0,
                "page_url": "/test",
                "session_id": session_id,
                "visitor_id": visitor_id
            }
            conversion_url = f"{self.base_url}/api/customer-analytics/track/conversion"
            await loop.run_in_executor(None, lambda: requests.post(conversion_url, json=conversion_data))
            print("   ✅ Conversion tracked")
            
        except Exception as e:
            print(f"   ❌ Error triggering events: {e}")

    async def run_tests(self):
        """Run all WebSocket tests"""
        print("🧪 WebSocket Analytics Test Suite")
        print("=" * 40)
        
        results = []
        
        # Test 1: Basic connection
        result1 = await self.test_websocket_connection()
        results.append(("Basic Connection", result1))
        
        # Get auth token for other tests
        if not self.get_auth_token():
            print("❌ Cannot continue without auth token")
            return
        
        # Test 2: Real-time broadcasts
        result2 = await self.test_realtime_broadcasts()
        results.append(("Real-time Broadcasts", result2))
        
        # Summary
        print("\n📊 WebSocket Test Results:")
        passed = 0
        for test_name, result in results:
            status = "✅ PASSED" if result else "❌ FAILED"
            print(f"   {test_name}: {status}")
            if result:
                passed += 1
        
        print(f"\nSuccess Rate: {passed}/{len(results)} ({passed/len(results)*100:.1f}%)")
        return passed == len(results)

async def main():
    """Main test runner"""
    tester = WebSocketAnalyticsTester()
    success = await tester.run_tests()
    return 0 if success else 1

if __name__ == "__main__":
    result = asyncio.run(main())
    exit(result)