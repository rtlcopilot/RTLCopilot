import json
import math
import os
import re
from pathlib import Path


CHECKED_STAGES = ("synthesis", "placement", "cts", "routing")

STAGE_LOG_FILES = {
    "synthesis": "yosys.log",
    "floorplan": "floorplan.log",
    "pdn":       "pdn.log",
    "placement": "placement.log",
    "cts":       "cts.log",
    "routing":   "routing.log",
    "spef":      "spef.log",
    "timing":    "timing.log",
}


class PolicyError(RuntimeError):
    """A required policy value is unavailable. Raised instead of silently
    falling back to a number invented in code."""


_MODULE_DIR = Path(__file__).resolve().parent
DEFAULT_POLICY_FILE = _MODULE_DIR / "verification_policy.json"


def load_policy() -> dict:
    """Assemble the effective policy. Precedence (lowest → highest):
      1. verification_policy.json shipped next to this module
      2. a user-editable copy at $PDV_POLICY_FILE (default
         /work/verification_policy.json — the volume-mounted work dir, so it
         can be edited on the host without rebuilding the container)
      3. environment variables PDV_<KEY> (e.g. PDV_DENSITY_FLOOR=0.25)
    Keys starting with '_' are documentation and ignored. Reloaded on every
    evaluate() call so edits take effect immediately. Never raises."""
    policy = {}
    override_path = os.environ.get("PDV_POLICY_FILE", "/work/verification_policy.json")
    for path in (DEFAULT_POLICY_FILE, Path(override_path)):
        try:
            if path.exists():
                data = json.loads(path.read_text())
                if isinstance(data, dict):
                    policy.update({k: v for k, v in data.items()
                                   if not str(k).startswith("_")})
        except Exception:
            continue
    for key in list(policy.keys()):
        env = os.environ.get("PDV_" + key.upper())
        if env is not None:
            try:
                policy[key] = json.loads(env)
            except Exception:
                pass  # unparseable env override — keep the file value
    return policy


def _pol(policy, key):
    """Fetch a required policy value; loud, actionable failure if absent."""
    if isinstance(policy, dict) and key in policy:
        return policy[key]
    raise PolicyError(
        "Verification policy value '" + key + "' is unavailable. Ensure "
        "verification_policy.json is present next to pd_verification.py (it "
        "ships with the container), place an override copy in the work "
        "volume, or set the PDV_" + key.upper() + " environment variable.")


def _read_stage_text(stage: str, run_dir, stdout_text: str = "") -> str:
    """Return the best available text for a stage: on-disk log preferred,
    captured stdout as fallback. Never raises."""
    log_name = STAGE_LOG_FILES.get(stage)
    if log_name:
        try:
            p = Path(run_dir) / log_name
            if p.exists():
                txt = p.read_text(errors="replace")
                if txt.strip():
                    return txt
        except Exception:
            pass
    return stdout_text or ""


def _last_match(patterns, text, cast):
    """Try each regex in order; return cast(last match) of the first pattern
    that matches anywhere in the text. None if nothing matches."""
    for pat in patterns:
        try:
            matches = re.findall(pat, text, re.IGNORECASE | re.MULTILINE)
        except re.error:
            continue
        for raw in reversed(matches):
            try:
                return cast(raw)
            except (TypeError, ValueError):
                continue
    return None


def _last_float(patterns, text):
    return _last_match(patterns, text, float)


def _last_int(patterns, text):
    return _last_match(patterns, text, lambda s: int(float(s)))


def _sentinels(text: str) -> dict:
    """Parse deterministic 'PDV <key> <value>' sentinel lines that api.py's
    generated TCL emits (via catch { puts ... }). These are the most reliable
    source for STA-derived metrics."""
    out = {}
    for m in re.finditer(r"^PDV\s+(\w+)\s+(-?[\d\.eE\+]+)\s*$", text, re.MULTILINE):
        try:
            out[m.group(1)] = float(m.group(2))
        except ValueError:
            continue
    return out


def _to_float(v):
    try:
        if v is None or isinstance(v, bool):
            return None
        return float(v)
    except (TypeError, ValueError):
        return None


def _to_int(v):
    f = _to_float(v)
    return int(f) if f is not None else None


def _fmt(v, digits=4):
    """Compact number formatting for messages/contexts (presentation only)."""
    if v is None:
        return "?"
    if isinstance(v, float):
        s = f"{v:.{digits}f}".rstrip("0").rstrip(".")
        return s if s not in ("", "-") else "0"
    return str(v)


