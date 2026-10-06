"""
skip_keywords.py — Robot Framework PreRunModifier

Removes specific keyword calls from test cases at runtime, **without
modifying the .robot file on disk**. Useful when a single test case
contains many keyword calls and you only want to skip a few of them
(e.g. the supplier .robot files where "Download the report from the
web portal" and "Send the excel file to the management" are keywords
inside one big test case, not separate test cases — Robot's built-in
--skip flag matches test names only, not keyword calls inside a test).

Lives at: /config/rpa/openclaw/Finance/Supplier/LCC/skip_keywords.py

Usage from the command line:
    robot --prerunmodifier /path/to/skip_keywords.py:Keyword Name 1:Keyword Name 2 \
          path/to/test.robot

Usage from nova_api.py:
    cmd = [ROBOT_CMD,
           "--prerunmodifier",
           f"{SKIP_KW_PATH}:{':'.join(supplier['skip_tests'])}",
           ...]

Args after the file path are colon-separated keyword names. Matching
is case-insensitive, exact (whole-name) match. Robot subprocess passes
each whole arg through without shell interpretation, so spaces in
keyword names are fine.

Behaviour:
  - Walks every test case in the suite tree.
  - For each test, removes any keyword call in its body whose name
    matches one of the names supplied on the command line.
  - Recurses into IF / FOR / TRY / WHILE blocks so a nested keyword
    call is also removed.
  - Leaves Setup / Teardown alone (they're rare and we don't want to
    accidentally drop a critical teardown).
  - The .robot file on disk is untouched. The scheduled job that runs
    the same .robot file without --prerunmodifier still executes the
    full flow; only on-demand runs from nova_api skip the requested
    keywords.
"""

from robot.api import SuiteVisitor


class skip_keywords(SuiteVisitor):
    def __init__(self, *names_to_skip):
        # Normalise: lowercase, strip whitespace. Empty entries dropped.
        self._skip = {n.strip().lower() for n in names_to_skip if n and n.strip()}
        self._removed_count = 0

    # ── SuiteVisitor hooks ─────────────────────────────────

    def start_suite(self, suite):
        for test in suite.tests:
            self._filter_body(test)
        # SuiteVisitor itself handles recursion into child suites,
        # so no need to walk suite.suites manually.

    def end_suite(self, suite):
        if self._removed_count:
            print(
                f"[skip_keywords] removed {self._removed_count} keyword call(s) "
                f"matching: {sorted(self._skip)}"
            )
            self._removed_count = 0  # reset between suites

    # ── internals ──────────────────────────────────────────

    def _filter_body(self, container):
        """Remove matching keyword calls from container.body, recursively."""
        if not hasattr(container, "body"):
            return
        kept = []
        for item in container.body:
            name = getattr(item, "name", None)
            if name and name.strip().lower() in self._skip:
                self._removed_count += 1
                continue
            # Recurse into IF / FOR / TRY / WHILE / Group bodies.
            self._filter_body(item)
            # Some control structures expose their branches differently.
            for attr in ("body", "orelse", "branches", "branch"):
                child = getattr(item, attr, None)
                if child is None or child is item.body:
                    continue
                # If it's iterable of containers, recurse into each.
                try:
                    for sub in child:
                        self._filter_body(sub)
                except TypeError:
                    pass
            kept.append(item)
        # In-place replacement preserves Body's special behaviour.
        container.body[:] = kept