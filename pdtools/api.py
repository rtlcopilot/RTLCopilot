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
from pathlib import Path
from fastapi import FastAPI, HTTPException
from fastapi.responses import StreamingResponse, FileResponse
from pydantic import BaseModel, Field
from typing import Optional
from jinja2 import Environment, FileSystemLoader

app = FastAPI(title="RTL Copilot PD Tools", version="2.0.0")

# ── Paths ──────────────────────────────────────────────────────────────────────
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
    },
    "sky130_fd_sc_hs": {
        "site":    "unithhs",
        "lib_tt":  "sky130_fd_sc_hs__tt_025C_1v80.lib",
        "lib_ss":  "sky130_fd_sc_hs__ss_100C_1v60.lib",
        "lib_ff":  "sky130_fd_sc_hs__ff_n40C_1v95.lib",
        "lef":     "sky130_fd_sc_hs.lef",
        "tlef":    "sky130_fd_sc_hs__nom.tlef",
    },
    "sky130_fd_sc_ms": {
        "site":    "unithdms",
        "lib_tt":  "sky130_fd_sc_ms__tt_025C_1v80.lib",
        "lib_ss":  "sky130_fd_sc_ms__ss_100C_1v60.lib",
        "lib_ff":  "sky130_fd_sc_ms__ff_n40C_1v95.lib",
        "lef":     "sky130_fd_sc_ms.lef",
        "tlef":    "sky130_fd_sc_ms__nom.tlef",
    },
}

CORNERS = {"tt": "lib_tt", "ss": "lib_ss", "ff": "lib_ff"}

# Files that can be downloaded
ALLOWED_DOWNLOADS = {
    "netlist.v", "yosys.log",
    "floorplan.def", "pdn.def", "placement.def",
    "cts.def", "routed.def",
    "output.spef", "route_drc.rpt",
    "timing.rpt", "drc.rpt", "output.gds",
    "run_meta.json",
}


# ── Helpers ────────────────────────────────────────────────────────────────────

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

    return {
        "lib":      base + "/lib/" + lib_cfg[corner_key],
        "lef":      base + "/lef/" + lib_cfg["lef"],
        "tech_lef": tech + "/techlef/" + lib_cfg["tlef"],
        "site":     lib_cfg["site"],
    }


def render_template(name: str, ctx: dict) -> str:
    """Render a Jinja2 template from /app/templates/."""
    env = Environment(loader=FileSystemLoader(TEMPLATES), trim_blocks=True, lstrip_blocks=True)
    return env.get_template(name).render(**ctx)


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
            "exit_code": proc.returncode,
        }
        if meta_extra:
            stage_data.update(meta_extra)
        # Save timing metrics into run_meta for run history
        if stage == "timing" and success:
            import re as _re_m
            full_out = "\n".join(lines)
            wns_m   = _re_m.search(r"wns\s+(?:max\s+)?([\-\d\.]+)", full_out, _re_m.IGNORECASE)
            slack_m = _re_m.search(r"([\d\.]+)\s+slack \(MET\)", full_out)
            power_m = _re_m.search(r"Total\s+[\d\.e\+\-]+\s+[\d\.e\+\-]+\s+[\d\.e\+\-]+\s+([\d\.e\+\-]+)", full_out)
            cells_m = _re_m.search(r"(\d+)\s+138\.\d+\s+cells", full_out)
            if wns_m:   stage_data["wns_ns"]   = wns_m.group(1)
            if slack_m: stage_data["slack_ns"] = slack_m.group(1)
            if power_m: stage_data["power_w"]  = power_m.group(1)
            if cells_m: stage_data["cell_count"] = cells_m.group(1)
        meta["stages"][stage] = stage_data

        meta_path.write_text(json.dumps(meta, indent=2))

        if not success:
            yield "\n[ERROR] Process exited with code " + str(proc.returncode) + "\n"
        else:
            yield "\n[DONE] Exit code 0\n"

    return StreamingResponse(generate(), media_type="text/plain")


# ── Health ─────────────────────────────────────────────────────────────────────

@app.get("/health")
def health():
    return {"status": "ok", "tools": ["yosys", "openroad", "klayout"], "version": "2.0.0"}


# ── New Run ────────────────────────────────────────────────────────────────────

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


# ── Stage 1: Synthesis ─────────────────────────────────────────────────────────

