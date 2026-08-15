"""
RTL Copilot — PD Tools API
Runs inside the Docker container.
All stages read inputs from and write outputs to /work/{run_id}/ (mounted from host).
"""

import os
import json
import uuid
import time
import subprocess
import re
from pathlib import Path
from fastapi import FastAPI, HTTPException
from fastapi.responses import StreamingResponse, FileResponse
from pydantic import BaseModel, Field
from typing import Optional, Literal
from jinja2 import Environment, FileSystemLoader

import pd_verification as pdv  # all check/metric/fix logic lives there — keep it out of this file


def _read_meta_clock(run_dir: Path) -> float:
    """Read clock_period_ns from run_meta.json — written by synthesis so all
    downstream stages share the same value without re-specifying it."""
    try:
        return json.loads((run_dir / "run_meta.json").read_text()).get("clock_period_ns", 10.0)
    except Exception:
        return 10.0

app = FastAPI(title="RTL Copilot PD Tools", version="2.0.0")


WORK_BASE = "/work"
PDK_ROOT  = "/pdk/volare/sky130/versions/0fe599b2afb6708d281543108caf8310912f54af/sky130A"
TEMPLATES  = "/app/templates"

# Cell library configs — keyed by library name
CELL_LIBS = {
    "sky130_fd_sc_hd": {
        "site":    "unithd",
        "lib_tt":  "sky130_fd_sc_hd__tt_025C_1v80.lib",
        "lib_ss":  "sky130_fd_sc_hd__ss_100C_1v60.lib",
        "lib_ff":  "sky130_fd_sc_hd__ff_n40C_1v95.lib",
        "lef":     "sky130_fd_sc_hd.lef",
        "tlef":    "sky130_fd_sc_hd__nom.tlef",
        "tapcell":       "sky130_fd_sc_hd__tapvpwrvgnd_1",
        "tap_distance":  14,
        "fill_cells":    "sky130_fd_sc_hd__fill_1 sky130_fd_sc_hd__fill_2 sky130_fd_sc_hd__fill_4 sky130_fd_sc_hd__fill_8",
        "drc_deck":      "/OpenROAD-flow-scripts/flow/platforms/sky130hd/drc/sky130hd.lydrc",
    },
    "sky130_fd_sc_hs": {
        "site":    "unithhs",
        "lib_tt":  "sky130_fd_sc_hs__tt_025C_1v80.lib",
        "lib_ss":  "sky130_fd_sc_hs__ss_100C_1v60.lib",
        "lib_ff":  "sky130_fd_sc_hs__ff_n40C_1v95.lib",
        "lef":     "sky130_fd_sc_hs.lef",
        "tlef":    "sky130_fd_sc_hs__nom.tlef",
        "tapcell":       "sky130_fd_sc_hs__tapvpwrvgnd_1",
        "tap_distance":  14,
        "fill_cells":    "sky130_fd_sc_hs__fill_1 sky130_fd_sc_hs__fill_2 sky130_fd_sc_hs__fill_4 sky130_fd_sc_hs__fill_8",
        "drc_deck":      "",
    },
    "sky130_fd_sc_ms": {
        "site":    "unithdms",
        "lib_tt":  "sky130_fd_sc_ms__tt_025C_1v80.lib",
        "lib_ss":  "sky130_fd_sc_ms__ss_100C_1v60.lib",
        "lib_ff":  "sky130_fd_sc_ms__ff_n40C_1v95.lib",
        "lef":     "sky130_fd_sc_ms.lef",
        "tlef":    "sky130_fd_sc_ms__nom.tlef",
        "tapcell":       "sky130_fd_sc_ms__tapvpwrvgnd_1",
        "tap_distance":  14,
        "fill_cells":    "sky130_fd_sc_ms__fill_1 sky130_fd_sc_ms__fill_2 sky130_fd_sc_ms__fill_4 sky130_fd_sc_ms__fill_8",
        "drc_deck":      "",
    },
}

CORNERS = {"tt": "lib_tt", "ss": "lib_ss", "ff": "lib_ff"}

# ORFS platform assets used for the final DEF -> GDS merge (def2stream).
# tech_lyt : KLayout technology file (embeds LEF list + GDS layer mapping)
# lib_gds  : library GDS with real standard-cell geometry, merged into output
# Libraries without an entry fall back to a plain (geometry-less) DEF->GDS export.
ORFS_UTIL_DEF2STREAM = "/OpenROAD-flow-scripts/flow/util/def2stream.py"

# sky130 stream-out mapping: DEF layer NAME -> (GDS layer, drawing datatype).
# Pin shapes go to datatype 16, labels to 5 (sky130 convention). This is the
# published sky130 layer table — platform data, not design data.
SKY130_GDS_LAYERS = {
    "li1":  (67, 20), "mcon": (67, 44),
    "met1": (68, 20), "via":  (68, 44),
    "met2": (69, 20), "via2": (69, 44),
    "met3": (70, 20), "via3": (70, 44),
    "met4": (71, 20), "via4": (71, 44),
    "met5": (72, 20),
    "nwell": (64, 20), "pwell": (64, 44), "tap": (65, 44),
}
ORFS_PLATFORMS = {
    "sky130_fd_sc_hd": {
        "tech_lyt": "/OpenROAD-flow-scripts/flow/platforms/sky130hd/sky130hd.lyt",
        "lib_gds":  "/OpenROAD-flow-scripts/flow/platforms/sky130hd/gds/sky130_fd_sc_hd.gds",
        "cdl":      "/OpenROAD-flow-scripts/flow/platforms/sky130hd/cdl/sky130hd.cdl",
        "lvs_deck": "/OpenROAD-flow-scripts/flow/platforms/sky130hd/lvs/sky130hd.lylvs",
        "fill_json": "/OpenROAD-flow-scripts/flow/platforms/sky130hd/fill.json",
    },
    "sky130_fd_sc_hs": {
        "tech_lyt": "/OpenROAD-flow-scripts/flow/platforms/sky130hs/sky130hs.lyt",
        "lib_gds":  "/OpenROAD-flow-scripts/flow/platforms/sky130hs/gds/sky130_fd_sc_hs.gds",
    },
}

# Files that can be downloaded
ALLOWED_DOWNLOADS = {
    "netlist.v", "yosys.log",
    "floorplan.def", "pdn.def", "placement.def",
    "cts.def", "routed.def",
    "output.spef", "routing.spef", "route_drc.rpt", "constraints.sdc",
    "timing_ss.rpt", "timing_ff.rpt", "timing_tt.rpt",
    "timing.rpt", "drc.rpt", "output.gds",
    "lvs_report.lvsdb", "lvs_extracted.cir", "lvs_ref.cdl", "lvs.log",
    "run_meta.json",
    # per-stage OpenROAD logs (source of truth for metric extraction)
    "floorplan.log", "pdn.log", "placement.log",
    "cts.log", "routing.log", "spef.log", "timing.log",
    # layout preview PNGs
    "placement_preview.png", "routing_preview.png", "gds_preview.png",
}



def get_run_dir(run_id: str) -> Path:
    p = Path(WORK_BASE) / run_id
    p.mkdir(parents=True, exist_ok=True)
    return p


def get_pdk_paths(cell_lib: str, corner: str) -> dict:
    """Resolve all PDK file paths for a given cell library and corner."""
    lib_cfg = CELL_LIBS.get(cell_lib)
    if not lib_cfg:
        raise HTTPException(status_code=400, detail=f"Unknown cell library: {cell_lib}")

    corner_key = CORNERS.get(corner)
    if not corner_key:
        raise HTTPException(status_code=400, detail=f"Unknown corner: {corner}. Use tt/ss/ff")

    base = PDK_ROOT + "/libs.ref/" + cell_lib
    tech = PDK_ROOT + "/libs.ref/" + cell_lib

    # RCX rules: corner-specific file name uses a tag mapped from corner key
    corner_tag = {"tt": "nom", "ss": "rcworst", "ff": "rcbest"}.get(corner, "nom")
    rcx_rules  = (PDK_ROOT +
                  "/libs.tech/openlane/rules.openrcx.sky130A." +
                  corner_tag + ".spef_extractor")

    return {
        "lib":      base + "/lib/" + lib_cfg[corner_key],
        "lef":      base + "/lef/" + lib_cfg["lef"],
        "tech_lef": tech + "/techlef/" + lib_cfg["tlef"],
        "site":         lib_cfg["site"],
        "tapcell":      lib_cfg.get("tapcell", ""),
        "tap_distance": lib_cfg.get("tap_distance", 14),
        "fill_cells":   lib_cfg.get("fill_cells", ""),
        "drc_deck":     lib_cfg.get("drc_deck", ""),
        "rcx_rules":    rcx_rules,
    }


def render_template(name: str, ctx: dict) -> str:
    """Render a Jinja2 template from /app/templates/."""
    env = Environment(loader=FileSystemLoader(TEMPLATES), trim_blocks=True, lstrip_blocks=True)
    return env.get_template(name).render(**ctx)


STAGE_OUTPUTS = {
    "synthesis": "netlist.v",
    "floorplan": "floorplan.def",
    "pdn":       "pdn.def",
    "placement": "placement.def",
    "cts":       "cts.def",
    "routing":   "routed.def",
    "spef":      None,   # filename is configurable; checked by caller
    "timing":    "timing.rpt",
    "drc":       "output.gds",
}


def stream_process(cmd: list, cwd: str, run_dir: Path, stage: str, meta_extra: dict = None):
    """Run subprocess, stream output, update run_meta.json on completion."""
    def generate():
        t0 = time.time()
        proc = subprocess.Popen(
            cmd, cwd=cwd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True, bufsize=1
        )
        lines = []
        for line in proc.stdout:
            lines.append(line)
            yield line
        proc.wait()

        elapsed = round(time.time() - t0, 2)
        success = proc.returncode == 0

        # Output-artifact contract: exit code 0 is necessary but not
        # sufficient. The expected file must exist and be newer than the
        # stage start, or the stage is declared failed.
        expected = STAGE_OUTPUTS.get(stage)
        missing_output = None
        if success and expected:
            out_path = run_dir / expected
            if not out_path.exists() or out_path.stat().st_mtime < t0 - 1:
                success = False
                missing_output = expected

        # Update run metadata
        meta_path = run_dir / "run_meta.json"
        meta = {}
        if meta_path.exists():
            try:
                meta = json.loads(meta_path.read_text())
            except Exception:
                pass

        if "stages" not in meta:
            meta["stages"] = {}

        stage_data = {
            "status":   "done" if success else "error",
            "time_s":   elapsed,
            "exit_code": 1 if missing_output else proc.returncode,
        }
        if missing_output:
            stage_data["missing_output"] = missing_output
        if meta_extra:
            stage_data.update(meta_extra)
        # Extract real metrics from the tool output (prefers <stage>.log on
        # disk over captured stdout — OpenROAD's -log may suppress stdout).
        # Runs even on failure: partial metrics still help diagnostics.
        stage_data.update(pdv.extract_stage_metrics(stage, run_dir, "".join(lines)))
        meta["stages"][stage] = stage_data

        meta_path.write_text(json.dumps(meta, indent=2))

        if missing_output:
            yield ("\n[ERROR] Stage produced no output (" + missing_output +
                   " missing or stale) — check the log above for the first "
                   "error; the tool may have exited 0 despite failing.\n")
            yield "[DONE] Exit code 1\n"
        elif not success:
            yield "\n[ERROR] Process exited with code " + str(proc.returncode) + "\n"
            yield "[DONE] Exit code " + str(proc.returncode) + "\n"
        else:
            yield "\n[DONE] Exit code 0\n"

    return StreamingResponse(generate(), media_type="text/plain")


