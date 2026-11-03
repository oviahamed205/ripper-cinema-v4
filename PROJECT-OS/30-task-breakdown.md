# TASK BREAKDOWN

Copy this block per task.

```
TASK-ID: TASK-XXX

TASK:
[one-line description]

WHY:
[reason / value]

RELATED REQUIREMENTS:
[PRD-XXX, FR-XXX, NFR-XXX]

FILES:
[files/directories touched]

DEPENDENCIES:
[other tasks that must land first]

IMPLEMENTATION:
[brief plan]

TESTS:
[what will be tested]

ACCEPTANCE CRITERIA:
- [ ] ...
- [ ] ...

RISKS:
[what could go wrong]

STATUS: Not Started / In Progress / Blocked / Done
```

## Example

```
TASK-001

TASK:
Create the integration adapter interface.

WHY:
Allow multiple external integrations without coupling the application core to any one of them.

RELATED:
FR-002, NFR-006

FILES:
src/integrations/
src/core/

TESTS:
- adapter interface contract test
- mock adapter test

ACCEPTANCE:
- [ ] Interface exists and is documented
- [ ] Mock implementation passes the contract test
- [ ] Application core depends only on the interface, not a concrete adapter

STATUS: Not Started
```
