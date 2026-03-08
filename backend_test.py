"""
TMS Vehicles/Fleet API Tests - Phase 4
Tests for Vehicle Management with Canadian Compliance (CVIP inspections)
VIN tracking, maintenance records, driver assignments, fleet tracking
"""

import requests
import json
import sys
from datetime import datetime, date, timedelta
import uuid

class TMSVehiclesTester:
    def __init__(self, base_url="https://5e2a63d0-abe8-4325-a9d8-8022eb861680.preview.emergentagent.com"):
        self.base_url = base_url.rstrip('/')
        self.token = None
        self.headers = {'Content-Type': 'application/json'}
        self.tests_run = 0
        self.tests_passed = 0
        self.failed_tests = []
        self.tenant_id = None
        self.created_vehicles = []  # Track created vehicles for cleanup
        self.created_driver_id = None

    def run_test(self, name, method, endpoint, expected_status, data=None, params=None):
        """Run a single API test"""
        url = f"{self.base_url}/api/fleet/{endpoint}"
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

    def create_test_driver(self):
        """Create a test driver for vehicle assignment tests"""
        print(f"\n👤 Creating test driver for vehicle assignments...")
        url = f"{self.base_url}/api/users"
        
        driver_data = {
            "email": f"test_driver_{datetime.now().strftime('%H%M%S')}@example.com",
            "password": "TestDriver123!",
            "full_name": "Test Driver",
            "phone": "555-0123",
            "role": "driver",
            "tenant_id": self.tenant_id,
            "license_number": "D123456789",
            "license_province": "ON",
            "license_expiry": "2025-12-31"
        }
        
        try:
            response = requests.post(url, json=driver_data, headers={'Authorization': f'Bearer {self.token}', 'Content-Type': 'application/json'}, timeout=30)
            if response.status_code in [200, 201]:
                result = response.json()
                self.created_driver_id = result.get('user_id') or result.get('id')
                print(f"✅ Test driver created: {self.created_driver_id}")
                return True
            else:
                print(f"⚠️  Failed to create test driver: {response.status_code} - Will use existing driver if available")
                # Try to get existing drivers for testing
                existing_drivers_url = f"{self.base_url}/api/users?role=driver&limit=1"
                resp = requests.get(existing_drivers_url, headers={'Authorization': f'Bearer {self.token}'}, timeout=30)
                if resp.status_code == 200:
                    drivers = resp.json()
                    if isinstance(drivers, list) and len(drivers) > 0:
                        self.created_driver_id = drivers[0].get('id')
                        print(f"✅ Using existing driver: {self.created_driver_id}")
                        return True
                return False
        except Exception as e:
            print(f"⚠️  Error creating test driver: {str(e)} - Will skip driver assignment tests")
            return False

    def test_create_power_unit(self):
        """Test POST /api/fleet/vehicles - Create power unit (tractor)"""
        tractor_data = {
            "tenant_id": self.tenant_id,
            "unit_number": f"T-{datetime.now().strftime('%H%M%S')}",
            "vehicle_type": "tractor_sleeper",
            "vin": f"1XKWDB0X57J{datetime.now().strftime('%H%M%S')}",
            "license_plate": f"TEST-{datetime.now().strftime('%H%M')}",
            "license_plate_province": "ON",
            "year": 2022,
            "make": "Freightliner",
            "model": "Cascadia",
            "fuel_type": "diesel",
            "gross_vehicle_weight_kg": 36000,
            "sleeper": True,
            "ownership_type": "company_owned",
            "current_odometer_km": 150000,
            "status": "available"
        }
        
        success, response = self.run_test(
            "Create Power Unit (Tractor)",
            "POST",
            "vehicles",
            200,
            data=tractor_data
        )
        
        if (success or response.get('id')) and response.get('id'):
            vehicle_id = response['id']
            self.created_vehicles.append(vehicle_id)
            print(f"   ✓ Power unit created with ID: {vehicle_id}")
            print(f"   ✓ Unit number: {response.get('unit_number')}")
            print(f"   ✓ Vehicle type: {response.get('vehicle_type')}")
            print(f"   ✓ Category: {response.get('category')}")
            return vehicle_id
        return None

    def test_create_trailer(self):
        """Test POST /api/fleet/vehicles - Create trailer with auto-categorization"""
        trailer_data = {
            "tenant_id": self.tenant_id,
            "unit_number": f"TR-{datetime.now().strftime('%H%M%S')}",
            "vehicle_type": "dry_van_trailer",
            "vin": f"1GRAA0621XK{datetime.now().strftime('%H%M%S')}",
            "license_plate": f"TRL-{datetime.now().strftime('%H%M')}",
            "license_plate_province": "ON",
            "year": 2021,
            "make": "Great Dane",
            "model": "Everest",
            "trailer_length_ft": 53,
            "trailer_width_ft": 8.5,
            "trailer_height_ft": 13.5,
            "ownership_type": "company_owned",
            "status": "available"
        }
        
        success, response = self.run_test(
            "Create Trailer with Auto-categorization",
            "POST",
            "vehicles",
            200,
            data=trailer_data
        )
        
        if (success or response.get('id')) and response.get('id'):
            vehicle_id = response['id']
            self.created_vehicles.append(vehicle_id)
            print(f"   ✓ Trailer created with ID: {vehicle_id}")
            print(f"   ✓ Unit number: {response.get('unit_number')}")
            print(f"   ✓ Vehicle type: {response.get('vehicle_type')}")
            print(f"   ✓ Auto-categorized as: {response.get('category')}")
            return vehicle_id
        return None

    def test_list_vehicles(self):
        """Test GET /api/fleet/vehicles - List vehicles with filtering"""
        success, response = self.run_test(
            "List All Vehicles",
            "GET",
            "vehicles",
            200
        )
        
        if success and isinstance(response, list):
            print(f"   ✓ Found {len(response)} vehicles")
            for vehicle in response[:3]:  # Show first 3
                print(f"   ✓ Vehicle: {vehicle.get('unit_number')} - {vehicle.get('vehicle_type')} - {vehicle.get('status')}")
            return True
        return False

    def test_list_vehicles_with_filters(self):
        """Test vehicle filtering by status, type, category"""
        # Test status filter
        success, response = self.run_test(
            "Filter Vehicles by Status (available)",
            "GET",
            "vehicles?status=available",
            200
        )
        
        if success:
            available_count = len(response) if isinstance(response, list) else 0
            print(f"   ✓ Found {available_count} available vehicles")
        
        # Test category filter
        success, response = self.run_test(
            "Filter Vehicles by Category (power_unit)",
            "GET",
            "vehicles?category=power_unit",
            200
        )
        
        if success:
            power_units = len(response) if isinstance(response, list) else 0
            print(f"   ✓ Found {power_units} power units")
        
        # Test CVIP expiring soon
        success, response = self.run_test(
            "Filter Vehicles - CVIP Expiring Soon",
            "GET",
            "vehicles?cvip_expiring_soon=true",
            200
        )
        
        if success:
            cvip_expiring = len(response) if isinstance(response, list) else 0
            print(f"   ✓ Found {cvip_expiring} vehicles with CVIP expiring soon")
        
        return True

    def test_vehicles_summary(self):
        """Test GET /api/fleet/vehicles/summary - Fleet summary"""
        success, response = self.run_test(
            "Get Fleet Summary",
            "GET",
            "vehicles/summary",
            200
        )
        
        if success and response:
            print(f"   ✓ Total vehicles: {response.get('total_vehicles', 0)}")
            print(f"   ✓ By status: {response.get('by_status', {})}")
            print(f"   ✓ By category: {response.get('by_category', {})}")
            print(f"   ✓ CVIP expiring (30 days): {response.get('cvip_expiring_30_days', 0)}")
            print(f"   ✓ CVIP expired: {response.get('cvip_expired', 0)}")
            print(f"   ✓ Compliance alerts: {response.get('compliance_alerts', 0)}")
            return True
        return False

    def test_get_vehicle_details(self, vehicle_id):
        """Test GET /api/fleet/vehicles/{id} - Get vehicle with details"""
        if not vehicle_id:
            print("   ⚠️  No vehicle ID provided, skipping test")
            return False
            
        success, response = self.run_test(
            f"Get Vehicle Details ({vehicle_id[:8]}...)",
            "GET",
            f"vehicles/{vehicle_id}",
            200
        )
        
        if success and response:
            print(f"   ✓ Unit number: {response.get('unit_number')}")
            print(f"   ✓ Year/Make/Model: {response.get('year_make_model')}")
            print(f"   ✓ Status: {response.get('status')}")
            print(f"   ✓ CVIP status: {response.get('cvip_status', 'unknown')}")
            print(f"   ✓ Recent inspections: {len(response.get('recent_inspections', []))}")
            print(f"   ✓ Recent maintenance: {len(response.get('recent_maintenance', []))}")
            return True
        return False

    def test_update_vehicle(self, vehicle_id):
        """Test PUT /api/fleet/vehicles/{id} - Update vehicle"""
        if not vehicle_id:
            print("   ⚠️  No vehicle ID provided, skipping test")
            return False
            
        update_data = {
            "current_odometer_km": 155000,
            "status": "in_use",
            "notes": "Updated for testing"
        }
        
        success, response = self.run_test(
            f"Update Vehicle ({vehicle_id[:8]}...)",
            "PUT",
            f"vehicles/{vehicle_id}",
            200,
            data=update_data
        )
        
        if success:
            print(f"   ✓ Vehicle updated successfully")
            return True
        return False

    def test_assign_driver(self, vehicle_id):
        """Test POST /api/fleet/vehicles/{id}/assign-driver"""
        if not vehicle_id or not self.created_driver_id:
            print("   ⚠️  No vehicle ID or driver ID available, skipping test")
            return False
            
        success, response = self.run_test(
            f"Assign Driver to Vehicle ({vehicle_id[:8]}...)",
            "POST",
            f"vehicles/{vehicle_id}/assign-driver?driver_id={self.created_driver_id}&is_primary=true",
            200
        )
        
        if success:
            print(f"   ✓ Driver assigned successfully")
            print(f"   ✓ Driver name: {response.get('driver_name')}")
            return True
        return False

    def test_add_cvip_inspection(self, vehicle_id):
        """Test POST /api/fleet/vehicles/{id}/inspections - Add CVIP"""
        if not vehicle_id:
            print("   ⚠️  No vehicle ID provided, skipping test")
            return False
            
        # Convert to query parameters
        params = {
            "inspection_type": "cvip",
            "inspection_date": date.today().isoformat(),
            "expiry_date": (date.today() + timedelta(days=365)).isoformat(),
            "result": "passed",
            "location": "Toronto Inspection Station",
            "inspector_name": "John Inspector",
            "sticker_number": f"CVIP-{datetime.now().strftime('%Y%m%d%H%M')}",
            "cost": 150.00,
            "notes": "Annual CVIP inspection completed"
        }
        
        success, response = self.run_test(
            f"Add CVIP Inspection ({vehicle_id[:8]}...)",
            "POST",
            f"vehicles/{vehicle_id}/inspections",
            200,
            params=params
        )
        
        if success:
            print(f"   ✓ CVIP inspection added successfully")
            print(f"   ✓ Inspection ID: {response.get('id')}")
            print(f"   ✓ Result: {response.get('result')}")
            return response.get('id')
        return None

    def test_get_vehicle_inspections(self, vehicle_id):
        """Test GET /api/fleet/vehicles/{id}/inspections"""
        if not vehicle_id:
            print("   ⚠️  No vehicle ID provided, skipping test")
            return False
            
        success, response = self.run_test(
            f"Get Vehicle Inspections ({vehicle_id[:8]}...)",
            "GET",
            f"vehicles/{vehicle_id}/inspections",
            200
        )
        
        if success and isinstance(response, list):
            print(f"   ✓ Found {len(response)} inspections")
            for inspection in response[:2]:  # Show first 2
                print(f"   ✓ Inspection: {inspection.get('inspection_type')} - {inspection.get('result')} - {inspection.get('inspection_date')}")
            return True
        return False

    def test_add_maintenance_record(self, vehicle_id):
        """Test POST /api/fleet/vehicles/{id}/maintenance"""
        if not vehicle_id:
            print("   ⚠️  No vehicle ID provided, skipping test")
            return False
            
        # Convert to query parameters
        params = {
            "maintenance_type": "preventive",
            "description": "Scheduled 90-day PM service",
            "scheduled_date": date.today().isoformat(),
            "completed_at": datetime.now().isoformat(),
            "odometer_at_service": 155000,
            "shop_name": "Toronto Fleet Services",
            "labor_cost": 250.00,
            "parts_cost": 150.00,
            "notes": "Oil change, filter replacement, brake inspection"
        }
        
        success, response = self.run_test(
            f"Add Maintenance Record ({vehicle_id[:8]}...)",
            "POST",
            f"vehicles/{vehicle_id}/maintenance",
            200,
            params=params
        )
        
        if success:
            print(f"   ✓ Maintenance record added successfully")
            print(f"   ✓ Maintenance ID: {response.get('id')}")
            print(f"   ✓ Total cost: ${response.get('total_cost', 0)}")
            return response.get('id')
        return None

    def test_get_vehicle_maintenance(self, vehicle_id):
        """Test GET /api/fleet/vehicles/{id}/maintenance"""
        if not vehicle_id:
            print("   ⚠️  No vehicle ID provided, skipping test")
            return False
            
        success, response = self.run_test(
            f"Get Vehicle Maintenance ({vehicle_id[:8]}...)",
            "GET",
            f"vehicles/{vehicle_id}/maintenance",
            200
        )
        
        if success and isinstance(response, list):
            print(f"   ✓ Found {len(response)} maintenance records")
            for maintenance in response[:2]:  # Show first 2
                print(f"   ✓ Maintenance: {maintenance.get('maintenance_type')} - ${maintenance.get('total_cost', 0)} - {maintenance.get('description')}")
            return True
        return False

    def test_update_vehicle_location(self, vehicle_id):
        """Test POST /api/fleet/vehicles/{id}/location"""
        if not vehicle_id:
            print("   ⚠️  No vehicle ID provided, skipping test")
            return False
            
        # Convert to query parameters
        params = {
            "latitude": 43.6532,
            "longitude": -79.3832,
            "speed_kmh": 65.0,
            "heading": 180.0,
            "odometer_km": 155100,
            "source": "gps"
        }
        
        success, response = self.run_test(
            f"Update Vehicle Location ({vehicle_id[:8]}...)",
            "POST",
            f"vehicles/{vehicle_id}/location",
            200,
            params=params
        )
        
        if success:
            print(f"   ✓ Vehicle location updated (Toronto, ON)")
            return True
        return False

    def test_fleet_tracking(self):
        """Test GET /api/fleet/vehicles/fleet-tracking - Real-time fleet map"""
        success, response = self.run_test(
            "Get Fleet Tracking Data",
            "GET",
            "vehicles/fleet-tracking",
            200
        )
        
        if success and isinstance(response, list):
            print(f"   ✓ Found {len(response)} vehicles in fleet tracking")
            for vehicle in response[:3]:  # Show first 3
                print(f"   ✓ Vehicle: {vehicle.get('unit_number')} - {vehicle.get('status')} - Lat: {vehicle.get('latitude')} - Driver: {vehicle.get('driver_name') or 'Unassigned'}")
            return True
        return False

    def test_unassign_driver(self, vehicle_id):
        """Test POST /api/fleet/vehicles/{id}/unassign-driver"""
        if not vehicle_id:
            print("   ⚠️  No vehicle ID provided, skipping test")
            return False
            
        success, response = self.run_test(
            f"Unassign Driver from Vehicle ({vehicle_id[:8]}...)",
            "POST",
            f"vehicles/{vehicle_id}/unassign-driver?is_primary=true&reason=End of shift",
            200
        )
        
        if success:
            print(f"   ✓ Driver unassigned successfully")
            return True
        return False

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
    print("🚛 TMS Vehicles/Fleet API Tests - Phase 4")
    print("Testing Vehicle Management with Canadian Compliance")
    print("=" * 60)
    
    tester = TMSVehiclesTester()
    
    # Login
    if not tester.login("aminderpro@gmail.com", "Admin@123!"):
        print("❌ Login failed, aborting tests")
        return 1
    
    # Create test driver for assignment tests
    tester.create_test_driver()
    
    # Test Vehicle CRUD
    print(f"\n🚛 VEHICLE CRUD OPERATIONS")
    print("-" * 40)
    tractor_id = tester.test_create_power_unit()
    trailer_id = tester.test_create_trailer()
    tester.test_list_vehicles()
    tester.test_list_vehicles_with_filters()
    tester.test_vehicles_summary()
    
    # Test vehicle details and updates
    if tractor_id:
        tester.test_get_vehicle_details(tractor_id)
        tester.test_update_vehicle(tractor_id)
    
    # Test driver assignments
    print(f"\n👤 DRIVER ASSIGNMENTS")
    print("-" * 40)
    if tractor_id:
        tester.test_assign_driver(tractor_id)
    
    # Test inspections
    print(f"\n🔍 CVIP INSPECTIONS")
    print("-" * 40)
    if tractor_id:
        tester.test_add_cvip_inspection(tractor_id)
        tester.test_get_vehicle_inspections(tractor_id)
    
    # Test maintenance
    print(f"\n🔧 MAINTENANCE RECORDS")
    print("-" * 40)
    if tractor_id:
        tester.test_add_maintenance_record(tractor_id)
        tester.test_get_vehicle_maintenance(tractor_id)
    
    # Test location tracking
    print(f"\n📍 LOCATION TRACKING")
    print("-" * 40)
    if tractor_id:
        tester.test_update_vehicle_location(tractor_id)
    tester.test_fleet_tracking()
    
    # Test unassign driver
    if tractor_id:
        tester.test_unassign_driver(tractor_id)
    
    # Print results
    success = tester.print_final_results()
    
    print(f"\n🎯 Created vehicles for testing: {len(tester.created_vehicles)}")
    if tester.created_vehicles:
        for vid in tester.created_vehicles:
            print(f"   - Vehicle ID: {vid}")
    
    return 0 if success else 1

if __name__ == "__main__":
    sys.exit(main())