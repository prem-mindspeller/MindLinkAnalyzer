"""
run_neuroprofile_report.py
--------------------------
Generates a synthetic EEG session, runs it through the full newBackend
analysis pipeline, prints the neuroprofile report to the console, and
SAVES it to reports/neuroprofile_session<N>_<timestamp>.txt

Usage:
    python tests/run_neuroprofile_report.py               # session 1 (default)
    python tests/run_neuroprofile_report.py --session 2   # session 2
    python tests/run_neuroprofile_report.py --session 3   # session 3
    python tests/run_neuroprofile_report.py --json        # also save full JSON sidecar
    python tests/run_neuroprofile_report.py --debug       # print raw feature stats
"""
import sys, os, io, json, math, random, argparse, datetime

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "newBackend"))

REPORTS_DIR = os.path.join(os.path.dirname(__file__), "..", "reports")

# ── Synthetic EEG generators ──────────────────────────────────────────────────
# 512 Hz | 1024-sample (2 s) windows | 4 windows per 8-s block
# >= 2 blocks needed for Welch t-test  ->  >= 16 s (8192 samples) per segment
FS         = 512
N_BASELINE = 60 * FS   # 60 s eyes-closed
N_TASK     = 32 * FS   # 32 s per task = 4 x 8-s blocks

def _multi(n, components, noise_std=15, seed=0):
    """Sum of sinusoids + Gaussian noise."""
    rng = random.Random(seed)
    return [
        sum(a * math.sin(2 * math.pi * f * i / FS) for f, a in components)
        + rng.gauss(0, noise_std)
        for i in range(n)
    ]

# Baseline: eyes-closed, strong alpha (10 Hz) + light theta (6 Hz)
BASELINE_EC = _multi(N_BASELINE, [(10, 80), (6, 20), (20, 12)], noise_std=10, seed=42)

# ── All 12 canonical tasks (only the relevant subset is passed to the pipeline)
ALL_TASKS = {
    # Session 1 ────────────────────────────────────────────────────────────────
    # Task 1: Mental Math  — beta up, alpha down
    "mental_math":         _multi(N_TASK, [(20, 75), (10, 15), (6, 15)], noise_std=12, seed=11),
    # Task 2: Visual Imagery — alpha up (internal top-down)
    "visual_imagery":      _multi(N_TASK, [(10, 95), (6, 20), (20, 10)], noise_std=11, seed=12),
    # Task 3: Focused Attention — alpha down, beta up
    "focused_attention":   _multi(N_TASK, [(10, 28), (20, 45), (6, 18)], noise_std=12, seed=13),
    # Task 4: Static Emotion Grasp — mild alpha change (moderator-only)
    "static_emotion_grasp": _multi(N_TASK, [(10, 55), (6, 30), (20, 22)], noise_std=14, seed=14),
    # Session 2 additions ──────────────────────────────────────────────────────
    # Task 5: Working Memory — frontal theta up, alpha down
    "working_memory":      _multi(N_TASK, [(6, 70), (10, 18), (20, 25)], noise_std=12, seed=15),
    # Task 6: Language Processing — beta up, alpha down
    "language_processing": _multi(N_TASK, [(20, 60), (10, 22), (6, 16)], noise_std=12, seed=16),
    # Task 7: Motor Imagery — mu/alpha ERD, mild beta
    "motor_imagery":       _multi(N_TASK, [(10, 30), (20, 38), (6, 22)], noise_std=13, seed=17),
    # Task 8: Cognitive Load / Multitasking — theta up, alpha down
    "cognitive_load_multitasking": _multi(N_TASK, [(6, 65), (10, 20), (20, 30)], noise_std=13, seed=18),
    # Task 9: Divergent Thinking — frontal alpha up, theta mid
    "divergent_thinking":  _multi(N_TASK, [(10, 85), (6, 35), (20, 12)], noise_std=12, seed=19),
    # Session 3 additions ──────────────────────────────────────────────────────
    # Task 10: Body Scan — relaxed, alpha stable (moderator-only)
    "body_scan":           _multi(N_TASK, [(10, 82), (6, 18), (20, 10)], noise_std=11, seed=20),
    # Task 11: Visual Colour Processing — moderate alpha shift (moderator-only)
    "visual_colour_processing": _multi(N_TASK, [(10, 62), (6, 25), (20, 18)], noise_std=13, seed=21),
    # Task 12: Semantic Memory Retrieval — theta up, beta mild
    "semantic_memory_retrieval": _multi(N_TASK, [(6, 58), (10, 28), (20, 28)], noise_std=12, seed=22),
}