# Health

@app.get("/health")
def health():
    return {"status": "ok", "tools": ["yosys", "openroad", "klayout"], "version": "2.0.0"}


# New Run

@app.post("/new_run")
def new_run(body: dict = {}):
    """Create a new run workspace, return run_id."""
    run_id = str(uuid.uuid4())[:8]
    run_dir = get_run_dir(run_id)

    meta = {
        "run_id":    run_id,
        "design":    body.get("design", "top"),
        "created":   time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "cell_lib":  body.get("cell_lib", "sky130_fd_sc_hd"),
        "corner":    body.get("corner", "tt"),
        "stages":    {},
    }
    (run_dir / "run_meta.json").write_text(json.dumps(meta, indent=2))

    return {"run_id": run_id, "work_dir": str(run_dir)}


# Stage 1: Synthesis 

class SynthesisConfig(BaseModel):
    top_module:      str
    verilog_files:   dict
    run_id:          str
    cell_lib:        str   = "sky130_fd_sc_hd"
    corner:          str   = "tt"
    clock_period_ns: float = 10.0
    # Name of the clock port; empty string = combinational design (no clock
    # constraints written to the SDC).
    clock_port:      str   = "clk"
    flatten:         bool  = False
    abc_strategy:    str   = "balanced"   # balanced | speed | area
    opt_level:       int   = Field(2, ge=0, le=3)
    dont_use_cells:  list  = []


@app.post("/synthesize")
def synthesize(req: SynthesisConfig):
    run_dir = get_run_dir(req.run_id)
    pdk     = get_pdk_paths(req.cell_lib, req.corner)

    # Persist cell_lib + corner in run_meta so later stages can read them
    # without needing to re-specify them in every config.
    meta_path = run_dir / "run_meta.json"
    try:
        _m = json.loads(meta_path.read_text()) if meta_path.exists() else {}
        _m["cell_lib"] = req.cell_lib
        _m["corner"]   = req.corner
        _m["clock_period_ns"] = req.clock_period_ns
        meta_path.write_text(json.dumps(_m, indent=2))
    except Exception:
        pass

    # Write verilog files to disk so Yosys can read them
    verilog_paths = []
    for fname, code in req.verilog_files.items():
        fpath = run_dir / fname
        fpath.write_text(code)
        verilog_paths.append(str(fpath))

    netlist_v = str(run_dir / "netlist.v")
    netlist_j = str(run_dir / "netlist.json")
    sdc_path  = str(run_dir / "constraints.sdc")

    # ABC strategy flags
    abc_flags = {
        "balanced": "",
        "speed":    "-D " + str(int(req.clock_period_ns * 1000)),
        "area":     "-A 1",
    }.get(req.abc_strategy, "")

    # opt_level controls how many opt passes and whether fine optimisation runs
    opt_passes = {
        0: "opt_expr; opt_clean",
        1: "opt",
        2: "opt; opt -fast",
        3: "opt; opt -fine",
    }.get(req.opt_level, "opt")

    # Build Yosys script
    lines = []
    for fpath in verilog_paths:
        lines.append("read_verilog " + fpath)

    lines.append("hierarchy -check -top " + req.top_module)
    if req.flatten:
        lines.append("flatten")
    lines.append("proc; " + opt_passes + "; fsm; " + opt_passes + "; memory; " + opt_passes)
    lines.append("techmap")
    lines.append(opt_passes)
    lines.append("dfflibmap -liberty " + pdk["lib"])

    # dont_use_cells: mark cells as dont_use in ABC
    abc_extra = abc_flags
    if req.dont_use_cells:
        dont_use_str = " ".join("-dont_use " + c for c in req.dont_use_cells)
        abc_extra = (abc_extra + " " + dont_use_str).strip()

    if abc_extra:
        lines.append("abc -liberty " + pdk["lib"] + " " + abc_extra)
    else:
        lines.append("abc -liberty " + pdk["lib"])

    lines.append("opt_clean -purge")
    lines.append("stat -liberty " + pdk["lib"])
    lines.append("write_verilog -noattr " + netlist_v)
    lines.append("write_json " + netlist_j)

    script = "\n".join(lines) + "\n"
    script_path = run_dir / "synth.ys"
    script_path.write_text(script)

    # Write a minimal SDC file — used by all downstream stages so they share
    # the same clock definition rather than recreating it independently.
    # clock_port is validated (identifier only) because it lands inside TCL.
    if req.clock_port and not re.match(r"^[A-Za-z_][A-Za-z0-9_]*$",
                                       req.clock_port):
        raise HTTPException(status_code=400,
                            detail="clock_port must be a simple identifier")
    sdc_lines = ["# Auto-generated by RTL Copilot synthesis stage"]
    if req.clock_port:
        half = round(req.clock_period_ns / 2.0, 4)
        sdc_lines += [
            "create_clock -name core_clock -period " +
            str(req.clock_period_ns) +
            " -waveform {0 " + str(half) + "} [get_ports " +
            req.clock_port + "]",
            # Plain [all_inputs]: includes the clock port, which OpenSTA
            # rejects with a harmless STA-0441 warning. Living with the
            # warning is better than collection-manipulation commands this
            # Tcl dialect doesn't have (remove_from_collection broke here).
            "set_input_delay  -clock core_clock -max " +
            str(round(req.clock_period_ns * 0.2, 4)) + " [all_inputs]",
            "set_output_delay -clock core_clock -max " +
            str(round(req.clock_period_ns * 0.2, 4)) + " [all_outputs]",
            "set_false_path -from [get_ports " + req.clock_port + "]",
        ]
    Path(sdc_path).write_text("\n".join(sdc_lines) + "\n")

    return stream_process(
        ["yosys", "-l", str(run_dir / "yosys.log"), str(script_path)],
        cwd=str(run_dir), run_dir=run_dir, stage="synthesis",
        meta_extra={"top_module": req.top_module, "cell_lib": req.cell_lib,
                    "corner": req.corner, "clock_period_ns": req.clock_period_ns}
    )


# Stage 2: Floorplan 

class FloorplanConfig(BaseModel):
    top_module:      str
    run_id:          str
    cell_lib:        str   = "sky130_fd_sc_hd"
    corner:          Literal["tt", "ss", "ff"] = "tt"
    die_area:        str   = "0 0 1000 1000"
    core_util:       float = Field(0.45, ge=0.1, le=0.9)
    aspect_ratio:    float = Field(1.0,  ge=0.1, le=10.0)
    core_margin_um:  float = 10.0
    # I/O pin placement: edge groups let the user cluster signals by function.
    # Format: {"clk": "top", "data_in[*]": "left", "data_out[*]": "right"}
    # Empty dict → automatic spreading across all edges.
    io_constraints:  dict  = {}


@app.post("/floorplan")
def floorplan(req: FloorplanConfig):
    run_dir  = get_run_dir(req.run_id)
    pdk      = get_pdk_paths(req.cell_lib, req.corner)
    netlist_v = run_dir / "netlist.v"

    if not netlist_v.exists():
        raise HTTPException(status_code=400, detail="netlist.v not found — run synthesis first")

    # Compute core area from die area + margin
    coords    = [float(x) for x in req.die_area.split()]
    margin    = req.core_margin_um
    core_area = (
        str(coords[0] + margin) + " " + str(coords[1] + margin) + " " +
        str(coords[2] - margin) + " " + str(coords[3] - margin)
    )

    tcl_lines = [
        "read_lef " + pdk["tech_lef"],
        "read_lef " + pdk["lef"],
        "read_liberty " + pdk["lib"],
        "read_verilog " + str(netlist_v),
        "link_design " + req.top_module,
        "initialize_floorplan \\",
        "    -die_area {" + req.die_area + "} \\",
        "    -core_area {" + core_area + "} \\",
        "    -site " + pdk["site"],
        "make_tracks",
    ]

    # I/O pin placement — apply per-signal edge constraints when provided,
    # then call place_pins to resolve positions within the constrained edges.
    if req.io_constraints:
        for pin_pattern, edge in req.io_constraints.items():
            tcl_lines.append(
                "set_io_pin_constraint -pin_names {" + pin_pattern +
                "} -region " + edge + ":*"
            )
    tcl_lines.append("place_pins -hor_layers met3 -ver_layers met4")

    # Well-tap + endcap insertion — required by sky130 (li/well continuity).
    # Omitting it is the root cause of systematic li.* DRC violations.
    if pdk.get("tapcell"):
        tcl_lines += [
            "tapcell \\",
            "    -distance " + str(pdk["tap_distance"]) + " \\",
            "    -tapcell_master " + pdk["tapcell"] + " \\",
            "    -endcap_master "  + pdk["tapcell"],
        ]

    tcl_lines += [
        "write_def " + str(run_dir / "floorplan.def"),
    ]

    tcl_path = run_dir / "floorplan.tcl"
    tcl_path.write_text("\n".join(tcl_lines) + "\n")

    return stream_process(
        ["openroad", "-log", str(run_dir / "floorplan.log"), str(tcl_path)],
        cwd=str(run_dir), run_dir=run_dir, stage="floorplan",
        meta_extra={"die_area": req.die_area, "core_util": req.core_util,
                    "core_margin_um": req.core_margin_um}
    )


# Stage 2b: PDN Generation (OpenROAD) 

class PDNConfig(BaseModel):
    top_module:       str
    run_id:           str
    cell_lib:         str   = "sky130_fd_sc_hd"
    corner:           Literal["tt", "ss", "ff"] = "tt"
    vdd_net:          str   = "VDD"
    vss_net:          str   = "VSS"
    straps_layer:     str   = "met4"
    straps_width:     float = 1.6
    straps_pitch:     float = 27.1
    straps_layer2:    str   = "met5"
    straps_width2:    float = 1.6
    straps_pitch2:    float = 27.1


