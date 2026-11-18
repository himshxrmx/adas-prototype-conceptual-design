"""
Builds the Week 3 conceptual design document (.docx) from the design analyses and reusable text blocks.
Run from the week folder:  python src/design_analysis.py  then  python src/build_report.py
"""
import json
import sys

import pandas as pd

sys.path.insert(0, "src")
from doclib import Report, section  # noqa: E402

OUT = "Week3_ADAS_Prototype_Conceptual_Design.docx"
GH = "https://github.com/himshxrmx/adas-prototype-conceptual-design"
B = json.load(open("content/base_text.json", encoding="utf-8"))
D = json.load(open("results/design_analysis.json"))
IMG = ["images/fig1_system_architecture.png", "images/fig2_hardware_block_diagram.png", "images/fig3_data_flow.png", "images/fig4_alert_escalation.png"]


def fix(blocks, repl):
    def f(x):
        if isinstance(x, str):
            for a, b in repl.items():
                x = x.replace(a, b)
            return x
        return [f(i) for i in x] if isinstance(x, list) else x
    return [f(b) for b in blocks]


B = fix(B, {"Figure 3 shows how data flows": "The data-flow diagram below shows how data flows",
            "Figure 4 shows the escalation logic": "The escalation diagram below shows the logic",
            "Table 9 shows the worst-case": "The table below shows the worst-case",
            "Table 12 traces a concrete example": "The table below traces a concrete example",
            "TTC below the 2.5 s threshold": "TTC below the 2.4 s threshold", "TTC below about 2.5 s": "TTC below about 2.4 s"})
cam = pd.DataFrame(D["camera_ranges"]); fcw = pd.DataFrame(D["fcw"]["table"]); dz = pd.DataFrame(D["drowsiness"]["table"])
F = D["fcw"]; T = F["chosen_threshold_s"]; ft = fcw[fcw.threshold_s == T].iloc[0]
req = D["camera_required_range_m"]; we = D["camera_worked_example"]; pw = D["power"]; cp = D["compute"]
chosen = cam[(cam.camera.str.startswith("3 MP")) & (cam.strategy.str.startswith("dual"))].iloc[0]
plain = cam[(cam.camera.str.startswith("3 MP")) & (cam.strategy.str.startswith("full"))].iloc[0]
g = lambda cond, det: dz[(dz.condition == cond) & (dz.detector == det)].iloc[0]  # noqa: E731
P12, MS10, MS15 = "PERCLOS > 12% over 60 s", "microsleep: eyes closed > 1.0 s", "microsleep: eyes closed > 1.5 s"
sev_drop = 100 * (1 - ft.severe_crash_pct / F["baseline_severe_crash_pct"])

R = Report()
R.title_page("Conceptual Design of an AI-Powered Driver Assistance System Prototype",
             "Saarthi Copilot v1: architecture, components, algorithms, and the analyses behind each design number",
             ["Week 3 · Automotive AI Innovation Internship (YuvaIntern)", "Author: Him Sharma, B.Tech CSE, ABES Engineering College",
              "November 2026", f"Analysis code, results and figures: {GH}"])

# ------------------------------------------------------------------ 1
R.h1("1. Executive Summary")
R.p("This document presents the conceptual design of Saarthi Copilot v1, a windscreen-mounted, warning-only driver assistance system for Indian "
    "roads. It warns about drowsiness, distraction, forward collision risk, short headway, lane departure and overspeeding, and flags vehicle faults "
    "from the OBD-II port. It turns the Week 1 product concept into a buildable design and applies the Week 2 finding that a camera-first system "
    "should be able to grow into camera-radar fusion.")
R.p("A design is only as good as the reasoning behind its numbers, so every key parameter in this document is derived rather than assumed. "
    "Four original analyses, all published with code, drive the main decisions:")