class SynthesisConfig(BaseModel):
    top_module:      str
    verilog_files:   dict
    run_id:          str
    cell_lib:        str   = "sky130_fd_sc_hd"
    corner:          str   = "tt"
    clock_period_ns: float = 10.0
    flatten:         bool  = False
    abc_strategy:    str   = "balanced"   # balanced | speed | area
    opt_level:       int   = Field(2, ge=0, le=3)
    dont_use_cells:  list  = []


@app.post("/synthesize")
def synthesize(req: SynthesisConfig):
    run_dir = get_run_dir(req.run_id)
    pdk     = get_pdk_paths(req.cell_lib, req.corner)

    # Write verilog files
    verilog_paths = []
    for fname, code in req.verilog_files.items():
        fpath = run_dir / fname
        fpath.write_text(code)
        verilog_paths.append(str(fpath))

    netlist_v = str(run_dir / "netlist.v")
    netlist_j = str(run_dir / "netlist.json")

    # ABC strategy flags
    abc_flags = {
        "balanced": "",
        "speed":    "-D " + str(int(req.clock_period_ns * 1000)),
        "area":     "-A 1",
    }.get(req.abc_strategy, "")

    # Build Yosys script
    lines = []
    for p in verilog_paths:
        lines.append("read_verilog " + p)
    lines.append("hierarchy -check -top " + req.top_module)
    if req.flatten:
        lines.append("flatten")
    lines.append("proc; opt; fsm; opt; memory; opt")
    lines.append("techmap")
    lines.append("opt")
    lines.append("dfflibmap -liberty " + pdk["lib"])
    if abc_flags:
        lines.append("abc -liberty " + pdk["lib"] + " " + abc_flags)
    else:
        lines.append("abc -liberty " + pdk["lib"])
    lines.append("opt_clean -purge")
    lines.append("stat -liberty " + pdk["lib"])
    lines.append("write_verilog -noattr " + netlist_v)
    lines.append("write_json " + netlist_j)

    script = "\n".join(lines) + "\n"
    script_path = run_dir / "synth.ys"
    script_path.write_text(script)

    return stream_process(
        ["yosys", "-l", str(run_dir / "yosys.log"), str(script_path)],
        cwd=str(run_dir), run_dir=run_dir, stage="synthesis",
        meta_extra={"top_module": req.top_module, "cell_lib": req.cell_lib, "corner": req.corner}
    )


# ── Stage 2: Floorplan ─────────────────────────────────────────────────────────

class FloorplanConfig(BaseModel):
    top_module:      str
    run_id:          str
    cell_lib:        str   = "sky130_fd_sc_hd"
    corner:          str   = "tt"
    die_area:        str   = "0 0 1000 1000"
    core_util:       float = Field(0.45, ge=0.1, le=0.9)
    aspect_ratio:    float = Field(1.0,  ge=0.1, le=10.0)
    pin_placement:   str   = "random"    # random | edge | annealing
    core_margin_um:  float = 10.0


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
        "place_pins -hor_layers met1 -ver_layers met2",
        "write_def " + str(run_dir / "floorplan.def"),
    ]

    tcl_path = run_dir / "floorplan.tcl"
    tcl_path.write_text("\n".join(tcl_lines) + "\n")

    return stream_process(
        ["openroad", str(tcl_path)],
        cwd=str(run_dir), run_dir=run_dir, stage="floorplan",
        meta_extra={"die_area": req.die_area, "core_util": req.core_util}
    )



# ── Stage 2b: PDN Generation (OpenROAD) ──────────────────────────────────────

class PDNConfig(BaseModel):
    top_module:       str
    run_id:           str
    cell_lib:         str   = "sky130_fd_sc_hd"
    corner:           str   = "tt"
    vdd_net:          str   = "VDD"
    vss_net:          str   = "VSS"
    straps_layer:     str   = "met4"
    straps_width:     float = 1.6
    straps_pitch:     float = 27.1


