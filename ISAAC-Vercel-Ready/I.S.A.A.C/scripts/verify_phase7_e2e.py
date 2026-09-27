"""
End-to-end verification script for ISAAC Phase 7:
Dashboard Repair History + Maintenance Cost Analytics.
"""

import json
import urllib.request
import urllib.error
from datetime import datetime

BASE_URL = "http://localhost:8000/api"

def make_req(path, method="GET", data=None, token=None):
    url = f"{BASE_URL}{path}"
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    body = json.dumps(data).encode("utf-8") if data else None
    req = urllib.request.Request(url, data=body, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req) as resp:
            return resp.status, json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8")
        try:
            return e.code, json.loads(body)
        except Exception:
            return e.code, body

def main():
    print("==================================================")
    print("ISAAC PHASE 7: E2E VERIFICATION TEST")
    print("==================================================")

    # 1. Login as Anu Sharma (Maintenance Lead)
    status, token_data = make_req("/auth/login", method="POST", data={
        "username": "anu_sharma",
        "password": "Password123!"
    })
    assert status == 200, f"Login failed: {status} {token_data}"
    token = token_data["access_token"]
    user = token_data["user"]
    print(f"1. Authenticated as: {user['full_name']} ({user['role']})")

    # 2. Check initial KPIs and cost analytics
    status, summary = make_req("/maintenance/summary")
    assert status == 200
    print(f"2. Initial Maintenance Summary KPIs:")
    print(f"   - Repaired Machines: {summary['completed_count']}")
    print(f"   - Active Repairs: {summary['active_repairs_count']}")
    print(f"   - Pending Maintenance: {summary['pending_count']}")
    print(f"   - Total Repair Cost: INR {summary['total_maintenance_cost']}")

    status, cost_analytics = make_req("/maintenance/cost-analytics")
    assert status == 200
    print(f"3. Cost Analytics Breakdown:")
    print(f"   - Total Repairs: {cost_analytics['total_repairs']}")
    print(f"   - Labour: INR {cost_analytics['total_labour_cost']}")
    print(f"   - Parts: INR {cost_analytics['total_parts_cost']}")
    print(f"   - Other: INR {cost_analytics['total_other_cost']}")
    print(f"   - Total: INR {cost_analytics['total_maintenance_cost']}")

    # 4. Create a fresh real work order for machine M14860
    target_machine = "M14860"
    status, create_res = make_req("/maintenance/requests", method="POST", data={
        "machine_id": target_machine,
        "issue": "Spindle micro-vibration & thermal dissipation warning",
        "priority": "HIGH",
        "recommendation": "Inspect and replace worn high-speed ceramic bearing cartridge",
        "requested_by": "Dhananjay Sharma (Reliability Engineer)"
    }, token=token)
    assert status == 201 or status == 200, f"Create work order failed: {status} {create_res}"
    req_id = create_res["request_id"]
    print(f"4. Created Work Order: {req_id} on Machine {target_machine}")

    # 5. Assign technician Ramesh Kumar (TECH-101)
    status, assign_res = make_req(f"/maintenance/requests/{req_id}/assign-technician", method="POST", data={
        "technician_id": "TECH-101",
        "assigned_by": "Anu Sharma (Maintenance Lead)",
        "notes": "Urgent spindle replacement dispatched"
    }, token=token)
    assert status == 200, f"Assign failed: {status} {assign_res}"
    print(f"5. Assigned Technician: Ramesh Kumar (TECH-101) by Anu Sharma")

    # 6. Technician Arrived
    status, arr_res = make_req(f"/maintenance/requests/{req_id}/technician-arrived", method="POST", data={
        "performed_by": "Ramesh Kumar (TECH-101)",
        "notes": "On-site at Spindle Bay 1"
    }, token=token)
    assert status == 200, f"Arrived failed: {status} {arr_res}"
    print(f"6. Marked Technician Arrived (Status: {arr_res.get('new_status')})")

    # 7. Start Inspection
    status, insp_res = make_req(f"/maintenance/requests/{req_id}/start-inspection", method="POST", data={
        "performed_by": "Ramesh Kumar (TECH-101)",
        "notes": "Visual and vibration probe diagnostic inspection"
    }, token=token)
    assert status == 200, f"Start inspection failed: {status} {insp_res}"
    print(f"7. Started Inspection (Status: {insp_res.get('new_status')})")

    # 8. Start Repair
    status, rep_res = make_req(f"/maintenance/requests/{req_id}/start-repair", method="POST", data={
        "performed_by": "Ramesh Kumar (TECH-101)",
        "diagnosis": "Inner bearing race spalling causing localized heat buildup",
        "notes": "Dismantling spindle housing"
    }, token=token)
    assert status == 200, f"Start repair failed: {status} {rep_res}"
    print(f"8. Started Repair (Status: {rep_res.get('new_status')})")

    # 9. Complete Repair & Record Real Costs
    labour_cost = 1800.00
    parts_cost = 3200.00
    other_cost = 600.00
    expected_total = labour_cost + parts_cost + other_cost

    status, comp_res = make_req(f"/maintenance/requests/{req_id}/complete-repair", method="POST", data={
        "performed_by": "Ramesh Kumar (TECH-101)",
        "diagnosis": "Inner bearing race spalling confirmed",
        "work_performed": "Replaced high-speed spindle bearing, re-greased and dynamic balanced to 0.02 mm/s",
        "root_cause": "Lubrication starvation at 2800 RPM duty cycle",
        "parts_used": "SKF 7014 CD/P4A ceramic angular contact bearing, Klüber Isoflex NBU 15 grease",
        "labour_cost": labour_cost,
        "parts_cost": parts_cost,
        "other_cost": other_cost,
        "completion_notes": "Spindle tested at 3000 RPM idle; vibration within nominal tolerances"
    }, token=token)
    assert status == 200, f"Complete repair failed: {status} {comp_res}"
    print(f"9. Completed Repair (Status: {comp_res.get('new_status')})")

    # 10. Close Maintenance & Sign Off by Anu Sharma
    status, close_res = make_req(f"/maintenance/requests/{req_id}/close", method="POST", data={
        "performed_by": "Anu Sharma (Maintenance Lead)",
        "closure_notes": "Repair verified and approved; machine restored to OPERATIONAL.",
        "resolve_linked_alerts": True
    }, token=token)
    assert status == 200, f"Close failed: {status} {close_res}"
    print(f"10. Closed Maintenance (Status: {close_res.get('new_status')})")

    # 11. Fetch Recently Repaired Machines from API
    status, recent_repairs = make_req("/maintenance/recent-repairs?limit=5")
    assert status == 200, f"Fetch recent repairs failed: {status}"
    assert len(recent_repairs) > 0, "Expected at least 1 recent repair"

    newest = recent_repairs[0]
    print("\n==================================================")
    print("VERIFYING 10 CORE OPERATIONAL QUESTIONS:")
    print("==================================================")
    print(f"1. Kaunsi machine repair hui? -> {newest['machine_id']} (Grade: {newest['machine_type']})")
    assert newest["machine_id"] == target_machine

    print(f"2. Kya problem thi? -> Issue: {newest['issue']} | Dx: {newest['diagnosis']}")
    assert "spalling" in (newest["diagnosis"] or "").lower() or "bearing" in (newest["issue"] or "").lower()

    tech_name = newest['technician'].get('technician_name') or newest['technician'].get('name')
    print(f"3. Kis technician ne repair ki? -> {tech_name} (ID: {newest['technician_id']}, Spec: {newest['technician']['specialization']})")
    assert tech_name == "Ramesh Kumar"

    print(f"4. Technician ko kisne assign/bulaya? -> {newest['assigned_by']}")
    assert "Anu Sharma" in newest["assigned_by"]

    print(f"5. Kab repair hui? -> Completed At: {newest['repair_completed_at']} | Closed At: {newest['maintenance_closed_at']}")
    assert newest["repair_completed_at"] is not None

    print(f"6. Repair kitni der chali? -> Duration: {newest['duration_minutes']} min (Started: {newest['repair_started_at']}, Completed: {newest['repair_completed_at']})")

    print(f"7. Labour cost kitna tha? -> INR {newest['labour_cost']}")
    assert newest["labour_cost"] == labour_cost

    print(f"8. Parts cost kitna tha? -> INR {newest['parts_cost']} (Parts: {newest['parts_used']})")
    assert newest["parts_cost"] == parts_cost

    print(f"9. Total repair charge kitna aaya? -> INR {newest['total_cost']}")
    assert newest["total_cost"] == expected_total

    print(f"10. Current maintenance status kya hai? -> {newest['status']}")
    assert newest["status"] == "CLOSED"

    # 12. Cross-machine check: query machine L47181
    status, l_history = make_req("/maintenance/history?machine_id=L47181")
    assert status == 200
    for h in l_history:
        assert h["machine_id"] == "L47181", f"Cross-machine leak! Expected L47181 but got {h['machine_id']}"
    print("\n11. Machine Isolation Confirmed: No data cross-mixing between M14860 and L47181.")

    # 13. Persistence Check
    status, recheck = make_req("/maintenance/recent-repairs?limit=5")
    assert status == 200
    assert recheck[0]["request_id"] == newest["request_id"]
    print("12. Persistence Confirmed: Repair record persists across independent requests.")

    print("\n==================================================")
    print("ALL PHASE 7 VERIFICATION CHECKS PASSED SUCCESSFULLY!")
    print("==================================================")

if __name__ == "__main__":
    main()
