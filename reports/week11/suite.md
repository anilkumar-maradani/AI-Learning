# Suite output: RED before the fix, GREEN after

Runner: `python evals/week11.py suite --version V --label L`. Cases: the same first 10 Week-6 cases Week 10 raced, plus the regression cases in `evals/cases/week11_regressions.jsonl`. Grading is code-checked from each case's own fields: decision, every exclusion the adjuster relied on, the deductible applied and, where stated, the payable. No judge, so judge noise cannot flip a RED or a GREEN.

## Run 1: the drill-1 failure (W11-1), 11 cases

### RED, before the fix (workflow-v2)

```
Week 11 suite, label=before, workflow version=workflow-v2, run 2026-11-03T09:17:17+00:00
cases: the first 10 Week-6 cases (same 10 as Week 10) + 1 regression case(s) from evals/cases/week11_regressions.jsonl

  case  claim           expected                   got                                    result
     1  CLM-2026-10001  covered                    covered - pay=3600.0                   PASS
     2  CLM-2026-10002  excluded E-41              excluded E-41 pay=0.0                  PASS
     3  CLM-2026-10003  partially_covered E-63     partially_covered E-63 pay=1800.0      PASS
     4  CLM-2026-10004  covered                    needs_info - pay=None                  FAIL  decision needs_info != covered; deductible None != 6000
     5  CLM-2026-10005  excluded E-52              excluded E-52 pay=0.0                  PASS
     6  CLM-2026-10006  covered                    covered - pay=6200.0                   PASS
     7  CLM-2026-10007  excluded E-73              excluded E-73 pay=0.0                  PASS
     8  CLM-2026-10008  excluded E-83              excluded - pay=0.0                     FAIL  missing E-83
     9  CLM-2026-10009  excluded E-44              excluded E-44 pay=0.0                  PASS
    10  CLM-2026-10010  partially_covered E-45     partially_covered - pay=1900.0         FAIL  missing E-45
 W11-1  CLM-2026-10011  partially_covered E-93     partially_covered - pay=800.0          FAIL  missing E-93

Week-6 cases      : 7/10
regression cases  : 0/1
SUITE             : 7/11  RED
tokens 17,260  cost $0.00592
```

### GREEN for W11-1, after the fix (workflow-v3)

```
Week 11 suite, label=after, workflow version=workflow-v3, run 2026-11-03T09:21:48+00:00
cases: the first 10 Week-6 cases (same 10 as Week 10) + 1 regression case(s) from evals/cases/week11_regressions.jsonl

  case  claim           expected                   got                                    result
     1  CLM-2026-10001  covered                    covered - pay=3600.0                   PASS
     2  CLM-2026-10002  excluded E-41              excluded E-41 pay=0.0                  PASS
     3  CLM-2026-10003  partially_covered E-63     partially_covered E-63 pay=1800.0      PASS
     4  CLM-2026-10004  covered                    needs_info - pay=None                  FAIL  decision needs_info != covered; deductible None != 6000
     5  CLM-2026-10005  excluded E-52              excluded E-52 pay=0.0                  PASS
     6  CLM-2026-10006  covered                    covered - pay=6200.0                   PASS
     7  CLM-2026-10007  excluded E-73              excluded E-73 pay=0.0                  PASS
     8  CLM-2026-10008  excluded E-83              excluded E-83 pay=0.0                  PASS
     9  CLM-2026-10009  excluded E-44              excluded E-44 pay=0.0                  PASS
    10  CLM-2026-10010  partially_covered E-45     partially_covered E-45 pay=1900.0      PASS
 W11-1  CLM-2026-10011  partially_covered E-93     partially_covered E-93 pay=800.0       PASS

Week-6 cases      : 9/10
regression cases  : 1/1
SUITE             : 10/11  RED
tokens 21,191  cost $0.00657
```

```
suite before (workflow-v2) -> after (workflow-v3): 7/11 -> 10/11
  regressed (PASS -> FAIL)    0  -
  fixed (FAIL -> PASS)        3  8 CLM-2026-10008; 10 CLM-2026-10010; W11-1 CLM-2026-10011
  still failing               1  4 CLM-2026-10004 (decision needs_info != covered; deductible None != 6000)
  still passing               7  1 CLM-2026-10001; 2 CLM-2026-10002; 3 CLM-2026-10003; 5 CLM-2026-10005; 6 CLM-2026-10006; 7 CLM-2026-10007; 9 CLM-2026-10009
```

**7/11 → 10/11. W11-1 went RED → GREEN, and 0 cases regressed.** The one failure left, case 4 (the hurricane-deductible case), failed with the same `needs_info` before and after the fix, so the fix did not break it.

## Run 2: after drill 2 added W11-2, 12 cases (fresh runs of both versions)

### RED, before the fix (workflow-v2)