def parse_violation_table(text: str) -> dict:
    """Parse the LAST 'Viol/Layer' table from an OpenROAD detailed route log.

        Viol/Layer        met1   met2   met3
        Metal Spacing       24      0      0
        Short               96      6      1

    Returns {category: summed_int_count}. detailed_route prints one table per
    iteration, so only the final table reflects the end state.
    """
    out = {}
    starts = [m.start() for m in re.finditer(r"^\s*Viol/Layer", text, re.MULTILINE)]
    if not starts:
        return out
    chunk = text[starts[-1]:]
    lines = chunk.splitlines()
    for line in lines[1:]:
        if not line.strip():
            break
        m = re.match(r"^\s*([A-Za-z][A-Za-z ./_\-]*?)\s{2,}((?:-?\d+\s*)+)$", line)
        if not m:
            break
        name = m.group(1).strip()
        try:
            counts = [int(x) for x in m.group(2).split()]
        except ValueError:
            continue
        out[name] = out.get(name, 0) + sum(counts)
    return out


def normalize_violation_types(raw) -> dict:
    """run_meta.json may hold violation_types as summed ints (new format) or
    raw space-separated per-layer strings like '96      6      1' (old format
    from existing runs). Normalize both to {category: int}."""
    if not isinstance(raw, dict):
        return {}
    out = {}
    for k, v in raw.items():
        if isinstance(v, bool):
            continue
        if isinstance(v, (int, float)):
            out[str(k)] = int(v)
        elif isinstance(v, str):
            nums = re.findall(r"-?\d+", v)
            if nums:
                out[str(k)] = sum(int(n) for n in nums)
        elif isinstance(v, (list, tuple)):
            try:
                out[str(k)] = sum(int(x) for x in v)
            except (TypeError, ValueError):
                continue
    return out


def _parse_clock_skew(text: str) -> float:
    """Parse OpenSTA report_clock_skew output. Handles two formats:

    Format A (older OpenROAD):
        Clock core_clock
        Latency      CRPR       Skew
           1.05      0.00       0.36

    Format B (your OpenROAD version):
        Clock core_clock
           0.24 source latency _442_/CLK ^
          -0.24 target latency _455_/CLK ^
           0.00 CRPR
        --------------
          -0.00 setup skew

    Returns the last skew value found (float) or None.
    """
    best = None
    lines = text.splitlines()

    # Format A: header line has both CRPR and Skew, data on next line
    for i, line in enumerate(lines):
        if "CRPR" in line and "Skew" in line:
            for j in range(i + 1, min(i + 6, len(lines))):
                nums = re.findall(r"-?\d+\.\d+", lines[j])
                if len(nums) >= 3:
                    try:
                        best = abs(float(nums[-1]))
                    except ValueError:
                        pass
                    break

    if best is not None:
        return best

    # Format B: skew value appears on a line ending with "setup skew" or "hold skew"
    for line in lines:
        m = re.match(r"^\s*(-?[\d\.]+)\s+(?:setup|hold|total)\s+skew\s*$", line, re.IGNORECASE)
        if m:
            try:
                best = abs(float(m.group(1)))
            except ValueError:
                pass

    if best is not None:
        return best

    return _last_float([r"\bskew[:\s]+(-?[\d\.]+)"], text)


def extract_stage_metrics(stage: str, run_dir, stdout_text: str = "") -> dict:
    """Extract real metrics from a completed stage's tool output.
    Prefers the on-disk log file; falls back to captured stdout.
    Returns a dict containing only the metrics that were actually found.
    Never raises."""
    try:
        text = _read_stage_text(stage, run_dir, stdout_text)
        if not text:
            return {}
        fn = {
            "synthesis": _extract_synthesis,
            "placement": _extract_placement,
            "cts":       _extract_cts,
            "routing":   _extract_routing,
            "timing":    _extract_timing,
        }.get(stage)
        if not fn:
            return {}
        metrics = fn(text)
        return {k: v for k, v in metrics.items() if v is not None}
    except Exception:
        return {}


def _extract_synthesis(text: str) -> dict:
    return {
        "chip_area_um2":       _last_float([r"Chip area for (?:top )?module[^:]*:\s*([\d\.]+)"], text),
        "sequential_area_um2": _last_float([r"sequential elements:\s*([\d\.]+)"], text),
        "cell_count":          _last_int([
                                   r"Number of cells:\s+(\d+)",
                                   r"^\s*(\d+)\s+[\d\.E+\-]+\s+cells\s*$",
                               ], text),
        "wire_count":          _last_int([
                                   r"Number of wires:\s+(\d+)",
                                   r"^\s*(\d+)\s+- wires\s*$",
                               ], text),
    }