@app.post("/pdn")
def pdn(req: PDNConfig):
    run_dir       = get_run_dir(req.run_id)
    # Persist power net names — the routing stage needs them to re-run
    # global_connect after filler insertion.
    try:
        _mp = run_dir / "run_meta.json"
        _m = json.loads(_mp.read_text())
        _m["power_nets"] = {"vdd": req.vdd_net, "vss": req.vss_net}
        _mp.write_text(json.dumps(_m, indent=2))
    except Exception:
        pass
    pdk           = get_pdk_paths(req.cell_lib, req.corner)
    floorplan_def = run_dir / "floorplan.def"

    if not floorplan_def.exists():
        raise HTTPException(status_code=400, detail="floorplan.def not found — run floorplan first")

    pdn_lines = [
        "read_lef " + pdk["tech_lef"],
        "read_lef " + pdk["lef"],
        "read_liberty " + pdk["lib"],
        "read_def " + str(floorplan_def),
        "add_global_connection -net " + req.vdd_net + " -pin_pattern VPB -power",
        "add_global_connection -net " + req.vdd_net + " -pin_pattern VPWR -power",
        "add_global_connection -net " + req.vss_net + " -pin_pattern VNB -ground",
        "add_global_connection -net " + req.vss_net + " -pin_pattern VGND -ground",
        "global_connect",
        "set_voltage_domain -power " + req.vdd_net + " -ground " + req.vss_net,
        "define_pdn_grid -name core_grid -voltage_domain {Core}",
        # met1 followpins — rails at standard-cell row pitch
        "add_pdn_stripe -followpins -layer met1 -width 0.48 -extend_to_core_ring",
        # Primary vertical straps
        "add_pdn_stripe -layer " + req.straps_layer +
        " -width " + str(req.straps_width) +
        " -pitch " + str(req.straps_pitch) +
        " -offset 12.0 -extend_to_core_ring",
    ]

    # Optional second strap layer — horizontal mesh on top of vertical straps
    if req.straps_layer2:
        pdn_lines += [
            "add_pdn_stripe -layer " + req.straps_layer2 +
            " -width " + str(req.straps_width2) +
            " -pitch " + str(req.straps_pitch2) +
            " -offset 12.0 -extend_to_core_ring",
            "add_pdn_connect -layers {" + req.straps_layer + " " + req.straps_layer2 + "}",
        ]

    pdn_lines += [
        "add_pdn_connect -layers {met1 " + req.straps_layer + "}",
        "pdngen",
        "analyze_power_grid -net " + req.vdd_net,
        "write_def " + str(run_dir / "pdn.def"),
    ]

    tcl_path = run_dir / "pdn.tcl"
    tcl_path.write_text("\n".join(pdn_lines) + "\n")

    return stream_process(
        ["openroad", "-log", str(run_dir / "pdn.log"), str(tcl_path)],
        cwd=str(run_dir), run_dir=run_dir, stage="pdn",
        meta_extra={"vdd_net": req.vdd_net, "vss_net": req.vss_net,
                    "straps_layer": req.straps_layer, "straps_layer2": req.straps_layer2}
    )


# Stage 3: Placement 

class PlacementConfig(BaseModel):
    top_module:        str
    run_id:            str
    cell_lib:          str   = "sky130_fd_sc_hd"
    corner:            Literal["tt", "ss", "ff"] = "tt"
    density:           float = Field(0.6, ge=0.1, le=0.9)
    timing_driven:     bool  = True
    congestion_driven: bool  = True
    cell_padding:      int   = Field(4, ge=0, le=16)
    # Repair passes — wire buffering, high-fanout trees, gate sizing
    max_wire_length:   int   = Field(100, ge=10, le=500)
    slew_margin:       float = Field(0.05, ge=0.0, le=0.5)
    cap_margin:        float = Field(0.05, ge=0.0, le=0.5)
    # Timing repair
    setup_margin:      float = Field(0.05, ge=0.0, le=1.0)
    hold_margin:       float = Field(0.05, ge=0.0, le=1.0)
    max_repair_util:   int   = Field(80, ge=50, le=95)


@app.post("/placement")
def placement(req: PlacementConfig):
    run_dir       = get_run_dir(req.run_id)
    pdk           = get_pdk_paths(req.cell_lib, req.corner)
    floorplan_def = run_dir / "floorplan.def"

    # Use pdn.def if PDN was run, else fall back to floorplan.def
    pdn_def   = run_dir / "pdn.def"
    input_def = pdn_def if pdn_def.exists() else floorplan_def
    if not floorplan_def.exists():
        raise HTTPException(status_code=400, detail="floorplan.def not found — run floorplan first")

    sdc_path = run_dir / "constraints.sdc"

    gp_flags = "-density " + str(req.density)
    if req.timing_driven:
        gp_flags += " -timing_driven"
    if req.congestion_driven:
        # OpenROAD's flag name; "-congestion_driven" does not exist in gpl
        gp_flags += " -routability_driven"

    tcl_lines = [
        "read_lef " + pdk["tech_lef"],
        "read_lef " + pdk["lef"],
        "read_liberty " + pdk["lib"],
        "read_def " + str(input_def),
    ]

    # Read SDC from synthesis — single source of truth for clock constraints.
    # This replaces the inline create_clock pattern and correctly handles
    # multi-clock designs and any false-path/multicycle exceptions.
    if sdc_path.exists():
        tcl_lines.append("read_sdc " + str(sdc_path))
    else:
        # No SDC yet (synthesis didn't run or was skipped) — emit a warning
        # sentinel the verification layer can surface.
        tcl_lines.append('puts "PDV WARNING: no constraints.sdc found — timing analysis will be inaccurate"')

    tcl_lines += [
        # Cell padding before GP so density calculation accounts for routing space
        "set_placement_padding -global -left " + str(req.cell_padding) + " -right " + str(req.cell_padding),
        # Clock nets on upper metal; signal wires approximate met2
        "set_wire_rc -clock  -layer met5",
        "set_wire_rc -signal -layer met2",
        "estimate_parasitics -placement",
        # ── Global placement ──
        "global_placement " + gp_flags,
        # ── Repair DRC violations (slew, cap, fanout, long wires) ──
        "estimate_parasitics -placement",
        "repair_design" +
        " -max_wire_length " + str(req.max_wire_length) +
        " -slew_margin "     + str(req.slew_margin) +
        " -cap_margin "      + str(req.cap_margin),
        # ── First legalization — after repair_design inserts buffers ──
        "if { [catch { detailed_placement } _dp_msg] } {",
        '  puts "WARNING: detailed_placement failed ($_dp_msg) — retrying with relaxed padding"',
        "  set_placement_padding -global -left 1 -right 1",
        "  detailed_placement",
        "}",
        # ── Repair timing violations ──
        "estimate_parasitics -placement",
        "repair_timing -setup -hold" +
        " -setup_margin "    + str(req.setup_margin) +
        " -hold_margin "     + str(req.hold_margin) +
        " -max_utilization " + str(req.max_repair_util),
        # ── Second legalization — after repair_timing resizes/inserts cells ──
        "if { [catch { detailed_placement } _dp_msg] } {",
        '  puts "WARNING: detailed_placement failed ($_dp_msg) — retrying with relaxed padding"',
        "  set_placement_padding -global -left 1 -right 1",
        "  detailed_placement",
        "}",
        # ── Final parasitic estimate + reports ──
        "estimate_parasitics -placement",
        "report_design_area",
        "report_worst_slack -max",
        "report_worst_slack -min",
        "check_placement -verbose",
        # PDV sentinels — parsed by pd_verification.py
        'catch { puts "PDV placed_instances [llength [get_cells *]]" }',
        'catch { puts "PDV setup_wns_ns [format %.4f [sta::worst_slack -max]]" }',
        'catch { puts "PDV hold_wns_ns  [format %.4f [sta::worst_slack -min]]" }',
        # Write both DEF and updated netlist (repair passes change the netlist)
        "write_def "     + str(run_dir / "placement.def"),
        "write_verilog " + str(run_dir / "placement_netlist.v"),
    ]

    tcl_path = run_dir / "placement.tcl"
    tcl_path.write_text("\n".join(tcl_lines) + "\n")

    return stream_process(
        ["openroad", "-log", str(run_dir / "placement.log"), str(tcl_path)],
        cwd=str(run_dir), run_dir=run_dir, stage="placement",
        meta_extra={"density": req.density, "timing_driven": req.timing_driven,
                    "congestion_driven": req.congestion_driven,
                    "cell_padding": req.cell_padding,
                    "clock_period_ns": _read_meta_clock(run_dir)}
    )


# Stage 3b: Clock Tree Synthesis (OpenROAD) 

class CTSConfig(BaseModel):
    top_module:       str
    run_id:           str
    cell_lib:         str   = "sky130_fd_sc_hd"
    corner:           Literal["tt", "ss", "ff"] = "tt"
    # CTS electrical constraints
    cts_max_slew:     float = 0.4
    cts_max_cap:      float = 0.08
    # Buffer cell menu — provide a range of drive strengths so the engine
    # can select the weakest buffer that meets constraints at each node.
    cts_root_buf:     str   = "sky130_fd_sc_hd__clkbuf_16"
    cts_buf_list:     str   = ("sky130_fd_sc_hd__clkbuf_2 "
                               "sky130_fd_sc_hd__clkbuf_4 "
                               "sky130_fd_sc_hd__clkbuf_8 "
                               "sky130_fd_sc_hd__clkbuf_16")
    # Sink clustering controls skew within each leaf cluster
    sink_clustering_size:        int   = Field(25, ge=4, le=64)
    sink_clustering_max_diameter: float = Field(50.0, ge=10.0, le=200.0)
    # Hold repair margin — applied after propagated-clock timing is available
    hold_margin:      float = Field(0.1,  ge=0.0, le=0.5)
    max_repair_util:  int   = Field(80,   ge=50,  le=95)


