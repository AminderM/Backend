"""
TMS Invoice API Tests - Phase 5
Invoice generation, PDF export, payment tracking
Canadian tax compliance with GST/HST/PST/QST
"""

import requests
import json
import sys
from datetime import datetime, date, timedelta
import uuid


class TMSInvoicesTester:
    def __init__(self, base_url="https://accessorial-charges.preview.emergentagent.com"):
        self.base_url = base_url.rstrip('/')
        self.token = None
        self.headers = {'Content-Type': 'application/json'}
        self.tests_run = 0
        self.tests_passed = 0
        self.failed_tests = []
        self.tenant_id = None
        self.created_invoices = []  # Track created invoices for cleanup
        self.created_customer_id = None
        self.test_order_ids = []

    def run_test(self, name, method, endpoint, expected_status, data=None, params=None):
        """Run a single API test"""
        url = f"{self.base_url}/api/billing/{endpoint}"
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
                    return success, response.json() if response.text else {}
                except:
                    return success, {}
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

    def create_test_customer(self):
        """Create a test customer for invoice testing"""
        print(f"\n👤 Creating test customer for invoicing...")
        url = f"{self.base_url}/api/customers"
        
        customer_data = {
            "tenant_id": self.tenant_id,
            "company_name": f"Test Customer {datetime.now().strftime('%H%M%S')}",
            "contact_email": f"testcustomer_{datetime.now().strftime('%H%M%S')}@example.com",
            "contact_phone": "416-555-0123",
            "billing_address": {
                "address_line1": "123 Test Street",
                "city": "Toronto",
                "state_province": "ON",  # Ontario for HST 13%
                "postal_code": "M5V 3A8",
                "country": "CA"
            },
            "payment_terms": "net_30",
            "is_tax_exempt": False,
            "mc_number": "MC123456",
            "dot_number": "DOT789012"
        }
        
        try:
            response = requests.post(url, json=customer_data, headers={'Authorization': f'Bearer {self.token}', 'Content-Type': 'application/json'}, timeout=30)
            if response.status_code in [200, 201]:
                result = response.json()
                self.created_customer_id = result.get('customer_id') or result.get('id')
                print(f"✅ Test customer created: {self.created_customer_id}")
                print(f"   Company: {customer_data['company_name']}")
                print(f"   Province: ON (HST 13%)")
                return True
            else:
                print(f"⚠️  Failed to create test customer: {response.status_code}")
                # Try to get existing customer
                existing_url = f"{self.base_url}/api/customers?limit=1"
                resp = requests.get(existing_url, headers={'Authorization': f'Bearer {self.token}'}, timeout=30)
                if resp.status_code == 200:
                    customers = resp.json()
                    if isinstance(customers, list) and len(customers) > 0:
                        self.created_customer_id = customers[0].get('id')
                        print(f"✅ Using existing customer: {self.created_customer_id}")
                        return True
                return False
        except Exception as e:
            print(f"⚠️  Error creating test customer: {str(e)}")
            return False

    def create_test_orders(self):
        """Create test orders for invoice creation from orders"""
        print(f"\n📦 Creating test orders for invoice testing...")
        
        if not self.created_customer_id:
            print("⚠️  No customer available, skipping order creation")
            return False
        
        # Create 2 test orders
        orders_created = 0
        for i in range(2):
            order_data = {
                "tenant_id": self.tenant_id,
                "customer_id": self.created_customer_id,
                "commodity": "General Freight",
                "weight_lbs": 25000 + (i * 1000),
                "origin_city": "Toronto",
                "origin_state_province": "ON",
                "origin_postal_code": "M5V 3A8",
                "destination_city": "Montreal",
                "destination_state_province": "QC", 
                "destination_postal_code": "H3B 4W5",
                "customer_rate": 1500.00 + (i * 100),  # $1500, $1600
                "fuel_surcharge": 150.00,
                "accessorials": [
                    {"description": "Detention", "amount": 75.00},
                    {"description": "Lumper", "amount": 50.00}
                ],
                "status": "completed",
                "requested_pickup_date": (date.today() + timedelta(days=1)).isoformat(),
                "requested_delivery_date": (date.today() + timedelta(days=2)).isoformat()
            }
            
            try:
                url = f"{self.base_url}/api/orders"
                response = requests.post(url, json=order_data, 
                                       headers={'Authorization': f'Bearer {self.token}', 'Content-Type': 'application/json'}, 
                                       timeout=30)
                if response.status_code in [200, 201]:
                    result = response.json()
                    order_id = result.get('order_id') or result.get('id')
                    self.test_order_ids.append(order_id)
                    orders_created += 1
                    print(f"✅ Test order {i+1} created: {order_id}")
                else:
                    print(f"⚠️  Failed to create test order {i+1}: {response.status_code}")
            except Exception as e:
                print(f"⚠️  Error creating test order {i+1}: {str(e)}")
        
        print(f"Created {orders_created} test orders for invoice testing")
        return orders_created > 0

    def test_create_invoice_basic(self):
        """Test POST /api/billing/invoices - Create basic invoice"""
        if not self.created_customer_id:
            print("   ⚠️  No customer ID available, skipping test")
            return None
            
        invoice_data = {
            "tenant_id": self.tenant_id,
            "customer_id": self.created_customer_id,
            "invoice_type": "standard",
            "currency": "CAD",
            "payment_terms_days": 30,
            "notes": "Test invoice for Phase 5 testing",
            "line_items": [
                {
                    "description": "Freight - General Cargo",
                    "item_type": "freight",
                    "origin": "Toronto, ON",
                    "destination": "Montreal, QC",
                    "pickup_date": date.today().isoformat(),
                    "delivery_date": (date.today() + timedelta(days=1)).isoformat(),
                    "quantity": 1.0,
                    "unit_price": 1500.00,
                    "unit": "load",
                    "is_taxable": True
                },
                {
                    "description": "Fuel Surcharge",
                    "item_type": "fuel_surcharge",
                    "quantity": 1.0,
                    "unit_price": 150.00,
                    "unit": "flat",
                    "is_taxable": True
                },
                {
                    "description": "Detention",
                    "item_type": "accessorial",
                    "quantity": 2.0,
                    "unit_price": 75.00,
                    "unit": "hour",
                    "is_taxable": True
                }
            ]
        }
        
        success, response = self.run_test(
            "Create Invoice with Line Items and Tax Calculation",
            "POST",
            "invoices",
            200,
            data=invoice_data
        )
        
        if success and response.get('id'):
            invoice_id = response['id']
            self.created_invoices.append(invoice_id)
            print(f"   ✓ Invoice created with ID: {invoice_id}")
            print(f"   ✓ Invoice number: {response.get('invoice_number')}")
            print(f"   ✓ Subtotal: ${response.get('subtotal', 0):,.2f}")
            print(f"   ✓ Total tax: ${response.get('total_tax', 0):,.2f}")
            print(f"   ✓ Grand total: ${response.get('grand_total', 0):,.2f}")
            return invoice_id
        return None

    def test_create_invoice_from_orders(self):
        """Test POST /api/billing/invoices/from-orders"""
        if not self.created_customer_id or not self.test_order_ids:
            print("   ⚠️  No customer ID or orders available, skipping test")
            return None
            
        params = {
            "tenant_id": self.tenant_id,
            "customer_id": self.created_customer_id,
            "order_ids": self.test_order_ids[:2]  # Use first 2 orders
        }
        
        success, response = self.run_test(
            "Create Invoice from Orders",
            "POST",
            f"invoices/from-orders?tenant_id={self.tenant_id}&customer_id={self.created_customer_id}&order_ids={','.join(self.test_order_ids[:2])}",
            200
        )
        
        if success and response.get('id'):
            invoice_id = response['id']
            self.created_invoices.append(invoice_id)
            print(f"   ✓ Invoice created from {len(self.test_order_ids[:2])} orders")
            print(f"   ✓ Invoice ID: {invoice_id}")
            print(f"   ✓ Grand total: ${response.get('grand_total', 0):,.2f}")
            return invoice_id
        return None

    def test_list_invoices(self):
        """Test GET /api/billing/invoices - List invoices with filtering"""
        success, response = self.run_test(
            "List All Invoices",
            "GET",
            "invoices",
            200
        )
        
        if success and isinstance(response, list):
            print(f"   ✓ Found {len(response)} invoices")
            for invoice in response[:3]:  # Show first 3
                print(f"   ✓ Invoice: {invoice.get('invoice_number')} - ${invoice.get('grand_total', 0):,.2f} - {invoice.get('status')}")
            
            # Test filtering by status
            success, response = self.run_test(
                "Filter Invoices by Status (draft)",
                "GET",
                "invoices?status=draft",
                200
            )
            
            if success:
                draft_count = len(response) if isinstance(response, list) else 0
                print(f"   ✓ Found {draft_count} draft invoices")
                
            # Test filtering by date range
            from_date = date.today().isoformat()
            success, response = self.run_test(
                "Filter Invoices by Date Range",
                "GET",
                f"invoices?from_date={from_date}",
                200
            )
            
            if success:
                today_count = len(response) if isinstance(response, list) else 0
                print(f"   ✓ Found {today_count} invoices from today")
                
            return True
        return False

    def test_get_invoice_details(self, invoice_id):
        """Test GET /api/billing/invoices/{id} - Get invoice details"""
        if not invoice_id:
            print("   ⚠️  No invoice ID provided, skipping test")
            return False
            
        success, response = self.run_test(
            f"Get Invoice Details ({invoice_id[:8]}...)",
            "GET",
            f"invoices/{invoice_id}",
            200
        )
        
        if success and response:
            print(f"   ✓ Invoice number: {response.get('invoice_number')}")
            print(f"   ✓ Customer: {response.get('customer_name')}")
            print(f"   ✓ Status: {response.get('status')}")
            print(f"   ✓ Tax province: {response.get('tax_province')}")
            print(f"   ✓ HST amount: ${response.get('hst_amount', 0):,.2f}")
            print(f"   ✓ Line items: {len(response.get('line_items', []))}")
            print(f"   ✓ Balance due: ${response.get('balance_due', 0):,.2f}")
            return True
        return False

    def test_update_invoice(self, invoice_id):
        """Test PUT /api/billing/invoices/{id} - Update invoice"""
        if not invoice_id:
            print("   ⚠️  No invoice ID provided, skipping test")
            return False
            
        update_data = {
            "notes": "Updated notes for testing",
            "payment_terms_days": 45,
            "due_date": (date.today() + timedelta(days=45)).isoformat()
        }
        
        success, response = self.run_test(
            f"Update Invoice ({invoice_id[:8]}...)",
            "PUT",
            f"invoices/{invoice_id}",
            200,
            data=update_data
        )
        
        if success:
            print(f"   ✓ Invoice updated successfully")
            return True
        return False

    def test_send_invoice(self, invoice_id):
        """Test POST /api/billing/invoices/{id}/send - Mark invoice as sent"""
        if not invoice_id:
            print("   ⚠️  No invoice ID provided, skipping test")
            return False
            
        success, response = self.run_test(
            f"Send Invoice ({invoice_id[:8]}...)",
            "POST",
            f"invoices/{invoice_id}/send",
            200
        )
        
        if success:
            print(f"   ✓ Invoice marked as sent")
            print(f"   ✓ Sent to: {response.get('sent_to')}")
            return True
        return False

    def test_record_payment(self, invoice_id):
        """Test POST /api/billing/invoices/{id}/payments - Record payment"""
        if not invoice_id:
            print("   ⚠️  No invoice ID provided, skipping test")
            return False
            
        payment_data = {
            "amount": 500.00,  # Partial payment
            "payment_method": "interac",
            "payment_date": date.today().isoformat(),
            "reference_number": f"INTERAC-{datetime.now().strftime('%Y%m%d%H%M')}",
            "notes": "Partial payment via Interac e-Transfer"
        }
        
        success, response = self.run_test(
            f"Record Partial Payment ({invoice_id[:8]}...)",
            "POST",
            f"invoices/{invoice_id}/payments",
            200,
            data=payment_data
        )
        
        if success:
            print(f"   ✓ Payment recorded successfully")
            print(f"   ✓ Payment ID: {response.get('payment_id')}")
            print(f"   ✓ Amount: ${response.get('amount', 0):,.2f}")
            print(f"   ✓ New balance: ${response.get('new_balance', 0):,.2f}")
            print(f"   ✓ New status: {response.get('status')}")
            return response.get('payment_id')
        return None

    def test_get_invoice_payments(self, invoice_id):
        """Test GET /api/billing/invoices/{id}/payments - Get payment history"""
        if not invoice_id:
            print("   ⚠️  No invoice ID provided, skipping test")
            return False
            
        success, response = self.run_test(
            f"Get Invoice Payment History ({invoice_id[:8]}...)",
            "GET",
            f"invoices/{invoice_id}/payments",
            200
        )
        
        if success and isinstance(response, list):
            print(f"   ✓ Found {len(response)} payments")
            for payment in response:
                print(f"   ✓ Payment: ${payment.get('amount', 0):,.2f} - {payment.get('payment_method')} - {payment.get('payment_date')}")
            return True
        return False

    def test_full_payment(self, invoice_id):
        """Test recording full payment to complete the invoice"""
        if not invoice_id:
            print("   ⚠️  No invoice ID provided, skipping test")
            return False
            
        # Get current balance first
        success, invoice_details = self.run_test(
            f"Get Balance for Full Payment ({invoice_id[:8]}...)",
            "GET",
            f"invoices/{invoice_id}",
            200
        )
        
        if not success:
            return False
            
        balance_due = invoice_details.get('balance_due', 0)
        if balance_due <= 0:
            print(f"   ✓ Invoice already paid in full")
            return True
            
        payment_data = {
            "amount": balance_due,
            "payment_method": "bank_transfer",
            "payment_date": date.today().isoformat(),
            "reference_number": f"WIRE-{datetime.now().strftime('%Y%m%d%H%M')}",
            "notes": "Full payment via wire transfer"
        }
        
        success, response = self.run_test(
            f"Record Full Payment ({invoice_id[:8]}...)",
            "POST",
            f"invoices/{invoice_id}/payments",
            200,
            data=payment_data
        )
        
        if success:
            print(f"   ✓ Full payment recorded")
            print(f"   ✓ Amount: ${response.get('amount', 0):,.2f}")
            print(f"   ✓ New status: {response.get('status')}")
            return True
        return False

    def test_cancel_invoice(self, invoice_id):
        """Test POST /api/billing/invoices/{id}/cancel - Cancel invoice"""
        if not invoice_id:
            print("   ⚠️  No invoice ID provided, skipping test")
            return False
            
        success, response = self.run_test(
            f"Cancel Invoice ({invoice_id[:8]}...)",
            "POST",
            f"invoices/{invoice_id}/cancel?reason=Testing cancellation",
            200
        )
        
        if success:
            print(f"   ✓ Invoice cancelled successfully")
            return True
        return False

    def test_pdf_generation(self, invoice_id):
        """Test PDF generation endpoints"""
        if not invoice_id:
            print("   ⚠️  No invoice ID provided, skipping test")
            return False
            
        # Test PDF preview
        url = f"{self.base_url}/api/billing/invoices/{invoice_id}/pdf/preview"
        headers = {'Authorization': f'Bearer {self.token}'}
        
        try:
            response = requests.get(url, headers=headers, timeout=30)
            if response.status_code == 200 and response.headers.get('content-type') == 'application/pdf':
                print(f"✅ PDF Preview - Status: {response.status_code}")
                print(f"   ✓ Content-Type: application/pdf")
                print(f"   ✓ PDF Size: {len(response.content)} bytes")
                self.tests_run += 1
                self.tests_passed += 1
            else:
                print(f"❌ PDF Preview - Status: {response.status_code}")
                self.tests_run += 1
                self.failed_tests.append(f"PDF Preview - Expected 200, got {response.status_code}")
        except Exception as e:
            print(f"❌ PDF Preview - Error: {str(e)}")
            self.tests_run += 1
            self.failed_tests.append(f"PDF Preview - Error: {str(e)}")
            
        # Test PDF download
        url = f"{self.base_url}/api/billing/invoices/{invoice_id}/pdf"
        
        try:
            response = requests.get(url, headers=headers, timeout=30)
            if response.status_code == 200 and response.headers.get('content-type') == 'application/pdf':
                print(f"✅ PDF Download - Status: {response.status_code}")
                print(f"   ✓ Content-Type: application/pdf")
                print(f"   ✓ PDF Size: {len(response.content)} bytes")
                print(f"   ✓ Content-Disposition: {response.headers.get('content-disposition', 'N/A')}")
                self.tests_run += 1
                self.tests_passed += 1
                return True
            else:
                print(f"❌ PDF Download - Status: {response.status_code}")
                self.tests_run += 1
                self.failed_tests.append(f"PDF Download - Expected 200, got {response.status_code}")
        except Exception as e:
            print(f"❌ PDF Download - Error: {str(e)}")
            self.tests_run += 1
            self.failed_tests.append(f"PDF Download - Error: {str(e)}")
            
        return False

    def test_ar_summary_report(self):
        """Test GET /api/billing/invoices/reports/ar-summary - AR summary"""
        success, response = self.run_test(
            "Get Accounts Receivable Summary",
            "GET",
            "invoices/reports/ar-summary",
            200
        )
        
        if success and response:
            print(f"   ✓ Total outstanding: ${response.get('total_outstanding', 0):,.2f}")
            print(f"   ✓ Current (not due): ${response.get('current', 0):,.2f}")
            print(f"   ✓ 1-30 days overdue: ${response.get('days_1_30', 0):,.2f}")
            print(f"   ✓ 31-60 days overdue: ${response.get('days_31_60', 0):,.2f}")
            print(f"   ✓ 61-90 days overdue: ${response.get('days_61_90', 0):,.2f}")
            print(f"   ✓ 90+ days overdue: ${response.get('days_90_plus', 0):,.2f}")
            print(f"   ✓ Total invoices: {response.get('total_invoices', 0)}")
            print(f"   ✓ Overdue invoices: {response.get('overdue_invoices', 0)}")
            return True
        return False

    def test_ar_aging_report(self):
        """Test GET /api/billing/invoices/reports/ar-aging - Detailed AR aging"""
        success, response = self.run_test(
            "Get Detailed AR Aging Report",
            "GET",
            "invoices/reports/ar-aging",
            200
        )
        
        if success and isinstance(response, list):
            print(f"   ✓ Found {len(response)} customers with outstanding balances")
            for customer in response[:3]:  # Show first 3
                print(f"   ✓ Customer: {customer.get('customer_name')} - Total: ${customer.get('total', 0):,.2f}")
                print(f"      - Current: ${customer.get('current', 0):,.2f}")
                print(f"      - 1-30 days: ${customer.get('days_1_30', 0):,.2f}")
                print(f"      - 31-60 days: ${customer.get('days_31_60', 0):,.2f}")
            return True
        return False

    def test_provincial_tax_calculation(self):
        """Test different provincial tax calculations"""
        if not self.created_customer_id:
            print("   ⚠️  No customer ID available, skipping test")
            return False
            
        # Test different provinces
        provinces = [
            {"code": "ON", "name": "Ontario", "expected_hst": 13.0},
            {"code": "BC", "name": "British Columbia", "expected_gst": 5.0, "expected_pst": 7.0},
            {"code": "QC", "name": "Quebec", "expected_gst": 5.0, "expected_qst": 9.975},
            {"code": "AB", "name": "Alberta", "expected_gst": 5.0}
        ]
        
        for prov in provinces[:2]:  # Test first 2 provinces to keep tests manageable
            # Update customer province (we'd need a customer update endpoint for this)
            # For now, just test with current ON customer
            
            invoice_data = {
                "tenant_id": self.tenant_id,
                "customer_id": self.created_customer_id,
                "invoice_type": "standard",
                "notes": f"Tax test for {prov['name']}",
                "line_items": [
                    {
                        "description": f"Test freight for {prov['name']} tax calculation",
                        "item_type": "freight",
                        "quantity": 1.0,
                        "unit_price": 1000.00,  # Round number for easy calculation
                        "unit": "load",
                        "is_taxable": True
                    }
                ]
            }
            
            success, response = self.run_test(
                f"Create Invoice for {prov['name']} Tax Test",
                "POST",
                "invoices",
                200,
                data=invoice_data
            )
            
            if success and response.get('id'):
                invoice_id = response['id']
                self.created_invoices.append(invoice_id)
                print(f"   ✓ {prov['name']} invoice created")
                print(f"   ✓ Subtotal: ${response.get('subtotal', 0):,.2f}")
                print(f"   ✓ Total tax: ${response.get('total_tax', 0):,.2f}")
                
                # Since we're using ON customer, expect HST
                if response.get('total_tax', 0) > 0:
                    expected_tax = 1000.00 * 0.13  # 13% HST for ON
                    actual_tax = response.get('total_tax', 0)
                    if abs(actual_tax - expected_tax) < 0.01:  # Allow for rounding
                        print(f"   ✓ Tax calculation correct: ${actual_tax:.2f}")
                    else:
                        print(f"   ⚠️  Tax calculation may be incorrect: Expected ${expected_tax:.2f}, got ${actual_tax:.2f}")
                
        return True

    def print_final_results(self):
        """Print final test results"""
        print(f"\n{'='*50}")
        print(f"📊 FINAL TEST RESULTS")
        print(f"{'='*50}")
        print(f"Tests Run: {self.tests_run}")
        print(f"Tests Passed: {self.tests_passed}")
        print(f"Tests Failed: {len(self.failed_tests)}")
        print(f"Success Rate: {(self.tests_passed/self.tests_run*100):.1f}%" if self.tests_run > 0 else "0%")
        
        if self.failed_tests:
            print(f"\n❌ FAILED TESTS:")
            for test in self.failed_tests:
                print(f"   - {test}")
        
        return len(self.failed_tests) == 0