def _extract_placement(text: str) -> dict:
    s = _sentinels(text)
    overflow = _last_float([r"[Oo]verflow:\s*([\d\.]+)"], text)
    if overflow is not None:
        # gpl reports overflow as a 0–1 fraction; the detection bound is
        # policy, not code. If policy is unavailable, omit rather than guess.
        try:
            if overflow <= _pol(load_policy(), "overflow_fraction_detect_max"):
                overflow = round(overflow * 100.0, 2)
        except PolicyError:
            overflow = None
    return {
        # report_design_area → "Design area 1387 u^2 4% utilization."
        "utilization_pct":  _last_float([r"([\d\.]+)%\s+utilization"], text),
        "overflow_pct":     overflow,
        "placed_instances": (_to_int(s.get("placed_instances"))
                             or _last_int([r"Placed\s+(\d+)\s+instances",
                                           r"[Nn]umber of instances[:\s]+(\d+)",
                                           r"[Ii]nstance count[:\s]+(\d+)"], text)),
        "setup_wns_ns":     (s.get("setup_wns_ns")
                             if s.get("setup_wns_ns") is not None
                             else _last_float([r"worst slack (?:max\s+)?(-?[\d\.]+)"], text)),
    }


def _extract_cts(text: str) -> dict:
    s = _sentinels(text)
    setup = s.get("setup_wns_ns")
    hold = s.get("hold_wns_ns")
    if setup is None:
        setup = _last_float([r"worst slack max\s+(-?[\d\.]+)"], text)
    if hold is None:
        hold = _last_float([r"worst slack min\s+(-?[\d\.]+)"], text)
    return {
        "clock_skew_ns": _parse_clock_skew(text),
        "cts_buffers":   _last_int([r"[Ii]nserted\s+(\d+)\s+(?:clock\s+)?buffers",
                                    r"Created\s+(\d+)\s+(?:clock\s+)?buffers",
                                    r"Total number of buffers inserted[:\s]+(\d+)",
                                    r"(\d+)\s+clock buffers"], text),
        "setup_wns_ns":  setup,
        "hold_wns_ns":   hold,
    }


def _extract_routing(text: str) -> dict:
    vt = parse_violation_table(text)
    return {
        # detailed_route prints these once per iteration — take the LAST
        "drc_violations":     _last_int([r"[Nn]umber of violations\s*=\s*(\d+)"], text),
        "wire_length_um":     _last_float([r"Total wire length\s*=\s*([\d\.]+)"], text),
        "via_count":          _last_int([r"Total number of vias\s*=\s*(\d+)"], text),
        "violation_types":    vt if vt else None,
        # check_antennas — only present when antenna fixing was enabled
        "antenna_violations": _last_int([r"Found\s+(\d+)\s+net violations",
                                         r"(\d+)\s+net violations found",
                                         r"[Nn]ets with antenna violations[:\s]+(\d+)"], text),
    }


def _extract_timing(text: str) -> dict:
    """Keeps the same run_meta keys the /runs history endpoint reads
    (wns_ns, slack_ns, power_w, cell_count) — library-agnostic patterns,
    no hardcoded cell footprints."""
    return {
        "wns_ns":     _last_float([r"\bwns\s+(?:max\s+)?(-?[\d\.]+)"], text),
        "tns_ns":     _last_float([r"\btns\s+(?:max\s+)?(-?[\d\.]+)"], text),
        "slack_ns":   _last_float([r"(-?[\d\.]+)\s+slack \((?:MET|VIOLATED)\)"], text),
        "power_w":    _last_float([r"Total\s+[\d\.eE\+\-]+\s+[\d\.eE\+\-]+\s+[\d\.eE\+\-]+\s+([\d\.eE\+\-]+)"], text),
        "cell_count": _last_int([r"[Nn]umber of instances[:\s]+(\d+)"], text),
    }


def _die_geometry(meta: dict):
    """Parse floorplan geometry stored in run_meta. Returns dict with die
    width/height/area and core area (die shrunk by core_margin_um on all
    sides, when the margin is known). None if unavailable."""
    fp = (meta.get("stages", {}) or {}).get("floorplan", {}) or {}
    die_str = fp.get("die_area")
    if not die_str:
        return None
    try:
        coords = [float(x) for x in str(die_str).split()]
        if len(coords) != 4:
            return None
        w = coords[2] - coords[0]
        h = coords[3] - coords[1]
        if w <= 0 or h <= 0:
            return None
    except (TypeError, ValueError):
        return None
    geo = {"die_str": str(die_str), "w": w, "h": h, "die_area": w * h}
    margin = _to_float(fp.get("core_margin_um"))
    if margin is not None and w > 2 * margin and h > 2 * margin:
        geo["core_area"] = (w - 2 * margin) * (h - 2 * margin)
    return geo