@app.post("/pdn")
def pdn(req: PDNConfig):
    run_dir       = get_run_dir(req.run_id)
    pdk           = get_pdk_paths(req.cell_lib, req.corner)
    floorplan_def = run_dir / "floorplan.def"

    if not floorplan_def.exists():
        raise HTTPException(status_code=400, detail="floorplan.def not found — run floorplan first")

    tcl = (
        "read_lef " + pdk["tech_lef"] + "\n"
        "read_lef " + pdk["lef"] + "\n"
        "read_liberty " + pdk["lib"] + "\n"
        "read_def " + str(floorplan_def) + "\n"
        "add_global_connection -net " + req.vdd_net + " -pin_pattern VPB -power\n"
        "add_global_connection -net " + req.vdd_net + " -pin_pattern VPWR -power\n"
        "add_global_connection -net " + req.vss_net + " -pin_pattern VNB -ground\n"
        "add_global_connection -net " + req.vss_net + " -pin_pattern VGND -ground\n"
        "global_connect\n"
        "set_voltage_domain -power " + req.vdd_net + " -ground " + req.vss_net + "\n"
        "define_pdn_grid -name core_grid -voltage_domain {Core}\n"
        "add_pdn_stripe -followpins -layer met1 -width 0.48 -extend_to_core_ring\n"
        "add_pdn_stripe -layer " + req.straps_layer + " "
        "-width " + str(req.straps_width) + " "
        "-pitch " + str(req.straps_pitch) + " "
        "-offset 12.0 -extend_to_core_ring\n"
        "add_pdn_connect -layers {met1 " + req.straps_layer + "}\n"
        "pdngen\n"
        "write_def " + str(run_dir / "pdn.def") + "\n"
    )

    tcl_path = run_dir / "pdn.tcl"
    tcl_path.write_text(tcl)

    return stream_process(
        ["openroad", str(tcl_path)],
        cwd=str(run_dir), run_dir=run_dir, stage="pdn",
        meta_extra={"vdd_net": req.vdd_net, "vss_net": req.vss_net}
    )

# ── Stage 3: Placement ─────────────────────────────────────────────────────────

class PlacementConfig(BaseModel):
    top_module:        str
    run_id:            str
    cell_lib:          str   = "sky130_fd_sc_hd"
    corner:            str   = "tt"
    density:           float = Field(0.6, ge=0.1, le=0.9)
    timing_driven:     bool  = True
    congestion_driven: bool  = False
    cell_padding:      int   = Field(4, ge=0, le=16)
    clock_port:        str   = "clk"      # needed for timing-driven placement
    clock_period_ns:   float = 10.0       # needed for timing-driven placement


@app.post("/placement")
def placement(req: PlacementConfig):
    run_dir     = get_run_dir(req.run_id)
    pdk         = get_pdk_paths(req.cell_lib, req.corner)
    floorplan_def = run_dir / "floorplan.def"

    # Use pdn.def if PDN was run, else fall back to floorplan.def
    pdn_def = run_dir / "pdn.def"
    input_def = pdn_def if pdn_def.exists() else floorplan_def
    if not floorplan_def.exists():
        raise HTTPException(status_code=400, detail="floorplan.def not found — run floorplan first")

    gp_flags = "-density " + str(req.density)
    if req.timing_driven and req.clock_port:
        gp_flags += " -timing_driven"
    if req.congestion_driven:
        gp_flags += " -congestion_driven"

    tcl_lines = [
        "read_lef " + pdk["tech_lef"],
        "read_lef " + pdk["lef"],
        "read_liberty " + pdk["lib"],
        "read_def " + str(input_def),
        "set_placement_padding -global -left " + str(req.cell_padding) + " -right " + str(req.cell_padding),
    ]

    # Clock must be defined before timing-driven placement
    if req.timing_driven and req.clock_port:
        tcl_lines += [
            "create_clock -period " + str(req.clock_period_ns) + " -name core_clock [get_ports " + req.clock_port + "]",
            "set_wire_rc -clock -layer met2",
            "set_wire_rc -signal -layer met2",
            "estimate_parasitics -placement",
        ]

    tcl_lines += [
        "global_placement " + gp_flags,
        "detailed_placement",
        "write_def " + str(run_dir / "placement.def"),
    ]

    tcl_path = run_dir / "placement.tcl"
    tcl_path.write_text("\n".join(tcl_lines) + "\n")

    return stream_process(
        ["openroad", str(tcl_path)],
        cwd=str(run_dir), run_dir=run_dir, stage="placement",
        meta_extra={"density": req.density, "timing_driven": req.timing_driven}
    )



# ── Stage 3b: Clock Tree Synthesis (OpenROAD) ────────────────────────────────

class CTSConfig(BaseModel):
    top_module:      str
    run_id:          str
    cell_lib:        str   = "sky130_fd_sc_hd"
    corner:          str   = "tt"
    clock_port:      str   = "clk"
    clock_period_ns: float = 10.0
    cts_buf_list:    str   = "sky130_fd_sc_hd__clkbuf_4 sky130_fd_sc_hd__clkbuf_8"
    cts_max_slew:    float = 0.4
    cts_max_cap:     float = 0.08


