"""
Tests for the CORDIC vector rotation block (macro_cordic).

Run from the backend folder:   python -m pytest tests/test_cordic.py -v
(needs iverilog installed for the simulation tests)
"""
import math
import os
import random
import shutil
import subprocess
import sys
import tempfile

import pytest

HERE    = os.path.dirname(os.path.abspath(__file__))
BACKEND = os.path.dirname(HERE)
sys.path.insert(0, BACKEND)
sys.path.insert(0, os.path.join(BACKEND, "rtl_codegen"))

from emit_cordic import emit_cordic                       # noqa: E402
from emit_testbench import emit_testbench                 # noqa: E402
import port_contract as pc                                # noqa: E402

needs_iverilog = pytest.mark.skipif(shutil.which("iverilog") is None, reason="iverilog not installed")

IR = {
    "module": "top", "parameters": {},
    "ports": [
        {"id": "ix", "name": "X",   "dir": "input",  "width": "16"},
        {"id": "iy", "name": "Y",   "dir": "input",  "width": "16"},
        {"id": "ia", "name": "ANG", "dir": "input",  "width": "16"},
        {"id": "ox", "name": "XR",  "dir": "output", "width": "16"},
        {"id": "oy", "name": "YR",  "dir": "output", "width": "16"},
    ],
    "nodes": [
        {"id": "ix", "type": "input",  "name": "X",   "width": "16"},
        {"id": "iy", "type": "input",  "name": "Y",   "width": "16"},
        {"id": "ia", "type": "input",  "name": "ANG", "width": "16"},
        {"id": "c1", "type": "macro_cordic", "name": "c1", "width": "16"},
        {"id": "ox", "type": "output", "name": "XR",  "width": "16"},
        {"id": "oy", "type": "output", "name": "YR",  "width": "16"},
    ],
    "edges": [
        {"src": "ix", "dst": "c1", "src_port": "out",   "dst_port": "x"},
        {"src": "iy", "dst": "c1", "src_port": "out",   "dst_port": "y"},
        {"src": "ia", "dst": "c1", "src_port": "out",   "dst_port": "angle"},
        {"src": "c1", "dst": "ox", "src_port": "x_out", "dst_port": "in"},
        {"src": "c1", "dst": "oy", "src_port": "y_out", "dst_port": "in"},
    ],
}


def _ideal(x, y, deg):
    c, s = math.cos(math.radians(deg)), math.sin(math.radians(deg))
    return x * c - y * s, x * s + y * c


def test_port_contract():
    w = pc.port_widths("macro_cordic", data_width=16)
    assert w["inputs"] == {"x": 16, "y": 16, "angle": 16}
    assert w["outputs"] == {"x_out": 16, "y_out": 16}
    assert pc.required_inputs("macro_cordic") == ["x", "y", "angle"]


def test_module_name_and_ports():
    name, v = emit_cordic("abc", 16)
    assert name == "cordic_abc"
    for port in ("clk", "rst", "x", "y", "angle", "x_out", "y_out"):
        assert port in v