def _target_die_side(chip_area_um2: float, policy) -> int:
    """ceil(sqrt(chip_area / die_density_target) * die_margin_factor): a
    square die sized for the policy's target cell density with its margin —
    computed from synthesis chip area, never from the current die value."""
    return int(math.ceil(math.sqrt(chip_area_um2 / _pol(policy, "die_density_target"))
                         * _pol(policy, "die_margin_factor")))


def _cell_density_pct(chip_area_um2, geo):
    """Die-level cell density in %. Uses the full die rectangle (the die²
    formula generalized to rectangular dies)."""
    if not chip_area_um2 or not geo or geo["die_area"] <= 0:
        return None
    return chip_area_um2 / geo["die_area"] * 100.0


# Check construction 

def _check(check_id, label, status, value=None, unit="", message=""):
    return {"id": check_id, "label": label, "status": status,
            "value": value, "unit": unit, "message": message}


def _wns_check(check_id, label, wns, margin, config_hint):
    """Shared WNS-margin logic: negative WNS is always an error; the
    user-configured margin only separates ok from warning. The margin comes
    from the user, never from code or policy."""
    if wns is None:
        return _check(check_id, label, "warning", None, "ns",
                      "Setup WNS could not be extracted.")
    if wns < 0:
        return _check(check_id, label, "error", wns, "ns",
                      f"Setup timing VIOLATED — worst slack {_fmt(wns)}ns is negative.")
    if margin is None:
        return _check(check_id, label, "unset", wns, "ns",
                      f"Setup WNS is {_fmt(wns)}ns (positive). Set \"{config_hint}\" in the Config "
                      f"panel to enable margin checking.")
    if wns < margin:
        return _check(check_id, label, "warning", wns, "ns",
                      f"Setup WNS {_fmt(wns)}ns is positive but below your {_fmt(margin)}ns margin.")
    return _check(check_id, label, "ok", wns, "ns",
                  f"Setup WNS {_fmt(wns)}ns meets your {_fmt(margin)}ns margin.")


