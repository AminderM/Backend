"""
Quick test to verify tracking events are being stored correctly
"""

import requests
import json

# Test configuration
base_url = "https://accessorial-charges.preview.emergentagent.com"
headers = {'Content-Type': 'application/json'}

def login():
    """Login and get token"""
    response = requests.post(f"{base_url}/api/auth/login", 
                           json={"email": "aminderpro@gmail.com", "password": "Admin@123!"})
    if response.status_code == 200:
        token = response.json().get('access_token')
        headers['Authorization'] = f'Bearer {token}'
        print(f"✅ Logged in successfully")
        return True
    return False

def test_tracking_events():
    """Test if tracking events are being created"""
    print("\n🔍 Testing tracking events...")
    
    # Get a recent shipment
    response = requests.get(f"{base_url}/api/operations/shipments", headers=headers)
    if response.status_code != 200:
        print("❌ Failed to get shipments")
        return
    
    shipments = response.json()
    if not shipments:
        print("❌ No shipments found")
        return
    
    shipment_id = shipments[0]['id']
    shipment_number = shipments[0]['shipment_number']
    print(f"Testing shipment: {shipment_number} ({shipment_id})")
    
    # Get shipment details with status history
    response = requests.get(f"{base_url}/api/operations/shipments/{shipment_id}", headers=headers)
    if response.status_code == 200:
        shipment_details = response.json()
        status_history = shipment_details.get('status_history', [])
        print(f"Status history entries: {len(status_history)}")
        for entry in status_history[:3]:
            print(f"  - {entry.get('new_status')}: {entry.get('notes', 'No notes')}")
    
    # Check tracking events
    response = requests.get(f"{base_url}/api/operations/shipments/{shipment_id}/tracking", headers=headers)
    if response.status_code == 200:
        events = response.json()
        print(f"Tracking events: {len(events)}")
        for event in events[:3]:
            print(f"  - {event.get('event_type')}: {event.get('message', 'No message')}")
    
    # Try to add a tracking event manually
    response = requests.post(f"{base_url}/api/operations/shipments/{shipment_id}/tracking",
                           headers=headers,
                           params={
                               'event_type': 'check_call',
                               'message': 'Test tracking event',
                               'location_name': 'Toronto, ON'
                           })
    
    if response.status_code == 200:
        print("✅ Successfully added tracking event")
        
        # Check if it appears now
        response = requests.get(f"{base_url}/api/operations/shipments/{shipment_id}/tracking", headers=headers)
        if response.status_code == 200:
            events = response.json()
            print(f"Tracking events after adding: {len(events)}")
    else:
        print(f"❌ Failed to add tracking event: {response.status_code}")
        print(response.text)

if __name__ == "__main__":
    if login():
        test_tracking_events()