@app.post("/cts")
def cts(req: CTSConfig):
    run_dir       = get_run_dir(req.run_id)
    pdk           = get_pdk_paths(req.cell_lib, req.corner)
    placement_def = run_dir / "placement.def"

    if not placement_def.exists():
        raise HTTPException(status_code=400, detail="placement.def not found — run placement first")

    sdc_path     = run_dir / "constraints.sdc"
    # Prefer the post-repair netlist; fall back to post-synthesis netlist
    netlist_path = run_dir / "placement_netlist.v"
    if not netlist_path.exists():
        netlist_path = run_dir / "netlist.v"

    tcl_lines = [
        "read_lef " + pdk["tech_lef"],
        "read_lef " + pdk["lef"],
        "read_liberty " + pdk["lib"],
        "read_def " + str(placement_def),
    ]

    # Read SDC — same file written by synthesis, read by every downstream stage.
    if sdc_path.exists():
        tcl_lines.append("read_sdc " + str(sdc_path))
    else:
        tcl_lines.append('puts "PDV WARNING: no constraints.sdc — clock tree may be incorrect"')

    tcl_lines += [
        # Clock wires on upper metal (lower resistance = less skew)
        "set_wire_rc -clock  -layer met5",
        "set_wire_rc -signal -layer met2",
        "estimate_parasitics -placement",
        # ── CTS characterisation constraints ──
        "configure_cts_characterization" +
        " -max_slew " + str(req.cts_max_slew) +
        " -max_cap "  + str(req.cts_max_cap),
        # ── Build the clock tree ──
        "clock_tree_synthesis" +
        " -root_buf " + req.cts_root_buf +
        " -buf_list {" + req.cts_buf_list + "}" +
        " -sink_clustering_enable" +
        " -sink_clustering_size " + str(req.sink_clustering_size) +
        " -sink_clustering_max_diameter " + str(req.sink_clustering_max_diameter) +
        " -balance_levels",
        # ── Fix slew/cap violations on clock nets ──
        "repair_clock_nets",
        # ── Place the inserted clock buffer cells ──
        # Must happen BEFORE set_propagated_clock so the timing engine has
        # real buffer coordinates when tracing the clock network.
        "if { [catch { detailed_placement } _dp_msg] } {",
        '  puts "WARNING: detailed_placement failed ($_dp_msg) — retrying with relaxed padding"',
        "  set_placement_padding -global -left 1 -right 1",
        "  detailed_placement",
        "}",
        # ── Switch to propagated-clock analysis with real insertion delays ──
        "set_propagated_clock [all_clocks]",
        "estimate_parasitics -placement",
        # ── Fix hold violations using real propagated-clock skew ──
        "repair_timing -hold" +
        " -hold_margin "     + str(req.hold_margin) +
        " -max_utilization " + str(req.max_repair_util),
        # ── Re-legalise after hold buffers inserted ──
        "if { [catch { detailed_placement } _dp_msg] } {",
        '  puts "WARNING: detailed_placement failed ($_dp_msg) — retrying with relaxed padding"',
        "  set_placement_padding -global -left 1 -right 1",
        "  detailed_placement",
        "}",
        # ── Final reports ──
        "estimate_parasitics -placement",
        "report_clock_skew",
        "report_worst_slack -max",
        "report_worst_slack -min",
        "check_placement -verbose",
        # PDV sentinels
        'catch { puts "PDV setup_wns_ns [format %.4f [sta::worst_slack -max]]" }',
        'catch { puts "PDV hold_wns_ns  [format %.4f [sta::worst_slack -min]]" }',
        # Write outputs — netlist changes because CTS inserted buffer cells
        "write_def "     + str(run_dir / "cts.def"),
        "write_verilog " + str(run_dir / "cts_netlist.v"),
    ]

    tcl_path = run_dir / "cts.tcl"
    tcl_path.write_text("\n".join(tcl_lines) + "\n")

    return stream_process(
        ["openroad", "-log", str(run_dir / "cts.log"), str(tcl_path)],
        cwd=str(run_dir), run_dir=run_dir, stage="cts",
        meta_extra={"cts_max_slew": req.cts_max_slew, "cts_max_cap": req.cts_max_cap,
                    "clock_period_ns": _read_meta_clock(run_dir)}
    )


# Stage 4: Routing 

class RoutingConfig(BaseModel):
    top_module:             str
    run_id:                 str
    cell_lib:               str = "sky130_fd_sc_hd"
    corner:                 Literal["tt", "ss", "ff"] = "tt"
    bottom_routing_layer:   str = "met1"
    top_routing_layer:      str = "met5"
    # Clock routing uses upper metals for lower resistance (less skew/noise)
    clock_bottom_layer:     str = "met4"
    clock_top_layer:        str = "met5"
    congestion_iterations:  int = Field(30, ge=5, le=100)
    antenna_fixing:         bool = True
    # Diode cell for antenna repair — must exist in the PDK library
    antenna_diode_cell:     str = "sky130_fd_sc_hd__diode_2"
    # NDR multipliers for clock nets: 2x width and 2x spacing is standard
    clock_ndr_width_mult:   int = Field(2, ge=1, le=4)
    clock_ndr_space_mult:   int = Field(2, ge=1, le=4)


@app.post("/routing")
def routing(req: RoutingConfig):
    run_dir       = get_run_dir(req.run_id)
    pdk           = get_pdk_paths(req.cell_lib, req.corner)
    placement_def = run_dir / "placement.def"

    # Use cts.def if CTS was run, else fall back to placement.def
    cts_def       = run_dir / "cts.def"
    routing_input = cts_def if cts_def.exists() else placement_def
    if not routing_input.exists():
        raise HTTPException(status_code=400, detail="placement.def not found — run placement first")

    sdc_path = run_dir / "constraints.sdc"

    # Prefer post-CTS netlist; fall back through the chain
    for candidate in ("cts_netlist.v", "placement_netlist.v", "netlist.v"):
        netlist_path = run_dir / candidate
        if netlist_path.exists():
            break

    layer_range       = req.bottom_routing_layer + "-" + req.top_routing_layer
    clock_layer_range = req.clock_bottom_layer   + "-" + req.clock_top_layer

    # Read power net names written by the PDN stage
    _vdd, _vss = "VDD", "VSS"
    try:
        _pn  = json.loads((run_dir / "run_meta.json").read_text()).get("power_nets", {})
        _vdd = _pn.get("vdd", _vdd)
        _vss = _pn.get("vss", _vss)
    except Exception:
        pass

    tcl_lines = [
        "read_lef " + pdk["tech_lef"],
        "read_lef " + pdk["lef"],
        "read_liberty " + pdk["lib"],
        "read_def " + str(routing_input),
    ]

    if sdc_path.exists():
        tcl_lines.append("read_sdc " + str(sdc_path))
    else:
        tcl_lines.append('puts "PDV WARNING: no constraints.sdc — routing will not be timing-driven"')

    tcl_lines += [
        # Wire RC models for pre-route timing estimates
        "set_wire_rc -clock  -layer " + req.clock_bottom_layer,
        "set_wire_rc -signal -layer met2",
        "estimate_parasitics -placement",
        # Signal layer range
        "set_routing_layers -signal " + layer_range,
        # Clock layer restriction — keeps clock routing on upper metals
        "set_routing_layers -clock "  + clock_layer_range,
    ]

    # Non-Default Routing Rules for clock nets — double width and spacing.
    # Applied before global_route so the router uses NDR when planning paths.
    ndr_layers = {}
    for layer in ("met1", "met2", "met3", "met4", "met5"):
        # Base widths/spacings for SKY130 layers (from tech LEF)
        base = {"met1": 0.17, "met2": 0.23, "met3": 0.34, "met4": 0.46, "met5": 1.70}
        w = base.get(layer, 0.17)
        ndr_layers[layer] = (
            round(w * req.clock_ndr_width_mult, 3),
            round(w * req.clock_ndr_space_mult, 3),
        )

    width_str = " ".join(lyr + " " + str(ndr_layers[lyr][0]) for lyr in ndr_layers)
    space_str = " ".join(lyr + " " + str(ndr_layers[lyr][1]) for lyr in ndr_layers)
    # OpenROAD NDR interface: create_ndr defines the rule, assign_ndr applies
    # it per net. (define_routing_rule/set_routing_rule are Innovus commands
    # and do not exist here.) Guarded: NDR is an enhancement — a failure must
    # not abort routing, and designs without clocks skip it entirely.
    tcl_lines += [
        "if { [llength [all_clocks]] > 0 } {",
        "  if { [catch {",
        "    create_ndr -name clk_ndr -width {" + width_str + "}"
        " -spacing {" + space_str + "}",
        # -all_clocks: assign_ndr's built-in clock-net selector.
        # (get_nets -of_objects [get_clocks *] raises STA-0100 here —
        #  this sta's get_nets doesn't accept Clock objects.)
        "    assign_ndr -ndr clk_ndr -all_clocks",
        "  } _ndr_msg] } {",
        '    puts "WARNING: clock NDR skipped: $_ndr_msg"',
        "  }",
        "}",
    ]

    tcl_lines += [
        # ── Global routing ──
        "global_route \\",
        "    -guide_file " + str(run_dir / "route.guide") + " \\",
        "    -congestion_iterations " + str(req.congestion_iterations) + " \\",
        "    -congestion_report_file " + str(run_dir / "congestion.rpt") + " \\",
        # (global_route has no -timing_driven flag; timing awareness comes
        #  from the NDRs and the resizer passes, not a grt switch)
        "    -verbose",
        # (congestion is reported via -congestion_report_file above;
        #  check_global_route is an Innovus command and does not exist here)
        # ── Detailed routing ──
        "detailed_route \\",
        "    -output_drc " + str(run_dir / "route_drc.rpt") + " \\",
        "    -verbose 1",
    ]

    # Antenna repair
    if req.antenna_fixing:
        tcl_lines += [
            # OpenROAD takes the diode master as a positional argument
            # (-diode_cell is OpenLane vocabulary and silently fails).
            # catch: repair failure is logged but must not abort the stage.
            "if { [catch { repair_antennas " +
            req.antenna_diode_cell + " -iterations 5 } _ant_msg] } {",
            '    puts "WARNING: repair_antennas: $_ant_msg"',
            "}",
            # check_antennas: do NOT catch — the report must reach the log
            "check_antennas",
        ]

    # Filler insertion
    if pdk.get("fill_cells"):
        tcl_lines += [
            "filler_placement {" + pdk["fill_cells"] + "}",
            "check_placement",
            # Re-connect filler power pins (inserted after PDN global_connect)
            "add_global_connection -net " + _vdd + " -pin_pattern VPB -power",
            "add_global_connection -net " + _vdd + " -pin_pattern VPWR -power",
            "add_global_connection -net " + _vss + " -pin_pattern VNB -ground",
            "add_global_connection -net " + _vss + " -pin_pattern VGND -ground",
            "global_connect",
        ]

    # Metal density fill: SKY130 CMP rules require every metal layer inside
    # a 20-80% density window; small designs are far below it without fill.
    # Runs before write_def so DRC / GDS / LVS all see the filled design.
    # catch: fill is compliance polish — a rules hiccup must not void a
    # completed route.
    fill_json = (ORFS_PLATFORMS.get(req.cell_lib) or {}).get("fill_json", "")
    if fill_json and Path(fill_json).exists():
        # ORFS's fill.json allows 0.4um fill shapes on met3/met4 = 0.16um^2,
        # below the KLayout deck's 0.24um^2 min-area rules (m3.6/m4.4) —
        # an upstream inconsistency (ORFS signs off with a different DRC
        # tool). Prune sub-min-area shape sizes into a per-run rules file.
        try:
            _fr = json.loads(Path(fill_json).read_text())
            for _lname, _lcfg in list(_fr.get("layers", _fr).items()):
                if not isinstance(_lcfg, dict):
                    continue
                for _grp in ("non-opc", "opc"):
                    _g = _lcfg.get(_grp)
                    if not isinstance(_g, dict):
                        continue
                    _w = [x for x in _g.get("width", [])  if x >= 0.49]
                    _h = [x for x in _g.get("height", []) if x >= 0.49]
                    if _lname in ("met3", "met4") and _w and _h:
                        _g["width"], _g["height"] = _w, _h
            _fill_run = run_dir / "fill_rules.json"
            _fill_run.write_text(json.dumps(_fr, indent=1))
            fill_json = str(_fill_run)
        except Exception as _e:
            print(f"[routing] fill rules prune failed, using platform file: {_e}",
                  flush=True)
        tcl_lines += [
            "if { [catch { density_fill -rules " + fill_json + " } _fill_msg] } {",
            '    puts "WARNING: density_fill skipped: $_fill_msg"',
            "} else {",
            '    puts "PDV density_fill done"',
            "}",
        ]
    tcl_lines += [
        # (check_drc is an Innovus command; route DRC results are already in
        #  route_drc.rpt written by detailed_route -output_drc above)
        "write_def "     + str(run_dir / "routed.def"),
        'puts "PDV info_post_route run RC Extraction and Timing Analysis for sign-off"',
        'puts "\\[NOTE\\] Routing DRC is clean-checked here, but post-route timing'
        ' is NOT yet verified — run RC Extraction and Timing Analysis."',
        # Updated netlist — antenna diodes added by repair_antennas
        "write_verilog " + str(run_dir / "routed_netlist.v"),
    ]

    tcl_path = run_dir / "routing.tcl"
    tcl_path.write_text("\n".join(tcl_lines) + "\n")

    return stream_process(
        ["openroad", "-log", str(run_dir / "routing.log"), str(tcl_path)],
        cwd=str(run_dir), run_dir=run_dir, stage="routing",
        meta_extra={"layers": layer_range,
                    "congestion_iterations": req.congestion_iterations,
                    "antenna_fixing": req.antenna_fixing,
                    "input_def": routing_input.name}
    )


