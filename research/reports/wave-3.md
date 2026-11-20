# Wave 3

Orchestrator document: it contains figures and is given to no agent. Agents only receive `wave-3-statuses.json`.

Grid trials: 100; extra lines (arena, control): 0; of which re-read from the journal without a rerun (resume): 0; actual N in the journal: 220; DSR N: 726.
Best DSR: 0.001438. Stop rule triggered: yes.

## All trials

| id | family | parameters | code | net Sharpe | failed gates | passed |
|---|---|---|---|---|---|---|
| R0121 | p-levier-accelere | {fenetre_long: 20, h_bas: 0.3} | OK | 1.115 | C1, C6, C7, C8, C11, C16 | no |
| R0122 | p-levier-accelere | {fenetre_long: 20, h_bas: 0.39} | OK | 1.099 | C1, C6, C7, C8, C11, C16 | no |
| R0123 | p-levier-accelere | {fenetre_long: 20, h_bas: 0.5} | OK | 1.171 | C1, C6, C7, C8, C11, C16 | no |
| R0124 | p-levier-accelere | {fenetre_long: 20, h_bas: 0.65} | OK | 1.314 | C1, C6, C7, C11, C16 | no |
| R0125 | p-levier-accelere | {fenetre_long: 20, h_bas: 0.84} | OK | 1.425 | C1, C6, C7, C11, C16 | no |
| R0126 | p-levier-accelere | {fenetre_long: 32, h_bas: 0.3} | OK | 0.9314 | C1, C6, C7, C8, C11, C16 | no |
| R0127 | p-levier-accelere | {fenetre_long: 32, h_bas: 0.39} | OK | 0.9938 | C1, C6, C8, C11, C16 | no |
| R0128 | p-levier-accelere | {fenetre_long: 32, h_bas: 0.5} | OK | 1.043 | C1, C6, C8, C11, C16 | no |
| R0129 | p-levier-accelere | {fenetre_long: 32, h_bas: 0.65} | OK | 1.152 | C1, C6, C8, C11, C16 | no |
| R0130 | p-levier-accelere | {fenetre_long: 32, h_bas: 0.84} | OK | 1.333 | C1, C6, C7, C8, C11, C16 | no |
| R0131 | p-levier-accelere | {fenetre_long: 50, h_bas: 0.3} | OK | 1.041 | C1, C6, C7, C8, C11, C16 | no |
| R0132 | p-levier-accelere | {fenetre_long: 50, h_bas: 0.39} | OK | 1.057 | C1, C6, C8, C11, C16 | no |
| R0133 | p-levier-accelere | {fenetre_long: 50, h_bas: 0.5} | OK | 1.121 | C1, C6, C8, C11, C16 | no |
| R0134 | p-levier-accelere | {fenetre_long: 50, h_bas: 0.65} | OK | 1.216 | C1, C6, C8, C11, C16 | no |
| R0135 | p-levier-accelere | {fenetre_long: 50, h_bas: 0.84} | OK | 1.364 | C1, C6, C7, C8, C11, C16 | no |
| R0136 | p-levier-accelere | {fenetre_long: 80, h_bas: 0.3} | OK | 0.915 | C1, C6, C7, C8, C11, C16 | no |
| R0137 | p-levier-accelere | {fenetre_long: 80, h_bas: 0.39} | OK | 0.9518 | C1, C6, C8, C11, C16 | no |
| R0138 | p-levier-accelere | {fenetre_long: 80, h_bas: 0.5} | OK | 1.03 | C1, C6, C8, C11, C16 | no |
| R0139 | p-levier-accelere | {fenetre_long: 80, h_bas: 0.65} | OK | 1.208 | C1, C6, C8, C11, C16 | no |
| R0140 | p-levier-accelere | {fenetre_long: 80, h_bas: 0.84} | OK | 1.352 | C1, C6, C7, C8, C11, C16 | no |
| R0141 | p-levier-accelere | {fenetre_long: 126, h_bas: 0.3} | OK | 0.9543 | C1, C6, C7, C8, C11, C16 | no |
| R0142 | p-levier-accelere | {fenetre_long: 126, h_bas: 0.39} | OK | 1.001 | C1, C6, C7, C8, C11, C16 | no |
| R0143 | p-levier-accelere | {fenetre_long: 126, h_bas: 0.5} | OK | 1.052 | C1, C6, C7, C8, C11, C16 | no |
| R0144 | p-levier-accelere | {fenetre_long: 126, h_bas: 0.65} | OK | 1.194 | C1, C6, C7, C8, C11, C16 | no |
| R0145 | p-levier-accelere | {fenetre_long: 126, h_bas: 0.84} | OK | 1.349 | C1, C6, C7, C8, C11, C16 | no |
| R0146 | r-cible-vol-perp | {L_vol_jours: 10, sigma_cible: 0.06} | OK | 2.342 | C1, C5, C7, C16 | no |
| R0147 | r-cible-vol-perp | {L_vol_jours: 10, sigma_cible: 0.08} | OK | 1.965 | C1, C5, C7, C16 | no |
| R0148 | r-cible-vol-perp | {L_vol_jours: 10, sigma_cible: 0.11} | OK | 1.646 | C1, C5, C7, C16 | no |
| R0149 | r-cible-vol-perp | {L_vol_jours: 10, sigma_cible: 0.15} | OK | 1.427 | C1, C5, C7, C16 | no |
| R0150 | r-cible-vol-perp | {L_vol_jours: 10, sigma_cible: 0.22} | OK | 1.215 | C1, C5, C6, C7, C8, C11, C16 | no |
| R0151 | r-cible-vol-perp | {L_vol_jours: 20, sigma_cible: 0.06} | OK | 2.276 | C1, C5, C7, C16 | no |
| R0152 | r-cible-vol-perp | {L_vol_jours: 20, sigma_cible: 0.08} | OK | 1.988 | C1, C5, C16 | no |
| R0153 | r-cible-vol-perp | {L_vol_jours: 20, sigma_cible: 0.11} | OK | 1.666 | C1, C5, C16 | no |
| R0154 | r-cible-vol-perp | {L_vol_jours: 20, sigma_cible: 0.15} | OK | 1.455 | C1, C5, C16 | no |
| R0155 | r-cible-vol-perp | {L_vol_jours: 20, sigma_cible: 0.22} | OK | 1.179 | C1, C5, C6, C7, C8, C11, C16 | no |
| R0156 | r-cible-vol-perp | {L_vol_jours: 40, sigma_cible: 0.06} | OK | 2.396 | C1, C5, C7, C16 | no |
| R0157 | r-cible-vol-perp | {L_vol_jours: 40, sigma_cible: 0.08} | OK | 2.004 | C1, C5, C16 | no |
| R0158 | r-cible-vol-perp | {L_vol_jours: 40, sigma_cible: 0.11} | OK | 1.698 | C1, C5, C16 | no |
| R0159 | r-cible-vol-perp | {L_vol_jours: 40, sigma_cible: 0.15} | OK | 1.498 | C1, C5, C16 | no |
| R0160 | r-cible-vol-perp | {L_vol_jours: 40, sigma_cible: 0.22} | OK | 1.297 | C1, C5, C6, C7, C16 | no |
| R0161 | r-cible-vol-perp | {L_vol_jours: 80, sigma_cible: 0.06} | OK | 2.448 | C1, C5, C7, C16 | no |
| R0162 | r-cible-vol-perp | {L_vol_jours: 80, sigma_cible: 0.08} | OK | 2.148 | C1, C5, C16 | no |
| R0163 | r-cible-vol-perp | {L_vol_jours: 80, sigma_cible: 0.11} | OK | 1.75 | C1, C5, C16 | no |
| R0164 | r-cible-vol-perp | {L_vol_jours: 80, sigma_cible: 0.15} | OK | 1.472 | C1, C5, C16 | no |
| R0165 | r-cible-vol-perp | {L_vol_jours: 80, sigma_cible: 0.22} | OK | 1.247 | C1, C5, C6, C7, C16 | no |
| R0166 | r-cible-vol-perp | {L_vol_jours: 160, sigma_cible: 0.06} | OK | 2.477 | C1, C5, C7, C16 | no |
| R0167 | r-cible-vol-perp | {L_vol_jours: 160, sigma_cible: 0.08} | OK | 2.137 | C1, C5, C7, C16 | no |
| R0168 | r-cible-vol-perp | {L_vol_jours: 160, sigma_cible: 0.11} | OK | 1.808 | C1, C5, C7, C16 | no |
| R0169 | r-cible-vol-perp | {L_vol_jours: 160, sigma_cible: 0.15} | OK | 1.488 | C1, C5, C7, C16 | no |
| R0170 | r-cible-vol-perp | {L_vol_jours: 160, sigma_cible: 0.22} | OK | 1.266 | C1, C5, C7, C16 | no |
| R0171 | r-coussin-plancher | {W_jours: 7, f_plancher: 0.01} | OK | 1.86 | C1, C5, C7, C16 | no |
| R0172 | r-coussin-plancher | {W_jours: 7, f_plancher: 0.016} | OK | 1.385 | C1, C5, C7, C16 | no |
| R0173 | r-coussin-plancher | {W_jours: 7, f_plancher: 0.025} | OK | 1.089 | C1, C5, C6, C7, C8, C11, C16 | no |
| R0174 | r-coussin-plancher | {W_jours: 7, f_plancher: 0.04} | OK | 1.175 | C1, C5, C6, C7, C8, C11, C16 | no |
| R0175 | r-coussin-plancher | {W_jours: 7, f_plancher: 0.06} | OK | 1.226 | C1, C5, C6, C7, C11, C16 | no |
| R0176 | r-coussin-plancher | {W_jours: 14, f_plancher: 0.01} | OK | 1.701 | C1, C5, C7, C16 | no |
| R0177 | r-coussin-plancher | {W_jours: 14, f_plancher: 0.016} | OK | 1.523 | C1, C5, C16 | no |
| R0178 | r-coussin-plancher | {W_jours: 14, f_plancher: 0.025} | OK | 1.263 | C1, C5, C8, C11, C16 | no |
| R0179 | r-coussin-plancher | {W_jours: 14, f_plancher: 0.04} | OK | 1.195 | C1, C5, C6, C8, C11, C16 | no |
| R0180 | r-coussin-plancher | {W_jours: 14, f_plancher: 0.06} | OK | 1.21 | C1, C5, C6, C7, C11, C16 | no |
| R0181 | r-coussin-plancher | {W_jours: 28, f_plancher: 0.01} | OK | 1.908 | C1, C5, C7, C16 | no |
| R0182 | r-coussin-plancher | {W_jours: 28, f_plancher: 0.016} | OK | 1.812 | C1, C5, C16 | no |
| R0183 | r-coussin-plancher | {W_jours: 28, f_plancher: 0.025} | OK | 1.467 | C1, C5, C16 | no |
| R0184 | r-coussin-plancher | {W_jours: 28, f_plancher: 0.04} | OK | 1.196 | C1, C5, C6, C8, C11, C16 | no |
| R0185 | r-coussin-plancher | {W_jours: 28, f_plancher: 0.06} | OK | 1.216 | C1, C5, C6, C7, C11, C16 | no |
| R0186 | r-coussin-plancher | {W_jours: 56, f_plancher: 0.01} | OK | 2.186 | C1, C5, C7, C16 | no |
| R0187 | r-coussin-plancher | {W_jours: 56, f_plancher: 0.016} | OK | 2.091 | C1, C5, C16 | no |
| R0188 | r-coussin-plancher | {W_jours: 56, f_plancher: 0.025} | OK | 1.545 | C1, C5, C16 | no |
| R0189 | r-coussin-plancher | {W_jours: 56, f_plancher: 0.04} | OK | 1.351 | C1, C5, C6, C11, C16 | no |
| R0190 | r-coussin-plancher | {W_jours: 56, f_plancher: 0.06} | OK | 1.397 | C1, C6, C7, C11, C16 | no |
| R0191 | r-coussin-plancher | {W_jours: 112, f_plancher: 0.01} | OK | 2.279 | C1, C5, C7, C16 | no |
| R0192 | r-coussin-plancher | {W_jours: 112, f_plancher: 0.016} | OK | 2.108 | C1, C5, C7, C16 | no |
| R0193 | r-coussin-plancher | {W_jours: 112, f_plancher: 0.025} | OK | 1.56 | C1, C5, C7, C11, C16 | no |
| R0194 | r-coussin-plancher | {W_jours: 112, f_plancher: 0.04} | OK | 1.379 | C1, C5, C7, C11, C16 | no |
| R0195 | r-coussin-plancher | {W_jours: 112, f_plancher: 0.06} | OK | 1.255 | C1, C5, C6, C7, C8, C11, C16 | no |
| R0196 | t-ecart | {L_jours: 30, zs_saturation: 0.15} | OK | 1.544 | C1, C5, C7, C16 | no |
| R0197 | t-ecart | {L_jours: 30, zs_saturation: 0.25} | OK | 1.591 | C1, C5, C7, C16 | no |
| R0198 | t-ecart | {L_jours: 30, zs_saturation: 0.4} | OK | 1.632 | C1, C5, C7, C16 | no |
| R0199 | t-ecart | {L_jours: 30, zs_saturation: 0.65} | OK | 1.622 | C1, C5, C7, C16 | no |
| R0200 | t-ecart | {L_jours: 30, zs_saturation: 1} | OK | 1.588 | C1, C5, C7, C16 | no |
| R0201 | t-ecart | {L_jours: 50, zs_saturation: 0.15} | OK | 1.512 | C1, C5, C7, C16 | no |
| R0202 | t-ecart | {L_jours: 50, zs_saturation: 0.25} | OK | 1.52 | C1, C5, C16 | no |
| R0203 | t-ecart | {L_jours: 50, zs_saturation: 0.4} | OK | 1.509 | C1, C5, C16 | no |
| R0204 | t-ecart | {L_jours: 50, zs_saturation: 0.65} | OK | 1.541 | C1, C5, C16 | no |
| R0205 | t-ecart | {L_jours: 50, zs_saturation: 1} | OK | 1.503 | C1, C5, C7, C16 | no |
| R0206 | t-ecart | {L_jours: 80, zs_saturation: 0.15} | OK | 1.272 | C1, C5, C6, C7, C8, C11, C16 | no |
| R0207 | t-ecart | {L_jours: 80, zs_saturation: 0.25} | OK | 1.301 | C1, C5, C6, C8, C11, C16 | no |
| R0208 | t-ecart | {L_jours: 80, zs_saturation: 0.4} | OK | 1.316 | C1, C5, C11, C16 | no |
| R0209 | t-ecart | {L_jours: 80, zs_saturation: 0.65} | OK | 1.373 | C1, C5, C11, C16 | no |
| R0210 | t-ecart | {L_jours: 80, zs_saturation: 1} | OK | 1.381 | C1, C5, C7, C11, C16 | no |
| R0211 | t-ecart | {L_jours: 130, zs_saturation: 0.15} | OK | 1.185 | C1, C5, C6, C7, C8, C11, C16 | no |
| R0212 | t-ecart | {L_jours: 130, zs_saturation: 0.25} | OK | 1.205 | C1, C5, C6, C8, C11, C16 | no |
| R0213 | t-ecart | {L_jours: 130, zs_saturation: 0.4} | OK | 1.229 | C1, C5, C8, C11, C16 | no |
| R0214 | t-ecart | {L_jours: 130, zs_saturation: 0.65} | OK | 1.26 | C1, C5, C8, C11, C16 | no |
| R0215 | t-ecart | {L_jours: 130, zs_saturation: 1} | OK | 1.329 | C1, C5, C7, C11, C16 | no |
| R0216 | t-ecart | {L_jours: 210, zs_saturation: 0.15} | OK | 1.018 | C1, C5, C6, C7, C8, C11, C16 | no |
| R0217 | t-ecart | {L_jours: 210, zs_saturation: 0.25} | OK | 1.032 | C1, C5, C6, C7, C8, C11, C16 | no |
| R0218 | t-ecart | {L_jours: 210, zs_saturation: 0.4} | OK | 1.073 | C1, C5, C6, C7, C8, C11, C16 | no |
| R0219 | t-ecart | {L_jours: 210, zs_saturation: 0.65} | OK | 1.142 | C1, C5, C7, C8, C11, C16 | no |
| R0220 | t-ecart | {L_jours: 210, zs_saturation: 1} | OK | 1.209 | C1, C5, C7, C8, C11, C16 | no |

## Detailed verdicts

C16: measure = (share, positives, evaluable, not evaluable, size of the control universe); the share is relative to the fixed size of the universe.

### R0121 (p-levier-accelere {fenetre_long: 20, h_bas: 0.3})
- C1: FAIL; measure 6.505e-11; threshold 0.95
- C5: OK; measure {2020: 2.031, 2021: 2.565, 2022: -0.7628, 2023: 1.61, 2024: 1.283, 2025: 0.4045}; threshold {sharpe_min: -1, positives_min: 4}
- C6: FAIL; measure 0.371; threshold 0.2
- C7: FAIL; measure None; threshold {min_neighbors_share: 0.75, ratio: 0.6, min_neighbor_sharpe: 0.5}
- C8: FAIL; measure (1.352, 0.3511); threshold (2, 0.3)
- C9: OK; measure 1.388e-16; threshold {random_cuts: 20, fixed_cuts: 3, not_full_share_min: 0.4, tolerance: 1e-09}
- C11: FAIL; measure (0.3276, -0.2534); threshold (0.5574, 0)
- C12: OK; measure (0.04459, 7.475); threshold (0.5, 40)
- C13: OK; measure (1.566, 0.3759); threshold 0
- C14: OK; measure 0.3387; threshold 0.04
- C15: OK; measure not applicable (hedged); threshold None
- C16: FAIL; measure None; threshold 0.6
- C2: OK; measure 1.115; threshold 0.5
- C3: OK; measure 2.785; threshold 2
- C4: OK; measure 1.063; threshold 0
- C10: OK; measure 0.002999; threshold 0.05

### R0122 (p-levier-accelere {fenetre_long: 20, h_bas: 0.39})
- C1: FAIL; measure 5.227e-11; threshold 0.95
- C5: OK; measure {2020: 2.022, 2021: 2.602, 2022: -0.9282, 2023: 1.724, 2024: 1.373, 2025: 0.3192}; threshold {sharpe_min: -1, positives_min: 4}
- C6: FAIL; measure 0.3602; threshold 0.2
- C7: FAIL; measure None; threshold {min_neighbors_share: 0.75, ratio: 0.6, min_neighbor_sharpe: 0.5}
- C8: FAIL; measure (1.266, 0.316); threshold (2, 0.3)
- C9: OK; measure 2.22e-16; threshold {random_cuts: 20, fixed_cuts: 3, not_full_share_min: 0.4, tolerance: 1e-09}
- C11: FAIL; measure (0.3229, -0.2489); threshold (0.5497, 0)
- C12: OK; measure (0.04562, 6.545); threshold (0.5, 40)
- C13: OK; measure (1.546, 0.3492); threshold 0
- C14: OK; measure 0.3024; threshold 0.04
- C15: OK; measure not applicable (hedged); threshold None
- C16: FAIL; measure None; threshold 0.6
- C2: OK; measure 1.099; threshold 0.5
- C3: OK; measure 2.676; threshold 2
- C4: OK; measure 1.047; threshold 0
- C10: OK; measure 0.003999; threshold 0.05