@needs_iverilog
def test_verilog_matches_ideal_math():
    """Random vectors, all quadrants: error must stay below 0.02 (decimal units)."""
    name, v = emit_cordic("t", 16)
    random.seed(11)
    vecs = []
    for _ in range(400):
        r, th = random.uniform(0.5, 120), random.uniform(0, 2 * math.pi)
        vecs.append((round(r * math.cos(th) * 256), round(r * math.sin(th) * 256),
                     round(random.uniform(-180, 180) * 100)))
    tb = ["`timescale 1ns/1ps",
          "module tb; reg clk=0, rst=1; reg signed [15:0] x,y,a; wire signed [15:0] xo,yo;",
          f"{name} u(.clk(clk),.rst(rst),.x(x),.y(y),.angle(a),.x_out(xo),.y_out(yo));",
          "always #5 clk=~clk; initial begin x=0;y=0;a=0; repeat(3) @(posedge clk); #1 rst=0;"]
    for x, y, a in vecs:
        tb.append(f'  x={x}; y={y}; a={a}; @(posedge clk); #1; $display("%0d %0d", xo, yo);')
    tb.append("  $finish; end endmodule")

    with tempfile.TemporaryDirectory() as d:
        open(os.path.join(d, "c.v"), "w").write(v)
        open(os.path.join(d, "tb.v"), "w").write("\n".join(tb))
        subprocess.run(["iverilog", "-o", os.path.join(d, "s"), os.path.join(d, "c.v"), os.path.join(d, "tb.v")], check=True)
        out = subprocess.run(["vvp", os.path.join(d, "s")], capture_output=True, text=True).stdout

    rows = [tuple(map(int, l.split())) for l in out.splitlines() if l.strip() and l.split()[0].lstrip("-").isdigit()]
    assert len(rows) == len(vecs)
    for (x, y, a), (ox, oy) in zip(vecs, rows):
        ex, ey = _ideal(x, y, a / 100)
        assert abs(ox - ex) / 256 < 0.02 and abs(oy - ey) / 256 < 0.02, (x, y, a, ox, oy, ex, ey)


@needs_iverilog
def test_gain_is_removed():
    """Rotation must keep the vector length (a CORDIC with gain would give x1.647)."""
    name, v = emit_cordic("g", 16)
    tb = f"""`timescale 1ns/1ps
module tb; reg clk=0, rst=1; reg signed [15:0] x,y,a; wire signed [15:0] xo,yo;
{name} u(.clk(clk),.rst(rst),.x(x),.y(y),.angle(a),.x_out(xo),.y_out(yo));
always #5 clk=~clk;
initial begin x=3*256; y=4*256; a=3700; repeat(3) @(posedge clk); #1 rst=0; @(posedge clk); #1;
 $display("%0d %0d", xo, yo); $finish; end endmodule"""
    with tempfile.TemporaryDirectory() as d:
        open(os.path.join(d, "c.v"), "w").write(v)
        open(os.path.join(d, "tb.v"), "w").write(tb)
        subprocess.run(["iverilog", "-o", os.path.join(d, "s"), os.path.join(d, "c.v"), os.path.join(d, "tb.v")], check=True)
        out = subprocess.run(["vvp", os.path.join(d, "s")], capture_output=True, text=True).stdout.split()
    xo, yo = int(out[0]) / 256, int(out[1]) / 256
    assert abs(math.hypot(xo, yo) - 5.0) < 0.02


def test_testbench_converts_decimals():
    stim = {"steps": [{"time": 100, "label": "s", "values": {"X": "3.5", "Y": "-2", "ANG": "30.25"},
                       "expected": {"XR": "1.5", "YR": "4"}}]}
    tb = emit_testbench(IR, stim)
    assert "X = 896;" in tb          # 3.5   x 256
    assert "Y = -512;" in tb         # -2    x 256
    assert "ANG = 3025;" in tb       # 30.25 x 100
    assert "tolerance" in tb         # decimal check with tolerance, not ===


def test_testbench_other_blocks_unchanged():
    """A circuit without CORDIC must keep the old exact (===) check and %0d display."""
    ir = {"module": "top", "parameters": {},
          "ports": [{"id": "i", "name": "A", "dir": "input", "width": "8"},
                    {"id": "o", "name": "B", "dir": "output", "width": "8"}],
          "nodes": [{"id": "i", "type": "input", "name": "A", "width": "8"},
                    {"id": "o", "type": "output", "name": "B", "width": "8"}],
          "edges": [{"src": "i", "dst": "o", "src_port": "out", "dst_port": "in"}]}
    tb = emit_testbench(ir, {"steps": [{"time": 100, "values": {"A": "5"}, "expected": {"B": "5"}}]})
    assert "B === 5" in tb and "%0.4f" not in tb