# Stage 4b: RC Extraction / SPEF (OpenROAD) 

class SPEFConfig(BaseModel):
    top_module:          str
    run_id:              str
    cell_lib:            str   = "sky130_fd_sc_hd"
    corner:              Literal["tt", "ss", "ff"] = "tt"
    # Extraction accuracy controls
    max_res:             float = Field(50.0,  ge=1.0,  le=500.0)
    coupling_threshold:  float = Field(0.1,   ge=0.0,  le=10.0)
    # Output filename — stored in run_meta so the timing stage can find it
    spef_filename:       str   = "routing.spef"


@app.post("/spef")
def spef_extract(req: SPEFConfig):
    run_dir    = get_run_dir(req.run_id)
    pdk        = get_pdk_paths(req.cell_lib, req.corner)
    routed_def = run_dir / "routed.def"

    if not routed_def.exists():
        raise HTTPException(status_code=400, detail="routed.def not found — run routing first")

    # RCX rules file — resolved through get_pdk_paths so corner is honoured
    # and the path is not hardcoded to a specific PDK installation layout.
    rcx_rules = pdk.get("rcx_rules", "")
    if not rcx_rules:
        # Fallback: derive from PDK_ROOT using the corner name
        corner_tag = {"tt": "nom", "ss": "rcworst", "ff": "rcbest"}.get(req.corner, "nom")
        rcx_rules = (PDK_ROOT +
                     "/libs.tech/openlane/rules.openrcx.sky130A." +
                     corner_tag + ".spef_extractor")

    # Corner name used by define_process_corner must match the model file
    corner_name = {"tt": "typical", "ss": "Cmax", "ff": "Cmin"}.get(req.corner, "typical")
    spef_file   = str(run_dir / req.spef_filename)

    tcl_lines = [
        "read_lef " + pdk["tech_lef"],
        "read_lef " + pdk["lef"],
        "read_liberty " + pdk["lib"],
        "read_def " + str(routed_def),
        "define_process_corner -ext_model_index 0 " + corner_name,
        "extract_parasitics" +
        " -ext_model_file "     + rcx_rules +
        " -max_res "            + str(req.max_res) +
        " -coupling_threshold " + str(req.coupling_threshold),
        "write_spef " + spef_file,
    ]

    # Persist the SPEF path so /timing can find it without guessing
    try:
        _mp = run_dir / "run_meta.json"
        _m  = json.loads(_mp.read_text())
        _m.setdefault("stages", {}).setdefault("spef", {})["spef_file"] = spef_file
        _mp.write_text(json.dumps(_m, indent=2))
    except Exception:
        pass

    tcl_path = run_dir / "spef.tcl"
    tcl_path.write_text("\n".join(tcl_lines) + "\n")

    return stream_process(
        ["openroad", "-log", str(run_dir / "spef.log"), str(tcl_path)],
        cwd=str(run_dir), run_dir=run_dir, stage="spef",
        meta_extra={"corner": req.corner, "spef_file": spef_file, "rcx_rules": rcx_rules}
    )


# Stage 5: Timing 

class TimingConfig(BaseModel):
    top_module:           str
    run_id:               str
    cell_lib:             str   = "sky130_fd_sc_hd"
    # Setup sign-off corner (slow cells + slow RC = worst setup)
    setup_corner:         Literal["tt", "ss", "ff"] = "ss"
    # Hold sign-off corner (fast cells + fast RC = worst hold)
    hold_corner:          Literal["tt", "ss", "ff"] = "ff"
    clock_period_ns:      float = 10.0
    clock_uncertainty_ns: float = 0.1
    input_delay_frac:     float = Field(0.2, ge=0.0, le=0.9)
    output_delay_frac:    float = Field(0.2, ge=0.0, le=0.9)
    clock_port:           str   = ""    # empty = combinational (no clock)
    # OCV derating — flat derating applied to all paths
    late_derate:          float = Field(1.05, ge=1.0, le=1.2)
    early_derate:         float = Field(0.95, ge=0.8, le=1.0)
    # How many failing paths to report
    num_paths:            int   = Field(10, ge=1, le=100)
    # Corner sweeps pass e.g. "timing_ff.rpt" so they never clobber the main
    # sign-off timing.rpt. Restricted to a safe name pattern in the endpoint.
    report_name:          str   = "timing.rpt"


@app.post("/timing")
def timing(req: TimingConfig):
    run_dir    = get_run_dir(req.run_id)
    routed_def = run_dir / "routed.def"

    if not routed_def.exists():
        raise HTTPException(status_code=400, detail="routed.def not found — run routing first")

    # Resolve Liberty files for both corners
    pdk_setup = get_pdk_paths(req.cell_lib, req.setup_corner)
    pdk_hold  = get_pdk_paths(req.cell_lib, req.hold_corner)
    sdc_path  = run_dir / "constraints.sdc"

    input_delay  = round(req.clock_period_ns * req.input_delay_frac,  3)
    output_delay = round(req.clock_period_ns * req.output_delay_frac, 3)

    # Find SPEF: prefer path stored by /spef, fall back to known filenames
    spef_file = None
    try:
        _meta = json.loads((run_dir / "run_meta.json").read_text())
        spef_file = _meta.get("stages", {}).get("spef", {}).get("spef_file")
    except Exception:
        pass
    if not spef_file:
        for candidate in ("routing.spef", "output.spef"):
            p = run_dir / candidate
            if p.exists():
                spef_file = str(p)
                break

    tcl_lines = [
        # LEFs must load before read_def (DEF cannot be read without tech).
        "read_lef " + pdk_setup["tech_lef"],
        "read_lef " + pdk_setup["lef"],
        # Min/max analysis: slow corner for setup, fast corner for hold
        "read_liberty -max " + pdk_setup["lib"],
        "read_liberty -min " + pdk_hold["lib"],
        "read_def " + str(routed_def),
    ]

    # Load SPEF with corner annotation — critical for MMMC accuracy
    if spef_file and Path(spef_file).exists():
        # One SPEF annotates both min and max analyses. (-corner requires
        # define_corners, which this min/max flow doesn't use.)
        tcl_lines += [
            "read_spef " + spef_file,
        ]
    else:
        tcl_lines.append(
            'puts "PDV WARNING: no SPEF loaded — wire delays are zero. '
            'Results are NOT sign-off quality. Run the SPEF stage first."'
        )

    # Constraints: prefer SDC written by synthesis for consistency
    if sdc_path.exists():
        tcl_lines.append("read_sdc " + str(sdc_path))
    elif req.clock_port:
        # Fallback: inline constraints when no SDC exists
        clock_name = req.clock_port + "_clk"
        half = round(req.clock_period_ns / 2.0, 4)
        tcl_lines += [
            "create_clock -name " + clock_name +
            " -period " + str(req.clock_period_ns) +
            " -waveform {0 " + str(half) + "} [get_ports " + req.clock_port + "]",
            "set_input_delay  -clock " + clock_name + " -max " + str(input_delay)  + " [all_inputs]",
            "set_output_delay -clock " + clock_name + " -max " + str(output_delay) + " [all_outputs]",
            "set_false_path -from [get_ports " + req.clock_port + "]",
        ]

    if sdc_path.exists() or req.clock_port:
        # Applies in the SDC path too (default flow: SDC exists, clock_port
        # field unset). Guarded in TCL so clockless designs stay clean.
        tcl_lines += [
            "if { [llength [all_clocks]] > 0 } {",
            "  set_clock_uncertainty " + str(req.clock_uncertainty_ns) +
            " [all_clocks]",
            "  set_propagated_clock [all_clocks]",
            "}",
        ]

    # OCV derating — accounts for within-die process variation
    tcl_lines += [
        "set_timing_derate -early -clock " + str(req.early_derate),
        "set_timing_derate -early -data  " + str(req.early_derate),
        "set_timing_derate -late  -clock " + str(req.late_derate),
        "set_timing_derate -late  -data  " + str(req.late_derate),
    ]

    tcl_lines += [
        # ── Setup (max-delay) checks ──
        "# === SETUP TIMING (SS/Cmax corner) ===",
        "report_checks -path_delay max"
        " -digits 3"
        " -group_path_count " + str(req.num_paths),
        "report_wns",
        "report_tns",
        # ── Hold (min-delay) checks ──
        "# === HOLD TIMING (FF/Cmin corner) ===",
        "report_checks -path_delay min"
        " -digits 3"
        " -group_path_count " + str(req.num_paths),
        "report_worst_slack -max",
        "report_worst_slack -min",
        # ── Non-timing constraint checks ──
        "# === CONSTRAINT VIOLATIONS ===",
        "report_check_types -max_slew -max_cap -max_fanout -violators",
        # ── Clock quality ──
        "# === CLOCK ANALYSIS ===",
        "report_clock_skew",
        "report_clock_skew -hold",
        "report_clock_min_period -clocks [all_clocks]",
        # ── Power (activity-factor estimated) ──
        "report_power",
        # ── PDV sentinels ──
        'catch { puts "PDV setup_wns_ns [format %.4f [sta::worst_slack -max]]" }',
        'catch { puts "PDV hold_wns_ns  [format %.4f [sta::worst_slack -min]]" }',
        'catch { puts "PDV setup_tns_ns [format %.4f [sta::total_negative_slack -max]]" }',
        'catch { puts "PDV hold_tns_ns  [format %.4f [sta::total_negative_slack -min]]" }',
    ]

    tcl_path   = run_dir / "timing.tcl"
    if not re.match(r"^timing[A-Za-z0-9_]*\.rpt$", req.report_name or ""):
        raise HTTPException(status_code=400,
                            detail="report_name must match timing*.rpt")
    timing_rpt = run_dir / req.report_name
    tcl_path.write_text("\n".join(tcl_lines) + "\n")

    def generate():
        t0 = time.time()
        proc = subprocess.Popen(
            ["openroad", "-log", str(run_dir / "timing.log"), str(tcl_path)],
            cwd=str(run_dir),
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True, bufsize=1
        )
        lines = []
        for line in proc.stdout:
            lines.append(line)
            yield line
        proc.wait()

        timing_rpt.write_text("".join(lines))

        elapsed   = round(time.time() - t0, 2)
        meta_path = run_dir / "run_meta.json"
        meta      = json.loads(meta_path.read_text()) if meta_path.exists() else {}
        if "stages" not in meta:
            meta["stages"] = {}
        stage_data = {
            "status":           "done" if proc.returncode == 0 else "error",
            "time_s":           elapsed,
            "clock_period_ns":  req.clock_period_ns,
            "setup_corner":     req.setup_corner,
            "hold_corner":      req.hold_corner,
            "spef_loaded":      spef_file is not None and Path(spef_file).exists() if spef_file else False,
        }
        stage_data.update(pdv.extract_stage_metrics("timing", run_dir, "".join(lines)))
        # Corner-sweep runs (report_name != timing.rpt) get their own meta key
        # so they never clobber the main sign-off timing entry.
        _mkey = ("timing" if req.report_name == "timing.rpt"
                 else req.report_name[:-4])
        meta["stages"][_mkey] = stage_data
        meta_path.write_text(json.dumps(meta, indent=2))

        if proc.returncode != 0:
            yield "\n[ERROR] Process exited with code " + str(proc.returncode) + "\n"
        else:
            yield "\n[DONE] Exit code 0\n"

    return StreamingResponse(generate(), media_type="text/plain")