### R0123 (p-levier-accelere {fenetre_long: 20, h_bas: 0.5})
- C1: FAIL; measure 2.058e-10; threshold 0.95
- C5: OK; measure {2020: 2.077, 2021: 2.585, 2022: -0.8055, 2023: 1.821, 2024: 1.576, 2025: 0.2015}; threshold {sharpe_min: -1, positives_min: 4}
- C6: FAIL; measure 0.2906; threshold 0.2
- C7: FAIL; measure None; threshold {min_neighbors_share: 0.75, ratio: 0.6, min_neighbor_sharpe: 0.5}
- C8: FAIL; measure (1.568, 0.2765); threshold (2, 0.3)
- C9: OK; measure 9.714e-17; threshold {random_cuts: 20, fixed_cuts: 3, not_full_share_min: 0.4, tolerance: 1e-09}
- C11: FAIL; measure (0.3943, -0.1719); threshold (0.5853, 0)
- C12: OK; measure (0.04359, 5.498); threshold (0.5, 40)
- C13: OK; measure (1.614, 0.4205); threshold 0
- C14: OK; measure 0.2918; threshold 0.04
- C15: OK; measure not applicable (hedged); threshold None
- C16: FAIL; measure None; threshold 0.6
- C2: OK; measure 1.171; threshold 0.5
- C3: OK; measure 2.772; threshold 2
- C4: OK; measure 1.117; threshold 0
- C10: OK; measure 0.003199; threshold 0.05

### R0124 (p-levier-accelere {fenetre_long: 20, h_bas: 0.65})
- C1: FAIL; measure 1.658e-09; threshold 0.95
- C5: OK; measure {2020: 2.168, 2021: 2.95, 2022: -0.8674, 2023: 1.673, 2024: 1.497, 2025: 0.3769}; threshold {sharpe_min: -1, positives_min: 4}
- C6: FAIL; measure 0.2433; threshold 0.2
- C7: FAIL; measure None; threshold {min_neighbors_share: 0.75, ratio: 0.6, min_neighbor_sharpe: 0.5}
- C8: OK; measure (2.042, 0.2191); threshold (2, 0.3)
- C9: OK; measure 1.18e-16; threshold {random_cuts: 20, fixed_cuts: 3, not_full_share_min: 0.4, tolerance: 1e-09}
- C11: FAIL; measure (0.5188, -0.09976); threshold (0.6571, 0)
- C12: OK; measure (0.04339, 4.298); threshold (0.5, 40)
- C13: OK; measure (1.794, 0.4976); threshold 0
- C14: OK; measure 0.2735; threshold 0.04
- C15: OK; measure not applicable (hedged); threshold None
- C16: FAIL; measure None; threshold 0.6
- C2: OK; measure 1.314; threshold 0.5
- C3: OK; measure 2.903; threshold 2
- C4: OK; measure 1.255; threshold 0
- C10: OK; measure 0.0024; threshold 0.05

### R0125 (p-levier-accelere {fenetre_long: 20, h_bas: 0.84})
- C1: FAIL; measure 1.078e-08; threshold 0.95
- C5: OK; measure {2020: 2.159, 2021: 3.106, 2022: -0.8191, 2023: 2.037, 2024: 2.365, 2025: 0.4404}; threshold {sharpe_min: -1, positives_min: 4}
- C6: FAIL; measure 0.2039; threshold 0.2
- C7: FAIL; measure None; threshold {min_neighbors_share: 0.75, ratio: 0.6, min_neighbor_sharpe: 0.5}
- C8: OK; measure (2.196, 0.1537); threshold (2, 0.3)
- C9: OK; measure 1.318e-16; threshold {random_cuts: 20, fixed_cuts: 3, not_full_share_min: 0.4, tolerance: 1e-09}
- C11: FAIL; measure (0.6188, -0.05888); threshold (0.7123, 0)
- C12: OK; measure (0.04695, 3.436); threshold (0.5, 40)
- C13: OK; measure (1.912, 0.8153); threshold 0
- C14: OK; measure 0.2333; threshold 0.04
- C15: OK; measure not applicable (hedged); threshold None
- C16: FAIL; measure None; threshold 0.6
- C2: OK; measure 1.425; threshold 0.5
- C3: OK; measure 2.913; threshold 2
- C4: OK; measure 1.355; threshold 0
- C10: OK; measure 0.002799; threshold 0.05

### R0126 (p-levier-accelere {fenetre_long: 32, h_bas: 0.3})
- C1: FAIL; measure 5.739e-12; threshold 0.95
- C5: OK; measure {2020: 1.648, 2021: 2.275, 2022: -0.8752, 2023: 1.805, 2024: 1.055, 2025: 0.3766}; threshold {sharpe_min: -1, positives_min: 4}
- C6: FAIL; measure 0.3969; threshold 0.2
- C7: FAIL; measure None; threshold {min_neighbors_share: 0.75, ratio: 0.6, min_neighbor_sharpe: 0.5}
- C8: FAIL; measure (0.2606, 0.3626); threshold (2, 0.3)
- C9: OK; measure 1.943e-16; threshold {random_cuts: 20, fixed_cuts: 3, not_full_share_min: 0.4, tolerance: 1e-09}
- C11: FAIL; measure (0.1375, -0.4253); threshold (0.5, 0)
- C12: OK; measure (0.04623, 6.182); threshold (0.5, 40)
- C13: OK; measure (1.297, 0.3283); threshold 0
- C14: OK; measure 0.2744; threshold 0.04
- C15: OK; measure not applicable (hedged); threshold None
- C16: FAIL; measure None; threshold 0.6
- C2: OK; measure 0.9314; threshold 0.5
- C3: OK; measure 2.31; threshold 2
- C4: OK; measure 0.8861; threshold 0
- C10: OK; measure 0.0118; threshold 0.05

### R0127 (p-levier-accelere {fenetre_long: 32, h_bas: 0.39})
- C1: FAIL; measure 3.491e-11; threshold 0.95
- C5: OK; measure {2020: 1.581, 2021: 2.44, 2022: -0.7905, 2023: 1.894, 2024: 1.231, 2025: 0.3536}; threshold {sharpe_min: -1, positives_min: 4}
- C6: FAIL; measure 0.3842; threshold 0.2
- C7: OK; measure 1; threshold {min_neighbors_share: 0.75, ratio: 0.6, min_neighbor_sharpe: 0.5}
- C8: FAIL; measure (0.6037, 0.3228); threshold (2, 0.3)
- C9: OK; measure 1.318e-16; threshold {random_cuts: 20, fixed_cuts: 3, not_full_share_min: 0.4, tolerance: 1e-09}
- C11: FAIL; measure (0.2254, -0.3299); threshold (0.5, 0)
- C12: OK; measure (0.04413, 5.416); threshold (0.5, 40)
- C13: OK; measure (1.364, 0.381); threshold 0
- C14: OK; measure 0.2721; threshold 0.04
- C15: OK; measure not applicable (hedged); threshold None
- C16: FAIL; measure None; threshold 0.6
- C2: OK; measure 0.9938; threshold 0.5
- C3: OK; measure 2.423; threshold 2
- C4: OK; measure 0.9479; threshold 0
- C10: OK; measure 0.009198; threshold 0.05

### R0128 (p-levier-accelere {fenetre_long: 32, h_bas: 0.5})
- C1: FAIL; measure 8.682e-11; threshold 0.95
- C5: OK; measure {2020: 1.628, 2021: 2.512, 2022: -0.9192, 2023: 1.918, 2024: 1.398, 2025: 0.3698}; threshold {sharpe_min: -1, positives_min: 4}
- C6: FAIL; measure 0.344; threshold 0.2
- C7: OK; measure 1; threshold {min_neighbors_share: 0.75, ratio: 0.6, min_neighbor_sharpe: 0.5}
- C8: FAIL; measure (0.8404, 0.2808); threshold (2, 0.3)
- C9: OK; measure 1.804e-16; threshold {random_cuts: 20, fixed_cuts: 3, not_full_share_min: 0.4, tolerance: 1e-09}
- C11: FAIL; measure (0.283, -0.2922); threshold (0.5217, 0)
- C12: OK; measure (0.04458, 4.682); threshold (0.5, 40)
- C13: OK; measure (1.399, 0.4736); threshold 0
- C14: OK; measure 0.257; threshold 0.04
- C15: OK; measure not applicable (hedged); threshold None
- C16: FAIL; measure None; threshold 0.6
- C2: OK; measure 1.043; threshold 0.5
- C3: OK; measure 2.473; threshold 2
- C4: OK; measure 0.9945; threshold 0
- C10: OK; measure 0.007199; threshold 0.05

### R0129 (p-levier-accelere {fenetre_long: 32, h_bas: 0.65})
- C1: FAIL; measure 4.52e-10; threshold 0.95
- C5: OK; measure {2020: 1.804, 2021: 2.763, 2022: -0.9126, 2023: 1.971, 2024: 1.396, 2025: 0.2417}; threshold {sharpe_min: -1, positives_min: 4}
- C6: FAIL; measure 0.2883; threshold 0.2
- C7: OK; measure 1; threshold {min_neighbors_share: 0.75, ratio: 0.6, min_neighbor_sharpe: 0.5}
- C8: FAIL; measure (1.282, 0.2211); threshold (2, 0.3)
- C9: OK; measure 1.249e-16; threshold {random_cuts: 20, fixed_cuts: 3, not_full_share_min: 0.4, tolerance: 1e-09}
- C11: FAIL; measure (0.3657, -0.226); threshold (0.5758, 0)
- C12: OK; measure (0.04722, 4.01); threshold (0.5, 40)
- C13: OK; measure (1.577, 0.4156); threshold 0
- C14: OK; measure 0.2382; threshold 0.04
- C15: OK; measure not applicable (hedged); threshold None
- C16: FAIL; measure None; threshold 0.6
- C2: OK; measure 1.152; threshold 0.5
- C3: OK; measure 2.576; threshold 2
- C4: OK; measure 1.095; threshold 0
- C10: OK; measure 0.005999; threshold 0.05

### R0130 (p-levier-accelere {fenetre_long: 32, h_bas: 0.84})
- C1: FAIL; measure 5.558e-09; threshold 0.95
- C5: OK; measure {2020: 2.021, 2021: 2.955, 2022: -0.8248, 2023: 2.373, 2024: 2.321, 2025: 0.2942}; threshold {sharpe_min: -1, positives_min: 4}
- C6: FAIL; measure 0.2246; threshold 0.2
- C7: FAIL; measure None; threshold {min_neighbors_share: 0.75, ratio: 0.6, min_neighbor_sharpe: 0.5}
- C8: FAIL; measure (1.872, 0.1554); threshold (2, 0.3)
- C9: OK; measure 9.021e-17; threshold {random_cuts: 20, fixed_cuts: 3, not_full_share_min: 0.4, tolerance: 1e-09}
- C11: FAIL; measure (0.5226, -0.1265); threshold (0.6667, 0)
- C12: OK; measure (0.04828, 3.275); threshold (0.5, 40)
- C13: OK; measure (1.795, 0.7332); threshold 0
- C14: OK; measure 0.2195; threshold 0.04
- C15: OK; measure not applicable (hedged); threshold None
- C16: FAIL; measure None; threshold 0.6
- C2: OK; measure 1.333; threshold 0.5
- C3: OK; measure 2.757; threshold 2
- C4: OK; measure 1.266; threshold 0
- C10: OK; measure 0.004199; threshold 0.05

### R0131 (p-levier-accelere {fenetre_long: 50, h_bas: 0.3})
- C1: FAIL; measure 2.192e-11; threshold 0.95
- C5: OK; measure {2020: 1.906, 2021: 2.323, 2022: -0.8073, 2023: 2.169, 2024: 0.9764, 2025: 0.415}; threshold {sharpe_min: -1, positives_min: 4}
- C6: FAIL; measure 0.3883; threshold 0.2
- C7: FAIL; measure None; threshold {min_neighbors_share: 0.75, ratio: 0.6, min_neighbor_sharpe: 0.5}
- C8: FAIL; measure (0.9101, 0.3541); threshold (2, 0.3)
- C9: OK; measure 1.041e-16; threshold {random_cuts: 20, fixed_cuts: 3, not_full_share_min: 0.4, tolerance: 1e-09}
- C11: FAIL; measure (0.2663, -0.2916); threshold (0.5205, 0)
- C12: OK; measure (0.03803, 5.208); threshold (0.5, 40)
- C13: OK; measure (1.412, 0.4571); threshold 0
- C14: OK; measure 0.3132; threshold 0.04
- C15: OK; measure not applicable (hedged); threshold None
- C16: FAIL; measure None; threshold 0.6
- C2: OK; measure 1.041; threshold 0.5
- C3: OK; measure 2.618; threshold 2
- C4: OK; measure 0.9999; threshold 0
- C10: OK; measure 0.004999; threshold 0.05

### R0132 (p-levier-accelere {fenetre_long: 50, h_bas: 0.39})
- C1: FAIL; measure 3.113e-11; threshold 0.95
- C5: OK; measure {2020: 1.957, 2021: 2.313, 2022: -0.8621, 2023: 2.234, 2024: 1.052, 2025: 0.3224}; threshold {sharpe_min: -1, positives_min: 4}
- C6: FAIL; measure 0.3636; threshold 0.2
- C7: OK; measure 1; threshold {min_neighbors_share: 0.75, ratio: 0.6, min_neighbor_sharpe: 0.5}
- C8: FAIL; measure (1.008, 0.3167); threshold (2, 0.3)
- C9: OK; measure 1.249e-16; threshold {random_cuts: 20, fixed_cuts: 3, not_full_share_min: 0.4, tolerance: 1e-09}
- C11: FAIL; measure (0.2842, -0.2855); threshold (0.5284, 0)
- C12: OK; measure (0.04094, 4.955); threshold (0.5, 40)
- C13: OK; measure (1.434, 0.4499); threshold 0
- C14: OK; measure 0.2899; threshold 0.04
- C15: OK; measure not applicable (hedged); threshold None
- C16: FAIL; measure None; threshold 0.6
- C2: OK; measure 1.057; threshold 0.5
- C3: OK; measure 2.614; threshold 2
- C4: OK; measure 1.011; threshold 0
- C10: OK; measure 0.004399; threshold 0.05

### R0133 (p-levier-accelere {fenetre_long: 50, h_bas: 0.5})
- C1: FAIL; measure 9.013e-11; threshold 0.95
- C5: OK; measure {2020: 1.936, 2021: 2.565, 2022: -0.9594, 2023: 2.095, 2024: 1.123, 2025: 0.2383}; threshold {sharpe_min: -1, positives_min: 4}
- C6: FAIL; measure 0.3181; threshold 0.2
- C7: OK; measure 1; threshold {min_neighbors_share: 0.75, ratio: 0.6, min_neighbor_sharpe: 0.5}
- C8: FAIL; measure (1.278, 0.2758); threshold (2, 0.3)
- C9: OK; measure 1.804e-16; threshold {random_cuts: 20, fixed_cuts: 3, not_full_share_min: 0.4, tolerance: 1e-09}
- C11: FAIL; measure (0.3564, -0.2327); threshold (0.5605, 0)
- C12: OK; measure (0.04106, 4.2); threshold (0.5, 40)
- C13: OK; measure (1.541, 0.4132); threshold 0
- C14: OK; measure 0.276; threshold 0.04
- C15: OK; measure not applicable (hedged); threshold None
- C16: FAIL; measure None; threshold 0.6
- C2: OK; measure 1.121; threshold 0.5
- C3: OK; measure 2.641; threshold 2
- C4: OK; measure 1.073; threshold 0
- C10: OK; measure 0.004599; threshold 0.05

### R0134 (p-levier-accelere {fenetre_long: 50, h_bas: 0.65})
- C1: FAIL; measure 6.048e-10; threshold 0.95
- C5: OK; measure {2020: 2.098, 2021: 2.655, 2022: -0.9797, 2023: 2.262, 2024: 1.357, 2025: 0.2209}; threshold {sharpe_min: -1, positives_min: 4}
- C6: FAIL; measure 0.2623; threshold 0.2
- C7: OK; measure 1; threshold {min_neighbors_share: 0.75, ratio: 0.6, min_neighbor_sharpe: 0.5}
- C8: FAIL; measure (1.584, 0.2194); threshold (2, 0.3)
- C9: OK; measure 1.388e-16; threshold {random_cuts: 20, fixed_cuts: 3, not_full_share_min: 0.4, tolerance: 1e-09}
- C11: FAIL; measure (0.4448, -0.152); threshold (0.6081, 0)
- C12: OK; measure (0.04308, 3.613); threshold (0.5, 40)
- C13: OK; measure (1.653, 0.4836); threshold 0
- C14: OK; measure 0.2517; threshold 0.04
- C15: OK; measure not applicable (hedged); threshold None
- C16: FAIL; measure None; threshold 0.6
- C2: OK; measure 1.216; threshold 0.5
- C3: OK; measure 2.71; threshold 2
- C4: OK; measure 1.162; threshold 0
- C10: OK; measure 0.004199; threshold 0.05

### R0135 (p-levier-accelere {fenetre_long: 50, h_bas: 0.84})
- C1: FAIL; measure 5.165e-09; threshold 0.95
- C5: OK; measure {2020: 2.135, 2021: 2.936, 2022: -0.9516, 2023: 2.651, 2024: 2.261, 2025: 0.2787}; threshold {sharpe_min: -1, positives_min: 4}
- C6: FAIL; measure 0.2039; threshold 0.2
- C7: FAIL; measure None; threshold {min_neighbors_share: 0.75, ratio: 0.6, min_neighbor_sharpe: 0.5}
- C8: FAIL; measure (1.974, 0.1539); threshold (2, 0.3)
- C9: OK; measure 2.498e-16; threshold {random_cuts: 20, fixed_cuts: 3, not_full_share_min: 0.4, tolerance: 1e-09}
- C11: FAIL; measure (0.5532, -0.09983); threshold (0.6818, 0)
- C12: OK; measure (0.04686, 3.105); threshold (0.5, 40)
- C13: OK; measure (1.827, 0.7976); threshold 0
- C14: OK; measure 0.2228; threshold 0.04
- C15: OK; measure not applicable (hedged); threshold None
- C16: FAIL; measure None; threshold 0.6
- C2: OK; measure 1.364; threshold 0.5
- C3: OK; measure 2.799; threshold 2
- C4: OK; measure 1.297; threshold 0
- C10: OK; measure 0.003599; threshold 0.05

### R0136 (p-levier-accelere {fenetre_long: 80, h_bas: 0.3})
- C1: FAIL; measure 2.032e-12; threshold 0.95
- C5: OK; measure {2020: 1.976, 2021: 2.276, 2022: -0.737, 2023: 1.688, 2024: 0.683, 2025: -0.3499}; threshold {sharpe_min: -1, positives_min: 4}
- C6: FAIL; measure 0.399; threshold 0.2
- C7: FAIL; measure None; threshold {min_neighbors_share: 0.75, ratio: 0.6, min_neighbor_sharpe: 0.5}
- C8: FAIL; measure (0.2261, 0.3514); threshold (2, 0.3)
- C9: OK; measure 1.388e-16; threshold {random_cuts: 20, fixed_cuts: 3, not_full_share_min: 0.4, tolerance: 1e-09}
- C11: FAIL; measure (0.136, -0.4083); threshold (0.5, 0)
- C12: OK; measure (0.04156, 4.621); threshold (0.5, 40)
- C13: OK; measure (1.392, 0.06276); threshold 0
- C14: OK; measure 0.2633; threshold 0.04
- C15: OK; measure not applicable (hedged); threshold None
- C16: FAIL; measure None; threshold 0.6
- C2: OK; measure 0.915; threshold 0.5
- C3: OK; measure 2.34; threshold 2
- C4: OK; measure 0.8753; threshold 0
- C10: OK; measure 0.009598; threshold 0.05

