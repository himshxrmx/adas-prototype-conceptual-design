"""
Engineering analyses behind the Saarthi Copilot v1 design (Week 3).

A. Camera geometry: detection range per road-user type for candidate cameras and network input strategies.
B. Forward collision warning (FCW): Monte Carlo of lead-vehicle-braking crashes with a distracted driver, used to
   choose the warning threshold by trading crashes avoided against nuisance alerts in normal driving.
C. Drowsiness: simulated eye-closure signals, PERCLOS and microsleep detectors, threshold choice.
D. Compute budget from published model sizes; E. power and thermal budget.

All human-behaviour and sensor numbers are assumptions taken from typical published ranges; they are listed in
the code and in the report. Outputs: results/design_analysis.json, results/*.csv, figures/*.png
Run: python src/design_analysis.py      (about 1-2 minutes)
"""
import json
import os

import matplotlib
import numpy as np
import pandas as pd

matplotlib.use("Agg")
import matplotlib.pyplot as plt

os.makedirs("results", exist_ok=True); os.makedirs("figures", exist_ok=True)
OUT = {}
G = 9.81

# ===================================================================== A. camera geometry
OBJECTS = {"car (1.7 m wide)": 1.7, "two-wheeler (0.7 m)": 0.7, "pedestrian (0.5 m)": 0.5, "cow, head-on (0.6 m)": 0.6}
PX_RELIABLE = 20          # object width in network-input pixels for reliable detection (small-object limit)
CAMERAS = [("2 MP, 1920 px, 100° HFOV", 1920, 100), ("2 MP, 1920 px, 60° HFOV", 1920, 60), ("3 MP, 2048 px, 60° HFOV", 2048, 60),
           ("8 MP, 3840 px, 120° HFOV", 3840, 120), ("8 MP, 3840 px, 60° HFOV", 3840, 60)]


def det_range(width_m, hfov_deg, px_across):
    ifov = np.radians(hfov_deg) / px_across
    return width_m / (PX_RELIABLE * ifov)


rows = []
for name, w, fov in CAMERAS:
    for strat, eff_px, eff_fov in [("full frame resized to 640 px", 640, fov),
                                   ("dual-scale: full frame at 640 + native 1280 px centre crop", 1280, fov * 1280 / w)]:
        r = dict(camera=name, strategy=strat, centre_crop_fov_deg=round(eff_fov, 1))
        for o, wd in OBJECTS.items():
            r[o] = round(det_range(wd, eff_fov, eff_px), 1)
        rows.append(r)
cam = pd.DataFrame(rows); cam.to_csv("results/camera_ranges.csv", index=False)
req = {"urban 50 km/h, pedestrian": 13.9 * (2.4 + 0.3), "highway 80 km/h, stopped car": 22.2 * (2.4 + 0.3),
       "highway 100 km/h, stopped car": 27.8 * (2.4 + 0.3)}
OUT["camera_required_range_m"] = {k: round(v, 1) for k, v in req.items()}
OUT["camera_ranges"] = rows
# pixels on target for the chosen camera, worked example
ifov_native = np.radians(60) / 2048
OUT["camera_worked_example"] = {"ifov_deg_per_px_native": round(60 / 2048, 4), "car_100m_native_px": round(1.7 / (100 * ifov_native), 1),
                                "car_100m_at_640_px": round(1.7 / (100 * np.radians(60) / 640), 1), "two_wheeler_60m_native_px": round(0.7 / (60 * ifov_native), 1)}

fig, ax = plt.subplots(figsize=(10, 4.3))
labels = [f"{r['camera'].split(',')[0]} {r['camera'].split(',')[2].strip().split()[0]}\n{'640 resize' if r['strategy'].startswith('full') else 'dual-scale'}" for r in rows]
x = np.arange(len(rows)); wbar = 0.2
for i, (o, c) in enumerate(zip(OBJECTS, ["#1f77b4", "#ff7f0e", "#2ca02c", "#8c564b"])):
    ax.bar(x + (i - 1.5) * wbar, cam[o], wbar, label=o, color=c)
for k, v in req.items():
    ax.axhline(v, ls="--", lw=0.8, color="grey"); ax.text(len(rows) - 0.4, v + 1, k, fontsize=7, ha="right", color="grey")
