#!/usr/bin/env python3
"""
CSV and PDF Export Features Backend Test Suite
Tests the new export endpoints added to dashboard_routes.py:
- GET /api/dashboard/export/csv?data_type={sessions,pageviews,conversions,clicks}&days=30
- GET /api/dashboard/export/pdf?days=30
- Error handling for invalid data types
- Authentication requirements
"""

import requests
import json
import sys
import time
import traceback
from datetime import datetime

class ExportFeaturesAPITester:
    def __init__(self, base_url="http://localhost:8001"):
        self.base_url = base_url
        self.token = None
        self.tests_run = 0
        self.tests_passed = 0
        self.failed_tests = []
        self.passed_tests = []
        
        print(f"🚀 Initializing CSV and PDF Export Features Test Suite")
        print(f"📡 Base URL: {base_url}")
        print("=" * 60)

    def run_test(self, name, method, endpoint, expected_status, data=None, params=None, description="", check_content_type=None):
        """Run a single API test with enhanced validation"""
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
                response = requests.get(url, headers=headers, params=params, timeout=30)
            elif method == 'POST':
                response = requests.post(url, json=data, headers=headers, timeout=30)
            
            duration = round(time.time() - start_time, 2)
            
            # Check status code
            if response.status_code == expected_status:
                self.tests_passed += 1
                print(f"   ✅ PASSED - Status: {response.status_code} ({duration}s)")
                self.passed_tests.append(name)
                
                # Additional validations for successful responses
                if expected_status == 200:
                    # Check content type if specified
                    if check_content_type:
                        content_type = response.headers.get('Content-Type', '')
                        if check_content_type in content_type:
                            print(f"   ✅ Correct Content-Type: {content_type}")
                        else:
                            print(f"   ⚠️ Unexpected Content-Type: {content_type} (expected: {check_content_type})")
                    
                    # Check content disposition for downloads
                    content_disp = response.headers.get('Content-Disposition', '')
                    if 'attachment' in content_disp:
                        filename = content_disp.split('filename=')[-1]
                        print(f"   📄 Download file: {filename}")
                    
                    # Check response size
                    content_length = len(response.content) if response.content else 0
                    print(f"   📊 Response size: {content_length} bytes")
                    
                    # For CSV files, check if it contains CSV headers
                    if check_content_type == 'text/csv' and content_length > 0:
                        content_preview = response.text[:200] if response.text else ""
                        if ',' in content_preview:
                            print(f"   ✅ Valid CSV format detected")
                            print(f"   📄 CSV preview: {content_preview[:100]}...")
                        else:
                            print(f"   ⚠️ CSV format might be invalid")
                    
                    # For PDF files, check magic number
                    if check_content_type == 'application/pdf' and content_length > 0:
                        if response.content.startswith(b'%PDF'):
                            print(f"   ✅ Valid PDF format detected")
                        else:
                            print(f"   ⚠️ PDF format might be invalid")
                
                return True, response
            else:
                print(f"   ❌ FAILED - Expected {expected_status}, got {response.status_code}")
                try:
                    error_data = response.json()
                    print(f"   📊 Error: {json.dumps(error_data, indent=2)}")
                except:
                    print(f"   📊 Error: {response.text[:200]}...")
                self.failed_tests.append({
                    "test": name,
                    "expected": expected_status,
                    "actual": response.status_code,
                    "error": response.text
                })
                return False, response
                
        except Exception as e:
            print(f"   ❌ FAILED - Exception: {str(e)}")
            print(f"   📍 Traceback: {traceback.format_exc()}")
            self.failed_tests.append({
                "test": name,
                "error": str(e),
                "traceback": traceback.format_exc()
            })
            return False, None

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
            print(f"🔍 Logging in as platform admin...")
            response = requests.post(login_url, json=login_data, timeout=10)
            
            if response.status_code == 200:
                response_data = response.json()
                if 'access_token' in response_data:
                    self.token = response_data['access_token']
                    print(f"✅ Login successful - Token acquired")
                    print(f"🔐 Token preview: {self.token[:20]}...")
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

    def test_csv_export_endpoints(self):
        """Test all CSV export endpoints"""
        print("\n📊 Testing CSV Export Endpoints")
        print("=" * 40)
        
        if not self.token:
            print("❌ Cannot test export endpoints - no auth token")
            return
        
        # Test all 4 data types for CSV export
        data_types = ["sessions", "pageviews", "conversions", "clicks"]
        
        for data_type in data_types:
            success, response = self.run_test(
                f"CSV Export - {data_type.title()}",
                "GET",
                f"/api/dashboard/export/csv",
                200,
                params={"data_type": data_type, "days": 30},
                description=f"Export {data_type} data as CSV file",
                check_content_type="text/csv"
            )
            
            # Test with different days parameter
            success, response = self.run_test(
                f"CSV Export - {data_type.title()} (7 days)",
                "GET",
                f"/api/dashboard/export/csv",
                200,
                params={"data_type": data_type, "days": 7},
                description=f"Export {data_type} data for last 7 days",
                check_content_type="text/csv"
            )
    
    def test_csv_export_invalid_data_type(self):
        """Test CSV export with invalid data type"""
        print("\n🔍 Testing CSV Export Error Handling")
        print("=" * 45)
        
        if not self.token:
            print("❌ Cannot test export endpoints - no auth token")
            return
        
        # Test invalid data_type parameter
        success, response = self.run_test(
            "CSV Export - Invalid Data Type",
            "GET",
            f"/api/dashboard/export/csv",
            400,
            params={"data_type": "invalid", "days": 30},
            description="Test error handling for invalid data_type parameter"
        )
        
        if response and response.status_code == 400:
            try:
                error_data = response.json()
                if "Invalid data_type" in error_data.get("detail", ""):
                    print(f"   ✅ Proper error message returned")
                else:
                    print(f"   ⚠️ Unexpected error message: {error_data}")
            except:
                print(f"   ⚠️ Could not parse error response")
        
        # Test missing data_type parameter
        success, response = self.run_test(
            "CSV Export - Missing Data Type",
            "GET",
            f"/api/dashboard/export/csv",
            422,
            params={"days": 30},
            description="Test error handling for missing data_type parameter"
        )

    def test_pdf_export_endpoint(self):
        """Test PDF export endpoint"""
        print("\n📄 Testing PDF Export Endpoint")
        print("=" * 35)
        
        if not self.token:
            print("❌ Cannot test export endpoints - no auth token")
            return
        
        # Test PDF export with default 30 days
        success, response = self.run_test(
            "PDF Export - Default (30 days)",
            "GET",
            f"/api/dashboard/export/pdf",
            200,
            params={"days": 30},
            description="Export analytics summary as PDF report",
            check_content_type="application/pdf"
        )
        
        # Test PDF export with different days
        success, response = self.run_test(
            "PDF Export - 7 days",
            "GET", 
            f"/api/dashboard/export/pdf",
            200,
            params={"days": 7},
            description="Export 7-day analytics summary as PDF",
            check_content_type="application/pdf"
        )
        
        # Test PDF export with 90 days
        success, response = self.run_test(
            "PDF Export - 90 days",
            "GET",
            f"/api/dashboard/export/pdf",
            200,
            params={"days": 90},
            description="Export 90-day analytics summary as PDF",
            check_content_type="application/pdf"
        )

    def test_authentication_requirements(self):
        """Test that export endpoints require authentication"""
        print("\n🔐 Testing Authentication Requirements")
        print("=" * 43)
        
        # Save current token
        original_token = self.token
        self.token = None  # Remove auth
        
        # Test CSV export without auth
        success, response = self.run_test(
            "CSV Export - No Authentication",
            "GET",
            f"/api/dashboard/export/csv",
            401,
            params={"data_type": "sessions", "days": 30},
            description="Verify CSV export requires authentication"
        )
        
        # Test PDF export without auth
        success, response = self.run_test(
            "PDF Export - No Authentication",
            "GET",
            f"/api/dashboard/export/pdf",
            401,
            params={"days": 30},
            description="Verify PDF export requires authentication"
        )
        
        # Test with invalid token
        self.token = "invalid.token.here"
        
        success, response = self.run_test(
            "CSV Export - Invalid Token",
            "GET",
            f"/api/dashboard/export/csv",
            401,
            params={"data_type": "sessions", "days": 30},
            description="Verify invalid token is rejected"
        )
        
        # Restore original token
        self.token = original_token

    def test_parameter_validation(self):
        """Test parameter validation for export endpoints"""
        print("\n📋 Testing Parameter Validation")
        print("=" * 38)
        
        if not self.token:
            print("❌ Cannot test export endpoints - no auth token")
            return
        
        # Test invalid days parameter (too low)
        success, response = self.run_test(
            "CSV Export - Invalid Days (0)",
            "GET",
            f"/api/dashboard/export/csv",
            422,
            params={"data_type": "sessions", "days": 0},
            description="Test validation for days parameter (minimum 1)"
        )
        
        # Test invalid days parameter (too high)
        success, response = self.run_test(
            "CSV Export - Invalid Days (999)",
            "GET",
            f"/api/dashboard/export/csv",
            422,
            params={"data_type": "sessions", "days": 999},
            description="Test validation for days parameter (maximum 365)"
        )
        
        # Test invalid days parameter for PDF
        success, response = self.run_test(
            "PDF Export - Invalid Days (0)",
            "GET",
            f"/api/dashboard/export/pdf",
            422,
            params={"days": 0},
            description="Test validation for PDF days parameter"
        )

    def test_content_headers_and_format(self):
        """Test response headers and file format validation"""
        print("\n📁 Testing Content Headers and Format")
        print("=" * 42)
        
        if not self.token:
            print("❌ Cannot test export endpoints - no auth token")
            return
        
        # Test CSV headers and filename
        success, response = self.run_test(
            "CSV Headers Validation",
            "GET",
            f"/api/dashboard/export/csv",
            200,
            params={"data_type": "sessions", "days": 30},
            description="Validate CSV response headers and filename"
        )
        
        if success and response:
            # Check specific headers
            headers = response.headers
            print(f"   📋 Content-Type: {headers.get('Content-Type', 'N/A')}")
            print(f"   📄 Content-Disposition: {headers.get('Content-Disposition', 'N/A')}")
            
            # Validate filename pattern
            content_disp = headers.get('Content-Disposition', '')
            if 'analytics_sessions_30days.csv' in content_disp:
                print(f"   ✅ Correct filename pattern detected")
            else:
                print(f"   ⚠️ Unexpected filename pattern")
        
        # Test PDF headers and filename
        success, response = self.run_test(
            "PDF Headers Validation",
            "GET",
            f"/api/dashboard/export/pdf",
            200,
            params={"days": 30},
            description="Validate PDF response headers and filename"
        )
        
        if success and response:
            headers = response.headers
            print(f"   📋 Content-Type: {headers.get('Content-Type', 'N/A')}")
            print(f"   📄 Content-Disposition: {headers.get('Content-Disposition', 'N/A')}")
            
            # Validate filename contains date
            content_disp = headers.get('Content-Disposition', '')
            current_date = datetime.now().strftime('%Y%m%d')
            if current_date in content_disp and '.pdf' in content_disp:
                print(f"   ✅ Correct PDF filename with date detected")
            else:
                print(f"   ⚠️ Unexpected PDF filename pattern")

    def run_all_tests(self):
        """Run all export feature tests in sequence"""
        print("\n" + "="*60)
        print("🧪 CSV AND PDF EXPORT FEATURES TEST SUITE")
        print("="*60)
        
        start_time = time.time()
        
        # Step 1: Authentication
        if not self.test_admin_login():
            print("\n❌ Authentication failed - stopping tests")
            return self.generate_summary()
        
        # Step 2: Test CSV export endpoints
        self.test_csv_export_endpoints()
        
        # Step 3: Test CSV error handling
        self.test_csv_export_invalid_data_type()
        
        # Step 4: Test PDF export endpoint
        self.test_pdf_export_endpoint()
        
        # Step 5: Test authentication requirements
        self.test_authentication_requirements()
        
        # Step 6: Test parameter validation
        self.test_parameter_validation()
        
        # Step 7: Test content headers and format
        self.test_content_headers_and_format()
        
        # Generate final summary
        total_time = round(time.time() - start_time, 2)
        return self.generate_summary(total_time)

    def generate_summary(self, total_time=0):
        """Generate test summary"""
        print("\n" + "="*60)
        print("📊 EXPORT FEATURES TEST RESULTS SUMMARY")
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
        
        # Summary of features tested
        print("🔍 FEATURES TESTED:")
        print("✓ CSV Export for sessions, pageviews, conversions, clicks")
        print("✓ PDF Export for analytics reports")
        print("✓ Error handling for invalid data types")
        print("✓ Authentication requirements (platform_admin)")
        print("✓ Parameter validation (days range)")
        print("✓ Response headers and file formats")
        print("=" * 60)
        
        # Return status for exit code
        return 0 if success_rate >= 80 else 1

def main():
    """Main test runner"""
    try:
        # Use provided backend URL
        tester = ExportFeaturesAPITester("http://localhost:8001")
        exit_code = tester.run_all_tests()
        
        print(f"\n🏁 Export features test suite completed with exit code: {exit_code}")
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