### R0137 (p-levier-accelere {fenetre_long: 80, h_bas: 0.39})
- C1: FAIL; measure 4.385e-12; threshold 0.95
- C5: OK; measure {2020: 2.005, 2021: 2.289, 2022: -0.8176, 2023: 1.76, 2024: 0.6526, 2025: -0.2097}; threshold {sharpe_min: -1, positives_min: 4}
- C6: FAIL; measure 0.3609; threshold 0.2
- C7: OK; measure 1; threshold {min_neighbors_share: 0.75, ratio: 0.6, min_neighbor_sharpe: 0.5}
- C8: FAIL; measure (0.4052, 0.3181); threshold (2, 0.3)
- C9: OK; measure 1.388e-16; threshold {random_cuts: 20, fixed_cuts: 3, not_full_share_min: 0.4, tolerance: 1e-09}
- C11: FAIL; measure (0.174, -0.3902); threshold (0.5, 0)
- C12: OK; measure (0.04087, 4.216); threshold (0.5, 40)
- C13: OK; measure (1.424, 0.08522); threshold 0
- C14: OK; measure 0.2538; threshold 0.04
- C15: OK; measure not applicable (hedged); threshold None
- C16: FAIL; measure None; threshold 0.6
- C2: OK; measure 0.9518; threshold 0.5
- C3: OK; measure 2.36; threshold 2
- C4: OK; measure 0.911; threshold 0
- C10: OK; measure 0.008798; threshold 0.05

### R0138 (p-levier-accelere {fenetre_long: 80, h_bas: 0.5})
- C1: FAIL; measure 2.069e-11; threshold 0.95
- C5: OK; measure {2020: 2.042, 2021: 2.367, 2022: -0.8595, 2023: 1.784, 2024: 0.8611, 2025: -0.121}; threshold {sharpe_min: -1, positives_min: 4}
- C6: FAIL; measure 0.318; threshold 0.2
- C7: OK; measure 1; threshold {min_neighbors_share: 0.75, ratio: 0.6, min_neighbor_sharpe: 0.5}
- C8: FAIL; measure (0.7979, 0.2734); threshold (2, 0.3)
- C9: OK; measure 1.388e-16; threshold {random_cuts: 20, fixed_cuts: 3, not_full_share_min: 0.4, tolerance: 1e-09}
- C11: FAIL; measure (0.2576, -0.3066); threshold (0.5148, 0)
- C12: OK; measure (0.04264, 3.803); threshold (0.5, 40)
- C13: OK; measure (1.491, 0.1687); threshold 0
- C14: OK; measure 0.2472; threshold 0.04
- C15: OK; measure not applicable (hedged); threshold None
- C16: FAIL; measure None; threshold 0.6
- C2: OK; measure 1.03; threshold 0.5
- C3: OK; measure 2.445; threshold 2
- C4: OK; measure 0.9837; threshold 0
- C10: OK; measure 0.008398; threshold 0.05

### R0139 (p-levier-accelere {fenetre_long: 80, h_bas: 0.65})
- C1: FAIL; measure 4.601e-10; threshold 0.95
- C5: OK; measure {2020: 2.052, 2021: 2.771, 2022: -0.6476, 2023: 1.816, 2024: 0.9713, 2025: -0.2357}; threshold {sharpe_min: -1, positives_min: 4}
- C6: FAIL; measure 0.2585; threshold 0.2
- C7: OK; measure 1; threshold {min_neighbors_share: 0.75, ratio: 0.6, min_neighbor_sharpe: 0.5}
- C8: FAIL; measure (1.521, 0.2196); threshold (2, 0.3)
- C9: OK; measure 1.388e-16; threshold {random_cuts: 20, fixed_cuts: 3, not_full_share_min: 0.4, tolerance: 1e-09}
- C11: FAIL; measure (0.424, -0.1818); threshold (0.6038, 0)
- C12: OK; measure (0.04185, 3.334); threshold (0.5, 40)
- C13: OK; measure (1.739, 0.1436); threshold 0
- C14: OK; measure 0.2516; threshold 0.04
- C15: OK; measure not applicable (hedged); threshold None
- C16: FAIL; measure None; threshold 0.6
- C2: OK; measure 1.208; threshold 0.5
- C3: OK; measure 2.694; threshold 2
- C4: OK; measure 1.155; threshold 0
- C10: OK; measure 0.005199; threshold 0.05

### R0140 (p-levier-accelere {fenetre_long: 80, h_bas: 0.84})
- C1: FAIL; measure 4.268e-09; threshold 0.95
- C5: OK; measure {2020: 2.135, 2021: 2.953, 2022: -0.6679, 2023: 2.285, 2024: 1.953, 2025: -0.2008}; threshold {sharpe_min: -1, positives_min: 4}
- C6: FAIL; measure 0.2039; threshold 0.2
- C7: FAIL; measure None; threshold {min_neighbors_share: 0.75, ratio: 0.6, min_neighbor_sharpe: 0.5}
- C8: FAIL; measure (1.935, 0.1554); threshold (2, 0.3)
- C9: OK; measure 2.22e-16; threshold {random_cuts: 20, fixed_cuts: 3, not_full_share_min: 0.4, tolerance: 1e-09}
- C11: FAIL; measure (0.5421, -0.1198); threshold (0.6758, 0)
- C12: OK; measure (0.04692, 3.077); threshold (0.5, 40)
- C13: OK; measure (1.865, 0.4716); threshold 0
- C14: OK; measure 0.2238; threshold 0.04
- C15: OK; measure not applicable (hedged); threshold None
- C16: FAIL; measure None; threshold 0.6
- C2: OK; measure 1.352; threshold 0.5
- C3: OK; measure 2.793; threshold 2
- C4: OK; measure 1.285; threshold 0
- C10: OK; measure 0.003599; threshold 0.05

### R0141 (p-levier-accelere {fenetre_long: 126, h_bas: 0.3})
- C1: FAIL; measure 4.292e-12; threshold 0.95
- C5: OK; measure {2020: 1.983, 2021: 2.3, 2022: -0.6051, 2023: 1.542, 2024: 0.8789, 2025: -0.2531}; threshold {sharpe_min: -1, positives_min: 4}
- C6: FAIL; measure 0.3806; threshold 0.2
- C7: FAIL; measure None; threshold {min_neighbors_share: 0.75, ratio: 0.6, min_neighbor_sharpe: 0.5}
- C8: FAIL; measure (0.4192, 0.3532); threshold (2, 0.3)
- C9: OK; measure 1.527e-16; threshold {random_cuts: 20, fixed_cuts: 3, not_full_share_min: 0.4, tolerance: 1e-09}
- C11: FAIL; measure (0.1809, -0.3714); threshold (0.5, 0)
- C12: OK; measure (0.03746, 4.014); threshold (0.5, 40)
- C13: OK; measure (1.456, 0.08105); threshold 0
- C14: OK; measure 0.2784; threshold 0.04
- C15: OK; measure not applicable (hedged); threshold None
- C16: FAIL; measure None; threshold 0.6
- C2: OK; measure 0.9543; threshold 0.5
- C3: OK; measure 2.419; threshold 2
- C4: OK; measure 0.917; threshold 0
- C10: OK; measure 0.007399; threshold 0.05

### R0142 (p-levier-accelere {fenetre_long: 126, h_bas: 0.39})
- C1: FAIL; measure 1.053e-11; threshold 0.95
- C5: OK; measure {2020: 1.97, 2021: 2.322, 2022: -0.6007, 2023: 1.692, 2024: 1.098, 2025: -0.3232}; threshold {sharpe_min: -1, positives_min: 4}
- C6: FAIL; measure 0.3595; threshold 0.2
- C7: FAIL; measure None; threshold {min_neighbors_share: 0.75, ratio: 0.6, min_neighbor_sharpe: 0.5}
- C8: FAIL; measure (0.6587, 0.3155); threshold (2, 0.3)
- C9: OK; measure 1.457e-16; threshold {random_cuts: 20, fixed_cuts: 3, not_full_share_min: 0.4, tolerance: 1e-09}
- C11: FAIL; measure (0.2272, -0.3247); threshold (0.5004, 0)
- C12: OK; measure (0.03863, 3.656); threshold (0.5, 40)
- C13: OK; measure (1.491, 0.1259); threshold 0
- C14: OK; measure 0.2684; threshold 0.04
- C15: OK; measure not applicable (hedged); threshold None
- C16: FAIL; measure None; threshold 0.6
- C2: OK; measure 1.001; threshold 0.5
- C3: OK; measure 2.472; threshold 2
- C4: OK; measure 0.9607; threshold 0
- C10: OK; measure 0.007199; threshold 0.05

### R0143 (p-levier-accelere {fenetre_long: 126, h_bas: 0.5})
- C1: FAIL; measure 2.74e-11; threshold 0.95
- C5: OK; measure {2020: 2.009, 2021: 2.442, 2022: -0.7755, 2023: 1.682, 2024: 1.209, 2025: -0.2455}; threshold {sharpe_min: -1, positives_min: 4}
- C6: FAIL; measure 0.3106; threshold 0.2
- C7: FAIL; measure None; threshold {min_neighbors_share: 0.75, ratio: 0.6, min_neighbor_sharpe: 0.5}
- C8: FAIL; measure (0.9021, 0.2739); threshold (2, 0.3)
- C9: OK; measure 1.249e-16; threshold {random_cuts: 20, fixed_cuts: 3, not_full_share_min: 0.4, tolerance: 1e-09}
- C11: FAIL; measure (0.2708, -0.2957); threshold (0.5258, 0)
- C12: OK; measure (0.04069, 3.324); threshold (0.5, 40)
- C13: OK; measure (1.512, 0.2105); threshold 0
- C14: OK; measure 0.2527; threshold 0.04
- C15: OK; measure not applicable (hedged); threshold None
- C16: FAIL; measure None; threshold 0.6
- C2: OK; measure 1.052; threshold 0.5
- C3: OK; measure 2.504; threshold 2
- C4: OK; measure 1.007; threshold 0
- C10: OK; measure 0.007598; threshold 0.05

### R0144 (p-levier-accelere {fenetre_long: 126, h_bas: 0.65})
- C1: FAIL; measure 3.208e-10; threshold 0.95
- C5: OK; measure {2020: 2.09, 2021: 2.672, 2022: -0.7041, 2023: 1.47, 2024: 1.5, 2025: -0.1335}; threshold {sharpe_min: -1, positives_min: 4}
- C6: FAIL; measure 0.2608; threshold 0.2
- C7: FAIL; measure None; threshold {min_neighbors_share: 0.75, ratio: 0.6, min_neighbor_sharpe: 0.5}
- C8: FAIL; measure (1.481, 0.2204); threshold (2, 0.3)
- C9: OK; measure 1.041e-16; threshold {random_cuts: 20, fixed_cuts: 3, not_full_share_min: 0.4, tolerance: 1e-09}
- C11: FAIL; measure (0.4084, -0.1863); threshold (0.5972, 0)
- C12: OK; measure (0.04102, 2.982); threshold (0.5, 40)
- C13: OK; measure (1.689, 0.2619); threshold 0
- C14: OK; measure 0.2478; threshold 0.04
- C15: OK; measure not applicable (hedged); threshold None
- C16: FAIL; measure None; threshold 0.6
- C2: OK; measure 1.194; threshold 0.5
- C3: OK; measure 2.696; threshold 2
- C4: OK; measure 1.143; threshold 0
- C10: OK; measure 0.004799; threshold 0.05

### R0145 (p-levier-accelere {fenetre_long: 126, h_bas: 0.84})
- C1: FAIL; measure 3.733e-09; threshold 0.95
- C5: OK; measure {2020: 2.137, 2021: 2.906, 2022: -0.7049, 2023: 1.981, 2024: 2.467, 2025: -0.06649}; threshold {sharpe_min: -1, positives_min: 4}
- C6: FAIL; measure 0.2039; threshold 0.2
- C7: FAIL; measure None; threshold {min_neighbors_share: 0.75, ratio: 0.6, min_neighbor_sharpe: 0.5}
- C8: FAIL; measure (1.93, 0.1545); threshold (2, 0.3)
- C9: OK; measure 1.249e-16; threshold {random_cuts: 20, fixed_cuts: 3, not_full_share_min: 0.4, tolerance: 1e-09}
- C11: FAIL; measure (0.5335, -0.1118); threshold (0.6746, 0)
- C12: OK; measure (0.04696, 2.903); threshold (0.5, 40)
- C13: OK; measure (1.842, 0.5773); threshold 0
- C14: OK; measure 0.2211; threshold 0.04
- C15: OK; measure not applicable (hedged); threshold None
- C16: FAIL; measure None; threshold 0.6
- C2: OK; measure 1.349; threshold 0.5
- C3: OK; measure 2.795; threshold 2
- C4: OK; measure 1.282; threshold 0
- C10: OK; measure 0.003399; threshold 0.05

### R0146 (r-cible-vol-perp {L_vol_jours: 10, sigma_cible: 0.06})
- C1: FAIL; measure 0.0004322; threshold 0.95
- C5: FAIL; measure {2020: 4.258, 2021: 7.03, 2022: -2.162, 2023: 2.163, 2024: 3.287, 2025: 0.4334}; threshold {sharpe_min: -1, positives_min: 4}
- C6: OK; measure 0.0795; threshold 0.2
- C7: FAIL; measure None; threshold {min_neighbors_share: 0.75, ratio: 0.6, min_neighbor_sharpe: 0.5}
- C8: OK; measure (4.741, 0.04467); threshold (2, 0.3)
- C9: OK; measure 2.082e-16; threshold {random_cuts: 20, fixed_cuts: 3, not_full_share_min: 0.4, tolerance: 1e-09}
- C11: OK; measure (1.796, 1.337); threshold (1.171, 0)
- C12: OK; measure (0.07787, 2.147); threshold (0.5, 40)
- C13: OK; measure (3.304, 1.262); threshold 0
- C14: OK; measure 0.09596; threshold 0.04
- C15: OK; measure not applicable (hedged); threshold None
- C16: FAIL; measure None; threshold 0.6
- C2: OK; measure 2.342; threshold 0.5
- C3: OK; measure 3.877; threshold 2
- C4: OK; measure 2.132; threshold 0
- C10: OK; measure 0.0003999; threshold 0.05

### R0147 (r-cible-vol-perp {L_vol_jours: 10, sigma_cible: 0.08})
- C1: FAIL; measure 9.886e-06; threshold 0.95
- C5: FAIL; measure {2020: 3.868, 2021: 6.212, 2022: -2.084, 2023: 2.003, 2024: 2.759, 2025: 0.2804}; threshold {sharpe_min: -1, positives_min: 4}
- C6: OK; measure 0.1053; threshold 0.2
- C7: FAIL; measure None; threshold {min_neighbors_share: 0.75, ratio: 0.6, min_neighbor_sharpe: 0.5}
- C8: OK; measure (4.21, 0.05923); threshold (2, 0.3)
- C9: OK; measure 1.527e-16; threshold {random_cuts: 20, fixed_cuts: 3, not_full_share_min: 0.4, tolerance: 1e-09}
- C11: OK; measure (1.404, 0.9464); threshold (0.9824, 0)
- C12: OK; measure (0.073, 2.269); threshold (0.5, 40)
- C13: OK; measure (2.81, 1.048); threshold 0
- C14: OK; measure 0.1056; threshold 0.04
- C15: OK; measure not applicable (hedged); threshold None
- C16: FAIL; measure None; threshold 0.6
- C2: OK; measure 1.965; threshold 0.5
- C3: OK; measure 3.531; threshold 2
- C4: OK; measure 1.804; threshold 0
- C10: OK; measure 0.0009998; threshold 0.05

### R0148 (r-cible-vol-perp {L_vol_jours: 10, sigma_cible: 0.11})
- C1: FAIL; measure 1.91e-07; threshold 0.95
- C5: FAIL; measure {2020: 3.336, 2021: 5.41, 2022: -1.815, 2023: 1.858, 2024: 2.372, 2025: 0.1818}; threshold {sharpe_min: -1, positives_min: 4}
- C6: OK; measure 0.1349; threshold 0.2
- C7: FAIL; measure None; threshold {min_neighbors_share: 0.75, ratio: 0.6, min_neighbor_sharpe: 0.5}
- C8: OK; measure (3.576, 0.08188); threshold (2, 0.3)
- C9: OK; measure 2.082e-16; threshold {random_cuts: 20, fixed_cuts: 3, not_full_share_min: 0.4, tolerance: 1e-09}
- C11: OK; measure (1.078, 0.619); threshold (0.8231, 0)
- C12: OK; measure (0.06662, 2.49); threshold (0.5, 40)
- C13: OK; measure (2.368, 0.8864); threshold 0
- C14: OK; measure 0.1226; threshold 0.04
- C15: OK; measure not applicable (hedged); threshold None
- C16: FAIL; measure None; threshold 0.6
- C2: OK; measure 1.646; threshold 0.5
- C3: OK; measure 3.22; threshold 2
- C4: OK; measure 1.526; threshold 0
- C10: OK; measure 0.0014; threshold 0.05

### R0149 (r-cible-vol-perp {L_vol_jours: 10, sigma_cible: 0.15})
- C1: FAIL; measure 8.595e-09; threshold 0.95
- C5: FAIL; measure {2020: 2.979, 2021: 4.516, 2022: -1.622, 2023: 1.851, 2024: 2.072, 2025: 0.1469}; threshold {sharpe_min: -1, positives_min: 4}
- C6: OK; measure 0.1717; threshold 0.2
- C7: FAIL; measure None; threshold {min_neighbors_share: 0.75, ratio: 0.6, min_neighbor_sharpe: 0.5}
- C8: OK; measure (2.909, 0.1135); threshold (2, 0.3)
- C9: OK; measure 2.498e-16; threshold {random_cuts: 20, fixed_cuts: 3, not_full_share_min: 0.4, tolerance: 1e-09}
- C11: OK; measure (0.8353, 0.3722); threshold (0.7135, 0)
- C12: OK; measure (0.05939, 2.716); threshold (0.5, 40)
- C13: OK; measure (2.036, 0.7851); threshold 0
- C14: OK; measure 0.1468; threshold 0.04
- C15: OK; measure not applicable (hedged); threshold None
- C16: FAIL; measure None; threshold 0.6
- C2: OK; measure 1.427; threshold 0.5
- C3: OK; measure 2.957; threshold 2
- C4: OK; measure 1.335; threshold 0
- C10: OK; measure 0.0022; threshold 0.05

### R0150 (r-cible-vol-perp {L_vol_jours: 10, sigma_cible: 0.22})
- C1: FAIL; measure 2.353e-10; threshold 0.95
- C5: FAIL; measure {2020: 2.717, 2021: 3.83, 2022: -1.491, 2023: 1.747, 2024: 1.754, 2025: 0.06422}; threshold {sharpe_min: -1, positives_min: 4}
- C6: FAIL; measure 0.2368; threshold 0.2
- C7: FAIL; measure None; threshold {min_neighbors_share: 0.75, ratio: 0.6, min_neighbor_sharpe: 0.5}
- C8: FAIL; measure (1.973, 0.1697); threshold (2, 0.3)
- C9: OK; measure 3.331e-16; threshold {random_cuts: 20, fixed_cuts: 3, not_full_share_min: 0.4, tolerance: 1e-09}
- C11: FAIL; measure (0.5958, 0.1268); threshold (0.6073, 0)
- C12: OK; measure (0.05099, 3.038); threshold (0.5, 40)
- C13: OK; measure (1.772, 0.6289); threshold 0
- C14: OK; measure 0.1838; threshold 0.04
- C15: OK; measure not applicable (hedged); threshold None
- C16: FAIL; measure None; threshold 0.6
- C2: OK; measure 1.215; threshold 0.5
- C3: OK; measure 2.634; threshold 2
- C4: OK; measure 1.149; threshold 0
- C10: OK; measure 0.004399; threshold 0.05

