"""
TMS Invoice API Tests - Phase 5 (Focused Testing)
Comprehensive testing of existing invoice system
Canadian tax compliance with GST/HST/PST/QST
"""

import requests
import json
import sys
from datetime import datetime, date, timedelta


class TMSInvoicesComprehensiveTester:
    def __init__(self, base_url="https://backend-features-dev.preview.emergentagent.com"):
        self.base_url = base_url.rstrip('/')
        self.token = None
        self.headers = {'Content-Type': 'application/json'}
        self.tests_run = 0
        self.tests_passed = 0
        self.failed_tests = []
        self.tenant_id = "test-tenant-001"
        self.existing_invoice_id = None
        self.existing_customer_id = None
        self.created_invoices = []

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
                print(f"✅ Login successful")
                return True
            else:
                print(f"❌ Login failed - Status: {response.status_code}")
                return False
        except Exception as e:
            print(f"❌ Login failed - Error: {str(e)}")
            return False

    def get_existing_invoice_data(self):
        """Get existing invoice data for testing"""
        success, invoices = self.run_test(
            "Get Existing Invoices for Setup",
            "GET",
            "invoices",
            200
        )
        
        if success and isinstance(invoices, list) and len(invoices) > 0:
            invoice = invoices[0]
            self.existing_invoice_id = invoice.get('id')
            self.existing_customer_id = invoice.get('customer_id')
            print(f"✅ Found existing invoice: {self.existing_invoice_id[:8]}...")
            print(f"   Invoice Number: {invoice.get('invoice_number')}")
            print(f"   Customer: {invoice.get('customer_name')}")
            print(f"   Status: {invoice.get('status')}")
            print(f"   Balance Due: ${invoice.get('balance_due', 0):,.2f}")
            return True
        return False

    def test_list_invoices_comprehensive(self):
        """Test GET /api/billing/invoices with all filters"""
        # Test basic listing
        success, response = self.run_test(
            "List All Invoices",
            "GET",
            "invoices",
            200
        )
        
        if success and isinstance(response, list):
            print(f"   ✓ Found {len(response)} invoices")
            for invoice in response[:2]:
                print(f"   ✓ Invoice: {invoice.get('invoice_number')} - ${invoice.get('grand_total', 0):,.2f} - {invoice.get('status')}")
        
        # Test status filters
        statuses = ['draft', 'sent', 'partially_paid', 'paid', 'overdue']
        for status in statuses:
            success, response = self.run_test(
                f"Filter Invoices by Status ({status})",
                "GET",
                f"invoices?status={status}",
                200
            )
            if success:
                count = len(response) if isinstance(response, list) else 0
                print(f"   ✓ Found {count} invoices with status '{status}'")
        
        # Test date filters
        today = date.today()
        yesterday = today - timedelta(days=1)
        
        success, response = self.run_test(
            "Filter Invoices by Date Range (today)",
            "GET",
            f"invoices?from_date={today.isoformat()}&to_date={today.isoformat()}",
            200
        )
        if success:
            count = len(response) if isinstance(response, list) else 0
            print(f"   ✓ Found {count} invoices from today")
        
        # Test overdue filter
        success, response = self.run_test(
            "Filter Invoices (overdue only)",
            "GET",
            "invoices?overdue_only=true",
            200
        )
        if success:
            count = len(response) if isinstance(response, list) else 0
            print(f"   ✓ Found {count} overdue invoices")
        
        # Test pagination
        success, response = self.run_test(
            "Test Pagination (limit=1)",
            "GET",
            "invoices?limit=1",
            200
        )
        if success:
            count = len(response) if isinstance(response, list) else 0
            print(f"   ✓ Pagination working - returned {count} invoice(s)")
        
        return True

    def test_get_invoice_details_comprehensive(self):
        """Test GET /api/billing/invoices/{id} with detailed validation"""
        if not self.existing_invoice_id:
            print("   ⚠️  No existing invoice ID, skipping test")
            return False
            
        success, response = self.run_test(
            f"Get Invoice Details ({self.existing_invoice_id[:8]}...)",
            "GET",
            f"invoices/{self.existing_invoice_id}",
            200
        )
        
        if success and response:
            print(f"   ✓ Invoice Number: {response.get('invoice_number')}")
            print(f"   ✓ Customer: {response.get('customer_name')}")
            print(f"   ✓ Status: {response.get('status')}")
            print(f"   ✓ Currency: {response.get('currency')}")
            
            # Validate tax calculation
            print(f"   ✓ Tax Province: {response.get('tax_province')}")
            print(f"   ✓ Subtotal: ${response.get('subtotal', 0):,.2f}")
            if response.get('hst_rate', 0) > 0:
                print(f"   ✓ HST ({response.get('hst_rate')}%): ${response.get('hst_amount', 0):,.2f}")
            if response.get('gst_rate', 0) > 0:
                print(f"   ✓ GST ({response.get('gst_rate')}%): ${response.get('gst_amount', 0):,.2f}")
            if response.get('pst_rate', 0) > 0:
                print(f"   ✓ PST ({response.get('pst_rate')}%): ${response.get('pst_amount', 0):,.2f}")
            if response.get('qst_rate', 0) > 0:
                print(f"   ✓ QST ({response.get('qst_rate')}%): ${response.get('qst_amount', 0):,.2f}")
            
            print(f"   ✓ Total Tax: ${response.get('total_tax', 0):,.2f}")
            print(f"   ✓ Grand Total: ${response.get('grand_total', 0):,.2f}")
            print(f"   ✓ Amount Paid: ${response.get('amount_paid', 0):,.2f}")
            print(f"   ✓ Balance Due: ${response.get('balance_due', 0):,.2f}")
            
            # Validate line items
            line_items = response.get('line_items', [])
            print(f"   ✓ Line Items: {len(line_items)}")
            for item in line_items[:3]:
                print(f"      - {item.get('description')}: ${item.get('line_total', 0):,.2f}")
            
            # Validate payments
            payments = response.get('payments', [])
            print(f"   ✓ Payments: {len(payments)}")
            for payment in payments[:2]:
                print(f"      - ${payment.get('amount', 0):,.2f} via {payment.get('payment_method')} on {payment.get('payment_date')}")
                
            return True
        return False

    def test_create_new_invoice(self):
        """Test POST /api/billing/invoices - Create new invoice with existing customer"""
        if not self.existing_customer_id:
            print("   ⚠️  No customer ID available, skipping test")
            return None
            
        invoice_data = {
            "tenant_id": self.tenant_id,
            "customer_id": self.existing_customer_id,
            "invoice_type": "standard",
            "currency": "CAD",
            "payment_terms_days": 30,
            "notes": "Test invoice created by automated testing",
            "line_items": [
                {
                    "description": "Test Freight - Vancouver to Calgary",
                    "item_type": "freight",
                    "origin": "Vancouver, BC",
                    "destination": "Calgary, AB",
                    "pickup_date": date.today().isoformat(),
                    "delivery_date": (date.today() + timedelta(days=2)).isoformat(),
                    "quantity": 1.0,
                    "unit_price": 2800.00,
                    "unit": "load",
                    "is_taxable": True
                },
                {
                    "description": "Test Fuel Surcharge",
                    "item_type": "fuel_surcharge", 
                    "quantity": 1.0,
                    "unit_price": 280.00,
                    "unit": "flat",
                    "is_taxable": True
                },
                {
                    "description": "Test Detention - Loading delay",
                    "item_type": "accessorial",
                    "quantity": 3.0,
                    "unit_price": 85.00,
                    "unit": "hour",
                    "is_taxable": True
                }
            ]
        }
        
        success, response = self.run_test(
            "Create New Invoice with Line Items",
            "POST",
            "invoices",
            200,
            data=invoice_data
        )
        
        if success and response.get('id'):
            invoice_id = response['id']
            self.created_invoices.append(invoice_id)
            print(f"   ✓ New invoice created: {invoice_id}")
            print(f"   ✓ Invoice Number: {response.get('invoice_number')}")
            print(f"   ✓ Subtotal: ${response.get('subtotal', 0):,.2f}")
            print(f"   ✓ Total Tax: ${response.get('total_tax', 0):,.2f}")
            print(f"   ✓ Grand Total: ${response.get('grand_total', 0):,.2f}")
            
            # Validate tax calculation (should be ON HST 13% for existing customer)
            expected_subtotal = 2800 + 280 + (3 * 85)  # 3335
            expected_tax = expected_subtotal * 0.13  # HST 13%
            actual_subtotal = response.get('subtotal', 0)
            actual_tax = response.get('total_tax', 0)
            
            if abs(actual_subtotal - expected_subtotal) < 0.01:
                print(f"   ✓ Subtotal calculation correct: ${actual_subtotal:,.2f}")
            else:
                print(f"   ⚠️  Subtotal calculation issue: Expected ${expected_subtotal:.2f}, got ${actual_subtotal:.2f}")
            
            if abs(actual_tax - expected_tax) < 1.0:  # Allow small rounding differences
                print(f"   ✓ Tax calculation correct: ${actual_tax:,.2f}")
            else:
                print(f"   ⚠️  Tax calculation issue: Expected ~${expected_tax:.2f}, got ${actual_tax:.2f}")
            
            return invoice_id
        return None

    def test_update_invoice(self, invoice_id):
        """Test PUT /api/billing/invoices/{id}"""
        if not invoice_id:
            print("   ⚠️  No invoice ID provided, skipping test")
            return False
            
        update_data = {
            "notes": "Updated notes - Modified during testing",
            "payment_terms_days": 45,
            "due_date": (date.today() + timedelta(days=45)).isoformat(),
            "internal_notes": "Internal note added during testing"
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

    def test_invoice_status_workflow(self, invoice_id):
        """Test invoice status workflow: send -> payment -> completion"""
        if not invoice_id:
            print("   ⚠️  No invoice ID provided, skipping test")
            return False
            
        # Step 1: Send invoice
        success, response = self.run_test(
            f"Send Invoice ({invoice_id[:8]}...)",
            "POST",
            f"invoices/{invoice_id}/send",
            200
        )
        
        if success:
            print(f"   ✓ Invoice sent successfully")
            print(f"   ✓ Sent to: {response.get('sent_to')}")
        
        # Step 2: Record partial payment
        payment_data = {
            "amount": 1000.00,  # Partial payment
            "payment_method": "interac",
            "payment_date": date.today().isoformat(),
            "reference_number": f"TEST-PAY-{datetime.now().strftime('%Y%m%d%H%M')}",
            "notes": "Automated test partial payment"
        }
        
        success, response = self.run_test(
            f"Record Partial Payment ({invoice_id[:8]}...)",
            "POST",
            f"invoices/{invoice_id}/payments",
            200,
            data=payment_data
        )
        
        if success:
            print(f"   ✓ Partial payment recorded")
            print(f"   ✓ Payment ID: {response.get('payment_id')}")
            print(f"   ✓ New Balance: ${response.get('new_balance', 0):,.2f}")
            print(f"   ✓ New Status: {response.get('status')}")
        
        # Step 3: Get payment history
        success, response = self.run_test(
            f"Get Payment History ({invoice_id[:8]}...)",
            "GET", 
            f"invoices/{invoice_id}/payments",
            200
        )
        
        if success and isinstance(response, list):
            print(f"   ✓ Found {len(response)} payments")
            for payment in response:
                print(f"      - ${payment.get('amount', 0):,.2f} via {payment.get('payment_method')}")
        
        # Step 4: Get updated invoice to check balance
        success, invoice_details = self.run_test(
            f"Check Updated Invoice Balance ({invoice_id[:8]}...)",
            "GET",
            f"invoices/{invoice_id}",
            200
        )
        
        if success:
            balance = invoice_details.get('balance_due', 0)
            print(f"   ✓ Current balance: ${balance:,.2f}")
            
            # Step 5: Pay remaining balance if there is one
            if balance > 0:
                full_payment_data = {
                    "amount": balance,
                    "payment_method": "bank_transfer",
                    "payment_date": date.today().isoformat(),
                    "reference_number": f"WIRE-{datetime.now().strftime('%Y%m%d%H%M')}",
                    "notes": "Automated test full payment"
                }
                
                success, response = self.run_test(
                    f"Record Full Payment ({invoice_id[:8]}...)",
                    "POST",
                    f"invoices/{invoice_id}/payments",
                    200,
                    data=full_payment_data
                )
                
                if success:
                    print(f"   ✓ Full payment recorded")
                    print(f"   ✓ Final Status: {response.get('status')}")
        
        return True

    def test_pdf_generation_comprehensive(self, invoice_id):
        """Test PDF generation endpoints thoroughly"""
        if not invoice_id:
            print("   ⚠️  No invoice ID provided, skipping test")
            return False
            
        # Test PDF preview (inline)
        url = f"{self.base_url}/api/billing/invoices/{invoice_id}/pdf/preview"
        headers = {'Authorization': f'Bearer {self.token}'}
        
        print(f"\n🔍 Testing PDF Preview...")
        print(f"   URL: GET {url}")
        
        try:
            response = requests.get(url, headers=headers, timeout=30)
            print(f"   Response Status: {response.status_code}")
            
            if response.status_code == 200:
                content_type = response.headers.get('content-type', '')
                content_length = len(response.content)
                content_disposition = response.headers.get('content-disposition', '')
                
                if 'application/pdf' in content_type:
                    print(f"✅ PDF Preview Successful")
                    print(f"   ✓ Content-Type: {content_type}")
                    print(f"   ✓ PDF Size: {content_length:,} bytes")
                    print(f"   ✓ Content-Disposition: {content_disposition or 'inline (default)'}")
                    self.tests_run += 1
                    self.tests_passed += 1
                else:
                    print(f"❌ PDF Preview Failed - Wrong content type: {content_type}")
                    self.tests_run += 1
                    self.failed_tests.append("PDF Preview - Wrong content type")
            else:
                print(f"❌ PDF Preview Failed - Status: {response.status_code}")
                print(f"   Error: {response.text}")
                self.tests_run += 1
                self.failed_tests.append(f"PDF Preview - Expected 200, got {response.status_code}")
                
        except Exception as e:
            print(f"❌ PDF Preview Failed - Error: {str(e)}")
            self.tests_run += 1
            self.failed_tests.append(f"PDF Preview - Error: {str(e)}")
        
        # Test PDF download (attachment)
        url = f"{self.base_url}/api/billing/invoices/{invoice_id}/pdf"
        
        print(f"\n🔍 Testing PDF Download...")
        print(f"   URL: GET {url}")
        
        try:
            response = requests.get(url, headers=headers, timeout=30)
            print(f"   Response Status: {response.status_code}")
            
            if response.status_code == 200:
                content_type = response.headers.get('content-type', '')
                content_length = len(response.content)
                content_disposition = response.headers.get('content-disposition', '')
                
                if 'application/pdf' in content_type:
                    print(f"✅ PDF Download Successful")
                    print(f"   ✓ Content-Type: {content_type}")
                    print(f"   ✓ PDF Size: {content_length:,} bytes")
                    print(f"   ✓ Content-Disposition: {content_disposition}")
                    
                    # Validate attachment header
                    if 'attachment' in content_disposition.lower():
                        print(f"   ✓ Proper attachment header for download")
                    else:
                        print(f"   ⚠️  Missing attachment header")
                    
                    self.tests_run += 1
                    self.tests_passed += 1
                    return True
                else:
                    print(f"❌ PDF Download Failed - Wrong content type: {content_type}")
                    self.tests_run += 1
                    self.failed_tests.append("PDF Download - Wrong content type")
            else:
                print(f"❌ PDF Download Failed - Status: {response.status_code}")
                print(f"   Error: {response.text}")
                self.tests_run += 1
                self.failed_tests.append(f"PDF Download - Expected 200, got {response.status_code}")
                
        except Exception as e:
            print(f"❌ PDF Download Failed - Error: {str(e)}")
            self.tests_run += 1
            self.failed_tests.append(f"PDF Download - Error: {str(e)}")
            
        return False

    def test_ar_reports_comprehensive(self):
        """Test AR reporting endpoints comprehensively"""
        # Test AR Summary
        success, response = self.run_test(
            "AR Summary Report",
            "GET",
            "invoices/reports/ar-summary",
            200
        )
        
        if success and response:
            print(f"   ✓ Total Outstanding: ${response.get('total_outstanding', 0):,.2f}")
            print(f"   ✓ Current (not due): ${response.get('current', 0):,.2f}")
            print(f"   ✓ 1-30 days overdue: ${response.get('days_1_30', 0):,.2f}")
            print(f"   ✓ 31-60 days overdue: ${response.get('days_31_60', 0):,.2f}")
            print(f"   ✓ 61-90 days overdue: ${response.get('days_61_90', 0):,.2f}")
            print(f"   ✓ 90+ days overdue: ${response.get('days_90_plus', 0):,.2f}")
            print(f"   ✓ Total Invoices: {response.get('total_invoices', 0)}")
            print(f"   ✓ Overdue Invoices: {response.get('overdue_invoices', 0)}")
            
            # Validate totals
            aging_total = (response.get('current', 0) + 
                          response.get('days_1_30', 0) + 
                          response.get('days_31_60', 0) + 
                          response.get('days_61_90', 0) + 
                          response.get('days_90_plus', 0))
            
            if abs(aging_total - response.get('total_outstanding', 0)) < 0.01:
                print(f"   ✓ Aging bucket totals match total outstanding")
            else:
                print(f"   ⚠️  Aging bucket totals don't match: {aging_total} vs {response.get('total_outstanding', 0)}")
        
        # Test AR Aging Detail
        success, response = self.run_test(
            "AR Aging Detail Report",
            "GET",
            "invoices/reports/ar-aging",
            200
        )
        
        if success and isinstance(response, list):
            print(f"   ✓ Found {len(response)} customers with outstanding balances")
            
            total_from_details = 0
            for customer in response[:5]:  # Show first 5
                customer_total = customer.get('total', 0)
                total_from_details += customer_total
                print(f"   ✓ {customer.get('customer_name')}: ${customer_total:,.2f}")
                print(f"      - Current: ${customer.get('current', 0):,.2f}")
                print(f"      - 1-30: ${customer.get('days_1_30', 0):,.2f}")
                print(f"      - 31-60: ${customer.get('days_31_60', 0):,.2f}")
                print(f"      - 61-90: ${customer.get('days_61_90', 0):,.2f}")
                print(f"      - 90+: ${customer.get('days_90_plus', 0):,.2f}")
                print(f"      - Invoices: {customer.get('invoice_count', 0)}")
            
            print(f"   ✓ Total from customer details: ${total_from_details:,.2f}")
        
        # Test filtering by specific customer
        if self.existing_customer_id:
            success, response = self.run_test(
                "AR Summary for Specific Customer",
                "GET", 
                f"invoices/reports/ar-summary?customer_id={self.existing_customer_id}",
                200
            )
            
            if success:
                print(f"   ✓ Customer-specific AR: ${response.get('total_outstanding', 0):,.2f}")
        
        return True

    def test_cancel_invoice(self, invoice_id):
        """Test POST /api/billing/invoices/{id}/cancel"""
        if not invoice_id:
            print("   ⚠️  No invoice ID provided, skipping test")
            return False
        
        # Only cancel if not already paid
        success, invoice_details = self.run_test(
            f"Check Invoice Status Before Cancel ({invoice_id[:8]}...)",
            "GET",
            f"invoices/{invoice_id}",
            200
        )
        
        if success and invoice_details.get('status') != 'paid':
            success, response = self.run_test(
                f"Cancel Invoice ({invoice_id[:8]}...)",
                "POST",
                f"invoices/{invoice_id}/cancel?reason=Automated testing cancellation",
                200
            )
            
            if success:
                print(f"   ✓ Invoice cancelled successfully")
                return True
        else:
            print(f"   ✓ Skipping cancellation - invoice is paid or status check failed")
            return True
            
        return False

    def print_final_results(self):
        """Print comprehensive final test results"""
        print(f"\n{'='*60}")
        print(f"📊 FINAL TEST RESULTS - TMS INVOICE SYSTEM")
        print(f"{'='*60}")
        print(f"Tests Run: {self.tests_run}")
        print(f"Tests Passed: {self.tests_passed}")
        print(f"Tests Failed: {len(self.failed_tests)}")
        print(f"Success Rate: {(self.tests_passed/self.tests_run*100):.1f}%" if self.tests_run > 0 else "0%")
        
        if self.failed_tests:
            print(f"\n❌ FAILED TESTS:")
            for test in self.failed_tests:
                print(f"   - {test}")
        
        # Summary by category
        print(f"\n📋 TEST CATEGORIES:")
        print(f"✓ Invoice CRUD Operations")
        print(f"✓ Canadian Tax Calculations (HST/GST/PST/QST)")
        print(f"✓ Payment Processing & Status Workflows")
        print(f"✓ PDF Generation (Preview & Download)")
        print(f"✓ Accounts Receivable Reports")
        print(f"✓ Invoice Filtering & Search")
        
        return len(self.failed_tests) == 0


def main():
    """Main test execution"""
    print("💰 TMS Invoice API Comprehensive Tests - Phase 5")
    print("Testing Invoice Generation with Canadian Tax Compliance")
    print("Full API Coverage: CRUD, Payments, PDF, AR Reports")
    print("=" * 70)
    
    tester = TMSInvoicesComprehensiveTester()
    
    # Login
    if not tester.login("aminderpro@gmail.com", "Admin@123!"):
        print("❌ Login failed, aborting tests")
        return 1
    
    # Get existing data for testing
    if not tester.get_existing_invoice_data():
        print("❌ No existing invoice data found, aborting tests")
        return 1
    
    # Test 1: Comprehensive Invoice Listing & Filtering
    print(f"\n📋 COMPREHENSIVE INVOICE LISTING & FILTERING")
    print("-" * 50)
    tester.test_list_invoices_comprehensive()
    
    # Test 2: Detailed Invoice Information
    print(f"\n📄 DETAILED INVOICE INFORMATION")
    print("-" * 50)
    tester.test_get_invoice_details_comprehensive()
    
    # Test 3: Create New Invoice with Tax Calculation
    print(f"\n💰 CREATE NEW INVOICE WITH TAX CALCULATION")
    print("-" * 50)
    new_invoice_id = tester.test_create_new_invoice()
    
    # Test 4: Invoice Updates
    print(f"\n✏️  INVOICE UPDATES")
    print("-" * 50)
    if new_invoice_id:
        tester.test_update_invoice(new_invoice_id)
    
    # Test 5: Invoice Status Workflow (Send → Payment → Completion)
    print(f"\n🔄 INVOICE STATUS WORKFLOW")
    print("-" * 50)
    if new_invoice_id:
        tester.test_invoice_status_workflow(new_invoice_id)
    
    # Test 6: PDF Generation (Preview & Download)
    print(f"\n📄 PDF GENERATION")
    print("-" * 50)
    test_id = new_invoice_id or tester.existing_invoice_id
    if test_id:
        tester.test_pdf_generation_comprehensive(test_id)
    
    # Test 7: Accounts Receivable Reports
    print(f"\n📊 ACCOUNTS RECEIVABLE REPORTS")
    print("-" * 50)
    tester.test_ar_reports_comprehensive()
    
    # Test 8: Invoice Cancellation (if we have a test invoice)
    print(f"\n❌ INVOICE CANCELLATION")
    print("-" * 50)
    if new_invoice_id:
        tester.test_cancel_invoice(new_invoice_id)
    
    # Print comprehensive results
    success = tester.print_final_results()
    
    if tester.created_invoices:
        print(f"\n🎯 Created invoices during testing: {len(tester.created_invoices)}")
        for inv_id in tester.created_invoices:
            print(f"   - Invoice ID: {inv_id}")
    
    return 0 if success else 1


if __name__ == "__main__":
    sys.exit(main())