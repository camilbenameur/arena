# Wave 1

Internal report: it contains figures and is not given to any research agent. The agents receive only `wave-1-statuses.json`.

Grid trials: 45; extra rows (arena, control): 0; of which re-read from the journal without a rerun (resume): 0; actual N in the journal: 45; N for the DSR: 726.
Best DSR: 0.4201. Stop rule triggered: yes.

## All trials

| id | family | parameters | code | net Sharpe | failed gates | pass |
|---|---|---|---|---|---|---|
| R0001 | c-persistent-carry | {entry: 0.09, exit_ratio: 0.2} | OK | 0.425 | C1, C5, C7, C8, C11, C12, C13, C14, C16, C2, C3, C4, C10 | no |
| R0002 | c-persistent-carry | {entry: 0.09, exit_ratio: 0.4} | OK | -0.07978 | C1, C5, C7, C8, C11, C12, C13, C14, C16, C2, C3, C4, C10 | no |
| R0003 | c-persistent-carry | {entry: 0.09, exit_ratio: 0.8} | OK | -0.6915 | C1, C5, C6, C7, C8, C11, C12, C13, C14, C16, C2, C3, C4, C10 | no |
| R0004 | c-persistent-carry | {entry: 0.135, exit_ratio: 0.2} | OK | 1.246 | C1, C5, C7, C8, C11, C12, C13, C14, C16, C3, C4, C10 | no |
| R0005 | c-persistent-carry | {entry: 0.135, exit_ratio: 0.4} | OK | 0.8678 | C1, C5, C7, C8, C11, C12, C13, C14, C16, C3, C4, C10 | no |
| R0006 | c-persistent-carry | {entry: 0.135, exit_ratio: 0.8} | OK | 0.4414 | C1, C5, C7, C8, C11, C12, C13, C14, C16, C2, C3, C4, C10 | no |
| R0007 | c-persistent-carry | {entry: 0.2, exit_ratio: 0.2} | OK | 1.235 | C1, C5, C7, C8, C11, C12, C13, C14, C16, C3, C4, C10 | no |
| R0008 | c-persistent-carry | {entry: 0.2, exit_ratio: 0.4} | OK | 1.164 | C1, C5, C7, C8, C11, C12, C13, C14, C16, C3, C4, C10 | no |
| R0009 | c-persistent-carry | {entry: 0.2, exit_ratio: 0.8} | OK | 0.3942 | C1, C5, C7, C8, C11, C12, C13, C14, C16, C2, C3, C4, C10 | no |
| R0010 | c-rank-carry | {k: 2, buffer: 1} | OK | -1.539 | C1, C5, C6, C7, C8, C11, C12, C13, C14, C16, C2, C3, C4, C10 | no |
| R0011 | c-rank-carry | {k: 2, buffer: 2} | OK | -0.8742 | C1, C5, C6, C7, C8, C11, C12, C13, C14, C16, C2, C3, C4, C10 | no |
| R0012 | c-rank-carry | {k: 2, buffer: 4} | OK | -0.2583 | C1, C5, C6, C7, C8, C11, C12, C13, C14, C16, C2, C3, C4, C10 | no |
| R0013 | c-rank-carry | {k: 3, buffer: 1} | OK | -1.345 | C1, C5, C6, C7, C8, C11, C12, C13, C14, C16, C2, C3, C4, C10 | no |
| R0014 | c-rank-carry | {k: 3, buffer: 2} | OK | -0.5806 | C1, C5, C6, C7, C8, C11, C12, C13, C14, C16, C2, C3, C4, C10 | no |
| R0015 | c-rank-carry | {k: 3, buffer: 4} | OK | -0.1744 | C1, C5, C6, C7, C8, C11, C12, C13, C14, C16, C2, C3, C4, C10 | no |
| R0016 | c-rank-carry | {k: 5, buffer: 1} | OK | -0.7179 | C1, C5, C6, C7, C8, C11, C12, C13, C14, C16, C2, C3, C4, C10 | no |
| R0017 | c-rank-carry | {k: 5, buffer: 2} | OK | -0.6193 | C1, C5, C6, C7, C8, C11, C12, C13, C14, C16, C2, C3, C4, C10 | no |
| R0018 | c-rank-carry | {k: 5, buffer: 4} | OK | -0.382 | C1, C5, C6, C7, C8, C11, C12, C13, C14, C16, C2, C3, C4, C10 | no |
| R0019 | c-carry-regime | {entry: 0.09, extreme_cap: 0.25} | OK | -4.489 | C1, C5, C6, C7, C8, C11, C12, C13, C14, C16, C2, C3, C4, C10 | no |
| R0020 | c-carry-regime | {entry: 0.09, extreme_cap: 0.5} | OK | -2.315 | C1, C5, C6, C7, C8, C11, C12, C13, C14, C16, C2, C3, C4, C10 | no |
| R0021 | c-carry-regime | {entry: 0.09, extreme_cap: 1} | OK | -0.4901 | C1, C5, C7, C8, C11, C12, C13, C14, C16, C2, C3, C4, C10 | no |
| R0022 | c-carry-regime | {entry: 0.135, extreme_cap: 0.25} | OK | -3.895 | C1, C5, C6, C7, C8, C11, C12, C13, C14, C16, C2, C3, C4, C10 | no |
| R0023 | c-carry-regime | {entry: 0.135, extreme_cap: 0.5} | OK | -1.596 | C1, C5, C7, C8, C11, C12, C13, C14, C16, C2, C3, C4, C10 | no |
| R0024 | c-carry-regime | {entry: 0.135, extreme_cap: 1} | OK | 0.4515 | C1, C5, C7, C8, C11, C12, C13, C14, C16, C2, C3, C4, C10 | no |
| R0025 | c-carry-regime | {entry: 0.2, extreme_cap: 0.25} | OK | -3.835 | C1, C5, C6, C7, C8, C11, C12, C13, C14, C16, C2, C3, C4, C10 | no |
| R0026 | c-carry-regime | {entry: 0.2, extreme_cap: 0.5} | OK | -1.528 | C1, C5, C7, C8, C11, C12, C13, C14, C16, C2, C3, C4, C10 | no |
| R0027 | c-carry-regime | {entry: 0.2, extreme_cap: 1} | OK | 0.7327 | C1, C5, C7, C8, C11, C12, C13, C14, C16, C3, C4, C10 | no |
| R0028 | m-semivar | {L_days: 14, s: 0.1} | OK | 1.064 | C1, C5, C6, C7, C8, C11, C12, C15, C16 | no |
| R0029 | m-semivar | {L_days: 14, s: 0.2} | OK | 1.058 | C1, C5, C6, C7, C8, C11, C15, C16 | no |
| R0030 | m-semivar | {L_days: 14, s: 0.4} | OK | 0.6721 | C1, C5, C6, C7, C8, C9, C11, C15, C16, C3, C10 | no |
| R0031 | m-semivar | {L_days: 28, s: 0.1} | OK | 1.161 | C1, C6, C7, C8, C11, C15, C16 | no |
| R0032 | m-semivar | {L_days: 28, s: 0.2} | OK | 0.7992 | C1, C5, C6, C8, C11, C15, C16, C3 | no |
| R0033 | m-semivar | {L_days: 28, s: 0.4} | OK | 0.6199 | C1, C6, C7, C8, C9, C11, C15, C16, C3, C10 | no |
| R0034 | m-semivar | {L_days: 56, s: 0.1} | OK | 0.7191 | C1, C5, C6, C7, C8, C11, C15, C16, C3, C10 | no |
| R0035 | m-semivar | {L_days: 56, s: 0.2} | OK | 0.6628 | C1, C5, C6, C7, C8, C11, C15, C16, C3, C10 | no |
| R0036 | m-semivar | {L_days: 56, s: 0.4} | OK | 0.9058 | C1, C7, C8, C9, C11, C15, C16 | no |
| R0037 | r-crowded-funding | {L: 7, q: 0.5} | OK | 0.7057 | C1, C5, C6, C7, C8, C11, C15, C16, C3 | no |
| R0038 | r-crowded-funding | {L: 7, q: 0.7} | OK | 0.6733 | C1, C5, C6, C7, C8, C11, C15, C16, C3 | no |
| R0039 | r-crowded-funding | {L: 7, q: 0.9} | OK | 0.8252 | C1, C5, C6, C7, C8, C11, C15, C16 | no |
| R0040 | r-crowded-funding | {L: 14, q: 0.5} | OK | 0.6764 | C1, C5, C6, C7, C8, C11, C15, C16, C3 | no |
| R0041 | r-crowded-funding | {L: 14, q: 0.7} | OK | 0.6535 | C1, C5, C6, C8, C11, C15, C16, C3 | no |
| R0042 | r-crowded-funding | {L: 14, q: 0.9} | OK | 0.7766 | C1, C5, C6, C7, C8, C11, C15, C16, C3 | no |
| R0043 | r-crowded-funding | {L: 28, q: 0.5} | OK | 0.6227 | C1, C5, C6, C7, C8, C11, C15, C16, C3, C10 | no |
| R0044 | r-crowded-funding | {L: 28, q: 0.7} | OK | 0.6219 | C1, C5, C6, C7, C8, C11, C15, C16, C3, C10 | no |
| R0045 | r-crowded-funding | {L: 28, q: 0.9} | OK | 0.6133 | C1, C5, C6, C7, C8, C11, C15, C16, C3, C10 | no |

## Detailed verdicts

C16: measure = (share, positives, evaluable, not evaluable, size of the control universe); the share is relative to the fixed size of the universe.