### R0151 (r-cible-vol-perp {L_vol_jours: 20, sigma_cible: 0.06})
- C1: FAIL; measure 0.0003263; threshold 0.95
- C5: FAIL; measure {2020: 3.807, 2021: 6.996, 2022: -2.142, 2023: 2.23, 2024: 3.327, 2025: 0.4368}; threshold {sharpe_min: -1, positives_min: 4}
- C6: OK; measure 0.07567; threshold 0.2
- C7: FAIL; measure None; threshold {min_neighbors_share: 0.75, ratio: 0.6, min_neighbor_sharpe: 0.5}
- C8: OK; measure (4.418, 0.0449); threshold (2, 0.3)
- C9: OK; measure 3.469e-16; threshold {random_cuts: 20, fixed_cuts: 3, not_full_share_min: 0.4, tolerance: 1e-09}
- C11: OK; measure (1.731, 1.268); threshold (1.138, 0)
- C12: OK; measure (0.07805, 2); threshold (0.5, 40)
- C13: OK; measure (3.199, 1.199); threshold 0
- C14: OK; measure 0.0922; threshold 0.04
- C15: OK; measure not applicable (hedged); threshold None
- C16: FAIL; measure None; threshold 0.6
- C2: OK; measure 2.276; threshold 0.5
- C3: OK; measure 3.729; threshold 2
- C4: OK; measure 2.073; threshold 0
- C10: OK; measure 0.0007998; threshold 0.05

### R0152 (r-cible-vol-perp {L_vol_jours: 20, sigma_cible: 0.08})
- C1: FAIL; measure 1.667e-05; threshold 0.95
- C5: FAIL; measure {2020: 3.577, 2021: 6.479, 2022: -1.936, 2023: 2.082, 2024: 2.809, 2025: 0.3524}; threshold {sharpe_min: -1, positives_min: 4}
- C6: OK; measure 0.09269; threshold 0.2
- C7: OK; measure 1; threshold {min_neighbors_share: 0.75, ratio: 0.6, min_neighbor_sharpe: 0.5}
- C8: OK; measure (4.234, 0.05858); threshold (2, 0.3)
- C9: OK; measure 1.665e-16; threshold {random_cuts: 20, fixed_cuts: 3, not_full_share_min: 0.4, tolerance: 1e-09}
- C11: OK; measure (1.437, 0.9677); threshold (0.9938, 0)
- C12: OK; measure (0.06958, 2.023); threshold (0.5, 40)
- C13: OK; measure (2.882, 1.005); threshold 0
- C14: OK; measure 0.1046; threshold 0.04
- C15: OK; measure not applicable (hedged); threshold None
- C16: FAIL; measure None; threshold 0.6
- C2: OK; measure 1.988; threshold 0.5
- C3: OK; measure 3.538; threshold 2
- C4: OK; measure 1.834; threshold 0
- C10: OK; measure 0.0009998; threshold 0.05

### R0153 (r-cible-vol-perp {L_vol_jours: 20, sigma_cible: 0.11})
- C1: FAIL; measure 3.3e-07; threshold 0.95
- C5: FAIL; measure {2020: 3.175, 2021: 5.442, 2022: -1.663, 2023: 1.846, 2024: 2.546, 2025: 0.2978}; threshold {sharpe_min: -1, positives_min: 4}
- C6: OK; measure 0.1221; threshold 0.2
- C7: OK; measure 1; threshold {min_neighbors_share: 0.75, ratio: 0.6, min_neighbor_sharpe: 0.5}
- C8: OK; measure (3.639, 0.08166); threshold (2, 0.3)
- C9: OK; measure 3.608e-16; threshold {random_cuts: 20, fixed_cuts: 3, not_full_share_min: 0.4, tolerance: 1e-09}
- C11: OK; measure (1.106, 0.6384); threshold (0.8329, 0)
- C12: OK; measure (0.06112, 2.09); threshold (0.5, 40)
- C13: OK; measure (2.415, 0.8517); threshold 0
- C14: OK; measure 0.1217; threshold 0.04
- C15: OK; measure not applicable (hedged); threshold None
- C16: FAIL; measure None; threshold 0.6
- C2: OK; measure 1.666; threshold 0.5
- C3: OK; measure 3.228; threshold 2
- C4: OK; measure 1.555; threshold 0
- C10: OK; measure 0.0014; threshold 0.05

### R0154 (r-cible-vol-perp {L_vol_jours: 20, sigma_cible: 0.15})
- C1: FAIL; measure 1.52e-08; threshold 0.95
- C5: FAIL; measure {2020: 2.93, 2021: 4.867, 2022: -1.585, 2023: 1.73, 2024: 2.256, 2025: 0.2052}; threshold {sharpe_min: -1, positives_min: 4}
- C6: OK; measure 0.1614; threshold 0.2
- C7: OK; measure 1; threshold {min_neighbors_share: 0.75, ratio: 0.6, min_neighbor_sharpe: 0.5}
- C8: OK; measure (2.954, 0.1115); threshold (2, 0.3)
- C9: OK; measure 1.388e-16; threshold {random_cuts: 20, fixed_cuts: 3, not_full_share_min: 0.4, tolerance: 1e-09}
- C11: OK; measure (0.878, 0.407); threshold (0.7277, 0)
- C12: OK; measure (0.05376, 2.193); threshold (0.5, 40)
- C13: OK; measure (2.146, 0.725); threshold 0
- C14: OK; measure 0.1451; threshold 0.04
- C15: OK; measure not applicable (hedged); threshold None
- C16: FAIL; measure None; threshold 0.6
- C2: OK; measure 1.455; threshold 0.5
- C3: OK; measure 2.965; threshold 2
- C4: OK; measure 1.372; threshold 0
- C10: OK; measure 0.0018; threshold 0.05

### R0155 (r-cible-vol-perp {L_vol_jours: 20, sigma_cible: 0.22})
- C1: FAIL; measure 1.813e-10; threshold 0.95
- C5: FAIL; measure {2020: 2.563, 2021: 4.124, 2022: -1.493, 2023: 1.653, 2024: 1.951, 2025: 0.1426}; threshold {sharpe_min: -1, positives_min: 4}
- C6: FAIL; measure 0.2382; threshold 0.2
- C7: FAIL; measure None; threshold {min_neighbors_share: 0.75, ratio: 0.6, min_neighbor_sharpe: 0.5}
- C8: FAIL; measure (1.699, 0.1675); threshold (2, 0.3)
- C9: OK; measure 1.943e-16; threshold {random_cuts: 20, fixed_cuts: 3, not_full_share_min: 0.4, tolerance: 1e-09}
- C11: FAIL; measure (0.5814, 0.1089); threshold (0.5895, 0)
- C12: OK; measure (0.04622, 2.302); threshold (0.5, 40)
- C13: OK; measure (1.778, 0.5525); threshold 0
- C14: OK; measure 0.1738; threshold 0.04
- C15: OK; measure not applicable (hedged); threshold None
- C16: FAIL; measure None; threshold 0.6
- C2: OK; measure 1.179; threshold 0.5
- C3: OK; measure 2.555; threshold 2
- C4: OK; measure 1.121; threshold 0
- C10: OK; measure 0.006199; threshold 0.05

### R0156 (r-cible-vol-perp {L_vol_jours: 40, sigma_cible: 0.06})
- C1: FAIL; measure 0.0008761; threshold 0.95
- C5: FAIL; measure {2020: 3.822, 2021: 6.787, 2022: -2.09, 2023: 2.402, 2024: 3.647, 2025: 0.3536}; threshold {sharpe_min: -1, positives_min: 4}
- C6: OK; measure 0.07522; threshold 0.2
- C7: FAIL; measure None; threshold {min_neighbors_share: 0.75, ratio: 0.6, min_neighbor_sharpe: 0.5}
- C8: OK; measure (4.801, 0.04533); threshold (2, 0.3)
- C9: OK; measure 1.11e-16; threshold {random_cuts: 20, fixed_cuts: 3, not_full_share_min: 0.4, tolerance: 1e-09}
- C11: OK; measure (1.835, 1.366); threshold (1.198, 0)
- C12: OK; measure (0.07421, 1.968); threshold (0.5, 40)
- C13: OK; measure (3.186, 1.42); threshold 0
- C14: OK; measure 0.09686; threshold 0.04
- C15: OK; measure not applicable (hedged); threshold None
- C16: FAIL; measure None; threshold 0.6
- C2: OK; measure 2.396; threshold 0.5
- C3: OK; measure 3.904; threshold 2
- C4: OK; measure 2.195; threshold 0
- C10: OK; measure 0.0005999; threshold 0.05

### R0157 (r-cible-vol-perp {L_vol_jours: 40, sigma_cible: 0.08})
- C1: FAIL; measure 2.04e-05; threshold 0.95
- C5: FAIL; measure {2020: 3.268, 2021: 6.405, 2022: -1.866, 2023: 2.283, 2024: 3.078, 2025: 0.219}; threshold {sharpe_min: -1, positives_min: 4}
- C6: OK; measure 0.08862; threshold 0.2
- C7: OK; measure 1; threshold {min_neighbors_share: 0.75, ratio: 0.6, min_neighbor_sharpe: 0.5}
- C8: OK; measure (4.232, 0.05787); threshold (2, 0.3)
- C9: OK; measure 1.249e-16; threshold {random_cuts: 20, fixed_cuts: 3, not_full_share_min: 0.4, tolerance: 1e-09}
- C11: OK; measure (1.44, 0.9683); threshold (1.002, 0)
- C12: OK; measure (0.06871, 1.937); threshold (0.5, 40)
- C13: OK; measure (2.798, 1.098); threshold 0
- C14: OK; measure 0.1029; threshold 0.04
- C15: OK; measure not applicable (hedged); threshold None
- C16: FAIL; measure None; threshold 0.6
- C2: OK; measure 2.004; threshold 0.5
- C3: OK; measure 3.54; threshold 2
- C4: OK; measure 1.851; threshold 0
- C10: OK; measure 0.0007998; threshold 0.05

### R0158 (r-cible-vol-perp {L_vol_jours: 40, sigma_cible: 0.11})
- C1: FAIL; measure 5.516e-07; threshold 0.95
- C5: FAIL; measure {2020: 3.01, 2021: 5.33, 2022: -1.686, 2023: 2.148, 2024: 2.641, 2025: 0.2215}; threshold {sharpe_min: -1, positives_min: 4}
- C6: OK; measure 0.1159; threshold 0.2
- C7: OK; measure 1; threshold {min_neighbors_share: 0.75, ratio: 0.6, min_neighbor_sharpe: 0.5}
- C8: OK; measure (3.834, 0.08059); threshold (2, 0.3)
- C9: OK; measure 1.527e-16; threshold {random_cuts: 20, fixed_cuts: 3, not_full_share_min: 0.4, tolerance: 1e-09}
- C11: OK; measure (1.132, 0.6721); threshold (0.8488, 0)
- C12: OK; measure (0.0591, 1.939); threshold (0.5, 40)
- C13: OK; measure (2.35, 0.974); threshold 0
- C14: OK; measure 0.1207; threshold 0.04
- C15: OK; measure not applicable (hedged); threshold None
- C16: FAIL; measure None; threshold 0.6
- C2: OK; measure 1.698; threshold 0.5
- C3: OK; measure 3.302; threshold 2
- C4: OK; measure 1.589; threshold 0
- C10: OK; measure 0.0012; threshold 0.05

### R0159 (r-cible-vol-perp {L_vol_jours: 40, sigma_cible: 0.15})
- C1: FAIL; measure 3.594e-08; threshold 0.95
- C5: FAIL; measure {2020: 2.791, 2021: 4.834, 2022: -1.579, 2023: 2.049, 2024: 2.386, 2025: 0.1516}; threshold {sharpe_min: -1, positives_min: 4}
- C6: OK; measure 0.1607; threshold 0.2
- C7: OK; measure 1; threshold {min_neighbors_share: 0.75, ratio: 0.6, min_neighbor_sharpe: 0.5}
- C8: OK; measure (3.148, 0.1105); threshold (2, 0.3)
- C9: OK; measure 8.327e-17; threshold {random_cuts: 20, fixed_cuts: 3, not_full_share_min: 0.4, tolerance: 1e-09}
- C11: OK; measure (0.9303, 0.465); threshold (0.749, 0)
- C12: OK; measure (0.05048, 1.977); threshold (0.5, 40)
- C13: OK; measure (2.114, 0.827); threshold 0
- C14: OK; measure 0.1467; threshold 0.04
- C15: OK; measure not applicable (hedged); threshold None
- C16: FAIL; measure None; threshold 0.6
- C2: OK; measure 1.498; threshold 0.5
- C3: OK; measure 3.039; threshold 2
- C4: OK; measure 1.417; threshold 0
- C10: OK; measure 0.0016; threshold 0.05

### R0160 (r-cible-vol-perp {L_vol_jours: 40, sigma_cible: 0.22})
- C1: FAIL; measure 1.405e-09; threshold 0.95
- C5: FAIL; measure {2020: 2.533, 2021: 4.08, 2022: -1.43, 2023: 1.951, 2024: 2.135, 2025: 0.1722}; threshold {sharpe_min: -1, positives_min: 4}
- C6: FAIL; measure 0.2327; threshold 0.2
- C7: FAIL; measure None; threshold {min_neighbors_share: 0.75, ratio: 0.6, min_neighbor_sharpe: 0.5}
- C8: OK; measure (2.355, 0.1642); threshold (2, 0.3)
- C9: OK; measure 1.943e-16; threshold {random_cuts: 20, fixed_cuts: 3, not_full_share_min: 0.4, tolerance: 1e-09}
- C11: OK; measure (0.7056, 0.2377); threshold (0.6484, 0)
- C12: OK; measure (0.0394, 1.966); threshold (0.5, 40)
- C13: OK; measure (1.839, 0.7178); threshold 0
- C14: OK; measure 0.1876; threshold 0.04
- C15: OK; measure not applicable (hedged); threshold None
- C16: FAIL; measure None; threshold 0.6
- C2: OK; measure 1.297; threshold 0.5
- C3: OK; measure 2.795; threshold 2
- C4: OK; measure 1.243; threshold 0
- C10: OK; measure 0.003399; threshold 0.05

### R0161 (r-cible-vol-perp {L_vol_jours: 80, sigma_cible: 0.06})
- C1: FAIL; measure 0.001263; threshold 0.95
- C5: FAIL; measure {2020: 3.899, 2021: 6.382, 2022: -2.06, 2023: 2.644, 2024: 3.524, 2025: 0.3109}; threshold {sharpe_min: -1, positives_min: 4}
- C6: OK; measure 0.07128; threshold 0.2
- C7: FAIL; measure None; threshold {min_neighbors_share: 0.75, ratio: 0.6, min_neighbor_sharpe: 0.5}
- C8: OK; measure (4.853, 0.04475); threshold (2, 0.3)
- C9: OK; measure 1.804e-16; threshold {random_cuts: 20, fixed_cuts: 3, not_full_share_min: 0.4, tolerance: 1e-09}
- C11: OK; measure (1.893, 1.429); threshold (1.224, 0)
- C12: OK; measure (0.07356, 1.921); threshold (0.5, 40)
- C13: OK; measure (3.205, 1.483); threshold 0
- C14: OK; measure 0.09611; threshold 0.04
- C15: OK; measure not applicable (hedged); threshold None
- C16: FAIL; measure None; threshold 0.6
- C2: OK; measure 2.448; threshold 0.5
- C3: OK; measure 3.912; threshold 2
- C4: OK; measure 2.244; threshold 0
- C10: OK; measure 0.0005999; threshold 0.05

### R0162 (r-cible-vol-perp {L_vol_jours: 80, sigma_cible: 0.08})
- C1: FAIL; measure 9.162e-05; threshold 0.95
- C5: FAIL; measure {2020: 3.326, 2021: 6.152, 2022: -1.954, 2023: 2.448, 2024: 3.057, 2025: 0.246}; threshold {sharpe_min: -1, positives_min: 4}
- C6: OK; measure 0.08062; threshold 0.2
- C7: OK; measure 1; threshold {min_neighbors_share: 0.75, ratio: 0.6, min_neighbor_sharpe: 0.5}
- C8: OK; measure (4.771, 0.05757); threshold (2, 0.3)
- C9: OK; measure 1.943e-16; threshold {random_cuts: 20, fixed_cuts: 3, not_full_share_min: 0.4, tolerance: 1e-09}
- C11: OK; measure (1.588, 1.112); threshold (1.074, 0)
- C12: OK; measure (0.065, 1.883); threshold (0.5, 40)
- C13: OK; measure (2.918, 1.24); threshold 0
- C14: OK; measure 0.1082; threshold 0.04
- C15: OK; measure not applicable (hedged); threshold None
- C16: FAIL; measure None; threshold 0.6
- C2: OK; measure 2.148; threshold 0.5
- C3: OK; measure 3.767; threshold 2
- C4: OK; measure 1.993; threshold 0
- C10: OK; measure 0.0005999; threshold 0.05

### R0163 (r-cible-vol-perp {L_vol_jours: 80, sigma_cible: 0.11})
- C1: FAIL; measure 1.305e-06; threshold 0.95
- C5: FAIL; measure {2020: 2.748, 2021: 5.399, 2022: -1.706, 2023: 2.202, 2024: 2.747, 2025: 0.09656}; threshold {sharpe_min: -1, positives_min: 4}
- C6: OK; measure 0.1045; threshold 0.2
- C7: OK; measure 1; threshold {min_neighbors_share: 0.75, ratio: 0.6, min_neighbor_sharpe: 0.5}
- C8: OK; measure (4.027, 0.07812); threshold (2, 0.3)
- C9: OK; measure 9.714e-17; threshold {random_cuts: 20, fixed_cuts: 3, not_full_share_min: 0.4, tolerance: 1e-09}
- C11: OK; measure (1.183, 0.7197); threshold (0.8749, 0)
- C12: OK; measure (0.05908, 1.858); threshold (0.5, 40)
- C13: OK; measure (2.384, 1.056); threshold 0
- C14: OK; measure 0.119; threshold 0.04
- C15: OK; measure not applicable (hedged); threshold None
- C16: FAIL; measure None; threshold 0.6
- C2: OK; measure 1.75; threshold 0.5
- C3: OK; measure 3.355; threshold 2
- C4: OK; measure 1.639; threshold 0
- C10: OK; measure 0.0009998; threshold 0.05

### R0164 (r-cible-vol-perp {L_vol_jours: 80, sigma_cible: 0.15})
- C1: FAIL; measure 2.703e-08; threshold 0.95
- C5: FAIL; measure {2020: 2.464, 2021: 4.77, 2022: -1.5, 2023: 1.959, 2024: 2.394, 2025: 0.1149}; threshold {sharpe_min: -1, positives_min: 4}
- C6: OK; measure 0.1487; threshold 0.2
- C7: OK; measure 1; threshold {min_neighbors_share: 0.75, ratio: 0.6, min_neighbor_sharpe: 0.5}
- C8: OK; measure (3.173, 0.108); threshold (2, 0.3)
- C9: OK; measure 1.804e-16; threshold {random_cuts: 20, fixed_cuts: 3, not_full_share_min: 0.4, tolerance: 1e-09}
- C11: OK; measure (0.8914, 0.4101); threshold (0.7361, 0)
- C12: OK; measure (0.05136, 1.843); threshold (0.5, 40)
- C13: OK; measure (2.027, 0.8911); threshold 0
- C14: OK; measure 0.1383; threshold 0.04
- C15: OK; measure not applicable (hedged); threshold None
- C16: FAIL; measure None; threshold 0.6
- C2: OK; measure 1.472; threshold 0.5
- C3: OK; measure 3.046; threshold 2
- C4: OK; measure 1.391; threshold 0
- C10: OK; measure 0.002; threshold 0.05