ax.set_xticks(x); ax.set_xticklabels(labels, fontsize=7.5); ax.set_ylabel("reliable detection range (m)")
ax.set_title(f"Detection range from pixel geometry (object ≥ {PX_RELIABLE} px wide in the network input)"); ax.legend(fontsize=7, ncol=4)
ax.grid(axis="y", alpha=0.3); fig.tight_layout(); fig.savefig("figures/fig5_camera_range.png", dpi=160); plt.close(fig)

# ===================================================================== B. FCW threshold Monte Carlo
rng = np.random.default_rng(31)
N = 20000
v0 = rng.uniform(30, 90, N) / 3.6                                    # ego and lead initial speed
hw = np.clip(rng.lognormal(np.log(1.5), 0.35, N), 0.6, 3.5)          # following headway (s)
gap0 = v0 * hw
a_lead = rng.uniform(2.0, 6.0, N)                                    # lead vehicle braking (m/s^2)
b_dur = rng.uniform(1.5, 5.0, N)                                     # how long the lead brakes before holding speed
glance = rng.uniform(0.5, 4.0, N)                                    # remaining eyes-off-road time after the lead brakes
rt_self = rng.lognormal(np.log(0.75), 0.30, N)                       # reaction once the driver looks back
rt_warn = rng.lognormal(np.log(0.90), 0.30, N)                       # reaction to a warning (includes looking up)
a_drv = rng.uniform(5.0, 8.0, N)                                     # driver's braking once reacting (dry road)
ttc_noise = 0.10                                                     # TTC estimate noise from scale-change tracking
SYS_LAT = 0.10                                                       # hazard -> alert latency (Section 6.4 budget)
DTS = 0.01


def simulate(thresh, wet=False):
    """Vectorised kinematics; returns crash flag and impact speed for every encounter."""
    adrv = a_drv * (0.6 if wet else 1.0)
    natural = glance + rt_self
    t = 0.0
    xl, xe = gap0.copy(), np.zeros(N)
    vl, ve = v0.copy(), v0.copy()
    respond = natural.copy()
    warned = np.zeros(N, bool) if thresh is not None else np.ones(N, bool)
    below = np.zeros(N, int)
    crash = np.zeros(N, bool); impact = np.zeros(N)
    frame_every = int(round((1 / 30) / DTS))
    k = 0
    while t < 15.0:
        gap = xl - xe
        hit = (gap <= 0) & ~crash
        impact[hit] = (ve - vl)[hit] * 3.6; crash |= hit
        if thresh is not None and k % frame_every == 0:
            closing = ve - vl
            ttc = np.where(closing > 0.1, gap / np.maximum(closing, 1e-6), np.inf)
            est = ttc * np.exp(rng.normal(0, ttc_noise, N))
            below = np.where(est < thresh, below + 1, 0)
            fire = (below >= 3) & ~warned
            respond = np.where(fire, np.minimum(respond, t + SYS_LAT + rt_warn), respond)
            warned |= fire
        braking = t >= respond
        ramp = np.clip((t - respond) / 0.3, 0, 1)
        ae = np.where(braking, -adrv * ramp, 0.0)
        al = np.where((vl > 0) & (t < b_dur), -a_lead, 0.0)
        vl = np.maximum(0, vl + al * DTS); ve = np.maximum(0, ve + ae * DTS)
        xl += vl * DTS; xe += ve * DTS
        ve = np.where(crash, vl, ve); xe = np.where(crash, xl, xe)
        t += DTS; k += 1
        if ((ve <= 0.01) | crash).all():
            break
    return crash, impact


def nuisance_rate(thresh, events_per_hour=20, n=40000, seed=5, median_tmin=4.5):
    """Normal driving: approaches to slower vehicles where the attentive driver resolves the conflict at a
    comfortable minimum TTC (lognormal, median 4.5 s). Counts warnings per hour that would have fired."""
    r = np.random.default_rng(seed)
    tmin = r.lognormal(np.log(median_tmin), 0.35, n)
    curv = r.uniform(0.5, 2.0, n)
    tt = np.arange(-1.0, 1.0, 1 / 30)
    ttc = tmin[:, None] + curv[:, None] * tt[None, :] ** 2
    est = ttc * np.exp(r.normal(0, ttc_noise, ttc.shape))
    b = est < thresh
    run3 = b[:, 2:] & b[:, 1:-1] & b[:, :-2]
    return float(events_per_hour * run3.any(1).mean())


