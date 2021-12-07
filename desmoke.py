#!/usr/bin/env python3
from abc import ABC, abstractmethod
import argparse
from dataclasses import dataclass
from io import TextIOBase
import json
import re
import sys
import os
from typing import Any, Dict, List, Tuple, Union


Json = Dict[str, Any]


def diff(a, b) -> Tuple[Any, Any]:
    """
    Return the deep diff between two elements, or None if they are equal.
    """
    if a == b:
        return None

    if type(a) != type(b):
        return (a, b)

    if isinstance(a, dict):
        return dict_diff(a, b)

    if isinstance(a, (list, tuple)):
        return list_diff(a, b)

    return a, b


def list_diff(a: List[Any], b: List[Any]) -> Tuple[List[Any], List[Any]]:
    """
    Get the deep diff of two lists.
    """
    diff_a = list()
    diff_b = list()

    for (va, vb) in zip(a, b):
        result = diff(va, vb)
        if result is not None:
            diff_a.append(result[0])
            diff_b.append(result[1])

    if len(a) != len(b):
        shorter_len = min(len(a), len(b))
        longer_len = max(len(a), len(b))
        if shorter_len == len(a):
            diff_b.extend(b[shorter_len:longer_len])
        else:
            diff_a.extend(a[shorter_len:longer_len])

    return diff_a, diff_b


def dict_diff(a: Json, b: Json) -> Tuple[Json, Json]:
    """
    Get the deep diff of two dictionaries.
    """
    diff_a = dict()
    diff_b = dict()

    if not (isinstance(a, dict) and isinstance(b, dict)):
        return (a, b)

    both = set(a.keys()).intersection(set(b.keys()))
    only_a = set(a.keys()).difference(both)
    only_b = set(b.keys()).difference(both)

    for k in only_a:
        diff_a[k] = a[k]
    for k in only_b:
        diff_b[k] = b[k]

    for k in both:
        result = diff(a[k], b[k])
        if result is not None:
            diff_a[k], diff_b[k] = result
    return (diff_a, diff_b)


FILE_TRACE_PATTERN = re.compile(r"^([\w\.]*@)?([\w\.\/]+):(\d+):(\d+)$")


@dataclass
class Position:
    """
    A position in a file.
    """

    file: str
    line: str
    column: str

    @classmethod
    def from_traceback(cls, traces: List[str]):
        """
        The relevant line position for errors is the top-most error in a file in
        the jstests/ directory.
        """
        for trace in traces:
            match = FILE_TRACE_PATTERN.match(trace)
            if match is None:
                raise ValueError("string did not match traceback.")
            if match.group(2).startswith("jstests"):
                return cls(match.group(2), match.group(3), match.group(4))
        return None

    def __str__(self) -> str:
        return f"{self.file}:{self.line}:{self.column}"


@dataclass
class Assertion:
    """
    A generic assertion.
    """

    PATTERN = re.compile(f"Error: (.*)?:$")

    position: Position
    message: Union[str, Json]

    @classmethod
    def do_parse(cls, match, pos):
        msg = match.group(1)
        if msg is None:
            msg = "<no message>"
        return cls(pos, msg)

    @classmethod
    def parse(cls, assertion, pos):
        """
        Parse an assertion from a string which represents it, and return None
        if the string doesn't match.
        """
        if match := cls.PATTERN.search(assertion):
            return cls.do_parse(match, pos)

    def __str__(self) -> str:
        return f"{self.position}: error: {self.message}"


@dataclass
class JSError(Assertion):
    PATTERN = re.compile(f"(\w+Error): (.*) :")

    error_type: str

    @classmethod
    def do_parse(cls, match, pos):
        return cls(pos, match.group(2), match.group(1))

    def __str__(self) -> str:
        return f"{self.position}: warning: {self.error_type}: {self.message}"


@dataclass
class Inequality(Assertion):
    """
    A failing equality assertion.
    """

    PATTERN = re.compile(r"Error: (.+) != (.+) are not equal (:.*)?:")

    left: Json
    right: Json

    @classmethod
    def do_parse(cls, match, pos):
        left = json.loads(match.group(1))
        right = json.loads(match.group(2))
        if match.group(3) is not None:
            try:
                msg = json.loads(match.group(3)[1:])
            except json.decoder.JSONDecodeError:
                msg = match.group(3)[1:]
        else:
            msg = "<no message>"
        return cls(pos, msg, left, right)

    def __str__(self) -> str:
        left_diff, right_diff = diff(self.left, self.right)
        return f"{self.position}: error: assert equals failed: {self.message}: {json.dumps(self.left)} != {json.dumps(self.right)}\nDiff:\nLeft:{json.dumps(left_diff)}\nRight:{json.dumps(right_diff)}"