### R0165 (r-cible-vol-perp {L_vol_jours: 80, sigma_cible: 0.22})
- C1: FAIL; measure 9.553e-10; threshold 0.95
- C5: FAIL; measure {2020: 2.059, 2021: 4.025, 2022: -1.391, 2023: 1.858, 2024: 2.178, 2025: 0.11}; threshold {sharpe_min: -1, positives_min: 4}
- C6: FAIL; measure 0.2157; threshold 0.2
- C7: FAIL; measure None; threshold {min_neighbors_share: 0.75, ratio: 0.6, min_neighbor_sharpe: 0.5}
- C8: OK; measure (2.103, 0.162); threshold (2, 0.3)
- C9: OK; measure 1.388e-16; threshold {random_cuts: 20, fixed_cuts: 3, not_full_share_min: 0.4, tolerance: 1e-09}
- C11: OK; measure (0.6569, 0.1795); threshold (0.6236, 0)
- C12: OK; measure (0.03968, 1.771); threshold (0.5, 40)
- C13: OK; measure (1.663, 0.8036); threshold 0
- C14: OK; measure 0.1737; threshold 0.04
- C15: OK; measure not applicable (hedged); threshold None
- C16: FAIL; measure None; threshold 0.6
- C2: OK; measure 1.247; threshold 0.5
- C3: OK; measure 2.726; threshold 2
- C4: OK; measure 1.196; threshold 0
- C10: OK; measure 0.003999; threshold 0.05

### R0166 (r-cible-vol-perp {L_vol_jours: 160, sigma_cible: 0.06})
- C1: FAIL; measure 0.001438; threshold 0.95
- C5: FAIL; measure {2020: 4.216, 2021: 6.678, 2022: -2.144, 2023: 2.846, 2024: 3.302, 2025: 0.2231}; threshold {sharpe_min: -1, positives_min: 4}
- C6: OK; measure 0.06912; threshold 0.2
- C7: FAIL; measure None; threshold {min_neighbors_share: 0.75, ratio: 0.6, min_neighbor_sharpe: 0.5}
- C8: OK; measure (4.69, 0.04098); threshold (2, 0.3)
- C9: OK; measure 1.11e-16; threshold {random_cuts: 20, fixed_cuts: 3, not_full_share_min: 0.4, tolerance: 1e-09}
- C11: OK; measure (1.907, 1.439); threshold (1.239, 0)
- C12: OK; measure (0.07813, 1.926); threshold (0.5, 40)
- C13: OK; measure (3.373, 1.373); threshold 0
- C14: OK; measure 0.0902; threshold 0.04
- C15: OK; measure not applicable (hedged); threshold None
- C16: FAIL; measure None; threshold 0.6
- C2: OK; measure 2.477; threshold 0.5
- C3: OK; measure 3.922; threshold 2
- C4: OK; measure 2.256; threshold 0
- C10: OK; measure 0.0003999; threshold 0.05

### R0167 (r-cible-vol-perp {L_vol_jours: 160, sigma_cible: 0.08})
- C1: FAIL; measure 6.574e-05; threshold 0.95
- C5: FAIL; measure {2020: 3.615, 2021: 6.252, 2022: -1.99, 2023: 2.417, 2024: 2.658, 2025: 0.1395}; threshold {sharpe_min: -1, positives_min: 4}
- C6: OK; measure 0.07409; threshold 0.2
- C7: FAIL; measure None; threshold {min_neighbors_share: 0.75, ratio: 0.6, min_neighbor_sharpe: 0.5}
- C8: OK; measure (4.65, 0.05386); threshold (2, 0.3)
- C9: OK; measure 6.939e-17; threshold {random_cuts: 20, fixed_cuts: 3, not_full_share_min: 0.4, tolerance: 1e-09}
- C11: OK; measure (1.565, 1.094); threshold (1.069, 0)
- C12: OK; measure (0.06892, 1.882); threshold (0.5, 40)
- C13: OK; measure (3.075, 1.103); threshold 0
- C14: OK; measure 0.1016; threshold 0.04
- C15: OK; measure not applicable (hedged); threshold None
- C16: FAIL; measure None; threshold 0.6
- C2: OK; measure 2.137; threshold 0.5
- C3: OK; measure 3.756; threshold 2
- C4: OK; measure 1.974; threshold 0
- C10: OK; measure 0.0005999; threshold 0.05

### R0168 (r-cible-vol-perp {L_vol_jours: 160, sigma_cible: 0.11})
- C1: FAIL; measure 1.807e-06; threshold 0.95
- C5: FAIL; measure {2020: 3.084, 2021: 5.135, 2022: -1.69, 2023: 2.241, 2024: 2.521, 2025: 0.06704}; threshold {sharpe_min: -1, positives_min: 4}
- C6: OK; measure 0.09475; threshold 0.2
- C7: FAIL; measure None; threshold {min_neighbors_share: 0.75, ratio: 0.6, min_neighbor_sharpe: 0.5}
- C8: OK; measure (4.445, 0.07514); threshold (2, 0.3)
- C9: OK; measure 7.633e-17; threshold {random_cuts: 20, fixed_cuts: 3, not_full_share_min: 0.4, tolerance: 1e-09}
- C11: OK; measure (1.233, 0.7737); threshold (0.904, 0)
- C12: OK; measure (0.05962, 1.84); threshold (0.5, 40)
- C13: OK; measure (2.524, 1.027); threshold 0
- C14: OK; measure 0.1178; threshold 0.04
- C15: OK; measure not applicable (hedged); threshold None
- C16: FAIL; measure None; threshold 0.6
- C2: OK; measure 1.808; threshold 0.5
- C3: OK; measure 3.513; threshold 2
- C4: OK; measure 1.692; threshold 0
- C10: OK; measure 0.0007998; threshold 0.05

### R0169 (r-cible-vol-perp {L_vol_jours: 160, sigma_cible: 0.15})
- C1: FAIL; measure 2.708e-08; threshold 0.95
- C5: FAIL; measure {2020: 2.613, 2021: 4.474, 2022: -1.548, 2023: 2.034, 2024: 2.326, 2025: -0.08351}; threshold {sharpe_min: -1, positives_min: 4}
- C6: OK; measure 0.1374; threshold 0.2
- C7: FAIL; measure None; threshold {min_neighbors_share: 0.75, ratio: 0.6, min_neighbor_sharpe: 0.5}
- C8: OK; measure (3.499, 0.1033); threshold (2, 0.3)
- C9: OK; measure 1.11e-16; threshold {random_cuts: 20, fixed_cuts: 3, not_full_share_min: 0.4, tolerance: 1e-09}
- C11: OK; measure (0.8978, 0.4317); threshold (0.7442, 0)
- C12: OK; measure (0.05259, 1.803); threshold (0.5, 40)
- C13: OK; measure (2.112, 0.8471); threshold 0
- C14: OK; measure 0.1328; threshold 0.04
- C15: OK; measure not applicable (hedged); threshold None
- C16: FAIL; measure None; threshold 0.6
- C2: OK; measure 1.488; threshold 0.5
- C3: OK; measure 3.112; threshold 2
- C4: OK; measure 1.404; threshold 0
- C10: OK; measure 0.0016; threshold 0.05

### R0170 (r-cible-vol-perp {L_vol_jours: 160, sigma_cible: 0.22})
- C1: FAIL; measure 9.012e-10; threshold 0.95
- C5: FAIL; measure {2020: 2.235, 2021: 3.878, 2022: -1.325, 2023: 1.906, 2024: 2.089, 2025: -0.1137}; threshold {sharpe_min: -1, positives_min: 4}
- C6: OK; measure 0.1979; threshold 0.2
- C7: FAIL; measure None; threshold {min_neighbors_share: 0.75, ratio: 0.6, min_neighbor_sharpe: 0.5}
- C8: OK; measure (2.435, 0.1549); threshold (2, 0.3)
- C9: OK; measure 1.943e-16; threshold {random_cuts: 20, fixed_cuts: 3, not_full_share_min: 0.4, tolerance: 1e-09}
- C11: OK; measure (0.6663, 0.1825); threshold (0.6329, 0)
- C12: OK; measure (0.04074, 1.725); threshold (0.5, 40)
- C13: OK; measure (1.77, 0.7461); threshold 0
- C14: OK; measure 0.1676; threshold 0.04
- C15: OK; measure not applicable (hedged); threshold None
- C16: FAIL; measure None; threshold 0.6
- C2: OK; measure 1.266; threshold 0.5
- C3: OK; measure 2.82; threshold 2
- C4: OK; measure 1.212; threshold 0
- C10: OK; measure 0.003599; threshold 0.05

### R0171 (r-coussin-plancher {W_jours: 7, f_plancher: 0.01})
- C1: FAIL; measure 3.205e-06; threshold 0.95
- C5: FAIL; measure {2020: 3.712, 2021: 5.079, 2022: -1.75, 2023: 2.347, 2024: 2.441, 2025: 0.09811}; threshold {sharpe_min: -1, positives_min: 4}
- C6: OK; measure 0.09136; threshold 0.2
- C7: FAIL; measure None; threshold {min_neighbors_share: 0.75, ratio: 0.6, min_neighbor_sharpe: 0.5}
- C8: OK; measure (3.705, 0.05541); threshold (2, 0.3)
- C9: OK; measure 2.29e-16; threshold {random_cuts: 20, fixed_cuts: 3, not_full_share_min: 0.4, tolerance: 1e-09}
- C11: OK; measure (1.272, 0.7744); threshold (0.9301, 0)
- C12: OK; measure (0.0771, 2.02); threshold (0.5, 40)
- C13: OK; measure (2.578, 0.8894); threshold 0
- C14: OK; measure 0.09248; threshold 0.04
- C15: OK; measure not applicable (hedged); threshold None
- C16: FAIL; measure None; threshold 0.6
- C2: OK; measure 1.86; threshold 0.5
- C3: OK; measure 3.183; threshold 2
- C4: OK; measure 1.7; threshold 0
- C10: OK; measure 0.0016; threshold 0.05

### R0172 (r-coussin-plancher {W_jours: 7, f_plancher: 0.016})
- C1: FAIL; measure 2.875e-09; threshold 0.95
- C5: FAIL; measure {2020: 2.66, 2021: 4.423, 2022: -1.785, 2023: 2.09, 2024: 1.958, 2025: -0.3229}; threshold {sharpe_min: -1, positives_min: 4}
- C6: OK; measure 0.1488; threshold 0.2
- C7: FAIL; measure None; threshold {min_neighbors_share: 0.75, ratio: 0.6, min_neighbor_sharpe: 0.5}
- C8: OK; measure (2.281, 0.08331); threshold (2, 0.3)
- C9: OK; measure 2.22e-16; threshold {random_cuts: 20, fixed_cuts: 3, not_full_share_min: 0.4, tolerance: 1e-09}
- C11: OK; measure (0.7218, 0.1964); threshold (0.6923, 0)
- C12: OK; measure (0.07367, 2.433); threshold (0.5, 40)
- C13: OK; measure (2.042, 0.4791); threshold 0
- C14: OK; measure 0.1039; threshold 0.04
- C15: OK; measure not applicable (hedged); threshold None
- C16: FAIL; measure None; threshold 0.6
- C2: OK; measure 1.385; threshold 0.5
- C3: OK; measure 2.484; threshold 2
- C4: OK; measure 1.271; threshold 0
- C10: OK; measure 0.008398; threshold 0.05

### R0173 (r-coussin-plancher {W_jours: 7, f_plancher: 0.025})
- C1: FAIL; measure 2.122e-11; threshold 0.95
- C5: FAIL; measure {2020: 2.787, 2021: 3.404, 2022: -1.388, 2023: 1.857, 2024: 1.472, 2025: -0.4065}; threshold {sharpe_min: -1, positives_min: 4}
- C6: FAIL; measure 0.2183; threshold 0.2
- C7: FAIL; measure None; threshold {min_neighbors_share: 0.75, ratio: 0.6, min_neighbor_sharpe: 0.5}
- C8: FAIL; measure (1.136, 0.1371); threshold (2, 0.3)
- C9: OK; measure 5.967e-16; threshold {random_cuts: 20, fixed_cuts: 3, not_full_share_min: 0.4, tolerance: 1e-09}
- C11: FAIL; measure (0.4031, -0.1166); threshold (0.5444, 0)
- C12: OK; measure (0.07017, 3.785); threshold (0.5, 40)
- C13: OK; measure (1.697, 0.3298); threshold 0
- C14: OK; measure 0.1343; threshold 0.04
- C15: OK; measure not applicable (hedged); threshold None
- C16: FAIL; measure None; threshold 0.6
- C2: OK; measure 1.089; threshold 0.5
- C3: OK; measure 2.148; threshold 2
- C4: OK; measure 1.006; threshold 0
- C10: OK; measure 0.0186; threshold 0.05

### R0174 (r-coussin-plancher {W_jours: 7, f_plancher: 0.04})
- C1: FAIL; measure 8.978e-11; threshold 0.95
- C5: FAIL; measure {2020: 2.825, 2021: 3.013, 2022: -1.487, 2023: 1.758, 2024: 1.529, 2025: -0.1553}; threshold {sharpe_min: -1, positives_min: 4}
- C6: FAIL; measure 0.2684; threshold 0.2
- C7: FAIL; measure None; threshold {min_neighbors_share: 0.75, ratio: 0.6, min_neighbor_sharpe: 0.5}
- C8: FAIL; measure (1.813, 0.1915); threshold (2, 0.3)
- C9: OK; measure 3.469e-16; threshold {random_cuts: 20, fixed_cuts: 3, not_full_share_min: 0.4, tolerance: 1e-09}
- C11: FAIL; measure (0.48, -0.02801); threshold (0.5877, 0)
- C12: OK; measure (0.04108, 2.472); threshold (0.5, 40)
- C13: OK; measure (1.671, 0.4696); threshold 0
- C14: OK; measure 0.1962; threshold 0.04
- C15: OK; measure not applicable (hedged); threshold None
- C16: FAIL; measure None; threshold 0.6
- C2: OK; measure 1.175; threshold 0.5
- C3: OK; measure 2.386; threshold 2
- C4: OK; measure 1.125; threshold 0
- C10: OK; measure 0.009598; threshold 0.05

### R0175 (r-coussin-plancher {W_jours: 7, f_plancher: 0.06})
- C1: FAIL; measure 2.16e-10; threshold 0.95
- C5: FAIL; measure {2020: 2.513, 2021: 3.244, 2022: -1.445, 2023: 1.758, 2024: 1.622, 2025: -0.1099}; threshold {sharpe_min: -1, positives_min: 4}
- C6: FAIL; measure 0.2883; threshold 0.2
- C7: FAIL; measure None; threshold {min_neighbors_share: 0.75, ratio: 0.6, min_neighbor_sharpe: 0.5}
- C8: OK; measure (3.023, 0.2292); threshold (2, 0.3)
- C9: OK; measure 5.135e-16; threshold {random_cuts: 20, fixed_cuts: 3, not_full_share_min: 0.4, tolerance: 1e-09}
- C11: FAIL; measure (0.5705, 0.06267); threshold (0.6132, 0)
- C12: OK; measure (0.02847, 1.609); threshold (0.5, 40)
- C13: OK; measure (1.721, 0.5178); threshold 0
- C14: OK; measure 0.2393; threshold 0.04
- C15: OK; measure not applicable (hedged); threshold None
- C16: FAIL; measure None; threshold 0.6
- C2: OK; measure 1.226; threshold 0.5
- C3: OK; measure 2.64; threshold 2
- C4: OK; measure 1.19; threshold 0
- C10: OK; measure 0.005199; threshold 0.05

### R0176 (r-coussin-plancher {W_jours: 14, f_plancher: 0.01})
- C1: FAIL; measure 5.523e-07; threshold 0.95
- C5: FAIL; measure {2020: 3.637, 2021: 4.865, 2022: -2.388, 2023: 5.476, 2024: 2.397, 2025: -0.2393}; threshold {sharpe_min: -1, positives_min: 4}
- C6: OK; measure 0.0823; threshold 0.2
- C7: FAIL; measure None; threshold {min_neighbors_share: 0.75, ratio: 0.6, min_neighbor_sharpe: 0.5}
- C8: OK; measure (2.491, 0.03872); threshold (2, 0.3)
- C9: OK; measure 5.274e-16; threshold {random_cuts: 20, fixed_cuts: 3, not_full_share_min: 0.4, tolerance: 1e-09}
- C11: OK; measure (1.035, 0.4656); threshold (0.8505, 0)
- C12: OK; measure (0.09904, 2.05); threshold (0.5, 40)
- C13: OK; measure (2.609, 0.5011); threshold 0
- C14: OK; measure 0.07044; threshold 0.04
- C15: OK; measure not applicable (hedged); threshold None
- C16: FAIL; measure None; threshold 0.6
- C2: OK; measure 1.701; threshold 0.5
- C3: OK; measure 2.685; threshold 2
- C4: OK; measure 1.506; threshold 0
- C10: OK; measure 0.005599; threshold 0.05

### R0177 (r-coussin-plancher {W_jours: 14, f_plancher: 0.016})
- C1: FAIL; measure 1.802e-08; threshold 0.95
- C5: FAIL; measure {2020: 2.644, 2021: 4.4, 2022: -1.629, 2023: 2.118, 2024: 2.614, 2025: -0.4003}; threshold {sharpe_min: -1, positives_min: 4}
- C6: OK; measure 0.1143; threshold 0.2
- C7: OK; measure 1; threshold {min_neighbors_share: 0.75, ratio: 0.6, min_neighbor_sharpe: 0.5}
- C8: OK; measure (2.599, 0.072); threshold (2, 0.3)
- C9: OK; measure 4.718e-16; threshold {random_cuts: 20, fixed_cuts: 3, not_full_share_min: 0.4, tolerance: 1e-09}
- C11: OK; measure (0.8206, 0.2601); threshold (0.7616, 0)
- C12: OK; measure (0.07267, 2.304); threshold (0.5, 40)
- C13: OK; measure (2.135, 0.6848); threshold 0
- C14: OK; measure 0.1042; threshold 0.04
- C15: OK; measure not applicable (hedged); threshold None
- C16: FAIL; measure None; threshold 0.6
- C2: OK; measure 1.523; threshold 0.5
- C3: OK; measure 2.654; threshold 2
- C4: OK; measure 1.403; threshold 0
- C10: OK; measure 0.004999; threshold 0.05

### R0178 (r-coussin-plancher {W_jours: 14, f_plancher: 0.025})
- C1: FAIL; measure 3.064e-10; threshold 0.95
- C5: FAIL; measure {2020: 3.257, 2021: 3.618, 2022: -1.6, 2023: 1.688, 2024: 1.916, 2025: -0.8039}; threshold {sharpe_min: -1, positives_min: 4}
- C6: OK; measure 0.1893; threshold 0.2
- C7: OK; measure 1; threshold {min_neighbors_share: 0.75, ratio: 0.6, min_neighbor_sharpe: 0.5}
- C8: FAIL; measure (1.891, 0.1216); threshold (2, 0.3)
- C9: OK; measure 4.996e-16; threshold {random_cuts: 20, fixed_cuts: 3, not_full_share_min: 0.4, tolerance: 1e-09}
- C11: FAIL; measure (0.5511, 0.01182); threshold (0.6314, 0)
- C12: OK; measure (0.06245, 3.352); threshold (0.5, 40)
- C13: OK; measure (1.947, 0.3794); threshold 0
- C14: OK; measure 0.1435; threshold 0.04
- C15: OK; measure not applicable (hedged); threshold None
- C16: FAIL; measure None; threshold 0.6
- C2: OK; measure 1.263; threshold 0.5
- C3: OK; measure 2.425; threshold 2
- C4: OK; measure 1.178; threshold 0
- C10: OK; measure 0.0104; threshold 0.05

