#!/usr/bin/env python3
"""
Bundle Workspace Mapping API Backend Test Suite
Tests workspace-to-product mapping functionality in bundles
"""

import requests
import json
import sys
from datetime import datetime, timedelta
import uuid
import time
import traceback

class BundleWorkspaceAPITester:
    def __init__(self, base_url="http://localhost:8001"):
        self.base_url = base_url
        self.token = None
        self.tests_run = 0
        self.tests_passed = 0
        self.failed_tests = []
        self.passed_tests = []
        self.created_bundle_id = None
        
        # Valid workspace IDs for testing
        self.valid_workspaces = [
            "dispatch_operations",
            "accounting", 
            "sales_business_dev",
            "hr",
            "fleet_maintenance",
            "fleet_safety"
        ]
        
        print(f"🚀 Initializing Bundle Workspace API Tester")
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
                        print(f"   📊 Response: {json.dumps(response_data, indent=2)[:300]}...")
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

    def test_get_available_workspaces(self):
        """Test GET /api/bundles/workspaces - Returns list of 6 valid workspaces"""
        print("\n🏢 Testing Available Workspaces Endpoint")
        print("=" * 45)
        
        if not self.token:
            print("❌ Cannot test workspace endpoint - no auth token")
            return False
        
        success, response = self.run_test(
            "Get Available Workspaces",
            "GET",
            "/bundles/workspaces",
            200,
            description="Should return 6 valid workspace IDs"
        )
        
        if success and 'workspaces' in response:
            workspaces = response['workspaces']
            print(f"   📋 Found {len(workspaces)} workspaces")
            
            # Verify we have exactly 6 workspaces
            if len(workspaces) != 6:
                print(f"   ❌ Expected 6 workspaces, got {len(workspaces)}")
                self.failed_tests.append({
                    "test": "Workspace count validation",
                    "expected": 6,
                    "actual": len(workspaces),
                    "error": f"Wrong number of workspaces"
                })
                return False
            
            # Verify all expected workspace IDs are present
            workspace_ids = [w.get('id') for w in workspaces]
            missing_ids = set(self.valid_workspaces) - set(workspace_ids)
            if missing_ids:
                print(f"   ❌ Missing workspace IDs: {missing_ids}")
                self.failed_tests.append({
                    "test": "Workspace ID validation",
                    "error": f"Missing workspace IDs: {missing_ids}"
                })
                return False
            
            print(f"   ✅ All 6 valid workspaces found: {workspace_ids}")
            return True
        
        return False

    def test_create_bundle_with_workspaces(self):
        """Test POST /api/bundles - Create bundle with workspaces array per product"""
        print("\n📦 Testing Bundle Creation with Workspaces")
        print("=" * 48)
        
        if not self.token:
            print("❌ Cannot test bundle creation - no auth token")
            return False
        
        # Test 1: Create bundle with valid workspaces
        bundle_data = {
            "name": f"Test Bundle {datetime.now().strftime('%H%M%S')}",
            "description": "Test bundle for workspace mapping",
            "products": [
                {
                    "product_id": "tms_basic",
                    "product_name": "TMS Basic",
                    "included_seats": 5,
                    "included_storage_gb": 10,
                    "workspaces": ["dispatch_operations", "accounting"]  # Valid workspaces
                },
                {
                    "product_id": "tms_pro",
                    "product_name": "TMS Pro", 
                    "included_seats": 10,
                    "included_storage_gb": 50,
                    "workspaces": ["sales_business_dev", "hr", "fleet_maintenance", "fleet_safety"]  # Valid workspaces
                }
            ],
            "monthly_price": 199.99,
            "original_price": 299.99,
            "is_active": True
        }
        
        success, response = self.run_test(
            "Create Bundle with Valid Workspaces",
            "POST",
            "/bundles",
            200,
            data=bundle_data,
            description="Create bundle with valid workspace assignments"
        )
        
        if success and 'bundle_id' in response:
            self.created_bundle_id = response['bundle_id']
            print(f"   🆔 Created bundle ID: {self.created_bundle_id}")
            
            # Verify workspaces are correctly stored
            if 'bundle' in response:
                bundle = response['bundle']
                for product in bundle.get('products', []):
                    workspaces = product.get('workspaces', [])
                    print(f"   📋 Product {product.get('product_id')} has workspaces: {workspaces}")
                    
                    # Verify all workspaces are valid
                    invalid_workspaces = set(workspaces) - set(self.valid_workspaces)
                    if invalid_workspaces:
                        print(f"   ❌ Found invalid workspaces: {invalid_workspaces}")
                        self.failed_tests.append({
                            "test": "Workspace validation in response",
                            "error": f"Invalid workspaces found: {invalid_workspaces}"
                        })
                        return False
            
            print(f"   ✅ Bundle created successfully with valid workspaces")
            return True
        
        return False

    def test_workspace_validation_and_deduplication(self):
        """Test workspace validation and deduplication"""
        print("\n✅ Testing Workspace Validation & Deduplication")
        print("=" * 50)
        
        if not self.token:
            print("❌ Cannot test validation - no auth token")
            return False
        
        # Test 2: Create bundle with invalid and duplicate workspaces
        bundle_data = {
            "name": f"Validation Test Bundle {datetime.now().strftime('%H%M%S')}",
            "description": "Test bundle for validation",
            "products": [
                {
                    "product_id": "tms_basic",
                    "product_name": "TMS Basic",
                    "included_seats": 5,
                    "included_storage_gb": 10,
                    "workspaces": [
                        "dispatch_operations", 
                        "accounting", 
                        "invalid_workspace1",  # Invalid - should be filtered
                        "dispatch_operations",  # Duplicate - should be deduplicated
                        "another_invalid",  # Invalid - should be filtered
                        "accounting"  # Duplicate - should be deduplicated
                    ]
                }
            ],
            "monthly_price": 99.99,
            "is_active": True
        }
        
        success, response = self.run_test(
            "Create Bundle with Invalid & Duplicate Workspaces",
            "POST",
            "/bundles",
            200,
            data=bundle_data,
            description="Should filter invalid and deduplicate workspace IDs"
        )
        
        if success and 'bundle' in response:
            bundle = response['bundle']
            product = bundle['products'][0]
            workspaces = product.get('workspaces', [])
            
            print(f"   📋 Filtered workspaces: {workspaces}")
            
            # Should only have 2 unique valid workspaces
            expected_workspaces = ["dispatch_operations", "accounting"]
            if set(workspaces) != set(expected_workspaces):
                print(f"   ❌ Expected {expected_workspaces}, got {workspaces}")
                self.failed_tests.append({
                    "test": "Workspace validation/deduplication",
                    "expected": expected_workspaces,
                    "actual": workspaces,
                    "error": "Validation or deduplication failed"
                })
                return False
            
            print(f"   ✅ Validation and deduplication working correctly")
            return True
        
        return False

    def test_empty_workspaces_array(self):
        """Test that empty workspaces array is valid"""
        print("\n📝 Testing Empty Workspaces Array")
        print("=" * 36)
        
        if not self.token:
            print("❌ Cannot test empty workspaces - no auth token")
            return False
        
        bundle_data = {
            "name": f"Empty Workspaces Bundle {datetime.now().strftime('%H%M%S')}",
            "description": "Test bundle with empty workspaces",
            "products": [
                {
                    "product_id": "tms_basic",
                    "product_name": "TMS Basic",
                    "included_seats": 5,
                    "included_storage_gb": 10,
                    "workspaces": []  # Empty array
                }
            ],
            "monthly_price": 49.99,
            "is_active": True
        }
        
        success, response = self.run_test(
            "Create Bundle with Empty Workspaces",
            "POST",
            "/bundles",
            200,
            data=bundle_data,
            description="Empty workspaces array should be valid"
        )
        
        if success and 'bundle' in response:
            bundle = response['bundle']
            product = bundle['products'][0]
            workspaces = product.get('workspaces', [])
            
            if workspaces == []:
                print(f"   ✅ Empty workspaces array handled correctly")
                return True
            else:
                print(f"   ❌ Expected empty array, got {workspaces}")
                self.failed_tests.append({
                    "test": "Empty workspaces validation",
                    "expected": [],
                    "actual": workspaces,
                    "error": "Empty array not handled correctly"
                })
                return False
        
        return False

    def test_get_bundles_with_workspaces(self):
        """Test GET /api/bundles - Returns workspaces array in each product"""
        print("\n📋 Testing Get All Bundles with Workspaces")
        print("=" * 45)
        
        if not self.token:
            print("❌ Cannot test get bundles - no auth token")
            return False
        
        success, response = self.run_test(
            "Get All Bundles",
            "GET",
            "/bundles",
            200,
            description="Should return workspaces array in each product"
        )
        
        if success and 'bundles' in response:
            bundles = response['bundles']
            print(f"   📦 Found {len(bundles)} bundles")
            
            # Check that each product has workspaces array
            for bundle in bundles:
                for product in bundle.get('products', []):
                    if 'workspaces' not in product:
                        print(f"   ❌ Product {product.get('product_id')} missing workspaces array")
                        self.failed_tests.append({
                            "test": "Workspaces array presence",
                            "error": f"Product {product.get('product_id')} missing workspaces array"
                        })
                        return False
                    
                    workspaces = product['workspaces']
                    print(f"   📋 Product {product.get('product_id')}: {workspaces}")
            
            print(f"   ✅ All products have workspaces array")
            return True
        
        return False

    def test_get_single_bundle_with_workspaces(self):
        """Test GET /api/bundles/{id} - Returns workspaces array in each product"""
        print("\n🔍 Testing Get Single Bundle with Workspaces")
        print("=" * 48)
        
        if not self.token:
            print("❌ Cannot test get single bundle - no auth token")
            return False
        
        if not self.created_bundle_id:
            print("❌ No bundle ID available for testing")
            return False
        
        success, response = self.run_test(
            "Get Single Bundle",
            "GET",
            f"/bundles/{self.created_bundle_id}",
            200,
            description="Should return workspaces array in each product"
        )
        
        if success and 'products' in response:
            products = response['products']
            print(f"   📦 Bundle has {len(products)} products")
            
            # Check that each product has workspaces array
            for product in products:
                if 'workspaces' not in product:
                    print(f"   ❌ Product {product.get('product_id')} missing workspaces array")
                    self.failed_tests.append({
                        "test": "Single bundle workspaces array",
                        "error": f"Product {product.get('product_id')} missing workspaces array"
                    })
                    return False
                
                workspaces = product['workspaces']
                print(f"   📋 Product {product.get('product_id')}: {workspaces}")
            
            print(f"   ✅ Single bundle has workspaces arrays")
            return True
        
        return False

    def test_update_bundle_workspaces(self):
        """Test PUT /api/bundles/{id} - Update bundle with workspaces"""
        print("\n✏️ Testing Update Bundle Workspaces")
        print("=" * 38)
        
        if not self.token:
            print("❌ Cannot test update bundle - no auth token")
            return False
        
        if not self.created_bundle_id:
            print("❌ No bundle ID available for testing")
            return False
        
        # Update with new workspaces
        update_data = {
            "products": [
                {
                    "product_id": "tms_basic",
                    "product_name": "TMS Basic",
                    "included_seats": 8,
                    "included_storage_gb": 15,
                    "workspaces": ["fleet_maintenance", "fleet_safety"]  # Different valid workspaces
                },
                {
                    "product_id": "tms_pro",
                    "product_name": "TMS Pro",
                    "included_seats": 12,
                    "included_storage_gb": 100,
                    "workspaces": ["dispatch_operations"]  # Different valid workspace
                }
            ]
        }
        
        success, response = self.run_test(
            "Update Bundle Workspaces",
            "PUT",
            f"/bundles/{self.created_bundle_id}",
            200,
            data=update_data,
            description="Update bundle with new workspace assignments"
        )
        
        if success:
            print(f"   ✅ Bundle workspaces updated successfully")
            
            # Verify the update by getting the bundle again
            verify_success, verify_response = self.run_test(
                "Verify Updated Workspaces",
                "GET",
                f"/bundles/{self.created_bundle_id}",
                200,
                description="Verify workspaces were updated correctly"
            )
            
            if verify_success and 'products' in verify_response:
                for product in verify_response['products']:
                    workspaces = product.get('workspaces', [])
                    print(f"   📋 Updated Product {product.get('product_id')}: {workspaces}")
                
                print(f"   ✅ Workspace updates verified")
                return True
        
        return False

    def run_all_tests(self):
        """Run all tests in sequence"""
        print("\n" + "="*60)
        print("🧪 BUNDLE WORKSPACE API TEST SUITE")
        print("="*60)
        
        start_time = time.time()
        
        # Step 1: Authentication
        if not self.test_admin_login():
            print("\n❌ Authentication failed - stopping tests")
            return self.generate_summary()
        
        # Step 2: Test available workspaces endpoint
        self.test_get_available_workspaces()
        
        # Step 3: Test bundle creation with workspaces
        self.test_create_bundle_with_workspaces()
        
        # Step 4: Test workspace validation and deduplication
        self.test_workspace_validation_and_deduplication()
        
        # Step 5: Test empty workspaces array
        self.test_empty_workspaces_array()
        
        # Step 6: Test get all bundles with workspaces
        self.test_get_bundles_with_workspaces()
        
        # Step 7: Test get single bundle with workspaces
        self.test_get_single_bundle_with_workspaces()
        
        # Step 8: Test update bundle workspaces
        self.test_update_bundle_workspaces()
        
        # Generate final summary
        total_time = round(time.time() - start_time, 2)
        return self.generate_summary(total_time)

    def generate_summary(self, total_time=0):
        """Generate test summary"""
        print("\n" + "="*60)
        print("📊 BUNDLE WORKSPACE TEST RESULTS")
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
        tester = BundleWorkspaceAPITester("http://localhost:8001")
        exit_code = tester.run_all_tests()
        
        print(f"\n🏁 Bundle workspace test suite completed with exit code: {exit_code}")
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