R.bullets([
    ("Camera choice from pixel geometry:", f"to warn 2.4 s before a stopped car at 100 km/h the system must detect it at {req['highway 100 km/h, stopped car']:.0f} m. "
     f"A 3 MP, 60° camera whose full frame is shrunk to the usual 640-pixel network input sees a car reliably only to {plain['car (1.7 m wide)']:.0f} m. Adding a native-resolution "
     f"centre crop raises this to {chosen['car (1.7 m wide)']:.0f} m for cars and {chosen['two-wheeler (0.7 m)']:.0f} m for two-wheelers, so the design uses a dual-scale detector."),
    ("Collision-warning threshold from a Monte Carlo study:", f"in {F['encounters']:,} simulated lead-vehicle-braking encounters with a distracted driver, a warning at "
     f"TTC {T} s cut severe crashes (impact above 30 km/h) from {F['baseline_severe_crash_pct']:.1f}% to {ft.severe_crash_pct:.1f}% of encounters ({sev_drop:.0f}% fewer) and mean impact "
     f"speed from {F['baseline_mean_impact_kmh']:.1f} to {ft.mean_impact_kmh:.1f} km/h, while staying at {ft.nuisance_alerts_per_hour:.2f} nuisance alerts per hour, inside the limit of one."),
    ("Drowsiness thresholds from simulated eye signals:", f"glances down at the dashboard look like closed eyes and caused {g('IR camera, normal', MS10).false_alarms_per_hour:.1f} false "
     f"microsleep alarms per hour. Gating eye closure with head pose cuts this to {g('normal + head-pose gating', MS10).false_alarms_per_hour:.1f}, and PERCLOS above 12% over "
     f"60 s detects {g('normal + head-pose gating', P12).recall_pct:.0f}% of drowsy drivers at {g('normal + head-pose gating', P12).false_alarms_per_hour:.2f} false alarms per hour."),
    ("Compute, power and heat:", f"the five neural networks need about {cp['production SoC (8 TOPS INT8)']['required_gops']:,.0f} GOPS, {cp['production SoC (8 TOPS INT8)']['load_pct']:.0f}% of an 8 TOPS "
     f"automotive SoC at a realistic 30% utilisation. The production unit draws {pw['typical_w']} W typical; at a 50 °C cabin its case reaches about {pw['case_temp_typical_at_50c_cabin']:.0f} °C, "
     "which sets the thermal design and a throttling policy."),
])
R.p("A failure modes and effects analysis (FMEA) of twelve failure modes ranks driver over-reliance, missed drowsiness behind sunglasses and missed "
    "two-wheelers at night as the top risks, each with a specific mitigation. The production bill of materials stays at about ₹7,500 per unit.")

# ------------------------------------------------------------------ 2
R.emit(section(B, "2. Introduction"), drop={"2.4 Scope and Assumptions"})
R.h2("2.4 Deriving the Quantitative Requirements")
R.p("The non-functional targets above follow from the physics of a warning. A warning only helps if it leaves the driver enough time to react and brake. "
    f"With a warning at TTC {T} s and 0.3 s needed to confirm a track, the forward camera must detect a hazard at distance d = v × ({T} + 0.3):")
R.table(["Situation", "Closing speed", "Required detection range", "Notes"], [
    ["Urban, pedestrian stepping out", "50 km/h (13.9 m/s)", f"{req['urban 50 km/h, pedestrian']:.1f} m", "Pedestrian is 0.5 m wide: the hardest small target"],
    ["Highway, stopped car or truck", "80 km/h (22.2 m/s)", f"{req['highway 80 km/h, stopped car']:.1f} m", "Typical Indian national highway"],
    ["Expressway, stopped car", "100 km/h (27.8 m/s)", f"{req['highway 100 km/h, stopped car']:.1f} m", "Sets the long-range requirement"],
], caption="Detection range needed for a timely warning", widths=[4.4, 3.3, 3.4, 5.4])
R.p("Latency matters in the same units. At 80 km/h every 100 ms of delay costs 2.2 m of stopping distance; against a 2.4 s warning, the 90 ms latency "
    "budget in Section 6.4 uses less than 4% of the time available. After a warning, a driver who reacts in 0.9 s and brakes at 6 m/s² from 80 km/h needs "
    "22.2 × 1.0 + 22.2² / (2 × 6) = 63 m, which is why the design targets warnings at 2.4 s rather than the 1.5 s at which a crash is often already unavoidable.")