### R0001 (c-persistent-carry {entry: 0.09, exit_ratio: 0.2})
- C1: FAIL ; measure 1.334e-29 ; threshold 0.95
- C5: FAIL ; measure {2020: 2.223, 2021: 6.904, 2022: -5.748, 2023: -2.607, 2024: 1.179, 2025: -5.707} ; threshold {sharpe_min: -1, positives_min: 4}
- C6: OK ; measure 0.1379 ; threshold 0.2
- C7: FAIL ; measure None ; threshold {min_neighbors_share: 0.75, ratio: 0.6, min_neighbor_sharpe: 0.5}
- C8: FAIL ; measure (0.5139, -0.001167) ; threshold (2, 0.3)
- C9: OK ; measure 0 ; threshold {random_cuts: 20, fixed_cuts: 3, not_full_share_min: 0.4, tolerance: 1e-09}
- C11: FAIL ; measure (-0.5668, -1.284) ; threshold (0.5, 0)
- C12: FAIL ; measure (0.9388, 23.21) ; threshold (0.5, 40)
- C13: FAIL ; measure (1.807, -2.236) ; threshold 0
- C14: FAIL ; measure 0.005627 ; threshold 0.04
- C15: OK ; measure not applicable (hedged) ; threshold None
- C16: FAIL ; measure None ; threshold 0.6
- C2: FAIL ; measure 0.425 ; threshold 0.5
- C3: FAIL ; measure 0.4397 ; threshold 2
- C4: FAIL ; measure -4.33 ; threshold 0
- C10: FAIL ; measure 0.3189 ; threshold 0.05

### R0002 (c-persistent-carry {entry: 0.09, exit_ratio: 0.4})
- C1: FAIL ; measure 9.412e-37 ; threshold 0.95
- C5: FAIL ; measure {2020: 2.136, 2021: 6.616, 2022: -4.509, 2023: -3.531, 2024: -1.574, 2025: -5.202} ; threshold {sharpe_min: -1, positives_min: 4}
- C6: OK ; measure 0.1748 ; threshold 0.2
- C7: FAIL ; measure None ; threshold {min_neighbors_share: 0.75, ratio: 0.6, min_neighbor_sharpe: 0.5}
- C8: FAIL ; measure (-0.02738, -0.001032) ; threshold (2, 0.3)
- C9: OK ; measure 0 ; threshold {random_cuts: 20, fixed_cuts: 3, not_full_share_min: 0.4, tolerance: 1e-09}
- C11: FAIL ; measure (-1.041, -1.704) ; threshold (0.5, 0)
- C12: FAIL ; measure (1.013, 22.95) ; threshold (0.5, 40)
- C13: FAIL ; measure (1.718, -2.965) ; threshold 0
- C14: FAIL ; measure -0.001267 ; threshold 0.04
- C15: OK ; measure not applicable (hedged) ; threshold None
- C16: FAIL ; measure None ; threshold 0.6
- C2: FAIL ; measure -0.07978 ; threshold 0.5
- C3: FAIL ; measure -0.08444 ; threshold 2
- C4: FAIL ; measure -3.948 ; threshold 0
- C10: FAIL ; measure 0.5315 ; threshold 0.05

### R0003 (c-persistent-carry {entry: 0.09, exit_ratio: 0.8})
- C1: FAIL ; measure 2.166e-48 ; threshold 0.95
- C5: FAIL ; measure {2020: 1.122, 2021: 5.764, 2022: -4.313, 2023: -4.608, 2024: -2.385, 2025: -4.617} ; threshold {sharpe_min: -1, positives_min: 4}
- C6: FAIL ; measure 0.2133 ; threshold 0.2
- C7: FAIL ; measure None ; threshold {min_neighbors_share: 0.75, ratio: 0.6, min_neighbor_sharpe: 0.5}
- C8: FAIL ; measure (-0.7358, -0.0008204) ; threshold (2, 0.3)
- C9: OK ; measure 0 ; threshold {random_cuts: 20, fixed_cuts: 3, not_full_share_min: 0.4, tolerance: 1e-09}
- C11: FAIL ; measure (-1.615, -2.227) ; threshold (0.5, 0)
- C12: FAIL ; measure (1.127, 24.81) ; threshold (0.5, 40)
- C13: FAIL ; measure (1.01, -3.305) ; threshold 0
- C14: FAIL ; measure -0.01107 ; threshold 0.04
- C15: OK ; measure not applicable (hedged) ; threshold None
- C16: FAIL ; measure None ; threshold 0.6
- C2: FAIL ; measure -0.6915 ; threshold 0.5
- C3: FAIL ; measure -0.7703 ; threshold 2
- C4: FAIL ; measure -4.197 ; threshold 0
- C10: FAIL ; measure 0.7946 ; threshold 0.05

### R0004 (c-persistent-carry {entry: 0.135, exit_ratio: 0.2})
- C1: FAIL ; measure 4.711e-19 ; threshold 0.95
- C5: FAIL ; measure {2020: 2.167, 2021: 6.758, 2022: -3.499, 2023: -1.828, 2024: 1.412, 2025: -3.812} ; threshold {sharpe_min: -1, positives_min: 4}
- C6: OK ; measure 0.07588 ; threshold 0.2
- C7: FAIL ; measure None ; threshold {min_neighbors_share: 0.75, ratio: 0.6, min_neighbor_sharpe: 0.5}
- C8: FAIL ; measure (1.362, -0.001011) ; threshold (2, 0.3)
- C9: OK ; measure 0 ; threshold {random_cuts: 20, fixed_cuts: 3, not_full_share_min: 0.4, tolerance: 1e-09}
- C11: FAIL ; measure (0.3458, -0.3416) ; threshold (0.6229, 0)
- C12: FAIL ; measure (0.8093, 17.88) ; threshold (0.5, 40)
- C13: FAIL ; measure (2.664, -1.283) ; threshold 0
- C14: FAIL ; measure 0.01618 ; threshold 0.04
- C15: OK ; measure not applicable (hedged) ; threshold None
- C16: FAIL ; measure None ; threshold 0.6
- C2: OK ; measure 1.246 ; threshold 0.5
- C3: FAIL ; measure 1.282 ; threshold 2
- C4: FAIL ; measure -2.835 ; threshold 0
- C10: FAIL ; measure 0.09778 ; threshold 0.05

### R0005 (c-persistent-carry {entry: 0.135, exit_ratio: 0.4})
- C1: FAIL ; measure 5.173e-23 ; threshold 0.95
- C5: FAIL ; measure {2020: 1.773, 2021: 5.414, 2022: -2.454, 2023: -1.963, 2024: -0.6901, 2025: -3.361} ; threshold {sharpe_min: -1, positives_min: 4}
- C6: OK ; measure 0.09418 ; threshold 0.2
- C7: FAIL ; measure 0.5 ; threshold {min_neighbors_share: 0.75, ratio: 0.6, min_neighbor_sharpe: 0.5}
- C8: FAIL ; measure (1.003, -0.001029) ; threshold (2, 0.3)
- C9: OK ; measure 0 ; threshold {random_cuts: 20, fixed_cuts: 3, not_full_share_min: 0.4, tolerance: 1e-09}
- C11: FAIL ; measure (-0.02455, -0.6845) ; threshold (0.5, 0)
- C12: FAIL ; measure (0.8538, 17.52) ; threshold (0.5, 40)
- C13: FAIL ; measure (2.221, -1.549) ; threshold 0
- C14: FAIL ; measure 0.01192 ; threshold 0.04
- C15: OK ; measure not applicable (hedged) ; threshold None
- C16: FAIL ; measure None ; threshold 0.6
- C2: OK ; measure 0.8678 ; threshold 0.5
- C3: FAIL ; measure 0.9272 ; threshold 2
- C4: FAIL ; measure -2.771 ; threshold 0
- C10: FAIL ; measure 0.1668 ; threshold 0.05

### R0006 (c-persistent-carry {entry: 0.135, exit_ratio: 0.8})
- C1: FAIL ; measure 3.498e-28 ; threshold 0.95
- C5: FAIL ; measure {2020: 0.06809, 2021: 4.563, 2022: -1.064, 2023: -2.231, 2024: -1.637, 2025: -2.153} ; threshold {sharpe_min: -1, positives_min: 4}
- C6: OK ; measure 0.1002 ; threshold 0.2
- C7: FAIL ; measure None ; threshold {min_neighbors_share: 0.75, ratio: 0.6, min_neighbor_sharpe: 0.5}
- C8: FAIL ; measure (0.5432, -0.0007719) ; threshold (2, 0.3)
- C9: OK ; measure 0 ; threshold {random_cuts: 20, fixed_cuts: 3, not_full_share_min: 0.4, tolerance: 1e-09}
- C11: FAIL ; measure (-0.4658, -1.088) ; threshold (0.5, 0)
- C12: FAIL ; measure (0.9139, 17.61) ; threshold (0.5, 40)
- C13: FAIL ; measure (1.523, -1.596) ; threshold 0
- C14: FAIL ; measure 0.006315 ; threshold 0.04
- C15: OK ; measure not applicable (hedged) ; threshold None
- C16: FAIL ; measure None ; threshold 0.6
- C2: FAIL ; measure 0.4414 ; threshold 0.5
- C3: FAIL ; measure 0.4873 ; threshold 2
- C4: FAIL ; measure -2.66 ; threshold 0
- C10: FAIL ; measure 0.3083 ; threshold 0.05

