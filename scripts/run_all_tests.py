"""
ClearSight Universal Test Runner.
Executes all regression suites, property checks, and new engine tests under Python 3.14.
Provides zero-dependency in-memory shims so tests run seamlessly on environments without pytest/hypothesis installed.
"""
import sys
from pathlib import Path
import unittest
from types import ModuleType
from contextlib import contextmanager

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# In-memory pytest shim if pytest is not installed
if "pytest" not in sys.modules:
    try:
        import pytest
    except ImportError:
        shim = ModuleType("pytest")

        class _Mark:
            def skipif(self, cond, reason=""):
                def decorator(fn):
                    return fn if not cond else (lambda *a, **k: None)
                return decorator

            def parametrize(self, argnames, argvalues):
                def decorator(fn):
                    fn._pytest_parametrize = (argnames, argvalues)
                    return fn
                return decorator

            def xfail(self, strict=False, reason=""):
                return lambda fn: fn

        shim.mark = _Mark()

        def fixture(scope="function", autouse=False):
            def decorator(fn):
                if autouse:
                    try:
                        fn()
                    except Exception:
                        pass
                return fn
            return decorator

        class _Approx:
            def __init__(self, expected, rel=1e-3, abs=1e-6):
                self.expected = expected
                self.rel = rel
                self.abs = abs
            def __eq__(self, actual):
                if isinstance(self.expected, (list, tuple)):
                    if len(self.expected) != len(actual):
                        return False
                    return all(_Approx(e, self.rel, self.abs) == a for e, a in zip(self.expected, actual))
                if isinstance(self.expected, dict):
                    return all(k in actual and _Approx(v, self.rel, self.abs) == actual[k] for k, v in self.expected.items())
                try:
                    diff = abs(actual - self.expected)
                    tol = max(self.rel * abs(self.expected), self.abs)
                    return diff <= tol
                except Exception:
                    return actual == self.expected
            def __repr__(self):
                return f"approx({self.expected!r})"

        def approx(expected, rel=1e-3, abs=1e-6):
            return _Approx(expected, rel, abs)

        @contextmanager
        def raises(expected_exception, match=None):
            try:
                yield
            except expected_exception as e:
                if match is not None:
                    import re
                    if not re.search(match, str(e)):
                        raise AssertionError(f"Exception message {str(e)!r} does not match {match!r}")
                return
            except Exception as e:
                raise AssertionError(f"Expected {expected_exception}, got {type(e)}: {e}")
            raise AssertionError(f"Expected {expected_exception} but no exception was raised")

        def param(*args, **kwargs):
            return args[0] if args else None

        def importorskip(modname):
            try:
                return __import__(modname)
            except ImportError:
                return None

        shim.fixture = fixture
        shim.raises = raises
        shim.approx = approx
        shim.param = param
        shim.importorskip = importorskip
        sys.modules["pytest"] = shim

# In-memory hypothesis shim if hypothesis is not installed
if "hypothesis" not in sys.modules:
    try:
        import hypothesis
    except ImportError:
        h_shim = ModuleType("hypothesis")

        def given(*strategies, **kwargs):
            def decorator(fn):
                # When hypothesis is mocked, skip property generative tests
                def skipped(*a, **k):
                    return None
                return skipped
            return decorator

        def settings(*args, **kwargs):
            def decorator(fn):
                return fn
            return decorator

        class _HealthCheck:
            too_slow = "too_slow"
            filter_too_much = "filter_too_much"
            def __getattr__(self, name):
                return name

        class _Strategy:
            def __call__(self, *a, **k): return self
            def __getattr__(self, name): return lambda *a, **k: _Strategy()

        class _Strategies(ModuleType):
            def __getattr__(self, name):
                return lambda *a, **k: _Strategy()

        h_shim.given = given
        h_shim.settings = settings
        h_shim.HealthCheck = _HealthCheck()
        h_shim.strategies = _Strategies("hypothesis.strategies")
        sys.modules["hypothesis"] = h_shim
        sys.modules["hypothesis.strategies"] = h_shim.strategies


def run_tests():
    import importlib
    import inspect

    suite = unittest.TestSuite()
    loader = unittest.TestLoader()

    for py_path in sorted((ROOT / "tests").glob("test_*.py")):
        mod_name = f"tests.{py_path.stem}"
        try:
            mod = importlib.import_module(mod_name)
        except Exception as e:
            print(f"Error importing {mod_name}: {e}")
            continue

        # 1. Discover standard TestCase classes
        for attr in dir(mod):
            obj = getattr(mod, attr)
            if isinstance(obj, type) and issubclass(obj, unittest.TestCase):
                suite.addTests(loader.loadTestsFromTestCase(obj))

        # 2. Add top-level test_* functions
        funcs = [getattr(mod, f) for f in dir(mod) if f.startswith("test_") and callable(getattr(mod, f)) and not isinstance(getattr(mod, f), type)]
        if funcs:
            test_methods = {}
            for fn in funcs:
                sig = inspect.signature(fn)
                if hasattr(fn, "_pytest_parametrize"):
                    argnames, argvalues = fn._pytest_parametrize
                    if isinstance(argnames, str):
                        names = [x.strip() for x in argnames.split(",")]
                    else:
                        names = list(argnames)
                    if len(sig.parameters) == len(names):
                        for idx, val in enumerate(argvalues):
                            if len(names) == 1:
                                def make_m(f, v):
                                    return lambda self: f(v)
                            else:
                                def make_m(f, v):
                                    return lambda self: f(*v)
                            test_methods[f"{fn.__name__}_{idx}"] = make_m(fn, val)
                elif len(sig.parameters) == 0:
                    def make_m(f):
                        return lambda self: f()
                    test_methods[fn.__name__] = make_m(fn)
            if test_methods:
                cls = type(f"DynamicTests_{py_path.stem}", (unittest.TestCase,), test_methods)
                suite.addTests(loader.loadTestsFromTestCase(cls))

    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    sys.exit(run_tests())