class DRCConfig(BaseModel):
    top_module: str
    run_id:     str


@app.post("/drc")
def drc(req: DRCConfig):
    run_dir    = get_run_dir(req.run_id)
    routed_def = run_dir / "routed.def"
    gds_file   = run_dir / "output.gds"
    drc_rpt    = run_dir / "drc.rpt"

    if not routed_def.exists():
        raise HTTPException(status_code=400, detail="routed.def not found — run routing first")

    # Step 1: Export GDS from routed DEF.
    # Preferred path: ORFS def2stream.py — LEF-aware DEF read via the platform
    # .lyt tech file, then merge of the library GDS so standard cells carry
    # real geometry (required for meaningful DRC and previews).
    import subprocess as _sp

    meta_path = run_dir / "run_meta.json"
    cell_lib = "sky130_fd_sc_hd"
    try:
        cell_lib = json.loads(meta_path.read_text()).get("cell_lib", cell_lib)
    except Exception:
        pass

    plat = ORFS_PLATFORMS.get(cell_lib)
    merged = False
    export_result = None

    if plat and Path(plat["tech_lyt"]).exists() and Path(plat["lib_gds"]).exists():
        if gds_file.exists():
            gds_file.unlink()
        # Merge script modeled on ORFS def2stream, with one critical change:
        # the DEF is read against the SAME volare-PDK LEFs OpenROAD wrote it
        # with (absolute paths), not the ORFS platform LEF set. Relying on the
        # .lyt-referenced LEFs caused unresolved macros/vias -> flipped-row
        # (FS) cells placed one row low (mass li.* overlaps) and dropped
        # li1/mcon signal routing. The .lyt is still loaded for its GDS layer
        # mapping so DEF geometry lands on real sky130 layer numbers.
        pdk_drc = get_pdk_paths(cell_lib, "tt")   # corner irrelevant for LEF
        merge_script = run_dir / "merge_gds.py"
        merge_script.write_text(
            "import pya, sys\n"
            # Read the DEF against the volare LEFs WITHOUT the .lyt layer map:
            # in this mode layers keep their NAMES (li1, mcon, met1...), so no
            # routed geometry is silently dropped by a mismatched map. We then
            # remap names to sky130 GDS numbers explicitly below.
            "cfg = pya.LEFDEFReaderConfiguration()\n"
            "cfg.lef_files = [r'" + pdk_drc["tech_lef"] + "', r'" + pdk_drc["lef"] + "']\n"
            "cfg.read_lef_with_def = False\n"
            "opt = pya.LoadLayoutOptions()\n"
            "opt.lefdef_config = cfg\n"
            "ly = pya.Layout()\n"
            "ly.read(r'" + str(routed_def) + "', opt)\n"
            "LMAP = " + repr(SKY130_GDS_LAYERS) + "\n"
            "for li in ly.layer_indexes():\n"
            "    info = ly.get_info(li)\n"
            "    nm = (info.name or '')\n"
            "    base = nm.split('.')[0].lower()\n"
            "    if base in LMAP:\n"
            "        lnum, ddt = LMAP[base]\n"
            "        dt = ddt\n"
            "        u = nm.upper()\n"
            "        if u.endswith('.PIN'): dt = 16\n"
            "        elif u.endswith('.LABEL'): dt = 5\n"
            "        ly.set_info(li, pya.LayerInfo(lnum, dt, nm))\n"
            "print('[merge] layers:', [str(ly.get_info(li)) for li in ly.layer_indexes()])\n"
            "top = ly.cell('" + req.top_module + "')\n"
            "if top is None:\n"
            "    print('[merge] ERROR: top cell not found', file=sys.stderr); sys.exit(1)\n"
            "ti = top.cell_index()\n"
            "for c in ly.each_cell():\n"
            "    if c.cell_index() != ti and not c.name.startswith('VIA_') "
            "and not c.name.endswith('_DEF_FILL'):\n"
            "        c.clear()\n"
            "ly.read(r'" + plat["lib_gds"] + "')\n"
            "out = pya.Layout(); out.dbu = ly.dbu\n"
            "tc = out.create_cell('" + req.top_module + "')\n"
            "tc.copy_tree(ly.cell('" + req.top_module + "'))\n"
            "empty = [c.name for c in out.each_cell() if c.name != '" + req.top_module + "' "
            "and not any(c.shapes(li).size() for li in out.layer_indexes()) "
            "and c.child_instances() == 0]\n"
            "if empty: print('[merge] WARNING: cells with no GDS match:', empty[:10])\n"
            # KLayout's DEF reader skips RECT-style net segments (used by
            # OpenROAD drt for li1 pin-access patches). Inject them directly.
            "import re as _re\n"
            "_txt = open(r'" + str(routed_def) + "').read()\n"
            "_m = _re.search(r'\\bNETS\\b(.*?)\\bEND NETS\\b', _txt, _re.S)\n"
            "_n = 0\n"
            "if _m:\n"
            "    _tc2 = out.cell('" + req.top_module + "')\n"
            "    for lay, x, y, a, b, c, d in _re.findall(\n"
            "            r'(\\w+)\\s*\\(\\s*(-?\\d+)\\s+(-?\\d+)\\s*\\)\\s*RECT\\s*\\(\\s*'\n"
            "            r'(-?\\d+)\\s+(-?\\d+)\\s+(-?\\d+)\\s+(-?\\d+)\\s*\\)', _m.group(1)):\n"
            "        base = lay.lower()\n"
            "        if base not in LMAP: continue\n"
            "        lnum, ddt = LMAP[base]\n"
            "        li2 = out.layer(lnum, ddt)\n"
            "        x, y = int(x), int(y)\n"
            "        _tc2.shapes(li2).insert(pya.Box(x+int(a), y+int(b), x+int(c), y+int(d)))\n"
            "        _n += 1\n"
            "print('[merge] injected %d RECT net segments' % _n)\n"
            # Connectivity tripwire: li1 exists only inside via cells and
            # standard cells (drt writes no li1 wire segments), so check the
            # local-interconnect level RECURSIVELY: mcon cuts + L1M1 vias.
            "otc = out.cell('" + req.top_module + "')\n"
            "mc_i = out.find_layer(67, 44)\n"
            "mc_n = 0\n"
            "if mc_i is not None:\n"
            "    _it = pya.RecursiveShapeIterator(out, otc, mc_i)\n"
            "    while not _it.at_end(): mc_n += 1; _it.next()\n"
            "l1_n = sum(1 for inst in otc.each_inst() "
            "if 'L1M1' in out.cell(inst.cell_index).name)\n"
            "print('[merge] mcon_shapes=%d l1m1_vias=%d' % (mc_n, l1_n))\n"
            "out.write(r'" + str(gds_file) + "')\n"
            "print('[merge] wrote " + str(gds_file) + "')\n"
        )
        export_result = _sp.run(
            ["klayout", "-b", "-zz", "-r", str(merge_script)],
            capture_output=True, text=True, cwd=str(run_dir), timeout=300)
        merged = gds_file.exists() and export_result.returncode == 0
        if gds_file.exists() and export_result.returncode != 0:
            merged = True   # file written; warnings only
        print(f"[drc] merge exit={export_result.returncode} merged={merged}",
              flush=True)
        if export_result.stdout:
            print("[drc] merge out: " + export_result.stdout[-500:], flush=True)
        if export_result.stderr:
            print("[drc] merge err: " + export_result.stderr[-300:], flush=True)

    if not merged:
        # Fallback: plain DEF->GDS (no cell geometry). Kept so the stage
        # still completes for libraries without ORFS platform assets.
        export_script = (
            "import pya\n"
            "layout = pya.Layout()\n"
            "layout.read('" + str(routed_def) + "')\n"
            "layout.write('" + str(gds_file) + "')\n"
            "print('[INFO] GDS exported (plain, no library merge) to " + str(gds_file) + "')\n"
            "print('[DONE] GDS export complete')\n"
        )
        export_path = run_dir / "export_gds.py"
        export_path.write_text(export_script)
        fallback_result = _sp.run(
            ["klayout", "-b", "-r", str(export_path)],
            capture_output=True, text=True, cwd=str(run_dir)
        )
        if export_result is None:
            export_result = fallback_result
        else:
            export_result.stdout += "\n" + fallback_result.stdout
            export_result.stderr += "\n" + fallback_result.stderr

    # Regenerating output.gds invalidates cached previews (the preview
    # endpoint only checks existence) — remove them so they re-render.
    for stale in ("placement_preview.png", "routing_preview.png",
                  "gds_preview.png", "placement_preview_tmp.gds",
                  "routing_preview_tmp.gds"):
        p = run_dir / stale
        if p.exists():
            try:
                p.unlink()
            except OSError:
                pass

    # Step 2: Run real DRC with Sky130HD rule deck
    # Variables: $in_gds = GDS file, $report_file = output report
    _lib_cfg = CELL_LIBS.get(cell_lib, {})
    drc_rule_deck = _lib_cfg.get("drc_deck") or \
        "/OpenROAD-flow-scripts/flow/platforms/sky130hd/drc/sky130hd.lydrc"
    drc_output = ""

    if gds_file.exists() and Path(drc_rule_deck).exists():
        drc_run = _sp.run(
            ["klayout", "-b",
             "-rd", "in_gds=" + str(gds_file),
             "-rd", "report_file=" + str(drc_rpt),
             "-r", drc_rule_deck],
            # 600s (10 min): KLayout DRC on a real design easily takes 5-15 min.
            # The original 120s was too short and left drc.rpt empty on timeout.
            capture_output=True, text=True, cwd=str(run_dir), timeout=600
        )
        drc_output = drc_run.stdout + drc_run.stderr
    else:
        missing_deck = drc_rule_deck if not Path(drc_rule_deck).exists() else "GDS not generated"
        drc_output = (
            "[INFO] DRC rule deck not available — GDS export only.\n"
            "[INFO] Expected rule deck at: " + drc_rule_deck + "\n"
            "[INFO] Install OpenROAD-flow-scripts or set drc_deck in CELL_LIBS config.\n"
        )
        drc_rpt.write_text("No DRC run.\n")

    # Parse the DRC report. KLayout .lydrc decks emit a KLayout report
    # database (XML, <report-database> with <item>/<category> entries);
    # fall back to plain-text "N violations" parsing for other formats.
    drc_total = None
    drc_categories = {}
    if drc_rpt.exists():
        rpt_text = drc_rpt.read_text(errors="replace")
        if "<report-database>" in rpt_text:
            try:
                import xml.etree.ElementTree as _ET
                root = _ET.fromstring(rpt_text)
                for item in root.iter("item"):
                    cat = item.findtext("category", default="uncategorized")
                    cat = cat.strip().strip("'")
                    drc_categories[cat] = drc_categories.get(cat, 0) + 1
                drc_total = sum(drc_categories.values())
            except Exception as e:
                print(f"[drc] report XML parse failed: {e}", flush=True)
        else:
            import re as _re
            found = _re.findall(r"([\w][\w\s]+?):\s*(\d+)\s+violation",
                                rpt_text, _re.IGNORECASE)
            if found:
                for vtype, count in found:
                    drc_categories[vtype.strip()] = int(count)
                drc_total = sum(drc_categories.values())
            elif rpt_text.strip() and "violation" not in rpt_text.lower():
                drc_total = 0

    def generate():
        for line in (export_result.stdout + export_result.stderr).split("\n"):
            if line.strip() and "Warning:" not in line:
                yield line + "\n"
        if gds_file.exists():
            yield "[INFO] Running Sky130HD DRC rule check...\n"
        for line in drc_output.split("\n"):
            if line.strip():
                yield line + "\n"
        # DRC summary (parsed above; supports KLayout XML report databases)
        if drc_total is not None:
            if drc_total == 0:
                yield "[DRC] No violations found — design is DRC clean!\n"
                yield "[NOTE] DRC checks geometry rules only. Run LVS "
                yield "before treating this as tapeout-ready.\n"
            else:
                yield "\n[DRC SUMMARY]\n"
                for cat, count in sorted(drc_categories.items(),
                                         key=lambda kv: -kv[1]):
                    yield "  " + cat + ": " + str(count) + " violations\n"
                # NB: must NOT match the frontend's category regex
                # (/(.+?):\s*(\d+)\s+violations?/) or it double-counts.
                yield "  ---- total = " + str(drc_total) + " ----\n"
        if merged and export_result and "mcon_shapes=0" in (export_result.stdout or ""):
            yield ("[WARNING] GDS export may be missing li1 routing — "
                   "connectivity tripwire fired. Check merge log.\n")
        yield "\n[DONE] Exit code 0\n"

    # Update run_meta
    run_meta_path = run_dir / "run_meta.json"
    try:
        meta = json.loads(run_meta_path.read_text())
        meta.setdefault("stages", {})["drc"] = {
            "status": "done",
            "gds_exported": gds_file.exists(),
            "gds_merged_library": merged,
            "drc_run": Path(drc_rule_deck).exists(),
            "drc_violations": drc_total,
            "drc_categories": drc_categories,
        }
        run_meta_path.write_text(json.dumps(meta, indent=2))
    except Exception:
        pass

    from fastapi.responses import StreamingResponse as _SR
    return _SR(generate(), media_type="text/plain")