### R0007 (c-persistent-carry {entry: 0.2, exit_ratio: 0.2})
- C1: FAIL ; measure 5.893e-19 ; threshold 0.95
- C5: FAIL ; measure {2020: 2.19, 2021: 6.476, 2022: -2.684, 2023: -1.265, 2024: -0.8912, 2025: -3.44} ; threshold {sharpe_min: -1, positives_min: 4}
- C6: OK ; measure 0.07786 ; threshold 0.2
- C7: FAIL ; measure None ; threshold {min_neighbors_share: 0.75, ratio: 0.6, min_neighbor_sharpe: 0.5}
- C8: FAIL ; measure (1.333, -0.000635) ; threshold (2, 0.3)
- C9: OK ; measure 0 ; threshold {random_cuts: 20, fixed_cuts: 3, not_full_share_min: 0.4, tolerance: 1e-09}
- C11: FAIL ; measure (0.3287, -0.3625) ; threshold (0.6174, 0)
- C12: FAIL ; measure (0.7965, 16.23) ; threshold (0.5, 40)
- C13: FAIL ; measure (2.826, -1.597) ; threshold 0
- C14: FAIL ; measure 0.01585 ; threshold 0.04
- C15: OK ; measure not applicable (hedged) ; threshold None
- C16: FAIL ; measure None ; threshold 0.6
- C2: OK ; measure 1.235 ; threshold 0.5
- C3: FAIL ; measure 1.265 ; threshold 2
- C4: FAIL ; measure -2.447 ; threshold 0
- C10: FAIL ; measure 0.102 ; threshold 0.05

### R0008 (c-persistent-carry {entry: 0.2, exit_ratio: 0.4})
- C1: FAIL ; measure 7.493e-19 ; threshold 0.95
- C5: FAIL ; measure {2020: 1.522, 2021: 5.767, 2022: -2.441, 2023: -1.265, 2024: -0.8121, 2025: -2.594} ; threshold {sharpe_min: -1, positives_min: 4}
- C6: OK ; measure 0.07255 ; threshold 0.2
- C7: FAIL ; measure None ; threshold {min_neighbors_share: 0.75, ratio: 0.6, min_neighbor_sharpe: 0.5}
- C8: FAIL ; measure (1.267, -0.00028) ; threshold (2, 0.3)
- C9: OK ; measure 0 ; threshold {random_cuts: 20, fixed_cuts: 3, not_full_share_min: 0.4, tolerance: 1e-09}
- C11: FAIL ; measure (0.2715, -0.4025) ; threshold (0.5821, 0)
- C12: FAIL ; measure (0.7947, 15.44) ; threshold (0.5, 40)
- C13: FAIL ; measure (2.532, -1.348) ; threshold 0
- C14: FAIL ; measure 0.01536 ; threshold 0.04
- C15: OK ; measure not applicable (hedged) ; threshold None
- C16: FAIL ; measure None ; threshold 0.6
- C2: OK ; measure 1.164 ; threshold 0.5
- C3: FAIL ; measure 1.218 ; threshold 2
- C4: FAIL ; measure -2.204 ; threshold 0
- C10: FAIL ; measure 0.111 ; threshold 0.05

### R0009 (c-persistent-carry {entry: 0.2, exit_ratio: 0.8})
- C1: FAIL ; measure 6.193e-29 ; threshold 0.95
- C5: FAIL ; measure {2020: 0.6301, 2021: 3.426, 2022: 0, 2023: -1.265, 2024: -3.221, 2025: -1.596} ; threshold {sharpe_min: -1, positives_min: 4}
- C6: OK ; measure 0.1129 ; threshold 0.2
- C7: FAIL ; measure None ; threshold {min_neighbors_share: 0.75, ratio: 0.6, min_neighbor_sharpe: 0.5}
- C8: FAIL ; measure (0.4787, -0.0003595) ; threshold (2, 0.3)
- C9: OK ; measure 0 ; threshold {random_cuts: 20, fixed_cuts: 3, not_full_share_min: 0.4, tolerance: 1e-09}
- C11: FAIL ; measure (-0.5164, -1.152) ; threshold (0.5, 0)
- C12: FAIL ; measure (0.9166, 16.35) ; threshold (0.5, 40)
- C13: FAIL ; measure (1.643, -2.097) ; threshold 0
- C14: FAIL ; measure 0.005717 ; threshold 0.04
- C15: OK ; measure not applicable (hedged) ; threshold None
- C16: FAIL ; measure None ; threshold 0.6
- C2: FAIL ; measure 0.3942 ; threshold 0.5
- C3: FAIL ; measure 0.4452 ; threshold 2
- C4: FAIL ; measure -2.42 ; threshold 0
- C10: FAIL ; measure 0.3261 ; threshold 0.05

### R0010 (c-rank-carry {k: 2, buffer: 1})
- C1: FAIL ; measure 3.486e-69 ; threshold 0.95
- C5: FAIL ; measure {2020: -0.1983, 2021: 3.702, 2022: -3.424, 2023: -5.592, 2024: -4.364, 2025: -3.523} ; threshold {sharpe_min: -1, positives_min: 4}
- C6: FAIL ; measure 0.33 ; threshold 0.2
- C7: FAIL ; measure None ; threshold {min_neighbors_share: 0.75, ratio: 0.6, min_neighbor_sharpe: 0.5}
- C8: FAIL ; measure (-2.114, -0.0003485) ; threshold (2, 0.3)
- C9: OK ; measure 0 ; threshold {random_cuts: 20, fixed_cuts: 3, not_full_share_min: 0.4, tolerance: 1e-09}
- C11: FAIL ; measure (-2.357, -2.909) ; threshold (0.5, 0)
- C12: FAIL ; measure (1.372, 35.79) ; threshold (0.5, 40)
- C13: FAIL ; measure (0.2932, -3.994) ; threshold 0
- C14: FAIL ; measure -0.03687 ; threshold 0.04
- C15: OK ; measure not applicable (hedged) ; threshold None
- C16: FAIL ; measure None ; threshold 0.6
- C2: FAIL ; measure -1.539 ; threshold 0.5
- C3: FAIL ; measure -2.092 ; threshold 2
- C4: FAIL ; measure -4.097 ; threshold 0
- C10: FAIL ; measure 0.9876 ; threshold 0.05

### R0011 (c-rank-carry {k: 2, buffer: 2})
- C1: FAIL ; measure 6.724e-53 ; threshold 0.95
- C5: FAIL ; measure {2020: 1.102, 2021: 4.189, 2022: -3.388, 2023: -5.066, 2024: -3.276, 2025: -3.227} ; threshold {sharpe_min: -1, positives_min: 4}
- C6: FAIL ; measure 0.2839 ; threshold 0.2
- C7: FAIL ; measure None ; threshold {min_neighbors_share: 0.75, ratio: 0.6, min_neighbor_sharpe: 0.5}
- C8: FAIL ; measure (-1.162, -0.0005172) ; threshold (2, 0.3)
- C9: OK ; measure 0 ; threshold {random_cuts: 20, fixed_cuts: 3, not_full_share_min: 0.4, tolerance: 1e-09}
- C11: FAIL ; measure (-1.703, -2.259) ; threshold (0.5, 0)
- C12: FAIL ; measure (1.203, 30.54) ; threshold (0.5, 40)
- C13: FAIL ; measure (1.009, -3.428) ; threshold 0
- C14: FAIL ; measure -0.02005 ; threshold 0.04
- C15: OK ; measure not applicable (hedged) ; threshold None
- C16: FAIL ; measure None ; threshold 0.6
- C2: FAIL ; measure -0.8742 ; threshold 0.5
- C3: FAIL ; measure -1.164 ; threshold 2
- C4: FAIL ; measure -3.505 ; threshold 0
- C10: FAIL ; measure 0.885 ; threshold 0.05

### R0012 (c-rank-carry {k: 2, buffer: 4})
- C1: FAIL ; measure 2.607e-40 ; threshold 0.95
- C5: FAIL ; measure {2020: 3.331, 2021: 4.077, 2022: -3.505, 2023: -4.583, 2024: -1.653, 2025: -2.75} ; threshold {sharpe_min: -1, positives_min: 4}
- C6: FAIL ; measure 0.2389 ; threshold 0.2
- C7: FAIL ; measure None ; threshold {min_neighbors_share: 0.75, ratio: 0.6, min_neighbor_sharpe: 0.5}
- C8: FAIL ; measure (-0.2753, -0.0009863) ; threshold (2, 0.3)
- C9: OK ; measure 0 ; threshold {random_cuts: 20, fixed_cuts: 3, not_full_share_min: 0.4, tolerance: 1e-09}
- C11: FAIL ; measure (-1.052, -1.569) ; threshold (0.5, 0)
- C12: FAIL ; measure (1.056, 25.5) ; threshold (0.5, 40)
- C13: FAIL ; measure (1.503, -2.607) ; threshold 0
- C14: FAIL ; measure -0.005548 ; threshold 0.04
- C15: OK ; measure not applicable (hedged) ; threshold None
- C16: FAIL ; measure None ; threshold 0.6
- C2: FAIL ; measure -0.2583 ; threshold 0.5
- C3: FAIL ; measure -0.3182 ; threshold 2
- C4: FAIL ; measure -3.008 ; threshold 0
- C10: FAIL ; measure 0.6381 ; threshold 0.05

### R0013 (c-rank-carry {k: 3, buffer: 1})
- C1: FAIL ; measure 4.4e-62 ; threshold 0.95
- C5: FAIL ; measure {2020: 0.2653, 2021: 4.001, 2022: -3.714, 2023: -5.433, 2024: -4.453, 2025: -3.681} ; threshold {sharpe_min: -1, positives_min: 4}
- C6: FAIL ; measure 0.2943 ; threshold 0.2
- C7: FAIL ; measure None ; threshold {min_neighbors_share: 0.75, ratio: 0.6, min_neighbor_sharpe: 0.5}
- C8: FAIL ; measure (-1.71, -0.0006558) ; threshold (2, 0.3)
- C9: OK ; measure 0 ; threshold {random_cuts: 20, fixed_cuts: 3, not_full_share_min: 0.4, tolerance: 1e-09}
- C11: FAIL ; measure (-2.256, -2.868) ; threshold (0.5, 0)
- C12: FAIL ; measure (1.291, 30.19) ; threshold (0.5, 40)
- C13: FAIL ; measure (0.5465, -4.042) ; threshold 0
- C14: FAIL ; measure -0.02791 ; threshold 0.04
- C15: OK ; measure not applicable (hedged) ; threshold None
- C16: FAIL ; measure None ; threshold 0.6
- C2: FAIL ; measure -1.345 ; threshold 0.5
- C3: FAIL ; measure -1.708 ; threshold 2
- C4: FAIL ; measure -4.267 ; threshold 0
- C10: FAIL ; measure 0.9674 ; threshold 0.05