### R0179 (r-coussin-plancher {W_jours: 14, f_plancher: 0.04})
- C1: FAIL; measure 1.005e-10; threshold 0.95
- C5: FAIL; measure {2020: 2.517, 2021: 3.397, 2022: -1.882, 2023: 1.846, 2024: 1.643, 2025: -0.08329}; threshold {sharpe_min: -1, positives_min: 4}
- C6: FAIL; measure 0.2669; threshold 0.2
- C7: OK; measure 1; threshold {min_neighbors_share: 0.75, ratio: 0.6, min_neighbor_sharpe: 0.5}
- C8: FAIL; measure (1.697, 0.1611); threshold (2, 0.3)
- C9: OK; measure 2.359e-16; threshold {random_cuts: 20, fixed_cuts: 3, not_full_share_min: 0.4, tolerance: 1e-09}
- C11: FAIL; measure (0.4431, -0.1001); threshold (0.5974, 0)
- C12: OK; measure (0.04693, 2.486); threshold (0.5, 40)
- C13: OK; measure (1.651, 0.544); threshold 0
- C14: OK; measure 0.17; threshold 0.04
- C15: OK; measure not applicable (hedged); threshold None
- C16: FAIL; measure None; threshold 0.6
- C2: OK; measure 1.195; threshold 0.5
- C3: OK; measure 2.326; threshold 2
- C4: OK; measure 1.136; threshold 0
- C10: OK; measure 0.0132; threshold 0.05

### R0180 (r-coussin-plancher {W_jours: 14, f_plancher: 0.06})
- C1: FAIL; measure 1.621e-10; threshold 0.95
- C5: FAIL; measure {2020: 2.635, 2021: 3.134, 2022: -1.491, 2023: 1.818, 2024: 1.684, 2025: -0.1142}; threshold {sharpe_min: -1, positives_min: 4}
- C6: FAIL; measure 0.2872; threshold 0.2
- C7: FAIL; measure None; threshold {min_neighbors_share: 0.75, ratio: 0.6, min_neighbor_sharpe: 0.5}
- C8: OK; measure (2.466, 0.2098); threshold (2, 0.3)
- C9: OK; measure 2.984e-16; threshold {random_cuts: 20, fixed_cuts: 3, not_full_share_min: 0.4, tolerance: 1e-09}
- C11: FAIL; measure (0.5317, 0.007689); threshold (0.6052, 0)
- C12: OK; measure (0.03219, 1.746); threshold (0.5, 40)
- C13: OK; measure (1.755, 0.4117); threshold 0
- C14: OK; measure 0.2204; threshold 0.04
- C15: OK; measure not applicable (hedged); threshold None
- C16: FAIL; measure None; threshold 0.6
- C2: OK; measure 1.21; threshold 0.5
- C3: OK; measure 2.519; threshold 2
- C4: OK; measure 1.17; threshold 0
- C10: OK; measure 0.006599; threshold 0.05

### R0181 (r-coussin-plancher {W_jours: 28, f_plancher: 0.01})
- C1: FAIL; measure 5.515e-06; threshold 0.95
- C5: FAIL; measure {2020: 3.559, 2021: 4.756, 2022: -2.144, 2023: 2.644, 2024: 3.021, 2025: 0.314}; threshold {sharpe_min: -1, positives_min: 4}
- C6: OK; measure 0.08959; threshold 0.2
- C7: FAIL; measure None; threshold {min_neighbors_share: 0.75, ratio: 0.6, min_neighbor_sharpe: 0.5}
- C8: OK; measure (3.243, 0.04633); threshold (2, 0.3)
- C9: OK; measure 2.984e-16; threshold {random_cuts: 20, fixed_cuts: 3, not_full_share_min: 0.4, tolerance: 1e-09}
- C11: OK; measure (1.27, 0.7346); threshold (0.954, 0)
- C12: OK; measure (0.08243, 1.988); threshold (0.5, 40)
- C13: OK; measure (2.444, 1.171); threshold 0
- C14: OK; measure 0.08533; threshold 0.04
- C15: OK; measure not applicable (hedged); threshold None
- C16: FAIL; measure None; threshold 0.6
- C2: OK; measure 1.908; threshold 0.5
- C3: OK; measure 3.169; threshold 2
- C4: OK; measure 1.728; threshold 0
- C10: OK; measure 0.0018; threshold 0.05

### R0182 (r-coussin-plancher {W_jours: 28, f_plancher: 0.016})
- C1: FAIL; measure 6.483e-07; threshold 0.95
- C5: FAIL; measure {2020: 3.858, 2021: 4.928, 2022: -2.413, 2023: 2.086, 2024: 2.421, 2025: -0.02451}; threshold {sharpe_min: -1, positives_min: 4}
- C6: OK; measure 0.1384; threshold 0.2
- C7: OK; measure 1; threshold {min_neighbors_share: 0.75, ratio: 0.6, min_neighbor_sharpe: 0.5}
- C8: OK; measure (3.454, 0.06537); threshold (2, 0.3)
- C9: OK; measure 3.747e-16; threshold {random_cuts: 20, fixed_cuts: 3, not_full_share_min: 0.4, tolerance: 1e-09}
- C11: OK; measure (1.117, 0.5519); threshold (0.9062, 0)
- C12: OK; measure (0.06445, 2.188); threshold (0.5, 40)
- C13: OK; measure (2.509, 0.8881); threshold 0
- C14: OK; measure 0.1171; threshold 0.04
- C15: OK; measure not applicable (hedged); threshold None
- C16: FAIL; measure None; threshold 0.6
- C2: OK; measure 1.812; threshold 0.5
- C3: OK; measure 3.064; threshold 2
- C4: OK; measure 1.683; threshold 0
- C10: OK; measure 0.0022; threshold 0.05

### R0183 (r-coussin-plancher {W_jours: 28, f_plancher: 0.025})
- C1: FAIL; measure 6.368e-09; threshold 0.95
- C5: FAIL; measure {2020: 3.409, 2021: 4.114, 2022: -1.311, 2023: 1.291, 2024: 2.251, 2025: -0.7932}; threshold {sharpe_min: -1, positives_min: 4}
- C6: OK; measure 0.1521; threshold 0.2
- C7: OK; measure 1; threshold {min_neighbors_share: 0.75, ratio: 0.6, min_neighbor_sharpe: 0.5}
- C8: OK; measure (2.571, 0.1021); threshold (2, 0.3)
- C9: OK; measure 1.527e-16; threshold {random_cuts: 20, fixed_cuts: 3, not_full_share_min: 0.4, tolerance: 1e-09}
- C11: OK; measure (0.7386, 0.1676); threshold (0.7334, 0)
- C12: OK; measure (0.05774, 3.086); threshold (0.5, 40)
- C13: OK; measure (2.188, 0.5534); threshold 0
- C14: OK; measure 0.1538; threshold 0.04
- C15: OK; measure not applicable (hedged); threshold None
- C16: FAIL; measure None; threshold 0.6
- C2: OK; measure 1.467; threshold 0.5
- C3: OK; measure 2.7; threshold 2
- C4: OK; measure 1.375; threshold 0
- C10: OK; measure 0.005999; threshold 0.05

### R0184 (r-coussin-plancher {W_jours: 28, f_plancher: 0.04})
- C1: FAIL; measure 1.43e-10; threshold 0.95
- C5: FAIL; measure {2020: 2.957, 2021: 3.447, 2022: -1.912, 2023: 1.774, 2024: 1.698, 2025: -0.2752}; threshold {sharpe_min: -1, positives_min: 4}
- C6: FAIL; measure 0.2965; threshold 0.2
- C7: OK; measure 1; threshold {min_neighbors_share: 0.75, ratio: 0.6, min_neighbor_sharpe: 0.5}
- C8: FAIL; measure (1.642, 0.1547); threshold (2, 0.3)
- C9: OK; measure 4.025e-16; threshold {random_cuts: 20, fixed_cuts: 3, not_full_share_min: 0.4, tolerance: 1e-09}
- C11: FAIL; measure (0.4823, -0.05571); threshold (0.5978, 0)
- C12: OK; measure (0.04894, 2.782); threshold (0.5, 40)
- C13: OK; measure (1.717, 0.4771); threshold 0
- C14: OK; measure 0.1717; threshold 0.04
- C15: OK; measure not applicable (hedged); threshold None
- C16: FAIL; measure None; threshold 0.6
- C2: OK; measure 1.196; threshold 0.5
- C3: OK; measure 2.315; threshold 2
- C4: OK; measure 1.134; threshold 0
- C10: OK; measure 0.0126; threshold 0.05

### R0185 (r-coussin-plancher {W_jours: 28, f_plancher: 0.06})
- C1: FAIL; measure 1.87e-10; threshold 0.95
- C5: FAIL; measure {2020: 2.824, 2021: 3.322, 2022: -1.339, 2023: 1.758, 2024: 1.548, 2025: -0.323}; threshold {sharpe_min: -1, positives_min: 4}
- C6: FAIL; measure 0.2808; threshold 0.2
- C7: FAIL; measure None; threshold {min_neighbors_share: 0.75, ratio: 0.6, min_neighbor_sharpe: 0.5}
- C8: OK; measure (2.288, 0.2046); threshold (2, 0.3)
- C9: OK; measure 1.249e-15; threshold {random_cuts: 20, fixed_cuts: 3, not_full_share_min: 0.4, tolerance: 1e-09}
- C11: FAIL; measure (0.5341, 0.01026); threshold (0.6081, 0)
- C12: OK; measure (0.03409, 2.143); threshold (0.5, 40)
- C13: OK; measure (1.82, 0.3323); threshold 0
- C14: OK; measure 0.2211; threshold 0.04
- C15: OK; measure not applicable (hedged); threshold None
- C16: FAIL; measure None; threshold 0.6
- C2: OK; measure 1.216; threshold 0.5
- C3: OK; measure 2.528; threshold 2
- C4: OK; measure 1.173; threshold 0
- C10: OK; measure 0.007199; threshold 0.05

### R0186 (r-coussin-plancher {W_jours: 56, f_plancher: 0.01})
- C1: FAIL; measure 9.607e-05; threshold 0.95
- C5: FAIL; measure {2020: 3.507, 2021: 5.001, 2022: -1.831, 2023: 1.764, 2024: 2.929, 2025: 0.435}; threshold {sharpe_min: -1, positives_min: 4}
- C6: OK; measure 0.05698; threshold 0.2
- C7: FAIL; measure None; threshold {min_neighbors_share: 0.75, ratio: 0.6, min_neighbor_sharpe: 0.5}
- C8: OK; measure (3.935, 0.0426); threshold (2, 0.3)
- C9: OK; measure 3.886e-16; threshold {random_cuts: 20, fixed_cuts: 3, not_full_share_min: 0.4, tolerance: 1e-09}
- C11: OK; measure (1.555, 1.016); threshold (1.093, 0)
- C12: OK; measure (0.07593, 1.956); threshold (0.5, 40)
- C13: OK; measure (2.866, 1.262); threshold 0
- C14: OK; measure 0.09317; threshold 0.04
- C15: OK; measure not applicable (hedged); threshold None
- C16: FAIL; measure None; threshold 0.6
- C2: OK; measure 2.186; threshold 0.5
- C3: OK; measure 3.551; threshold 2
- C4: OK; measure 1.998; threshold 0
- C10: OK; measure 0.0012; threshold 0.05

### R0187 (r-coussin-plancher {W_jours: 56, f_plancher: 0.016})
- C1: FAIL; measure 1.518e-05; threshold 0.95
- C5: FAIL; measure {2020: 3.753, 2021: 4.945, 2022: -1.241, 2023: 2.351, 2024: 2.973, 2025: -0.3669}; threshold {sharpe_min: -1, positives_min: 4}
- C6: OK; measure 0.0767; threshold 0.2
- C7: OK; measure 1; threshold {min_neighbors_share: 0.75, ratio: 0.6, min_neighbor_sharpe: 0.5}
- C8: OK; measure (3.718, 0.05125); threshold (2, 0.3)
- C9: OK; measure 4.51e-16; threshold {random_cuts: 20, fixed_cuts: 3, not_full_share_min: 0.4, tolerance: 1e-09}
- C11: OK; measure (1.382, 0.7951); threshold (1.045, 0)
- C12: OK; measure (0.06307, 2.086); threshold (0.5, 40)
- C13: OK; measure (2.898, 0.9891); threshold 0
- C14: OK; measure 0.1168; threshold 0.04
- C15: OK; measure not applicable (hedged); threshold None
- C16: FAIL; measure None; threshold 0.6
- C2: OK; measure 2.091; threshold 0.5
- C3: OK; measure 3.354; threshold 2
- C4: OK; measure 1.949; threshold 0
- C10: OK; measure 0.0012; threshold 0.05

### R0188 (r-coussin-plancher {W_jours: 56, f_plancher: 0.025})
- C1: FAIL; measure 2.688e-08; threshold 0.95
- C5: FAIL; measure {2020: 3.338, 2021: 4.435, 2022: -2.039, 2023: 1.333, 2024: 1.975, 2025: -0.2567}; threshold {sharpe_min: -1, positives_min: 4}
- C6: OK; measure 0.1446; threshold 0.2
- C7: OK; measure 1; threshold {min_neighbors_share: 0.75, ratio: 0.6, min_neighbor_sharpe: 0.5}
- C8: OK; measure (2.516, 0.07948); threshold (2, 0.3)
- C9: OK; measure 3.955e-16; threshold {random_cuts: 20, fixed_cuts: 3, not_full_share_min: 0.4, tolerance: 1e-09}
- C11: OK; measure (0.7779, 0.1678); threshold (0.7723, 0)
- C12: OK; measure (0.06224, 2.711); threshold (0.5, 40)
- C13: OK; measure (2.35, 0.56); threshold 0
- C14: OK; measure 0.1333; threshold 0.04
- C15: OK; measure not applicable (hedged); threshold None
- C16: FAIL; measure None; threshold 0.6
- C2: OK; measure 1.545; threshold 0.5
- C3: OK; measure 2.622; threshold 2
- C4: OK; measure 1.442; threshold 0
- C10: OK; measure 0.006399; threshold 0.05

### R0189 (r-coussin-plancher {W_jours: 56, f_plancher: 0.04})
- C1: FAIL; measure 1.234e-09; threshold 0.95
- C5: FAIL; measure {2020: 3.007, 2021: 3.59, 2022: -1.498, 2023: 1.751, 2024: 1.595, 2025: -0.05988}; threshold {sharpe_min: -1, positives_min: 4}
- C6: FAIL; measure 0.2059; threshold 0.2
- C7: OK; measure 1; threshold {min_neighbors_share: 0.75, ratio: 0.6, min_neighbor_sharpe: 0.5}
- C8: OK; measure (2.161, 0.1363); threshold (2, 0.3)
- C9: OK; measure 7.147e-16; threshold {random_cuts: 20, fixed_cuts: 3, not_full_share_min: 0.4, tolerance: 1e-09}
- C11: FAIL; measure (0.5945, 0.04415); threshold (0.6755, 0)
- C12: OK; measure (0.04648, 2.721); threshold (0.5, 40)
- C13: OK; measure (2.014, 0.4843); threshold 0
- C14: OK; measure 0.1825; threshold 0.04
- C15: OK; measure not applicable (hedged); threshold None
- C16: FAIL; measure None; threshold 0.6
- C2: OK; measure 1.351; threshold 0.5
- C3: OK; measure 2.549; threshold 2
- C4: OK; measure 1.285; threshold 0
- C10: OK; measure 0.008598; threshold 0.05

### R0190 (r-coussin-plancher {W_jours: 56, f_plancher: 0.06})
- C1: FAIL; measure 2.602e-09; threshold 0.95
- C5: OK; measure {2020: 2.523, 2021: 3.622, 2022: -0.8528, 2023: 1.804, 2024: 1.626, 2025: -0.1783}; threshold {sharpe_min: -1, positives_min: 4}
- C6: FAIL; measure 0.2092; threshold 0.2
- C7: FAIL; measure None; threshold {min_neighbors_share: 0.75, ratio: 0.6, min_neighbor_sharpe: 0.5}
- C8: OK; measure (2.939, 0.1764); threshold (2, 0.3)
- C9: OK; measure 2.22e-16; threshold {random_cuts: 20, fixed_cuts: 3, not_full_share_min: 0.4, tolerance: 1e-09}
- C11: FAIL; measure (0.6747, 0.1127); threshold (0.6985, 0)
- C12: OK; measure (0.03242, 2.011); threshold (0.5, 40)
- C13: OK; measure (2.083, 0.4049); threshold 0
- C14: OK; measure 0.2346; threshold 0.04
- C15: OK; measure not applicable (hedged); threshold None
- C16: FAIL; measure None; threshold 0.6
- C2: OK; measure 1.397; threshold 0.5
- C3: OK; measure 2.807; threshold 2
- C4: OK; measure 1.35; threshold 0
- C10: OK; measure 0.003599; threshold 0.05

### R0191 (r-coussin-plancher {W_jours: 112, f_plancher: 0.01})
- C1: FAIL; measure 0.0003948; threshold 0.95
- C5: FAIL; measure {2020: 3.426, 2021: 5.338, 2022: -3.214, 2023: 1.894, 2024: 2.132, 2025: 1.119}; threshold {sharpe_min: -1, positives_min: 4}
- C6: OK; measure 0.05619; threshold 0.2
- C7: FAIL; measure None; threshold {min_neighbors_share: 0.75, ratio: 0.6, min_neighbor_sharpe: 0.5}
- C8: OK; measure (3.646, 0.0324); threshold (2, 0.3)
- C9: OK; measure 2.706e-16; threshold {random_cuts: 20, fixed_cuts: 3, not_full_share_min: 0.4, tolerance: 1e-09}
- C11: OK; measure (1.628, 1.06); threshold (1.14, 0)
- C12: OK; measure (0.08121, 1.971); threshold (0.5, 40)
- C13: OK; measure (3.124, 1.146); threshold 0
- C14: OK; measure 0.08702; threshold 0.04
- C15: OK; measure not applicable (hedged); threshold None
- C16: FAIL; measure None; threshold 0.6
- C2: OK; measure 2.279; threshold 0.5
- C3: OK; measure 3.445; threshold 2
- C4: OK; measure 2.064; threshold 0
- C10: OK; measure 0.0007998; threshold 0.05

### R0192 (r-coussin-plancher {W_jours: 112, f_plancher: 0.016})
- C1: FAIL; measure 1.043e-05; threshold 0.95
- C5: FAIL; measure {2020: 3.572, 2021: 5.189, 2022: -2.657, 2023: 1.656, 2024: 1.91, 2025: 0.6093}; threshold {sharpe_min: -1, positives_min: 4}
- C6: OK; measure 0.07717; threshold 0.2
- C7: FAIL; measure None; threshold {min_neighbors_share: 0.75, ratio: 0.6, min_neighbor_sharpe: 0.5}
- C8: OK; measure (3.562, 0.0409); threshold (2, 0.3)
- C9: OK; measure 5.343e-16; threshold {random_cuts: 20, fixed_cuts: 3, not_full_share_min: 0.4, tolerance: 1e-09}
- C11: OK; measure (1.35, 0.7141); threshold (1.054, 0)
- C12: OK; measure (0.06927, 2.016); threshold (0.5, 40)
- C13: OK; measure (2.989, 0.9769); threshold 0
- C14: OK; measure 0.1044; threshold 0.04
- C15: OK; measure not applicable (hedged); threshold None
- C16: FAIL; measure None; threshold 0.6
- C2: OK; measure 2.108; threshold 0.5
- C3: OK; measure 3.279; threshold 2
- C4: OK; measure 1.947; threshold 0
- C10: OK; measure 0.0016; threshold 0.05