SESSION_TASKS = {
    1: ["mental_math", "visual_imagery", "focused_attention", "static_emotion_grasp"],
    2: ["mental_math", "visual_imagery", "focused_attention", "static_emotion_grasp",
        "working_memory", "language_processing", "motor_imagery",
        "cognitive_load_multitasking", "divergent_thinking"],
    3: list(ALL_TASKS.keys()),
}


def run(session: int = 1):
    """Run the full pipeline for the given session number."""
    task_ids = SESSION_TASKS[session]
    tasks = {tid: ALL_TASKS[tid] for tid in task_ids}

    import types, importlib.util

    for mod_name in ("serial", "serial.tools", "serial.tools.list_ports"):
        if mod_name not in sys.modules:
            sys.modules[mod_name] = types.ModuleType(mod_name)
    sys.modules["serial"].Serial = object
    sys.modules["serial"].SerialException = Exception
    sys.modules["serial.tools.list_ports"].comports = lambda: []

    if "fastapi" not in sys.modules:
        try:
            import fastapi  # noqa
        except ImportError:
            for mod_name in ("fastapi", "fastapi.middleware", "fastapi.middleware.cors"):
                sys.modules[mod_name] = types.ModuleType(mod_name)

            class _FakeApp:
                def add_middleware(self, *a, **kw): pass
                def get(self, *a, **kw):
                    def _d(f): return f
                    return _d
                def post(self, *a, **kw):
                    def _d(f): return f
                    return _d
                def websocket(self, *a, **kw):
                    def _d(f): return f
                    return _d

            sys.modules["fastapi"].FastAPI = lambda **kw: _FakeApp()
            sys.modules["fastapi"].WebSocket = object
            sys.modules["fastapi"].WebSocketDisconnect = Exception
            sys.modules["fastapi"].middleware = sys.modules["fastapi.middleware"]
            sys.modules["fastapi.middleware.cors"].CORSMiddleware = object
            from contextlib import asynccontextmanager
            sys.modules["fastapi"].asynccontextmanager = asynccontextmanager

    spec = importlib.util.spec_from_file_location(
        "eeg_main",
        os.path.join(os.path.dirname(__file__), "..", "newBackend", "main.py"),
    )
    eeg_main = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(eeg_main)

    return eeg_main.analyze({
        "baseline":      {"eyes_closed": BASELINE_EC},
        "tasks":         tasks,
        "block_seconds": 8.0,
    })


