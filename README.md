## desmoke.py
*Un-grepping the MongoDB maintainer experience*

### Summary
The output from MongoDB's test harnesses can be quite tedious to read directly in the terminal without some `grep` magic or careful manual combing to locate specific errors and false assertions during development. Since JavaScript is a dynamic language, actual programming errors in jstests are intermixed with assertion failures, and it can be difficult to find out why a test is failing at-a-glance.

`desmoke.py` parses the output from the [integration test runner `resmoke.py`](https://github.com/mongodb/mongo/wiki/Test-The-Mongodb-Server#test-using-resmokepy), or the [unit test runner](https://github.com/mongodb/mongo/wiki/Test-The-Mongodb-Server#running-c-unit-tests), and can output more human-readable log lines.

Usage is easy, just pipe the test output into `desmoke.py`. By default, desmoke will output logs as it processes the file line-by-line, but you can optionally ask for a summary at the end of the output as well:

```bash
$ ./buildscripts/resmoke.py run [filename] | ./desmoke.py --summary
$ ninja +<unit test name> | ./desmoke.py --summary
```

`desmoke.py` can also read from a file to analyze past test runs:
```bash
$ ./buildscripts/resmoke.py run [filename] > test_output.log && ./desmoke.py --summary test_output.log
```

### VSCode Integration
The main motivation for this project came from a desire for a better experience writing and debugging tests inside VSCode. VSCode has built-in support for [custom problem matchers](https://code.visualstudio.com/docs/editor/tasks#_defining-a-problem-matcher) that look at a program's output and highlight lines in source code as warnings and errors. The actual matchers themselves are limited by how they parse log output, and MongoDB's testing utilities don't produce compatible output. In addition to being more human-readable, `desmoke.py`'s output is built to be easily parsed with a single one-line regular expression for use inside VSCode.

Rather than leaving the regex mangling as an exercise for the reader, `desmoke.py` can easily install VSCode custom tasks
to run both jstests and C++ unit tests with just one command run from the project root:

```bash
$ ./desmoke.py --install
```

To use the integration, open the Command Palette with the test file open and run `Tasks: Run Task` and select either `Desmoke: Run file as C++ unit test` or `Desmoke: Run file as jstest`.