### R0014 (c-rank-carry {k: 3, buffer: 2})
- C1: FAIL ; measure 3.113e-46 ; threshold 0.95
- C5: FAIL ; measure {2020: 2.808, 2021: 4.404, 2022: -3.793, 2023: -5.368, 2024: -2.739, 2025: -3.524} ; threshold {sharpe_min: -1, positives_min: 4}
- C6: FAIL ; measure 0.2504 ; threshold 0.2
- C7: FAIL ; measure 0 ; threshold {min_neighbors_share: 0.75, ratio: 0.6, min_neighbor_sharpe: 0.5}
- C8: FAIL ; measure (-0.6664, -0.00084) ; threshold (2, 0.3)
- C9: OK ; measure 0 ; threshold {random_cuts: 20, fixed_cuts: 3, not_full_share_min: 0.4, tolerance: 1e-09}
- C11: FAIL ; measure (-1.45, -2.013) ; threshold (0.5, 0)
- C12: FAIL ; measure (1.116, 25.02) ; threshold (0.5, 40)
- C13: FAIL ; measure (1.393, -3.419) ; threshold 0
- C14: FAIL ; measure -0.01121 ; threshold 0.04
- C15: OK ; measure not applicable (hedged) ; threshold None
- C16: FAIL ; measure None ; threshold 0.6
- C2: FAIL ; measure -0.5806 ; threshold 0.5
- C3: FAIL ; measure -0.6997 ; threshold 2
- C4: FAIL ; measure -3.67 ; threshold 0
- C10: FAIL ; measure 0.7706 ; threshold 0.05

### R0015 (c-rank-carry {k: 3, buffer: 4})
- C1: FAIL ; measure 1.523e-38 ; threshold 0.95
- C5: FAIL ; measure {2020: 2.919, 2021: 5.235, 2022: -3.848, 2023: -4.936, 2024: -1.505, 2025: -3.279} ; threshold {sharpe_min: -1, positives_min: 4}
- C6: FAIL ; measure 0.2237 ; threshold 0.2
- C7: FAIL ; measure None ; threshold {min_neighbors_share: 0.75, ratio: 0.6, min_neighbor_sharpe: 0.5}
- C8: FAIL ; measure (-0.1595, -0.0008826) ; threshold (2, 0.3)
- C9: OK ; measure 0 ; threshold {random_cuts: 20, fixed_cuts: 3, not_full_share_min: 0.4, tolerance: 1e-09}
- C11: FAIL ; measure (-0.999, -1.566) ; threshold (0.5, 0)
- C12: FAIL ; measure (1.035, 22.43) ; threshold (0.5, 40)
- C13: FAIL ; measure (1.685, -2.814) ; threshold 0
- C14: FAIL ; measure -0.00345 ; threshold 0.04
- C15: OK ; measure not applicable (hedged) ; threshold None
- C16: FAIL ; measure None ; threshold 0.6
- C2: FAIL ; measure -0.1744 ; threshold 0.5
- C3: FAIL ; measure -0.1984 ; threshold 2
- C4: FAIL ; measure -3.209 ; threshold 0
- C10: FAIL ; measure 0.5831 ; threshold 0.05

### R0016 (c-rank-carry {k: 5, buffer: 1})
- C1: FAIL ; measure 3.646e-49 ; threshold 0.95
- C5: FAIL ; measure {2020: 2.45, 2021: 4.883, 2022: -3.895, 2023: -5.442, 2024: -3.292, 2025: -4.336} ; threshold {sharpe_min: -1, positives_min: 4}
- C6: FAIL ; measure 0.2565 ; threshold 0.2
- C7: FAIL ; measure None ; threshold {min_neighbors_share: 0.75, ratio: 0.6, min_neighbor_sharpe: 0.5}
- C8: FAIL ; measure (-0.795, -0.0005224) ; threshold (2, 0.3)
- C9: OK ; measure 0 ; threshold {random_cuts: 20, fixed_cuts: 3, not_full_share_min: 0.4, tolerance: 1e-09}
- C11: FAIL ; measure (-1.61, -2.225) ; threshold (0.5, 0)
- C12: FAIL ; measure (1.138, 21.83) ; threshold (0.5, 40)
- C13: FAIL ; measure (1.386, -3.804) ; threshold 0
- C14: FAIL ; measure -0.01307 ; threshold 0.04
- C15: OK ; measure not applicable (hedged) ; threshold None
- C16: FAIL ; measure None ; threshold 0.6
- C2: FAIL ; measure -0.7179 ; threshold 0.5
- C3: FAIL ; measure -0.8066 ; threshold 2
- C4: FAIL ; measure -4.003 ; threshold 0
- C10: FAIL ; measure 0.7988 ; threshold 0.05

### R0017 (c-rank-carry {k: 5, buffer: 2})
- C1: FAIL ; measure 2.714e-47 ; threshold 0.95
- C5: FAIL ; measure {2020: 2.188, 2021: 4.866, 2022: -3.796, 2023: -5.162, 2024: -2.754, 2025: -4.018} ; threshold {sharpe_min: -1, positives_min: 4}
- C6: FAIL ; measure 0.2454 ; threshold 0.2
- C7: FAIL ; measure None ; threshold {min_neighbors_share: 0.75, ratio: 0.6, min_neighbor_sharpe: 0.5}
- C8: FAIL ; measure (-0.6482, -0.001113) ; threshold (2, 0.3)
- C9: OK ; measure 0 ; threshold {random_cuts: 20, fixed_cuts: 3, not_full_share_min: 0.4, tolerance: 1e-09}
- C11: FAIL ; measure (-1.495, -2.082) ; threshold (0.5, 0)
- C12: FAIL ; measure (1.122, 20.61) ; threshold (0.5, 40)
- C13: FAIL ; measure (1.316, -3.44) ; threshold 0
- C14: FAIL ; measure -0.01124 ; threshold 0.04
- C15: OK ; measure not applicable (hedged) ; threshold None
- C16: FAIL ; measure None ; threshold 0.6
- C2: FAIL ; measure -0.6193 ; threshold 0.5
- C3: FAIL ; measure -0.6931 ; threshold 2
- C4: FAIL ; measure -3.831 ; threshold 0
- C10: FAIL ; measure 0.7656 ; threshold 0.05

### R0018 (c-rank-carry {k: 5, buffer: 4})
- C1: FAIL ; measure 6.107e-43 ; threshold 0.95
- C5: FAIL ; measure {2020: 2.038, 2021: 5.404, 2022: -3.796, 2023: -5.101, 2024: -1.178, 2025: -4.051} ; threshold {sharpe_min: -1, positives_min: 4}
- C6: FAIL ; measure 0.2165 ; threshold 0.2
- C7: FAIL ; measure None ; threshold {min_neighbors_share: 0.75, ratio: 0.6, min_neighbor_sharpe: 0.5}
- C8: FAIL ; measure (-0.4126, -0.0004744) ; threshold (2, 0.3)
- C9: OK ; measure 0 ; threshold {random_cuts: 20, fixed_cuts: 3, not_full_share_min: 0.4, tolerance: 1e-09}
- C11: FAIL ; measure (-1.192, -1.733) ; threshold (0.5, 0)
- C12: FAIL ; measure (1.076, 18.3) ; threshold (0.5, 40)
- C13: FAIL ; measure (1.406, -2.993) ; threshold 0
- C14: FAIL ; measure -0.006832 ; threshold 0.04
- C15: OK ; measure not applicable (hedged) ; threshold None
- C16: FAIL ; measure None ; threshold 0.6
- C2: FAIL ; measure -0.382 ; threshold 0.5
- C3: FAIL ; measure -0.4289 ; threshold 2
- C4: FAIL ; measure -3.507 ; threshold 0
- C10: FAIL ; measure 0.6763 ; threshold 0.05

### R0019 (c-carry-regime {entry: 0.09, extreme_cap: 0.25})
- C1: FAIL ; measure 4.583e-230 ; threshold 0.95
- C5: FAIL ; measure {2020: -5.173, 2021: -5.42, 2022: -4.509, 2023: -3.71, 2024: -5.229, 2025: -5.202} ; threshold {sharpe_min: -1, positives_min: 4}
- C6: FAIL ; measure 0.3913 ; threshold 0.2
- C7: FAIL ; measure None ; threshold {min_neighbors_share: 0.75, ratio: 0.6, min_neighbor_sharpe: 0.5}
- C8: FAIL ; measure (-7.302, -0.001132) ; threshold (2, 0.3)
- C9: OK ; measure 0 ; threshold {random_cuts: 20, fixed_cuts: 3, not_full_share_min: 0.4, tolerance: 1e-09}
- C11: FAIL ; measure (-5.061, -5.35) ; threshold (0.5, 0)
- C12: FAIL ; measure (2.671, 30.04) ; threshold (0.5, 40)
- C13: FAIL ; measure (-4.933, -4.223) ; threshold 0
- C14: FAIL ; measure -0.07354 ; threshold 0.04
- C15: OK ; measure not applicable (hedged) ; threshold None
- C16: FAIL ; measure None ; threshold 0.6
- C2: FAIL ; measure -4.489 ; threshold 0.5
- C3: FAIL ; measure -7.422 ; threshold 2
- C4: FAIL ; measure -6.486 ; threshold 0
- C10: FAIL ; measure 1 ; threshold 0.05