LINE_PATTERN = re.compile(r"^\[([\w:]+)\] (.+)$")


class BaseState(ABC):
    """
    The resmoke log parser is defined as a finite state machine. Each state implements a process()
    method which takes in the relevant part of the log line, extracts relevant information
    from that line, and optionally transitions to a new state.
    """

    @abstractmethod
    def process(self, contents: str):
        pass

    def process_contents(self, contents):
        """
        If the process() function returns None, that means that the machine did not transition to a
        new state and self should be returned to the caller.
        """
        res = self.process(contents)
        if res is None:
            return self
        else:
            return res

    def step(self, line: str):
        """
        Process a single log line. This function does some pre-processing, removing the status column and
        filtering out mongod log lines from processing.
        """
        match = LINE_PATTERN.match(line)
        if match is None or not match.group(1).startswith("js_test"):
            return self

        contents = match.group(2)
        return self.process_contents(contents)

    def is_complete(self) -> bool:
        """
        Returns True if get() will return a fully parsed assertion.
        """
        return False

    def get():
        """
        Get the fully parsed assertion from the parser.
        """
        raise RuntimeError("Cannot get() on a non-complete parser.")


ASSERTION_START = "uncaught exception:"


class StartState(BaseState):
    """
    Don't collect any lines until we find the start of an assertion.
    """

    def process(self, contents: str):
        # TRANSITION: Beginning of assertion.
        if contents.startswith(ASSERTION_START):
            return AssertionState(contents)


class AssertionState(BaseState):
    """
    Collect all lines that make up the assertion message.
    the shell's tojson() method pretty-prints objects, and so many
    log files take up multiple lines.
    """

    def __init__(self, first_line):
        self.lines = [first_line[len(ASSERTION_START) :]]

    def process(self, contents: str):
        # TRANSITION: We've found all the lines from the assertion output, now it's time to collect the traceback.
        if FILE_TRACE_PATTERN.match(contents) is not None:
            return TracebackState(self.lines, contents)

        # Remove any indentation at the beginning of the line.
        self.lines.append(contents.strip())


class TracebackState(BaseState):
    def __init__(self, assertion_lines, first_traceback):
        self.assertion_lines = assertion_lines
        self.traceback_lines = [first_traceback]

    def process(self, contents: str):
        # TRANSITION: when the next line isn't a traceback, we've got all our information.
        if FILE_TRACE_PATTERN.match(contents) is None:
            return CompleteState(
                "".join(self.assertion_lines), self.traceback_lines, contents
            )
        self.traceback_lines.append(contents)


class CompleteState(BaseState):
    def __init__(
        self, raw_assertion: str, raw_traceback: List[str], next_contents: str
    ):
        self.raw_assertion = raw_assertion
        self.raw_traceback = raw_traceback
        self.next_contents = next_contents

    def is_complete(self) -> bool:
        return True

    def get(self):
        pos = Position.from_traceback(self.raw_traceback)
        assertion_string = "".join(self.raw_assertion)
        assert_order = [Inequality, JSError, Assertion]
        for assert_class in assert_order:
            if assert_obj := assert_class.parse(assertion_string, pos):
                return assert_obj
        raise RuntimeError(
            f"Assertion did not match any existing patterns: {assertion_string}"
        )

    def process(self, contents: str):
        """
        Calling process() on a complete state will need to process the stored next line as
        well as the passed in line. Make sure to call get() before process() to collect the assertion.
        """
        return (
            StartState().process_contents(self.next_contents).process_contents(contents)
        )