```
Week 11 suite, label=before2, workflow version=workflow-v2, run 2026-11-03T09:29:37+00:00
cases: the first 10 Week-6 cases (same 10 as Week 10) + 2 regression case(s) from evals/cases/week11_regressions.jsonl

  case  claim           expected                   got                                    result
     1  CLM-2026-10001  covered                    covered - pay=3600.0                   PASS
     2  CLM-2026-10002  excluded E-41              excluded E-41 pay=0.0                  PASS
     3  CLM-2026-10003  partially_covered E-63     partially_covered E-63 pay=1800.0      PASS
     4  CLM-2026-10004  covered                    needs_info - pay=None                  FAIL  decision needs_info != covered; deductible None != 6000
     5  CLM-2026-10005  excluded E-52              excluded E-52 pay=0.0                  PASS
     6  CLM-2026-10006  covered                    covered - pay=6200.0                   PASS
     7  CLM-2026-10007  excluded E-73              excluded E-73 pay=0.0                  PASS
     8  CLM-2026-10008  excluded E-83              excluded - pay=0.0                     FAIL  missing E-83
     9  CLM-2026-10009  excluded E-44              excluded E-44 pay=0.0                  PASS
    10  CLM-2026-10010  partially_covered E-45     covered - pay=2350.0                   FAIL  decision covered != partially_covered; missing E-45
 W11-1  CLM-2026-10011  partially_covered E-93     partially_covered - pay=2500.0         FAIL  missing E-93; payable 2500.0 != 800
 W11-2  CLM-2026-10014  excluded E-46              excluded - pay=0.0                     FAIL  missing E-46

Week-6 cases      : 7/10
regression cases  : 0/2
SUITE             : 7/12  RED
tokens 19,302  cost $0.00677
```

### GREEN, after the fix (workflow-v3)

```
Week 11 suite, label=after2, workflow version=workflow-v3, run 2026-11-03T09:33:10+00:00
cases: the first 10 Week-6 cases (same 10 as Week 10) + 2 regression case(s) from evals/cases/week11_regressions.jsonl

  case  claim           expected                   got                                    result
     1  CLM-2026-10001  covered                    covered - pay=3600.0                   PASS
     2  CLM-2026-10002  excluded E-41              excluded E-41 pay=0.0                  PASS
     3  CLM-2026-10003  partially_covered E-63     partially_covered E-63 pay=1800.0      PASS
     4  CLM-2026-10004  covered                    covered - pay=7200.0                   PASS
     5  CLM-2026-10005  excluded E-52              excluded E-52 pay=0.0                  PASS
     6  CLM-2026-10006  covered                    covered - pay=6200.0                   PASS
     7  CLM-2026-10007  excluded E-73              excluded E-73 pay=0.0                  PASS
     8  CLM-2026-10008  excluded E-83              excluded E-83 pay=0.0                  PASS
     9  CLM-2026-10009  excluded E-44              excluded E-44 pay=0.0                  PASS
    10  CLM-2026-10010  partially_covered E-45     partially_covered E-45 pay=1900.0      PASS
 W11-1  CLM-2026-10011  partially_covered E-93     partially_covered E-93 pay=800.0       PASS
 W11-2  CLM-2026-10014  excluded E-46              excluded E-46 pay=0.0                  PASS

Week-6 cases      : 10/10
regression cases  : 2/2
SUITE             : 12/12  GREEN
tokens 22,920  cost $0.00697
```

```
suite before2 (workflow-v2) -> after2 (workflow-v3): 7/12 -> 12/12
  regressed (PASS -> FAIL)    0  -
  fixed (FAIL -> PASS)        5  4 CLM-2026-10004; 8 CLM-2026-10008; 10 CLM-2026-10010; W11-1 CLM-2026-10011; W11-2 CLM-2026-10014
  still failing               0  -
  still passing               7  1 CLM-2026-10001; 2 CLM-2026-10002; 3 CLM-2026-10003; 5 CLM-2026-10005; 6 CLM-2026-10006; 7 CLM-2026-10007; 9 CLM-2026-10009
```

**7/12 → 12/12, 0 regressions. Both regression cases went RED → GREEN.**

## Read these honestly

- **Case 4 is flaky, not fixed.** It failed (`needs_info`) in 3 of the 4 runs, including the first v3 run, and passed in the last one. v3 does not touch the hurricane-deductible path, so do not count it as a win for the fix. It is the deductible case: a fix that changed it would be suspect.
- **Same input, different answer at temperature 0.** On the identical W11-1 input, production paid $2,500 and the first suite run paid $800 (still with no E-93). Case 10 under v2 was `partially_covered $1,900` in run 1 and `covered $2,350` in run 2. W11-1 stays RED on v2 regardless, because the cause is deterministic: retrieval never puts the E-93 row in front of the model, so the model cannot cite it.
- **Cases 8, 10, W11-1 and W11-2 turned GREEN in both v3 runs.** In all four, the exclusion row never reached the model on v2 (checked against each run's context ids in `suite_before*.jsonl`):
  - case 8: NG-1105's table was never retrieved (only NG-1101's), so E-83 was missing;
  - case 10: no exclusion table at all was retrieved, so E-45 was missing;
  - W11-1: neither form's table was retrieved, so E-93 was missing;
  - W11-2: NG-1101's table was retrieved but cut at 900 characters, so E-46 was missing.