### R0020 (c-carry-regime {entry: 0.09, extreme_cap: 0.5})
- C1: FAIL ; measure 2.703e-85 ; threshold 0.95
- C5: FAIL ; measure {2020: -1.086, 2021: -1.615, 2022: -4.509, 2023: -3.531, 2024: -1.941, 2025: -5.202} ; threshold {sharpe_min: -1, positives_min: 4}
- C6: FAIL ; measure 0.2351 ; threshold 0.2
- C7: FAIL ; measure None ; threshold {min_neighbors_share: 0.75, ratio: 0.6, min_neighbor_sharpe: 0.5}
- C8: FAIL ; measure (-3.86, -0.0004438) ; threshold (2, 0.3)
- C9: OK ; measure 0 ; threshold {random_cuts: 20, fixed_cuts: 3, not_full_share_min: 0.4, tolerance: 1e-09}
- C11: FAIL ; measure (-3.38, -3.804) ; threshold (0.5, 0)
- C12: FAIL ; measure (1.584, 26.31) ; threshold (0.5, 40)
- C13: FAIL ; measure (-2.102, -3.082) ; threshold 0
- C14: FAIL ; measure -0.03839 ; threshold 0.04
- C15: OK ; measure not applicable (hedged) ; threshold None
- C16: FAIL ; measure None ; threshold 0.6
- C2: FAIL ; measure -2.315 ; threshold 0.5
- C3: FAIL ; measure -3.912 ; threshold 2
- C4: FAIL ; measure -5.184 ; threshold 0
- C10: FAIL ; measure 0.9996 ; threshold 0.05

### R0021 (c-carry-regime {entry: 0.09, extreme_cap: 1})
- C1: FAIL ; measure 4.983e-44 ; threshold 0.95
- C5: FAIL ; measure {2020: 2.075, 2021: 4.96, 2022: -4.509, 2023: -3.531, 2024: -1.574, 2025: -5.202} ; threshold {sharpe_min: -1, positives_min: 4}
- C6: OK ; measure 0.1748 ; threshold 0.2
- C7: FAIL ; measure None ; threshold {min_neighbors_share: 0.75, ratio: 0.6, min_neighbor_sharpe: 0.5}
- C8: FAIL ; measure (-0.4947, -0.001242) ; threshold (2, 0.3)
- C9: OK ; measure 0 ; threshold {random_cuts: 20, fixed_cuts: 3, not_full_share_min: 0.4, tolerance: 1e-09}
- C11: FAIL ; measure (-1.442, -2.075) ; threshold (0.5, 0)
- C12: FAIL ; measure (1.082, 24.22) ; threshold (0.5, 40)
- C13: FAIL ; measure (1.068, -2.965) ; threshold 0
- C14: FAIL ; measure -0.007086 ; threshold 0.04
- C15: OK ; measure not applicable (hedged) ; threshold None
- C16: FAIL ; measure None ; threshold 0.6
- C2: FAIL ; measure -0.4901 ; threshold 0.5
- C3: FAIL ; measure -0.5677 ; threshold 2
- C4: FAIL ; measure -4.395 ; threshold 0
- C10: FAIL ; measure 0.7179 ; threshold 0.05

### R0022 (c-carry-regime {entry: 0.135, extreme_cap: 0.25})
- C1: FAIL ; measure 1.513e-204 ; threshold 0.95
- C5: FAIL ; measure {2020: -5.648, 2021: -5.874, 2022: -2.454, 2023: -2.15, 2024: -4.361, 2025: -3.361} ; threshold {sharpe_min: -1, positives_min: 4}
- C6: FAIL ; measure 0.3435 ; threshold 0.2
- C7: FAIL ; measure None ; threshold {min_neighbors_share: 0.75, ratio: 0.6, min_neighbor_sharpe: 0.5}
- C8: FAIL ; measure (-6.031, -0.001104) ; threshold (2, 0.3)
- C9: OK ; measure 0 ; threshold {random_cuts: 20, fixed_cuts: 3, not_full_share_min: 0.4, tolerance: 1e-09}
- C11: FAIL ; measure (-4.467, -4.762) ; threshold (0.5, 0)
- C12: FAIL ; measure (2.619, 24.88) ; threshold (0.5, 40)
- C13: FAIL ; measure (-4.656, -3.085) ; threshold 0
- C14: FAIL ; measure -0.06272 ; threshold 0.04
- C15: OK ; measure not applicable (hedged) ; threshold None
- C16: FAIL ; measure None ; threshold 0.6
- C2: FAIL ; measure -3.895 ; threshold 0.5
- C3: FAIL ; measure -6.121 ; threshold 2
- C4: FAIL ; measure -5.651 ; threshold 0
- C10: FAIL ; measure 1 ; threshold 0.05

### R0023 (c-carry-regime {entry: 0.135, extreme_cap: 0.5})
- C1: FAIL ; measure 2.453e-70 ; threshold 0.95
- C5: FAIL ; measure {2020: -1.44, 2021: -2.021, 2022: -2.454, 2023: -1.963, 2024: -1.041, 2025: -3.361} ; threshold {sharpe_min: -1, positives_min: 4}
- C6: OK ; measure 0.1674 ; threshold 0.2
- C7: FAIL ; measure 0 ; threshold {min_neighbors_share: 0.75, ratio: 0.6, min_neighbor_sharpe: 0.5}
- C8: FAIL ; measure (-2.759, -0.0004357) ; threshold (2, 0.3)
- C9: OK ; measure 0 ; threshold {random_cuts: 20, fixed_cuts: 3, not_full_share_min: 0.4, tolerance: 1e-09}
- C11: FAIL ; measure (-2.621, -3.036) ; threshold (0.5, 0)
- C12: FAIL ; measure (1.422, 20.88) ; threshold (0.5, 40)
- C13: FAIL ; measure (-1.73, -1.69) ; threshold 0
- C14: FAIL ; measure -0.02576 ; threshold 0.04
- C15: OK ; measure not applicable (hedged) ; threshold None
- C16: FAIL ; measure None ; threshold 0.6
- C2: FAIL ; measure -1.596 ; threshold 0.5
- C3: FAIL ; measure -2.812 ; threshold 2
- C4: FAIL ; measure -4.233 ; threshold 0
- C10: FAIL ; measure 0.9964 ; threshold 0.05

### R0024 (c-carry-regime {entry: 0.135, extreme_cap: 1})
- C1: FAIL ; measure 2.141e-28 ; threshold 0.95
- C5: FAIL ; measure {2020: 1.713, 2021: 3.868, 2022: -2.454, 2023: -1.963, 2024: -0.6901, 2025: -3.361} ; threshold {sharpe_min: -1, positives_min: 4}
- C6: OK ; measure 0.09418 ; threshold 0.2
- C7: FAIL ; measure None ; threshold {min_neighbors_share: 0.75, ratio: 0.6, min_neighbor_sharpe: 0.5}
- C8: FAIL ; measure (0.6234, -0.001238) ; threshold (2, 0.3)
- C9: OK ; measure 0 ; threshold {random_cuts: 20, fixed_cuts: 3, not_full_share_min: 0.4, tolerance: 1e-09}
- C11: FAIL ; measure (-0.4441, -1.082) ; threshold (0.5, 0)
- C12: FAIL ; measure (0.9241, 18.79) ; threshold (0.5, 40)
- C13: FAIL ; measure (1.572, -1.549) ; threshold 0
- C14: FAIL ; measure 0.006024 ; threshold 0.04
- C15: OK ; measure not applicable (hedged) ; threshold None
- C16: FAIL ; measure None ; threshold 0.6
- C2: FAIL ; measure 0.4515 ; threshold 0.5
- C3: FAIL ; measure 0.5338 ; threshold 2
- C4: FAIL ; measure -3.25 ; threshold 0
- C10: FAIL ; measure 0.2871 ; threshold 0.05

### R0025 (c-carry-regime {entry: 0.2, extreme_cap: 0.25})
- C1: FAIL ; measure 6.715e-221 ; threshold 0.95
- C5: FAIL ; measure {2020: -5.598, 2021: -5.979, 2022: -2.441, 2023: -1.412, 2024: -4.689, 2025: -2.594} ; threshold {sharpe_min: -1, positives_min: 4}
- C6: FAIL ; measure 0.3494 ; threshold 0.2
- C7: FAIL ; measure None ; threshold {min_neighbors_share: 0.75, ratio: 0.6, min_neighbor_sharpe: 0.5}
- C8: FAIL ; measure (-5.721, -0.0003341) ; threshold (2, 0.3)
- C9: OK ; measure 0 ; threshold {random_cuts: 20, fixed_cuts: 3, not_full_share_min: 0.4, tolerance: 1e-09}
- C11: FAIL ; measure (-4.38, -4.652) ; threshold (0.5, 0)
- C12: FAIL ; measure (3.099, 22.58) ; threshold (0.5, 40)
- C13: FAIL ; measure (-4.614, -3.011) ; threshold 0
- C14: FAIL ; measure -0.064 ; threshold 0.04
- C15: OK ; measure not applicable (hedged) ; threshold None
- C16: FAIL ; measure None ; threshold 0.6
- C2: FAIL ; measure -3.835 ; threshold 0.5
- C3: FAIL ; measure -5.725 ; threshold 2
- C4: FAIL ; measure -5.046 ; threshold 0
- C10: FAIL ; measure 1 ; threshold 0.05