base_crash, base_imp = simulate(None)
OUT_SEVERE0 = float(100 * (base_crash & (base_imp > 30)).mean())
fcw_rows = []
for T in [1.5, 1.8, 2.0, 2.2, 2.4, 2.6, 2.8, 3.0, 3.5]:
    c, imp = simulate(T)
    cw, _ = simulate(T, wet=True)
    fcw_rows.append(dict(threshold_s=T, crash_rate_pct=round(100 * c.mean(), 2), crashes_avoided_pct=round(100 * (1 - c.mean() / base_crash.mean()), 1),
                         mean_impact_kmh=round(float(imp[c].mean()) if c.any() else 0, 1), crash_rate_wet_pct=round(100 * cw.mean(), 2),
                         nuisance_alerts_per_hour=round(nuisance_rate(T), 2), nuisance_if_drivers_closer=round(nuisance_rate(T, median_tmin=3.8), 2),
                         severe_crash_pct=round(100 * (c & (imp > 30)).mean(), 2)))
cw0, _ = simulate(None, wet=True)
fcw = pd.DataFrame(fcw_rows); fcw.to_csv("results/fcw_threshold.csv", index=False)
OUT["fcw"] = dict(encounters=N, baseline_crash_rate_pct=round(100 * base_crash.mean(), 2), baseline_mean_impact_kmh=round(float(base_imp[base_crash].mean()), 1),
                  baseline_crash_rate_wet_pct=round(100 * cw0.mean(), 2), baseline_severe_crash_pct=round(OUT_SEVERE0, 2), table=fcw_rows)
ok = fcw[fcw.nuisance_alerts_per_hour < 1.0]
best = ok.sort_values("crashes_avoided_pct", ascending=False).iloc[0]
OUT["fcw"]["chosen_threshold_s"] = float(best.threshold_s)

fig, ax1 = plt.subplots(figsize=(8.5, 4))
ax1.plot(fcw.threshold_s, fcw.crashes_avoided_pct, "o-", color="#2ca02c", label="crashes avoided (dry)")
ax1.plot(fcw.threshold_s, 100 * (1 - fcw.crash_rate_wet_pct / (100 * cw0.mean())), "s--", color="#17becf", label="crashes avoided (wet)")
ax1.set_xlabel("FCW threshold: warn when estimated TTC is below (s)"); ax1.set_ylabel("crashes avoided vs no warning (%)")
ax2 = ax1.twinx(); ax2.plot(fcw.threshold_s, fcw.nuisance_alerts_per_hour, "^-", color="#d62728", label="nuisance alerts per hour")
ax2.axhline(1.0, color="#d62728", ls=":", lw=1); ax2.set_ylabel("nuisance alerts per driving hour", color="#d62728")
ax1.axvline(best.threshold_s, color="k", lw=0.8); ax1.text(best.threshold_s + 0.03, 23, f"chosen {best.threshold_s} s", fontsize=8)
h1, l1 = ax1.get_legend_handles_labels(); h2, l2 = ax2.get_legend_handles_labels(); ax1.legend(h1 + h2, l1 + l2, fontsize=8, loc="center right")
ax1.set_title(f"FCW threshold trade-off ({N:,} simulated lead-vehicle-braking encounters, distracted driver)"); ax1.grid(alpha=0.3)
fig.tight_layout(); fig.savefig("figures/fig6_fcw_tradeoff.png", dpi=160); plt.close(fig)

# ===================================================================== C. drowsiness detection
FPS = 30


