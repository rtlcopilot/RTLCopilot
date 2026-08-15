

from __future__ import annotations

from pydantic import BaseModel, Field
from typing import List, Dict, Optional


class NodeData(BaseModel):
    name: str
    width: str = "1"
    op: Optional[str] = None
    value: str = "0"
    bitIndex: str = "0"
    fifoDepth: Optional[str] = "16"
    aeThresh: Optional[str] = "4"
    lsbPriority: Optional[int] = 0
    edgeType: Optional[int] = 0
    addrWidth: Optional[str] = "6"
    countDir: Optional[int] = 1

class Node(BaseModel):
    id: str
    type: str
    position: Dict[str, float]
    data: NodeData

class Edge(BaseModel):
    id: str
    source: str
    target: str
    sourceHandle: Optional[str] = "out"
    targetHandle: Optional[str] = "in"

class CircuitResponse(BaseModel):
    explanation: str
    nodes: List[Node]
    edges: List[Edge]

class GenerateRequest(BaseModel):
    ir: dict

class TBRequest(BaseModel):
    ir: dict
    stimulus: dict

class SimulateRequest(BaseModel):
    verilog: str = ""
    verilog_files: dict = {}
    testbench: str

class ChatRequest(BaseModel):
    prompt: str = Field(..., max_length=2000)
    current_nodes: list = []
    current_edges: list = []

class ProjectSaveRequest(BaseModel):
    name: str
    description: Optional[str] = ""
    canvas: dict

class ProjectUpdateRequest(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    canvas: Optional[dict] = None

class FeedbackRequest(BaseModel):
    rating: int
    text: Optional[str] = ""
    trigger: Optional[str] = ""
    user_id: Optional[str] = None


class CreateOrderRequest(BaseModel):
    plan: str = Field(..., pattern="^(starter|pro)$")


class CustomBlockRequest(BaseModel):
    name:         str = Field(..., max_length=64)
    description:  str = Field(..., max_length=500)
    inputs:       list
    outputs:      list
    internal_signals: list = []
    behaviour:    str = Field(..., max_length=1000)


class SaveCustomBlockRequest(BaseModel):
    name:        str  = Field(..., max_length=64)
    description: str  = Field('', max_length=500)
    block_schema: dict
    verilog:     str
    ports:       list
    block_type:  str  = Field(..., max_length=32)


class VerifyRequest(BaseModel):
    ir:             dict
    verilog_files:  dict = {}
    stimulus:       dict = {}
    design_intent:  str  = ""   


class AutoVerifyRequest(BaseModel):
    ir:            dict
    verilog_files: dict = {}


class HierarchicalRequest(BaseModel):
    prompt: str = Field(..., max_length=2000)


class HierarchicalV2Request(BaseModel):
    prompt: str = Field(..., max_length=2000)


class FollowUpRequest(BaseModel):
    prompt:        str  = Field(..., max_length=2000)
    current_nodes: list = []
    current_edges: list = []


__all__ = [_n for _n in dir() if not _n.startswith("__")]