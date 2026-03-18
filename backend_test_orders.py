"""
TMS Orders & Shipments API Tests - Phase 3
Comprehensive testing of Orders (Sales) and Shipments (Operations) 
Canada-First Design with automatic tax calculation
"""

import requests
import json
import sys
from datetime import datetime, date
from typing import Optional, Dict, Any

class TMSOrdersShipmentsTest:
    def __init__(self, base_url="https://backend-features-dev.preview.emergentagent.com"):
        self.base_url = base_url.rstrip('/')
        self.token = None
        self.headers = {'Content-Type': 'application/json'}
        self.tests_run = 0
        self.tests_passed = 0
        self.failed_tests = []
        self.tenant_id = None
        
        # Test data storage
        self.created_entities = {
            'orders': [],
            'shipments': [],
            'customers': [],
            'carriers': [],
            'shippers': [],
            'consignees': []
        }

    def run_test(self, name, method, endpoint, expected_status, data=None, params=None, timeout=30):
        """Run a single API test"""
        url = f"{self.base_url}/api/operations/{endpoint}"
        headers = self.headers.copy()
        if self.token:
            headers['Authorization'] = f'Bearer {self.token}'

        self.tests_run += 1
        print(f"\n🔍 Testing {name}...")
        print(f"   URL: {method} {url}")
        if data:
            print(f"   Data: {json.dumps(data, indent=2)[:300]}...")
        
        try:
            if method == 'GET':
                response = requests.get(url, headers=headers, params=params, timeout=timeout)
            elif method == 'POST':
                response = requests.post(url, json=data, headers=headers, params=params, timeout=timeout)
            elif method == 'PUT':
                response = requests.put(url, json=data, headers=headers, params=params, timeout=timeout)
            elif method == 'DELETE':
                response = requests.delete(url, headers=headers, params=params, timeout=timeout)

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
                if 'user' in data:
                    user_data = data['user']
                    self.tenant_id = user_data.get('tenant_id') or user_data.get('company_id') or 'test-tenant-001'
                else:
                    self.tenant_id = 'test-tenant-001'
                    
                print(f"✅ Login successful")
                print(f"   Tenant ID: {self.tenant_id}")
                return True
            else:
                print(f"❌ Login failed - Status: {response.status_code}")
                return False
        except Exception as e:
            print(f"❌ Login failed - Error: {str(e)}")
            return False

    def setup_test_data(self):
        """Create prerequisite test data (customer, carrier, etc.)"""
        print(f"\n🏗️  Setting up test data...")
        
        # Create test customer with Ontario tax (HST 13%)
        customer_data = {
            "tenant_id": self.tenant_id,
            "company_name": "Test Customer Corp - ON",
            "contact_name": "Jane Doe",
            "contact_email": "jane@testcustomer.com",
            "contact_phone": "416-555-0456",
            "billing_address": {
                "address_line1": "456 Business Blvd",
                "city": "Toronto", 
                "state_province": "ON",
                "postal_code": "M5V 3A8",
                "country": "CA"
            },
            "tax_province": "ON",
            "credit_limit": 50000.0,
            "payment_terms": "net_30"
        }
        
        success, response = self.run_test(
            "Setup - Create Test Customer",
            "POST",
            "../master-data/customers",
            200,
            data=customer_data
        )
        
        if success and response:
            customer_id = response.get('id')
            self.created_entities['customers'].append(customer_id)
            print(f"   ✓ Created customer: {customer_id}")
        
        # Create test carrier
        carrier_data = {
            "tenant_id": self.tenant_id,
            "company_name": "Test Transport Inc",
            "entity_type": "carrier",
            "contact_name": "John Smith",
            "contact_email": "john@testtransport.com",
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
            "payment_terms": "net_30"
        }
        
        success, response = self.run_test(
            "Setup - Create Test Carrier",
            "POST",
            "../master-data/carriers-brokers", 
            200,
            data=carrier_data
        )
        
        if success and response:
            carrier_id = response.get('id')
            self.created_entities['carriers'].append(carrier_id)
            print(f"   ✓ Created carrier: {carrier_id}")

        # Create test shipper
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
            "Setup - Create Test Shipper",
            "POST",
            "../master-data/shippers",
            200,
            data=shipper_data
        )
        
        if success and response:
            shipper_id = response.get('id')
            self.created_entities['shippers'].append(shipper_id)
            print(f"   ✓ Created shipper: {shipper_id}")

        # Create test consignee 
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
            "unload_type": "live_unload"
        }
        
        success, response = self.run_test(
            "Setup - Create Test Consignee",
            "POST",
            "../master-data/consignees",
            200,
            data=consignee_data
        )
        
        if success and response:
            consignee_id = response.get('id')
            self.created_entities['consignees'].append(consignee_id)
            print(f"   ✓ Created consignee: {consignee_id}")

        return len(self.created_entities['customers']) > 0

    def test_create_order(self):
        """Test POST /api/operations/orders - Create order with tax calculation"""
        if not self.created_entities['customers']:
            print("   ⚠️  Skipping - no customer available")
            return None
            
        customer_id = self.created_entities['customers'][0]
        shipper_id = self.created_entities['shippers'][0] if self.created_entities['shippers'] else None
        consignee_id = self.created_entities['consignees'][0] if self.created_entities['consignees'] else None
        
        order_data = {
            "tenant_id": self.tenant_id,
            "customer_id": customer_id,
            "customer_reference": "PO-2024-001",
            "origin_city": "Toronto",
            "origin_state_province": "ON", 
            "origin_country": "CA",
            "destination_city": "Calgary",
            "destination_state_province": "AB",
            "destination_country": "CA",
            "shipper_id": shipper_id,
            "consignee_id": consignee_id,
            "requested_pickup_date": "2024-08-15",
            "requested_delivery_date": "2024-08-17",
            "freight_type": "ftl",
            "equipment_type": "dry_van",
            "commodity": "General Freight",
            "pieces": 20,
            "weight": 25000,
            "weight_unit": "lbs",
            "customer_rate": 1500.0,
            "fuel_surcharge": 200.0,
            "currency": "CAD",
            "special_instructions": "Handle with care"
        }
        
        success, response = self.run_test(
            "Create Order with Tax Calculation",
            "POST", 
            "orders",
            200,
            data=order_data
        )
        
        if success and response:
            order_id = response.get('id')
            if order_id:
                self.created_entities['orders'].append(order_id)
                print(f"   ✓ Order created: {response.get('order_number')}")
                print(f"   ✓ Total Amount: ${response.get('total_amount')}")
                print(f"   ✓ Tax Amount: ${response.get('tax_amount')}")
                print(f"   ✓ Grand Total: ${response.get('grand_total')}")
                
                # Verify tax calculation for Ontario customer (HST 13%)
                expected_tax = 1700 * 0.13  # (customer_rate + fuel_surcharge) * 13%
                actual_tax = response.get('tax_amount', 0)
                if abs(actual_tax - expected_tax) < 0.01:
                    print(f"   ✓ Tax calculation correct: {actual_tax} (expected ~{expected_tax})")
                    
                return order_id
        
        return None

    def test_list_orders(self):
        """Test GET /api/operations/orders - List orders with filtering"""
        success, response = self.run_test(
            "List Orders",
            "GET",
            "orders",
            200
        )
        
        if success and isinstance(response, list):
            print(f"   ✓ Found {len(response)} orders")
            return True
        
        return False

    def test_get_order_details(self, order_id):
        """Test GET /api/operations/orders/{id} - Get order with margin calculation"""
        if not order_id:
            print("   ⚠️  Skipping - no order ID available")
            return False
            
        success, response = self.run_test(
            "Get Order Details", 
            "GET",
            f"orders/{order_id}",
            200
        )
        
        if success and response:
            print(f"   ✓ Order Number: {response.get('order_number')}")
            print(f"   ✓ Status: {response.get('status')}")
            print(f"   ✓ Customer: {response.get('customer', {}).get('company_name', 'N/A')}")
            print(f"   ✓ Total Amount: ${response.get('total_amount', 0)}")
            print(f"   ✓ Tax Amount: ${response.get('tax_amount', 0)}")
            print(f"   ✓ Grand Total: ${response.get('grand_total', 0)}")
            print(f"   ✓ Margin: ${response.get('margin_amount', 0)} ({response.get('margin_percentage', 0)}%)")
            print(f"   ✓ Shipments: {len(response.get('shipments', []))}")
            return True
        
        return False

    def test_update_order(self, order_id):
        """Test PUT /api/operations/orders/{id} - Update order"""
        if not order_id:
            print("   ⚠️  Skipping - no order ID available")
            return False
            
        update_data = {
            "customer_rate": 1600.0,
            "fuel_surcharge": 250.0,
            "internal_notes": "Updated rates after negotiation"
        }
        
        success, response = self.run_test(
            "Update Order",
            "PUT",
            f"orders/{order_id}",
            200,
            data=update_data
        )
        
        return success

    def test_confirm_order(self, order_id):
        """Test POST /api/operations/orders/{id}/confirm - Confirm order"""
        if not order_id:
            print("   ⚠️  Skipping - no order ID available")
            return False
            
        success, response = self.run_test(
            "Confirm Order",
            "POST", 
            f"orders/{order_id}/confirm",
            200
        )
        
        if success and response:
            print(f"   ✓ Order confirmed: {response.get('status')}")
            return True
        
        return False

    def test_create_shipment(self, order_id):
        """Test POST /api/operations/shipments - Create shipment"""
        if not order_id:
            print("   ⚠️  Skipping - no order ID available")
            return None
            
        shipment_data = {
            "tenant_id": self.tenant_id,
            "order_id": order_id,
            "pieces": 20,
            "weight": 25000,
            "weight_unit": "lbs",
            "carrier_rate": 1200.0,
            "carrier_fuel_surcharge": 150.0,
            "currency": "CAD",
            "dispatch_notes": "Handle with care - fragile items"
        }
        
        success, response = self.run_test(
            "Create Shipment",
            "POST",
            "shipments",
            200,
            data=shipment_data
        )
        
        if success and response:
            shipment_id = response.get('id')
            if shipment_id:
                self.created_entities['shipments'].append(shipment_id)
                print(f"   ✓ Shipment created: {response.get('shipment_number')}")
                print(f"   ✓ Order ID: {response.get('order_id')}")
                print(f"   ✓ Status: {response.get('status')}")
                return shipment_id
        
        return None

    def test_list_shipments(self):
        """Test GET /api/operations/shipments - List shipments"""
        success, response = self.run_test(
            "List Shipments",
            "GET",
            "shipments", 
            200
        )
        
        if success and isinstance(response, list):
            print(f"   ✓ Found {len(response)} shipments")
            return True
        
        return False

    def test_dispatch_shipment(self, shipment_id):
        """Test POST /api/operations/shipments/{id}/dispatch - Dispatch shipment"""
        if not shipment_id or not self.created_entities['carriers']:
            print("   ⚠️  Skipping - no shipment ID or carrier available")
            return False
            
        carrier_id = self.created_entities['carriers'][0]
        
        success, response = self.run_test(
            "Dispatch Shipment",
            "POST",
            f"shipments/{shipment_id}/dispatch",
            200,
            params={
                "carrier_id": carrier_id,
                "carrier_rate": 1200.0
            }
        )
        
        if success and response:
            print(f"   ✓ Dispatched to: {response.get('carrier', 'N/A')}")
            print(f"   ✓ Status: {response.get('status')}")
            return True
        
        return False

    def test_update_shipment_status(self, shipment_id):
        """Test POST /api/operations/shipments/{id}/status - Update status with tracking"""
        if not shipment_id:
            print("   ⚠️  Skipping - no shipment ID available")
            return False
            
        # Test multiple status updates
        status_updates = [
            ("en_route_pickup", "Driver heading to pickup location"),
            ("at_pickup", "Arrived at pickup location"),
            ("loading", "Loading cargo"),
            ("loaded", "Cargo loaded, ready to depart"),
            ("in_transit", "En route to delivery")
        ]
        
        for status, notes in status_updates:
            success, response = self.run_test(
                f"Update Status - {status}",
                "POST",
                f"shipments/{shipment_id}/status",
                200,
                params={
                    "status": status,
                    "notes": notes,
                    "latitude": 43.6532,
                    "longitude": -79.3832
                }
            )
            
            if success and response:
                print(f"   ✓ Status updated: {response.get('new_status')}")
        
        return True

    def test_get_shipment_tracking(self, shipment_id):
        """Test GET /api/operations/shipments/{id}/tracking - Get tracking events"""
        if not shipment_id:
            print("   ⚠️  Skipping - no shipment ID available")
            return False
            
        success, response = self.run_test(
            "Get Tracking Events",
            "GET",
            f"shipments/{shipment_id}/tracking",
            200
        )
        
        if success and isinstance(response, list):
            print(f"   ✓ Found {len(response)} tracking events")
            for event in response[:3]:  # Show first 3 events
                print(f"   - {event.get('new_status', 'N/A')}: {event.get('notes', 'N/A')}")
            return True
        
        return False

    def test_margin_calculation(self, order_id):
        """Test margin calculation after shipment creation"""
        if not order_id:
            print("   ⚠️  Skipping - no order ID available")
            return False
            
        # Get order details after shipment was created/dispatched
        success, response = self.run_test(
            "Margin Calculation Verification",
            "GET",
            f"orders/{order_id}",
            200
        )
        
        if success and response:
            customer_rate = response.get('total_amount', 0)  # What customer pays
            total_cost = response.get('total_cost', 0)       # What we pay carriers
            margin_amount = response.get('margin_amount', 0)
            margin_percentage = response.get('margin_percentage', 0)
            
            print(f"   ✓ Customer Rate: ${customer_rate}")
            print(f"   ✓ Carrier Cost: ${total_cost}")
            print(f"   ✓ Margin Amount: ${margin_amount}")
            print(f"   ✓ Margin Percentage: {margin_percentage}%")
            
            # Verify calculation: (customer_rate - carrier_cost) / customer_rate * 100
            expected_margin = customer_rate - total_cost
            expected_percentage = (expected_margin / customer_rate * 100) if customer_rate > 0 else 0
            
            if (abs(margin_amount - expected_margin) < 0.01 and 
                abs(margin_percentage - expected_percentage) < 0.01):
                print(f"   ✅ Margin calculation verified!")
                return True
            else:
                print(f"   ❌ Margin calculation mismatch")
                print(f"      Expected: ${expected_margin} ({expected_percentage}%)")
                print(f"      Actual: ${margin_amount} ({margin_percentage}%)")
        
        return False

    def test_cancel_order(self):
        """Test POST /api/operations/orders/{id}/cancel - Cancel order"""
        # Create a new order specifically for cancellation test
        if not self.created_entities['customers']:
            print("   ⚠️  Skipping - no customer available")
            return False
            
        customer_id = self.created_entities['customers'][0]
        
        order_data = {
            "tenant_id": self.tenant_id,
            "customer_id": customer_id,
            "customer_reference": "PO-CANCEL-001",
            "origin_city": "Toronto",
            "origin_state_province": "ON",
            "destination_city": "Vancouver", 
            "destination_state_province": "BC",
            "freight_type": "ftl",
            "customer_rate": 2000.0,
            "currency": "CAD"
        }
        
        # Create order to cancel
        success, response = self.run_test(
            "Create Order for Cancellation",
            "POST",
            "orders",
            200,
            data=order_data
        )
        
        if not success or not response.get('id'):
            return False
            
        cancel_order_id = response.get('id')
        
        # Now cancel it
        success, response = self.run_test(
            "Cancel Order",
            "POST",
            f"orders/{cancel_order_id}/cancel",
            200,
            params={"reason": "Customer requested cancellation"}
        )
        
        return success

    def run_comprehensive_tests(self):
        """Run all Orders & Shipments tests"""
        print("=" * 80)
        print("TMS Orders & Shipments API Tests - Phase 3")
        print("Testing Orders (Sales) & Shipments (Operations)")
        print("Canada-First Design with Automatic Tax Calculation")
        print("=" * 80)

        # Login
        if not self.login("aminderpro@gmail.com", "Admin@123!"):
            print("\n❌ Authentication failed - cannot continue tests")
            return False

        # Setup test data
        if not self.setup_test_data():
            print("\n❌ Test data setup failed - cannot continue")
            return False

        print(f"\n📋 Testing Orders API...")
        
        # Test order creation and management
        order_id = self.test_create_order()
        self.test_list_orders()
        self.test_get_order_details(order_id)
        self.test_update_order(order_id)
        self.test_confirm_order(order_id)
        self.test_cancel_order()

        print(f"\n🚛 Testing Shipments API...")
        
        # Test shipment creation and operations
        shipment_id = self.test_create_shipment(order_id)
        self.test_list_shipments()
        self.test_dispatch_shipment(shipment_id)
        self.test_update_shipment_status(shipment_id)
        self.test_get_shipment_tracking(shipment_id)

        print(f"\n💰 Testing Business Logic...")
        
        # Test margin calculations
        self.test_margin_calculation(order_id)

        # Print results
        print("\n" + "=" * 80)
        print("📊 TEST RESULTS SUMMARY")
        print("=" * 80)
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
    tester = TMSOrdersShipmentsTest()
    success = tester.run_comprehensive_tests()
    return 0 if success else 1


if __name__ == "__main__":
    sys.exit(main())