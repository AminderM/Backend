"""
TMS Master Data API - Additional Edge Case Tests
Testing error handling, edge cases, and data validation
"""

import requests
import json
import sys

class TMSEdgeCaseTester:
    def __init__(self, base_url="https://accessorial-charges.preview.emergentagent.com"):
        self.base_url = base_url.rstrip('/')
        self.token = None
        self.headers = {'Content-Type': 'application/json'}
        self.tests_run = 0
        self.tests_passed = 0
        self.failed_tests = []

    def run_test(self, name, method, endpoint, expected_status, data=None, params=None):
        """Run a single API test"""
        url = f"{self.base_url}/api/master-data/{endpoint}" if not endpoint.startswith('http') else endpoint
        headers = self.headers.copy()
        if self.token:
            headers['Authorization'] = f'Bearer {self.token}'

        self.tests_run += 1
        print(f"\n🔍 Testing {name}...")
        
        try:
            if method == 'GET':
                response = requests.get(url, headers=headers, params=params, timeout=30)
            elif method == 'POST':
                response = requests.post(url, json=data, headers=headers, params=params, timeout=30)

            print(f"   Status: {response.status_code} (expected: {expected_status})")
            success = response.status_code == expected_status
            
            if success:
                self.tests_passed += 1
                print(f"✅ Passed")
                try:
                    return True, response.json()
                except:
                    return True, {}
            else:
                self.failed_tests.append(f"{name} - Expected {expected_status}, got {response.status_code}")
                print(f"❌ Failed")
                try:
                    error_data = response.json()
                    print(f"   Error: {json.dumps(error_data, indent=2)}")
                except:
                    print(f"   Error: {response.text}")
                return False, {}

        except Exception as e:
            self.failed_tests.append(f"{name} - Error: {str(e)}")
            print(f"❌ Failed - Error: {str(e)}")
            return False, {}

    def login(self, email, password):
        """Login and get token"""
        print(f"\n🔑 Logging in as {email}...")
        url = f"{self.base_url}/api/auth/login"
        
        try:
            response = requests.post(url, json={"email": email, "password": password}, timeout=30)
            
            if response.status_code == 200:
                data = response.json()
                self.token = data.get('access_token')
                print(f"✅ Login successful")
                return True
            else:
                print(f"❌ Login failed - Status: {response.status_code}")
                return False
        except Exception as e:
            print(f"❌ Login failed - Error: {str(e)}")
            return False

    def test_tax_edge_cases(self):
        """Test tax calculation edge cases"""
        print(f"\n🧮 Testing Tax Calculation Edge Cases...")
        
        # Test negative subtotal
        self.run_test(
            "Tax calculation with negative subtotal",
            "POST",
            "tax/calculate",
            400,
            params={"subtotal": -100.0, "province": "ON"}
        )
        
        # Test invalid province
        self.run_test(
            "Tax calculation with invalid province",
            "POST", 
            "tax/calculate",
            400,
            params={"subtotal": 100.0, "province": "XX"}
        )
        
        # Test zero subtotal
        self.run_test(
            "Tax calculation with zero subtotal",
            "POST",
            "tax/calculate", 
            200,
            params={"subtotal": 0.0, "province": "ON"}
        )
        
        # Test large subtotal
        self.run_test(
            "Tax calculation with large subtotal",
            "POST",
            "tax/calculate",
            200,
            params={"subtotal": 999999.99, "province": "BC"}
        )

    def test_auth_failures(self):
        """Test authentication failures"""
        print(f"\n🔒 Testing Authentication Edge Cases...")
        
        # Remove token temporarily
        original_token = self.token
        self.token = None
        
        # Test without auth
        self.run_test(
            "Access protected endpoint without auth",
            "GET",
            "carriers-brokers",
            401
        )
        
        # Test with invalid token
        self.token = "invalid-token-123"
        self.run_test(
            "Access with invalid token",
            "GET",
            "carriers-brokers", 
            401
        )
        
        # Restore valid token
        self.token = original_token

    def test_invalid_data_creation(self):
        """Test creation with invalid data"""
        print(f"\n📝 Testing Invalid Data Creation...")
        
        # Test carrier with missing required fields
        self.run_test(
            "Create carrier with missing company name",
            "POST",
            "carriers-brokers",
            422,
            data={"tenant_id": "test-tenant-001", "entity_type": "carrier"}
        )
        
        # Test customer with invalid email
        self.run_test(
            "Create customer with invalid email",
            "POST",
            "customers",
            422,
            data={
                "tenant_id": "test-tenant-001",
                "company_name": "Test Company",
                "contact_email": "invalid-email-format"
            }
        )
        
        # Test location with invalid location type
        self.run_test(
            "Create location with invalid type",
            "POST",
            "locations",
            422,
            data={
                "tenant_id": "test-tenant-001",
                "location_name": "Test Location",
                "location_type": "invalid_type",
                "address": {
                    "address_line1": "123 Test St",
                    "city": "Test City",
                    "state_province": "ON",
                    "postal_code": "M5V 1A1",
                    "country": "CA"
                }
            }
        )

    def test_nonexistent_resources(self):
        """Test accessing non-existent resources"""
        print(f"\n🔍 Testing Non-Existent Resources...")
        
        fake_id = "00000000-0000-0000-0000-000000000000"
        
        # Test get non-existent carrier
        self.run_test(
            "Get non-existent carrier",
            "GET",
            f"carriers-brokers/{fake_id}",
            404
        )
        
        # Test get non-existent customer
        self.run_test(
            "Get non-existent customer",
            "GET",
            f"customers/{fake_id}",
            404
        )
        
        # Test customer tax calculation for non-existent customer
        self.run_test(
            "Tax calculation for non-existent customer",
            "GET",
            f"customers/{fake_id}/tax-calculation",
            404,
            params={"subtotal": 100.0}
        )

    def test_multi_province_tax_calculation(self):
        """Test multi-province tax calculation endpoint"""
        print(f"\n🌎 Testing Multi-Province Tax Calculation...")
        
        # Test valid multi-province calculation
        self.run_test(
            "Multi-province tax calculation",
            "POST",
            "tax/calculate-multi",
            200,
            params={"subtotal": 100.0, "provinces": "ON,BC,QC,AB"}
        )
        
        # Test with some invalid provinces mixed in
        self.run_test(
            "Multi-province with some invalid provinces",
            "POST",
            "tax/calculate-multi",
            200,
            params={"subtotal": 100.0, "provinces": "ON,XX,BC,YY,AB"}
        )
        
        # Test with all invalid provinces
        self.run_test(
            "Multi-province with all invalid provinces",
            "POST",
            "tax/calculate-multi",
            400,
            params={"subtotal": 100.0, "provinces": "XX,YY,ZZ"}
        )

    def test_specific_province_rate(self):
        """Test getting specific province tax rate"""
        print(f"\n📊 Testing Province-Specific Tax Rates...")
        
        # Test valid province
        self.run_test(
            "Get Ontario tax rate",
            "GET",
            "tax/rates/ON",
            200
        )
        
        # Test Quebec tax rate
        self.run_test(
            "Get Quebec tax rate",
            "GET",
            "tax/rates/QC",
            200
        )
        
        # Test invalid province
        self.run_test(
            "Get invalid province tax rate",
            "GET",
            "tax/rates/XX",
            400
        )

    def test_filtering_endpoints(self):
        """Test filtering on list endpoints"""
        print(f"\n🔎 Testing List Filtering...")
        
        # Test carriers/brokers filtering
        self.run_test(
            "Filter carriers by entity type",
            "GET",
            "carriers-brokers",
            200,
            params={"entity_type": "carrier"}
        )
        
        # Test carriers/brokers filtering by province
        self.run_test(
            "Filter carriers by province",
            "GET",
            "carriers-brokers",
            200,
            params={"province": "ON"}
        )
        
        # Test locations filtering
        self.run_test(
            "Filter locations by type",
            "GET",
            "locations",
            200,
            params={"location_type": "warehouse"}
        )

    def run_all_tests(self):
        """Run all edge case tests"""
        print("=" * 60)
        print("TMS Master Data API - Edge Case Tests")
        print("Testing error handling and data validation")
        print("=" * 60)

        # Login first
        if not self.login("aminderpro@gmail.com", "Admin@123!"):
            print("\n❌ Authentication failed - cannot continue tests")
            return False

        # Run all test categories
        self.test_tax_edge_cases()
        self.test_auth_failures()
        self.test_invalid_data_creation()
        self.test_nonexistent_resources()
        self.test_multi_province_tax_calculation()
        self.test_specific_province_rate()
        self.test_filtering_endpoints()

        # Print results
        print("\n" + "=" * 60)
        print("📊 EDGE CASE TEST RESULTS")
        print("=" * 60)
        print(f"Total Tests: {self.tests_run}")
        print(f"Passed: {self.tests_passed}")
        print(f"Failed: {len(self.failed_tests)}")
        print(f"Success Rate: {(self.tests_passed/self.tests_run)*100:.1f}%")

        if self.failed_tests:
            print(f"\n❌ FAILED TESTS:")
            for i, failure in enumerate(self.failed_tests, 1):
                print(f"  {i}. {failure}")
        else:
            print(f"\n✅ All edge case tests passed!")

        return len(self.failed_tests) == 0


def main():
    tester = TMSEdgeCaseTester()
    success = tester.run_all_tests()
    return 0 if success else 1


if __name__ == "__main__":
    sys.exit(main())