def eye_signal(minutes, level, r, err, look_down_misread):
    """Frame-level eye state (True = looks closed to the camera) for one driver.
    level = 0 for an alert driver; 0.3-1.0 for a drowsy driver (drowsiness ramps up over the first 5 minutes).
    Alert drivers differ: each has their own typical blink length. Glances down at the dashboard or phone
    (about 4 a minute) are read as 'closed' with probability look_down_misread. Then random classifier errors
    and a 3-frame median filter."""
    n = int(minutes * 60 * FPS)
    closed = np.zeros(n, bool)
    person_blink = r.lognormal(np.log(0.15), 0.25)
    t = 0.0
    while True:
        lv = level * min(1.0, t / 300.0)
        t += r.exponential(60 / (15 + 6 * lv))
        if t * FPS >= n:
            break
        dur = r.lognormal(np.log(person_blink + 0.25 * lv), 0.3 + 0.2 * lv)
        closed[int(t * FPS): int((t + dur) * FPS)] = True
    t = 0.0
    while level > 0:                                   # microsleeps: up to about 1.5 a minute at full drowsiness
        lv_rate = 1.5 * level ** 2
        t += r.exponential(60 / max(lv_rate, 1e-3))
        if t * FPS >= n:
            break
        if r.random() < min(1.0, t / 300.0):
            closed[int(t * FPS): int((t + r.uniform(0.5, 2.0)) * FPS)] = True
    t = 0.0
    while True:                                        # glances down that look like closed eyes
        t += r.exponential(15)
        if t * FPS >= n:
            break
        if r.random() < look_down_misread:
            closed[int(t * FPS): int((t + r.uniform(0.3, 1.5)) * FPS)] = True
    flip = r.random(n) < err
    obs = closed ^ flip
    med = (obs.astype(int) + np.roll(obs, 1) + np.roll(obs, -1)) >= 2
    return med


def perclos(sig, window_s=60):
    w = window_s * FPS
    c = np.concatenate([[0], np.cumsum(sig)])
    return (c[w:] - c[:-w]) / w


r = np.random.default_rng(77)
dz_rows = []
alert_h, drowsy_n = 60, 120
for err, misread, cond in [(0.02, 0.15, "IR camera, normal"), (0.06, 0.35, "sunglasses or harsh sun"),
                          (0.02, 0.02, "normal + head-pose gating"), (0.06, 0.05, "sunglasses + head-pose gating")]:
    alert = np.concatenate([eye_signal(60, 0.0, r, err, misread) for _ in range(alert_h)])     # 60 different alert drivers, 1 h each
    pa = perclos(alert)
    drowsy = [eye_signal(10, r.uniform(0.3, 1.0), r, err, misread) for _ in range(drowsy_n)]
    pdz = [perclos(d) for d in drowsy]

    def longest_closed(sig):
        best, cur = 0, 0
        for v in sig[::3]:                            # sub-sampled scan is enough to find > 1 s closures
            cur = cur + 1 if v else 0; best = max(best, cur)
        return best * 3 / FPS

    for th in [0.08, 0.10, 0.12, 0.15, 0.20, 0.25]:
        above = pa > th
        starts = np.flatnonzero(above[1:] & ~above[:-1]).size + int(above[0])
        fa_h = starts / alert_h
        det = [np.argmax(p > th) / FPS for p in pdz if (p > th).any()]
        dz_rows.append(dict(condition=cond, detector=f"PERCLOS > {int(th * 100)}% over 60 s", recall_pct=round(100 * len(det) / drowsy_n, 1),
                            false_alarms_per_hour=round(fa_h, 2), median_detection_s=round(float(np.median(det)) + 60, 1) if det else None))
    # microsleep detector: eyes closed continuously for more than L seconds
    a_runs = np.diff(np.flatnonzero(np.diff(np.concatenate([[0], alert.astype(int), [0]]))))[::2] / FPS
    for L in (1.0, 1.5):
        fa_ms = (a_runs > L).sum() / alert_h
        det_ms = []
        for d in drowsy:
            edges = np.flatnonzero(np.diff(np.concatenate([[0], d.astype(int), [0]])))
            starts, ends = edges[::2], edges[1::2]
            long = starts[(ends - starts) > L * FPS]
            if len(long):
                det_ms.append(long[0] / FPS + L)
        dz_rows.append(dict(condition=cond, detector=f"microsleep: eyes closed > {L} s", recall_pct=round(100 * len(det_ms) / drowsy_n, 1),
                            false_alarms_per_hour=round(fa_ms, 2), median_detection_s=round(float(np.median(det_ms)), 1) if det_ms else None))
dz = pd.DataFrame(dz_rows); dz.to_csv("results/drowsiness_detection.csv", index=False)
OUT["drowsiness"] = dict(alert_hours=alert_h, drowsy_segments=drowsy_n, table=dz_rows)