### R0193 (r-coussin-plancher {W_jours: 112, f_plancher: 0.025})
- C1: FAIL; measure 3.837e-08; threshold 0.95
- C5: FAIL; measure {2020: 3.349, 2021: 3.913, 2022: -1.771, 2023: 0.9443, 2024: 2.191, 2025: 0.4126}; threshold {sharpe_min: -1, positives_min: 4}
- C6: OK; measure 0.1266; threshold 0.2
- C7: FAIL; measure None; threshold {min_neighbors_share: 0.75, ratio: 0.6, min_neighbor_sharpe: 0.5}
- C8: OK; measure (2.514, 0.07076); threshold (2, 0.3)
- C9: OK; measure 3.678e-16; threshold {random_cuts: 20, fixed_cuts: 3, not_full_share_min: 0.4, tolerance: 1e-09}
- C11: FAIL; measure (0.7488, 0.1473); threshold (0.7798, 0)
- C12: OK; measure (0.06457, 2.367); threshold (0.5, 40)
- C13: OK; measure (2.217, 0.7794); threshold 0
- C14: OK; measure 0.1192; threshold 0.04
- C15: OK; measure not applicable (hedged); threshold None
- C16: FAIL; measure None; threshold 0.6
- C2: OK; measure 1.56; threshold 0.5
- C3: OK; measure 2.716; threshold 2
- C4: OK; measure 1.452; threshold 0
- C10: OK; measure 0.006199; threshold 0.05

### R0194 (r-coussin-plancher {W_jours: 112, f_plancher: 0.04})
- C1: FAIL; measure 1.932e-09; threshold 0.95
- C5: FAIL; measure {2020: 2.652, 2021: 3.258, 2022: -1.775, 2023: 1.312, 2024: 1.708, 2025: 0.7946}; threshold {sharpe_min: -1, positives_min: 4}
- C6: OK; measure 0.1741; threshold 0.2
- C7: FAIL; measure None; threshold {min_neighbors_share: 0.75, ratio: 0.6, min_neighbor_sharpe: 0.5}
- C8: OK; measure (2.126, 0.1034); threshold (2, 0.3)
- C9: OK; measure 9.714e-16; threshold {random_cuts: 20, fixed_cuts: 3, not_full_share_min: 0.4, tolerance: 1e-09}
- C11: FAIL; measure (0.5551, -0.06197); threshold (0.6896, 0)
- C12: OK; measure (0.05111, 2.55); threshold (0.5, 40)
- C13: OK; measure (1.886, 0.7593); threshold 0
- C14: OK; measure 0.1603; threshold 0.04
- C15: OK; measure not applicable (hedged); threshold None
- C16: FAIL; measure None; threshold 0.6
- C2: OK; measure 1.379; threshold 0.5
- C3: OK; measure 2.529; threshold 2
- C4: OK; measure 1.304; threshold 0
- C10: OK; measure 0.0106; threshold 0.05

### R0195 (r-coussin-plancher {W_jours: 112, f_plancher: 0.06})
- C1: FAIL; measure 3.318e-10; threshold 0.95
- C5: FAIL; measure {2020: 2.137, 2021: 3.094, 2022: -1.324, 2023: 1.769, 2024: 1.319, 2025: 0.5477}; threshold {sharpe_min: -1, positives_min: 4}
- C6: FAIL; measure 0.2128; threshold 0.2
- C7: FAIL; measure None; threshold {min_neighbors_share: 0.75, ratio: 0.6, min_neighbor_sharpe: 0.5}
- C8: FAIL; measure (1.951, 0.1521); threshold (2, 0.3)
- C9: OK; measure 2.429e-16; threshold {random_cuts: 20, fixed_cuts: 3, not_full_share_min: 0.4, tolerance: 1e-09}
- C11: FAIL; measure (0.4798, -0.09342); threshold (0.6277, 0)
- C12: OK; measure (0.03993, 2.136); threshold (0.5, 40)
- C13: OK; measure (1.747, 0.5797); threshold 0
- C14: OK; measure 0.1909; threshold 0.04
- C15: OK; measure not applicable (hedged); threshold None
- C16: FAIL; measure None; threshold 0.6
- C2: OK; measure 1.255; threshold 0.5
- C3: OK; measure 2.495; threshold 2
- C4: OK; measure 1.203; threshold 0
- C10: OK; measure 0.009598; threshold 0.05

### R0196 (t-ecart {L_jours: 30, zs_saturation: 0.15})
- C1: FAIL; measure 3.665e-08; threshold 0.95
- C5: FAIL; measure {2020: 2.823, 2021: 3.571, 2022: -1.576, 2023: 1.939, 2024: 1.718, 2025: -0.4294}; threshold {sharpe_min: -1, positives_min: 4}
- C6: OK; measure 0.1777; threshold 0.2
- C7: FAIL; measure None; threshold {min_neighbors_share: 0.75, ratio: 0.6, min_neighbor_sharpe: 0.5}
- C8: OK; measure (2.806, 0.1239); threshold (2, 0.3)
- C9: OK; measure 4.857e-16; threshold {random_cuts: 20, fixed_cuts: 3, not_full_share_min: 0.4, tolerance: 1e-09}
- C11: OK; measure (0.7927, 0.1613); threshold (0.7719, 0)
- C12: OK; measure (0.06767, 5.082); threshold (0.5, 40)
- C13: OK; measure (2.058, 0.8016); threshold 0
- C14: OK; measure 0.2061; threshold 0.04
- C15: OK; measure not applicable (hedged); threshold None
- C16: FAIL; measure None; threshold 0.6
- C2: OK; measure 1.544; threshold 0.5
- C3: OK; measure 2.849; threshold 2
- C4: OK; measure 1.431; threshold 0
- C10: OK; measure 0.004199; threshold 0.05

### R0197 (t-ecart {L_jours: 30, zs_saturation: 0.25})
- C1: FAIL; measure 6.064e-08; threshold 0.95
- C5: FAIL; measure {2020: 2.905, 2021: 3.67, 2022: -1.613, 2023: 1.948, 2024: 1.763, 2025: -0.4329}; threshold {sharpe_min: -1, positives_min: 4}
- C6: OK; measure 0.1766; threshold 0.2
- C7: FAIL; measure None; threshold {min_neighbors_share: 0.75, ratio: 0.6, min_neighbor_sharpe: 0.5}
- C8: OK; measure (2.922, 0.124); threshold (2, 0.3)
- C9: OK; measure 4.233e-16; threshold {random_cuts: 20, fixed_cuts: 3, not_full_share_min: 0.4, tolerance: 1e-09}
- C11: OK; measure (0.8413, 0.2107); threshold (0.7957, 0)
- C12: OK; measure (0.06675, 4.996); threshold (0.5, 40)
- C13: OK; measure (2.125, 0.819); threshold 0
- C14: OK; measure 0.2102; threshold 0.04
- C15: OK; measure not applicable (hedged); threshold None
- C16: FAIL; measure None; threshold 0.6
- C2: OK; measure 1.591; threshold 0.5
- C3: OK; measure 2.891; threshold 2
- C4: OK; measure 1.477; threshold 0
- C10: OK; measure 0.003599; threshold 0.05

### R0198 (t-ecart {L_jours: 30, zs_saturation: 0.4})
- C1: FAIL; measure 8.464e-08; threshold 0.95
- C5: FAIL; measure {2020: 3.007, 2021: 3.752, 2022: -1.697, 2023: 1.945, 2024: 1.833, 2025: -0.4741}; threshold {sharpe_min: -1, positives_min: 4}
- C6: OK; measure 0.1774; threshold 0.2
- C7: FAIL; measure None; threshold {min_neighbors_share: 0.75, ratio: 0.6, min_neighbor_sharpe: 0.5}
- C8: OK; measure (3.046, 0.1242); threshold (2, 0.3)
- C9: OK; measure 2.22e-16; threshold {random_cuts: 20, fixed_cuts: 3, not_full_share_min: 0.4, tolerance: 1e-09}
- C11: OK; measure (0.8737, 0.2483); threshold (0.8161, 0)
- C12: OK; measure (0.06536, 4.772); threshold (0.5, 40)
- C13: OK; measure (2.185, 0.833); threshold 0
- C14: OK; measure 0.21; threshold 0.04
- C15: OK; measure not applicable (hedged); threshold None
- C16: FAIL; measure None; threshold 0.6
- C2: OK; measure 1.632; threshold 0.5
- C3: OK; measure 2.925; threshold 2
- C4: OK; measure 1.518; threshold 0
- C10: OK; measure 0.003399; threshold 0.05

### R0199 (t-ecart {L_jours: 30, zs_saturation: 0.65})
- C1: FAIL; measure 6.952e-08; threshold 0.95
- C5: FAIL; measure {2020: 2.961, 2021: 3.81, 2022: -1.848, 2023: 2.022, 2024: 1.928, 2025: -0.4808}; threshold {sharpe_min: -1, positives_min: 4}
- C6: OK; measure 0.1799; threshold 0.2
- C7: FAIL; measure None; threshold {min_neighbors_share: 0.75, ratio: 0.6, min_neighbor_sharpe: 0.5}
- C8: OK; measure (3.174, 0.1241); threshold (2, 0.3)
- C9: OK; measure 1.596e-16; threshold {random_cuts: 20, fixed_cuts: 3, not_full_share_min: 0.4, tolerance: 1e-09}
- C11: OK; measure (0.8803, 0.2707); threshold (0.8108, 0)
- C12: OK; measure (0.06586, 4.319); threshold (0.5, 40)
- C13: OK; measure (2.169, 0.8398); threshold 0
- C14: OK; measure 0.1955; threshold 0.04
- C15: OK; measure not applicable (hedged); threshold None
- C16: FAIL; measure None; threshold 0.6
- C2: OK; measure 1.622; threshold 0.5
- C3: OK; measure 2.924; threshold 2
- C4: OK; measure 1.507; threshold 0
- C10: OK; measure 0.003199; threshold 0.05

### R0200 (t-ecart {L_jours: 30, zs_saturation: 1})
- C1: FAIL; measure 4.803e-08; threshold 0.95
- C5: FAIL; measure {2020: 2.88, 2021: 3.879, 2022: -1.912, 2023: 2.132, 2024: 1.996, 2025: -0.4515}; threshold {sharpe_min: -1, positives_min: 4}
- C6: OK; measure 0.1823; threshold 0.2
- C7: FAIL; measure None; threshold {min_neighbors_share: 0.75, ratio: 0.6, min_neighbor_sharpe: 0.5}
- C8: OK; measure (3.33, 0.1229); threshold (2, 0.3)
- C9: OK; measure 2.637e-16; threshold {random_cuts: 20, fixed_cuts: 3, not_full_share_min: 0.4, tolerance: 1e-09}
- C11: OK; measure (0.8716, 0.2928); threshold (0.7939, 0)
- C12: OK; measure (0.06886, 3.819); threshold (0.5, 40)
- C13: OK; measure (2.128, 0.8233); threshold 0
- C14: OK; measure 0.1774; threshold 0.04
- C15: OK; measure not applicable (hedged); threshold None
- C16: FAIL; measure None; threshold 0.6
- C2: OK; measure 1.588; threshold 0.5
- C3: OK; measure 2.903; threshold 2
- C4: OK; measure 1.471; threshold 0
- C10: OK; measure 0.002799; threshold 0.05

### R0201 (t-ecart {L_jours: 50, zs_saturation: 0.15})
- C1: FAIL; measure 1.737e-08; threshold 0.95
- C5: FAIL; measure {2020: 2.389, 2021: 3.548, 2022: -1.836, 2023: 1.705, 2024: 1.502, 2025: 0.2254}; threshold {sharpe_min: -1, positives_min: 4}
- C6: OK; measure 0.1813; threshold 0.2
- C7: FAIL; measure None; threshold {min_neighbors_share: 0.75, ratio: 0.6, min_neighbor_sharpe: 0.5}
- C8: OK; measure (2.706, 0.1321); threshold (2, 0.3)
- C9: OK; measure 2.082e-16; threshold {random_cuts: 20, fixed_cuts: 3, not_full_share_min: 0.4, tolerance: 1e-09}
- C11: OK; measure (0.7576, 0.1401); threshold (0.756, 0)
- C12: OK; measure (0.0577, 3.869); threshold (0.5, 40)
- C13: OK; measure (1.964, 0.8715); threshold 0
- C14: OK; measure 0.2106; threshold 0.04
- C15: OK; measure not applicable (hedged); threshold None
- C16: FAIL; measure None; threshold 0.6
- C2: OK; measure 1.512; threshold 0.5
- C3: OK; measure 2.845; threshold 2
- C4: OK; measure 1.42; threshold 0
- C10: OK; measure 0.003999; threshold 0.05

### R0202 (t-ecart {L_jours: 50, zs_saturation: 0.25})
- C1: FAIL; measure 1.795e-08; threshold 0.95
- C5: FAIL; measure {2020: 2.368, 2021: 3.602, 2022: -1.932, 2023: 1.778, 2024: 1.531, 2025: 0.1605}; threshold {sharpe_min: -1, positives_min: 4}
- C6: OK; measure 0.1809; threshold 0.2
- C7: OK; measure 1; threshold {min_neighbors_share: 0.75, ratio: 0.6, min_neighbor_sharpe: 0.5}
- C8: OK; measure (2.727, 0.132); threshold (2, 0.3)
- C9: OK; measure 2.22e-16; threshold {random_cuts: 20, fixed_cuts: 3, not_full_share_min: 0.4, tolerance: 1e-09}
- C11: OK; measure (0.7628, 0.145); threshold (0.7601, 0)
- C12: OK; measure (0.05797, 3.818); threshold (0.5, 40)
- C13: OK; measure (1.969, 0.887); threshold 0
- C14: OK; measure 0.2086; threshold 0.04
- C15: OK; measure not applicable (hedged); threshold None
- C16: FAIL; measure None; threshold 0.6
- C2: OK; measure 1.52; threshold 0.5
- C3: OK; measure 2.842; threshold 2
- C4: OK; measure 1.427; threshold 0
- C10: OK; measure 0.004999; threshold 0.05

### R0203 (t-ecart {L_jours: 50, zs_saturation: 0.4})
- C1: FAIL; measure 1.881e-08; threshold 0.95
- C5: FAIL; measure {2020: 2.398, 2021: 3.577, 2022: -2.025, 2023: 1.917, 2024: 1.593, 2025: -0.004869}; threshold {sharpe_min: -1, positives_min: 4}
- C6: OK; measure 0.1801; threshold 0.2
- C7: OK; measure 1; threshold {min_neighbors_share: 0.75, ratio: 0.6, min_neighbor_sharpe: 0.5}
- C8: OK; measure (2.76, 0.1314); threshold (2, 0.3)
- C9: OK; measure 1.874e-16; threshold {random_cuts: 20, fixed_cuts: 3, not_full_share_min: 0.4, tolerance: 1e-09}
- C11: OK; measure (0.7724, 0.1594); threshold (0.7547, 0)
- C12: OK; measure (0.06013, 3.706); threshold (0.5, 40)
- C13: OK; measure (1.954, 0.8857); threshold 0
- C14: OK; measure 0.1992; threshold 0.04
- C15: OK; measure not applicable (hedged); threshold None
- C16: FAIL; measure None; threshold 0.6
- C2: OK; measure 1.509; threshold 0.5
- C3: OK; measure 2.842; threshold 2
- C4: OK; measure 1.414; threshold 0
- C10: OK; measure 0.004599; threshold 0.05

### R0204 (t-ecart {L_jours: 50, zs_saturation: 0.65})
- C1: FAIL; measure 2.626e-08; threshold 0.95
- C5: FAIL; measure {2020: 2.457, 2021: 3.691, 2022: -2.078, 2023: 1.959, 2024: 1.726, 2025: -0.08731}; threshold {sharpe_min: -1, positives_min: 4}
- C6: OK; measure 0.1803; threshold 0.2
- C7: OK; measure 1; threshold {min_neighbors_share: 0.75, ratio: 0.6, min_neighbor_sharpe: 0.5}
- C8: OK; measure (2.941, 0.1303); threshold (2, 0.3)
- C9: OK; measure 2.498e-16; threshold {random_cuts: 20, fixed_cuts: 3, not_full_share_min: 0.4, tolerance: 1e-09}
- C11: OK; measure (0.7938, 0.1905); threshold (0.7706, 0)
- C12: OK; measure (0.06172, 3.521); threshold (0.5, 40)
- C13: OK; measure (2.011, 0.8818); threshold 0
- C14: OK; measure 0.1921; threshold 0.04
- C15: OK; measure not applicable (hedged); threshold None
- C16: FAIL; measure None; threshold 0.6
- C2: OK; measure 1.541; threshold 0.5
- C3: OK; measure 2.871; threshold 2
- C4: OK; measure 1.44; threshold 0
- C10: OK; measure 0.004399; threshold 0.05

### R0205 (t-ecart {L_jours: 50, zs_saturation: 1})
- C1: FAIL; measure 1.844e-08; threshold 0.95
- C5: FAIL; measure {2020: 2.479, 2021: 3.631, 2022: -1.96, 2023: 2.054, 2024: 1.818, 2025: -0.1834}; threshold {sharpe_min: -1, positives_min: 4}
- C6: OK; measure 0.1769; threshold 0.2
- C7: FAIL; measure None; threshold {min_neighbors_share: 0.75, ratio: 0.6, min_neighbor_sharpe: 0.5}
- C8: OK; measure (3.063, 0.1274); threshold (2, 0.3)
- C9: OK; measure 1.735e-16; threshold {random_cuts: 20, fixed_cuts: 3, not_full_share_min: 0.4, tolerance: 1e-09}
- C11: OK; measure (0.7901, 0.223); threshold (0.7514, 0)
- C12: OK; measure (0.06369, 3.152); threshold (0.5, 40)
- C13: OK; measure (1.975, 0.8411); threshold 0
- C14: OK; measure 0.1723; threshold 0.04
- C15: OK; measure not applicable (hedged); threshold None
- C16: FAIL; measure None; threshold 0.6
- C2: OK; measure 1.503; threshold 0.5
- C3: OK; measure 2.861; threshold 2
- C4: OK; measure 1.402; threshold 0
- C10: OK; measure 0.004399; threshold 0.05

### R0206 (t-ecart {L_jours: 80, zs_saturation: 0.15})
- C1: FAIL; measure 7.44e-10; threshold 0.95
- C5: FAIL; measure {2020: 1.327, 2021: 3.285, 2022: -2.472, 2023: 1.441, 2024: 1.609, 2025: 0.1601}; threshold {sharpe_min: -1, positives_min: 4}
- C6: FAIL; measure 0.2133; threshold 0.2
- C7: FAIL; measure None; threshold {min_neighbors_share: 0.75, ratio: 0.6, min_neighbor_sharpe: 0.5}
- C8: FAIL; measure (1.834, 0.1443); threshold (2, 0.3)
- C9: OK; measure 3.192e-16; threshold {random_cuts: 20, fixed_cuts: 3, not_full_share_min: 0.4, tolerance: 1e-09}
- C11: FAIL; measure (0.5006, -0.09285); threshold (0.6359, 0)
- C12: OK; measure (0.06198, 3.343); threshold (0.5, 40)
- C13: OK; measure (1.561, 0.8963); threshold 0
- C14: OK; measure 0.1821; threshold 0.04
- C15: OK; measure not applicable (hedged); threshold None
- C16: FAIL; measure None; threshold 0.6
- C2: OK; measure 1.272; threshold 0.5
- C3: OK; measure 2.497; threshold 2
- C4: OK; measure 1.189; threshold 0
- C10: OK; measure 0.009198; threshold 0.05

