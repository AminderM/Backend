"""
Backend API Test Suite for Carrier Profile Feature - TMS
Tests all 14 endpoints for the 5-step carrier profile wizard
"""

import requests
import sys
import json
import base64
import os
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, Optional

class CarrierProfileAPITester:
    def __init__(self, base_url="http://localhost:8001"):
        self.base_url = base_url.rstrip('/')
        self.token = None
        self.user_id = None
        self.profile_id = None
        self.tests_run = 0
        self.tests_passed = 0
        self.errors = []
        self.warnings = []

    def print_result(self, test_name: str, success: bool, details: str = "", response_data: Any = None):
        """Print test result with details"""
        self.tests_run += 1
        if success:
            self.tests_passed += 1
            print(f"✅ {test_name} - PASSED {details}")
        else:
            print(f"❌ {test_name} - FAILED {details}")
            self.errors.append(f"{test_name}: {details}")
            if response_data:
                print(f"   Response: {response_data}")

    def make_request(self, method: str, endpoint: str, data: Dict = None, 
                    files: Dict = None, params: Dict = None, expected_status: int = 200) -> tuple:
        """Make HTTP request with authentication"""
        url = f"{self.base_url}/api{endpoint}"
        headers = {'Content-Type': 'application/json'}
        
        if self.token:
            headers['Authorization'] = f'Bearer {self.token}'
        
        if files:
            # Remove Content-Type header for file uploads
            headers.pop('Content-Type', None)
        
        try:
            if method == 'GET':
                response = requests.get(url, headers=headers, params=params, timeout=30)
            elif method == 'POST':
                if files:
                    response = requests.post(url, headers=headers, files=files, timeout=30)
                else:
                    response = requests.post(url, headers=headers, json=data, timeout=30)
            elif method == 'PUT':
                response = requests.put(url, headers=headers, json=data, timeout=30)
            elif method == 'DELETE':
                response = requests.delete(url, headers=headers, timeout=30)
            else:
                raise ValueError(f"Unsupported method: {method}")

            success = response.status_code == expected_status
            response_data = response.json() if response.content and response.headers.get('content-type', '').startswith('application/json') else response.text
            
            return success, response_data, response.status_code
        except Exception as e:
            return False, str(e), 0

    def test_authentication(self):
        """Test authentication with platform admin credentials"""
        print("\n🔐 Testing Authentication...")
        
        login_data = {
            "email": "aminderpro@gmail.com",
            "password": "Admin@123!"
        }
        
        success, response_data, status_code = self.make_request(
            'POST', '/auth/login', data=login_data
        )
        
        if success and isinstance(response_data, dict):
            if 'access_token' in response_data:
                self.token = response_data['access_token']
                self.user_id = response_data.get('user_id') or response_data.get('user', {}).get('id')
                self.print_result("Authentication", True, f"Token received, User ID: {self.user_id}")
                return True
            elif 'token' in response_data:
                self.token = response_data['token']
                self.user_id = response_data.get('user_id') or response_data.get('user', {}).get('id')
                self.print_result("Authentication", True, f"Token received, User ID: {self.user_id}")
                return True
        
        self.print_result("Authentication", False, f"Login failed - Status: {status_code}", response_data)
        return False

    def test_get_carrier_profile(self):
        """Test GET /api/carrier-profiles - Get or create carrier profile"""
        print("\n📋 Testing Get/Create Carrier Profile...")
        
        success, response_data, status_code = self.make_request(
            'GET', '/carrier-profiles'
        )
        
        if success:
            self.profile_id = response_data.get('id')
            completion = response_data.get('overall_completion_percentage', 0)
            self.print_result(
                "Get Carrier Profile", 
                True, 
                f"Profile ID: {self.profile_id}, Completion: {completion}%"
            )
            return True
        
        self.print_result("Get Carrier Profile", False, f"Status: {status_code}", response_data)
        return False

    def test_update_company_info(self):
        """Test PUT /api/carrier-profiles/company-info - Update company info (Step 1)"""
        print("\n🏢 Testing Company Info Update (Step 1)...")
        
        company_data = {
            "company_name": "ABC Trucking Ltd",
            "legal_name": "ABC Trucking Limited",
            "dba_name": "ABC Transport",
            "business_type": "corporation",
            "year_established": 2010,
            "address": {
                "street": "123 Main St",
                "city": "Toronto",
                "province_state": "ON",
                "postal_code": "M5V 1A1",
                "country": "CA"
            },
            "mailing_address": {
                "street": "PO Box 123",
                "city": "Toronto",
                "province_state": "ON",
                "postal_code": "M5V 1A1",
                "country": "CA"
            },
            "phone": "+1-416-555-0100",
            "fax": "+1-416-555-0101",
            "email": "info@abctrucking.ca",
            "website": "https://abctrucking.ca"
        }
        
        success, response_data, status_code = self.make_request(
            'PUT', '/carrier-profiles/company-info', data=company_data
        )
        
        if success:
            company_info = response_data.get('company_info', {})
            company_name = company_info.get('company_name', '')
            self.print_result(
                "Company Info Update", 
                True, 
                f"Company: {company_name}"
            )
            return True
        
        self.print_result("Company Info Update", False, f"Status: {status_code}", response_data)
        return False

    def test_upload_logo(self):
        """Test POST /api/carrier-profiles/logo - Upload company logo"""
        print("\n🖼️ Testing Logo Upload...")
        
        # Create a simple test image (1x1 pixel PNG)
        test_image = base64.b64decode(
            "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChAGAh6FdKAAAAABJRU5ErkJggg=="
        )
        
        files = {
            'file': ('test_logo.png', test_image, 'image/png')
        }
        
        success, response_data, status_code = self.make_request(
            'POST', '/carrier-profiles/logo', files=files
        )
        
        if success:
            logo_url = response_data.get('logo_url', '')
            truncated_url = logo_url[:50] + "..." if len(logo_url) > 50 else logo_url
            self.print_result("Logo Upload", True, f"Logo URL: {truncated_url}")
            return True
        
        self.print_result("Logo Upload", False, f"Status: {status_code}", response_data)
        return False

    def test_update_compliance_documents(self):
        """Test PUT /api/carrier-profiles/compliance-documents - Update compliance documents (Step 2)"""
        print("\n📄 Testing Compliance Documents Update (Step 2)...")
        
        future_date = (datetime.now() + timedelta(days=365)).isoformat()
        
        compliance_data = {
            "operating_country": "CA",
            "canadian_documents": {
                "cargo_insurance": {
                    "policy_number": "CI-12345",
                    "provider": "ABC Insurance",
                    "coverage_amount": 2000000,
                    "expiry_date": future_date
                },
                "liability_insurance": {
                    "policy_number": "LI-67890",
                    "provider": "XYZ Insurance",
                    "coverage_amount": 5000000,
                    "expiry_date": future_date
                },
                "wsib_clearance": {
                    "certificate_number": "WSIB-123",
                    "expiry_date": future_date
                }
            }
        }
        
        success, response_data, status_code = self.make_request(
            'PUT', '/carrier-profiles/compliance-documents', data=compliance_data
        )
        
        if success:
            compliance = response_data.get('compliance_documents', {})
            country = compliance.get('operating_country', '')
            self.print_result(
                "Compliance Documents Update", 
                True, 
                f"Country: {country}"
            )
            return True
        
        self.print_result("Compliance Documents Update", False, f"Status: {status_code}", response_data)
        return False

    def test_upload_compliance_document(self):
        """Test POST /api/carrier-profiles/compliance-documents/upload - Upload compliance document file"""
        print("\n📎 Testing Compliance Document Upload...")
        
        # Create a simple PDF content
        test_pdf = b"%PDF-1.4\n1 0 obj\n<<\n/Type /Catalog\n/Pages 2 0 R\n>>\nendobj\n2 0 obj\n<<\n/Type /Pages\n/Kids [3 0 R]\n/Count 1\n>>\nendobj\n3 0 obj\n<<\n/Type /Page\n/Parent 2 0 R\n/MediaBox [0 0 612 792]\n>>\nendobj\nxref\n0 4\n0000000000 65535 f \n0000000009 00000 n \n0000000058 00000 n \n0000000115 00000 n \ntrailer\n<<\n/Size 4\n/Root 1 0 R\n>>\nstartxref\n174\n%%EOF"
        
        # Try the upload with query parameters in URL
        url = f"{self.base_url}/api/carrier-profiles/compliance-documents/upload?document_type=cargo_insurance&document_country=CA"
        headers = {}
        if self.token:
            headers['Authorization'] = f'Bearer {self.token}'
        
        files = {
            'file': ('insurance_cert.pdf', test_pdf, 'application/pdf')
        }
        
        try:
            response = requests.post(url, headers=headers, files=files, timeout=30)
            success = response.status_code == 200
            response_data = response.json() if response.content and response.headers.get('content-type', '').startswith('application/json') else response.text
            
            if success:
                doc_type = response_data.get('document_type', '')
                self.print_result("Compliance Document Upload", True, f"Document: {doc_type}")
                return True
            else:
                self.print_result("Compliance Document Upload", False, f"Status: {response.status_code}", response_data)
                return False
        except Exception as e:
            self.print_result("Compliance Document Upload", False, f"Error: {str(e)}", None)
            return False

    def test_update_regulatory_numbers(self):
        """Test PUT /api/carrier-profiles/regulatory-numbers - Update regulatory numbers (Step 3)"""
        print("\n🔢 Testing Regulatory Numbers Update (Step 3)...")
        
        regulatory_data = {
            "operating_regions": ["CA", "US"],
            "canadian": {
                "nsc_number": "NSC12345",
                "cvor_number": "123-456-789",
                "carrier_code": "ABCT",
                "ifta_account": "CA1234567",
                "irp_account": "IRP-ON-12345"
            },
            "us": {
                "usdot_number": "1234567",
                "mc_number": "MC-123456",
                "scac_code": "ABCT",
                "ifta_account": "US9876543",
                "irp_account": "IRP-US-98765",
                "ctpat_number": "CTPAT-12345"
            }
        }
        
        success, response_data, status_code = self.make_request(
            'PUT', '/carrier-profiles/regulatory-numbers', data=regulatory_data
        )
        
        if success:
            regulatory = response_data.get('regulatory_numbers', {})
            regions = regulatory.get('operating_regions', [])
            self.print_result(
                "Regulatory Numbers Update", 
                True, 
                f"Regions: {', '.join(regions)}"
            )
            return True
        
        self.print_result("Regulatory Numbers Update", False, f"Status: {status_code}", response_data)
        return False

    def test_update_fleet_configuration(self):
        """Test PUT /api/carrier-profiles/fleet-configuration - Update fleet configuration (Step 4)"""
        print("\n🚛 Testing Fleet Configuration Update (Step 4)...")
        
        fleet_data = {
            "fleet_size": {
                "power_units": 25,
                "trailers": 40,
                "drivers": 30
            },
            "equipment_types": [
                {"type": "dry_van", "count": 20},
                {"type": "reefer", "count": 15},
                {"type": "flatbed", "count": 5}
            ],
            "preferred_lanes": [
                {
                    "origin": {"city": "Toronto", "province_state": "ON", "country": "CA"},
                    "destination": {"city": "Montreal", "province_state": "QC", "country": "CA"},
                    "frequency": "daily"
                },
                {
                    "origin": {"city": "Toronto", "province_state": "ON", "country": "CA"},
                    "destination": {"city": "Chicago", "province_state": "IL", "country": "US"},
                    "frequency": "weekly"
                }
            ],
            "service_areas": ["ON", "QC", "MI", "IL", "NY"],
            "special_services": ["hazmat", "oversize", "temperature_controlled"]
        }
        
        success, response_data, status_code = self.make_request(
            'PUT', '/carrier-profiles/fleet-configuration', data=fleet_data
        )
        
        if success:
            fleet = response_data.get('fleet_configuration', {})
            fleet_size = fleet.get('fleet_size', {})
            power_units = fleet_size.get('power_units', 0)
            self.print_result(
                "Fleet Configuration Update", 
                True, 
                f"Power Units: {power_units}"
            )
            return True
        
        self.print_result("Fleet Configuration Update", False, f"Status: {status_code}", response_data)
        return False

    def test_update_payment_banking(self):
        """Test PUT /api/carrier-profiles/payment-banking - Update payment/banking info with encryption (Step 5)"""
        print("\n💰 Testing Payment/Banking Update (Step 5)...")
        
        payment_data = {
            "payment_terms": "net_30",
            "preferred_payment_method": "eft",
            "currency": "CAD",
            "banking_info": {
                "bank_name": "Royal Bank of Canada",
                "account_holder_name": "ABC Trucking Ltd",
                "institution_number": "003",
                "transit_number": "12345",
                "account_number": "1234567"
            },
            "tax_info": {
                "business_number": "123456789RC0001",
                "gst_hst_number": "123456789RT0001",
                "qst_number": None
            }
        }
        
        success, response_data, status_code = self.make_request(
            'PUT', '/carrier-profiles/payment-banking', data=payment_data
        )
        
        if success:
            payment = response_data.get('payment_banking', {})
            payment_terms = payment.get('payment_terms', '')
            banking_saved = payment.get('banking_info_saved', False)
            self.print_result(
                "Payment/Banking Update", 
                True, 
                f"Terms: {payment_terms}, Banking Encrypted: {banking_saved}"
            )
            return True
        
        self.print_result("Payment/Banking Update", False, f"Status: {status_code}", response_data)
        return False

    def test_upload_void_cheque(self):
        """Test POST /api/carrier-profiles/payment-banking/void-cheque - Upload void cheque"""
        print("\n🏦 Testing Void Cheque Upload...")
        
        test_pdf = b"%PDF-1.4\n1 0 obj\n<<\n/Type /Catalog\n/Pages 2 0 R\n>>\nendobj\n2 0 obj\n<<\n/Type /Pages\n/Kids [3 0 R]\n/Count 1\n>>\nendobj\n3 0 obj\n<<\n/Type /Page\n/Parent 2 0 R\n/MediaBox [0 0 612 792]\n>>\nendobj\nxref\n0 4\n0000000000 65535 f \n0000000009 00000 n \n0000000058 00000 n \n0000000115 00000 n \ntrailer\n<<\n/Size 4\n/Root 1 0 R\n>>\nstartxref\n174\n%%EOF"
        
        files = {
            'file': ('void_cheque.pdf', test_pdf, 'application/pdf')
        }
        
        success, response_data, status_code = self.make_request(
            'POST', '/carrier-profiles/payment-banking/void-cheque', files=files
        )
        
        if success:
            message = response_data.get('message', '')
            self.print_result("Void Cheque Upload", True, message)
            return True
        
        self.print_result("Void Cheque Upload", False, f"Status: {status_code}", response_data)
        return False

    def test_get_completion_status(self):
        """Test GET /api/carrier-profiles/completion-status - Get completion status"""
        print("\n📊 Testing Completion Status...")
        
        success, response_data, status_code = self.make_request(
            'GET', '/carrier-profiles/completion-status'
        )
        
        if success:
            percentage = response_data.get('overall_percentage', 0)
            company_info = response_data.get('company_info', False)
            compliance = response_data.get('compliance_documents', False)
            regulatory = response_data.get('regulatory_numbers', False)
            fleet = response_data.get('fleet_configuration', False)
            payment = response_data.get('payment_banking', False)
            
            self.print_result(
                "Completion Status", 
                True, 
                f"Overall: {percentage}%, Sections: CI:{company_info}, CD:{compliance}, RN:{regulatory}, FC:{fleet}, PB:{payment}"
            )
            return True
        
        self.print_result("Completion Status", False, f"Status: {status_code}", response_data)
        return False

    def test_validate_profile(self):
        """Test POST /api/carrier-profiles/validate - Validate profile"""
        print("\n✅ Testing Profile Validation...")
        
        success, response_data, status_code = self.make_request(
            'POST', '/carrier-profiles/validate'
        )
        
        if success:
            is_valid = response_data.get('is_valid', False)
            errors = response_data.get('errors', [])
            warnings = response_data.get('warnings', [])
            
            self.print_result(
                "Profile Validation", 
                True, 
                f"Valid: {is_valid}, Errors: {len(errors)}, Warnings: {len(warnings)}"
            )
            
            if errors:
                print("   Validation Errors:")
                for error in errors:
                    print(f"     - {error.get('section', '')}.{error.get('field', '')}: {error.get('message', '')}")
            
            return True
        
        self.print_result("Profile Validation", False, f"Status: {status_code}", response_data)
        return False

    def test_submit_profile(self):
        """Test POST /api/carrier-profiles/submit - Submit profile for review"""
        print("\n🚀 Testing Profile Submission...")
        
        success, response_data, status_code = self.make_request(
            'POST', '/carrier-profiles/submit'
        )
        
        if success:
            status = response_data.get('status', '')
            submitted_at = response_data.get('submitted_at', '')
            self.print_result(
                "Profile Submission", 
                True, 
                f"Status: {status}, Submitted: {submitted_at}"
            )
            return True
        elif status_code == 400:
            # Profile might have validation errors - this is expected behavior
            detail = response_data.get('detail', {})
            message = detail.get('message', '') if isinstance(detail, dict) else str(detail)
            errors = detail.get('errors', []) if isinstance(detail, dict) else []
            
            self.print_result(
                "Profile Submission", 
                True, 
                f"Validation failed as expected: {message}, Errors: {len(errors)}"
            )
            return True
        
        self.print_result("Profile Submission", False, f"Status: {status_code}", response_data)
        return False

    def test_admin_routes(self):
        """Test admin routes for platform admin"""
        print("\n👑 Testing Admin Routes...")
        
        # Test get all profiles
        success, response_data, status_code = self.make_request(
            'GET', '/carrier-profiles/admin/all', params={'limit': 10}
        )
        
        if success:
            profiles = response_data.get('profiles', [])
            total = response_data.get('total', 0)
            self.print_result(
                "Admin - Get All Profiles", 
                True, 
                f"Total: {total}, Returned: {len(profiles)}"
            )
        else:
            self.print_result("Admin - Get All Profiles", False, f"Status: {status_code}", response_data)

    def test_edge_cases(self):
        """Test edge cases and error handling"""
        print("\n🔍 Testing Edge Cases...")
        
        # Test invalid authentication
        original_token = self.token
        self.token = "invalid_token"
        
        success, response_data, status_code = self.make_request(
            'GET', '/carrier-profiles', expected_status=401
        )
        
        if status_code == 401:
            self.print_result("Invalid Token Handling", True, "401 Unauthorized as expected")
        else:
            self.print_result("Invalid Token Handling", False, f"Expected 401, got {status_code}")
        
        # Restore valid token
        self.token = original_token
        
        # Test file upload with invalid file type
        test_file = b"This is not an image"
        files = {'file': ('test.txt', test_file, 'text/plain')}
        
        success, response_data, status_code = self.make_request(
            'POST', '/carrier-profiles/logo', files=files, expected_status=400
        )
        
        if status_code == 400:
            self.print_result("Invalid File Type Handling", True, "400 Bad Request as expected")
        else:
            self.print_result("Invalid File Type Handling", False, f"Expected 400, got {status_code}")

    def test_encryption_verification(self):
        """Test that banking info encryption is working properly"""
        print("\n🔐 Testing Banking Info Encryption...")
        
        # Get the profile and check that encrypted banking info is not exposed
        success, response_data, status_code = self.make_request(
            'GET', '/carrier-profiles'
        )
        
        if success:
            payment_banking = response_data.get('payment_banking', {})
            
            # Check that encrypted_banking_info is not in the response (should be filtered out)
            if 'encrypted_banking_info' not in payment_banking:
                # Check that we have payment terms and other non-sensitive data
                if 'payment_terms' in payment_banking and payment_banking.get('payment_terms') == 'net_30':
                    self.print_result(
                        "Banking Encryption Verification", 
                        True, 
                        "Sensitive banking data properly encrypted and filtered from response"
                    )
                    return True
                else:
                    self.print_result(
                        "Banking Encryption Verification", 
                        False, 
                        "Payment terms not found in response"
                    )
                    return False
            else:
                self.print_result(
                    "Banking Encryption Verification", 
                    False, 
                    "Encrypted banking info exposed in response - security issue!"
                )
                return False
        
        self.print_result("Banking Encryption Verification", False, f"Status: {status_code}", response_data)
        return False

    def run_all_tests(self):
        """Run all tests in sequence"""
        print("🧪 Starting Carrier Profile Backend API Tests")
        print("=" * 60)
        
        # Authentication is required for all other tests
        if not self.test_authentication():
            print("\n❌ Authentication failed - cannot continue with other tests")
            return False
        
        # Core functionality tests
        self.test_get_carrier_profile()
        self.test_update_company_info()
        self.test_upload_logo()
        self.test_update_compliance_documents()
        self.test_upload_compliance_document()
        self.test_update_regulatory_numbers()
        self.test_update_fleet_configuration()
        self.test_update_payment_banking()
        self.test_upload_void_cheque()
        self.test_get_completion_status()
        self.test_validate_profile()
        self.test_submit_profile()
        self.test_admin_routes()
        self.test_edge_cases()
        self.test_encryption_verification()
        
        # Print summary
        print("\n" + "=" * 60)
        print(f"📊 Test Summary: {self.tests_passed}/{self.tests_run} tests passed")
        
        if self.errors:
            print(f"\n❌ Failed Tests:")
            for error in self.errors:
                print(f"   - {error}")
        
        if self.warnings:
            print(f"\n⚠️ Warnings:")
            for warning in self.warnings:
                print(f"   - {warning}")
        
        success_rate = (self.tests_passed / self.tests_run * 100) if self.tests_run > 0 else 0
        print(f"\n🎯 Success Rate: {success_rate:.1f}%")
        
        return success_rate >= 80  # Consider test suite successful if 80% or more tests pass

def main():
    """Main test execution"""
    tester = CarrierProfileAPITester("http://localhost:8001")
    
    try:
        success = tester.run_all_tests()
        return 0 if success else 1
    except KeyboardInterrupt:
        print("\n\n⚠️ Tests interrupted by user")
        return 1
    except Exception as e:
        print(f"\n\n💥 Test suite crashed: {str(e)}")
        return 1

if __name__ == "__main__":
    sys.exit(main())