"""
Live end-to-end verification script for Phase 6:
Maintenance Technician + Repair Workflow + Cost Tracking on Machine M14860.
Executes against the running ISAAC backend (http://127.0.0.1:8000).
"""

import sys
import time
import requests

BASE_URL = "http://127.0.0.1:8000/api"

def log(step: str, detail: str):
    print(f"\n[PHASE 6 STEP: {step}]")
    print(f"  -> {detail}")

def main():
    print("================================================================================")
    print("      ISAAC PHASE 6 LIVE WORKFLOW VERIFICATION ON MACHINE M14860")
    print("================================================================================")

    # 0. Check Health
    health = requests.get("http://127.0.0.1:8000/health", timeout=5).json()
    assert health["status"] in ["ok", "healthy"]
    log("0. Health Check", f"ISAAC Backend is healthy: DB status = {health['database']['status']}")

    # 1. Register Technician
    tech_payload = {
        "technician_id": "TECH-101",
        "technician_name": "Ramesh Kumar",
        "specialization": "Mechanical",
        "company": "Precision Machine Works",
        "phone": "+91-9876543210",
        "email": "ramesh.kumar@precisionworks.in",
        "experience_years": 8,
        "certification": "ISO 18436 Vibration Cat II",
        "status": "AVAILABLE",
    }
    t_res = requests.post(f"{BASE_URL}/technicians", json=tech_payload, timeout=5)
    assert t_res.status_code in [200, 201], t_res.text
    tech = t_res.json()
    log("1. Technician Registration", f"Registered: {tech['technician_name']} ({tech['technician_id']}) - {tech['specialization']} - Status: {tech['status']}")

    # 2. Step 1: Create Maintenance Work Order for Machine M14860
    machine_id = "M14860"
    req_payload = {
        "machine_id": machine_id,
        "issue": "High tool wear index and excessive spindle vibration during 5000 RPM milling cycle.",
        "risk": "HIGH",
        "priority": "HIGH",
        "recommendation": "Inspect spindle drive bearings, clean cooling radiator fins, calibrate cutting tool offset.",
        "requested_by": "Dhananjay Sharma (Reliability Engineer)",
        "estimated_cost": 5000.0,
    }
    r_res = requests.post(f"{BASE_URL}/maintenance/requests", json=req_payload, timeout=5)
    assert r_res.status_code == 200, r_res.text
    wo = r_res.json()
    request_id = wo["request_id"]
    log("2. Create Work Order", f"Created Work Order: {request_id} | Status: {wo['status']} | Estimated Cost: Rs. {wo['estimated_cost']}")

    # Check machine status transitioned to MAINTENANCE_REQUIRED
    m_res = requests.get(f"{BASE_URL}/machines/{machine_id}", timeout=5).json()
    log("2b. Asset Status Check", f"Machine {machine_id} status updated to: {m_res['status']}")
    assert m_res["status"] == "MAINTENANCE_REQUIRED"

    # 3. Step 2: Anu Sharma (Maintenance Lead) assigns Technician
    assign_payload = {
        "technician_id": "TECH-101",
        "assigned_by": "Anu Sharma (Maintenance Lead)",
        "priority": "HIGH",
        "notes": "Dispatched Ramesh Kumar (Mechanical) for spindle overhaul and tool inspection.",
    }
    assign_res = requests.post(f"{BASE_URL}/maintenance/requests/{request_id}/assign-technician", json=assign_payload, timeout=5)
    assert assign_res.status_code == 200, assign_res.text
    log("3. Technician Assignment", f"Assigned by Anu Sharma to Ramesh Kumar. Work Order Status: {assign_res.json()['new_status']}")

    # Check technician status is now ASSIGNED
    t_assigned = requests.get(f"{BASE_URL}/technicians/TECH-101", timeout=5).json()
    log("3b. Technician Status Check", f"Technician TECH-101 status: {t_assigned['status']}")
    assert t_assigned["status"] == "ASSIGNED"

    # 4. Step 3: Technician Arrival
    arrive_payload = {
        "performed_by": "Ramesh Kumar",
        "notes": "Arrived on-site at Bay 1 - Spindle Line A with SKF bearing replacement unit.",
    }
    arr_res = requests.post(f"{BASE_URL}/maintenance/requests/{request_id}/technician-arrived", json=arrive_payload, timeout=5)
    assert arr_res.status_code == 200, arr_res.text
    log("4. Technician Arrival", f"Ramesh Kumar logged on-site arrival. New Status: {arr_res.json()['new_status']}")

    # Check technician status is now ON_SITE
    t_onsite = requests.get(f"{BASE_URL}/technicians/TECH-101", timeout=5).json()
    log("4b. Technician Status Check", f"Technician TECH-101 status: {t_onsite['status']}")
    assert t_onsite["status"] == "ON_SITE"

    # 5. Step 4: Physical Inspection
    inspect_payload = {
        "performed_by": "Ramesh Kumar",
        "notes": "Lockout-tagout procedure completed. Disassembled spindle protective shroud. Vibration probes deployed.",
    }
    ins_res = requests.post(f"{BASE_URL}/maintenance/requests/{request_id}/start-inspection", json=inspect_payload, timeout=5)
    assert ins_res.status_code == 200, ins_res.text
    log("5. Start Inspection", f"Inspection commenced by Ramesh Kumar. New Status: {ins_res.json()['new_status']}")

    m_ins = requests.get(f"{BASE_URL}/machines/{machine_id}", timeout=5).json()
    log("5b. Asset Status Check", f"Machine {machine_id} status updated to: {m_ins['status']}")
    assert m_ins["status"] == "INSPECTION_IN_PROGRESS"

    # 6. Step 5: Start Repair
    start_rep_payload = {
        "performed_by": "Ramesh Kumar",
        "diagnosis": "Micro-cracks in bearing cage assembly; carbide tool insert flank wear at 0.45mm.",
        "problem_description": "High tool wear index and excessive vibration under load.",
        "notes": "Commencing bearing replacement and tool calibration.",
    }
    srep_res = requests.post(f"{BASE_URL}/maintenance/requests/{request_id}/start-repair", json=start_rep_payload, timeout=5)
    assert srep_res.status_code == 200, srep_res.text
    log("6. Start Repair", f"Repair started by Ramesh Kumar. New Status: {srep_res.json()['new_status']}")

    time.sleep(0.5)

    # 7. Step 6: Complete Repair with Test Costs: Labour ₹1500 + Parts ₹2500 + Other ₹500 = ₹4500
    complete_payload = {
        "performed_by": "Ramesh Kumar",
        "diagnosis": "Micro-cracks in bearing cage assembly; insert flank wear at 0.45mm.",
        "work_performed": "Installed SKF precision spindle bearing; replaced 2x carbide inserts; calibrated tool offset.",
        "root_cause": "High-torque machining cycle without sufficient coolant flow.",
        "parts_used": "1x SKF Precision Spindle Bearing, 2x Carbide Cutting Inserts, 2L Synthetic Coolant",
        "repair_notes": "Spindle runout tolerance measured at 0.002mm (within OEM specification).",
        "completion_notes": "Assembly rebuilt, tested at 5000 RPM without vibration or heat rise.",
        "labour_cost": 1500.0,
        "parts_cost": 2500.0,
        "other_cost": 500.0,
    }
    comp_res = requests.post(f"{BASE_URL}/maintenance/requests/{request_id}/complete-repair", json=complete_payload, timeout=5)
    assert comp_res.status_code == 200, comp_res.text
    log("7. Complete Repair", f"Repair completed! New Status: {comp_res.json()['new_status']}")

    # Verify work order costs and calculated duration
    wo_comp = requests.get(f"{BASE_URL}/maintenance/requests/{request_id}", timeout=5).json()
    log("7b. Cost & Duration Verification", (
        f"Labour Cost: Rs. {wo_comp['labour_cost']:,.2f} | "
        f"Parts Cost: Rs. {wo_comp['parts_cost']:,.2f} | "
        f"Other Cost: Rs. {wo_comp['other_cost']:,.2f} | "
        f"TOTAL COST: Rs. {wo_comp['total_cost']:,.2f} | "
        f"Calculated Duration: {wo_comp['duration_minutes']} minutes"
    ))
    assert wo_comp["total_cost"] == 4500.0
    assert wo_comp["labour_cost"] == 1500.0
    assert wo_comp["parts_cost"] == 2500.0
    assert wo_comp["other_cost"] == 500.0

    # 8. Step 7: Maintenance Closure by Anu Sharma (Maintenance Lead)
    close_payload = {
        "performed_by": "Anu Sharma (Maintenance Lead)",
        "closure_notes": "Maintenance verified on-site. Spindle dynamics normal. Approved return to production.",
        "resolve_linked_alerts": True,
    }
    close_res = requests.post(f"{BASE_URL}/maintenance/requests/{request_id}/close", json=close_payload, timeout=5)
    assert close_res.status_code == 200, close_res.text
    log("8. Maintenance Closure", f"Work Order {request_id} closed by Anu Sharma. Final Status: {close_res.json()['new_status']}")

    # Verify final closed order
    wo_closed = requests.get(f"{BASE_URL}/maintenance/requests/{request_id}", timeout=5).json()
    assert wo_closed["status"] == "CLOSED"
    assert wo_closed["maintenance_closed_at"] is not None

    # Verify machine restored to OPERATIONAL
    m_restored = requests.get(f"{BASE_URL}/machines/{machine_id}", timeout=5).json()
    log("8b. Final Asset Status", f"Machine {machine_id} restored to: {m_restored['status']}")
    assert m_restored["status"] == "OPERATIONAL"

    # Verify technician freed to AVAILABLE
    t_freed = requests.get(f"{BASE_URL}/technicians/TECH-101", timeout=5).json()
    log("8c. Final Technician Status", f"Technician TECH-101 restored to: {t_freed['status']}")
    assert t_freed["status"] == "AVAILABLE"

    # 9. Verify Dashboard Summary total maintenance cost includes ₹4500
    dash_sum = requests.get(f"{BASE_URL}/maintenance/summary", timeout=5).json()
    log("9. Maintenance Summary Verification", (
        f"Completed Count: {dash_sum['completed_count']} | "
        f"Closed Count: {dash_sum.get('closed_count', 0)} | "
        f"Total Maintenance Cost across fleet: Rs. {dash_sum['total_maintenance_cost']:,.2f}"
    ))
    assert dash_sum["total_maintenance_cost"] >= 4500.0

    print("\n================================================================================")
    print("   SUCCESS! ALL 7 STEPS OF PHASE 6 MAINTENANCE WORKFLOW VERIFIED LIVE ON M14860!")
    print("================================================================================\n")

if __name__ == "__main__":
    main()