### R0026 (c-carry-regime {entry: 0.2, extreme_cap: 0.5})
- C1: FAIL ; measure 7.153e-75 ; threshold 0.95
- C5: FAIL ; measure {2020: -1.672, 2021: -2.123, 2022: -2.441, 2023: -1.265, 2024: -1.181, 2025: -2.594} ; threshold {sharpe_min: -1, positives_min: 4}
- C6: OK ; measure 0.1547 ; threshold 0.2
- C7: FAIL ; measure None ; threshold {min_neighbors_share: 0.75, ratio: 0.6, min_neighbor_sharpe: 0.5}
- C8: FAIL ; measure (-2.652, 0.0003698) ; threshold (2, 0.3)
- C9: OK ; measure 0 ; threshold {random_cuts: 20, fixed_cuts: 3, not_full_share_min: 0.4, tolerance: 1e-09}
- C11: FAIL ; measure (-2.503, -2.902) ; threshold (0.5, 0)
- C12: FAIL ; measure (1.439, 18.93) ; threshold (0.5, 40)
- C13: FAIL ; measure (-1.719, -1.503) ; threshold 0
- C14: FAIL ; measure -0.02348 ; threshold 0.04
- C15: OK ; measure not applicable (hedged) ; threshold None
- C16: FAIL ; measure None ; threshold 0.6
- C2: FAIL ; measure -1.528 ; threshold 0.5
- C3: FAIL ; measure -2.609 ; threshold 2
- C4: FAIL ; measure -3.915 ; threshold 0
- C10: FAIL ; measure 0.9928 ; threshold 0.05

### R0027 (c-carry-regime {entry: 0.2, extreme_cap: 1})
- C1: FAIL ; measure 6.585e-24 ; threshold 0.95
- C5: FAIL ; measure {2020: 1.467, 2021: 4.172, 2022: -2.441, 2023: -1.265, 2024: -0.8121, 2025: -2.594} ; threshold {sharpe_min: -1, positives_min: 4}
- C6: OK ; measure 0.07255 ; threshold 0.2
- C7: FAIL ; measure None ; threshold {min_neighbors_share: 0.75, ratio: 0.6, min_neighbor_sharpe: 0.5}
- C8: FAIL ; measure (0.9046, -0.0004968) ; threshold (2, 0.3)
- C9: OK ; measure 0 ; threshold {random_cuts: 20, fixed_cuts: 3, not_full_share_min: 0.4, tolerance: 1e-09}
- C11: FAIL ; measure (-0.1686, -0.8041) ; threshold (0.5, 0)
- C12: FAIL ; measure (0.8712, 16.72) ; threshold (0.5, 40)
- C13: FAIL ; measure (1.866, -1.348) ; threshold 0
- C14: FAIL ; measure 0.009395 ; threshold 0.04
- C15: OK ; measure not applicable (hedged) ; threshold None
- C16: FAIL ; measure None ; threshold 0.6
- C2: OK ; measure 0.7327 ; threshold 0.5
- C3: FAIL ; measure 0.8511 ; threshold 2
- C4: FAIL ; measure -2.71 ; threshold 0
- C10: FAIL ; measure 0.1938 ; threshold 0.05

### R0028 (m-semivar {L_days: 14, s: 0.1})
- C1: FAIL ; measure 0.3267 ; threshold 0.95
- C5: FAIL ; measure {2020: 1.944, 2021: 2.834, 2022: -1.043, 2023: 1.889, 2024: 1.227, 2025: -0.7852} ; threshold {sharpe_min: -1, positives_min: 4}
- C6: FAIL ; measure 0.567 ; threshold 0.45
- C7: FAIL ; measure None ; threshold {min_neighbors_share: 0.75, ratio: 0.6, min_neighbor_sharpe: 0.5}
- C8: FAIL ; measure 0.9626 ; threshold 0.05
- C9: OK ; measure 0 ; threshold {random_cuts: 20, fixed_cuts: 3, not_full_share_min: 0.4, tolerance: 1e-09}
- C11: FAIL ; measure (0.3115, -0.2928) ; threshold (0.532, 0)
- C12: FAIL ; measure (0.1774, 18.05) ; threshold (0.5, 15)
- C13: OK ; measure (1.623, 0.2341) ; threshold 0
- C14: OK ; measure 0.4774 ; threshold 0.04
- C15: FAIL ; measure None ; threshold (0, 0.585)
- C16: FAIL ; measure None ; threshold 0.6
- C2: OK ; measure 1.064 ; threshold 0.5
- C3: OK ; measure 2.093 ; threshold 2
- C4: OK ; measure 0.8341 ; threshold 0
- C10: OK ; measure 0.02539 ; threshold 0.05

### R0029 (m-semivar {L_days: 14, s: 0.2})
- C1: FAIL ; measure 0.3224 ; threshold 0.95
- C5: FAIL ; measure {2020: 1.714, 2021: 2.849, 2022: -1.081, 2023: 1.912, 2024: 0.8734, 2025: -0.2922} ; threshold {sharpe_min: -1, positives_min: 4}
- C6: FAIL ; measure 0.5261 ; threshold 0.45
- C7: FAIL ; measure None ; threshold {min_neighbors_share: 0.75, ratio: 0.6, min_neighbor_sharpe: 0.5}
- C8: FAIL ; measure 0.9614 ; threshold 0.05
- C9: OK ; measure 0 ; threshold {random_cuts: 20, fixed_cuts: 3, not_full_share_min: 0.4, tolerance: 1e-09}
- C11: FAIL ; measure (0.3263, -0.2602) ; threshold (0.5292, 0)
- C12: OK ; measure (0.1205, 11.64) ; threshold (0.5, 15)
- C13: OK ; measure (1.609, 0.2389) ; threshold 0
- C14: OK ; measure 0.4813 ; threshold 0.04
- C15: FAIL ; measure None ; threshold (0, 0.585)
- C16: FAIL ; measure None ; threshold 0.6
- C2: OK ; measure 1.058 ; threshold 0.5
- C3: OK ; measure 2.155 ; threshold 2
- C4: OK ; measure 0.9138 ; threshold 0
- C10: OK ; measure 0.0208 ; threshold 0.05

### R0030 (m-semivar {L_days: 14, s: 0.4})
- C1: FAIL ; measure 0.07692 ; threshold 0.95
- C5: FAIL ; measure {2020: 0.04066, 2021: 2.425, 2022: -1.507, 2023: 1.386, 2024: 1.425, 2025: 0.1503} ; threshold {sharpe_min: -1, positives_min: 4}
- C6: FAIL ; measure 0.6918 ; threshold 0.45
- C7: FAIL ; measure None ; threshold {min_neighbors_share: 0.75, ratio: 0.6, min_neighbor_sharpe: 0.5}
- C8: FAIL ; measure 0.9954 ; threshold 0.05
- C9: FAIL ; measure 0 ; threshold {random_cuts: 20, fixed_cuts: 3, not_full_share_min: 0.4, tolerance: 1e-09}
- C11: FAIL ; measure (-0.1317, -0.6851) ; threshold (0.5, 0)
- C12: OK ; measure (0.09006, 5.424) ; threshold (0.5, 15)
- C13: OK ; measure (0.7689, 0.6259) ; threshold 0
- C14: OK ; measure 0.2294 ; threshold 0.04
- C15: FAIL ; measure None ; threshold (0, 0.585)
- C16: FAIL ; measure None ; threshold 0.6
- C2: OK ; measure 0.6721 ; threshold 0.5
- C3: FAIL ; measure 1.55 ; threshold 2
- C4: OK ; measure 0.6058 ; threshold 0
- C10: FAIL ; measure 0.06519 ; threshold 0.05

### R0031 (m-semivar {L_days: 28, s: 0.1})
- C1: FAIL ; measure 0.4201 ; threshold 0.95
- C5: OK ; measure {2020: 1.864, 2021: 3.14, 2022: -0.9929, 2023: 2.158, 2024: 0.8957, 2025: -0.397} ; threshold {sharpe_min: -1, positives_min: 4}
- C6: FAIL ; measure 0.5601 ; threshold 0.45
- C7: FAIL ; measure None ; threshold {min_neighbors_share: 0.75, ratio: 0.6, min_neighbor_sharpe: 0.5}
- C8: FAIL ; measure 0.9162 ; threshold 0.05
- C9: OK ; measure 0 ; threshold {random_cuts: 20, fixed_cuts: 3, not_full_share_min: 0.4, tolerance: 1e-09}
- C11: FAIL ; measure (0.4489, -0.1322) ; threshold (0.5807, 0)
- C12: OK ; measure (0.1019, 10.57) ; threshold (0.5, 15)
- C13: OK ; measure (1.72, 0.3467) ; threshold 0
- C14: OK ; measure 0.5566 ; threshold 0.04
- C15: FAIL ; measure None ; threshold (0, 0.585)
- C16: FAIL ; measure None ; threshold 0.6
- C2: OK ; measure 1.161 ; threshold 0.5
- C3: OK ; measure 2.383 ; threshold 2
- C4: OK ; measure 1.03 ; threshold 0
- C10: OK ; measure 0.0124 ; threshold 0.05

### R0032 (m-semivar {L_days: 28, s: 0.2})
- C1: FAIL ; measure 0.1338 ; threshold 0.95
- C5: FAIL ; measure {2020: 0.62, 2021: 2.722, 2022: -1.933, 2023: 1.394, 2024: 0.8407, 2025: -0.5722} ; threshold {sharpe_min: -1, positives_min: 4}
- C6: FAIL ; measure 0.5941 ; threshold 0.45
- C7: OK ; measure 1 ; threshold {min_neighbors_share: 0.75, ratio: 0.6, min_neighbor_sharpe: 0.5}
- C8: FAIL ; measure 0.991 ; threshold 0.05
- C9: OK ; measure 0 ; threshold {random_cuts: 20, fixed_cuts: 3, not_full_share_min: 0.4, tolerance: 1e-09}
- C11: FAIL ; measure (0.02665, -0.5657) ; threshold (0.5, 0)
- C12: OK ; measure (0.1003, 7.294) ; threshold (0.5, 15)
- C13: OK ; measure (1.203, 0.1721) ; threshold 0
- C14: OK ; measure 0.3097 ; threshold 0.04
- C15: FAIL ; measure None ; threshold (0, 0.585)
- C16: FAIL ; measure None ; threshold 0.6
- C2: OK ; measure 0.7992 ; threshold 0.5
- C3: FAIL ; measure 1.738 ; threshold 2
- C4: OK ; measure 0.7104 ; threshold 0
- C10: OK ; measure 0.04699 ; threshold 0.05