def run_checks(meta: dict, stage: str, thresholds: dict = None, policy: dict = None) -> list:
    """Evaluate a completed stage. thresholds: {wns_margin_ns, max_util_pct},
    values may be None (user hasn't configured them → status 'unset').
    May raise PolicyError if the policy file is missing."""
    thresholds = thresholds or {}
    if policy is None:
        policy = load_policy()
    sm = ((meta or {}).get("stages", {}) or {}).get(stage, {}) or {}
    checks = []

    if stage == "synthesis":
        cells = _to_int(sm.get("cell_count"))
        area = _to_float(sm.get("chip_area_um2"))
        seq = _to_float(sm.get("sequential_area_um2"))
        wires = _to_int(sm.get("wire_count"))
        if cells is None:
            checks.append(_check("cell_count", "Netlist Cells", "warning", None, "",
                                 "Cell count not found in yosys.log — did `stat -liberty` run?"))
        elif cells == 0:
            checks.append(_check("cell_count", "Netlist Cells", "error", 0, "",
                                 "Synthesis produced 0 cells — the design was optimized away. "
                                 "Check the top module name and that outputs are actually driven."))
        else:
            checks.append(_check("cell_count", "Netlist Cells", "ok", cells, "",
                                 f"{cells} standard cells mapped."))
        if area is None:
            checks.append(_check("chip_area", "Chip Area", "warning", None, "µm²",
                                 "Chip area not found in yosys.log. Downstream die-sizing "
                                 "diagnostics need this — they will degrade gracefully."))
        else:
            msg = f"Total cell area {_fmt(area, 1)}µm²."
            if seq is not None and area > 0:
                msg += f" {_fmt(seq / area * 100, 1)}% sequential."
            checks.append(_check("chip_area", "Chip Area", "ok", round(area, 1), "µm²", msg))
        if wires is not None:
            checks.append(_check("wire_count", "Nets", "ok", wires, "",
                                 f"{wires} wires in the netlist."))

    elif stage == "placement":
        util = _to_float(sm.get("utilization_pct"))
        max_util = _to_float(thresholds.get("max_util_pct"))
        if util is None:
            checks.append(_check("utilization", "Core Utilization", "warning", None, "%",
                                 "Utilization not found in placement.log."))
        elif max_util is None:
            checks.append(_check("utilization", "Core Utilization", "unset", util, "%",
                                 f"Utilization is {_fmt(util)}%. Set \"Max Utilization %\" in "
                                 f"Placement Config to enable this check."))
        elif util > max_util:
            checks.append(_check("utilization", "Core Utilization", "error", util, "%",
                                 f"Utilization {_fmt(util)}% exceeds your {_fmt(max_util)}% limit — "
                                 f"expect routing congestion."))
        elif util > _pol(policy, "util_warning_fraction") * max_util:
            pct_gap = round((1.0 - _pol(policy, "util_warning_fraction")) * 100.0)
            checks.append(_check("utilization", "Core Utilization", "warning", util, "%",
                                 f"Utilization {_fmt(util)}% is within {pct_gap}% of your "
                                 f"{_fmt(max_util)}% limit."))
        else:
            checks.append(_check("utilization", "Core Utilization", "ok", util, "%",
                                 f"Utilization {_fmt(util)}% is under your {_fmt(max_util)}% limit."))

        timing_driven = bool(sm.get("timing_driven"))
        wns = _to_float(sm.get("setup_wns_ns"))
        if wns is None and not timing_driven:
            # Not a failure — the user chose non-timing-driven placement.
            checks.append(_check("setup_wns", "Setup WNS (post-place)", "unset", None, "ns",
                                 "No post-placement slack available. Enable Timing-Driven "
                                 "placement (with a Clock Port) in Placement Config to check "
                                 "setup timing here."))
        else:
            checks.append(_wns_check(
                "setup_wns", "Setup WNS (post-place)", wns,
                _to_float(thresholds.get("wns_margin_ns")),
                "WNS Margin (ns)"))

        overflow = _to_float(sm.get("overflow_pct"))
        if overflow is not None:
            checks.append(_check("overflow", "GP Overflow (final)", "ok", overflow, "%",
                                 f"Final global-placement overflow {_fmt(overflow)}%."))
        inst = _to_int(sm.get("placed_instances"))
        if inst is not None:
            checks.append(_check("placed_instances", "Placed Instances", "ok", inst, "",
                                 f"{inst} instances placed."))

    elif stage == "cts":
        skew = _to_float(sm.get("clock_skew_ns"))
        period = _to_float(sm.get("clock_period_ns"))
        if skew is None:
            checks.append(_check("clock_skew", "Clock Skew", "warning", None, "ns",
                                 "Clock skew not found in cts.log."))
        else:
            msg = f"Global clock skew {_fmt(skew)}ns."
            if period:
                msg += f" ({_fmt(skew / period * 100, 1)}% of the {_fmt(period)}ns period.)"
            checks.append(_check("clock_skew", "Clock Skew", "ok", skew, "ns", msg))

        checks.append(_wns_check(
            "setup_wns", "Setup WNS (post-CTS)",
            _to_float(sm.get("setup_wns_ns")),
            _to_float(thresholds.get("wns_margin_ns")),
            "WNS Margin (ns)"))

        hold = _to_float(sm.get("hold_wns_ns"))
        if hold is None:
            checks.append(_check("hold_wns", "Hold WNS (post-CTS)", "warning", None, "ns",
                                 "Hold slack not found in cts.log."))
        elif hold < 0:
            checks.append(_check("hold_wns", "Hold WNS (post-CTS)", "error", hold, "ns",
                                 f"Hold timing VIOLATED after repair_timing — worst hold slack "
                                 f"{_fmt(hold)}ns."))
        else:
            checks.append(_check("hold_wns", "Hold WNS (post-CTS)", "ok", hold, "ns",
                                 f"Hold slack {_fmt(hold)}ns — no hold violations."))

        bufs = _to_int(sm.get("cts_buffers"))
        if bufs is not None:
            checks.append(_check("cts_buffers", "Clock Buffers", "ok", bufs, "",
                                 f"{bufs} clock buffers inserted."))

    elif stage == "routing":
        # Zero tolerance — no user threshold, by definition ("zero" here is
        # definitional, not a tunable constant).
        drc = _to_int(sm.get("drc_violations"))
        vt = normalize_violation_types(sm.get("violation_types"))
        if drc is None:
            checks.append(_check("drc", "Routing DRC Violations", "warning", None, "",
                                 "Violation count not found in routing.log."))
        elif drc > 0:
            top = sorted(vt.items(), key=lambda kv: -kv[1])[:3]
            breakdown = (" Breakdown: " + ", ".join(f"{k} {v}" for k, v in top) + ".") if top else ""
            checks.append(_check("drc", "Routing DRC Violations", "error", drc, "",
                                 f"{drc} DRC violations after detailed route — zero tolerance."
                                 + breakdown))
        else:
            checks.append(_check("drc", "Routing DRC Violations", "ok", 0, "",
                                 "Detailed route finished DRC clean."))

        ant = _to_int(sm.get("antenna_violations"))
        antenna_enabled = sm.get("antenna_fixing")
        if ant is None:
            if antenna_enabled is False:
                checks.append(_check("antenna", "Antenna Violations", "unset", None, "",
                                     "Antenna check not run. Enable \"Antenna Fixing\" in "
                                     "Routing Config to run repair + check."))
            else:
                checks.append(_check("antenna", "Antenna Violations", "warning", None, "",
                                     "Antenna check output not found in routing.log."))
        elif ant > 0:
            checks.append(_check("antenna", "Antenna Violations", "error", ant, "",
                                 f"{ant} nets with antenna violations — zero tolerance."))
        else:
            checks.append(_check("antenna", "Antenna Violations", "ok", 0, "",
                                 "No antenna violations."))

        wl = _to_float(sm.get("wire_length_um"))
        if wl is not None:
            checks.append(_check("wire_length", "Total Wire Length", "ok", round(wl, 1), "µm",
                                 f"{_fmt(wl, 1)}µm routed wire."))
        vias = _to_int(sm.get("via_count"))
        if vias is not None:
            checks.append(_check("via_count", "Vias", "ok", vias, "",
                                 f"{vias} vias."))

    return checks