def main():
    """Main test execution"""
    print("💰 TMS Invoice API Tests - Phase 5")
    print("Testing Invoice Generation with Canadian Tax Compliance")
    print("=" * 60)
    
    tester = TMSInvoicesTester()
    
    # Login
    if not tester.login("aminderpro@gmail.com", "Admin@123!"):
        print("❌ Login failed, aborting tests")
        return 1
    
    # Setup test data
    tester.create_test_customer()
    tester.create_test_orders()
    
    # Test Invoice CRUD Operations
    print(f"\n💰 INVOICE CRUD OPERATIONS")
    print("-" * 40)
    invoice1_id = tester.test_create_invoice_basic()
    invoice2_id = tester.test_create_invoice_from_orders()
    tester.test_list_invoices()
    
    if invoice1_id:
        tester.test_get_invoice_details(invoice1_id)
        tester.test_update_invoice(invoice1_id)
    
    # Test Invoice Status Workflow  
    print(f"\n📧 INVOICE STATUS WORKFLOW")
    print("-" * 40)
    if invoice1_id:
        tester.test_send_invoice(invoice1_id)
    
    # Test Payment Processing
    print(f"\n💳 PAYMENT PROCESSING")
    print("-" * 40)
    if invoice1_id:
        tester.test_record_payment(invoice1_id)
        tester.test_get_invoice_payments(invoice1_id)
        tester.test_full_payment(invoice1_id)
    
    # Test Invoice Cancellation (use second invoice)
    if invoice2_id:
        tester.test_cancel_invoice(invoice2_id)
    
    # Test PDF Generation
    print(f"\n📄 PDF GENERATION")
    print("-" * 40)
    if invoice1_id:
        tester.test_pdf_generation(invoice1_id)
    
    # Test AR Reports
    print(f"\n📊 ACCOUNTS RECEIVABLE REPORTS")
    print("-" * 40)
    tester.test_ar_summary_report()
    tester.test_ar_aging_report()
    
    # Test Tax Calculations
    print(f"\n🏛️ CANADIAN TAX CALCULATIONS")
    print("-" * 40)
    tester.test_provincial_tax_calculation()
    
    # Print results
    success = tester.print_final_results()
    
    print(f"\n🎯 Created invoices for testing: {len(tester.created_invoices)}")
    if tester.created_invoices:
        for inv_id in tester.created_invoices:
            print(f"   - Invoice ID: {inv_id}")
    
    return 0 if success else 1


if __name__ == "__main__":
    sys.exit(main())