@app.post("/cts")
def cts(req: CTSConfig):
    run_dir       = get_run_dir(req.run_id)
    pdk           = get_pdk_paths(req.cell_lib, req.corner)
    placement_def = run_dir / "placement.def"

    if not placement_def.exists():
        raise HTTPException(status_code=400, detail="placement.def not found — run placement first")

    tcl = (
        "read_lef " + pdk["tech_lef"] + "\n"
        "read_lef " + pdk["lef"] + "\n"
        "read_liberty " + pdk["lib"] + "\n"
        "read_def " + str(placement_def) + "\n"
        "create_clock -period " + str(req.clock_period_ns) + " -name core_clock [get_ports " + req.clock_port + "]\n"
        "set_wire_rc -clock -layer met2\n"
        "set_wire_rc -signal -layer met2\n"
        "estimate_parasitics -placement\n"
        "configure_cts_characterization "
        "-max_slew " + str(req.cts_max_slew) + " "
        "-max_cap " + str(req.cts_max_cap) + "\n"
        "clock_tree_synthesis "
        "-root_buf sky130_fd_sc_hd__clkbuf_16 "
        "-buf_list {" + req.cts_buf_list + "} "
        "-sink_clustering_enable\n"
        "set_propagated_clock [all_clocks]\n"
        "estimate_parasitics -placement\n"
        "repair_timing -setup -hold\n"
        "detailed_placement\n"
        "write_def " + str(run_dir / "cts.def") + "\n"
    )

    tcl_path = run_dir / "cts.tcl"
    tcl_path.write_text(tcl)

    return stream_process(
        ["openroad", str(tcl_path)],
        cwd=str(run_dir), run_dir=run_dir, stage="cts",
        meta_extra={"clock_port": req.clock_port, "clock_period_ns": req.clock_period_ns}
    )

# ── Stage 4: Routing ───────────────────────────────────────────────────────────

class RoutingConfig(BaseModel):
    top_module:             str
    run_id:                 str
    cell_lib:               str = "sky130_fd_sc_hd"
    corner:                 str = "tt"
    bottom_routing_layer:   str = "met1"
    top_routing_layer:      str = "met5"
    congestion_iterations:  int = Field(30, ge=5, le=100)
    antenna_fixing:         bool = True


@app.post("/routing")
def routing(req: RoutingConfig):
    run_dir       = get_run_dir(req.run_id)
    pdk           = get_pdk_paths(req.cell_lib, req.corner)
    placement_def = run_dir / "placement.def"

    # Use cts.def if CTS was run, else fall back to placement.def
    cts_def = run_dir / "cts.def"
    routing_input_def = cts_def if cts_def.exists() else placement_def
    # Use cts.def if CTS was run, else fall back to placement.def
    cts_def = run_dir / "cts.def"
    routing_input = cts_def if cts_def.exists() else placement_def
    if not placement_def.exists():
        raise HTTPException(status_code=400, detail="placement.def not found — run placement first")

    layer_range = req.bottom_routing_layer + "-" + req.top_routing_layer

    tcl_lines = [
        "read_lef " + pdk["tech_lef"],
        "read_lef " + pdk["lef"],
        "read_liberty " + pdk["lib"],
        "read_def " + str(placement_def),
        "set_routing_layers -signal " + layer_range,
        "global_route \\",
        "    -guide_file " + str(run_dir / "route.guide") + " \\",
        "    -congestion_iterations " + str(req.congestion_iterations),
        "detailed_route \\",
        "    -output_drc " + str(run_dir / "route_drc.rpt") + " \\",
        "    -verbose 1",
        "write_def " + str(run_dir / "routed.def"),
    ]

    tcl_path = run_dir / "routing.tcl"
    tcl_path.write_text("\n".join(tcl_lines) + "\n")

    return stream_process(
        ["openroad", str(tcl_path)],
        cwd=str(run_dir), run_dir=run_dir, stage="routing",
        meta_extra={"layers": layer_range, "congestion_iterations": req.congestion_iterations}
    )



# ── Stage 4b: RC Extraction / SPEF (OpenROAD) ────────────────────────────────

class SPEFConfig(BaseModel):
    top_module: str
    run_id:     str
    cell_lib:   str = "sky130_fd_sc_hd"
    corner:     str = "tt"


