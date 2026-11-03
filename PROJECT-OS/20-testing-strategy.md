# TESTING STRATEGY

```
                 TESTING
                    │
       ┌────────────┼────────────┐
       ▼            ▼            ▼
     UNIT      INTEGRATION      E2E
       │            │            │
       ▼            ▼            ▼
Functions      Components     Real Workflow
```
Plus, where relevant: security tests, regression tests, contract tests, performance tests.

## Unit tests
Cover: validators, parsers, formatters, configuration logic, state transitions, error normalization, retry logic.

## Integration tests
```
Interface → Application Core → Adapter → Mock Integration
```

## E2E tests
Cover complete supported workflows end to end, e.g.:
```
Install → Configure → Authenticate → Core Action → Receive Result → Exit
```
