## Your decision

Your final answer is the requested structured object:

```
{"coefficients": [
   {"instrument": "PF_XBTUSD", "coefficient": 0.5,
    "reason": "contract maintenance announcement at 14:00 UTC"}
 ],
 "validity_h": 4,
 "justification": "at most 600 characters"}
```

- `coefficients`: from 0 to 6 items. **An absent contract is worth 1** (the engine is followed). List only the contracts that are braked.
  - `coefficient`: `0`, `0.5` or `1` only; **every contract listed with 0 or 0.5 carries a factual `reason`** of at most 200 characters.
- `validity_h`: an integer from 1 to 4 (hours). It never goes beyond the next bar.
- `justification`: the overall reasoning in at most 600 characters. "Nothing abnormal, the engine is followed" is a valid justification.