@app.post("/spef")
def spef_extract(req: SPEFConfig):
    run_dir    = get_run_dir(req.run_id)
    pdk        = get_pdk_paths(req.cell_lib, req.corner)
    routed_def = run_dir / "routed.def"

    if not routed_def.exists():
        raise HTTPException(status_code=400, detail="routed.def not found — run routing first")

    rcx_rules = PDK_ROOT + "/libs.tech/openlane/rules.openrcx.sky130A.nom.spef_extractor"
    spef_file  = str(run_dir / "output.spef")

    tcl = (
        "read_lef " + pdk["tech_lef"] + "\n"
        "read_lef " + pdk["lef"] + "\n"
        "read_liberty " + pdk["lib"] + "\n"
        "read_def " + str(routed_def) + "\n"
        "define_process_corner -ext_model_index 0 C\n"
        "extract_parasitics -ext_model_file " + rcx_rules + "\n"
        "write_spef " + spef_file + "\n"
    )

    tcl_path = run_dir / "spef.tcl"
    tcl_path.write_text(tcl)

    return stream_process(
        ["openroad", str(tcl_path)],
        cwd=str(run_dir), run_dir=run_dir, stage="spef"
    )

# ── Stage 5: Timing ────────────────────────────────────────────────────────────

class TimingConfig(BaseModel):
    top_module:          str
    run_id:              str
    cell_lib:            str   = "sky130_fd_sc_hd"
    corner:              str   = "tt"
    clock_period_ns:     float = 10.0
    clock_uncertainty_ns: float = 0.1
    input_delay_frac:    float = Field(0.2, ge=0.0, le=0.9)
    output_delay_frac:   float = Field(0.2, ge=0.0, le=0.9)
    clock_port:          str   = ""    # empty = combinational (no clock)


@app.post("/timing")
def timing(req: TimingConfig):
    run_dir    = get_run_dir(req.run_id)
    pdk        = get_pdk_paths(req.cell_lib, req.corner)
    routed_def = run_dir / "routed.def"

    if not routed_def.exists():
        raise HTTPException(status_code=400, detail="routed.def not found — run routing first")

    input_delay  = round(req.clock_period_ns * req.input_delay_frac,  3)
    output_delay = round(req.clock_period_ns * req.output_delay_frac, 3)

    spef_path = run_dir / "output.spef"

    # Use routed DEF — best available post-route database
    tcl_lines = [
        "read_lef " + pdk["tech_lef"],
        "read_lef " + pdk["lef"],
        "read_liberty " + pdk["lib"],
        "read_def " + str(routed_def),
    ]

    # Load SPEF for accurate post-route parasitic STA
    if spef_path.exists():
        tcl_lines.append("read_spef " + str(spef_path))

    # Clock constraints — only if a clock port is specified
    if req.clock_port:
        tcl_lines += [
            "create_clock -period " + str(req.clock_period_ns) +
            " -name core_clock [get_ports " + req.clock_port + "]",
            "set_clock_uncertainty " + str(req.clock_uncertainty_ns) + " [get_clocks core_clock]",
            "set_propagated_clock [all_clocks]",
        ]
        # set_input_delay only on non-clock inputs to avoid STA-0441 warning
        # Apply input delay to all inputs, then remove from clock port
        tcl_lines += [
            "set_input_delay " + str(input_delay) + " -clock core_clock [all_inputs]",
            "set_false_path -from [get_ports " + req.clock_port + "]",
            "set_output_delay " + str(output_delay) + " -clock core_clock [all_outputs]",
        ]

    tcl_lines += [
        "# Setup (max) timing",
        "report_checks -path_delay max -format full_clock_expanded",
        "report_wns",
        "report_tns",
        "# Hold (min) timing",
        "report_checks -path_delay min -format full_clock_expanded",
        "report_power",
    ]

    tcl_path = run_dir / "timing.tcl"
    tcl_path.write_text("\n".join(tcl_lines) + "\n")

    timing_rpt = run_dir / "timing.rpt"

    def generate():
        t0 = time.time()
        proc = subprocess.Popen(
            ["openroad", str(tcl_path)], cwd=str(run_dir),
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True, bufsize=1
        )
        lines = []
        for line in proc.stdout:
            lines.append(line)
            yield line
        proc.wait()

        timing_rpt.write_text("".join(lines))

        elapsed = round(time.time() - t0, 2)
        meta_path = run_dir / "run_meta.json"
        meta = json.loads(meta_path.read_text()) if meta_path.exists() else {}
        if "stages" not in meta:
            meta["stages"] = {}
        meta["stages"]["timing"] = {
            "status": "done" if proc.returncode == 0 else "error",
            "time_s": elapsed,
            "clock_period_ns": req.clock_period_ns,
        }
        meta_path.write_text(json.dumps(meta, indent=2))

        if proc.returncode != 0:
            yield "\n[ERROR] Process exited with code " + str(proc.returncode) + "\n"
        else:
            yield "\n[DONE] Exit code 0\n"

    return StreamingResponse(generate(), media_type="text/plain")