R.emit(section(B, "2.4 Scope and Assumptions"), rename={"2.4 Scope and Assumptions": "2.5 Scope and Assumptions"})

# ------------------------------------------------------------------ 3-4
R.emit(section(B, "3. Research: Existing Driver Assistance Systems and the Role of AI"))
R.emit(section(B, "4. System Overview"), images=IMG)

# ------------------------------------------------------------------ 5 hardware
R.emit(section(B, "5. Hardware Design"), images=IMG, drop={"5.3 Prototype Versus Production Hardware", "5.4 Power and Thermal Design"})
R.h2("5.3 Camera Selection from Pixel Geometry")
R.p(f"A detector finds an object reliably only if it covers enough pixels in the image the network actually sees. I used a working limit of about "
    "20 pixels across the object, a common small-object limit for single-stage detectors. For a camera with horizontal field of view θ and N pixels "
    "across, each pixel covers θ/N, so an object of width w is reliably detectable out to d = w / (20 × θ/N), with θ in radians.")
R.p(f"Worked example for the chosen 3 MP sensor (2,048 pixels across, 60°): one pixel covers {we['ifov_deg_per_px_native']}°. A car 1.7 m wide at 100 m spans "
    f"{we['car_100m_native_px']} native pixels, comfortably detectable. But most detectors run on a 640-pixel-wide input; shrunk to 640 pixels the same car spans "
    f"only {we['car_100m_at_640_px']} pixels and is likely to be missed. A two-wheeler 0.7 m wide at 60 m spans {we['two_wheeler_60m_native_px']} native pixels.")
rows = [[r.camera, "640 resize" if r.strategy.startswith("full") else "dual-scale", f"{r['car (1.7 m wide)']:.0f}", f"{r['two-wheeler (0.7 m)']:.0f}",
         f"{r['pedestrian (0.5 m)']:.0f}", f"{r['cow, head-on (0.6 m)']:.0f}"] for _, r in cam.iterrows()]
R.table(["Camera", "Network input", "Car (m)", "Two-wheeler (m)", "Pedestrian (m)", "Cow, head-on (m)"], rows,
        caption="Reliable detection range by camera and input strategy (object at least 20 pixels wide)", widths=[4.6, 2.4, 1.8, 2.5, 2.4, 2.6], font=9)
R.figure("figures/fig5_camera_range.png", "Detection range for each camera option, against the ranges required for a timely warning")
R.p(f"Three conclusions follow. First, shrinking the full frame to 640 pixels limits every camera to about {plain['car (1.7 m wide)']:.0f} m for cars, short of the "
    f"{req['highway 100 km/h, stopped car']:.0f} m needed at 100 km/h, so a second, native-resolution centre crop is essential. Second, a wide 100–120° lens is good for "
    "nearby cut-ins but halves long range. Third, the 3 MP, 60° camera with a dual-scale detector (full frame at 640 pixels for near objects, plus a 1280 × 384 "
    f"native crop around the horizon) reaches {chosen['car (1.7 m wide)']:.0f} m for cars, {chosen['two-wheeler (0.7 m)']:.0f} m for two-wheelers and {chosen['pedestrian (0.5 m)']:.0f} m "
    f"for pedestrians, meeting every requirement in Section 2.4 at a sensor cost of about ₹900. An 8 MP sensor would reach further but costs more, needs more "
    "bandwidth and gives no benefit at the speeds of Indian roads, so it is kept for v2.")

R.h2("5.4 Compute Sizing")
rows = [[c["model"], f"{c['gflops_per_inference']:.1f}", str(c["fps"]), f"{c['gops_per_s']:.0f}", c["source"]] for c in D["compute_table"]]
need = cp["production SoC (8 TOPS INT8)"]["required_gops"]
rows.append(["Total", "", "", f"{need:.0f}", ""])
R.table(["Network", "GFLOPs per run", "Runs per second", "GOPS needed", "Source of size"], rows, caption="Compute needed by the perception and driver-monitoring networks", widths=[6.0, 2.2, 2.2, 2.2, 4.0], font=9)
R.p(f"Counting each multiply-accumulate as two operations, the networks need about {need:,.0f} giga-operations per second (GOPS). Neural accelerators rarely "
    "sustain their peak rating, so I assumed 30% utilisation. An 8 TOPS automotive SoC then gives about 2,400 effective GOPS, a load of "
    f"{cp['production SoC (8 TOPS INT8)']['load_pct']:.0f}%, which leaves room for tracking, the decision engine and future features. The roughly 26 TOPS prototype module "
    f"runs at {cp['prototype module (~26 TOPS INT8)']['load_pct']:.0f}% load, which is why it is used for development: models can be tried at higher resolution before being "
    "squeezed into the production part. The forward detector dominates the budget (about 85%), so it is the first target for pruning and INT8 quantisation (Section 7.7).")
