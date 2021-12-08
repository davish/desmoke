## desmoke.py

### Summary

The output from MongoDB's test harnesses can be quite tedious to read in order to locate specific errors and false assertions during development, even with some `grep` magic. JavaScript assertions in `resmoke.py` can be spread out over many lines and interspersed with output lines from spawned `mongod` and `mongos` processes, making it difficult if not impossible for a regular expression alone to parse properly. Since JavaScript is a dynamic language, actual programming errors in jstests are intermixed with assertion failures, and determining whether something is a mistake in the JS test code or an assertion failure is more difficult than it needs to be. C++ unit tests that are run through `ninja` and `scons.py` output long and verbose JSON objects from which important information is difficult to extract at a glance.

`desmoke.py` parses the output from the [integration test runner `resmoke.py`](https://github.com/mongodb/mongo/wiki/Test-The-Mongodb-Server#test-using-resmokepy), or the [unit test runner](https://github.com/mongodb/mongo/wiki/Test-The-Mongodb-Server#running-c-unit-tests), and can output more human-readable log lines resembling

Usage is easy, just pipe the test output into `desmoke.py`. By default, desmoke will prefix its output with `[desmoke]` as it processes the file line-by-line, but you can optionally ask for a summary at the end of the output as well:

```bash
$ ./buildscripts/resmoke.py run [filename] | desmoke.py --summary
$ ninja +<unit test name> | desmoke.py --summary
```

This works nicely with `grep`, too:

```bash
$ ./buildscripts/resmoke.py run [filename] | desmoke.py | grep "[desmoke]"
```

To analyze past test runs, `desmoke.py` can read from a file:

```bash
$ ./buildscripts/resmoke.py run [filename] > test_output.log && desmoke.py --summary test_output.log
```

### Installation

`desmoke.py` is a single Python file. It has no dependencies, and works with the virtual environment used with MongoDB development (Python 3.9). You can download the git repository to make sure that you can always `git pull` to get any updates:

```
$ git clone https://github.com/davish/desmoke.git
$ export PATH="$(pwd)/desmoke:$PATH" # Add this line to your bash/zsh config to keep desmoke in your PATH
$ chmod +x desmoke/desmoke.py
```

### VSCode Integration

The main motivation for this project came from a desire for a better experience writing and debugging tests inside VSCode. VSCode has built-in support for [custom problem matchers](https://code.visualstudio.com/docs/editor/tasks#_defining-a-problem-matcher) that look at a program's output and highlight lines in source code as warnings and errors. The actual matchers themselves are limited by how they parse log output, and MongoDB's testing utilities don't produce compatible output. In addition to being more human-readable, `desmoke.py`'s output is built to be easily parsed with a single one-line regular expression for use inside VSCode.

Rather than leaving the regex mangling as an exercise for the reader, `desmoke.py` can easily install VSCode custom tasks
to run both jstests and C++ unit tests with just one command run from the project root:

```bash
$ desmoke.py --install
```

> Note that VSCode's JSON parser is noticeably more permissive than the JSON Spec that Python's JSON parser follows quite closely. If you get a JSON parse error when running the installation command, check your `.vscode/tasks.json` file for any invalid JSON, like trailing commas, comments, or single quotes.

To use the integration, open the Command Palette with the test file open and run `Tasks: Run Task` and select either `Desmoke: Run file as C++ unit test` or `Desmoke: Run file as jstest`.

### Example

Take this failing jstest:

```javascript
(function () {
  "use strict";
  let a = { message: { hello: "MongoDB World!", timestamp: "abc123" }, id: 1 };
  let b = { message: { hello: "MongoDB Live!", timestamp: "abc123" }, id: 1 };
  assert.eq(a, b, "Payloads should be equal.");
})();
```

Running it through `desmoke.py` with the following invocation:

```bash
./buildscripts/resmoke.py run jstests/failing_test.js | desmoke.py --summary
```

Produces this at the end of its output:

```
...
...
[executor] 18:37:18.211Z Summary of latest execution: 3 test(s) ran in 2.91 seconds (2 succeeded, 0 were skipped, 1 failed, 0 errored)
    The following tests failed (with exit code):
        jstests/failures.js (253 Failure executing JS file)
    If you're unsure where to begin investigating these errors, consider looking at tests in the following order:
        jstests/failures.js
[resmoke] 18:37:18.211Z ================================================================================
[resmoke] 18:37:18.211Z Summary of with_server suite: 3 test(s) ran in 2.91 seconds (2 succeeded, 0 were skipped, 1 failed, 0 errored)
The following tests failed (with exit code):
    jstests/failures.js (253 Failure executing JS file)
If you're unsure where to begin investigating these errors, consider looking at tests in the following order:
    jstests/failures.js
[resmoke] 18:37:18.211Z Exiting with code: 1
----
jstests/failures.js:6:1: error: assert equals failed:  Payloads should be equal. : [{"message": {"hello": "MongoDB World!", "timestamp": "abc123"}, "id": 1}] != [{"message": {"hello": "MongoDB Live!", "timestamp": "abc123"}, "id": 1}]
Diff:
Left:[{"message": {"hello": "MongoDB World!"}}]
Right:[{"message": {"hello": "MongoDB Live!"}}]
----
```

Here you can also see the custom parser for `assert.eq()` errors which outputs a diff along with the regular failure report.
