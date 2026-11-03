# AI DECISION TREE

```
Is the requirement clear?
       │
   ┌───┴───┐
   YES     NO
   │        │
   │        ▼
   │   Inspect PRD / functional specs
   │        │
   │        ▼
   │   Inspect decision log (ADRs)
   │        │
   │        ▼
   │   Choose the safest, most conventional
   │   option and document the assumption
   │
   ▼
Can existing code solve it?
       │
   ┌───┴───┐
   YES     NO
   │        │
 reuse    design
           │
           ▼
     smallest coherent change
           │
           ▼
          test
           │
           ▼
        verify
```