R.emit(section(B, "5.3 Prototype Versus Production Hardware"), rename={"5.3 Prototype Versus Production Hardware": "5.5 Prototype Versus Production Hardware"})
R.emit(section(B, "5.4 Power and Thermal Design"), rename={"5.4 Power and Thermal Design": "5.6 Power and Thermal Design"})
R.h3("Production power and thermal check")
rows = [[n, f"{a:.1f} W", f"{b:.1f} W"] for n, a, b in pw["items"]] + [["Total", f"{pw['typical_w']} W", f"{pw['peak_w']} W"]]
R.table(["Block (production unit)", "Typical", "Peak"], rows, caption="Production power budget", widths=[8.5, 3.0, 3.0])
R.p(f"With an aluminium back plate coupled to the mount, the case-to-cabin thermal resistance is estimated at {pw['rth_c_per_w']} °C/W. In a 50 °C cabin the case "
    f"then settles at 50 + {pw['typical_w']} × {pw['rth_c_per_w']} = {pw['case_temp_typical_at_50c_cabin']} °C in normal use, inside the 85 °C rating. At peak load (LTE upload, loud audio and "
    f"full NPU at once) it would reach {pw['case_temp_peak_at_50c_cabin']} °C, so peaks must never coincide: event uploads are deferred while the case is above 75 °C, "
    f"and driver monitoring drops from 30 to 15 frames per second before forward perception is touched. A car parked in the sun can reach 70 °C inside; starting "
    f"at full load would push the case to about {pw['case_temp_parked_sun_70c_typical']:.0f} °C, so the unit starts in a reduced mode (forward collision warning only) and "
    "enables all features once the case has cooled, typically within a few minutes of the air conditioning running.")

# ------------------------------------------------------------------ 6-7
R.emit(section(B, "6. Software Design"), images=IMG)
R.emit(section(B, "7. AI Algorithms and Justification"))

# ------------------------------------------------------------------ 8 HMI with derived thresholds
R.h1("8. Driver Interaction Design")
R.emit(section(B, "8.1 HMI Principles"))
R.h2("8.2 Alert Levels and Escalation")
R.emit(section(B, "8.2 Alert Levels and Escalation", include_heading=False), images=IMG)
R.p("The thresholds in the table above were starting points. Sections 8.3 and 8.4 replace the two most important ones with values derived from "
    "simulation, and the table below gives the thresholds used in the prototype.")
R.table(["Alert", "Advisory", "Warning", "Critical", "How the value was set"], [
    ["Forward collision", "headway < 1.2 s", f"TTC < {T} s", "TTC < 1.5 s", "Monte Carlo trade-off (Section 8.3); NHTSA test timing 2.0–2.4 s"],
    ["Drowsiness", "PERCLOS > 10% (60 s)", "PERCLOS > 12% (60 s)", "eyes closed > 1.5 s (microsleep)", "Simulated eye signals with head-pose gating (Section 8.4)"],
    ["Distraction", "-", "eyes off road > 2.0 s", "> 3.0 s at > 60 km/h", "Common 2-second glance rule; distance travelled blind: 33 m at 60 km/h in 2 s"],
    ["Lane departure", "-", "wheel within 0.2 s of line, no indicator", "-", "Suppressed below 55 km/h to avoid city nuisance"],
], caption="Prototype alert thresholds", widths=[2.6, 2.8, 3.2, 3.0, 4.9], font=8.5)