### R0207 (t-ecart {L_jours: 80, zs_saturation: 0.25})
- C1: FAIL; measure 1.016e-09; threshold 0.95
- C5: FAIL; measure {2020: 1.486, 2021: 3.302, 2022: -2.412, 2023: 1.441, 2024: 1.585, 2025: 0.2159}; threshold {sharpe_min: -1, positives_min: 4}
- C6: FAIL; measure 0.2082; threshold 0.2
- C7: OK; measure 1; threshold {min_neighbors_share: 0.75, ratio: 0.6, min_neighbor_sharpe: 0.5}
- C8: FAIL; measure (1.95, 0.1427); threshold (2, 0.3)
- C9: OK; measure 1.943e-16; threshold {random_cuts: 20, fixed_cuts: 3, not_full_share_min: 0.4, tolerance: 1e-09}
- C11: FAIL; measure (0.5296, -0.05936); threshold (0.6505, 0)
- C12: OK; measure (0.06279, 3.326); threshold (0.5, 40)
- C13: OK; measure (1.613, 0.8868); threshold 0
- C14: OK; measure 0.1822; threshold 0.04
- C15: OK; measure not applicable (hedged); threshold None
- C16: FAIL; measure None; threshold 0.6
- C2: OK; measure 1.301; threshold 0.5
- C3: OK; measure 2.542; threshold 2
- C4: OK; measure 1.215; threshold 0
- C10: OK; measure 0.008798; threshold 0.05

### R0208 (t-ecart {L_jours: 80, zs_saturation: 0.4})
- C1: FAIL; measure 1.44e-09; threshold 0.95
- C5: FAIL; measure {2020: 1.554, 2021: 3.332, 2022: -2.339, 2023: 1.537, 2024: 1.566, 2025: 0.1863}; threshold {sharpe_min: -1, positives_min: 4}
- C6: OK; measure 0.1959; threshold 0.2
- C7: OK; measure 1; threshold {min_neighbors_share: 0.75, ratio: 0.6, min_neighbor_sharpe: 0.5}
- C8: OK; measure (2.008, 0.1404); threshold (2, 0.3)
- C9: OK; measure 1.874e-16; threshold {random_cuts: 20, fixed_cuts: 3, not_full_share_min: 0.4, tolerance: 1e-09}
- C11: FAIL; measure (0.548, -0.03946); threshold (0.6581, 0)
- C12: OK; measure (0.06217, 3.226); threshold (0.5, 40)
- C13: OK; measure (1.656, 0.8537); threshold 0
- C14: OK; measure 0.1776; threshold 0.04
- C15: OK; measure not applicable (hedged); threshold None
- C16: FAIL; measure None; threshold 0.6
- C2: OK; measure 1.316; threshold 0.5
- C3: OK; measure 2.554; threshold 2
- C4: OK; measure 1.23; threshold 0
- C10: OK; measure 0.009398; threshold 0.05

### R0209 (t-ecart {L_jours: 80, zs_saturation: 0.65})
- C1: FAIL; measure 3.03e-09; threshold 0.95
- C5: FAIL; measure {2020: 1.722, 2021: 3.425, 2022: -2.221, 2023: 1.762, 2024: 1.616, 2025: 0.1137}; threshold {sharpe_min: -1, positives_min: 4}
- C6: OK; measure 0.1798; threshold 0.2
- C7: OK; measure 1; threshold {min_neighbors_share: 0.75, ratio: 0.6, min_neighbor_sharpe: 0.5}
- C8: OK; measure (2.279, 0.1387); threshold (2, 0.3)
- C9: OK; measure 2.151e-16; threshold {random_cuts: 20, fixed_cuts: 3, not_full_share_min: 0.4, tolerance: 1e-09}
- C11: FAIL; measure (0.6145, 0.03599); threshold (0.6865, 0)
- C12: OK; measure (0.06198, 3.067); threshold (0.5, 40)
- C13: OK; measure (1.749, 0.8527); threshold 0
- C14: OK; measure 0.1769; threshold 0.04
- C15: OK; measure not applicable (hedged); threshold None
- C16: FAIL; measure None; threshold 0.6
- C2: OK; measure 1.373; threshold 0.5
- C3: OK; measure 2.639; threshold 2
- C4: OK; measure 1.283; threshold 0
- C10: OK; measure 0.008198; threshold 0.05

### R0210 (t-ecart {L_jours: 80, zs_saturation: 1})
- C1: FAIL; measure 4.27e-09; threshold 0.95
- C5: FAIL; measure {2020: 1.935, 2021: 3.457, 2022: -2.054, 2023: 1.991, 2024: 1.623, 2025: 0.02229}; threshold {sharpe_min: -1, positives_min: 4}
- C6: OK; measure 0.1737; threshold 0.2
- C7: FAIL; measure None; threshold {min_neighbors_share: 0.75, ratio: 0.6, min_neighbor_sharpe: 0.5}
- C8: OK; measure (2.458, 0.1327); threshold (2, 0.3)
- C9: OK; measure 2.637e-16; threshold {random_cuts: 20, fixed_cuts: 3, not_full_share_min: 0.4, tolerance: 1e-09}
- C11: FAIL; measure (0.669, 0.1195); threshold (0.6903, 0)
- C12: OK; measure (0.068, 2.962); threshold (0.5, 40)
- C13: OK; measure (1.785, 0.8165); threshold 0
- C14: OK; measure 0.1624; threshold 0.04
- C15: OK; measure not applicable (hedged); threshold None
- C16: FAIL; measure None; threshold 0.6
- C2: OK; measure 1.381; threshold 0.5
- C3: OK; measure 2.685; threshold 2
- C4: OK; measure 1.281; threshold 0
- C10: OK; measure 0.006999; threshold 0.05

### R0211 (t-ecart {L_jours: 130, zs_saturation: 0.15})
- C1: FAIL; measure 2.79e-10; threshold 0.95
- C5: FAIL; measure {2020: 1.446, 2021: 2.898, 2022: -3.07, 2023: 1.288, 2024: 1.566, 2025: -0.2618}; threshold {sharpe_min: -1, positives_min: 4}
- C6: FAIL; measure 0.2108; threshold 0.2
- C7: FAIL; measure None; threshold {min_neighbors_share: 0.75, ratio: 0.6, min_neighbor_sharpe: 0.5}
- C8: FAIL; measure (1.465, 0.1488); threshold (2, 0.3)
- C9: OK; measure 3.608e-16; threshold {random_cuts: 20, fixed_cuts: 3, not_full_share_min: 0.4, tolerance: 1e-09}
- C11: FAIL; measure (0.3897, -0.2144); threshold (0.5927, 0)
- C12: OK; measure (0.06295, 2.954); threshold (0.5, 40)
- C13: OK; measure (1.52, 0.718); threshold 0
- C14: OK; measure 0.1713; threshold 0.04
- C15: OK; measure not applicable (hedged); threshold None
- C16: FAIL; measure None; threshold 0.6
- C2: OK; measure 1.185; threshold 0.5
- C3: OK; measure 2.436; threshold 2
- C4: OK; measure 1.107; threshold 0
- C10: OK; measure 0.0112; threshold 0.05

### R0212 (t-ecart {L_jours: 130, zs_saturation: 0.25})
- C1: FAIL; measure 3.836e-10; threshold 0.95
- C5: FAIL; measure {2020: 1.41, 2021: 2.967, 2022: -2.998, 2023: 1.389, 2024: 1.595, 2025: -0.1874}; threshold {sharpe_min: -1, positives_min: 4}
- C6: FAIL; measure 0.2059; threshold 0.2
- C7: OK; measure 1; threshold {min_neighbors_share: 0.75, ratio: 0.6, min_neighbor_sharpe: 0.5}
- C8: FAIL; measure (1.527, 0.1476); threshold (2, 0.3)
- C9: OK; measure 2.429e-16; threshold {random_cuts: 20, fixed_cuts: 3, not_full_share_min: 0.4, tolerance: 1e-09}
- C11: FAIL; measure (0.4083, -0.1898); threshold (0.6024, 0)
- C12: OK; measure (0.063, 2.928); threshold (0.5, 40)
- C13: OK; measure (1.527, 0.7616); threshold 0
- C14: OK; measure 0.1709; threshold 0.04
- C15: OK; measure not applicable (hedged); threshold None
- C16: FAIL; measure None; threshold 0.6
- C2: OK; measure 1.205; threshold 0.5
- C3: OK; measure 2.452; threshold 2
- C4: OK; measure 1.125; threshold 0
- C10: OK; measure 0.0112; threshold 0.05

### R0213 (t-ecart {L_jours: 130, zs_saturation: 0.4})
- C1: FAIL; measure 5.752e-10; threshold 0.95
- C5: FAIL; measure {2020: 1.421, 2021: 3.078, 2022: -2.873, 2023: 1.558, 2024: 1.582, 2025: -0.1446}; threshold {sharpe_min: -1, positives_min: 4}
- C6: OK; measure 0.1987; threshold 0.2
- C7: OK; measure 1; threshold {min_neighbors_share: 0.75, ratio: 0.6, min_neighbor_sharpe: 0.5}
- C8: FAIL; measure (1.599, 0.1445); threshold (2, 0.3)
- C9: OK; measure 1.735e-16; threshold {random_cuts: 20, fixed_cuts: 3, not_full_share_min: 0.4, tolerance: 1e-09}
- C11: FAIL; measure (0.4419, -0.1489); threshold (0.6144, 0)
- C12: OK; measure (0.06399, 2.905); threshold (0.5, 40)
- C13: OK; measure (1.555, 0.7807); threshold 0
- C14: OK; measure 0.1677; threshold 0.04
- C15: OK; measure not applicable (hedged); threshold None
- C16: FAIL; measure None; threshold 0.6
- C2: OK; measure 1.229; threshold 0.5
- C3: OK; measure 2.463; threshold 2
- C4: OK; measure 1.146; threshold 0
- C10: OK; measure 0.0118; threshold 0.05

### R0214 (t-ecart {L_jours: 130, zs_saturation: 0.65})
- C1: FAIL; measure 8.089e-10; threshold 0.95
- C5: FAIL; measure {2020: 1.582, 2021: 3.209, 2022: -2.582, 2023: 1.755, 2024: 1.51, 2025: -0.1102}; threshold {sharpe_min: -1, positives_min: 4}
- C6: OK; measure 0.1881; threshold 0.2
- C7: OK; measure 1; threshold {min_neighbors_share: 0.75, ratio: 0.6, min_neighbor_sharpe: 0.5}
- C8: FAIL; measure (1.715, 0.1386); threshold (2, 0.3)
- C9: OK; measure 2.984e-16; threshold {random_cuts: 20, fixed_cuts: 3, not_full_share_min: 0.4, tolerance: 1e-09}
- C11: FAIL; measure (0.4939, -0.0772); threshold (0.6301, 0)
- C12: OK; measure (0.06737, 2.84); threshold (0.5, 40)
- C13: OK; measure (1.633, 0.7374); threshold 0
- C14: OK; measure 0.1597; threshold 0.04
- C15: OK; measure not applicable (hedged); threshold None
- C16: FAIL; measure None; threshold 0.6
- C2: OK; measure 1.26; threshold 0.5
- C3: OK; measure 2.478; threshold 2
- C4: OK; measure 1.17; threshold 0
- C10: OK; measure 0.0116; threshold 0.05

### R0215 (t-ecart {L_jours: 130, zs_saturation: 1})
- C1: FAIL; measure 2.011e-09; threshold 0.95
- C5: FAIL; measure {2020: 1.914, 2021: 3.369, 2022: -2.313, 2023: 1.987, 2024: 1.535, 2025: -0.1085}; threshold {sharpe_min: -1, positives_min: 4}
- C6: OK; measure 0.1806; threshold 0.2
- C7: FAIL; measure None; threshold {min_neighbors_share: 0.75, ratio: 0.6, min_neighbor_sharpe: 0.5}
- C8: OK; measure (2.108, 0.1316); threshold (2, 0.3)
- C9: OK; measure 2.151e-16; threshold {random_cuts: 20, fixed_cuts: 3, not_full_share_min: 0.4, tolerance: 1e-09}
- C11: FAIL; measure (0.5985, 0.04658); threshold (0.6645, 0)
- C12: OK; measure (0.06996, 2.768); threshold (0.5, 40)
- C13: OK; measure (1.756, 0.7265); threshold 0
- C14: OK; measure 0.1542; threshold 0.04
- C15: OK; measure not applicable (hedged); threshold None
- C16: FAIL; measure None; threshold 0.6
- C2: OK; measure 1.329; threshold 0.5
- C3: OK; measure 2.604; threshold 2
- C4: OK; measure 1.23; threshold 0
- C10: OK; measure 0.008198; threshold 0.05

### R0216 (t-ecart {L_jours: 210, zs_saturation: 0.15})
- C1: FAIL; measure 2.293e-11; threshold 0.95
- C5: FAIL; measure {2020: 1.388, 2021: 2.569, 2022: -2.842, 2023: 1.404, 2024: 1.209, 2025: -0.6034}; threshold {sharpe_min: -1, positives_min: 4}
- C6: FAIL; measure 0.2062; threshold 0.2
- C7: FAIL; measure None; threshold {min_neighbors_share: 0.75, ratio: 0.6, min_neighbor_sharpe: 0.5}
- C8: FAIL; measure (0.8448, 0.1491); threshold (2, 0.3)
- C9: OK; measure 3.192e-16; threshold {random_cuts: 20, fixed_cuts: 3, not_full_share_min: 0.4, tolerance: 1e-09}
- C11: FAIL; measure (0.2043, -0.3402); threshold (0.5089, 0)
- C12: OK; measure (0.07176, 2.813); threshold (0.5, 40)
- C13: OK; measure (1.405, 0.4527); threshold 0
- C14: OK; measure 0.1423; threshold 0.04
- C15: OK; measure not applicable (hedged); threshold None
- C16: FAIL; measure None; threshold 0.6
- C2: OK; measure 1.018; threshold 0.5
- C3: OK; measure 2.281; threshold 2
- C4: OK; measure 0.9401; threshold 0
- C10: OK; measure 0.0148; threshold 0.05

### R0217 (t-ecart {L_jours: 210, zs_saturation: 0.25})
- C1: FAIL; measure 2.592e-11; threshold 0.95
- C5: FAIL; measure {2020: 1.476, 2021: 2.548, 2022: -2.985, 2023: 1.573, 2024: 1.215, 2025: -0.6035}; threshold {sharpe_min: -1, positives_min: 4}
- C6: FAIL; measure 0.2071; threshold 0.2
- C7: FAIL; measure None; threshold {min_neighbors_share: 0.75, ratio: 0.6, min_neighbor_sharpe: 0.5}
- C8: FAIL; measure (0.891, 0.1469); threshold (2, 0.3)
- C9: OK; measure 2.151e-16; threshold {random_cuts: 20, fixed_cuts: 3, not_full_share_min: 0.4, tolerance: 1e-09}
- C11: FAIL; measure (0.2195, -0.3265); threshold (0.5158, 0)
- C12: OK; measure (0.07314, 2.812); threshold (0.5, 40)
- C13: OK; measure (1.417, 0.4708); threshold 0
- C14: OK; measure 0.1414; threshold 0.04
- C15: OK; measure not applicable (hedged); threshold None
- C16: FAIL; measure None; threshold 0.6
- C2: OK; measure 1.032; threshold 0.5
- C3: OK; measure 2.306; threshold 2
- C4: OK; measure 0.9511; threshold 0
- C10: OK; measure 0.0144; threshold 0.05

### R0218 (t-ecart {L_jours: 210, zs_saturation: 0.4})
- C1: FAIL; measure 4.856e-11; threshold 0.95
- C5: FAIL; measure {2020: 1.614, 2021: 2.574, 2022: -3.06, 2023: 1.717, 2024: 1.266, 2025: -0.5382}; threshold {sharpe_min: -1, positives_min: 4}
- C6: FAIL; measure 0.2025; threshold 0.2
- C7: FAIL; measure None; threshold {min_neighbors_share: 0.75, ratio: 0.6, min_neighbor_sharpe: 0.5}
- C8: FAIL; measure (1.04, 0.1428); threshold (2, 0.3)
- C9: OK; measure 1.735e-16; threshold {random_cuts: 20, fixed_cuts: 3, not_full_share_min: 0.4, tolerance: 1e-09}
- C11: FAIL; measure (0.2688, -0.2753); threshold (0.5363, 0)
- C12: OK; measure (0.07377, 2.779); threshold (0.5, 40)
- C13: OK; measure (1.448, 0.5303); threshold 0
- C14: OK; measure 0.1418; threshold 0.04
- C15: OK; measure not applicable (hedged); threshold None
- C16: FAIL; measure None; threshold 0.6
- C2: OK; measure 1.073; threshold 0.5
- C3: OK; measure 2.366; threshold 2
- C4: OK; measure 0.9882; threshold 0
- C10: OK; measure 0.0126; threshold 0.05

### R0219 (t-ecart {L_jours: 210, zs_saturation: 0.65})
- C1: FAIL; measure 1.699e-10; threshold 0.95
- C5: FAIL; measure {2020: 1.854, 2021: 2.762, 2022: -2.88, 2023: 1.816, 2024: 1.418, 2025: -0.4581}; threshold {sharpe_min: -1, positives_min: 4}
- C6: OK; measure 0.1836; threshold 0.2
- C7: FAIL; measure None; threshold {min_neighbors_share: 0.75, ratio: 0.6, min_neighbor_sharpe: 0.5}
- C8: FAIL; measure (1.301, 0.1354); threshold (2, 0.3)
- C9: OK; measure 1.596e-16; threshold {random_cuts: 20, fixed_cuts: 3, not_full_share_min: 0.4, tolerance: 1e-09}
- C11: FAIL; measure (0.3723, -0.1634); threshold (0.5708, 0)
- C12: OK; measure (0.07557, 2.736); threshold (0.5, 40)
- C13: OK; measure (1.537, 0.5783); threshold 0
- C14: OK; measure 0.1391; threshold 0.04
- C15: OK; measure not applicable (hedged); threshold None
- C16: FAIL; measure None; threshold 0.6
- C2: OK; measure 1.142; threshold 0.5
- C3: OK; measure 2.458; threshold 2
- C4: OK; measure 1.05; threshold 0
- C10: OK; measure 0.009198; threshold 0.05

### R0220 (t-ecart {L_jours: 210, zs_saturation: 1})
- C1: FAIL; measure 4.699e-10; threshold 0.95
- C5: FAIL; measure {2020: 2.085, 2021: 2.96, 2022: -2.471, 2023: 1.98, 2024: 1.543, 2025: -0.3673}; threshold {sharpe_min: -1, positives_min: 4}
- C6: OK; measure 0.1732; threshold 0.2
- C7: FAIL; measure None; threshold {min_neighbors_share: 0.75, ratio: 0.6, min_neighbor_sharpe: 0.5}
- C8: FAIL; measure (1.674, 0.1284); threshold (2, 0.3)
- C9: OK; measure 2.567e-16; threshold {random_cuts: 20, fixed_cuts: 3, not_full_share_min: 0.4, tolerance: 1e-09}
- C11: FAIL; measure (0.4727, -0.03085); threshold (0.6046, 0)
- C12: OK; measure (0.07673, 2.65); threshold (0.5, 40)
- C13: OK; measure (1.629, 0.6191); threshold 0
- C14: OK; measure 0.1346; threshold 0.04
- C15: OK; measure not applicable (hedged); threshold None
- C16: FAIL; measure None; threshold 0.6
- C2: OK; measure 1.209; threshold 0.5
- C3: OK; measure 2.561; threshold 2
- C4: OK; measure 1.109; threshold 0
- C10: OK; measure 0.006599; threshold 0.05

## Selection

No candidate: outcome B if no other wave is decided.
