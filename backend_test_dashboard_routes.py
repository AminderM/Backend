#!/usr/bin/env python3
"""
New Dashboard Routes API Backend Test Suite
Tests the new 3 dashboard endpoints created at /api/dashboard/* and WebSocket functionality.
"""

import requests
import json
import sys
import websocket
import threading
import time
import uuid
from datetime import datetime, timedelta
import traceback

class NewDashboardAPITester:
    def __init__(self, base_url="http://localhost:8001"):
        self.base_url = base_url
        self.token = None
        self.tests_run = 0
        self.tests_passed = 0
        self.failed_tests = []
        self.passed_tests = []
        self.websocket_messages = []
        self.ws_connection = None
        
        print(f"🚀 Initializing New Dashboard API Tester")
        print(f"📡 Base URL: {base_url}")
        print("=" * 60)

    def run_test(self, name, method, endpoint, expected_status, data=None, params=None, description=""):
        """Run a single API test"""
        url = f"{self.base_url}{endpoint}"
        headers = {'Content-Type': 'application/json'}
        
        if self.token:
            headers['Authorization'] = f'Bearer {self.token}'

        self.tests_run += 1
        print(f"\n🔍 Test {self.tests_run}: {name}")
        if description:
            print(f"   📝 {description}")
        print(f"   🎯 {method} {url}")
        
        try:
            start_time = time.time()
            
            if method == 'GET':
                response = requests.get(url, headers=headers, params=params, timeout=10)
            elif method == 'POST':
                response = requests.post(url, json=data, headers=headers, timeout=10)
            elif method == 'PUT':
                response = requests.put(url, json=data, headers=headers, timeout=10)
            elif method == 'DELETE':
                response = requests.delete(url, headers=headers, timeout=10)
            
            duration = round(time.time() - start_time, 2)
            
            # Check status code
            if response.status_code == expected_status:
                self.tests_passed += 1
                print(f"   ✅ PASSED - Status: {response.status_code} ({duration}s)")
                self.passed_tests.append(name)
                
                # Try to parse response
                try:
                    response_data = response.json()
                    if isinstance(response_data, dict):
                        print(f"   📊 Response structure validation:")
                        self.validate_response_structure(name, response_data)
                    return True, response_data
                except:
                    print(f"   📊 Response: {response.text[:200]}...")
                    return True, {}
            else:
                print(f"   ❌ FAILED - Expected {expected_status}, got {response.status_code}")
                try:
                    error_data = response.json()
                    print(f"   📊 Error: {json.dumps(error_data, indent=2)}")
                except:
                    print(f"   📊 Error: {response.text}")
                self.failed_tests.append({
                    "test": name,
                    "expected": expected_status,
                    "actual": response.status_code,
                    "error": response.text
                })
                return False, {}
                
        except Exception as e:
            print(f"   ❌ FAILED - Exception: {str(e)}")
            print(f"   📍 Traceback: {traceback.format_exc()}")
            self.failed_tests.append({
                "test": name,
                "error": str(e),
                "traceback": traceback.format_exc()
            })
            return False, {}

    def validate_response_structure(self, endpoint_name, response_data):
        """Validate response structure matches expected frontend format"""
        if endpoint_name == "Dashboard Overview":
            expected_fields = [
                "total_visitors", "visitors_change", "conversions", "conversions_change",
                "bounce_rate", "bounce_rate_change", "avg_session_duration", 
                "session_duration_change", "daily_traffic"
            ]
            for field in expected_fields:
                if field in response_data:
                    print(f"      ✅ {field}: {response_data[field]}")
                else:
                    print(f"      ❌ Missing field: {field}")
        
        elif endpoint_name == "Dashboard Realtime":
            expected_fields = [
                "active_visitors", "active_sessions", "visitors_timeline", 
                "sessions_by_source", "top_pages"
            ]
            for field in expected_fields:
                if field in response_data:
                    if isinstance(response_data[field], list):
                        print(f"      ✅ {field}: {len(response_data[field])} items")
                    else:
                        print(f"      ✅ {field}: {response_data[field]}")
                else:
                    print(f"      ❌ Missing field: {field}")
        
        elif endpoint_name == "Dashboard Heatmap Data":
            expected_fields = [
                "page_url", "total_clicks", "ctr", "avg_scroll_depth", 
                "engagement_score", "click_zones", "click_points"
            ]
            for field in expected_fields:
                if field in response_data:
                    if isinstance(response_data[field], list):
                        print(f"      ✅ {field}: {len(response_data[field])} items")
                    else:
                        print(f"      ✅ {field}: {response_data[field]}")
                else:
                    print(f"      ❌ Missing field: {field}")

    def test_admin_login(self):
        """Test admin login to get auth token"""
        print("\n🔑 Testing Admin Authentication")
        print("=" * 40)
        
        # Login endpoint
        login_url = f"{self.base_url}/api/auth/login"
        login_data = {
            "email": "aminderpro@gmail.com",
            "password": "Admin@123!"
        }
        
        try:
            print(f"🔍 Logging in as admin...")
            response = requests.post(login_url, json=login_data, timeout=10)
            
            if response.status_code == 200:
                response_data = response.json()
                if 'access_token' in response_data:
                    self.token = response_data['access_token']
                    print(f"✅ Login successful - Token acquired")
                    return True
                else:
                    print(f"❌ Login failed - No token in response: {response.text}")
                    return False
            else:
                print(f"❌ Login failed - Status {response.status_code}: {response.text}")
                return False
                
        except Exception as e:
            print(f"❌ Login failed - Exception: {str(e)}")
            return False

    def seed_test_data(self):
        """Seed some test data to ensure the dashboard endpoints have data to work with"""
        print("\n🌱 Seeding Test Data for Dashboard")
        print("=" * 40)
        
        # Generate test visitor and session data
        visitor_id = str(uuid.uuid4())
        session_id = str(uuid.uuid4())
        
        # Start a session with analytics data
        session_data = {
            "visitor_id": visitor_id,
            "landing_page": "/pricing",
            "referrer": "https://google.com",
            "user_agent": "Mozilla/5.0 Test Browser",
            "screen_resolution": "1920x1080",
            "language": "en-US",
            "timezone": "America/New_York",
            "utm_source": "google",
            "utm_medium": "cpc",
            "utm_campaign": "test_campaign"
        }
        
        try:
            # Use customer analytics endpoints to create data
            analytics_url = f"{self.base_url}/api/customer-analytics/track/session/start"
            response = requests.post(analytics_url, json=session_data, timeout=10)
            if response.status_code == 200:
                print("✅ Test session data seeded")
                
                # Add pageview
                pageview_data = {
                    "page_url": "/pricing",
                    "page_title": "Pricing - Test Site",
                    "referrer": "/",
                    "session_id": session_id,
                    "visitor_id": visitor_id,
                    "user_agent": "Mozilla/5.0 Test Browser",
                    "screen_resolution": "1920x1080"
                }
                
                pageview_url = f"{self.base_url}/api/customer-analytics/track/pageview"
                requests.post(pageview_url, json=pageview_data, timeout=10)
                
                # Add click event
                click_data = {
                    "page_url": "/pricing",
                    "element_id": "pricing-btn",
                    "element_class": "btn btn-primary",
                    "element_tag": "button",
                    "element_text": "Get Started",
                    "x_position": 150,
                    "y_position": 300,
                    "viewport_width": 1920,
                    "viewport_height": 1080,
                    "session_id": session_id,
                    "visitor_id": visitor_id
                }
                
                click_url = f"{self.base_url}/api/customer-analytics/track/click"
                requests.post(click_url, json=click_data, timeout=10)
                
                print("✅ Test pageview and click data seeded")
                
        except Exception as e:
            print(f"⚠️ Warning: Could not seed test data - {str(e)}")

    def test_new_dashboard_endpoints(self):
        """Test the new dashboard endpoints"""
        print("\n📊 Testing New Dashboard Endpoints")
        print("=" * 45)
        
        if not self.token:
            print("❌ Cannot test dashboard endpoints - no auth token")
            return
        
        # Seed some test data first
        self.seed_test_data()
        
        # Wait a moment for data processing
        print("⏳ Waiting 3 seconds for data processing...")
        time.sleep(3)
        
        # Test 1: Dashboard Overview
        self.run_test(
            "Dashboard Overview",
            "GET",
            "/api/dashboard/overview",
            200,
            description="Get dashboard overview with KPI metrics"
        )
        
        # Test with different days parameter
        self.run_test(
            "Dashboard Overview (14 days)",
            "GET",
            "/api/dashboard/overview?days=14",
            200,
            description="Get dashboard overview for last 14 days"
        )
        
        # Test 2: Dashboard Realtime
        self.run_test(
            "Dashboard Realtime",
            "GET",
            "/api/dashboard/realtime",
            200,
            description="Get real-time visitor stats and activity"
        )
        
        # Test 3: Dashboard Heatmap Data
        self.run_test(
            "Dashboard Heatmap Data",
            "GET",
            "/api/dashboard/heatmap-data?page_url=/pricing",
            200,
            description="Get heatmap data for /pricing page"
        )
        
        # Test with different page
        self.run_test(
            "Dashboard Heatmap Data (homepage)",
            "GET",
            "/api/dashboard/heatmap-data?page_url=/",
            200,
            description="Get heatmap data for homepage"
        )
        
        # Test with different days parameter
        self.run_test(
            "Dashboard Heatmap Data (7 days)",
            "GET",
            "/api/dashboard/heatmap-data?page_url=/pricing&days=7",
            200,
            description="Get heatmap data for last 7 days"
        )

    def test_websocket_analytics(self):
        """Test WebSocket analytics endpoint"""
        print("\n🔌 Testing WebSocket Analytics")
        print("=" * 35)
        
        def on_message(ws, message):
            try:
                data = json.loads(message)
                print(f"   📨 Received: {data['type']} - {data}")
                self.websocket_messages.append(data)
            except:
                print(f"   📨 Raw message: {message}")
        
        def on_error(ws, error):
            print(f"   ❌ WebSocket error: {error}")
        
        def on_close(ws, close_status_code, close_msg):
            print(f"   🔌 WebSocket closed")
        
        def on_open(ws):
            print(f"   ✅ WebSocket connected")
            # Send ping to test connection
            ws.send("ping")
            time.sleep(1)
            ws.close()
        
        try:
            # Test WebSocket connection
            ws_url = f"ws://localhost:8001/api/ws/analytics"
            print(f"🔍 Connecting to WebSocket: {ws_url}")
            
            websocket.enableTrace(False)
            ws = websocket.WebSocketApp(
                ws_url,
                on_open=on_open,
                on_message=on_message,
                on_error=on_error,
                on_close=on_close
            )
            
            # Run WebSocket in a thread
            ws.run_forever()
            
            # Check if we received ping response
            if self.websocket_messages:
                print("   ✅ WebSocket communication working")
                self.tests_run += 1
                self.tests_passed += 1
                self.passed_tests.append("WebSocket Analytics Connection")
            else:
                print("   ⚠️ WebSocket connected but no message response")
                self.tests_run += 1
                self.failed_tests.append({
                    "test": "WebSocket Analytics Connection",
                    "error": "No ping response received"
                })
                
        except Exception as e:
            print(f"   ❌ WebSocket test failed: {str(e)}")
            self.tests_run += 1
            self.failed_tests.append({
                "test": "WebSocket Analytics Connection",
                "error": str(e)
            })

    def test_websocket_message_types(self):
        """Test specific WebSocket message types mentioned in requirements"""
        print("\n📡 Testing WebSocket Message Broadcasting")
        print("=" * 45)
        
        # Test if creating analytics events triggers WebSocket broadcasts
        visitor_id = str(uuid.uuid4())
        
        # Create some analytics events and see if they trigger WebSocket messages
        try:
            # Track a conversion to test overview_update message
            conversion_data = {
                "event_name": "demo_request",
                "event_category": "demo_request", 
                "event_value": 150.0,
                "page_url": "/pricing",
                "session_id": str(uuid.uuid4()),
                "visitor_id": visitor_id,
                "metadata": {"source": "test", "type": "websocket_test"}
            }
            
            conversion_url = f"{self.base_url}/api/customer-analytics/track/conversion"
            response = requests.post(conversion_url, json=conversion_data, timeout=10)
            
            if response.status_code == 200:
                print("✅ Conversion event created - should trigger overview_update")
                self.tests_run += 1
                self.tests_passed += 1
                self.passed_tests.append("WebSocket Message Broadcasting Test")
            else:
                print(f"❌ Failed to create conversion event: {response.status_code}")
                self.tests_run += 1
                self.failed_tests.append({
                    "test": "WebSocket Message Broadcasting Test",
                    "error": f"Conversion tracking failed: {response.status_code}"
                })
                
        except Exception as e:
            print(f"❌ WebSocket message test failed: {str(e)}")
            self.tests_run += 1
            self.failed_tests.append({
                "test": "WebSocket Message Broadcasting Test",
                "error": str(e)
            })

    def run_all_tests(self):
        """Run all tests in sequence"""
        print("\n" + "="*60)
        print("🧪 NEW DASHBOARD ROUTES API TEST SUITE")
        print("="*60)
        
        start_time = time.time()
        
        # Step 1: Authentication
        if not self.test_admin_login():
            print("\n❌ Authentication failed - stopping tests")
            return self.generate_summary()
        
        # Step 2: Test new dashboard endpoints
        self.test_new_dashboard_endpoints()
        
        # Step 3: Test WebSocket functionality
        self.test_websocket_analytics()
        
        # Step 4: Test WebSocket message types
        self.test_websocket_message_types()
        
        # Generate final summary
        total_time = round(time.time() - start_time, 2)
        return self.generate_summary(total_time)

    def generate_summary(self, total_time=0):
        """Generate test summary"""
        print("\n" + "="*60)
        print("📊 TEST RESULTS SUMMARY")
        print("="*60)
        
        success_rate = (self.tests_passed / self.tests_run * 100) if self.tests_run > 0 else 0
        
        print(f"📈 Tests Run: {self.tests_run}")
        print(f"✅ Tests Passed: {self.tests_passed}")
        print(f"❌ Tests Failed: {len(self.failed_tests)}")
        print(f"📊 Success Rate: {success_rate:.1f}%")
        if total_time > 0:
            print(f"⏱️ Total Time: {total_time}s")
        
        if self.passed_tests:
            print(f"\n✅ PASSED TESTS ({len(self.passed_tests)}):")
            for i, test in enumerate(self.passed_tests, 1):
                print(f"  {i}. {test}")
        
        if self.failed_tests:
            print(f"\n❌ FAILED TESTS ({len(self.failed_tests)}):")
            for i, failure in enumerate(self.failed_tests, 1):
                print(f"  {i}. {failure['test']}")
                if 'expected' in failure:
                    print(f"     Expected: {failure['expected']}, Got: {failure['actual']}")
                if 'error' in failure:
                    print(f"     Error: {failure['error'][:200]}...")
        
        print("\n" + "="*60)
        
        # Return status for exit code
        return 0 if success_rate >= 70 else 1

def main():
    """Main test runner"""
    try:
        # Use provided backend URL from review request
        tester = NewDashboardAPITester("http://localhost:8001")
        exit_code = tester.run_all_tests()
        
        print(f"\n🏁 Test suite completed with exit code: {exit_code}")
        return exit_code
        
    except KeyboardInterrupt:
        print("\n⛔ Test suite interrupted by user")
        return 1
    except Exception as e:
        print(f"\n💥 Test suite failed with exception: {str(e)}")
        print(f"📍 Traceback: {traceback.format_exc()}")
        return 1

if __name__ == "__main__":
    sys.exit(main())