R.h2("8.3 Choosing the Forward Collision Warning Threshold")
R.p("A warning that comes too late is useless and one that comes too early is ignored. To choose the threshold, I simulated 20,000 lead-vehicle-braking "
    "encounters, the most common rear-end crash type, with the driver looking away when the lead vehicle brakes. Each encounter draws its values from "
    "typical published ranges:")
R.bullets([
    "Speed 30–90 km/h; following headway lognormal with a median of 1.5 s (0.6–3.5 s).",
    "Lead vehicle brakes at 2–6 m/s² for 1.5–5 s, then holds its speed.",
    "Driver's eyes return to the road 0.5–4.0 s after the lead starts braking; reaction once looking: median 0.75 s. Reaction to a warning (including looking up): median 0.9 s.",
    "Driver brakes at 5–8 m/s² on a dry road (40% less on a wet road), building up over 0.3 s.",
    "The system's TTC estimate has 10% noise per frame, needs three frames below the threshold and adds 0.1 s of latency.",
])
R.p("Nuisance alerts were estimated separately from normal driving: about 20 approaches an hour to slower vehicles, which attentive drivers resolve at a "
    "comfortable minimum TTC with a median of 4.5 s. Any warning in these approaches is a nuisance. A second estimate assumes Indian drivers follow closer "
    "(median 3.8 s) to show how sensitive the choice is.")
rows = [[f"{r.threshold_s} s", f"{r.crash_rate_pct:.1f}%", f"{r.crashes_avoided_pct:.1f}%", f"{r.severe_crash_pct:.1f}%", f"{r.mean_impact_kmh:.1f}", f"{r.nuisance_alerts_per_hour:.2f}", f"{r.nuisance_if_drivers_closer:.2f}"] for r in fcw.itertuples()]
rows.insert(0, ["No warning", f"{F['baseline_crash_rate_pct']:.1f}%", "-", f"{F['baseline_severe_crash_pct']:.1f}%", f"{F['baseline_mean_impact_kmh']:.1f}", "0", "0"])
R.table(["Threshold", "Crash rate", "Crashes avoided", "Severe crashes (> 30 km/h)", "Mean impact (km/h)", "Nuisance / h", "Nuisance / h, closer drivers"], rows,
        caption="Effect of the FCW threshold (20,000 simulated encounters, dry road)", widths=[2.0, 2.0, 2.3, 2.9, 2.3, 2.1, 2.9], font=8.5)
R.figure("figures/fig6_fcw_tradeoff.png", "Crashes avoided against nuisance alerts for each warning threshold")
R.p(f"Every simulated encounter here is a genuine emergency with a distracted driver, so even without a warning {F['baseline_crash_rate_pct']:.0f}% end in a crash; this is not "
    f"the crash rate of normal driving. Earlier warnings help steadily: at {T} s, crashes fall by {ft.crashes_avoided_pct:.1f}%, severe crashes by {sev_drop:.0f}% and mean "
    f"impact speed by {F['baseline_mean_impact_kmh'] - ft.mean_impact_kmh:.1f} km/h, and impact energy grows with the square of speed. But nuisance alerts rise quickly beyond "
    f"2.4 s ({ft.nuisance_alerts_per_hour:.2f} per hour at 2.4 s, {fcw[fcw.threshold_s == 3.0].iloc[0].nuisance_alerts_per_hour:.2f} at 3.0 s). The requirement of fewer than one "
    f"false alert per hour therefore sets the threshold at {T} s, which matches the 2.0–2.4 s alert timing used in the US NCAP forward collision warning test. "
    f"If Indian drivers follow closer, nuisance alerts at 2.4 s rise to {ft.nuisance_if_drivers_closer:.2f} per hour; the pilot will measure real following behaviour and the "
    "threshold can drop to 2.2 s per vehicle type if needed. On a wet road the benefit is smaller, because even a well-timed warning cannot add grip: this "
    "is the strongest argument for adding automatic emergency braking in a later version.")

