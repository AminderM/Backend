"""
TMS Master Data API Tests - Phase 2
Tests for Canadian Tax Calculator and Master Data Tables
(Carriers, Brokers, Locations, Shippers, Consignees, Customers)
"""

import requests
import json
import sys
from datetime import datetime

class TMSMasterDataTester:
    def __init__(self, base_url="https://5e2a63d0-abe8-4325-a9d8-8022eb861680.preview.emergentagent.com"):
        self.base_url = base_url.rstrip('/')
        self.token = None
        self.headers = {'Content-Type': 'application/json'}
        self.tests_run = 0
        self.tests_passed = 0
        self.failed_tests = []
        self.tenant_id = None

    def run_test(self, name, method, endpoint, expected_status, data=None, params=None):
        """Run a single API test"""
        url = f"{self.base_url}/api/master-data/{endpoint}"
        headers = self.headers.copy()
        if self.token:
            headers['Authorization'] = f'Bearer {self.token}'

        self.tests_run += 1
        print(f"\n🔍 Testing {name}...")
        print(f"   URL: {method} {url}")
        if data:
            print(f"   Data: {json.dumps(data, indent=2)}")
        
        try:
            if method == 'GET':
                response = requests.get(url, headers=headers, params=params, timeout=30)
            elif method == 'POST':
                response = requests.post(url, json=data, headers=headers, params=params, timeout=30)
            elif method == 'PUT':
                response = requests.put(url, json=data, headers=headers, params=params, timeout=30)
            elif method == 'DELETE':
                response = requests.delete(url, headers=headers, params=params, timeout=30)

            print(f"   Response Status: {response.status_code}")
            success = response.status_code == expected_status
            
            if success:
                self.tests_passed += 1
                print(f"✅ Passed - Status: {response.status_code}")
                try:
                    response_data = response.json()
                    print(f"   Response: {json.dumps(response_data, indent=2)[:200]}...")
                    return True, response_data
                except:
                    return True, {}
            else:
                self.failed_tests.append(f"{name} - Expected {expected_status}, got {response.status_code}")
                print(f"❌ Failed - Expected {expected_status}, got {response.status_code}")
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
        """Test login and get token"""
        print(f"\n🔑 Logging in as {email}...")
        url = f"{self.base_url}/api/auth/login"
        
        try:
            response = requests.post(url, json={"email": email, "password": password}, timeout=30)
            print(f"   Login Status: {response.status_code}")
            
            if response.status_code == 200:
                data = response.json()
                self.token = data.get('access_token')
                # Try to get tenant_id from user data
                if 'user' in data:
                    user_data = data['user']
                    self.tenant_id = user_data.get('tenant_id') or user_data.get('company_id') or 'test-tenant-001'
                else:
                    self.tenant_id = 'test-tenant-001'  # Fallback
                    
                print(f"✅ Login successful")
                print(f"   Tenant ID: {self.tenant_id}")
                return True
            else:
                print(f"❌ Login failed - Status: {response.status_code}")
                try:
                    error_data = response.json()
                    print(f"   Error: {json.dumps(error_data, indent=2)}")
                except:
                    print(f"   Error: {response.text}")
                return False
        except Exception as e:
            print(f"❌ Login failed - Error: {str(e)}")
            return False

    def test_canadian_tax_rates(self):
        """Test GET /api/master-data/tax/rates - Returns all Canadian tax rates"""
        success, response = self.run_test(
            "Get Canadian Tax Rates",
            "GET",
            "tax/rates",
            200
        )
        
        if success and response:
            rates = response.get('rates', {})
            if 'ON' in rates and 'BC' in rates and 'QC' in rates:
                print("   ✓ Found tax rates for ON, BC, QC provinces")
                
                # Check Ontario HST
                on_rate = rates.get('ON', {})
                if on_rate.get('hst') == 13.0 and on_rate.get('total') == 13.0:
                    print("   ✓ Ontario HST 13% verified")
                
                # Check Quebec GST+QST
                qc_rate = rates.get('QC', {})
                if qc_rate.get('gst') == 5.0 and qc_rate.get('qst') == 9.975:
                    print("   ✓ Quebec GST 5% + QST 9.975% verified")
                
                return True
        
        return False

    def test_tax_calculation_ontario(self):
        """Test POST /api/master-data/tax/calculate - Ontario HST 13%"""
        success, response = self.run_test(
            "Calculate Tax - Ontario (HST 13%)",
            "POST",
            "tax/calculate",
            200,
            params={"subtotal": 100.0, "province": "ON"}
        )
        
        if success and response:
            if (response.get('province') == 'ON' and 
                response.get('hst_rate') == 13.0 and
                response.get('hst_amount') == 13.0 and
                response.get('total_tax_amount') == 13.0 and
                response.get('grand_total') == 113.0):
                print("   ✓ Ontario HST calculation correct")
                return True
        
        return False

    def test_tax_calculation_quebec(self):
        """Test POST /api/master-data/tax/calculate - Quebec GST+QST"""
        success, response = self.run_test(
            "Calculate Tax - Quebec (GST+QST)",
            "POST",
            "tax/calculate",
            200,
            params={"subtotal": 100.0, "province": "QC"}
        )
        
        if success and response:
            # QST is calculated on GST-inclusive amount: (100 + 5) * 9.975% = 10.47
            expected_gst = 5.0
            expected_qst = 10.47  # (100 + 5) * 0.09975
            expected_total = expected_gst + expected_qst
            
            if (response.get('province') == 'QC' and 
                response.get('gst_rate') == 5.0 and
                response.get('qst_rate') == 9.975 and
                abs(response.get('qst_amount', 0) - expected_qst) < 0.01):
                print("   ✓ Quebec GST+QST calculation correct")
                return True
        
        return False

    def test_tax_calculation_bc(self):
        """Test POST /api/master-data/tax/calculate - BC GST+PST"""
        success, response = self.run_test(
            "Calculate Tax - BC (GST+PST)",
            "POST",
            "tax/calculate",
            200,
            params={"subtotal": 100.0, "province": "BC"}
        )
        
        if success and response:
            if (response.get('province') == 'BC' and 
                response.get('gst_rate') == 5.0 and
                response.get('pst_rate') == 7.0 and
                response.get('gst_amount') == 5.0 and
                response.get('pst_amount') == 7.0 and
                response.get('total_tax_amount') == 12.0):
                print("   ✓ BC GST+PST calculation correct")
                return True
        
        return False

    def test_tax_calculation_alberta(self):
        """Test POST /api/master-data/tax/calculate - Alberta GST only"""
        success, response = self.run_test(
            "Calculate Tax - Alberta (GST only)",
            "POST",
            "tax/calculate",
            200,
            params={"subtotal": 100.0, "province": "AB"}
        )
        
        if success and response:
            if (response.get('province') == 'AB' and 
                response.get('gst_rate') == 5.0 and
                response.get('gst_amount') == 5.0 and
                response.get('total_tax_amount') == 5.0 and
                response.get('grand_total') == 105.0):
                print("   ✓ Alberta GST-only calculation correct")
                return True
        
        return False

    def test_create_carrier_broker(self):
        """Test POST /api/master-data/carriers-brokers - Create carrier/broker"""
        carrier_data = {
            "tenant_id": self.tenant_id,
            "company_name": "Test Carrier Inc",
            "entity_type": "carrier",
            "contact_name": "John Smith",
            "contact_email": "john@testcarrier.com",
            "contact_phone": "416-555-0123",
            "address": {
                "address_line1": "123 Industrial Way",
                "city": "Toronto",
                "state_province": "ON",
                "postal_code": "M5V 3A8",
                "country": "CA"
            },
            "nsc_number": "NSC123456",
            "cvor_number": "CVOR7890123",
            "fleet_size": 25,
            "equipment_types": ["dry_van", "reefer"],
            "operating_provinces": ["ON", "QC", "AB"],
            "payment_terms": "net_30"
        }
        
        success, response = self.run_test(
            "Create Carrier",
            "POST",
            "carriers-brokers",
            200,
            data=carrier_data
        )
        
        if success and response:
            carrier_id = response.get('id')
            if carrier_id:
                print(f"   ✓ Carrier created with ID: {carrier_id}")
                return carrier_id
        
        return None

    def test_list_carriers_brokers(self):
        """Test GET /api/master-data/carriers-brokers - List carriers/brokers"""
        success, response = self.run_test(
            "List Carriers/Brokers",
            "GET",
            "carriers-brokers",
            200
        )
        
        if success and isinstance(response, list):
            print(f"   ✓ Found {len(response)} carriers/brokers")
            return True
        
        return False

    def test_create_customer(self):
        """Test POST /api/master-data/customers - Create customer with billing address and tax_province"""
        customer_data = {
            "tenant_id": self.tenant_id,
            "company_name": "Test Customer Corp",
            "contact_name": "Jane Doe",
            "contact_email": "jane@testcustomer.com",
            "contact_phone": "416-555-0456",
            "billing_address": {
                "address_line1": "456 Business Blvd",
                "city": "Vancouver",
                "state_province": "BC",
                "postal_code": "V6B 2W9",
                "country": "CA"
            },
            "tax_province": "BC",
            "credit_limit": 50000.0,
            "payment_terms": "net_30"
        }
        
        success, response = self.run_test(
            "Create Customer",
            "POST",
            "customers",
            200,
            data=customer_data
        )
        
        if success and response:
            customer_id = response.get('id')
            if customer_id:
                print(f"   ✓ Customer created with ID: {customer_id}")
                return customer_id
        
        return None

    def test_customer_tax_calculation(self, customer_id):
        """Test GET /api/master-data/customers/{id}/tax-calculation"""
        if not customer_id:
            print("   ⚠️  Skipping - no customer ID available")
            return False
            
        success, response = self.run_test(
            "Customer Tax Calculation",
            "GET",
            f"customers/{customer_id}/tax-calculation",
            200,
            params={"subtotal": 1000.0}
        )
        
        if success and response:
            # Should calculate BC tax (GST 5% + PST 7% = 12%)
            if (response.get('province') == 'BC' and
                response.get('total_tax_rate') == 12.0 and
                response.get('total_tax_amount') == 120.0 and
                response.get('grand_total') == 1120.0):
                print("   ✓ Customer tax calculation correct for BC")
                return True
        
        return False

    def test_create_shipper(self):
        """Test POST /api/master-data/shippers - Create shipper"""
        shipper_data = {
            "tenant_id": self.tenant_id,
            "company_name": "Test Shipper Ltd",
            "contact_name": "Bob Wilson",
            "contact_email": "bob@testshipper.com",
            "contact_phone": "905-555-0789",
            "address": {
                "address_line1": "789 Shipping Ave",
                "city": "Mississauga",
                "state_province": "ON",
                "postal_code": "L5B 3C4",
                "country": "CA"
            },
            "appointment_required": True,
            "dock_hours_open": "08:00",
            "dock_hours_close": "17:00"
        }
        
        success, response = self.run_test(
            "Create Shipper",
            "POST",
            "shippers",
            200,
            data=shipper_data
        )
        
        if success and response:
            shipper_id = response.get('id')
            if shipper_id:
                print(f"   ✓ Shipper created with ID: {shipper_id}")
                return shipper_id
        
        return None

    def test_create_consignee(self):
        """Test POST /api/master-data/consignees - Create consignee"""
        consignee_data = {
            "tenant_id": self.tenant_id,
            "company_name": "Test Consignee Inc",
            "contact_name": "Alice Brown",
            "contact_email": "alice@testconsignee.com",
            "contact_phone": "403-555-0321",
            "address": {
                "address_line1": "321 Receiving Rd",
                "city": "Calgary",
                "state_province": "AB",
                "postal_code": "T2P 1M7",
                "country": "CA"
            },
            "appointment_required": False,
            "unload_type": "live_unload",
            "average_unload_time_minutes": 120
        }
        
        success, response = self.run_test(
            "Create Consignee",
            "POST",
            "consignees",
            200,
            data=consignee_data
        )
        
        if success and response:
            consignee_id = response.get('id')
            if consignee_id:
                print(f"   ✓ Consignee created with ID: {consignee_id}")
                return consignee_id
        
        return None

    def test_create_location(self):
        """Test POST /api/master-data/locations - Create location"""
        location_data = {
            "tenant_id": self.tenant_id,
            "location_name": "Test Distribution Center",
            "location_type": "distribution_center",
            "address": {
                "address_line1": "999 Logistics Blvd",
                "city": "Montreal",
                "state_province": "QC",
                "postal_code": "H3B 2M7",
                "country": "CA"
            },
            "contact_name": "Pierre Dubois",
            "contact_phone": "514-555-0654",
            "contact_email": "pierre@testlocation.com",
            "appointment_required": True,
            "dock_count": 12,
            "has_forklift": True,
            "max_trailer_length_ft": 53
        }
        
        success, response = self.run_test(
            "Create Location",
            "POST",
            "locations",
            200,
            data=location_data
        )
        
        if success and response:
            location_id = response.get('id')
            if location_id:
                print(f"   ✓ Location created with ID: {location_id}")
                return location_id
        
        return None

    def run_all_tests(self):
        """Run comprehensive Master Data API tests"""
        print("=" * 60)
        print("TMS Master Data API Tests - Phase 2")
        print("Testing Canadian Tax Calculator & Master Data Tables")
        print("=" * 60)

        # Login first
        if not self.login("aminderpro@gmail.com", "Admin@123!"):
            print("\n❌ Authentication failed - cannot continue tests")
            return False

        print(f"\n📋 Testing Master Data APIs...")
        
        # Test Canadian Tax Calculator
        print(f"\n🧮 Testing Canadian Tax Calculator...")
        self.test_canadian_tax_rates()
        self.test_tax_calculation_ontario()
        self.test_tax_calculation_quebec()
        self.test_tax_calculation_bc()
        self.test_tax_calculation_alberta()

        # Test Master Data CRUD
        print(f"\n📊 Testing Master Data CRUD Operations...")
        carrier_id = self.test_create_carrier_broker()
        self.test_list_carriers_brokers()
        
        customer_id = self.test_create_customer()
        self.test_customer_tax_calculation(customer_id)
        
        self.test_create_shipper()
        self.test_create_consignee()
        self.test_create_location()

        # Print results
        print("\n" + "=" * 60)
        print("📊 TEST RESULTS SUMMARY")
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
            print(f"\n✅ All tests passed!")

        return len(self.failed_tests) == 0


def main():
    tester = TMSMasterDataTester()
    success = tester.run_all_tests()
    return 0 if success else 1


if __name__ == "__main__":
    sys.exit(main())