def _fix(fix_id, label, stage, field, current, proposed, reason, context):
    return {"id": fix_id, "label": label, "stage": stage, "field": field,
            "current_value": current, "proposed_value": proposed,
            "reason": reason, "context": context}


def _synthesis_context(meta) -> str:
    syn = (meta.get("stages", {}) or {}).get("synthesis", {}) or {}
    cells = _to_int(syn.get("cell_count"))
    area = _to_float(syn.get("chip_area_um2"))
    if cells is None and area is None:
        return ""
    return f"Synthesis: {_fmt(cells)} cells, {_fmt(area, 1)}µm² chip area."


def _die_area_fix(meta, chip_area, geo, density_pct, policy, trailing_ctx=""):
    target = _target_die_side(chip_area, policy)
    proposed = f"0 0 {target} {target}"
    if geo and proposed == geo["die_str"]:
        return None
    core_note = ""
    if geo and geo.get("core_area"):
        core_note = f" (core-area density {_fmt(chip_area / geo['core_area'] * 100, 1)}%)"
    limit = _pol(policy, "die_density_limit_pct")
    tgt_density = _pol(policy, "die_density_target")
    margin_f = _pol(policy, "die_margin_factor")
    parts = [_synthesis_context(meta)]
    if geo:
        parts.append(f"Current die {_fmt(geo['w'], 1)}×{_fmt(geo['h'], 1)}µm = "
                     f"{_fmt(density_pct, 1)}% cell density{core_note}.")
    parts.append(f"Density exceeds the {_fmt(limit)}% limit — die area is the root cause. "
                 f"Target: ceil(sqrt({_fmt(chip_area, 1)}/{_fmt(tgt_density)})×{_fmt(margin_f)}) "
                 f"= {target}µm per side (~{_fmt(tgt_density * 100)}% density, "
                 f"{_fmt((margin_f - 1) * 100)}% margin).")
    if trailing_ctx:
        parts.append(trailing_ctx)
    return _fix("die_area", "Increase Die Area", "floorplan", "die_area",
                geo["die_str"] if geo else None, proposed,
                "Die is too small for the synthesized logic; nothing downstream can fix that.",
                " ".join(p for p in parts if p))


