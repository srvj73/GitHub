from __future__ import annotations
import importlib
import pathlib
import sys
import unittest

def fail(msg, code=2):
    print("UNITTEST_PATH_RUNNER_BLOCKED="+msg, flush=True)
    raise SystemExit(code)

def main():
    if len(sys.argv) < 3:
        fail("ARGS")
    workspace = pathlib.Path(sys.argv[1]).resolve()
    names = sys.argv[2:]
    if not workspace.is_dir():
        fail("WORKSPACE_MISSING")

    # -I intentionally omits CWD/script directory from sys.path.
    # The workspace is admitted explicitly and only once.
    ws = str(workspace)
    sys.path[:] = [p for p in sys.path if p != ws]
    sys.path.insert(0, ws)

    modules = []
    for name in names:
        if not name.isidentifier():
            fail("MODULE_NAME:"+name)
        expected = (workspace / (name + ".py")).resolve()
        if not expected.is_file():
            fail("MODULE_FILE_MISSING:"+name)
        mod = importlib.import_module(name)
        actual = pathlib.Path(mod.__file__).resolve()
        if actual != expected:
            fail("MODULE_ORIGIN_MISMATCH:"+name)
        modules.append(mod)

    loader = unittest.defaultTestLoader
    suite = unittest.TestSuite(loader.loadTestsFromModule(m) for m in modules)
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    raise SystemExit(0 if result.wasSuccessful() else 1)

if __name__ == "__main__":
    main()
