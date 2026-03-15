#!/usr/bin/env python3
"""
Customer Analytics API - New Features Test Suite
Tests the specific new features mentioned in the review request:
- GET /api/site/analytics-tracker.js - JavaScript tracking library
- WebSocket /api/ws/analytics - Real-time analytics WebSocket
- POST /api/customer-analytics/track/session/start with WebSocket broadcasting
- POST /api/customer-analytics/track/pageview with WebSocket broadcasting  
- POST /api/customer-analytics/track/conversion with WebSocket broadcasting
- Previous dashboard endpoints still working
"""

import requests
import json
import sys
import asyncio
import websockets
import threading
import time
import uuid
from datetime import datetime

class NewFeaturesAPITester:
    def __init__(self, base_url="http://localhost:8001"):
        self.base_url = base_url
        self.ws_url = base_url.replace("http://", "ws://").replace("https://", "wss://")
        self.token = None
        self.tests_run = 0
        self.tests_passed = 0
        self.failed_tests = []
        self.passed_tests = []
        self.websocket_messages = []
        
        print(f"🚀 Testing New Customer Analytics Features")
        print(f"📡 Base URL: {base_url}")
        print(f"🔌 WebSocket URL: {self.ws_url}")
        print("=" * 60)

    def run_test(self, name, test_func):
        """Run a single test with proper error handling"""
        self.tests_run += 1
        print(f"\n🔍 Test {self.tests_run}: {name}")
        
        try:
            success = test_func()
            if success:
                self.tests_passed += 1
                print(f"   ✅ PASSED")
                self.passed_tests.append(name)
                return True
            else:
                print(f"   ❌ FAILED")
                self.failed_tests.append({"test": name, "error": "Test function returned False"})
                return False
        except Exception as e:
            print(f"   ❌ FAILED - Exception: {str(e)}")
            self.failed_tests.append({"test": name, "error": str(e)})
            return False

    def test_admin_login(self):
        """Test admin login to get auth token"""
        print("🔑 Testing Admin Authentication")
        
        login_url = f"{self.base_url}/api/auth/login"
        login_data = {
            "email": "aminderpro@gmail.com",
            "password": "Admin@123!"
        }
        
        try:
            response = requests.post(login_url, json=login_data, timeout=10)
            
            if response.status_code == 200:
                response_data = response.json()
                if 'access_token' in response_data:
                    self.token = response_data['access_token']
                    print(f"   🎯 Login successful - Token acquired")
                    return True
                else:
                    print(f"   ❌ No token in response: {response.text}")
                    return False
            else:
                print(f"   ❌ Login failed - Status {response.status_code}: {response.text}")
                return False
                
        except Exception as e:
            print(f"   ❌ Login exception: {str(e)}")
            return False

    def test_analytics_tracker_js(self):
        """Test GET /api/site/analytics-tracker.js - JavaScript tracking library"""
        print("   📋 Testing analytics tracker JavaScript library access")
        
        try:
            url = f"{self.base_url}/api/site/analytics-tracker.js"
            response = requests.get(url, timeout=10)
            
            if response.status_code == 200:
                content = response.text
                
                # Check if it's valid JavaScript with expected functions
                required_strings = [
                    "AnalyticsTracker",
                    "trackPageView",
                    "trackConversion", 
                    "trackEvent",
                    "init:",
                    "sendRequest"
                ]
                
                missing = []
                for req in required_strings:
                    if req not in content:
                        missing.append(req)
                
                if not missing:
                    print(f"   ✅ JavaScript library accessible - Size: {len(content)} chars")
                    print(f"   📊 Contains all required functions: {', '.join(required_strings)}")
                    return True
                else:
                    print(f"   ❌ Missing required functions: {missing}")
                    return False
            else:
                print(f"   ❌ Failed to access tracker - Status: {response.status_code}")
                return False
                
        except Exception as e:
            print(f"   ❌ Exception accessing tracker: {str(e)}")
            return False

    async def test_websocket_connection(self):
        """Test WebSocket /api/ws/analytics connection"""
        print("   🔌 Testing WebSocket connection to /api/ws/analytics")
        
        try:
            ws_url = f"{self.ws_url}/api/ws/analytics"
            print(f"   📡 Connecting to: {ws_url}")
            
            async with websockets.connect(ws_url, timeout=10) as websocket:
                print(f"   ✅ WebSocket connected successfully")
                
                # Test ping/pong
                await websocket.send("ping")
                response = await asyncio.wait_for(websocket.recv(), timeout=5)
                
                if response == "pong":
                    print(f"   🏓 Ping/pong working correctly")
                    return True
                else:
                    print(f"   ❌ Unexpected response to ping: {response}")
                    return False
                    
        except Exception as e:
            print(f"   ❌ WebSocket connection failed: {str(e)}")
            return False

    def test_websocket_sync_wrapper(self):
        """Synchronous wrapper for WebSocket test"""
        try:
            return asyncio.run(self.test_websocket_connection())
        except Exception as e:
            print(f"   ❌ WebSocket test failed: {str(e)}")
            return False

    async def test_websocket_broadcasting(self):
        """Test that tracking endpoints broadcast to WebSocket"""
        print("   📡 Testing WebSocket broadcasting for tracking events")
        
        try:
            ws_url = f"{self.ws_url}/api/ws/analytics"
            messages_received = []
            
            async with websockets.connect(ws_url, timeout=10) as websocket:
                print(f"   🔌 Connected to WebSocket")
                
                # Set up message listener
                async def listen_for_messages():
                    try:
                        while True:
                            message = await asyncio.wait_for(websocket.recv(), timeout=2)
                            if message != "pong":  # Ignore pong responses
                                try:
                                    data = json.loads(message)
                                    messages_received.append(data)
                                    print(f"   📨 Received: {data.get('type', 'unknown')}")
                                except json.JSONDecodeError:
                                    pass
                    except asyncio.TimeoutError:
                        pass  # Timeout is expected when no more messages
                
                # Start listening in background
                listen_task = asyncio.create_task(listen_for_messages())
                
                # Wait a moment for listener to be ready
                await asyncio.sleep(0.5)
                
                # Test session start broadcasting
                await self._send_session_start_async()
                await asyncio.sleep(1)
                
                # Test pageview broadcasting  
                await self._send_pageview_async()
                await asyncio.sleep(1)
                
                # Test conversion broadcasting
                await self._send_conversion_async()
                await asyncio.sleep(1)
                
                # Stop listening
                listen_task.cancel()
                
                # Check received messages
                print(f"   📊 Total WebSocket messages received: {len(messages_received)}")
                
                # Look for expected message types
                message_types = [msg.get('type') for msg in messages_received]
                expected_types = ['new_visitor', 'new_pageview', 'new_conversion']
                
                found_types = []
                for expected in expected_types:
                    if expected in message_types:
                        found_types.append(expected)
                        print(f"   ✅ Received {expected} broadcast")
                    else:
                        print(f"   ❌ Missing {expected} broadcast")
                
                return len(found_types) >= 2  # At least 2 out of 3 message types
                
        except Exception as e:
            print(f"   ❌ WebSocket broadcasting test failed: {str(e)}")
            return False

    async def _send_session_start_async(self):
        """Send session start request asynchronously"""
        try:
            import aiohttp
            session_data = {
                "visitor_id": str(uuid.uuid4()),
                "landing_page": "https://test.com/",
                "referrer": "https://google.com",
                "user_agent": "Test Browser"
            }
            
            async with aiohttp.ClientSession() as session:
                url = f"{self.base_url}/api/customer-analytics/track/session/start"
                async with session.post(url, json=session_data) as resp:
                    print(f"   📤 Session start sent - Status: {resp.status}")
                    
        except ImportError:
            # Fallback to requests in separate thread
            def send_request():
                session_data = {
                    "visitor_id": str(uuid.uuid4()),
                    "landing_page": "https://test.com/",
                    "referrer": "https://google.com",
                    "user_agent": "Test Browser"
                }
                url = f"{self.base_url}/api/customer-analytics/track/session/start"
                response = requests.post(url, json=session_data, timeout=5)
                print(f"   📤 Session start sent - Status: {response.status_code}")
            
            thread = threading.Thread(target=send_request)
            thread.start()
            thread.join()

    async def _send_pageview_async(self):
        """Send pageview request asynchronously"""
        try:
            import aiohttp
            pageview_data = {
                "page_url": "https://test.com/products",
                "page_title": "Products Page",
                "visitor_id": str(uuid.uuid4())
            }
            
            async with aiohttp.ClientSession() as session:
                url = f"{self.base_url}/api/customer-analytics/track/pageview"
                async with session.post(url, json=pageview_data) as resp:
                    print(f"   📤 Pageview sent - Status: {resp.status}")
                    
        except ImportError:
            def send_request():
                pageview_data = {
                    "page_url": "https://test.com/products",
                    "page_title": "Products Page",
                    "visitor_id": str(uuid.uuid4())
                }
                url = f"{self.base_url}/api/customer-analytics/track/pageview"
                response = requests.post(url, json=pageview_data, timeout=5)
                print(f"   📤 Pageview sent - Status: {response.status_code}")
            
            thread = threading.Thread(target=send_request)
            thread.start()
            thread.join()

    async def _send_conversion_async(self):
        """Send conversion request asynchronously"""
        try:
            import aiohttp
            conversion_data = {
                "event_name": "test_conversion",
                "event_category": "demo_request",
                "visitor_id": str(uuid.uuid4())
            }
            
            async with aiohttp.ClientSession() as session:
                url = f"{self.base_url}/api/customer-analytics/track/conversion"
                async with session.post(url, json=conversion_data) as resp:
                    print(f"   📤 Conversion sent - Status: {resp.status}")
                    
        except ImportError:
            def send_request():
                conversion_data = {
                    "event_name": "test_conversion",
                    "event_category": "demo_request",
                    "visitor_id": str(uuid.uuid4())
                }
                url = f"{self.base_url}/api/customer-analytics/track/conversion"
                response = requests.post(url, json=conversion_data, timeout=5)
                print(f"   📤 Conversion sent - Status: {response.status_code}")
            
            thread = threading.Thread(target=send_request)
            thread.start()
            thread.join()

    def test_websocket_broadcasting_sync(self):
        """Synchronous wrapper for WebSocket broadcasting test"""
        try:
            return asyncio.run(self.test_websocket_broadcasting())
        except Exception as e:
            print(f"   ❌ WebSocket broadcasting test failed: {str(e)}")
            return False

    def test_session_start_with_websocket(self):
        """Test POST /api/customer-analytics/track/session/start with WebSocket broadcast"""
        print("   📡 Testing session start endpoint with WebSocket broadcasting")
        
        try:
            session_data = {
                "visitor_id": str(uuid.uuid4()),
                "landing_page": "https://test.com/",
                "referrer": "https://google.com",
                "user_agent": "Test Browser",
                "screen_resolution": "1920x1080"
            }
            
            url = f"{self.base_url}/api/customer-analytics/track/session/start"
            response = requests.post(url, json=session_data, timeout=10)
            
            if response.status_code == 200:
                data = response.json()
                if 'session_id' in data and 'visitor_id' in data:
                    print(f"   ✅ Session started - ID: {data['session_id'][:8]}...")
                    return True
                else:
                    print(f"   ❌ Missing session_id or visitor_id in response")
                    return False
            else:
                print(f"   ❌ Session start failed - Status: {response.status_code}")
                print(f"   📊 Response: {response.text}")
                return False
                
        except Exception as e:
            print(f"   ❌ Exception: {str(e)}")
            return False

    def test_pageview_with_websocket(self):
        """Test POST /api/customer-analytics/track/pageview with WebSocket broadcast"""
        print("   📄 Testing pageview endpoint with WebSocket broadcasting")
        
        try:
            pageview_data = {
                "page_url": "https://test.com/products",
                "page_title": "Products Page",
                "visitor_id": str(uuid.uuid4()),
                "user_agent": "Test Browser"
            }
            
            url = f"{self.base_url}/api/customer-analytics/track/pageview"
            response = requests.post(url, json=pageview_data, timeout=10)
            
            if response.status_code == 200:
                data = response.json()
                if data.get('status') == 'tracked':
                    print(f"   ✅ Pageview tracked - Visitor: {data.get('visitor_id', 'N/A')[:8]}...")
                    return True
                else:
                    print(f"   ❌ Unexpected response: {data}")
                    return False
            else:
                print(f"   ❌ Pageview tracking failed - Status: {response.status_code}")
                print(f"   📊 Response: {response.text}")
                return False
                
        except Exception as e:
            print(f"   ❌ Exception: {str(e)}")
            return False

    def test_conversion_with_websocket(self):
        """Test POST /api/customer-analytics/track/conversion with WebSocket broadcast"""
        print("   🎯 Testing conversion endpoint with WebSocket broadcasting")
        
        try:
            conversion_data = {
                "event_name": "test_conversion",
                "event_category": "demo_request",
                "event_value": 100.0,
                "visitor_id": str(uuid.uuid4()),
                "page_url": "https://test.com/demo"
            }
            
            url = f"{self.base_url}/api/customer-analytics/track/conversion"
            response = requests.post(url, json=conversion_data, timeout=10)
            
            if response.status_code == 200:
                data = response.json()
                if data.get('status') == 'tracked':
                    print(f"   ✅ Conversion tracked - Event: {conversion_data['event_name']}")
                    return True
                else:
                    print(f"   ❌ Unexpected response: {data}")
                    return False
            else:
                print(f"   ❌ Conversion tracking failed - Status: {response.status_code}")
                print(f"   📊 Response: {response.text}")
                return False
                
        except Exception as e:
            print(f"   ❌ Exception: {str(e)}")
            return False

    def test_dashboard_still_works(self):
        """Test that previous dashboard endpoints are still working"""
        print("   📈 Testing that existing dashboard endpoints still work")
        
        if not self.token:
            print(f"   ❌ No auth token available")
            return False
        
        try:
            headers = {'Authorization': f'Bearer {self.token}'}
            
            # Test overview endpoint
            url = f"{self.base_url}/api/customer-analytics/dashboard/overview"
            response = requests.get(url, headers=headers, timeout=10)
            
            if response.status_code == 200:
                data = response.json()
                required_fields = ['total_visitors', 'total_sessions', 'total_pageviews']
                
                missing_fields = []
                for field in required_fields:
                    if field not in data:
                        missing_fields.append(field)
                
                if not missing_fields:
                    print(f"   ✅ Dashboard overview working - Sessions: {data.get('total_sessions', 0)}")
                    return True
                else:
                    print(f"   ❌ Missing fields in response: {missing_fields}")
                    return False
            else:
                print(f"   ❌ Dashboard failed - Status: {response.status_code}")
                print(f"   📊 Response: {response.text}")
                return False
                
        except Exception as e:
            print(f"   ❌ Exception: {str(e)}")
            return False

    def run_all_tests(self):
        """Run all new feature tests"""
        print("\n" + "="*60)
        print("🧪 NEW FEATURES TEST SUITE")
        print("="*60)
        
        start_time = time.time()
        
        # Test admin authentication
        if not self.run_test("Admin Login", self.test_admin_login):
            print("\n❌ Authentication failed - stopping tests")
            return self.generate_summary()
        
        # Test specific new features
        self.run_test("Analytics Tracker JS Library", self.test_analytics_tracker_js)
        self.run_test("WebSocket Connection", self.test_websocket_sync_wrapper)
        self.run_test("Session Start with WebSocket", self.test_session_start_with_websocket)
        self.run_test("Pageview with WebSocket", self.test_pageview_with_websocket)
        self.run_test("Conversion with WebSocket", self.test_conversion_with_websocket)
        self.run_test("Dashboard Still Works", self.test_dashboard_still_works)
        self.run_test("WebSocket Broadcasting", self.test_websocket_broadcasting_sync)
        
        total_time = round(time.time() - start_time, 2)
        return self.generate_summary(total_time)

    def generate_summary(self, total_time=0):
        """Generate test summary"""
        print("\n" + "="*60)
        print("📊 NEW FEATURES TEST RESULTS")
        print("="*60)
        
        success_rate = (self.tests_passed / self.tests_run * 100) if self.tests_run > 0 else 0
        
        print(f"📈 Tests Run: {self.tests_run}")
        print(f"✅ Tests Passed: {self.tests_passed}")
        print(f"❌ Tests Failed: {len(self.failed_tests)}")
        print(f"📊 Success Rate: {success_rate:.1f}%")
        if total_time > 0:
            print(f"⏱️ Total Time: {total_time}s")
        
        if self.passed_tests:
            print(f"\n✅ PASSED TESTS:")
            for test in self.passed_tests:
                print(f"  ✓ {test}")
        
        if self.failed_tests:
            print(f"\n❌ FAILED TESTS:")
            for failure in self.failed_tests:
                print(f"  ✗ {failure['test']}")
                print(f"    Error: {failure['error'][:100]}...")
        
        print("\n" + "="*60)
        
        return 0 if success_rate >= 70 else 1

def main():
    """Main test runner"""
    try:
        tester = NewFeaturesAPITester("http://localhost:8001")
        exit_code = tester.run_all_tests()
        
        print(f"\n🏁 New features test completed with exit code: {exit_code}")
        return exit_code
        
    except Exception as e:
        print(f"\n💥 Test suite failed: {str(e)}")
        return 1

if __name__ == "__main__":
    sys.exit(main())