def _routing_fixes(meta, policy):
    """The engineer's diagnostic sequence for routing DRC violations.
    Returns (fixes, guidance)."""
    stages = (meta or {}).get("stages", {}) or {}
    rt = stages.get("routing", {}) or {}
    drc = _to_int(rt.get("drc_violations")) or 0
    if drc <= 0:
        return [], None

    syn = stages.get("synthesis", {}) or {}
    chip_area = _to_float(syn.get("chip_area_um2"))
    geo = _die_geometry(meta)

    # Step 1
    density_pct = _cell_density_pct(chip_area, geo)
    if density_pct is not None and density_pct > _pol(policy, "die_density_limit_pct"):
        f = _die_area_fix(meta, chip_area, geo, density_pct, policy,
                          trailing_ctx=f"{drc} routing violations are a symptom — fix the die first.")
        if f:
            return [f], None  # stop: nothing else matters until the die is fixed

    # Step 2
    vt = normalize_violation_types(rt.get("violation_types"))
    total_typed = sum(vt.values())
    shorts = sum(v for k, v in vt.items() if "short" in k.lower())
    spacing = sum(v for k, v in vt.items() if "spacing" in k.lower())
    dominance = _pol(policy, "violation_dominance_fraction")
    shorts_dominant = total_typed > 0 and shorts / total_typed > dominance
    spacing_dominant = total_typed > 0 and spacing / total_typed > dominance

    max_iters = _pol(policy, "max_congestion_iterations")
    iter_step = _pol(policy, "congestion_iteration_step")
    density_step = _pol(policy, "density_step")
    density_floor = _pol(policy, "density_floor")
    density_digits = _pol(policy, "density_round_digits")

    iters = _to_int(rt.get("congestion_iterations"))
    pl = stages.get("placement", {}) or {}
    density = _to_float(pl.get("density"))

    if total_typed:
        dom = ("shorts dominate" if shorts_dominant
               else "spacing dominates" if spacing_dominant
               else "mixed violation types")
        viol_line = f"{drc} violations ({shorts} shorts, {spacing} spacing — {dom})."
    else:
        viol_line = f"{drc} violations (no per-type breakdown available)."

    ctx_base = " ".join(p for p in [
        _synthesis_context(meta),
        (f"Current die {_fmt(geo['w'], 1)}×{_fmt(geo['h'], 1)}µm = {_fmt(density_pct, 1)}% cell "
         f"density (adequate)." if geo and density_pct is not None else
         "Die geometry / chip area unavailable — skipped die-area diagnosis."),
        viol_line,
    ] if p)

    def iterations_fix():
        if iters is None or iters >= max_iters:
            return None
        proposed = min(iters + iter_step, max_iters)
        return _fix("congestion_iterations", "Increase Congestion Iterations",
                    "routing", "congestion_iterations", iters, proposed,
                    "Shorts on lower metals typically resolve with more routing passes — "
                    "no placement change needed yet.",
                    ctx_base + f" Iterations at {iters}/{max_iters} — increasing to {proposed}.")

    def density_fix(extra=""):
        if density is None or density <= density_floor:
            return None
        proposed = round(max(density - density_step, density_floor), density_digits)
        if proposed >= density:
            return None
        return _fix("density", "Reduce Placement Density",
                    "placement", "density", density, proposed,
                    "Lower density spreads cells apart, freeing routing tracks.",
                    ctx_base + (" " + extra if extra else "") +
                    f" Density {_fmt(density)} → {_fmt(proposed)} (floor {_fmt(density_floor)}).")

    if spacing_dominant:
        # Spacing violations don't respond to more iterations — go straight to density.
        f = density_fix("Spacing dominates — skipping iteration bump (it won't help).")
        if f:
            return [f], None
    else:
        # Shorts-dominant and mixed both escalate: iterations first, then density.
        f = iterations_fix()
        if f:
            return [f], None
        f = density_fix(f"Iterations already maxed at {max_iters}.")
        if f:
            return [f], None


    exhausted = []
    if spacing_dominant:
        exhausted.append("iteration bumps won't help spacing violations")
    elif iters is not None and iters >= max_iters:
        exhausted.append(f"congestion iterations are maxed ({max_iters})")
    elif iters is None:
        exhausted.append("congestion iterations are unknown for this run")
    if density is not None and density <= density_floor:
        exhausted.append(f"placement density is at the {_fmt(density_floor)} floor")
    elif density is None:
        exhausted.append("placement density is unknown for this run")
    if density_pct is not None:
        exhausted.append(f"die area is adequate ({_fmt(density_pct, 1)}% cell density)")
    guidance = ("No config-level fix left: " + ", ".join(exhausted) +
                ". Look upstream — inspect the synthesized netlist for very high-fanout nets, "
                "and try a different Pin Placement in Floorplan Config (clustered pins on one "
                "edge cause local congestion no router setting can solve).")
    return [], guidance


def _clock_period_fix(fix_id, target_stage, wns, period, policy, prefix):
    margin = _pol(policy, "wns_clock_margin")
    digits = _pol(policy, "clock_period_round_digits")
    proposed = round(period + abs(wns) * margin, digits)
    if proposed == period:
        return None
    return _fix(
        fix_id, "Relax Clock Period", target_stage, "clock_period_ns",
        period, proposed,
        prefix + f" the proposed period covers the violation with "
        f"{_fmt((margin - 1) * 100)}% margin.",
        f"Setup WNS {_fmt(wns)}ns on a {_fmt(period)}ns clock. Proposed: "
        f"{_fmt(period)} + |{_fmt(wns)}| × {_fmt(margin)} = {_fmt(proposed)}ns. "
        f"(Applied to all stages that take a clock period.)")