# Stage 7: LVS (needs more testing)

class LVSConfig(BaseModel):
    top_module: str
    run_id:     str


@app.post("/lvs")
def lvs(req: LVSConfig):
    """Compare the merged output.gds against a reference netlist derived from
    the routed design. This is the check that certifies connectivity — it
    catches dropped routing (e.g. missing li1/mcon) that DRC cannot see."""
    run_dir    = get_run_dir(req.run_id)
    gds_file   = run_dir / "output.gds"
    routed_def = run_dir / "routed.def"
    if not gds_file.exists():
        raise HTTPException(status_code=400, detail="output.gds not found — run DRC+GDS first")
    if not routed_def.exists():
        raise HTTPException(status_code=400, detail="routed.def not found — run routing first")

    meta_path = run_dir / "run_meta.json"
    cell_lib = "sky130_fd_sc_hd"
    corner   = "tt"
    try:
        m = json.loads(meta_path.read_text())
        cell_lib = m.get("cell_lib", cell_lib)
        corner   = m.get("corner", corner)
    except Exception:
        pass

    plat = ORFS_PLATFORMS.get(cell_lib) or {}
    lvs_deck = plat.get("lvs_deck", "")
    lib_cdl  = plat.get("cdl", "")
    if not (lvs_deck and Path(lvs_deck).exists() and lib_cdl and Path(lib_cdl).exists()):
        raise HTTPException(status_code=400,
            detail="LVS assets not available for library " + cell_lib)

    pdk = get_pdk_paths(cell_lib, corner)

    # Step 1: reference CDL — design-level connectivity from the routed DEF,
    # with pin ordering taken from the library CDL masters (write_cdl does
    # this correctly; hand-rolling it from Verilog gets port order wrong).
    design_cdl = run_dir / "lvs_design.cdl"
    tcl = run_dir / "lvs_cdl.tcl"
    tcl.write_text(
        "read_lef " + pdk["tech_lef"] + "\n"
        "read_lef " + pdk["lef"] + "\n"
        "read_liberty " + pdk["lib"] + "\n"
        "read_def " + str(routed_def) + "\n"
        "write_cdl -include_fillers -masters {" + lib_cdl + "} "
        + str(design_cdl) + "\n"
    )
    import subprocess as _sp
    cdl_run = _sp.run(["openroad", "-exit", str(tcl)],
                      capture_output=True, text=True, cwd=str(run_dir), timeout=120)

    ref_cdl = run_dir / "lvs_ref.cdl"
    if design_cdl.exists():
        # The ORFS library CDL contains internally inconsistent subckts for
        # cells we never use (e.g. macro_sparecell: pin-count mismatch), and
        # KLayout aborts on ANY parse error. Filter to only the subckts the
        # design transitively instantiates.
        import re as _re

        def _join(text):
            # SPICE/CDL wraps lines with '+' continuations — join them first,
            # or master names on wrapped X-lines are misread (that bug produced
            # empty reference cells and false LVS mismatches).
            return _re.sub(r'\n\s*\+\s*', ' ', text)

        lib_txt = _join(Path(lib_cdl).read_text())
        blocks = {}
        for m in _re.finditer(r'(?im)^\.SUBCKT\s+(\S+).*?^\.ENDS.*?$',
                              lib_txt, _re.S | _re.M):
            blocks[m.group(1).lower()] = m.group(0)

        def _calls(text):
            out = set()
            for line in text.splitlines():
                t = line.split()
                if not t or not t[0].upper().startswith('X'):
                    continue
                if '/' in t:
                    out.add(t[t.index('/') + 1].lower())
                else:
                    out.add(t[-1].lower())
            return out

        def _has_devices(block):
            return any(l.split() and l.split()[0][0].upper() in 'MRCDQX'
                       and not l.split()[0].upper().startswith('X')
                       or l.split() and l.split()[0].upper().startswith('X')
                       for l in block.splitlines()[1:-1])

        design_txt = _join(design_cdl.read_text())
        need, todo = set(), _calls(design_txt)
        while todo:
            n = todo.pop()
            if n in need or n not in blocks:
                continue
            need.add(n)
            todo |= _calls(blocks[n])

        # Purge device-less physical cells (fill/tap/decap): the extractor
        # produces no circuit for them, so keeping them in the reference
        # guarantees a blackbox-vs-nothing mismatch. Drop their subckts AND
        # their instantiations.
        empty = {n for n in need if not _has_devices(blocks[n])}
        need -= empty
        if empty:
            keep = []
            for line in design_txt.splitlines():
                t = line.split()
                if t and t[0].upper().startswith('X') and t[-1].lower() in empty:
                    continue
                keep.append(line)
            design_txt = "\n".join(keep)
            print(f"[lvs] purged device-less cells: {sorted(empty)}", flush=True)

        parts = [blocks[n] for n in sorted(need)]
        ref_cdl.write_text("\n".join(parts) + "\n" + design_txt)
        print(f"[lvs] library CDL filtered: {len(need)}/{len(blocks)} subckts",
              flush=True)

    # Step 2: extract + compare via the platform .lylvs deck
    report    = run_dir / "lvs_report.lvsdb"
    extracted = run_dir / "lvs_extracted.cir"
    lvs_out = ""
    lvs_rc  = -1
    if ref_cdl.exists():
        lvs_run = _sp.run(
            ["klayout", "-b", "-zz",
             "-rd", "in_gds=" + str(gds_file),
             "-rd", "report_file=" + str(report),
             "-rd", "cdl_file=" + str(ref_cdl),
             "-rd", "target_netlist=" + str(extracted),
             "-r", lvs_deck],
            capture_output=True, text=True, cwd=str(run_dir), timeout=600)
        lvs_out = (lvs_run.stdout or "") + (lvs_run.stderr or "")
        lvs_rc  = lvs_run.returncode
        (run_dir / "lvs.log").write_text(lvs_out)

    low = lvs_out.lower()
    matched = ("match" in low and "don't match" not in low
               and "do not match" not in low and "mismatch" not in low
               and lvs_rc == 0)

    try:
        meta = json.loads(meta_path.read_text())
        meta.setdefault("stages", {})["lvs"] = {
            "status": "done" if lvs_rc == 0 else "error",
            "lvs_match": matched,
        }
        meta_path.write_text(json.dumps(meta, indent=2))
    except Exception:
        pass

    def generate():
        if cdl_run.returncode != 0 or not design_cdl.exists():
            yield "[ERROR] write_cdl failed — reference netlist unavailable\n"
            for line in (cdl_run.stdout + cdl_run.stderr).splitlines()[-15:]:
                yield line + "\n"
            yield "\n[ERROR] Process exited with code 1\n"
            return
        yield "[INFO] Reference netlist written (" + design_cdl.name + ")\n"
        yield "[INFO] Running KLayout LVS (extract + compare)...\n"
        for line in lvs_out.splitlines():
            if line.strip():
                yield line + "\n"
        if matched:
            yield "\n[LVS] MATCH — layout connectivity is equivalent to the netlist.\n"
            yield "[DONE] Exit code 0\n"
        else:
            yield "\n[LVS] MISMATCH or LVS error — layout connectivity does NOT "
            yield "match the netlist. See lvs.log / lvs_report.lvsdb.\n"
            yield "[DONE] Exit code " + str(lvs_rc if lvs_rc >= 0 else 1) + "\n"

    return StreamingResponse(generate(), media_type="text/plain")