R.h2("8.4 Choosing the Drowsiness Thresholds")
R.p("Drowsiness is detected from the eyes. PERCLOS, the percentage of time the eyes are more than 80% closed over a window, is the most validated "
    "camera measure of drowsiness. Long single closures (microsleeps) are a separate, more urgent sign. To set both thresholds I simulated eye-state "
    "signals at 30 frames per second for 60 hours of alert driving (60 different drivers, each with their own normal blink length) and 120 ten-minute "
    "drowsy segments in which drowsiness builds up over five minutes. Two real-world complications were modelled: random classifier errors (2% of frames "
    "normally, 6% with sunglasses or harsh sun) and glances down at the dashboard or phone, about four a minute, which a camera can mistake for closed eyes.")
sel = dz[dz.detector.isin(["PERCLOS > 10% over 60 s", P12, "PERCLOS > 15% over 60 s", MS10, MS15])]
rows = [[r.condition, r.detector, f"{r.recall_pct:.1f}%", f"{r.false_alarms_per_hour:.2f}", f"{r.median_detection_s:.0f} s" if r.median_detection_s else "-"] for r in sel.itertuples()]
R.table(["Condition", "Detector", "Drowsy drivers detected", "False alarms / h", "Median time to detect"], rows,
        caption="Drowsiness detector performance on simulated eye signals", widths=[4.3, 4.6, 2.6, 2.3, 2.7], font=8.5)
R.figure("figures/fig7_drowsiness_tradeoff.png", "PERCLOS threshold trade-off with and without head-pose gating", width_cm=12.5)
a, b = g("IR camera, normal", MS10), g("normal + head-pose gating", MS10)
R.p(f"The analysis exposed a design flaw that a generic design would miss. A simple 'eyes closed for more than 1 s' microsleep rule raised {a.false_alarms_per_hour:.1f} false "
    f"alarms an hour, nearly all caused by glances at the dashboard. Adding a head-pose check (a downward head pitch means a glance, not sleep) cuts this to "
    f"{b.false_alarms_per_hour:.1f} an hour, and a 1.5 s rule cuts it to {g('normal + head-pose gating', MS15).false_alarms_per_hour:.2f}. With gating, PERCLOS above 12% detects "
    f"{g('normal + head-pose gating', P12).recall_pct:.0f}% of drowsy drivers at {g('normal + head-pose gating', P12).false_alarms_per_hour:.2f} false alarms an hour "
    f"({g('sunglasses + head-pose gating', P12).recall_pct:.0f}% and {g('sunglasses + head-pose gating', P12).false_alarms_per_hour:.2f} with sunglasses), which meets the 90% prototype "
    f"target. The prototype therefore uses PERCLOS above 10% for a soft advisory (high recall, cheap to be wrong), above 12% for a warning, and a gated 1.5 s "
    "closure for the critical microsleep alarm. The cost is time: PERCLOS needs several minutes of rising drowsiness to trigger, so lane weaving and "
    "yawning are kept as supporting cues.")
R.emit(section(B, "8.3 Suppression and Personalisation Rules"), rename={"8.3 Suppression and Personalisation Rules": "8.5 Suppression and Personalisation Rules"})

# ------------------------------------------------------------------ 9-11
R.emit(section(B, "9. End-to-End Workflow: Data Acquisition, Processing and Response"))
R.emit(section(B, "10. Safety, Security and Privacy"))
R.h2("10.1 Failure Modes and Effects Analysis")
R.p("Each failure mode is scored for severity (S), occurrence (O) and detectability (D) from 1 to 10; the risk priority number RPN = S × O × D ranks "
    "where design effort goes. Scores after mitigation show the expected effect of the design measures in this document.")