def _placement_fixes(meta, thresholds, policy):
    stages = (meta or {}).get("stages", {}) or {}
    pl = stages.get("placement", {}) or {}
    fixes = []

    # Setup WNS violation 
    wns = _to_float(pl.get("setup_wns_ns"))
    period = (_to_float(pl.get("clock_period_ns"))
              or _pol(policy, "default_clock_period_ns"))
    if wns is not None and wns < 0:
        f = _clock_period_fix("clock_period", "placement", wns, period, policy,
                              "The placed design cannot meet this clock;")
        if f:
            fixes.append(f)

    # Over-utilization 
    util = _to_float(pl.get("utilization_pct"))
    max_util = _to_float((thresholds or {}).get("max_util_pct"))
    if util is not None and max_util is not None and util > max_util:
        chip_area = _to_float((stages.get("synthesis", {}) or {}).get("chip_area_um2"))
        geo = _die_geometry(meta)
        if chip_area and geo:
            target = _target_die_side(chip_area, policy)
            if target > max(geo["w"], geo["h"]):
                proposed = f"0 0 {target} {target}"
                if proposed != geo["die_str"]:
                    tgt_density = _pol(policy, "die_density_target")
                    margin_f = _pol(policy, "die_margin_factor")
                    fixes.append(_fix(
                        "die_area_util", "Increase Die Area", "floorplan", "die_area",
                        geo["die_str"], proposed,
                        "Utilization above your limit — a larger die computed from synthesis "
                        "area brings it down.",
                        f"{_synthesis_context(meta)} Utilization {_fmt(util)}% > "
                        f"{_fmt(max_util)}% limit on a {_fmt(geo['w'], 1)}×{_fmt(geo['h'], 1)}µm "
                        f"die. Target die {target}×{target}µm (from chip area at "
                        f"{_fmt(tgt_density * 100)}% density, "
                        f"{_fmt((margin_f - 1) * 100)}% margin)."))
    return fixes, None


def _cts_fixes(meta, policy):
    stages = (meta or {}).get("stages", {}) or {}
    cts = stages.get("cts", {}) or {}
    fixes = []
    guidance = None

    wns = _to_float(cts.get("setup_wns_ns"))
    period = (_to_float(cts.get("clock_period_ns"))
              or _pol(policy, "default_clock_period_ns"))
    if wns is not None and wns < 0:
        f = _clock_period_fix("clock_period_cts", "cts", wns, period, policy,
                              "Post-CTS setup violation with propagated clocks;")
        if f:
            fixes.append(f)

    hold = _to_float(cts.get("hold_wns_ns"))
    if hold is not None and hold < 0:
        guidance = ("Hold violations survived repair_timing — there is no single deterministic "
                    "knob for this. Typical causes: clock tree too fast relative to data paths. "
                    "Try lower-drive Buffer Cells or a larger Max Slew in CTS Config, then re-run CTS.")
    return fixes, guidance


def _synthesis_fixes(meta):
    syn = ((meta or {}).get("stages", {}) or {}).get("synthesis", {}) or {}
    if _to_int(syn.get("cell_count")) == 0:
        return [], ("The netlist has 0 cells — Yosys optimized the whole design away. Verify the "
                    "top module name is 'top', that outputs are connected, and that the RTL "
                    "actually drives them.")
    return [], None


def compute_fixes(meta: dict, stage: str, thresholds: dict = None, policy: dict = None):
    """Returns (fixes, guidance). Fixes are deterministic dicts with the real
    numbers used in the computation baked into `context`. No-op fixes
    (proposed == current) are never emitted. Raises PolicyError if the policy
    file is missing; never raises anything else."""
    if policy is None:
        policy = load_policy()
    try:
        fn = {
            "synthesis": lambda: _synthesis_fixes(meta),
            "placement": lambda: _placement_fixes(meta, thresholds, policy),
            "cts":       lambda: _cts_fixes(meta, policy),
            "routing":   lambda: _routing_fixes(meta, policy),
        }.get(stage)
        if not fn:
            return [], None
        fixes, guidance = fn()
        fixes = [f for f in fixes if f and f.get("proposed_value") != f.get("current_value")]
        return fixes, guidance
    except PolicyError:
        raise
    except Exception:
        return [], None


def evaluate(meta: dict, stage: str, thresholds: dict = None) -> dict:
    """Full check + fix payload for GET /check/{run_id}/{stage}. If the policy
    file is missing entirely, returns an explicit error payload instead of
    inventing numbers."""
    thresholds = {k: v for k, v in (thresholds or {}).items() if v is not None}
    policy = load_policy()
    sm = ((meta or {}).get("stages", {}) or {}).get(stage, {}) or {}
    metrics = {k: v for k, v in sm.items()
               if k not in ("status", "time_s", "exit_code")}
    base = {
        "run_id":   (meta or {}).get("run_id"),
        "stage":    stage,
        "status":   sm.get("status", "unknown"),
        "metrics":  metrics,
        "thresholds_used": thresholds,
        "policy_used": policy,
    }
    try:
        base["checks"] = run_checks(meta, stage, thresholds, policy)
        fixes, guidance = compute_fixes(meta, stage, thresholds, policy)
        base["fixes"] = fixes
        base["guidance"] = guidance
    except PolicyError as e:
        base.update({"checks": [], "fixes": [], "guidance": None, "error": str(e)})
    return base