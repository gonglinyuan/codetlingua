from argparse import Namespace
from dataclasses import dataclass, field
from enum import Enum
from typing import List, Optional, Tuple, Union

import requests


class ExecOutcome(Enum):
    PASSED = "PASSED"  # code executes and output matches expected output
    WRONG_ANSWER = "WRONG_ANSWER"  # code executes and output does NOT matches expected output
    TIME_LIMIT_EXCEEDED = "TIME_LIMIT_EXCEEDED"  # code executes and didn't exit in time, output is ignored in this case
    RUNTIME_ERROR = "RUNTIME_ERROR"  # code failed to execute (crashed)
    COMPILATION_ERROR = "COMPILATION_ERROR"  # code failed to compile
    MEMORY_LIMIT_EXCEEDED = "MEMORY_LIMIT_EXCEEDED"  # code exceeded memory limit during execution


@dataclass
class ExtendedUnittest:
    input: str
    output: List[str] = field(default_factory=list)
    result: Optional[str] = None
    exec_outcome: Optional[ExecOutcome] = None

    def json(self):
        _json = self.__dict__
        if self.exec_outcome is not None:
            _json["exec_outcome"] = self.exec_outcome.name

        return _json

    @classmethod
    def from_json(cls, _json):
        return cls(
            input=_json.get("input", ""),
            output=_json.get("output", list()),
            result=_json.get("result", None),
            exec_outcome=_json.get("exec_outcome", None), )


class APICommunication:
    _session: requests.Session

    def __init__(self, server_url: str = "http://localhost:5000"):
        self._session = requests.Session()
        self.execute_code_url = f"{server_url}/api/execute_code"
        self.get_runtimes_url = f"{server_url}/api/all_runtimes"

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self._session.close()

    def get_runtimes(self):
        return self._session.get(self.get_runtimes_url).json()

    def execute_code(
        self,
        language: str,
        source_code: str,
        unittests: List[dict],
        limits: Optional[dict] = None,
        block_network: bool = True,
        stop_on_first_fail: bool = True,
        use_sanitizer: bool = False,
        compiler_program_name: Optional[str] = None,
        compiler_flags: Optional[str] = None,
        interpreter_cmd: Optional[str] = None,
        interpreter_flags: Optional[str] = None,
        sample_id: Optional[int] = None,
        task_id: Union[str, int, None] = None, ) -> Tuple[List[ExtendedUnittest], Optional[int], Union[str, int, None]]:
        if language is None:
            raise ValueError("EmptyLanguage")

        if source_code is None:
            raise ValueError("EmptySourceCode")

        if unittests is None or len(unittests) == 0:
            raise ValueError("EmptyUnittest")

        request_body = dict(
            language=language,
            source_code=source_code,
            unittests=unittests,
            limits=limits if isinstance(limits, dict) else None,
            compile_cmd=compiler_program_name,
            compile_flags=compiler_flags,
            execute_cmd=interpreter_cmd,
            execute_flags=interpreter_flags,
            block_network=block_network,
            stop_on_first_fail=stop_on_first_fail,
            use_sanitizer=use_sanitizer, )
        try:
            json_response = self._session.post(
                self.execute_code_url, json=request_body, headers={"Content-Type": "application/json"}, ).json()
        except requests.exceptions.JSONDecodeError:
            json_response = {
                "task_id": task_id,
                "data": [{"exec_outcome": "COMPILATION_ERROR", "result": "", "passed": False}]
            }

        if "data" not in json_response:
            return json_response, sample_id, task_id

        return (json_response["data"], sample_id, task_id,)


LANG_TO_COMPILER = {
    "C++": "GNU C++17", "C#": "Mono C#", "Java": "Java 17", "Python": "PyPy 3"
}

execeval: APICommunication = None


def run_test(problem, code, target_lang):
    global execeval

    SUCCESS = "success"
    RUNTIME_FAILED = "runtime_failed"
    COMPILE_FAILED = "compile_failed"
    INFINTIE_LOOP = "infinite_loop"
    TEST_FAILED = "test_failed"

    result = execeval.execute_code(
        LANG_TO_COMPILER[target_lang],
        code,
        [{"input": s["input"], "output": [s["output"]]} for s in problem['test_IO']],
        task_id=problem['id']
    )[0]
    if not (isinstance(result, list) and isinstance(result[0], dict)):
        print(result)
        return result, COMPILE_FAILED
    for o in result:
        if o['result'] is not None and len(o['result']) > 1000:
            o['result'] = o['result'][:1000]
    if all(o['exec_outcome'] == 'PASSED' for o in result):
        return result, SUCCESS
    elif any(o['exec_outcome'] == 'COMPILATION_ERROR' for o in result):
        return result, COMPILE_FAILED
    elif any(o['exec_outcome'] == 'RUNTIME_ERROR' or o['exec_outcome'] == 'MEMORY_LIMIT_EXCEEDED' for o in result):
        return result, RUNTIME_FAILED
    elif any(o['exec_outcome'] == 'TIME_LIMIT_EXCEEDED' for o in result):
        return result, INFINTIE_LOOP
    elif any(o['exec_outcome'] == 'WRONG_ANSWER' for o in result):
        return result, TEST_FAILED
    else:
        assert False


def build_execeval(args: Namespace):
    global execeval
    execeval = APICommunication(server_url=f"http://localhost:{args.port}")