fmea = [
    ("Driver over-relies on the system (thinks it will brake)", 8, 4, 7, "Clear 'warning only' onboarding; no automatic actions; engagement tracked", 8, 3, 5),
    ("Drowsiness missed behind IR-blocking sunglasses", 8, 5, 5, "940 nm IR passes most sunglasses; head-nod and lane-weave cues; tell driver when DMS is unavailable", 8, 3, 3),
    ("Two-wheeler missed at night", 9, 4, 5, "HDR sensor; night-heavy training data; dual-scale detector; optional radar for fleets", 9, 3, 4),
    ("Camera calibration shifts after windscreen replacement", 7, 4, 6, "Online calibration from the lane vanishing point; service check procedure", 7, 4, 3),
    ("Thermal throttling in summer causes dropped frames", 7, 5, 4, "Back plate; deferred uploads above 75 °C; DMS throttled first (Section 5.6)", 7, 3, 4),
    ("Dashboard glance misread as microsleep", 4, 7, 4, "Head-pose gating; 1.5 s critical rule (Section 8.4)", 4, 2, 4),
    ("Wrong speed limit read (truck-specific limits)", 4, 5, 5, "Fuse sign recognition with maps; vehicle-class profile", 4, 3, 5),
    ("Alert not heard in a noisy truck cab", 6, 4, 4, "3 W speaker; LED bar; optional seat vibration", 6, 2, 4),
    ("False forward collision alerts in stop-and-go traffic", 5, 6, 3, "Suppressed below 10 km/h; three-frame persistence; threshold from Section 8.3", 5, 3, 3),
    ("Malicious software update", 9, 2, 5, "Secure boot; signed OTA updates (UN R155/R156)", 9, 1, 3),
    ("OBD queries disturb the vehicle CAN bus", 8, 2, 4, "Read-only design; certified transceiver; rate-limited queries", 8, 1, 4),
    ("Power cut corrupts the event log", 3, 4, 3, "Supercapacitor hold-up; journaling file system", 3, 2, 3),
]
rows = []
for name, s, o, d, act, s2, o2, d2 in sorted(fmea, key=lambda x: -x[1] * x[2] * x[3]):
    rows.append([name, str(s), str(o), str(d), str(s * o * d), act, str(s2 * o2 * d2)])
R.table(["Failure mode", "S", "O", "D", "RPN", "Mitigation in this design", "RPN after"], rows, caption="FMEA of Saarthi Copilot v1, sorted by risk", widths=[4.3, 0.8, 0.8, 0.8, 1.2, 6.6, 1.5], font=8)
R.p("Over-reliance tops the list because it is the one risk the hardware cannot fix: a driver who believes the device will brake may take more risks. "
    "That is why v1 stays warning-only and why onboarding and messaging are treated as safety features, not marketing.")
R.emit(section(B, "11. Key Design Trade-offs"))

# ------------------------------------------------------------------ 12 limitations
R.emit(section(B, "12. Potential Limitations"))
R.bullets([
    ("Wet roads:", f"the warning cannot add grip. In the simulation, crashes with a warning at {T} s were {ft.crash_rate_wet_pct:.1f}% on wet roads against {ft.crash_rate_pct:.1f}% on dry ones."),
    ("Slow drowsiness detection:", f"PERCLOS takes a median of about {g('normal + head-pose gating', P12).median_detection_s / 60:.0f} minutes from the start of a drowsy segment to trigger, so a driver "
     "who falls asleep suddenly is caught only by the microsleep rule."),
    ("Analysis assumptions:", "the Monte Carlo and eye-signal studies use typical published ranges for reaction times, braking and blinking, not Indian measurements; "
     "the pilot must re-fit them and re-run the threshold choice."),
])

# ------------------------------------------------------------------ 13-15
R.emit(section(B, "13. Future Scalability"))
R.emit(section(B, "14. Prototype Build and Validation Plan"))
R.h1("15. Conclusion")
R.p("Saarthi Copilot v1 is a practical, affordable first step: a warning-only, camera-first device that can be built for about ₹7,500 and installed in "
    "any car or truck. What makes the design credible is that its key numbers are derived and checked rather than chosen: the camera and dual-scale "
    f"detector from the detection range needed at 100 km/h; the {T} s collision-warning threshold from a 20,000-encounter Monte Carlo trade-off between "
    "crashes avoided and nuisance alerts; the drowsiness thresholds and the head-pose gate from simulated eye signals; the processor from a compute budget; "
    "and the thermal policy from a power budget.")
R.p(f"The analyses also show the limits of a warning-only device. A well-timed warning cut severe crashes by about {sev_drop:.0f}% in the simulated emergencies, "
    "but it cannot help on a wet road or when the driver does not respond. Those limits point directly to the roadmap: radar for fleets, then automatic "
    "emergency braking in v2, built on the same architecture and the fusion approach studied in Week 2. The next step is the bench prototype and a "
    "shadow-mode pilot, where each simulated assumption will be replaced with Indian road data.")

