#!/usr/bin/env python3
"""
Scheduled Email Reports API Backend Test Suite
Tests all scheduled reports endpoints including validation and admin authentication.
"""

import requests
import json
import sys
from datetime import datetime, timedelta
import uuid
import time
import traceback

class ScheduledReportsAPITester:
    def __init__(self, base_url="http://localhost:8001"):
        self.base_url = base_url
        self.token = None
        self.tests_run = 0
        self.tests_passed = 0
        self.failed_tests = []
        self.passed_tests = []
        self.created_schedule_ids = []  # Track created schedules for cleanup
        
        print(f"🚀 Initializing Scheduled Reports API Tester")
        print(f"📡 Base URL: {base_url}")
        print("=" * 60)

    def run_test(self, name, method, endpoint, expected_status, data=None, params=None, description=""):
        """Run a single API test"""
        url = f"{self.base_url}/api{endpoint}"
        headers = {'Content-Type': 'application/json'}
        
        if self.token:
            headers['Authorization'] = f'Bearer {self.token}'

        self.tests_run += 1
        print(f"\n🔍 Test {self.tests_run}: {name}")
        if description:
            print(f"   📝 {description}")
        print(f"   🎯 {method} {url}")
        if data:
            print(f"   📤 Data: {json.dumps(data, indent=2)}")
        
        try:
            start_time = time.time()
            
            if method == 'GET':
                response = requests.get(url, headers=headers, params=params, timeout=30)
            elif method == 'POST':
                response = requests.post(url, json=data, headers=headers, timeout=30)
            elif method == 'PUT':
                response = requests.put(url, json=data, headers=headers, timeout=30)
            elif method == 'DELETE':
                response = requests.delete(url, headers=headers, timeout=30)

            response_time = round(time.time() - start_time, 3)
            
            success = response.status_code == expected_status
            if success:
                self.tests_passed += 1
                print(f"   ✅ PASSED - Status: {response.status_code} ({response_time}s)")
                self.passed_tests.append(f"{name} - {method} {endpoint}")
                
                # Try to parse JSON response
                try:
                    response_data = response.json()
                    if response_data and len(str(response_data)) < 200:
                        print(f"   📥 Response: {json.dumps(response_data, indent=2)}")
                    return True, response_data
                except:
                    return True, {}
            else:
                print(f"   ❌ FAILED - Expected {expected_status}, got {response.status_code} ({response_time}s)")
                try:
                    error_data = response.json() if response.content else {}
                    print(f"   📥 Error Response: {json.dumps(error_data, indent=2)}")
                    self.failed_tests.append(f"{name} - Expected {expected_status}, got {response.status_code}: {error_data}")
                except:
                    print(f"   📥 Raw Response: {response.text}")
                    self.failed_tests.append(f"{name} - Expected {expected_status}, got {response.status_code}: {response.text}")
                return False, {}

        except Exception as e:
            print(f"   ❌ FAILED - Exception: {str(e)}")
            self.failed_tests.append(f"{name} - Exception: {str(e)}")
            return False, {}

    def test_admin_login(self, email, password):
        """Test admin login to get authentication token"""
        success, response = self.run_test(
            "Admin Login",
            "POST",
            "/auth/login",
            200,
            data={"email": email, "password": password},
            description="Authenticate as platform admin to access scheduled reports"
        )
        
        if success:
            # Check for token in response
            token = response.get('token') or response.get('access_token')
            if token:
                self.token = token
                print(f"   🔑 Admin token obtained successfully")
                return True
            else:
                print(f"   ⚠️ No token found in response: {response}")
                return False
        else:
            print(f"   ⚠️ Admin login failed - cannot proceed with protected endpoints")
            return False

    def test_create_schedule_validation(self):
        """Test input validation for creating schedules"""
        print("\n" + "="*50)
        print("📋 TESTING SCHEDULE CREATION VALIDATION")
        print("="*50)
        
        # Test invalid frequency
        self.run_test(
            "Create Schedule - Invalid Frequency",
            "POST",
            "/dashboard/reports/schedule",
            422,
            data={
                "frequency": "invalid",
                "email": "test@example.com",
                "report_type": "full",
                "time": "09:00"
            },
            description="Should reject invalid frequency values"
        )
        
        # Test invalid report_type
        self.run_test(
            "Create Schedule - Invalid Report Type",
            "POST", 
            "/dashboard/reports/schedule",
            422,
            data={
                "frequency": "daily",
                "email": "test@example.com", 
                "report_type": "invalid",
                "time": "09:00"
            },
            description="Should reject invalid report_type values"
        )
        
        # Test invalid time format
        self.run_test(
            "Create Schedule - Invalid Time Format",
            "POST",
            "/dashboard/reports/schedule", 
            422,
            data={
                "frequency": "daily",
                "email": "test@example.com",
                "report_type": "full",
                "time": "25:70"  # Invalid time
            },
            description="Should reject invalid HH:MM time format"
        )
        
        # Test invalid email format
        self.run_test(
            "Create Schedule - Invalid Email",
            "POST",
            "/dashboard/reports/schedule",
            422,
            data={
                "frequency": "daily",
                "email": "not-an-email",
                "report_type": "full", 
                "time": "09:00"
            },
            description="Should reject invalid email addresses"
        )

    def test_create_schedules(self):
        """Test creating different types of schedules"""
        print("\n" + "="*50)
        print("📅 TESTING SCHEDULE CREATION")
        print("="*50)
        
        # Create daily schedule
        success, response = self.run_test(
            "Create Daily Schedule",
            "POST",
            "/dashboard/reports/schedule",
            200,
            data={
                "frequency": "daily",
                "email": "daily@example.com",
                "report_type": "full",
                "time": "09:00",
                "timezone": "UTC",
                "include_csv": True,
                "report_days": 7
            },
            description="Create a daily scheduled report with CSV attachments"
        )
        
        if success and response.get('schedule', {}).get('id'):
            self.created_schedule_ids.append(response['schedule']['id'])
        
        # Create weekly schedule
        success, response = self.run_test(
            "Create Weekly Schedule",
            "POST",
            "/dashboard/reports/schedule", 
            200,
            data={
                "frequency": "weekly",
                "email": "weekly@example.com",
                "report_type": "summary",
                "day_of_week": 1,  # Monday
                "time": "08:30",
                "timezone": "UTC",
                "include_csv": False,
                "report_days": 14
            },
            description="Create a weekly scheduled report for Mondays"
        )
        
        if success and response.get('schedule', {}).get('id'):
            self.created_schedule_ids.append(response['schedule']['id'])
        
        # Create monthly schedule
        success, response = self.run_test(
            "Create Monthly Schedule", 
            "POST",
            "/dashboard/reports/schedule",
            200,
            data={
                "frequency": "monthly",
                "email": "monthly@example.com",
                "report_type": "kpi_only",
                "day_of_month": 1,  # First day of month
                "time": "10:00",
                "timezone": "UTC", 
                "include_csv": False,
                "report_days": 30
            },
            description="Create a monthly KPI-only report"
        )
        
        if success and response.get('schedule', {}).get('id'):
            self.created_schedule_ids.append(response['schedule']['id'])

    def test_list_schedules(self):
        """Test listing all scheduled reports"""
        print("\n" + "="*50)
        print("📋 TESTING SCHEDULE LISTING")
        print("="*50)
        
        success, response = self.run_test(
            "List All Schedules",
            "GET",
            "/dashboard/reports/schedules", 
            200,
            description="Retrieve all scheduled reports"
        )
        
        if success:
            schedules = response.get('schedules', [])
            print(f"   📊 Found {len(schedules)} scheduled reports")
            for i, schedule in enumerate(schedules, 1):
                print(f"   {i}. {schedule.get('frequency', 'N/A')} - {schedule.get('email', 'N/A')} - {schedule.get('report_type', 'N/A')}")

    def test_get_specific_schedule(self):
        """Test getting specific schedule details"""
        if not self.created_schedule_ids:
            print("\n⚠️ No created schedules to test - skipping get specific schedule test")
            return
            
        print("\n" + "="*50)
        print("🔍 TESTING SPECIFIC SCHEDULE RETRIEVAL")
        print("="*50)
        
        schedule_id = self.created_schedule_ids[0]
        self.run_test(
            "Get Specific Schedule",
            "GET",
            f"/dashboard/reports/schedule/{schedule_id}",
            200,
            description=f"Retrieve details for schedule {schedule_id}"
        )
        
        # Test non-existent schedule
        self.run_test(
            "Get Non-existent Schedule",
            "GET",
            "/dashboard/reports/schedule/non-existent-id",
            404,
            description="Should return 404 for non-existent schedule"
        )

    def test_update_schedule(self):
        """Test updating schedule configurations"""
        if not self.created_schedule_ids:
            print("\n⚠️ No created schedules to test - skipping update schedule test")
            return
            
        print("\n" + "="*50)
        print("✏️ TESTING SCHEDULE UPDATES")
        print("="*50)
        
        schedule_id = self.created_schedule_ids[0]
        self.run_test(
            "Update Schedule",
            "PUT",
            f"/dashboard/reports/schedule/{schedule_id}",
            200,
            data={
                "frequency": "weekly",
                "email": "updated@example.com",
                "report_type": "summary",
                "day_of_week": 5,  # Friday
                "time": "15:00",
                "timezone": "UTC",
                "include_csv": True,
                "report_days": 21
            },
            description=f"Update schedule {schedule_id} to weekly with new settings"
        )
        
        # Test updating non-existent schedule
        self.run_test(
            "Update Non-existent Schedule",
            "PUT",
            "/dashboard/reports/schedule/non-existent-id",
            404,
            data={
                "frequency": "daily",
                "email": "test@example.com",
                "report_type": "full",
                "time": "09:00"
            },
            description="Should return 404 when updating non-existent schedule"
        )

    def test_toggle_schedule(self):
        """Test toggling schedule active/inactive state"""
        if not self.created_schedule_ids:
            print("\n⚠️ No created schedules to test - skipping toggle schedule test")
            return
            
        print("\n" + "="*50)
        print("🔄 TESTING SCHEDULE TOGGLE")
        print("="*50)
        
        schedule_id = self.created_schedule_ids[0]
        
        # Toggle off
        success, response = self.run_test(
            "Toggle Schedule Off",
            "POST",
            f"/dashboard/reports/schedule/{schedule_id}/toggle",
            200,
            description=f"Toggle schedule {schedule_id} to inactive state"
        )
        
        if success:
            is_active = response.get('is_active', True)
            print(f"   📊 Schedule is now {'active' if is_active else 'inactive'}")
        
        # Toggle back on
        self.run_test(
            "Toggle Schedule On",
            "POST", 
            f"/dashboard/reports/schedule/{schedule_id}/toggle",
            200,
            description=f"Toggle schedule {schedule_id} back to active state"
        )
        
        # Test toggling non-existent schedule
        self.run_test(
            "Toggle Non-existent Schedule",
            "POST",
            "/dashboard/reports/schedule/non-existent-id/toggle",
            404,
            description="Should return 404 when toggling non-existent schedule"
        )

    def test_send_now(self):
        """Test manually triggering report generation"""
        if not self.created_schedule_ids:
            print("\n⚠️ No created schedules to test - skipping send now test")
            return
            
        print("\n" + "="*50)
        print("📤 TESTING MANUAL REPORT TRIGGER")
        print("="*50)
        
        schedule_id = self.created_schedule_ids[0]
        self.run_test(
            "Send Report Now",
            "POST",
            f"/dashboard/reports/schedule/{schedule_id}/send-now",
            200,
            description=f"Manually trigger report generation for schedule {schedule_id}"
        )
        
        # Test sending non-existent schedule
        self.run_test(
            "Send Non-existent Schedule Now",
            "POST",
            "/dashboard/reports/schedule/non-existent-id/send-now",
            404,
            description="Should return 404 when triggering non-existent schedule"
        )

    def test_delete_schedule(self):
        """Test deleting scheduled reports"""
        if not self.created_schedule_ids:
            print("\n⚠️ No created schedules to test - skipping delete schedule test")
            return
            
        print("\n" + "="*50)
        print("🗑️ TESTING SCHEDULE DELETION")
        print("="*50)
        
        # Delete one schedule (keep others for final cleanup)
        if len(self.created_schedule_ids) > 1:
            schedule_id = self.created_schedule_ids.pop()
            self.run_test(
                "Delete Schedule",
                "DELETE",
                f"/dashboard/reports/schedule/{schedule_id}",
                200,
                description=f"Delete schedule {schedule_id}"
            )
        
        # Test deleting non-existent schedule
        self.run_test(
            "Delete Non-existent Schedule",
            "DELETE",
            "/dashboard/reports/schedule/non-existent-id",
            404,
            description="Should return 404 when deleting non-existent schedule"
        )

    def test_unauthenticated_access(self):
        """Test that endpoints require admin authentication"""
        print("\n" + "="*50)
        print("🔒 TESTING AUTHENTICATION REQUIREMENTS")
        print("="*50)
        
        # Temporarily remove token
        original_token = self.token
        self.token = None
        
        self.run_test(
            "Unauthenticated Create Schedule",
            "POST",
            "/dashboard/reports/schedule",
            401,
            data={
                "frequency": "daily",
                "email": "test@example.com",
                "report_type": "full",
                "time": "09:00"
            },
            description="Should require authentication"
        )
        
        self.run_test(
            "Unauthenticated List Schedules",
            "GET",
            "/dashboard/reports/schedules",
            401,
            description="Should require authentication"
        )
        
        # Restore token
        self.token = original_token

    def cleanup_created_schedules(self):
        """Clean up any remaining test schedules"""
        if not self.created_schedule_ids:
            return
            
        print("\n" + "="*50)
        print("🧹 CLEANUP: DELETING TEST SCHEDULES")
        print("="*50)
        
        for schedule_id in self.created_schedule_ids[:]:
            success, _ = self.run_test(
                f"Cleanup Schedule",
                "DELETE",
                f"/dashboard/reports/schedule/{schedule_id}",
                200,
                description=f"Cleanup test schedule {schedule_id}"
            )
            if success:
                self.created_schedule_ids.remove(schedule_id)

    def run_all_tests(self, admin_email, admin_password):
        """Run the complete test suite"""
        print("🧪 STARTING SCHEDULED REPORTS API TEST SUITE")
        print("="*60)
        
        # 1. Admin authentication
        if not self.test_admin_login(admin_email, admin_password):
            print("\n❌ Cannot proceed without admin authentication")
            return self.print_results()
        
        try:
            # 2. Test input validation
            self.test_create_schedule_validation()
            
            # 3. Test authentication requirements
            self.test_unauthenticated_access()
            
            # 4. Test schedule creation
            self.test_create_schedules()
            
            # 5. Test listing schedules
            self.test_list_schedules()
            
            # 6. Test getting specific schedule
            self.test_get_specific_schedule()
            
            # 7. Test schedule updates
            self.test_update_schedule()
            
            # 8. Test toggle functionality
            self.test_toggle_schedule()
            
            # 9. Test manual report triggering
            self.test_send_now()
            
            # 10. Test schedule deletion
            self.test_delete_schedule()
            
        finally:
            # Cleanup any remaining test data
            self.cleanup_created_schedules()
        
        return self.print_results()

    def print_results(self):
        """Print comprehensive test results"""
        print("\n" + "="*60)
        print("📊 SCHEDULED REPORTS API TEST RESULTS")
        print("="*60)
        
        success_rate = (self.tests_passed / self.tests_run * 100) if self.tests_run > 0 else 0
        
        print(f"📈 Tests Run: {self.tests_run}")
        print(f"✅ Tests Passed: {self.tests_passed}")
        print(f"❌ Tests Failed: {len(self.failed_tests)}")
        print(f"🎯 Success Rate: {success_rate:.1f}%")
        
        if self.passed_tests:
            print(f"\n✅ PASSED TESTS ({len(self.passed_tests)}):")
            for test in self.passed_tests:
                print(f"   • {test}")
        
        if self.failed_tests:
            print(f"\n❌ FAILED TESTS ({len(self.failed_tests)}):")
            for test in self.failed_tests:
                print(f"   • {test}")
        
        print("\n" + "="*60)
        
        if success_rate >= 80:
            print("🎉 SCHEDULED REPORTS API TESTING COMPLETED SUCCESSFULLY!")
            return 0
        else:
            print("⚠️ SCHEDULED REPORTS API TESTING COMPLETED WITH ISSUES")
            return 1

def main():
    """Main test execution"""
    if len(sys.argv) > 1:
        base_url = sys.argv[1]
    else:
        base_url = "http://localhost:8001"
    
    # Admin credentials from request
    admin_email = "aminderpro@gmail.com"
    admin_password = "Admin@123!"
    
    tester = ScheduledReportsAPITester(base_url)
    
    try:
        return tester.run_all_tests(admin_email, admin_password)
    except KeyboardInterrupt:
        print("\n⏹️ Tests interrupted by user")
        return 1
    except Exception as e:
        print(f"\n💥 Unexpected error: {str(e)}")
        traceback.print_exc()
        return 1

if __name__ == "__main__":
    sys.exit(main())