fig, ax = plt.subplots(figsize=(7.5, 4))
for cond, mk in [("IR camera, normal", "o-"), ("sunglasses or harsh sun", "s--"), ("normal + head-pose gating", "^-"), ("sunglasses + head-pose gating", "v--")]:
    d = dz[(dz.condition == cond) & dz.detector.str.startswith("PERCLOS")]
    ax.plot(d.false_alarms_per_hour, d.recall_pct, mk, label=cond)
    for _, rr in d.iterrows():
        ax.annotate(rr.detector.split(">")[1].split("over")[0].strip(), (rr.false_alarms_per_hour, rr.recall_pct), fontsize=7, xytext=(3, -8), textcoords="offset points")
ax.set_xscale("symlog", linthresh=0.1); ax.set_xlabel("false alarms per hour of alert driving"); ax.set_ylabel("drowsy segments detected (%)")
ax.set_title("PERCLOS threshold trade-off (labels = threshold)"); ax.legend(fontsize=8); ax.grid(alpha=0.3)
fig.tight_layout(); fig.savefig("figures/fig7_drowsiness_tradeoff.png", dpi=160); plt.close(fig)

# ===================================================================== D. compute budget
models = [  # name, GFLOPs per inference at given input (published or assumed), fps
    ("Forward detector, YOLOv8s-class, full frame 640 px", 28.6, 15, "published (Ultralytics, 640 px)"),
    ("Forward detector, YOLOv8n-class, 1280 px centre crop", 8.7 * (1280 * 384) / (640 * 640), 15, "scaled from 8.7 GFLOPs at 640 px"),
    ("Lane and road-edge segmentation (lightweight)", 4.0, 15, "assumed"),
    ("Driver face + landmarks", 1.0, 30, "assumed"),
    ("Eye-state and gaze classifier", 0.3, 30, "assumed"),
    ("Phone-use classifier", 0.6, 5, "assumed"),
]
comp = []
for name, gf, fps, src in models:
    comp.append(dict(model=name, gflops_per_inference=round(gf, 2), fps=fps, gops_per_s=round(2 * gf * fps, 1), source=src))
cdf = pd.DataFrame(comp)
need = cdf.gops_per_s.sum()
for tops, lab in [(8, "production SoC (8 TOPS INT8)"), (26, "prototype module (~26 TOPS INT8)")]:
    for util in (0.30,):
        OUT.setdefault("compute", {})[lab] = dict(effective_gops=tops * 1000 * util, required_gops=round(need, 1), load_pct=round(100 * need / (tops * 1000 * util), 1))
OUT["compute_table"] = comp
OUT["compute_note"] = "FLOPs counted as multiply-accumulates x2 = operations; 30% sustained NPU utilisation assumed."

# ===================================================================== E. power and thermal
power = [("AI SoC (NPU + CPU, typical / peak)", 4.5, 7.0), ("Forward camera + ISP", 0.6, 0.8), ("Driver camera + 940 nm IR LEDs", 0.8, 1.5),
         ("4G LTE + GNSS", 0.8, 2.5), ("Memory, eMMC, CAN, IMU", 0.6, 0.8), ("Audio amplifier + speaker", 0.2, 1.5), ("Power conversion losses (88% efficient)", 1.0, 1.9)]
pt = sum(p[1] for p in power); pp = sum(p[2] for p in power)
rth = 3.0     # case-to-ambient thermal resistance with an aluminium back plate (°C/W), assumption
OUT["power"] = dict(items=power, typical_w=round(pt, 1), peak_w=round(pp, 1), rth_c_per_w=rth,
                    case_temp_typical_at_50c_cabin=round(50 + pt * rth, 1), case_temp_peak_at_50c_cabin=round(50 + pp * rth, 1),
                    case_temp_parked_sun_70c_typical=round(70 + pt * rth, 1))
json.dump(OUT, open("results/design_analysis.json", "w"), indent=2, default=float)
print(cam.to_string()); print(fcw.to_string()); print("baseline", OUT["fcw"]["baseline_crash_rate_pct"], OUT["fcw"]["baseline_mean_impact_kmh"], "wet", OUT["fcw"]["baseline_crash_rate_wet_pct"])
print(dz.to_string()); print(cdf.to_string()); print(json.dumps(OUT["compute"], indent=1)); print(json.dumps(OUT["power"], indent=1))