# ── Stage 6: DRC + GDS ─────────────────────────────────────────────────────────

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

    # Step 1: Export GDS from routed DEF
    export_script = (
        "import pya\n"
        "layout = pya.Layout()\n"
        "layout.read('" + str(routed_def) + "')\n"
        "layout.write('" + str(gds_file) + "')\n"
        "print('[INFO] GDS exported to " + str(gds_file) + "')\n"
        "print('[DONE] GDS export complete')\n"
    )
    export_path = run_dir / "export_gds.py"
    export_path.write_text(export_script)

    import subprocess as _sp
    export_result = _sp.run(
        ["klayout", "-b", "-r", str(export_path)],
        capture_output=True, text=True, cwd=str(run_dir)
    )

    # Step 2: Run real DRC with Sky130HD rule deck
    # Variables: $in_gds = GDS file, $report_file = output report
    drc_rule_deck = "/OpenROAD-flow-scripts/flow/platforms/sky130hd/drc/sky130hd.lydrc"
    drc_output = ""

    if gds_file.exists() and Path(drc_rule_deck).exists():
        drc_run = _sp.run(
            ["klayout", "-b",
             "-rd", "in_gds=" + str(gds_file),
             "-rd", "report_file=" + str(drc_rpt),
             "-r", drc_rule_deck],
            capture_output=True, text=True, cwd=str(run_dir), timeout=120
        )
        drc_output = drc_run.stdout + drc_run.stderr
    else:
        drc_output = "[INFO] DRC rule deck not available — GDS export only.\n"
        drc_rpt.write_text("No DRC run.\n")

    def generate():
        for line in (export_result.stdout + export_result.stderr).split("\n"):
            if line.strip() and "Warning:" not in line:
                yield line + "\n"
        if gds_file.exists():
            yield "[INFO] Running Sky130HD DRC rule check...\n"
        for line in drc_output.split("\n"):
            if line.strip():
                yield line + "\n"
        # Parse DRC report
        if drc_rpt.exists():
            import re as _re
            rpt_text = drc_rpt.read_text()
            violations = _re.findall(r"([\w][\w\s]+?):\s*(\d+)\s+violation", rpt_text, _re.IGNORECASE)
            if violations:
                yield "\n[DRC SUMMARY]\n"
                total = 0
                for vtype, count in violations:
                    yield "  " + vtype.strip() + ": " + count + " violations\n"
                    total += int(count)
                yield "  Total: " + str(total) + " violations\n"
            elif rpt_text.strip() and "violation" not in rpt_text.lower():
                yield "[DRC] No violations found — design is DRC clean!\n"
        yield "\n[DONE] Exit code 0\n"

    # Update run_meta
    run_meta_path = run_dir / "run_meta.json"
    try:
        meta = json.loads(run_meta_path.read_text())
        meta.setdefault("stages", {})["drc"] = {
            "status": "done",
            "gds_exported": gds_file.exists(),
            "drc_run": Path(drc_rule_deck).exists(),
        }
        run_meta_path.write_text(json.dumps(meta, indent=2))
    except Exception:
        pass

    from fastapi.responses import StreamingResponse as _SR
    return _SR(generate(), media_type="text/plain")


# ── Run metadata ───────────────────────────────────────────────────────────────

@app.get("/run/{run_id}/meta")
def get_meta(run_id: str):
    run_dir   = Path(WORK_BASE) / run_id
    meta_path = run_dir / "run_meta.json"
    if not meta_path.exists():
        raise HTTPException(status_code=404, detail="Run not found")
    return json.loads(meta_path.read_text())


# ── Download ───────────────────────────────────────────────────────────────────



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

    return FileResponse(str(fpath), filename=filename)