def install_task(filename):
    if filename is None:
        filename = ".vscode/tasks.json"

    jstest_task = {
        "label": "Run file as jstest",
        "type": "shell",
        "command": "bash",
        "args": [
            "-c",
            "source python3-venv/bin/activate && ./buildscripts/resmoke.py run ${relativeFile} | desmoke.py --filetype resmoke",
        ],
        "group": {"kind": "test", "isDefault": True},
        "presentation": {"focus": True, "clear": True},
        "problemMatcher": {
            "owner": "js",
            "fileLocation": ["relative", "${workspaceFolder}"],
            "pattern": {
                "regexp": r"^\[desmoke\]\s+(.*):(\d+):(\d+):\s+(warning|error):\s+(.*)$",
                "file": 1,
                "line": 2,
                "column": 3,
                "severity": 4,
                "message": 5,
            },
        },
    }

    cppunit_task = {
        "label": "Run file as C++ unit test",
        "type": "shell",
        "command": "bash",
        "args": [
            "-c",
            "source python3-venv/bin/activate && ninja -j400 +${fileBasenameNoExtension} | desmoke.py --filetype cppunit",
        ],
        "group": "test",
        "presentation": {"focus": True, "clear": True},
        "problemMatcher": {
            "owner": "cpp",
            "fileLocation": ["relative", "${workspaceFolder}"],
            "pattern": {
                "regexp": r"^\[desmoke\]\s+(.*):(\d+):\s+(.*)$",
                "file": 1,
                "line": 2,
                "message": 3,
            },
        },
    }

    if os.path.exists(filename):
        with open(filename, "r") as file:
            tasks = json.load(file)
    else:
        should_continue = input(f"{filename} does not yet exist. Create it? (y/N) ")
        if should_continue.lower() != "y":
            print("Goodbye!")
            return
        tasks = {"version": "2.0.0", "cwd": "${workspaceFolder}"}

    tasks.setdefault("tasks", []).append(jstest_task)
    tasks["tasks"].append(cppunit_task)

    with open(filename, "w") as file:
        json.dump(tasks, file, indent=4)


def desmoke_print(s, pass_through):
    if pass_through:
        print(f"[desmoke] {s}")
    else:
        print(s)


def process_resmoke(file, pass_through):
    parser = StartState()
    assertions = []
    while line := file.readline():
        if pass_through:
            sys.stdout.write(line)
        parser = parser.step(line)
        if parser.is_complete():
            assertion = parser.get()
            desmoke_print(assertion, pass_through)
            assertions.append(assertion)

    file.close()
    return assertions


UNITTEST_ERROR_PATTERN = re.compile(r"^(.*)\s+@([\w\.\/]+):(\d+)$")


def process_unittest(file, pass_through):
    """
    Luckily, each line in C++ unit test output is a JSON file, so parsing
    is much easier! Still need to do some string manipulation to get it in an unambiguous format
    for desmoke to output.
    """
    assertions = []
    while line := file.readline():
        if pass_through:
            sys.stdout.write(line)
        try:
            log = json.loads(line)
        except json.decoder.JSONDecodeError:
            continue

        # Look for log lines that represent test failures, then parse and reformat the error message.
        if log["c"] == "TEST" and log["msg"] == "FAIL":
            if match := UNITTEST_ERROR_PATTERN.match(log["attr"]["error"]):
                assertion = f"{match.group(2)}:{match.group(3)}: {match.group(1)}"
                desmoke_print(assertion, pass_through)
                assertions.append(assertion)
    file.close()
    return assertions


def setup_parser():
    parser = argparse.ArgumentParser(description="Prettify resmoke output.")
    parser.add_argument(
        "filename",
        nargs="?",
        help="File to use as input. If not provided, desmoke.py will read from stdin.",
    )
    group = parser.add_mutually_exclusive_group()
    group.add_argument(
        "--summary",
        action="store_true",
        help="Report a summary at the end of the output.",
    )
    group.add_argument(
        "--only",
        action="store_true",
        help="Only send desmoke.py output to stdout without forwarding the input file or stream.",
    )
    parser.add_argument(
        "--filetype",
        choices=["resmoke", "cppunit"],
        help="Force a certain log parser. By default, desmoke.py will make a best guess based on the first log line.",
    )
    parser.add_argument(
        "--install",
        action="store_true",
        help="Adds tasks to vscode's tasks.json to enable VSCode integration.",
    )
    return parser


def main():
    argparser = setup_parser()
    args = argparser.parse_args()
    if args.install:
        return install_task(args.filename)

    # Read from stdin (likely piped output) if a file wasn't specified.
    if args.filename is None:
        file = open(sys.stdin.fileno(), "r")
    else:
        file = open(args.filename, "r")

    pass_through = not args.only
    summary = args.summary

    # Infer filetype from the first line of the file.
    mode = args.filetype
    if mode is None:
        first_line = file.readline()
        if first_line.startswith("[resmoke]"):
            mode = "resmoke"
        else:
            mode = "cppunit"

    if mode == "resmoke":
        assertions = process_resmoke(file, pass_through)
    elif mode == "cppunit":
        assertions = process_unittest(file, pass_through)
    else:
        argparser.print_help()
        return

    if summary:
        print("----")
        print("\n".join(assertions))
        print("----")


if __name__ == "__main__":
    main()