### R0033 (m-semivar {L_days: 28, s: 0.4})
- C1: FAIL ; measure 0.05612 ; threshold 0.95
- C5: OK ; measure {2020: 0.7369, 2021: 2.053, 2022: -0.8208, 2023: 0.9882, 2024: 1.244, 2025: -0.1703} ; threshold {sharpe_min: -1, positives_min: 4}
- C6: FAIL ; measure 0.5364 ; threshold 0.45
- C7: FAIL ; measure None ; threshold {min_neighbors_share: 0.75, ratio: 0.6, min_neighbor_sharpe: 0.5}
- C8: FAIL ; measure 0.9962 ; threshold 0.05
- C9: FAIL ; measure 0 ; threshold {random_cuts: 20, fixed_cuts: 3, not_full_share_min: 0.4, tolerance: 1e-09}
- C11: FAIL ; measure (-0.1484, -0.688) ; threshold (0.5, 0)
- C12: OK ; measure (0.09128, 4.085) ; threshold (0.5, 15)
- C13: OK ; measure (0.8889, 0.1773) ; threshold 0
- C14: OK ; measure 0.1813 ; threshold 0.04
- C15: FAIL ; measure None ; threshold (0, 0.585)
- C16: FAIL ; measure None ; threshold 0.6
- C2: OK ; measure 0.6199 ; threshold 0.5
- C3: FAIL ; measure 1.523 ; threshold 2
- C4: OK ; measure 0.5577 ; threshold 0
- C10: FAIL ; measure 0.06839 ; threshold 0.05

### R0034 (m-semivar {L_days: 56, s: 0.1})
- C1: FAIL ; measure 0.0981 ; threshold 0.95
- C5: FAIL ; measure {2020: -0.08109, 2021: 2.759, 2022: -1.448, 2023: 1.732, 2024: 1.112, 2025: -0.7943} ; threshold {sharpe_min: -1, positives_min: 4}
- C6: FAIL ; measure 0.6371 ; threshold 0.45
- C7: FAIL ; measure None ; threshold {min_neighbors_share: 0.75, ratio: 0.6, min_neighbor_sharpe: 0.5}
- C8: FAIL ; measure 0.9926 ; threshold 0.05
- C9: OK ; measure 0 ; threshold {random_cuts: 20, fixed_cuts: 3, not_full_share_min: 0.4, tolerance: 1e-09}
- C11: FAIL ; measure (-0.03672, -0.6055) ; threshold (0.5, 0)
- C12: OK ; measure (0.1086, 7.405) ; threshold (0.5, 15)
- C13: OK ; measure (1.007, 0.2852) ; threshold 0
- C14: OK ; measure 0.2603 ; threshold 0.04
- C15: FAIL ; measure None ; threshold (0, 0.585)
- C16: FAIL ; measure None ; threshold 0.6
- C2: OK ; measure 0.7191 ; threshold 0.5
- C3: FAIL ; measure 1.504 ; threshold 2
- C4: OK ; measure 0.6317 ; threshold 0
- C10: FAIL ; measure 0.07159 ; threshold 0.05

### R0035 (m-semivar {L_days: 56, s: 0.2})
- C1: FAIL ; measure 0.07341 ; threshold 0.95
- C5: FAIL ; measure {2020: -0.06748, 2021: 2.413, 2022: -1.316, 2023: 1.799, 2024: 1.367, 2025: -0.1271} ; threshold {sharpe_min: -1, positives_min: 4}
- C6: FAIL ; measure 0.6534 ; threshold 0.45
- C7: FAIL ; measure None ; threshold {min_neighbors_share: 0.75, ratio: 0.6, min_neighbor_sharpe: 0.5}
- C8: FAIL ; measure 0.9972 ; threshold 0.05
- C9: OK ; measure 0 ; threshold {random_cuts: 20, fixed_cuts: 3, not_full_share_min: 0.4, tolerance: 1e-09}
- C11: FAIL ; measure (-0.1053, -0.6021) ; threshold (0.5, 0)
- C12: OK ; measure (0.08496, 5.48) ; threshold (0.5, 15)
- C13: OK ; measure (0.8234, 0.4484) ; threshold 0
- C14: OK ; measure 0.2312 ; threshold 0.04
- C15: FAIL ; measure None ; threshold (0, 0.585)
- C16: FAIL ; measure None ; threshold 0.6
- C2: OK ; measure 0.6628 ; threshold 0.5
- C3: FAIL ; measure 1.587 ; threshold 2
- C4: OK ; measure 0.6015 ; threshold 0
- C10: FAIL ; measure 0.06099 ; threshold 0.05

### R0036 (m-semivar {L_days: 56, s: 0.4})
- C1: FAIL ; measure 0.1397 ; threshold 0.95
- C5: OK ; measure {2020: 1.824, 2021: 1.863, 2022: -0.6568, 2023: 0.1823, 2024: 1.777, 2025: 0.5301} ; threshold {sharpe_min: -1, positives_min: 4}
- C6: OK ; measure 0.1936 ; threshold 0.45
- C7: FAIL ; measure None ; threshold {min_neighbors_share: 0.75, ratio: 0.6, min_neighbor_sharpe: 0.5}
- C8: FAIL ; measure 0.9864 ; threshold 0.05
- C9: FAIL ; measure 0 ; threshold {random_cuts: 20, fixed_cuts: 3, not_full_share_min: 0.4, tolerance: 1e-09}
- C11: FAIL ; measure (0.0008377, -0.6119) ; threshold (0.5, 0)
- C12: OK ; measure (0.06404, 1.739) ; threshold (0.5, 15)
- C13: OK ; measure (1.163, 0.54) ; threshold 0
- C14: OK ; measure 0.1493 ; threshold 0.04
- C15: FAIL ; measure None ; threshold (0, 0.585)
- C16: FAIL ; measure None ; threshold 0.6
- C2: OK ; measure 0.9058 ; threshold 0.5
- C3: OK ; measure 2.133 ; threshold 2
- C4: OK ; measure 0.8441 ; threshold 0
- C10: OK ; measure 0.02619 ; threshold 0.05

### R0037 (r-crowded-funding {L: 7, q: 0.5})
- C1: FAIL ; measure 0.08991 ; threshold 0.95
- C5: FAIL ; measure {2020: 1.657, 2021: 1.783, 2022: -1.065, 2023: 2.675, 2024: 1.498, 2025: -0.1062} ; threshold {sharpe_min: -1, positives_min: 4}
- C6: FAIL ; measure 0.7347 ; threshold 0.45
- C7: FAIL ; measure None ; threshold {min_neighbors_share: 0.75, ratio: 0.6, min_neighbor_sharpe: 0.5}
- C8: FAIL ; measure 0.9482 ; threshold 0.05
- C9: OK ; measure 0 ; threshold {random_cuts: 20, fixed_cuts: 3, not_full_share_min: 0.4, tolerance: 1e-09}
- C11: FAIL ; measure (-0.06173, -0.6449) ; threshold (0.5, 0)
- C12: OK ; measure (0.1025, 8.439) ; threshold (0.5, 15)
- C13: OK ; measure (0.9315, 0.3733) ; threshold 0
- C14: OK ; measure 0.2717 ; threshold 0.04
- C15: FAIL ; measure None ; threshold (0, 0.585)
- C16: FAIL ; measure None ; threshold 0.6
- C2: OK ; measure 0.7057 ; threshold 0.5
- C3: FAIL ; measure 1.989 ; threshold 2
- C4: OK ; measure 0.6252 ; threshold 0
- C10: OK ; measure 0.02579 ; threshold 0.05

### R0038 (r-crowded-funding {L: 7, q: 0.7})
- C1: FAIL ; measure 0.07657 ; threshold 0.95
- C5: FAIL ; measure {2020: 1.657, 2021: 2.43, 2022: -1.065, 2023: 1.408, 2024: 1.057, 2025: -0.2595} ; threshold {sharpe_min: -1, positives_min: 4}
- C6: FAIL ; measure 0.775 ; threshold 0.45
- C7: FAIL ; measure None ; threshold {min_neighbors_share: 0.75, ratio: 0.6, min_neighbor_sharpe: 0.5}
- C8: FAIL ; measure 0.9568 ; threshold 0.05
- C9: OK ; measure 0 ; threshold {random_cuts: 20, fixed_cuts: 3, not_full_share_min: 0.4, tolerance: 1e-09}
- C11: FAIL ; measure (-0.04573, -0.598) ; threshold (0.5, 0)
- C12: OK ; measure (0.09539, 8.098) ; threshold (0.5, 15)
- C13: OK ; measure (1.108, 0.03879) ; threshold 0
- C14: OK ; measure 0.2471 ; threshold 0.04
- C15: FAIL ; measure None ; threshold (0, 0.585)
- C16: FAIL ; measure None ; threshold 0.6
- C2: OK ; measure 0.6733 ; threshold 0.5
- C3: FAIL ; measure 1.785 ; threshold 2
- C4: OK ; measure 0.6026 ; threshold 0
- C10: OK ; measure 0.04199 ; threshold 0.05

### R0039 (r-crowded-funding {L: 7, q: 0.9})
- C1: FAIL ; measure 0.1481 ; threshold 0.95
- C5: FAIL ; measure {2020: 1.657, 2021: 2.421, 2022: -1.065, 2023: 1.826, 2024: 1.119, 2025: -0.2868} ; threshold {sharpe_min: -1, positives_min: 4}
- C6: FAIL ; measure 0.7906 ; threshold 0.45
- C7: FAIL ; measure None ; threshold {min_neighbors_share: 0.75, ratio: 0.6, min_neighbor_sharpe: 0.5}
- C8: FAIL ; measure 0.9856 ; threshold 0.05
- C9: OK ; measure 0 ; threshold {random_cuts: 20, fixed_cuts: 3, not_full_share_min: 0.4, tolerance: 1e-09}
- C11: FAIL ; measure (0.1251, -0.3901) ; threshold (0.5, 0)
- C12: OK ; measure (0.06857, 7.656) ; threshold (0.5, 15)
- C13: OK ; measure (1.216, 0.2695) ; threshold 0
- C14: OK ; measure 0.3922 ; threshold 0.04
- C15: FAIL ; measure None ; threshold (0, 0.585)
- C16: FAIL ; measure None ; threshold 0.6
- C2: OK ; measure 0.8252 ; threshold 0.5
- C3: OK ; measure 2.061 ; threshold 2
- C4: OK ; measure 0.7645 ; threshold 0
- C10: OK ; measure 0.022 ; threshold 0.05