def _fmt_section(title: str, width: int = 76):
    pad = "-" * ((width - len(title) - 2) // 2)
    return f"\n{pad} {title} {pad}"


def _render_report(result: dict, session: int, generated_at: str) -> str:
    """Render the full report as a string (written to file and printed)."""
    buf = io.StringIO()

    def pr(*args, **kwargs):
        kwargs["file"] = buf
        print(*args, **kwargs)

    W = 76
    export = result.get("neuroprofile_feature_export", {})

    if "error" in export:
        pr(f"[ERROR] Neuroprofile export failed: {export['error']}")
        return buf.getvalue()

    # ── Header ──────────────────────────────────────────────────────────────────
    pr("=" * W)
    pr("  MINDSPELLER EEG  |  NEUROPROFILE FEATURE REPORT")
    pr("=" * W)
    pr(f"  Generated        : {generated_at}")
    pr(f"  Protocol session : Session {session}")
    pr(f"  Session depth    : {export.get('protocol_session_depth', '')}")
    pr(f"  Headset scope    : {export.get('headset_scope', '')}")
    pr(f"  Report version   : {export.get('feature_report_version', '')}")
    pr(f"  Traceability     : {export.get('traceability_version', '')}")
    pr("-" * W)

    # Global reliability comes from the flat top-level key (v7.1+)
    reliability = (export.get("global_reliability") or
                   export.get("global_quality", {}).get("overall_reliability") or
                   "?").upper()
    bqc      = export.get("baseline_qc") or export.get("global_quality", {})
    kept     = bqc.get("kept", bqc.get("baseline_kept", "?"))
    rejected = bqc.get("rejected", bqc.get("baseline_rejected", 0)) or 0
    nw       = bqc.get("not_worn", bqc.get("baseline_rejected_not_worn", 0)) or 0
    art      = bqc.get("artifact", bqc.get("baseline_rejected_artifact", 0)) or 0
    flat     = bqc.get("flatline", bqc.get("baseline_rejected_flatline", 0)) or 0
    gq       = export.get("global_quality", {})
    gg       = gq.get("gamma_guard_count", 0) or 0

    pr(f"  Global reliability : {reliability}")
    pr(f"  Baseline windows   : {kept} kept  /  {rejected} rejected"
       f"  (not-worn={nw}, artifact={art}, flatline={flat})")
    if gg:
        pr(f"  Gamma guard        : fired on {gg} task(s)")
    for note in gq.get("notes", []):
        pr(f"  [!] {note}")

    # Session confidence cap block (v7.1)
    cap = export.get("session_confidence_cap")
    if cap:
        pr()
        pr(f"  Session confidence cap:")
        pr(f"    Implicit trait max      : {cap.get('implicit_trait_max', '?').upper()}")
        pr(f"    Role recommendation max : {cap.get('role_recommendation_max', '?').upper()}")
        pr(f"    Applied session cap     : {cap.get('applied_session_cap', '?').upper()}")
        pr(f"    Applied reliability cap : {cap.get('applied_reliability_cap', '?').upper()}")
        reason = cap.get('reason', '')
        if reason:
            # Wrap at ~70 chars
            words = reason.split()
            line = "    Reason: "
            for w in words:
                if len(line) + len(w) + 1 > 76:
                    pr(line)
                    line = "      " + w + " "
                else:
                    line += w + " "
            if line.strip():
                pr(line)

    # ── Allowed ability pool ─────────────────────────────────────────────────
    pool = export.get("allowed_ability_pool", [])
    pr(_fmt_section("ALLOWED O*NET ABILITY POOL", W))
    if pool:
        for a in pool:
            pr(f"    [ELIGIBLE]  {a}")
    else:
        pr("    (none -- all tasks are moderator-only or no features passed gate)")

    # Moderator characteristics
    mod_chars = export.get("moderator_only_characteristics", [])
    if mod_chars:
        pr()
        pr("  Moderator-only characteristics (context only, not role-matched):")
        for mc in mod_chars:
            pr(f"    [MODERATOR] {mc}")

    # Blocked labels
    blocked_all = export.get("blocked_unsupported_labels", [])
    if blocked_all:
        pr()
        pr(f"  Globally blocked inference labels ({len(blocked_all)}):")
        cols = [blocked_all[i:i+3] for i in range(0, len(blocked_all), 3)]
        for row in cols:
            pr("    " + "  |  ".join(f"{x:<30s}" for x in row))

    # ── Per-task sections ────────────────────────────────────────────────────
    for task_entry in (export.get("tasks") or export.get("tasks_detected", [])):
        tnum  = task_entry.get("task_number", "?")
        tname = task_entry["canonical_task_name"]
        rm    = task_entry["role_matching_status"]
        rstat = task_entry.get("repeat_status", "not_repeated")
        sq    = task_entry.get("signal_quality", {})
        ts    = task_entry.get("task_summary", {})

        pr(_fmt_section(f"TASK {tnum}: {tname.upper()}", W))
        pr(f"  Canonical ID    : {task_entry['canonical_task_id']}")
        pr(f"  Role matching   : {rm}")
        pr(f"  Repeat status   : {rstat}")
        pr(f"  Signal quality  : {sq.get('quality_level', '?').upper()}"
           f"  (usable: {sq.get('usable_feature_count', 0)},"
           f" rejected: {sq.get('rejected_feature_count', 0)})")
        if sq.get("artifact_flags"):
            pr(f"  Artifacts       : {', '.join(sq['artifact_flags'])}")
        conf_label = ts.get('confidence', '?').upper()
        conf_before = ts.get('confidence_before_cap', '')
        if conf_before and conf_before != ts.get('confidence', '?'):
            pr(f"  Confidence      : {conf_label}  (was: {conf_before.upper()} before reliability cap)")
        else:
            pr(f"  Confidence      : {conf_label}")
        pr()

        # Characteristics
        chars = ts.get("supported_characteristics", [])
        mod_c = ts.get("moderator_characteristics", [])
        if chars:
            pr(f"  Supported characteristics ({len(chars)}):")
            for c in chars:
                pr(f"    * {c}")
        elif mod_c:
            pr(f"  Moderator-only characteristics ({len(mod_c)}):")
            for c in mod_c:
                pr(f"    ~ {c}")
        else:
            pr("  Supported characteristics: none (moderator-only or insufficient evidence)")

        # Allowed abilities
        abilities = ts.get("allowed_onet_ability_candidates", [])
        pr()
        if abilities:
            pr(f"  Allowed O*NET ability candidates ({len(abilities)}):")
            for a in abilities:
                pr(f"    + {a}")
        else:
            pr("  Allowed O*NET ability candidates: none (moderator-only task)")

        # Blocked inferences
        blocked = ts.get("blocked_inferences", [])
        pr()
        pr(f"  Blocked inferences ({len(blocked)}):")
        for b in blocked:
            pr(f"    - {b}")

        # Top passing features
        feats = [
            f for f in task_entry.get("features", [])
            if f.get("passes_neuroprofile_gate")
        ]
        feats.sort(key=lambda f: abs(f.get("effect_size_d") or 0), reverse=True)
        pr()
        if feats:
            pr(f"  Top EEG evidence features (by |Cohen's d|, max 8 shown):")
            pr(f"  {'Strength':<10} {'Metric':<28} {'d':>7}  {'%chg':>7}  "
               f"{'q-val':>7}  {'basis':<28}  {'safety'}")
            pr("  " + "-" * (W - 2))
            for f in feats[:8]:
                d     = f.get("effect_size_d") or 0.0
                pct   = f.get("percent_change") or 0.0
                q     = f.get("q_value") or 1.0
                s     = f.get("feature_strength", "?")
                basis = f.get("significance_basis", "?")
                safety = f.get("interpretation_safety", "?")
                pr(f"  [{s:<8}] {f['metric_name']:<28} {d:>+7.3f}  "
                   f"{pct:>+7.1f}%  {q:>7.4f}  {basis:<28}  {safety}")
        else:
            pr("  No features passed the neuroprofile gate for this task.")

        # Task-level summary text
        summary_text = ts.get("summary", "")
        if summary_text:
            pr()
            pr(f"  Summary: {summary_text}")

    # ── Footer ──────────────────────────────────────────────────────────────────
    pr()
    pr("=" * W)
    pr("  DISCLAIMER: This report contains structured EEG evidence only.")
    pr("  Role matching, neuroprofile generation, and hiring decisions")
    pr("  are performed separately in the neuroprofile backend.")
    pr("=" * W)
    pr(f"  END OF REPORT  |  Session {session}  |  {generated_at}")
    pr("=" * W)

    return buf.getvalue()


def _print_report(result: dict, session: int, generated_at: str):
    print(_render_report(result, session, generated_at))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Generate a Mindspeller neuroprofile EEG report.")
    parser.add_argument("--session", type=int, choices=[1, 2, 3], default=1,
                        help="Protocol session number (default: 1)")
    parser.add_argument("--json",  action="store_true",
                        help="Also save a full JSON sidecar file")
    parser.add_argument("--debug", action="store_true",
                        help="Print raw per-feature stats to console")
    args = parser.parse_args()

    generated_at = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    ts_stamp     = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")

    print(f"Running Session {args.session} analysis...")
    result = run(session=args.session)

    # Ensure reports directory exists
    os.makedirs(REPORTS_DIR, exist_ok=True)

    # ── Save text report ───────────────────────────────────────────────────────────
    report_text = _render_report(result, args.session, generated_at)
    txt_path = os.path.join(
        REPORTS_DIR,
        f"neuroprofile_session{args.session}_{ts_stamp}.txt"
    )
    with open(txt_path, "w", encoding="utf-8") as fh:
        fh.write(report_text)

    # ── Always save JSON sidecar (machine-readable primary format) ─────────────────
    json_path = os.path.join(
        REPORTS_DIR,
        f"neuroprofile_session{args.session}_{ts_stamp}.json"
    )
    with open(json_path, "w", encoding="utf-8") as fh:
        json.dump(result.get("neuroprofile_feature_export", {}), fh, indent=2)

    # ── Debug raw stats ───────────────────────────────────────────────────────────────
    if args.debug:
        for tid, tdata in result.get("per_task", {}).items():
            print(f"\n--- {tid} raw stats (top 10 by |d|) ---")
            feats = [
                (fn, fd) for fn, fd in (tdata.get("analysis") or {}).items()
                if isinstance(fd, dict) and not fn.startswith("_")
            ]
            feats.sort(key=lambda x: abs(x[1].get("effect_size_d") or 0), reverse=True)
            for fn, fd in feats[:10]:
                print(f"  {fn:35s}  d={fd.get('effect_size_d', 0):+.3f}"
                      f"  p={fd.get('p_value', 1):.4f}"
                      f"  q={fd.get('q_value', 1):.4f}"
                      f"  pct={fd.get('percent_change', 0):+.1f}%"
                      f"  sig={fd.get('significant_change', False)}")

    # ── Print to console ───────────────────────────────────────────────────────────────
    print(report_text)
    print(f"Report saved  -> {os.path.abspath(txt_path)}")
    if json_path:
        print(f"JSON sidecar  -> {os.path.abspath(json_path)}")
