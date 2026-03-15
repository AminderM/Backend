#!/usr/bin/env python3
"""
Customer Analytics API Backend Test Suite
Tests all 22 API endpoints for the customer analytics system.
"""

import requests
import json
import sys
from datetime import datetime, timedelta
import uuid
import time
import traceback

class CustomerAnalyticsAPITester:
    def __init__(self, base_url="http://localhost:8001"):
        self.base_url = base_url
        self.token = None
        self.tests_run = 0
        self.tests_passed = 0
        self.session_id = None
        self.visitor_id = None
        self.failed_tests = []
        self.passed_tests = []
        
        print(f"🚀 Initializing Customer Analytics API Tester")
        print(f"📡 Base URL: {base_url}")
        print("=" * 60)

    def run_test(self, name, method, endpoint, expected_status, data=None, params=None, description=""):
        """Run a single API test"""
        url = f"{self.base_url}/api/customer-analytics{endpoint}"
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
                        if 'session_id' in response_data:
                            self.session_id = response_data['session_id']
                        if 'visitor_id' in response_data:
                            self.visitor_id = response_data['visitor_id']
                        print(f"   📊 Response: {json.dumps(response_data, indent=2)[:200]}...")
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

    def test_public_tracking_endpoints(self):
        """Test all public tracking endpoints (no auth required)"""
        print("\n📊 Testing Public Tracking Endpoints")
        print("=" * 45)
        
        # Generate test IDs
        test_visitor_id = str(uuid.uuid4())
        
        # 1. Start session
        session_data = {
            "visitor_id": test_visitor_id,
            "landing_page": "https://example.com/",
            "referrer": "https://google.com",
            "user_agent": "Mozilla/5.0 Test Browser",
            "screen_resolution": "1920x1080",
            "language": "en-US",
            "timezone": "America/New_York",
            "utm_source": "google",
            "utm_medium": "cpc",
            "utm_campaign": "test_campaign"
        }
        
        success, response = self.run_test(
            "Start Session",
            "POST",
            "/track/session/start",
            200,
            data=session_data,
            description="Initialize new tracking session"
        )
        
        if success and 'session_id' in response:
            session_id = response['session_id']
            visitor_id = response['visitor_id']
            print(f"   🆔 Session ID: {session_id}")
            print(f"   👤 Visitor ID: {visitor_id}")
            self.session_id = session_id
            self.visitor_id = visitor_id
        
        # 2. Track pageview
        pageview_data = {
            "page_url": "https://example.com/products",
            "page_title": "Products - Test Site",
            "referrer": "https://example.com/",
            "session_id": self.session_id,
            "visitor_id": self.visitor_id,
            "user_agent": "Mozilla/5.0 Test Browser",
            "screen_resolution": "1920x1080",
            "viewport_size": "1200x800",
            "language": "en-US",
            "timezone": "America/New_York"
        }
        
        self.run_test(
            "Track Page View",
            "POST",
            "/track/pageview",
            200,
            data=pageview_data,
            description="Track page view event"
        )
        
        # 3. Track click event
        click_data = {
            "page_url": "https://example.com/products",
            "element_id": "buy-button",
            "element_class": "btn btn-primary",
            "element_tag": "button",
            "element_text": "Buy Now",
            "x_position": 150,
            "y_position": 300,
            "viewport_width": 1200,
            "viewport_height": 800,
            "session_id": self.session_id,
            "visitor_id": self.visitor_id
        }
        
        self.run_test(
            "Track Click Event",
            "POST",
            "/track/click",
            200,
            data=click_data,
            description="Track click for heatmap data"
        )
        
        # 4. Track scroll event
        scroll_data = {
            "page_url": "https://example.com/products",
            "scroll_depth_percent": 75,
            "max_scroll_depth": 80,
            "time_on_page": 45,
            "session_id": self.session_id,
            "visitor_id": self.visitor_id
        }
        
        self.run_test(
            "Track Scroll Event",
            "POST",
            "/track/scroll",
            200,
            data=scroll_data,
            description="Track scroll depth for engagement"
        )
        
        # 5. Track form interaction
        form_data = {
            "page_url": "https://example.com/contact",
            "form_id": "contact-form",
            "form_name": "Contact Form",
            "event_type": "submit",
            "field_name": "email",
            "time_spent": 30,
            "session_id": self.session_id,
            "visitor_id": self.visitor_id,
            "form_data": {"email": "test@example.com", "name": "Test User"}
        }
        
        self.run_test(
            "Track Form Interaction",
            "POST",
            "/track/form",
            200,
            data=form_data,
            description="Track form submit event"
        )
        
        # 6. Track conversion
        conversion_data = {
            "event_name": "demo_request",
            "event_category": "demo_request",
            "event_value": 100.0,
            "page_url": "https://example.com/demo",
            "session_id": self.session_id,
            "visitor_id": self.visitor_id,
            "metadata": {"source": "website", "type": "form"}
        }
        
        self.run_test(
            "Track Conversion Event",
            "POST",
            "/track/conversion",
            200,
            data=conversion_data,
            description="Track conversion event"
        )
        
        # 7. Track custom event
        custom_data = {
            "event_name": "video_played",
            "event_data": {"video_id": "intro-video", "duration": 120},
            "page_url": "https://example.com/videos",
            "session_id": self.session_id,
            "visitor_id": self.visitor_id
        }
        
        self.run_test(
            "Track Custom Event",
            "POST",
            "/track/custom",
            200,
            data=custom_data,
            description="Track custom event"
        )
        
        # 8. End session
        self.run_test(
            "End Session",
            "POST",
            f"/track/session/end?session_id={self.session_id}&duration_seconds=300",
            200,
            description="End tracking session"
        )

    def test_dashboard_endpoints(self):
        """Test all dashboard endpoints (auth required)"""
        print("\n📈 Testing Dashboard Endpoints (Auth Required)")
        print("=" * 50)
        
        if not self.token:
            print("❌ Cannot test dashboard endpoints - no auth token")
            return
        
        # Wait a moment for data to be processed
        print("⏳ Waiting 2 seconds for data processing...")
        time.sleep(2)
        
        # 9. Analytics overview
        self.run_test(
            "Analytics Overview",
            "GET",
            "/dashboard/overview?days=30",
            200,
            description="Get dashboard analytics overview"
        )
        
        # 10. Real-time stats
        self.run_test(
            "Real-time Stats",
            "GET",
            "/dashboard/realtime",
            200,
            description="Get real-time visitor statistics"
        )
        
        # 11. Traffic sources
        self.run_test(
            "Traffic Sources",
            "GET",
            "/dashboard/traffic-sources?days=30",
            200,
            description="Get traffic source breakdown"
        )
        
        # 12. Top pages
        self.run_test(
            "Top Pages",
            "GET",
            "/dashboard/top-pages?days=30&limit=20",
            200,
            description="Get top pages by views"
        )
        
        # 13. User journeys
        self.run_test(
            "User Journeys",
            "GET",
            "/dashboard/user-journeys?days=30&limit=20",
            200,
            description="Get user journey paths"
        )
        
        # 14. Funnel analysis
        self.run_test(
            "Funnel Analysis",
            "GET",
            "/dashboard/funnel-analysis?days=30",
            200,
            description="Get conversion funnel analysis"
        )
        
        # 15. Heatmap data
        self.run_test(
            "Heatmap Data",
            "GET",
            "/dashboard/heatmap-data?page_url=https://example.com/products&days=30",
            200,
            description="Get heatmap data for specific page"
        )
        
        # 16. Form analytics
        self.run_test(
            "Form Analytics",
            "GET",
            "/dashboard/form-analytics?days=30",
            200,
            description="Get form interaction analytics"
        )
        
        # 17. Conversion analytics
        self.run_test(
            "Conversion Analytics",
            "GET",
            "/dashboard/conversion-analytics?days=30",
            200,
            description="Get conversion analytics"
        )
        
        # 18. Visitor activity log
        self.run_test(
            "Visitor Activity Log",
            "GET",
            "/dashboard/visitor-activity-log?days=7&limit=100",
            200,
            description="Get visitor activity log"
        )

    def test_configuration_endpoints(self):
        """Test custom event configuration endpoints"""
        print("\n⚙️ Testing Configuration Endpoints")
        print("=" * 40)
        
        if not self.token:
            print("❌ Cannot test config endpoints - no auth token")
            return
        
        # 19. Get event configs
        self.run_test(
            "Get Event Configs",
            "GET",
            "/config/events",
            200,
            description="Get all custom event configurations"
        )
        
        # 20. Create event config
        config_data = {
            "name": "button_click_test",
            "description": "Test button click tracking",
            "event_selector": ".test-button",
            "event_type": "click",
            "category": "engagement",
            "is_conversion": False,
            "is_active": True
        }
        
        success, response = self.run_test(
            "Create Event Config",
            "POST",
            "/config/events",
            200,
            data=config_data,
            description="Create custom event configuration"
        )
        
        config_id = None
        if success and 'config' in response and 'id' in response['config']:
            config_id = response['config']['id']
            print(f"   🆔 Created config ID: {config_id}")

    def test_reports_endpoints(self):
        """Test reports and export endpoints"""
        print("\n📋 Testing Reports & Export Endpoints")
        print("=" * 43)
        
        if not self.token:
            print("❌ Cannot test reports endpoints - no auth token")
            return
        
        # 21. Summary report
        start_date = (datetime.now() - timedelta(days=30)).isoformat()
        end_date = datetime.now().isoformat()
        
        self.run_test(
            "Summary Report",
            "GET",
            f"/reports/summary?start_date={start_date}&end_date={end_date}",
            200,
            description="Get comprehensive summary report"
        )
        
        # 22. Export data
        self.run_test(
            "Export Sessions Data",
            "GET",
            f"/reports/export?data_type=sessions&start_date={start_date}&end_date={end_date}&format=json",
            200,
            description="Export sessions analytics data"
        )

    def run_all_tests(self):
        """Run all tests in sequence"""
        print("\n" + "="*60)
        print("🧪 CUSTOMER ANALYTICS API TEST SUITE")
        print("="*60)
        
        start_time = time.time()
        
        # Step 1: Authentication
        if not self.test_admin_login():
            print("\n❌ Authentication failed - stopping tests")
            return self.generate_summary()
        
        # Step 2: Public tracking endpoints (no auth)
        self.test_public_tracking_endpoints()
        
        # Step 3: Dashboard endpoints (auth required)
        self.test_dashboard_endpoints()
        
        # Step 4: Configuration endpoints
        self.test_configuration_endpoints()
        
        # Step 5: Reports endpoints
        self.test_reports_endpoints()
        
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
        # Use provided backend URL
        tester = CustomerAnalyticsAPITester("http://localhost:8001")
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