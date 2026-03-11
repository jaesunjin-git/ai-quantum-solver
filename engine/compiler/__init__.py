from .base import BaseCompiler, DataBinder, CompileResult
from .ortools_compiler import ORToolsCompiler
from .dwave_cqm_compiler import DWaveCQMCompiler
from .dwave_bqm_compiler import DWaveBQMCompiler
from .dwave_nl_compiler import DWaveNLCompiler

COMPILER_MAP = {
    "classical_cpu": ORToolsCompiler,
    "nvidia_cuopt": ORToolsCompiler,      # cuOpt도 LP/MIP 입력
    "dwave_hybrid_cqm": DWaveCQMCompiler,
    "dwave_hybrid_bqm": DWaveBQMCompiler,
    "dwave_advantage_qpu": DWaveBQMCompiler,   # Advantage QPU (Pegasus)
    "dwave_advantage2_qpu": DWaveBQMCompiler, # Advantage2 QPU (Zephyr)
    "dwave_nl": DWaveNLCompiler,              # NL/Stride 비선형 모델
}


def get_compiler(solver_id: str) -> BaseCompiler:
    """솔버 ID에 맞는 컴파일러 인스턴스를 반환"""
    cls = COMPILER_MAP.get(solver_id)
    if cls is None:
        raise ValueError(f"No compiler available for solver: {solver_id}")
    return cls()