refs = section(B, "References")
R.emit(refs)
for e in ["[R1]  NHTSA (2013, updated). Forward Collision Warning System Confirmation Test, New Car Assessment Program (alert timing criteria of 2.0–2.4 s TTC).",
          "[R2]  Cicchino, J. B. (2017). Effectiveness of forward collision warning and autonomous emergency braking systems in reducing front-to-rear crash rates. Accident Analysis & Prevention, 99, 142–152.",
          "[R3]  Dinges, D. F. and Grace, R. (1998). PERCLOS: A valid psychophysiological measure of alertness as assessed by psychomotor vigilance. FHWA/NHTSA TechBrief.",
          "[R4]  Green, M. (2000). 'How long does it take to stop?' Methodological analysis of driver perception-brake times. Transportation Human Factors, 2(3), 195–216.",
          "[R5]  van der Horst, R. and Hogema, J. (1993). Time-to-collision and collision avoidance systems. ICTCT Workshop, Salzburg.",
          "[R6]  Ultralytics (2023). YOLOv8 model documentation: model sizes and FLOPs at 640-pixel input.",
          f"[R7]  Sharma, H. (2026). Saarthi Copilot v1 design analyses: code and results. {GH}"]:
    R.p(e)
R.emit(section(B, "Appendix A: Indicative Production Bill of Materials"))
R.h1("Appendix B: Requirements Traceability")
R.table(["Requirement", "Design element", "Evidence in this document", "Verification"], [
    ["FR3 forward collision warning", "Dual-scale detector; TTC tracker; warning at 2.4 s", f"Detection {chosen['car (1.7 m wide)']:.0f} m (car) vs {req['highway 100 km/h, stopped car']:.0f} m needed; {sev_drop:.0f}% fewer severe crashes in simulation", "Closed-track soft-target tests"],
    ["FR1 drowsiness", "IR DMS; PERCLOS 10/12%; gated 1.5 s microsleep", f"{g('normal + head-pose gating', P12).recall_pct:.0f}% recall at {g('normal + head-pose gating', P12).false_alarms_per_hour:.2f} false alarms/h (simulated)", "Driving-simulator study with volunteers"],
    ["FR2 distraction", "Gaze and head pose; 2 s rule", "Head-pose module shared with drowsiness gating", "Scripted distraction tasks on track"],
    ["NFR warning latency < 150 ms", "Parallel pipelines; INT8 models", "90 ms budget (Section 6.4); 57% NPU load (Section 5.4)", "Hardware timestamps on the bench"],
    ["NFR false alerts < 1 per hour", "Thresholds from trade-off; suppression rules", f"FCW {ft.nuisance_alerts_per_hour:.2f}/h; drowsiness {g('normal + head-pose gating', P12).false_alarms_per_hour:.2f}/h", "Shadow-mode road tests"],
    ["NFR power < 10 W (production)", "8 TOPS SoC; pulsed IR", f"{pw['typical_w']} W typical (Section 5.6)", "Power analyser on the bench"],
    ["NFR −20 to +85 °C", "Back plate; throttling policy; reduced start mode", f"Case {pw['case_temp_typical_at_50c_cabin']:.0f} °C at 50 °C cabin", "Climatic chamber tests"],
    ["NFR BOM ≤ ₹7,500", "Production SoC and camera choices", "Appendix A", "Supplier quotes at 10,000 units"],
], caption="Requirements, design elements and evidence", widths=[3.4, 4.0, 5.3, 3.8], font=8.5)
R.emit(section(B, "Appendix C: Glossary"))
R.h1("Appendix D: How to Reproduce the Analyses")
R.code("pip install numpy pandas matplotlib python-docx\npython src/design_analysis.py   # camera, FCW, drowsiness, compute, power (about 2 minutes)\npython src/build_report.py      # rebuilds this document")
print("words:", R.save(OUT), "figures:", R.fig_n, "tables:", R.tab_n)