### R0040 (r-crowded-funding {L: 14, q: 0.5})
- C1: FAIL ; measure 0.07856 ; threshold 0.95
- C5: FAIL ; measure {2020: 1.657, 2021: 2.126, 2022: -1.065, 2023: 2.772, 2024: 1.065, 2025: -0.5936} ; threshold {sharpe_min: -1, positives_min: 4}
- C6: FAIL ; measure 0.7331 ; threshold 0.45
- C7: FAIL ; measure None ; threshold {min_neighbors_share: 0.75, ratio: 0.6, min_neighbor_sharpe: 0.5}
- C8: FAIL ; measure 0.9594 ; threshold 0.05
- C9: OK ; measure 0 ; threshold {random_cuts: 20, fixed_cuts: 3, not_full_share_min: 0.4, tolerance: 1e-09}
- C11: FAIL ; measure (-0.08341, -0.6752) ; threshold (0.5, 0)
- C12: OK ; measure (0.09946, 7.745) ; threshold (0.5, 15)
- C13: OK ; measure (1.026, 0.1036) ; threshold 0
- C14: OK ; measure 0.2481 ; threshold 0.04
- C15: FAIL ; measure None ; threshold (0, 0.585)
- C16: FAIL ; measure None ; threshold 0.6
- C2: OK ; measure 0.6764 ; threshold 0.5
- C3: FAIL ; measure 1.847 ; threshold 2
- C4: OK ; measure 0.6017 ; threshold 0
- C10: OK ; measure 0.03379 ; threshold 0.05

### R0041 (r-crowded-funding {L: 14, q: 0.7})
- C1: FAIL ; measure 0.07024 ; threshold 0.95
- C5: FAIL ; measure {2020: 1.657, 2021: 2.266, 2022: -1.065, 2023: 1.612, 2024: 0.9307, 2025: -0.2722} ; threshold {sharpe_min: -1, positives_min: 4}
- C6: FAIL ; measure 0.7741 ; threshold 0.45
- C7: OK ; measure 1 ; threshold {min_neighbors_share: 0.75, ratio: 0.6, min_neighbor_sharpe: 0.5}
- C8: FAIL ; measure 0.9708 ; threshold 0.05
- C9: OK ; measure 0 ; threshold {random_cuts: 20, fixed_cuts: 3, not_full_share_min: 0.4, tolerance: 1e-09}
- C11: FAIL ; measure (-0.0294, -0.5751) ; threshold (0.5, 0)
- C12: OK ; measure (0.0915, 7.434) ; threshold (0.5, 15)
- C13: OK ; measure (1.054, 0.06476) ; threshold 0
- C14: OK ; measure 0.2295 ; threshold 0.04
- C15: FAIL ; measure None ; threshold (0, 0.585)
- C16: FAIL ; measure None ; threshold 0.6
- C2: OK ; measure 0.6535 ; threshold 0.5
- C3: FAIL ; measure 1.718 ; threshold 2
- C4: OK ; measure 0.5875 ; threshold 0
- C10: OK ; measure 0.04579 ; threshold 0.05

### R0042 (r-crowded-funding {L: 14, q: 0.9})
- C1: FAIL ; measure 0.1227 ; threshold 0.95
- C5: FAIL ; measure {2020: 1.657, 2021: 2.082, 2022: -1.065, 2023: 1.826, 2024: 1.427, 2025: -0.2868} ; threshold {sharpe_min: -1, positives_min: 4}
- C6: FAIL ; measure 0.7906 ; threshold 0.45
- C7: FAIL ; measure None ; threshold {min_neighbors_share: 0.75, ratio: 0.6, min_neighbor_sharpe: 0.5}
- C8: FAIL ; measure 0.9686 ; threshold 0.05
- C9: OK ; measure 0 ; threshold {random_cuts: 20, fixed_cuts: 3, not_full_share_min: 0.4, tolerance: 1e-09}
- C11: FAIL ; measure (0.1131, -0.4029) ; threshold (0.5, 0)
- C12: OK ; measure (0.07131, 7.381) ; threshold (0.5, 15)
- C13: OK ; measure (1.079, 0.3573) ; threshold 0
- C14: OK ; measure 0.3395 ; threshold 0.04
- C15: FAIL ; measure None ; threshold (0, 0.585)
- C16: FAIL ; measure None ; threshold 0.6
- C2: OK ; measure 0.7766 ; threshold 0.5
- C3: FAIL ; measure 1.983 ; threshold 2
- C4: OK ; measure 0.7172 ; threshold 0
- C10: OK ; measure 0.02819 ; threshold 0.05

### R0043 (r-crowded-funding {L: 28, q: 0.5})
- C1: FAIL ; measure 0.0612 ; threshold 0.95
- C5: FAIL ; measure {2020: 1.657, 2021: 2.309, 2022: -1.065, 2023: 1.823, 2024: 1.103, 2025: -0.08674} ; threshold {sharpe_min: -1, positives_min: 4}
- C6: FAIL ; measure 0.7234 ; threshold 0.45
- C7: FAIL ; measure None ; threshold {min_neighbors_share: 0.75, ratio: 0.6, min_neighbor_sharpe: 0.5}
- C8: FAIL ; measure 0.9722 ; threshold 0.05
- C9: OK ; measure 0 ; threshold {random_cuts: 20, fixed_cuts: 3, not_full_share_min: 0.4, tolerance: 1e-09}
- C11: FAIL ; measure (-0.1021, -0.664) ; threshold (0.5, 0)
- C12: OK ; measure (0.1016, 7.191) ; threshold (0.5, 15)
- C13: OK ; measure (0.9997, 0.007954) ; threshold 0
- C14: OK ; measure 0.2059 ; threshold 0.04
- C15: FAIL ; measure None ; threshold (0, 0.585)
- C16: FAIL ; measure None ; threshold 0.6
- C2: OK ; measure 0.6227 ; threshold 0.5
- C3: FAIL ; measure 1.608 ; threshold 2
- C4: OK ; measure 0.5522 ; threshold 0
- C10: FAIL ; measure 0.05439 ; threshold 0.05

### R0044 (r-crowded-funding {L: 28, q: 0.7})
- C1: FAIL ; measure 0.05972 ; threshold 0.95
- C5: FAIL ; measure {2020: 1.657, 2021: 1.626, 2022: -1.065, 2023: 1.787, 2024: 1.164, 2025: -0.2015} ; threshold {sharpe_min: -1, positives_min: 4}
- C6: FAIL ; measure 0.7906 ; threshold 0.45
- C7: FAIL ; measure None ; threshold {min_neighbors_share: 0.75, ratio: 0.6, min_neighbor_sharpe: 0.5}
- C8: FAIL ; measure 0.9734 ; threshold 0.05
- C9: OK ; measure 0 ; threshold {random_cuts: 20, fixed_cuts: 3, not_full_share_min: 0.4, tolerance: 1e-09}
- C11: FAIL ; measure (-0.06596, -0.6035) ; threshold (0.5, 0)
- C12: OK ; measure (0.08426, 6.637) ; threshold (0.5, 15)
- C13: OK ; measure (0.8923, 0.2324) ; threshold 0
- C14: OK ; measure 0.2021 ; threshold 0.04
- C15: FAIL ; measure None ; threshold (0, 0.585)
- C16: FAIL ; measure None ; threshold 0.6
- C2: OK ; measure 0.6219 ; threshold 0.5
- C3: FAIL ; measure 1.652 ; threshold 2
- C4: OK ; measure 0.5647 ; threshold 0
- C10: FAIL ; measure 0.05159 ; threshold 0.05

### R0045 (r-crowded-funding {L: 28, q: 0.9})
- C1: FAIL ; measure 0.05758 ; threshold 0.95
- C5: FAIL ; measure {2020: 1.657, 2021: 1.397, 2022: -1.065, 2023: 1.826, 2024: 1.198, 2025: -0.2868} ; threshold {sharpe_min: -1, positives_min: 4}
- C6: FAIL ; measure 0.7906 ; threshold 0.45
- C7: FAIL ; measure None ; threshold {min_neighbors_share: 0.75, ratio: 0.6, min_neighbor_sharpe: 0.5}
- C8: FAIL ; measure 0.9736 ; threshold 0.05
- C9: OK ; measure 0 ; threshold {random_cuts: 20, fixed_cuts: 3, not_full_share_min: 0.4, tolerance: 1e-09}
- C11: FAIL ; measure (-0.04743, -0.5569) ; threshold (0.5, 0)
- C12: OK ; measure (0.08085, 6.646) ; threshold (0.5, 15)
- C13: OK ; measure (0.8368, 0.3145) ; threshold 0
- C14: OK ; measure 0.1865 ; threshold 0.04
- C15: FAIL ; measure None ; threshold (0, 0.585)
- C16: FAIL ; measure None ; threshold 0.6
- C2: OK ; measure 0.6133 ; threshold 0.5
- C3: FAIL ; measure 1.641 ; threshold 2
- C4: OK ; measure 0.5595 ; threshold 0
- C10: FAIL ; measure 0.05259 ; threshold 0.05

## Selection

No candidate: outcome B if no other wave is decided.
