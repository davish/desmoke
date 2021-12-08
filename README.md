## desmoke.py
*De-grepping the MongoDB maintainer experience*

### Summary
MongoDB's unit and integration test harnesses are comprehensive, but their output can be quite tedious to parse directly
in the terminal without some `grep` magic or careful combing to locate specific errors and false assertions during development. Since JavaScript is a dynamic language, actual programming errors in integration tests are intermixed with assertion failures, and it can be difficult to find out why a test is failing at-a-glance.

`desmoke.py` parses the output from the [integration test runner `resmoke.py`](https://github.com/mongodb/mongo/wiki/Test-The-Mongodb-Server#test-using-resmokepy), or the [unit test runner](https://github.com/mongodb/mongo/wiki/Test-The-Mongodb-Server#running-c-unit-tests), and can output more human-readable log lines.

Usage is easy, just pipe the test output into `desmoke.py` and ask for a summary at the end of the output:

```bash
./buildscripts/resmoke.py run --suite <suite name> <filename> | ./desmoke.py --summary
ninja +<unit test name> | ./desmoke.py --summary
```

`desmoke.py` can also read from file to analyze past test runs:
```bash
./buildscripts/resmoke.py run --suite <suite name> <filename> > test_output.log && ./desmoke.py --summary test_output.log
```

### VSCode Integration
The main motivation for this project came from a desire to integrate better into VSCode. VSCode has built-in support for [custom problem matchers](https://code.visualstudio.com/docs/editor/tasks#_defining-a-problem-matcher) that look at a program's output and highlight lines in source code as warnings and errors. The actual matchers themselves are limited by how they parse log output, and MongoDB's testing utilities don't produce compatible output. `desmoke.py`'s output *is* compatible, though!

Rather than leaving the regex mangling as an exercise for the reader, `desmoke.py` can easily install VSCode custom tasks
to compile and run unit tests with just one command run from the project root:

```bash
./desmoke.py --install
```

If you want to modify a file that isn't `./.vscode/tasks.json`, you can specify it after the arguments.

### Help
```
$ ./desmoke.py --help
usage: desmoke.py [-h] [--summary | --only] [--filetype {js,cpp}] [--install] [filename]

Prettify resmoke output.

positional arguments:
  filename              File to use as input. If not provided, desmoke.py will read from stdin. In install mode, this file is used as output.

optional arguments:
  -h, --help            show this help message and exit
  --summary             Report a summary at the end of the output.
  --only                Only send desmoke.py output to stdout without forwarding the input file or stream.
  --filetype {resmoke,cppunit}
                        Force a certain log parser. By default, desmoke.py will make a best guess based on the first log line.
  --install             Adds tasks to vscode's tasks.json to enable VSCode integration. Defaults to .vscode/tasks.json if no filename is provided.
```