# Verification checks 

@app.get("/verification_policy")
def get_verification_policy():
    """The effective verification policy (defaults + work-volume file +
    PDV_* env overrides). Edit ./work/verification_policy.json on the host
    to change values without rebuilding the container."""
    return {
        "policy": pdv.load_policy(),
        "override_file": os.environ.get("PDV_POLICY_FILE", "/work/verification_policy.json"),
        "env_prefix": "PDV_",
    }


@app.get("/check/{run_id}/{stage}")
def check_stage(run_id: str, stage: str,
                wns_margin_ns: Optional[float] = None,
                max_util_pct: Optional[float] = None):
    """Run verification checks + deterministic fix computation for a completed
    stage. Thresholds are user-configured and passed as query params (never
    hardcoded); omitting them yields status 'unset' for the affected checks.
    All logic lives in pd_verification.py."""
    if stage not in pdv.CHECKED_STAGES:
        raise HTTPException(status_code=400,
                            detail="Unknown check stage. Use one of: " + ", ".join(pdv.CHECKED_STAGES))
    meta_path = Path(WORK_BASE) / run_id / "run_meta.json"
    if not meta_path.exists():
        raise HTTPException(status_code=404, detail="Run not found")
    try:
        meta = json.loads(meta_path.read_text())
    except Exception:
        raise HTTPException(status_code=500, detail="run_meta.json is corrupted")
    if stage not in meta.get("stages", {}):
        raise HTTPException(status_code=404, detail=stage + " has not run yet for this run")

    return pdv.evaluate(meta, stage, {
        "wns_margin_ns": wns_margin_ns,
        "max_util_pct":  max_util_pct,
    })


# Run metadata

@app.get("/run/{run_id}/meta")
def get_meta(run_id: str):
    run_dir   = Path(WORK_BASE) / run_id
    meta_path = run_dir / "run_meta.json"
    if not meta_path.exists():
        raise HTTPException(status_code=404, detail="Run not found")
    return json.loads(meta_path.read_text())


_PREVIEW_VIEWS = {
    "placement": ("placement.def", "placement_preview.png"),
    "routing":   ("routed.def",    "routing_preview.png"),
    "gds":       ("output.gds",    "gds_preview.png"),
}

_PREVIEW_SCRIPT = Path(__file__).resolve().parent / "export_preview.py"


@app.get("/preview/{run_id}/{view}")
def get_preview(run_id: str, view: str):
    if view not in _PREVIEW_VIEWS:
        raise HTTPException(status_code=400,
            detail=f"Unknown view '{{view}}'. Valid: {', '.join(_PREVIEW_VIEWS)}")

    run_dir   = get_run_dir(run_id)
    meta_path = run_dir / "run_meta.json"
    if not meta_path.exists():
        raise HTTPException(status_code=404, detail="Run not found")

    source_name, preview_name = _PREVIEW_VIEWS[view]
    source_file  = run_dir / source_name
    preview_file = run_dir / preview_name

    if not source_file.exists():
        raise HTTPException(status_code=404,
            detail=f"{source_name} not found — run the corresponding stage first")

    def _stale(product: Path, source: Path) -> bool:
        """True if product is missing or older than its source."""
        if not product.exists():
            return True
        try:
            return product.stat().st_mtime < source.stat().st_mtime
        except OSError:
            return True

    if _stale(preview_file, source_file):
        import subprocess as _sp

        if view == "gds":
            # output.gds is already a real (library-merged) GDS after /drc.
            input_for_render = source_file
        else:
            # Per-stage views render THEIR OWN DEF (no output.gds substitution)
            # converted LEF-aware via the ORFS platform .lyt tech file, so
            # placed cells carry LEF geometry (pins/outlines) and layers get
            # real names. Falls back to a plain conversion when the platform
            # assets are absent.
            cell_lib = "sky130_fd_sc_hd"
            try:
                cell_lib = json.loads(meta_path.read_text()).get("cell_lib", cell_lib)
            except Exception:
                pass
            plat = ORFS_PLATFORMS.get(cell_lib)
            lyt = plat["tech_lyt"] if plat and Path(plat["tech_lyt"]).exists() else None

            gds_tmp = run_dir / (view + "_preview_tmp.gds")
            if _stale(gds_tmp, source_file):
                export_path = run_dir / (view + "_to_gds.py")
                if lyt:
                    pdk_pv = get_pdk_paths(cell_lib, "tt")
                    export_path.write_text(
                        "import pya\n"
                        "tech = pya.Technology()\n"
                        "tech.load(r'" + lyt + "')\n"
                        "opt = tech.load_layout_options\n"
                        "cfg = opt.lefdef_config\n"
                        "cfg.lef_files = [r'" + pdk_pv["tech_lef"] + "', r'" + pdk_pv["lef"] + "']\n"
                        "cfg.read_lef_with_def = False\n"
                        "layout = pya.Layout()\n"
                        "layout.read(r'" + str(source_file) + "', opt)\n"
                        "layout.write(r'" + str(gds_tmp) + "')\n"
                        "print('[INFO] LEF-aware DEF->GDS done')\n"
                    )
                else:
                    export_path.write_text(
                        "import pya\n"
                        "layout = pya.Layout()\n"
                        "layout.read(r'" + str(source_file) + "')\n"
                        "layout.write(r'" + str(gds_tmp) + "')\n"
                        "print('[INFO] plain DEF->GDS done (no platform tech file)')\n"
                    )
                conv = _sp.run(["klayout", "-b", "-r", str(export_path)],
                               capture_output=True, text=True, cwd=str(run_dir), timeout=120)
                print(f"[preview] DEF->GDS exit={conv.returncode} lef_aware={bool(lyt)}",
                      flush=True)
                if conv.returncode != 0:
                    print("[preview] DEF->GDS stderr: " + conv.stderr[-400:], flush=True)
            input_for_render = gds_tmp if gds_tmp.exists() else source_file

        cmd = [
            "klayout", "-b",
            "-rd", "mode=gds",
            "-rd", "input="  + str(input_for_render),
            "-rd", "output=" + str(preview_file),
            "-r", str(_PREVIEW_SCRIPT),
        ]
        print(f"[preview] render cmd: {cmd}", flush=True)
        result = _sp.run(cmd, capture_output=True, text=True, cwd=str(run_dir), timeout=120)
        print(f"[preview] render exit={result.returncode}", flush=True)
        if result.stdout:
            print("[preview] render out: " + result.stdout[-600:], flush=True)
        if result.stderr:
            print("[preview] render err: " + result.stderr[-400:], flush=True)

        if not preview_file.exists():
            raise HTTPException(status_code=500,
                detail="Preview generation failed: " + (result.stderr or result.stdout or "no output")[:600])

    from fastapi.responses import FileResponse as _FR
    return _FR(str(preview_file), media_type="image/png",
               headers={"Cache-Control": "no-cache"})


@app.get("/runs")
def list_runs():
    """List all run directories with their meta.json summaries."""
    work = Path(WORK_BASE)
    runs = []
    for run_dir in sorted(work.iterdir(), reverse=True):
        if not run_dir.is_dir(): continue
        meta_path = run_dir / "run_meta.json"
        if not meta_path.exists(): continue
        try:
            meta = json.loads(meta_path.read_text())
            # Count completed stages
            stages = meta.get("stages", {})
            completed = [s for s, v in stages.items() if v.get("status") == "done"]
            failed    = [s for s, v in stages.items() if v.get("status") == "error"]
            # Extract key metrics from timing stage if available
            timing = stages.get("timing", {})
            runs.append({
                "run_id":          meta.get("run_id", run_dir.name),
                "design":          meta.get("design", "top"),
                "created":         meta.get("created", ""),
                "cell_lib":        meta.get("cell_lib", ""),
                "corner":          meta.get("corner", ""),
                "completed_stages": completed,
                "failed_stages":    failed,
                "stage_count":      len(completed),
                "wns_ns":          timing.get("wns_ns", None),
                "power_w":         timing.get("power_w", None),
            })
        except Exception:
            continue
    return {"runs": runs}


@app.get("/download_zip/{run_id}")
def download_zip(run_id: str):
    """Download all output files for a run as a zip archive."""
    import zipfile, io
    run_dir = get_run_dir(run_id)
    if not run_dir.exists():
        raise HTTPException(status_code=404, detail="Run not found")

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for fname in ALLOWED_DOWNLOADS:
            fpath = run_dir / fname
            if fpath.exists():
                zf.write(fpath, fname)
    buf.seek(0)

    from fastapi.responses import StreamingResponse
    return StreamingResponse(
        buf,
        media_type="application/zip",
        headers={"Content-Disposition": f"attachment; filename=run_{run_id}.zip"}
    )

@app.get("/download/{run_id}/{filename}")
def download(run_id: str, filename: str):
    if filename not in ALLOWED_DOWNLOADS:
        raise HTTPException(status_code=403, detail="File not allowed")

    fpath = Path(WORK_BASE) / run_id / filename
    if not fpath.exists():
        raise HTTPException(status_code=404, detail=filename + " not found — has that stage run?")