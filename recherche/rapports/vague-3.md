# Vague 3

Document de l'orchestrateur et du propriétaire : il contient des chiffres et ne va à aucun agent. Les agents ne reçoivent que `vague-3-statuts.json`.

Essais de grille : 100 ; lignes supplémentaires (arène, contrôle) : 0 ; dont relues du journal sans relance (reprise) : 0 ; N réel dans le journal : 220 ; N du DSR : 726.
Meilleur DSR : 0.001438. Règle d'arrêt déclenchée : oui.

## Tous les essais

| id | famille | paramètres | code | Sharpe net | portes en échec | passe |
|---|---|---|---|---|---|---|
| R0121 | p-levier-accelere | {fenetre_long: 20, h_bas: 0.3} | OK | 1.115 | C1, C6, C7, C8, C11, C16 | non |
| R0122 | p-levier-accelere | {fenetre_long: 20, h_bas: 0.39} | OK | 1.099 | C1, C6, C7, C8, C11, C16 | non |
| R0123 | p-levier-accelere | {fenetre_long: 20, h_bas: 0.5} | OK | 1.171 | C1, C6, C7, C8, C11, C16 | non |
| R0124 | p-levier-accelere | {fenetre_long: 20, h_bas: 0.65} | OK | 1.314 | C1, C6, C7, C11, C16 | non |
| R0125 | p-levier-accelere | {fenetre_long: 20, h_bas: 0.84} | OK | 1.425 | C1, C6, C7, C11, C16 | non |
| R0126 | p-levier-accelere | {fenetre_long: 32, h_bas: 0.3} | OK | 0.9314 | C1, C6, C7, C8, C11, C16 | non |
| R0127 | p-levier-accelere | {fenetre_long: 32, h_bas: 0.39} | OK | 0.9938 | C1, C6, C8, C11, C16 | non |
| R0128 | p-levier-accelere | {fenetre_long: 32, h_bas: 0.5} | OK | 1.043 | C1, C6, C8, C11, C16 | non |
| R0129 | p-levier-accelere | {fenetre_long: 32, h_bas: 0.65} | OK | 1.152 | C1, C6, C8, C11, C16 | non |
| R0130 | p-levier-accelere | {fenetre_long: 32, h_bas: 0.84} | OK | 1.333 | C1, C6, C7, C8, C11, C16 | non |
| R0131 | p-levier-accelere | {fenetre_long: 50, h_bas: 0.3} | OK | 1.041 | C1, C6, C7, C8, C11, C16 | non |
| R0132 | p-levier-accelere | {fenetre_long: 50, h_bas: 0.39} | OK | 1.057 | C1, C6, C8, C11, C16 | non |
| R0133 | p-levier-accelere | {fenetre_long: 50, h_bas: 0.5} | OK | 1.121 | C1, C6, C8, C11, C16 | non |
| R0134 | p-levier-accelere | {fenetre_long: 50, h_bas: 0.65} | OK | 1.216 | C1, C6, C8, C11, C16 | non |
| R0135 | p-levier-accelere | {fenetre_long: 50, h_bas: 0.84} | OK | 1.364 | C1, C6, C7, C8, C11, C16 | non |
| R0136 | p-levier-accelere | {fenetre_long: 80, h_bas: 0.3} | OK | 0.915 | C1, C6, C7, C8, C11, C16 | non |
| R0137 | p-levier-accelere | {fenetre_long: 80, h_bas: 0.39} | OK | 0.9518 | C1, C6, C8, C11, C16 | non |
| R0138 | p-levier-accelere | {fenetre_long: 80, h_bas: 0.5} | OK | 1.03 | C1, C6, C8, C11, C16 | non |
| R0139 | p-levier-accelere | {fenetre_long: 80, h_bas: 0.65} | OK | 1.208 | C1, C6, C8, C11, C16 | non |
| R0140 | p-levier-accelere | {fenetre_long: 80, h_bas: 0.84} | OK | 1.352 | C1, C6, C7, C8, C11, C16 | non |
| R0141 | p-levier-accelere | {fenetre_long: 126, h_bas: 0.3} | OK | 0.9543 | C1, C6, C7, C8, C11, C16 | non |
| R0142 | p-levier-accelere | {fenetre_long: 126, h_bas: 0.39} | OK | 1.001 | C1, C6, C7, C8, C11, C16 | non |
| R0143 | p-levier-accelere | {fenetre_long: 126, h_bas: 0.5} | OK | 1.052 | C1, C6, C7, C8, C11, C16 | non |
| R0144 | p-levier-accelere | {fenetre_long: 126, h_bas: 0.65} | OK | 1.194 | C1, C6, C7, C8, C11, C16 | non |
| R0145 | p-levier-accelere | {fenetre_long: 126, h_bas: 0.84} | OK | 1.349 | C1, C6, C7, C8, C11, C16 | non |
| R0146 | r-cible-vol-perp | {L_vol_jours: 10, sigma_cible: 0.06} | OK | 2.342 | C1, C5, C7, C16 | non |
| R0147 | r-cible-vol-perp | {L_vol_jours: 10, sigma_cible: 0.08} | OK | 1.965 | C1, C5, C7, C16 | non |
| R0148 | r-cible-vol-perp | {L_vol_jours: 10, sigma_cible: 0.11} | OK | 1.646 | C1, C5, C7, C16 | non |
| R0149 | r-cible-vol-perp | {L_vol_jours: 10, sigma_cible: 0.15} | OK | 1.427 | C1, C5, C7, C16 | non |
| R0150 | r-cible-vol-perp | {L_vol_jours: 10, sigma_cible: 0.22} | OK | 1.215 | C1, C5, C6, C7, C8, C11, C16 | non |
| R0151 | r-cible-vol-perp | {L_vol_jours: 20, sigma_cible: 0.06} | OK | 2.276 | C1, C5, C7, C16 | non |
| R0152 | r-cible-vol-perp | {L_vol_jours: 20, sigma_cible: 0.08} | OK | 1.988 | C1, C5, C16 | non |
| R0153 | r-cible-vol-perp | {L_vol_jours: 20, sigma_cible: 0.11} | OK | 1.666 | C1, C5, C16 | non |
| R0154 | r-cible-vol-perp | {L_vol_jours: 20, sigma_cible: 0.15} | OK | 1.455 | C1, C5, C16 | non |
| R0155 | r-cible-vol-perp | {L_vol_jours: 20, sigma_cible: 0.22} | OK | 1.179 | C1, C5, C6, C7, C8, C11, C16 | non |
| R0156 | r-cible-vol-perp | {L_vol_jours: 40, sigma_cible: 0.06} | OK | 2.396 | C1, C5, C7, C16 | non |
| R0157 | r-cible-vol-perp | {L_vol_jours: 40, sigma_cible: 0.08} | OK | 2.004 | C1, C5, C16 | non |
| R0158 | r-cible-vol-perp | {L_vol_jours: 40, sigma_cible: 0.11} | OK | 1.698 | C1, C5, C16 | non |
| R0159 | r-cible-vol-perp | {L_vol_jours: 40, sigma_cible: 0.15} | OK | 1.498 | C1, C5, C16 | non |
| R0160 | r-cible-vol-perp | {L_vol_jours: 40, sigma_cible: 0.22} | OK | 1.297 | C1, C5, C6, C7, C16 | non |
| R0161 | r-cible-vol-perp | {L_vol_jours: 80, sigma_cible: 0.06} | OK | 2.448 | C1, C5, C7, C16 | non |
| R0162 | r-cible-vol-perp | {L_vol_jours: 80, sigma_cible: 0.08} | OK | 2.148 | C1, C5, C16 | non |
| R0163 | r-cible-vol-perp | {L_vol_jours: 80, sigma_cible: 0.11} | OK | 1.75 | C1, C5, C16 | non |
| R0164 | r-cible-vol-perp | {L_vol_jours: 80, sigma_cible: 0.15} | OK | 1.472 | C1, C5, C16 | non |
| R0165 | r-cible-vol-perp | {L_vol_jours: 80, sigma_cible: 0.22} | OK | 1.247 | C1, C5, C6, C7, C16 | non |
| R0166 | r-cible-vol-perp | {L_vol_jours: 160, sigma_cible: 0.06} | OK | 2.477 | C1, C5, C7, C16 | non |
| R0167 | r-cible-vol-perp | {L_vol_jours: 160, sigma_cible: 0.08} | OK | 2.137 | C1, C5, C7, C16 | non |
| R0168 | r-cible-vol-perp | {L_vol_jours: 160, sigma_cible: 0.11} | OK | 1.808 | C1, C5, C7, C16 | non |
| R0169 | r-cible-vol-perp | {L_vol_jours: 160, sigma_cible: 0.15} | OK | 1.488 | C1, C5, C7, C16 | non |
| R0170 | r-cible-vol-perp | {L_vol_jours: 160, sigma_cible: 0.22} | OK | 1.266 | C1, C5, C7, C16 | non |
| R0171 | r-coussin-plancher | {W_jours: 7, f_plancher: 0.01} | OK | 1.86 | C1, C5, C7, C16 | non |
| R0172 | r-coussin-plancher | {W_jours: 7, f_plancher: 0.016} | OK | 1.385 | C1, C5, C7, C16 | non |
| R0173 | r-coussin-plancher | {W_jours: 7, f_plancher: 0.025} | OK | 1.089 | C1, C5, C6, C7, C8, C11, C16 | non |
| R0174 | r-coussin-plancher | {W_jours: 7, f_plancher: 0.04} | OK | 1.175 | C1, C5, C6, C7, C8, C11, C16 | non |
| R0175 | r-coussin-plancher | {W_jours: 7, f_plancher: 0.06} | OK | 1.226 | C1, C5, C6, C7, C11, C16 | non |
| R0176 | r-coussin-plancher | {W_jours: 14, f_plancher: 0.01} | OK | 1.701 | C1, C5, C7, C16 | non |
| R0177 | r-coussin-plancher | {W_jours: 14, f_plancher: 0.016} | OK | 1.523 | C1, C5, C16 | non |
| R0178 | r-coussin-plancher | {W_jours: 14, f_plancher: 0.025} | OK | 1.263 | C1, C5, C8, C11, C16 | non |
| R0179 | r-coussin-plancher | {W_jours: 14, f_plancher: 0.04} | OK | 1.195 | C1, C5, C6, C8, C11, C16 | non |
| R0180 | r-coussin-plancher | {W_jours: 14, f_plancher: 0.06} | OK | 1.21 | C1, C5, C6, C7, C11, C16 | non |
| R0181 | r-coussin-plancher | {W_jours: 28, f_plancher: 0.01} | OK | 1.908 | C1, C5, C7, C16 | non |
| R0182 | r-coussin-plancher | {W_jours: 28, f_plancher: 0.016} | OK | 1.812 | C1, C5, C16 | non |
| R0183 | r-coussin-plancher | {W_jours: 28, f_plancher: 0.025} | OK | 1.467 | C1, C5, C16 | non |
| R0184 | r-coussin-plancher | {W_jours: 28, f_plancher: 0.04} | OK | 1.196 | C1, C5, C6, C8, C11, C16 | non |
| R0185 | r-coussin-plancher | {W_jours: 28, f_plancher: 0.06} | OK | 1.216 | C1, C5, C6, C7, C11, C16 | non |
| R0186 | r-coussin-plancher | {W_jours: 56, f_plancher: 0.01} | OK | 2.186 | C1, C5, C7, C16 | non |
| R0187 | r-coussin-plancher | {W_jours: 56, f_plancher: 0.016} | OK | 2.091 | C1, C5, C16 | non |
| R0188 | r-coussin-plancher | {W_jours: 56, f_plancher: 0.025} | OK | 1.545 | C1, C5, C16 | non |
| R0189 | r-coussin-plancher | {W_jours: 56, f_plancher: 0.04} | OK | 1.351 | C1, C5, C6, C11, C16 | non |
| R0190 | r-coussin-plancher | {W_jours: 56, f_plancher: 0.06} | OK | 1.397 | C1, C6, C7, C11, C16 | non |
| R0191 | r-coussin-plancher | {W_jours: 112, f_plancher: 0.01} | OK | 2.279 | C1, C5, C7, C16 | non |
| R0192 | r-coussin-plancher | {W_jours: 112, f_plancher: 0.016} | OK | 2.108 | C1, C5, C7, C16 | non |
| R0193 | r-coussin-plancher | {W_jours: 112, f_plancher: 0.025} | OK | 1.56 | C1, C5, C7, C11, C16 | non |
| R0194 | r-coussin-plancher | {W_jours: 112, f_plancher: 0.04} | OK | 1.379 | C1, C5, C7, C11, C16 | non |
| R0195 | r-coussin-plancher | {W_jours: 112, f_plancher: 0.06} | OK | 1.255 | C1, C5, C6, C7, C8, C11, C16 | non |
| R0196 | t-ecart | {L_jours: 30, zs_saturation: 0.15} | OK | 1.544 | C1, C5, C7, C16 | non |
| R0197 | t-ecart | {L_jours: 30, zs_saturation: 0.25} | OK | 1.591 | C1, C5, C7, C16 | non |
| R0198 | t-ecart | {L_jours: 30, zs_saturation: 0.4} | OK | 1.632 | C1, C5, C7, C16 | non |
| R0199 | t-ecart | {L_jours: 30, zs_saturation: 0.65} | OK | 1.622 | C1, C5, C7, C16 | non |
| R0200 | t-ecart | {L_jours: 30, zs_saturation: 1} | OK | 1.588 | C1, C5, C7, C16 | non |
| R0201 | t-ecart | {L_jours: 50, zs_saturation: 0.15} | OK | 1.512 | C1, C5, C7, C16 | non |
| R0202 | t-ecart | {L_jours: 50, zs_saturation: 0.25} | OK | 1.52 | C1, C5, C16 | non |
| R0203 | t-ecart | {L_jours: 50, zs_saturation: 0.4} | OK | 1.509 | C1, C5, C16 | non |
| R0204 | t-ecart | {L_jours: 50, zs_saturation: 0.65} | OK | 1.541 | C1, C5, C16 | non |
| R0205 | t-ecart | {L_jours: 50, zs_saturation: 1} | OK | 1.503 | C1, C5, C7, C16 | non |
| R0206 | t-ecart | {L_jours: 80, zs_saturation: 0.15} | OK | 1.272 | C1, C5, C6, C7, C8, C11, C16 | non |
| R0207 | t-ecart | {L_jours: 80, zs_saturation: 0.25} | OK | 1.301 | C1, C5, C6, C8, C11, C16 | non |
| R0208 | t-ecart | {L_jours: 80, zs_saturation: 0.4} | OK | 1.316 | C1, C5, C11, C16 | non |
| R0209 | t-ecart | {L_jours: 80, zs_saturation: 0.65} | OK | 1.373 | C1, C5, C11, C16 | non |
| R0210 | t-ecart | {L_jours: 80, zs_saturation: 1} | OK | 1.381 | C1, C5, C7, C11, C16 | non |
| R0211 | t-ecart | {L_jours: 130, zs_saturation: 0.15} | OK | 1.185 | C1, C5, C6, C7, C8, C11, C16 | non |
| R0212 | t-ecart | {L_jours: 130, zs_saturation: 0.25} | OK | 1.205 | C1, C5, C6, C8, C11, C16 | non |
| R0213 | t-ecart | {L_jours: 130, zs_saturation: 0.4} | OK | 1.229 | C1, C5, C8, C11, C16 | non |
| R0214 | t-ecart | {L_jours: 130, zs_saturation: 0.65} | OK | 1.26 | C1, C5, C8, C11, C16 | non |
| R0215 | t-ecart | {L_jours: 130, zs_saturation: 1} | OK | 1.329 | C1, C5, C7, C11, C16 | non |
| R0216 | t-ecart | {L_jours: 210, zs_saturation: 0.15} | OK | 1.018 | C1, C5, C6, C7, C8, C11, C16 | non |
| R0217 | t-ecart | {L_jours: 210, zs_saturation: 0.25} | OK | 1.032 | C1, C5, C6, C7, C8, C11, C16 | non |
| R0218 | t-ecart | {L_jours: 210, zs_saturation: 0.4} | OK | 1.073 | C1, C5, C6, C7, C8, C11, C16 | non |
| R0219 | t-ecart | {L_jours: 210, zs_saturation: 0.65} | OK | 1.142 | C1, C5, C7, C8, C11, C16 | non |
| R0220 | t-ecart | {L_jours: 210, zs_saturation: 1} | OK | 1.209 | C1, C5, C7, C8, C11, C16 | non |

## Verdicts détaillés

C16 : mesure = (part, positifs, évaluables, non évaluables, taille de l'univers de contrôle) ; la part est rapportée à la taille fixe de l'univers.

### R0121 (p-levier-accelere {fenetre_long: 20, h_bas: 0.3})
- C1 : ÉCHEC ; mesure 6.505e-11 ; seuil 0.95
- C5 : OK ; mesure {2020: 2.031, 2021: 2.565, 2022: -0.7628, 2023: 1.61, 2024: 1.283, 2025: 0.4045} ; seuil {sharpe_min: -1, positives_min: 4}
- C6 : ÉCHEC ; mesure 0.371 ; seuil 0.2
- C7 : ÉCHEC ; mesure None ; seuil {part_voisins_min: 0.75, ratio: 0.6, sharpe_voisin_min: 0.5}
- C8 : ÉCHEC ; mesure (1.352, 0.3511) ; seuil (2, 0.3)
- C9 : OK ; mesure 1.388e-16 ; seuil {aleatoires: 20, fixes: 3, part_non_pleine_min: 0.4, tolerance: 1e-09}
- C11 : ÉCHEC ; mesure (0.3276, -0.2534) ; seuil (0.5574, 0)
- C12 : OK ; mesure (0.04459, 7.475) ; seuil (0.5, 40)
- C13 : OK ; mesure (1.566, 0.3759) ; seuil 0
- C14 : OK ; mesure 0.3387 ; seuil 0.04
- C15 : OK ; mesure non applicable (couvert) ; seuil None
- C16 : ÉCHEC ; mesure None ; seuil 0.6
- C2 : OK ; mesure 1.115 ; seuil 0.5
- C3 : OK ; mesure 2.785 ; seuil 2
- C4 : OK ; mesure 1.063 ; seuil 0
- C10 : OK ; mesure 0.002999 ; seuil 0.05

### R0122 (p-levier-accelere {fenetre_long: 20, h_bas: 0.39})
- C1 : ÉCHEC ; mesure 5.227e-11 ; seuil 0.95
- C5 : OK ; mesure {2020: 2.022, 2021: 2.602, 2022: -0.9282, 2023: 1.724, 2024: 1.373, 2025: 0.3192} ; seuil {sharpe_min: -1, positives_min: 4}
- C6 : ÉCHEC ; mesure 0.3602 ; seuil 0.2
- C7 : ÉCHEC ; mesure None ; seuil {part_voisins_min: 0.75, ratio: 0.6, sharpe_voisin_min: 0.5}
- C8 : ÉCHEC ; mesure (1.266, 0.316) ; seuil (2, 0.3)
- C9 : OK ; mesure 2.22e-16 ; seuil {aleatoires: 20, fixes: 3, part_non_pleine_min: 0.4, tolerance: 1e-09}
- C11 : ÉCHEC ; mesure (0.3229, -0.2489) ; seuil (0.5497, 0)
- C12 : OK ; mesure (0.04562, 6.545) ; seuil (0.5, 40)
- C13 : OK ; mesure (1.546, 0.3492) ; seuil 0
- C14 : OK ; mesure 0.3024 ; seuil 0.04
- C15 : OK ; mesure non applicable (couvert) ; seuil None
- C16 : ÉCHEC ; mesure None ; seuil 0.6
- C2 : OK ; mesure 1.099 ; seuil 0.5
- C3 : OK ; mesure 2.676 ; seuil 2
- C4 : OK ; mesure 1.047 ; seuil 0
- C10 : OK ; mesure 0.003999 ; seuil 0.05

### R0123 (p-levier-accelere {fenetre_long: 20, h_bas: 0.5})
- C1 : ÉCHEC ; mesure 2.058e-10 ; seuil 0.95
- C5 : OK ; mesure {2020: 2.077, 2021: 2.585, 2022: -0.8055, 2023: 1.821, 2024: 1.576, 2025: 0.2015} ; seuil {sharpe_min: -1, positives_min: 4}
- C6 : ÉCHEC ; mesure 0.2906 ; seuil 0.2
- C7 : ÉCHEC ; mesure None ; seuil {part_voisins_min: 0.75, ratio: 0.6, sharpe_voisin_min: 0.5}
- C8 : ÉCHEC ; mesure (1.568, 0.2765) ; seuil (2, 0.3)
- C9 : OK ; mesure 9.714e-17 ; seuil {aleatoires: 20, fixes: 3, part_non_pleine_min: 0.4, tolerance: 1e-09}
- C11 : ÉCHEC ; mesure (0.3943, -0.1719) ; seuil (0.5853, 0)
- C12 : OK ; mesure (0.04359, 5.498) ; seuil (0.5, 40)
- C13 : OK ; mesure (1.614, 0.4205) ; seuil 0
- C14 : OK ; mesure 0.2918 ; seuil 0.04
- C15 : OK ; mesure non applicable (couvert) ; seuil None
- C16 : ÉCHEC ; mesure None ; seuil 0.6
- C2 : OK ; mesure 1.171 ; seuil 0.5
- C3 : OK ; mesure 2.772 ; seuil 2
- C4 : OK ; mesure 1.117 ; seuil 0
- C10 : OK ; mesure 0.003199 ; seuil 0.05

### R0124 (p-levier-accelere {fenetre_long: 20, h_bas: 0.65})
- C1 : ÉCHEC ; mesure 1.658e-09 ; seuil 0.95
- C5 : OK ; mesure {2020: 2.168, 2021: 2.95, 2022: -0.8674, 2023: 1.673, 2024: 1.497, 2025: 0.3769} ; seuil {sharpe_min: -1, positives_min: 4}
- C6 : ÉCHEC ; mesure 0.2433 ; seuil 0.2
- C7 : ÉCHEC ; mesure None ; seuil {part_voisins_min: 0.75, ratio: 0.6, sharpe_voisin_min: 0.5}
- C8 : OK ; mesure (2.042, 0.2191) ; seuil (2, 0.3)
- C9 : OK ; mesure 1.18e-16 ; seuil {aleatoires: 20, fixes: 3, part_non_pleine_min: 0.4, tolerance: 1e-09}
- C11 : ÉCHEC ; mesure (0.5188, -0.09976) ; seuil (0.6571, 0)
- C12 : OK ; mesure (0.04339, 4.298) ; seuil (0.5, 40)
- C13 : OK ; mesure (1.794, 0.4976) ; seuil 0
- C14 : OK ; mesure 0.2735 ; seuil 0.04
- C15 : OK ; mesure non applicable (couvert) ; seuil None
- C16 : ÉCHEC ; mesure None ; seuil 0.6
- C2 : OK ; mesure 1.314 ; seuil 0.5
- C3 : OK ; mesure 2.903 ; seuil 2
- C4 : OK ; mesure 1.255 ; seuil 0
- C10 : OK ; mesure 0.0024 ; seuil 0.05

### R0125 (p-levier-accelere {fenetre_long: 20, h_bas: 0.84})
- C1 : ÉCHEC ; mesure 1.078e-08 ; seuil 0.95
- C5 : OK ; mesure {2020: 2.159, 2021: 3.106, 2022: -0.8191, 2023: 2.037, 2024: 2.365, 2025: 0.4404} ; seuil {sharpe_min: -1, positives_min: 4}
- C6 : ÉCHEC ; mesure 0.2039 ; seuil 0.2
- C7 : ÉCHEC ; mesure None ; seuil {part_voisins_min: 0.75, ratio: 0.6, sharpe_voisin_min: 0.5}
- C8 : OK ; mesure (2.196, 0.1537) ; seuil (2, 0.3)
- C9 : OK ; mesure 1.318e-16 ; seuil {aleatoires: 20, fixes: 3, part_non_pleine_min: 0.4, tolerance: 1e-09}
- C11 : ÉCHEC ; mesure (0.6188, -0.05888) ; seuil (0.7123, 0)
- C12 : OK ; mesure (0.04695, 3.436) ; seuil (0.5, 40)
- C13 : OK ; mesure (1.912, 0.8153) ; seuil 0
- C14 : OK ; mesure 0.2333 ; seuil 0.04
- C15 : OK ; mesure non applicable (couvert) ; seuil None
- C16 : ÉCHEC ; mesure None ; seuil 0.6
- C2 : OK ; mesure 1.425 ; seuil 0.5
- C3 : OK ; mesure 2.913 ; seuil 2
- C4 : OK ; mesure 1.355 ; seuil 0
- C10 : OK ; mesure 0.002799 ; seuil 0.05

### R0126 (p-levier-accelere {fenetre_long: 32, h_bas: 0.3})
- C1 : ÉCHEC ; mesure 5.739e-12 ; seuil 0.95
- C5 : OK ; mesure {2020: 1.648, 2021: 2.275, 2022: -0.8752, 2023: 1.805, 2024: 1.055, 2025: 0.3766} ; seuil {sharpe_min: -1, positives_min: 4}
- C6 : ÉCHEC ; mesure 0.3969 ; seuil 0.2
- C7 : ÉCHEC ; mesure None ; seuil {part_voisins_min: 0.75, ratio: 0.6, sharpe_voisin_min: 0.5}
- C8 : ÉCHEC ; mesure (0.2606, 0.3626) ; seuil (2, 0.3)
- C9 : OK ; mesure 1.943e-16 ; seuil {aleatoires: 20, fixes: 3, part_non_pleine_min: 0.4, tolerance: 1e-09}
- C11 : ÉCHEC ; mesure (0.1375, -0.4253) ; seuil (0.5, 0)
- C12 : OK ; mesure (0.04623, 6.182) ; seuil (0.5, 40)
- C13 : OK ; mesure (1.297, 0.3283) ; seuil 0
- C14 : OK ; mesure 0.2744 ; seuil 0.04
- C15 : OK ; mesure non applicable (couvert) ; seuil None
- C16 : ÉCHEC ; mesure None ; seuil 0.6
- C2 : OK ; mesure 0.9314 ; seuil 0.5
- C3 : OK ; mesure 2.31 ; seuil 2
- C4 : OK ; mesure 0.8861 ; seuil 0
- C10 : OK ; mesure 0.0118 ; seuil 0.05

### R0127 (p-levier-accelere {fenetre_long: 32, h_bas: 0.39})
- C1 : ÉCHEC ; mesure 3.491e-11 ; seuil 0.95
- C5 : OK ; mesure {2020: 1.581, 2021: 2.44, 2022: -0.7905, 2023: 1.894, 2024: 1.231, 2025: 0.3536} ; seuil {sharpe_min: -1, positives_min: 4}
- C6 : ÉCHEC ; mesure 0.3842 ; seuil 0.2
- C7 : OK ; mesure 1 ; seuil {part_voisins_min: 0.75, ratio: 0.6, sharpe_voisin_min: 0.5}
- C8 : ÉCHEC ; mesure (0.6037, 0.3228) ; seuil (2, 0.3)
- C9 : OK ; mesure 1.318e-16 ; seuil {aleatoires: 20, fixes: 3, part_non_pleine_min: 0.4, tolerance: 1e-09}
- C11 : ÉCHEC ; mesure (0.2254, -0.3299) ; seuil (0.5, 0)
- C12 : OK ; mesure (0.04413, 5.416) ; seuil (0.5, 40)
- C13 : OK ; mesure (1.364, 0.381) ; seuil 0
- C14 : OK ; mesure 0.2721 ; seuil 0.04
- C15 : OK ; mesure non applicable (couvert) ; seuil None
- C16 : ÉCHEC ; mesure None ; seuil 0.6
- C2 : OK ; mesure 0.9938 ; seuil 0.5
- C3 : OK ; mesure 2.423 ; seuil 2
- C4 : OK ; mesure 0.9479 ; seuil 0
- C10 : OK ; mesure 0.009198 ; seuil 0.05

### R0128 (p-levier-accelere {fenetre_long: 32, h_bas: 0.5})
- C1 : ÉCHEC ; mesure 8.682e-11 ; seuil 0.95
- C5 : OK ; mesure {2020: 1.628, 2021: 2.512, 2022: -0.9192, 2023: 1.918, 2024: 1.398, 2025: 0.3698} ; seuil {sharpe_min: -1, positives_min: 4}
- C6 : ÉCHEC ; mesure 0.344 ; seuil 0.2
- C7 : OK ; mesure 1 ; seuil {part_voisins_min: 0.75, ratio: 0.6, sharpe_voisin_min: 0.5}
- C8 : ÉCHEC ; mesure (0.8404, 0.2808) ; seuil (2, 0.3)
- C9 : OK ; mesure 1.804e-16 ; seuil {aleatoires: 20, fixes: 3, part_non_pleine_min: 0.4, tolerance: 1e-09}
- C11 : ÉCHEC ; mesure (0.283, -0.2922) ; seuil (0.5217, 0)
- C12 : OK ; mesure (0.04458, 4.682) ; seuil (0.5, 40)
- C13 : OK ; mesure (1.399, 0.4736) ; seuil 0
- C14 : OK ; mesure 0.257 ; seuil 0.04
- C15 : OK ; mesure non applicable (couvert) ; seuil None
- C16 : ÉCHEC ; mesure None ; seuil 0.6
- C2 : OK ; mesure 1.043 ; seuil 0.5
- C3 : OK ; mesure 2.473 ; seuil 2
- C4 : OK ; mesure 0.9945 ; seuil 0
- C10 : OK ; mesure 0.007199 ; seuil 0.05

### R0129 (p-levier-accelere {fenetre_long: 32, h_bas: 0.65})
- C1 : ÉCHEC ; mesure 4.52e-10 ; seuil 0.95
- C5 : OK ; mesure {2020: 1.804, 2021: 2.763, 2022: -0.9126, 2023: 1.971, 2024: 1.396, 2025: 0.2417} ; seuil {sharpe_min: -1, positives_min: 4}
- C6 : ÉCHEC ; mesure 0.2883 ; seuil 0.2
- C7 : OK ; mesure 1 ; seuil {part_voisins_min: 0.75, ratio: 0.6, sharpe_voisin_min: 0.5}
- C8 : ÉCHEC ; mesure (1.282, 0.2211) ; seuil (2, 0.3)
- C9 : OK ; mesure 1.249e-16 ; seuil {aleatoires: 20, fixes: 3, part_non_pleine_min: 0.4, tolerance: 1e-09}
- C11 : ÉCHEC ; mesure (0.3657, -0.226) ; seuil (0.5758, 0)
- C12 : OK ; mesure (0.04722, 4.01) ; seuil (0.5, 40)
- C13 : OK ; mesure (1.577, 0.4156) ; seuil 0
- C14 : OK ; mesure 0.2382 ; seuil 0.04
- C15 : OK ; mesure non applicable (couvert) ; seuil None
- C16 : ÉCHEC ; mesure None ; seuil 0.6
- C2 : OK ; mesure 1.152 ; seuil 0.5
- C3 : OK ; mesure 2.576 ; seuil 2
- C4 : OK ; mesure 1.095 ; seuil 0
- C10 : OK ; mesure 0.005999 ; seuil 0.05

### R0130 (p-levier-accelere {fenetre_long: 32, h_bas: 0.84})
- C1 : ÉCHEC ; mesure 5.558e-09 ; seuil 0.95
- C5 : OK ; mesure {2020: 2.021, 2021: 2.955, 2022: -0.8248, 2023: 2.373, 2024: 2.321, 2025: 0.2942} ; seuil {sharpe_min: -1, positives_min: 4}
- C6 : ÉCHEC ; mesure 0.2246 ; seuil 0.2
- C7 : ÉCHEC ; mesure None ; seuil {part_voisins_min: 0.75, ratio: 0.6, sharpe_voisin_min: 0.5}
- C8 : ÉCHEC ; mesure (1.872, 0.1554) ; seuil (2, 0.3)
- C9 : OK ; mesure 9.021e-17 ; seuil {aleatoires: 20, fixes: 3, part_non_pleine_min: 0.4, tolerance: 1e-09}
- C11 : ÉCHEC ; mesure (0.5226, -0.1265) ; seuil (0.6667, 0)
- C12 : OK ; mesure (0.04828, 3.275) ; seuil (0.5, 40)
- C13 : OK ; mesure (1.795, 0.7332) ; seuil 0
- C14 : OK ; mesure 0.2195 ; seuil 0.04
- C15 : OK ; mesure non applicable (couvert) ; seuil None
- C16 : ÉCHEC ; mesure None ; seuil 0.6
- C2 : OK ; mesure 1.333 ; seuil 0.5
- C3 : OK ; mesure 2.757 ; seuil 2
- C4 : OK ; mesure 1.266 ; seuil 0
- C10 : OK ; mesure 0.004199 ; seuil 0.05

### R0131 (p-levier-accelere {fenetre_long: 50, h_bas: 0.3})
- C1 : ÉCHEC ; mesure 2.192e-11 ; seuil 0.95
- C5 : OK ; mesure {2020: 1.906, 2021: 2.323, 2022: -0.8073, 2023: 2.169, 2024: 0.9764, 2025: 0.415} ; seuil {sharpe_min: -1, positives_min: 4}
- C6 : ÉCHEC ; mesure 0.3883 ; seuil 0.2
- C7 : ÉCHEC ; mesure None ; seuil {part_voisins_min: 0.75, ratio: 0.6, sharpe_voisin_min: 0.5}
- C8 : ÉCHEC ; mesure (0.9101, 0.3541) ; seuil (2, 0.3)
- C9 : OK ; mesure 1.041e-16 ; seuil {aleatoires: 20, fixes: 3, part_non_pleine_min: 0.4, tolerance: 1e-09}
- C11 : ÉCHEC ; mesure (0.2663, -0.2916) ; seuil (0.5205, 0)
- C12 : OK ; mesure (0.03803, 5.208) ; seuil (0.5, 40)
- C13 : OK ; mesure (1.412, 0.4571) ; seuil 0
- C14 : OK ; mesure 0.3132 ; seuil 0.04
- C15 : OK ; mesure non applicable (couvert) ; seuil None
- C16 : ÉCHEC ; mesure None ; seuil 0.6
- C2 : OK ; mesure 1.041 ; seuil 0.5
- C3 : OK ; mesure 2.618 ; seuil 2
- C4 : OK ; mesure 0.9999 ; seuil 0
- C10 : OK ; mesure 0.004999 ; seuil 0.05

### R0132 (p-levier-accelere {fenetre_long: 50, h_bas: 0.39})
- C1 : ÉCHEC ; mesure 3.113e-11 ; seuil 0.95
- C5 : OK ; mesure {2020: 1.957, 2021: 2.313, 2022: -0.8621, 2023: 2.234, 2024: 1.052, 2025: 0.3224} ; seuil {sharpe_min: -1, positives_min: 4}
- C6 : ÉCHEC ; mesure 0.3636 ; seuil 0.2
- C7 : OK ; mesure 1 ; seuil {part_voisins_min: 0.75, ratio: 0.6, sharpe_voisin_min: 0.5}
- C8 : ÉCHEC ; mesure (1.008, 0.3167) ; seuil (2, 0.3)
- C9 : OK ; mesure 1.249e-16 ; seuil {aleatoires: 20, fixes: 3, part_non_pleine_min: 0.4, tolerance: 1e-09}
- C11 : ÉCHEC ; mesure (0.2842, -0.2855) ; seuil (0.5284, 0)
- C12 : OK ; mesure (0.04094, 4.955) ; seuil (0.5, 40)
- C13 : OK ; mesure (1.434, 0.4499) ; seuil 0
- C14 : OK ; mesure 0.2899 ; seuil 0.04
- C15 : OK ; mesure non applicable (couvert) ; seuil None
- C16 : ÉCHEC ; mesure None ; seuil 0.6
- C2 : OK ; mesure 1.057 ; seuil 0.5
- C3 : OK ; mesure 2.614 ; seuil 2
- C4 : OK ; mesure 1.011 ; seuil 0
- C10 : OK ; mesure 0.004399 ; seuil 0.05

### R0133 (p-levier-accelere {fenetre_long: 50, h_bas: 0.5})
- C1 : ÉCHEC ; mesure 9.013e-11 ; seuil 0.95
- C5 : OK ; mesure {2020: 1.936, 2021: 2.565, 2022: -0.9594, 2023: 2.095, 2024: 1.123, 2025: 0.2383} ; seuil {sharpe_min: -1, positives_min: 4}
- C6 : ÉCHEC ; mesure 0.3181 ; seuil 0.2
- C7 : OK ; mesure 1 ; seuil {part_voisins_min: 0.75, ratio: 0.6, sharpe_voisin_min: 0.5}
- C8 : ÉCHEC ; mesure (1.278, 0.2758) ; seuil (2, 0.3)
- C9 : OK ; mesure 1.804e-16 ; seuil {aleatoires: 20, fixes: 3, part_non_pleine_min: 0.4, tolerance: 1e-09}
- C11 : ÉCHEC ; mesure (0.3564, -0.2327) ; seuil (0.5605, 0)
- C12 : OK ; mesure (0.04106, 4.2) ; seuil (0.5, 40)
- C13 : OK ; mesure (1.541, 0.4132) ; seuil 0
- C14 : OK ; mesure 0.276 ; seuil 0.04
- C15 : OK ; mesure non applicable (couvert) ; seuil None
- C16 : ÉCHEC ; mesure None ; seuil 0.6
- C2 : OK ; mesure 1.121 ; seuil 0.5
- C3 : OK ; mesure 2.641 ; seuil 2
- C4 : OK ; mesure 1.073 ; seuil 0
- C10 : OK ; mesure 0.004599 ; seuil 0.05

### R0134 (p-levier-accelere {fenetre_long: 50, h_bas: 0.65})
- C1 : ÉCHEC ; mesure 6.048e-10 ; seuil 0.95
- C5 : OK ; mesure {2020: 2.098, 2021: 2.655, 2022: -0.9797, 2023: 2.262, 2024: 1.357, 2025: 0.2209} ; seuil {sharpe_min: -1, positives_min: 4}
- C6 : ÉCHEC ; mesure 0.2623 ; seuil 0.2
- C7 : OK ; mesure 1 ; seuil {part_voisins_min: 0.75, ratio: 0.6, sharpe_voisin_min: 0.5}
- C8 : ÉCHEC ; mesure (1.584, 0.2194) ; seuil (2, 0.3)
- C9 : OK ; mesure 1.388e-16 ; seuil {aleatoires: 20, fixes: 3, part_non_pleine_min: 0.4, tolerance: 1e-09}
- C11 : ÉCHEC ; mesure (0.4448, -0.152) ; seuil (0.6081, 0)
- C12 : OK ; mesure (0.04308, 3.613) ; seuil (0.5, 40)
- C13 : OK ; mesure (1.653, 0.4836) ; seuil 0
- C14 : OK ; mesure 0.2517 ; seuil 0.04
- C15 : OK ; mesure non applicable (couvert) ; seuil None
- C16 : ÉCHEC ; mesure None ; seuil 0.6
- C2 : OK ; mesure 1.216 ; seuil 0.5
- C3 : OK ; mesure 2.71 ; seuil 2
- C4 : OK ; mesure 1.162 ; seuil 0
- C10 : OK ; mesure 0.004199 ; seuil 0.05

### R0135 (p-levier-accelere {fenetre_long: 50, h_bas: 0.84})
- C1 : ÉCHEC ; mesure 5.165e-09 ; seuil 0.95
- C5 : OK ; mesure {2020: 2.135, 2021: 2.936, 2022: -0.9516, 2023: 2.651, 2024: 2.261, 2025: 0.2787} ; seuil {sharpe_min: -1, positives_min: 4}
- C6 : ÉCHEC ; mesure 0.2039 ; seuil 0.2
- C7 : ÉCHEC ; mesure None ; seuil {part_voisins_min: 0.75, ratio: 0.6, sharpe_voisin_min: 0.5}
- C8 : ÉCHEC ; mesure (1.974, 0.1539) ; seuil (2, 0.3)
- C9 : OK ; mesure 2.498e-16 ; seuil {aleatoires: 20, fixes: 3, part_non_pleine_min: 0.4, tolerance: 1e-09}
- C11 : ÉCHEC ; mesure (0.5532, -0.09983) ; seuil (0.6818, 0)
- C12 : OK ; mesure (0.04686, 3.105) ; seuil (0.5, 40)
- C13 : OK ; mesure (1.827, 0.7976) ; seuil 0
- C14 : OK ; mesure 0.2228 ; seuil 0.04
- C15 : OK ; mesure non applicable (couvert) ; seuil None
- C16 : ÉCHEC ; mesure None ; seuil 0.6
- C2 : OK ; mesure 1.364 ; seuil 0.5
- C3 : OK ; mesure 2.799 ; seuil 2
- C4 : OK ; mesure 1.297 ; seuil 0
- C10 : OK ; mesure 0.003599 ; seuil 0.05

### R0136 (p-levier-accelere {fenetre_long: 80, h_bas: 0.3})
- C1 : ÉCHEC ; mesure 2.032e-12 ; seuil 0.95
- C5 : OK ; mesure {2020: 1.976, 2021: 2.276, 2022: -0.737, 2023: 1.688, 2024: 0.683, 2025: -0.3499} ; seuil {sharpe_min: -1, positives_min: 4}
- C6 : ÉCHEC ; mesure 0.399 ; seuil 0.2
- C7 : ÉCHEC ; mesure None ; seuil {part_voisins_min: 0.75, ratio: 0.6, sharpe_voisin_min: 0.5}
- C8 : ÉCHEC ; mesure (0.2261, 0.3514) ; seuil (2, 0.3)
- C9 : OK ; mesure 1.388e-16 ; seuil {aleatoires: 20, fixes: 3, part_non_pleine_min: 0.4, tolerance: 1e-09}
- C11 : ÉCHEC ; mesure (0.136, -0.4083) ; seuil (0.5, 0)
- C12 : OK ; mesure (0.04156, 4.621) ; seuil (0.5, 40)
- C13 : OK ; mesure (1.392, 0.06276) ; seuil 0
- C14 : OK ; mesure 0.2633 ; seuil 0.04
- C15 : OK ; mesure non applicable (couvert) ; seuil None
- C16 : ÉCHEC ; mesure None ; seuil 0.6
- C2 : OK ; mesure 0.915 ; seuil 0.5
- C3 : OK ; mesure 2.34 ; seuil 2
- C4 : OK ; mesure 0.8753 ; seuil 0
- C10 : OK ; mesure 0.009598 ; seuil 0.05

### R0137 (p-levier-accelere {fenetre_long: 80, h_bas: 0.39})
- C1 : ÉCHEC ; mesure 4.385e-12 ; seuil 0.95
- C5 : OK ; mesure {2020: 2.005, 2021: 2.289, 2022: -0.8176, 2023: 1.76, 2024: 0.6526, 2025: -0.2097} ; seuil {sharpe_min: -1, positives_min: 4}
- C6 : ÉCHEC ; mesure 0.3609 ; seuil 0.2
- C7 : OK ; mesure 1 ; seuil {part_voisins_min: 0.75, ratio: 0.6, sharpe_voisin_min: 0.5}
- C8 : ÉCHEC ; mesure (0.4052, 0.3181) ; seuil (2, 0.3)
- C9 : OK ; mesure 1.388e-16 ; seuil {aleatoires: 20, fixes: 3, part_non_pleine_min: 0.4, tolerance: 1e-09}
- C11 : ÉCHEC ; mesure (0.174, -0.3902) ; seuil (0.5, 0)
- C12 : OK ; mesure (0.04087, 4.216) ; seuil (0.5, 40)
- C13 : OK ; mesure (1.424, 0.08522) ; seuil 0
- C14 : OK ; mesure 0.2538 ; seuil 0.04
- C15 : OK ; mesure non applicable (couvert) ; seuil None
- C16 : ÉCHEC ; mesure None ; seuil 0.6
- C2 : OK ; mesure 0.9518 ; seuil 0.5
- C3 : OK ; mesure 2.36 ; seuil 2
- C4 : OK ; mesure 0.911 ; seuil 0
- C10 : OK ; mesure 0.008798 ; seuil 0.05

### R0138 (p-levier-accelere {fenetre_long: 80, h_bas: 0.5})
- C1 : ÉCHEC ; mesure 2.069e-11 ; seuil 0.95
- C5 : OK ; mesure {2020: 2.042, 2021: 2.367, 2022: -0.8595, 2023: 1.784, 2024: 0.8611, 2025: -0.121} ; seuil {sharpe_min: -1, positives_min: 4}
- C6 : ÉCHEC ; mesure 0.318 ; seuil 0.2
- C7 : OK ; mesure 1 ; seuil {part_voisins_min: 0.75, ratio: 0.6, sharpe_voisin_min: 0.5}
- C8 : ÉCHEC ; mesure (0.7979, 0.2734) ; seuil (2, 0.3)
- C9 : OK ; mesure 1.388e-16 ; seuil {aleatoires: 20, fixes: 3, part_non_pleine_min: 0.4, tolerance: 1e-09}
- C11 : ÉCHEC ; mesure (0.2576, -0.3066) ; seuil (0.5148, 0)
- C12 : OK ; mesure (0.04264, 3.803) ; seuil (0.5, 40)
- C13 : OK ; mesure (1.491, 0.1687) ; seuil 0
- C14 : OK ; mesure 0.2472 ; seuil 0.04
- C15 : OK ; mesure non applicable (couvert) ; seuil None
- C16 : ÉCHEC ; mesure None ; seuil 0.6
- C2 : OK ; mesure 1.03 ; seuil 0.5
- C3 : OK ; mesure 2.445 ; seuil 2
- C4 : OK ; mesure 0.9837 ; seuil 0
- C10 : OK ; mesure 0.008398 ; seuil 0.05

### R0139 (p-levier-accelere {fenetre_long: 80, h_bas: 0.65})
- C1 : ÉCHEC ; mesure 4.601e-10 ; seuil 0.95
- C5 : OK ; mesure {2020: 2.052, 2021: 2.771, 2022: -0.6476, 2023: 1.816, 2024: 0.9713, 2025: -0.2357} ; seuil {sharpe_min: -1, positives_min: 4}
- C6 : ÉCHEC ; mesure 0.2585 ; seuil 0.2
- C7 : OK ; mesure 1 ; seuil {part_voisins_min: 0.75, ratio: 0.6, sharpe_voisin_min: 0.5}
- C8 : ÉCHEC ; mesure (1.521, 0.2196) ; seuil (2, 0.3)
- C9 : OK ; mesure 1.388e-16 ; seuil {aleatoires: 20, fixes: 3, part_non_pleine_min: 0.4, tolerance: 1e-09}
- C11 : ÉCHEC ; mesure (0.424, -0.1818) ; seuil (0.6038, 0)
- C12 : OK ; mesure (0.04185, 3.334) ; seuil (0.5, 40)
- C13 : OK ; mesure (1.739, 0.1436) ; seuil 0
- C14 : OK ; mesure 0.2516 ; seuil 0.04
- C15 : OK ; mesure non applicable (couvert) ; seuil None
- C16 : ÉCHEC ; mesure None ; seuil 0.6
- C2 : OK ; mesure 1.208 ; seuil 0.5
- C3 : OK ; mesure 2.694 ; seuil 2
- C4 : OK ; mesure 1.155 ; seuil 0
- C10 : OK ; mesure 0.005199 ; seuil 0.05

### R0140 (p-levier-accelere {fenetre_long: 80, h_bas: 0.84})
- C1 : ÉCHEC ; mesure 4.268e-09 ; seuil 0.95
- C5 : OK ; mesure {2020: 2.135, 2021: 2.953, 2022: -0.6679, 2023: 2.285, 2024: 1.953, 2025: -0.2008} ; seuil {sharpe_min: -1, positives_min: 4}
- C6 : ÉCHEC ; mesure 0.2039 ; seuil 0.2
- C7 : ÉCHEC ; mesure None ; seuil {part_voisins_min: 0.75, ratio: 0.6, sharpe_voisin_min: 0.5}
- C8 : ÉCHEC ; mesure (1.935, 0.1554) ; seuil (2, 0.3)
- C9 : OK ; mesure 2.22e-16 ; seuil {aleatoires: 20, fixes: 3, part_non_pleine_min: 0.4, tolerance: 1e-09}
- C11 : ÉCHEC ; mesure (0.5421, -0.1198) ; seuil (0.6758, 0)
- C12 : OK ; mesure (0.04692, 3.077) ; seuil (0.5, 40)
- C13 : OK ; mesure (1.865, 0.4716) ; seuil 0
- C14 : OK ; mesure 0.2238 ; seuil 0.04
- C15 : OK ; mesure non applicable (couvert) ; seuil None
- C16 : ÉCHEC ; mesure None ; seuil 0.6
- C2 : OK ; mesure 1.352 ; seuil 0.5
- C3 : OK ; mesure 2.793 ; seuil 2
- C4 : OK ; mesure 1.285 ; seuil 0
- C10 : OK ; mesure 0.003599 ; seuil 0.05

### R0141 (p-levier-accelere {fenetre_long: 126, h_bas: 0.3})
- C1 : ÉCHEC ; mesure 4.292e-12 ; seuil 0.95
- C5 : OK ; mesure {2020: 1.983, 2021: 2.3, 2022: -0.6051, 2023: 1.542, 2024: 0.8789, 2025: -0.2531} ; seuil {sharpe_min: -1, positives_min: 4}
- C6 : ÉCHEC ; mesure 0.3806 ; seuil 0.2
- C7 : ÉCHEC ; mesure None ; seuil {part_voisins_min: 0.75, ratio: 0.6, sharpe_voisin_min: 0.5}
- C8 : ÉCHEC ; mesure (0.4192, 0.3532) ; seuil (2, 0.3)
- C9 : OK ; mesure 1.527e-16 ; seuil {aleatoires: 20, fixes: 3, part_non_pleine_min: 0.4, tolerance: 1e-09}
- C11 : ÉCHEC ; mesure (0.1809, -0.3714) ; seuil (0.5, 0)
- C12 : OK ; mesure (0.03746, 4.014) ; seuil (0.5, 40)
- C13 : OK ; mesure (1.456, 0.08105) ; seuil 0
- C14 : OK ; mesure 0.2784 ; seuil 0.04
- C15 : OK ; mesure non applicable (couvert) ; seuil None
- C16 : ÉCHEC ; mesure None ; seuil 0.6
- C2 : OK ; mesure 0.9543 ; seuil 0.5
- C3 : OK ; mesure 2.419 ; seuil 2
- C4 : OK ; mesure 0.917 ; seuil 0
- C10 : OK ; mesure 0.007399 ; seuil 0.05

### R0142 (p-levier-accelere {fenetre_long: 126, h_bas: 0.39})
- C1 : ÉCHEC ; mesure 1.053e-11 ; seuil 0.95
- C5 : OK ; mesure {2020: 1.97, 2021: 2.322, 2022: -0.6007, 2023: 1.692, 2024: 1.098, 2025: -0.3232} ; seuil {sharpe_min: -1, positives_min: 4}
- C6 : ÉCHEC ; mesure 0.3595 ; seuil 0.2
- C7 : ÉCHEC ; mesure None ; seuil {part_voisins_min: 0.75, ratio: 0.6, sharpe_voisin_min: 0.5}
- C8 : ÉCHEC ; mesure (0.6587, 0.3155) ; seuil (2, 0.3)
- C9 : OK ; mesure 1.457e-16 ; seuil {aleatoires: 20, fixes: 3, part_non_pleine_min: 0.4, tolerance: 1e-09}
- C11 : ÉCHEC ; mesure (0.2272, -0.3247) ; seuil (0.5004, 0)
- C12 : OK ; mesure (0.03863, 3.656) ; seuil (0.5, 40)
- C13 : OK ; mesure (1.491, 0.1259) ; seuil 0
- C14 : OK ; mesure 0.2684 ; seuil 0.04
- C15 : OK ; mesure non applicable (couvert) ; seuil None
- C16 : ÉCHEC ; mesure None ; seuil 0.6
- C2 : OK ; mesure 1.001 ; seuil 0.5
- C3 : OK ; mesure 2.472 ; seuil 2
- C4 : OK ; mesure 0.9607 ; seuil 0
- C10 : OK ; mesure 0.007199 ; seuil 0.05

### R0143 (p-levier-accelere {fenetre_long: 126, h_bas: 0.5})
- C1 : ÉCHEC ; mesure 2.74e-11 ; seuil 0.95
- C5 : OK ; mesure {2020: 2.009, 2021: 2.442, 2022: -0.7755, 2023: 1.682, 2024: 1.209, 2025: -0.2455} ; seuil {sharpe_min: -1, positives_min: 4}
- C6 : ÉCHEC ; mesure 0.3106 ; seuil 0.2
- C7 : ÉCHEC ; mesure None ; seuil {part_voisins_min: 0.75, ratio: 0.6, sharpe_voisin_min: 0.5}
- C8 : ÉCHEC ; mesure (0.9021, 0.2739) ; seuil (2, 0.3)
- C9 : OK ; mesure 1.249e-16 ; seuil {aleatoires: 20, fixes: 3, part_non_pleine_min: 0.4, tolerance: 1e-09}
- C11 : ÉCHEC ; mesure (0.2708, -0.2957) ; seuil (0.5258, 0)
- C12 : OK ; mesure (0.04069, 3.324) ; seuil (0.5, 40)
- C13 : OK ; mesure (1.512, 0.2105) ; seuil 0
- C14 : OK ; mesure 0.2527 ; seuil 0.04
- C15 : OK ; mesure non applicable (couvert) ; seuil None
- C16 : ÉCHEC ; mesure None ; seuil 0.6
- C2 : OK ; mesure 1.052 ; seuil 0.5
- C3 : OK ; mesure 2.504 ; seuil 2
- C4 : OK ; mesure 1.007 ; seuil 0
- C10 : OK ; mesure 0.007598 ; seuil 0.05

### R0144 (p-levier-accelere {fenetre_long: 126, h_bas: 0.65})
- C1 : ÉCHEC ; mesure 3.208e-10 ; seuil 0.95
- C5 : OK ; mesure {2020: 2.09, 2021: 2.672, 2022: -0.7041, 2023: 1.47, 2024: 1.5, 2025: -0.1335} ; seuil {sharpe_min: -1, positives_min: 4}
- C6 : ÉCHEC ; mesure 0.2608 ; seuil 0.2
- C7 : ÉCHEC ; mesure None ; seuil {part_voisins_min: 0.75, ratio: 0.6, sharpe_voisin_min: 0.5}
- C8 : ÉCHEC ; mesure (1.481, 0.2204) ; seuil (2, 0.3)
- C9 : OK ; mesure 1.041e-16 ; seuil {aleatoires: 20, fixes: 3, part_non_pleine_min: 0.4, tolerance: 1e-09}
- C11 : ÉCHEC ; mesure (0.4084, -0.1863) ; seuil (0.5972, 0)
- C12 : OK ; mesure (0.04102, 2.982) ; seuil (0.5, 40)
- C13 : OK ; mesure (1.689, 0.2619) ; seuil 0
- C14 : OK ; mesure 0.2478 ; seuil 0.04
- C15 : OK ; mesure non applicable (couvert) ; seuil None
- C16 : ÉCHEC ; mesure None ; seuil 0.6
- C2 : OK ; mesure 1.194 ; seuil 0.5
- C3 : OK ; mesure 2.696 ; seuil 2
- C4 : OK ; mesure 1.143 ; seuil 0
- C10 : OK ; mesure 0.004799 ; seuil 0.05

### R0145 (p-levier-accelere {fenetre_long: 126, h_bas: 0.84})
- C1 : ÉCHEC ; mesure 3.733e-09 ; seuil 0.95
- C5 : OK ; mesure {2020: 2.137, 2021: 2.906, 2022: -0.7049, 2023: 1.981, 2024: 2.467, 2025: -0.06649} ; seuil {sharpe_min: -1, positives_min: 4}
- C6 : ÉCHEC ; mesure 0.2039 ; seuil 0.2
- C7 : ÉCHEC ; mesure None ; seuil {part_voisins_min: 0.75, ratio: 0.6, sharpe_voisin_min: 0.5}
- C8 : ÉCHEC ; mesure (1.93, 0.1545) ; seuil (2, 0.3)
- C9 : OK ; mesure 1.249e-16 ; seuil {aleatoires: 20, fixes: 3, part_non_pleine_min: 0.4, tolerance: 1e-09}
- C11 : ÉCHEC ; mesure (0.5335, -0.1118) ; seuil (0.6746, 0)
- C12 : OK ; mesure (0.04696, 2.903) ; seuil (0.5, 40)
- C13 : OK ; mesure (1.842, 0.5773) ; seuil 0
- C14 : OK ; mesure 0.2211 ; seuil 0.04
- C15 : OK ; mesure non applicable (couvert) ; seuil None
- C16 : ÉCHEC ; mesure None ; seuil 0.6
- C2 : OK ; mesure 1.349 ; seuil 0.5
- C3 : OK ; mesure 2.795 ; seuil 2
- C4 : OK ; mesure 1.282 ; seuil 0
- C10 : OK ; mesure 0.003399 ; seuil 0.05

### R0146 (r-cible-vol-perp {L_vol_jours: 10, sigma_cible: 0.06})
- C1 : ÉCHEC ; mesure 0.0004322 ; seuil 0.95
- C5 : ÉCHEC ; mesure {2020: 4.258, 2021: 7.03, 2022: -2.162, 2023: 2.163, 2024: 3.287, 2025: 0.4334} ; seuil {sharpe_min: -1, positives_min: 4}
- C6 : OK ; mesure 0.0795 ; seuil 0.2
- C7 : ÉCHEC ; mesure None ; seuil {part_voisins_min: 0.75, ratio: 0.6, sharpe_voisin_min: 0.5}
- C8 : OK ; mesure (4.741, 0.04467) ; seuil (2, 0.3)
- C9 : OK ; mesure 2.082e-16 ; seuil {aleatoires: 20, fixes: 3, part_non_pleine_min: 0.4, tolerance: 1e-09}
- C11 : OK ; mesure (1.796, 1.337) ; seuil (1.171, 0)
- C12 : OK ; mesure (0.07787, 2.147) ; seuil (0.5, 40)
- C13 : OK ; mesure (3.304, 1.262) ; seuil 0
- C14 : OK ; mesure 0.09596 ; seuil 0.04
- C15 : OK ; mesure non applicable (couvert) ; seuil None
- C16 : ÉCHEC ; mesure None ; seuil 0.6
- C2 : OK ; mesure 2.342 ; seuil 0.5
- C3 : OK ; mesure 3.877 ; seuil 2
- C4 : OK ; mesure 2.132 ; seuil 0
- C10 : OK ; mesure 0.0003999 ; seuil 0.05

### R0147 (r-cible-vol-perp {L_vol_jours: 10, sigma_cible: 0.08})
- C1 : ÉCHEC ; mesure 9.886e-06 ; seuil 0.95
- C5 : ÉCHEC ; mesure {2020: 3.868, 2021: 6.212, 2022: -2.084, 2023: 2.003, 2024: 2.759, 2025: 0.2804} ; seuil {sharpe_min: -1, positives_min: 4}
- C6 : OK ; mesure 0.1053 ; seuil 0.2
- C7 : ÉCHEC ; mesure None ; seuil {part_voisins_min: 0.75, ratio: 0.6, sharpe_voisin_min: 0.5}
- C8 : OK ; mesure (4.21, 0.05923) ; seuil (2, 0.3)
- C9 : OK ; mesure 1.527e-16 ; seuil {aleatoires: 20, fixes: 3, part_non_pleine_min: 0.4, tolerance: 1e-09}
- C11 : OK ; mesure (1.404, 0.9464) ; seuil (0.9824, 0)
- C12 : OK ; mesure (0.073, 2.269) ; seuil (0.5, 40)
- C13 : OK ; mesure (2.81, 1.048) ; seuil 0
- C14 : OK ; mesure 0.1056 ; seuil 0.04
- C15 : OK ; mesure non applicable (couvert) ; seuil None
- C16 : ÉCHEC ; mesure None ; seuil 0.6
- C2 : OK ; mesure 1.965 ; seuil 0.5
- C3 : OK ; mesure 3.531 ; seuil 2
- C4 : OK ; mesure 1.804 ; seuil 0
- C10 : OK ; mesure 0.0009998 ; seuil 0.05

### R0148 (r-cible-vol-perp {L_vol_jours: 10, sigma_cible: 0.11})
- C1 : ÉCHEC ; mesure 1.91e-07 ; seuil 0.95
- C5 : ÉCHEC ; mesure {2020: 3.336, 2021: 5.41, 2022: -1.815, 2023: 1.858, 2024: 2.372, 2025: 0.1818} ; seuil {sharpe_min: -1, positives_min: 4}
- C6 : OK ; mesure 0.1349 ; seuil 0.2
- C7 : ÉCHEC ; mesure None ; seuil {part_voisins_min: 0.75, ratio: 0.6, sharpe_voisin_min: 0.5}
- C8 : OK ; mesure (3.576, 0.08188) ; seuil (2, 0.3)
- C9 : OK ; mesure 2.082e-16 ; seuil {aleatoires: 20, fixes: 3, part_non_pleine_min: 0.4, tolerance: 1e-09}
- C11 : OK ; mesure (1.078, 0.619) ; seuil (0.8231, 0)
- C12 : OK ; mesure (0.06662, 2.49) ; seuil (0.5, 40)
- C13 : OK ; mesure (2.368, 0.8864) ; seuil 0
- C14 : OK ; mesure 0.1226 ; seuil 0.04
- C15 : OK ; mesure non applicable (couvert) ; seuil None
- C16 : ÉCHEC ; mesure None ; seuil 0.6
- C2 : OK ; mesure 1.646 ; seuil 0.5
- C3 : OK ; mesure 3.22 ; seuil 2
- C4 : OK ; mesure 1.526 ; seuil 0
- C10 : OK ; mesure 0.0014 ; seuil 0.05

### R0149 (r-cible-vol-perp {L_vol_jours: 10, sigma_cible: 0.15})
- C1 : ÉCHEC ; mesure 8.595e-09 ; seuil 0.95
- C5 : ÉCHEC ; mesure {2020: 2.979, 2021: 4.516, 2022: -1.622, 2023: 1.851, 2024: 2.072, 2025: 0.1469} ; seuil {sharpe_min: -1, positives_min: 4}
- C6 : OK ; mesure 0.1717 ; seuil 0.2
- C7 : ÉCHEC ; mesure None ; seuil {part_voisins_min: 0.75, ratio: 0.6, sharpe_voisin_min: 0.5}
- C8 : OK ; mesure (2.909, 0.1135) ; seuil (2, 0.3)
- C9 : OK ; mesure 2.498e-16 ; seuil {aleatoires: 20, fixes: 3, part_non_pleine_min: 0.4, tolerance: 1e-09}
- C11 : OK ; mesure (0.8353, 0.3722) ; seuil (0.7135, 0)
- C12 : OK ; mesure (0.05939, 2.716) ; seuil (0.5, 40)
- C13 : OK ; mesure (2.036, 0.7851) ; seuil 0
- C14 : OK ; mesure 0.1468 ; seuil 0.04
- C15 : OK ; mesure non applicable (couvert) ; seuil None
- C16 : ÉCHEC ; mesure None ; seuil 0.6
- C2 : OK ; mesure 1.427 ; seuil 0.5
- C3 : OK ; mesure 2.957 ; seuil 2
- C4 : OK ; mesure 1.335 ; seuil 0
- C10 : OK ; mesure 0.0022 ; seuil 0.05

### R0150 (r-cible-vol-perp {L_vol_jours: 10, sigma_cible: 0.22})
- C1 : ÉCHEC ; mesure 2.353e-10 ; seuil 0.95
- C5 : ÉCHEC ; mesure {2020: 2.717, 2021: 3.83, 2022: -1.491, 2023: 1.747, 2024: 1.754, 2025: 0.06422} ; seuil {sharpe_min: -1, positives_min: 4}
- C6 : ÉCHEC ; mesure 0.2368 ; seuil 0.2
- C7 : ÉCHEC ; mesure None ; seuil {part_voisins_min: 0.75, ratio: 0.6, sharpe_voisin_min: 0.5}
- C8 : ÉCHEC ; mesure (1.973, 0.1697) ; seuil (2, 0.3)
- C9 : OK ; mesure 3.331e-16 ; seuil {aleatoires: 20, fixes: 3, part_non_pleine_min: 0.4, tolerance: 1e-09}
- C11 : ÉCHEC ; mesure (0.5958, 0.1268) ; seuil (0.6073, 0)
- C12 : OK ; mesure (0.05099, 3.038) ; seuil (0.5, 40)
- C13 : OK ; mesure (1.772, 0.6289) ; seuil 0
- C14 : OK ; mesure 0.1838 ; seuil 0.04
- C15 : OK ; mesure non applicable (couvert) ; seuil None
- C16 : ÉCHEC ; mesure None ; seuil 0.6
- C2 : OK ; mesure 1.215 ; seuil 0.5
- C3 : OK ; mesure 2.634 ; seuil 2
- C4 : OK ; mesure 1.149 ; seuil 0
- C10 : OK ; mesure 0.004399 ; seuil 0.05

### R0151 (r-cible-vol-perp {L_vol_jours: 20, sigma_cible: 0.06})
- C1 : ÉCHEC ; mesure 0.0003263 ; seuil 0.95
- C5 : ÉCHEC ; mesure {2020: 3.807, 2021: 6.996, 2022: -2.142, 2023: 2.23, 2024: 3.327, 2025: 0.4368} ; seuil {sharpe_min: -1, positives_min: 4}
- C6 : OK ; mesure 0.07567 ; seuil 0.2
- C7 : ÉCHEC ; mesure None ; seuil {part_voisins_min: 0.75, ratio: 0.6, sharpe_voisin_min: 0.5}
- C8 : OK ; mesure (4.418, 0.0449) ; seuil (2, 0.3)
- C9 : OK ; mesure 3.469e-16 ; seuil {aleatoires: 20, fixes: 3, part_non_pleine_min: 0.4, tolerance: 1e-09}
- C11 : OK ; mesure (1.731, 1.268) ; seuil (1.138, 0)
- C12 : OK ; mesure (0.07805, 2) ; seuil (0.5, 40)
- C13 : OK ; mesure (3.199, 1.199) ; seuil 0
- C14 : OK ; mesure 0.0922 ; seuil 0.04
- C15 : OK ; mesure non applicable (couvert) ; seuil None
- C16 : ÉCHEC ; mesure None ; seuil 0.6
- C2 : OK ; mesure 2.276 ; seuil 0.5
- C3 : OK ; mesure 3.729 ; seuil 2
- C4 : OK ; mesure 2.073 ; seuil 0
- C10 : OK ; mesure 0.0007998 ; seuil 0.05

### R0152 (r-cible-vol-perp {L_vol_jours: 20, sigma_cible: 0.08})
- C1 : ÉCHEC ; mesure 1.667e-05 ; seuil 0.95
- C5 : ÉCHEC ; mesure {2020: 3.577, 2021: 6.479, 2022: -1.936, 2023: 2.082, 2024: 2.809, 2025: 0.3524} ; seuil {sharpe_min: -1, positives_min: 4}
- C6 : OK ; mesure 0.09269 ; seuil 0.2
- C7 : OK ; mesure 1 ; seuil {part_voisins_min: 0.75, ratio: 0.6, sharpe_voisin_min: 0.5}
- C8 : OK ; mesure (4.234, 0.05858) ; seuil (2, 0.3)
- C9 : OK ; mesure 1.665e-16 ; seuil {aleatoires: 20, fixes: 3, part_non_pleine_min: 0.4, tolerance: 1e-09}
- C11 : OK ; mesure (1.437, 0.9677) ; seuil (0.9938, 0)
- C12 : OK ; mesure (0.06958, 2.023) ; seuil (0.5, 40)
- C13 : OK ; mesure (2.882, 1.005) ; seuil 0
- C14 : OK ; mesure 0.1046 ; seuil 0.04
- C15 : OK ; mesure non applicable (couvert) ; seuil None
- C16 : ÉCHEC ; mesure None ; seuil 0.6
- C2 : OK ; mesure 1.988 ; seuil 0.5
- C3 : OK ; mesure 3.538 ; seuil 2
- C4 : OK ; mesure 1.834 ; seuil 0
- C10 : OK ; mesure 0.0009998 ; seuil 0.05

### R0153 (r-cible-vol-perp {L_vol_jours: 20, sigma_cible: 0.11})
- C1 : ÉCHEC ; mesure 3.3e-07 ; seuil 0.95
- C5 : ÉCHEC ; mesure {2020: 3.175, 2021: 5.442, 2022: -1.663, 2023: 1.846, 2024: 2.546, 2025: 0.2978} ; seuil {sharpe_min: -1, positives_min: 4}
- C6 : OK ; mesure 0.1221 ; seuil 0.2
- C7 : OK ; mesure 1 ; seuil {part_voisins_min: 0.75, ratio: 0.6, sharpe_voisin_min: 0.5}
- C8 : OK ; mesure (3.639, 0.08166) ; seuil (2, 0.3)
- C9 : OK ; mesure 3.608e-16 ; seuil {aleatoires: 20, fixes: 3, part_non_pleine_min: 0.4, tolerance: 1e-09}
- C11 : OK ; mesure (1.106, 0.6384) ; seuil (0.8329, 0)
- C12 : OK ; mesure (0.06112, 2.09) ; seuil (0.5, 40)
- C13 : OK ; mesure (2.415, 0.8517) ; seuil 0
- C14 : OK ; mesure 0.1217 ; seuil 0.04
- C15 : OK ; mesure non applicable (couvert) ; seuil None
- C16 : ÉCHEC ; mesure None ; seuil 0.6
- C2 : OK ; mesure 1.666 ; seuil 0.5
- C3 : OK ; mesure 3.228 ; seuil 2
- C4 : OK ; mesure 1.555 ; seuil 0
- C10 : OK ; mesure 0.0014 ; seuil 0.05

### R0154 (r-cible-vol-perp {L_vol_jours: 20, sigma_cible: 0.15})
- C1 : ÉCHEC ; mesure 1.52e-08 ; seuil 0.95
- C5 : ÉCHEC ; mesure {2020: 2.93, 2021: 4.867, 2022: -1.585, 2023: 1.73, 2024: 2.256, 2025: 0.2052} ; seuil {sharpe_min: -1, positives_min: 4}
- C6 : OK ; mesure 0.1614 ; seuil 0.2
- C7 : OK ; mesure 1 ; seuil {part_voisins_min: 0.75, ratio: 0.6, sharpe_voisin_min: 0.5}
- C8 : OK ; mesure (2.954, 0.1115) ; seuil (2, 0.3)
- C9 : OK ; mesure 1.388e-16 ; seuil {aleatoires: 20, fixes: 3, part_non_pleine_min: 0.4, tolerance: 1e-09}
- C11 : OK ; mesure (0.878, 0.407) ; seuil (0.7277, 0)
- C12 : OK ; mesure (0.05376, 2.193) ; seuil (0.5, 40)
- C13 : OK ; mesure (2.146, 0.725) ; seuil 0
- C14 : OK ; mesure 0.1451 ; seuil 0.04
- C15 : OK ; mesure non applicable (couvert) ; seuil None
- C16 : ÉCHEC ; mesure None ; seuil 0.6
- C2 : OK ; mesure 1.455 ; seuil 0.5
- C3 : OK ; mesure 2.965 ; seuil 2
- C4 : OK ; mesure 1.372 ; seuil 0
- C10 : OK ; mesure 0.0018 ; seuil 0.05

### R0155 (r-cible-vol-perp {L_vol_jours: 20, sigma_cible: 0.22})
- C1 : ÉCHEC ; mesure 1.813e-10 ; seuil 0.95
- C5 : ÉCHEC ; mesure {2020: 2.563, 2021: 4.124, 2022: -1.493, 2023: 1.653, 2024: 1.951, 2025: 0.1426} ; seuil {sharpe_min: -1, positives_min: 4}
- C6 : ÉCHEC ; mesure 0.2382 ; seuil 0.2
- C7 : ÉCHEC ; mesure None ; seuil {part_voisins_min: 0.75, ratio: 0.6, sharpe_voisin_min: 0.5}
- C8 : ÉCHEC ; mesure (1.699, 0.1675) ; seuil (2, 0.3)
- C9 : OK ; mesure 1.943e-16 ; seuil {aleatoires: 20, fixes: 3, part_non_pleine_min: 0.4, tolerance: 1e-09}
- C11 : ÉCHEC ; mesure (0.5814, 0.1089) ; seuil (0.5895, 0)
- C12 : OK ; mesure (0.04622, 2.302) ; seuil (0.5, 40)
- C13 : OK ; mesure (1.778, 0.5525) ; seuil 0
- C14 : OK ; mesure 0.1738 ; seuil 0.04
- C15 : OK ; mesure non applicable (couvert) ; seuil None
- C16 : ÉCHEC ; mesure None ; seuil 0.6
- C2 : OK ; mesure 1.179 ; seuil 0.5
- C3 : OK ; mesure 2.555 ; seuil 2
- C4 : OK ; mesure 1.121 ; seuil 0
- C10 : OK ; mesure 0.006199 ; seuil 0.05

### R0156 (r-cible-vol-perp {L_vol_jours: 40, sigma_cible: 0.06})
- C1 : ÉCHEC ; mesure 0.0008761 ; seuil 0.95
- C5 : ÉCHEC ; mesure {2020: 3.822, 2021: 6.787, 2022: -2.09, 2023: 2.402, 2024: 3.647, 2025: 0.3536} ; seuil {sharpe_min: -1, positives_min: 4}
- C6 : OK ; mesure 0.07522 ; seuil 0.2
- C7 : ÉCHEC ; mesure None ; seuil {part_voisins_min: 0.75, ratio: 0.6, sharpe_voisin_min: 0.5}
- C8 : OK ; mesure (4.801, 0.04533) ; seuil (2, 0.3)
- C9 : OK ; mesure 1.11e-16 ; seuil {aleatoires: 20, fixes: 3, part_non_pleine_min: 0.4, tolerance: 1e-09}
- C11 : OK ; mesure (1.835, 1.366) ; seuil (1.198, 0)
- C12 : OK ; mesure (0.07421, 1.968) ; seuil (0.5, 40)
- C13 : OK ; mesure (3.186, 1.42) ; seuil 0
- C14 : OK ; mesure 0.09686 ; seuil 0.04
- C15 : OK ; mesure non applicable (couvert) ; seuil None
- C16 : ÉCHEC ; mesure None ; seuil 0.6
- C2 : OK ; mesure 2.396 ; seuil 0.5
- C3 : OK ; mesure 3.904 ; seuil 2
- C4 : OK ; mesure 2.195 ; seuil 0
- C10 : OK ; mesure 0.0005999 ; seuil 0.05

### R0157 (r-cible-vol-perp {L_vol_jours: 40, sigma_cible: 0.08})
- C1 : ÉCHEC ; mesure 2.04e-05 ; seuil 0.95
- C5 : ÉCHEC ; mesure {2020: 3.268, 2021: 6.405, 2022: -1.866, 2023: 2.283, 2024: 3.078, 2025: 0.219} ; seuil {sharpe_min: -1, positives_min: 4}
- C6 : OK ; mesure 0.08862 ; seuil 0.2
- C7 : OK ; mesure 1 ; seuil {part_voisins_min: 0.75, ratio: 0.6, sharpe_voisin_min: 0.5}
- C8 : OK ; mesure (4.232, 0.05787) ; seuil (2, 0.3)
- C9 : OK ; mesure 1.249e-16 ; seuil {aleatoires: 20, fixes: 3, part_non_pleine_min: 0.4, tolerance: 1e-09}
- C11 : OK ; mesure (1.44, 0.9683) ; seuil (1.002, 0)
- C12 : OK ; mesure (0.06871, 1.937) ; seuil (0.5, 40)
- C13 : OK ; mesure (2.798, 1.098) ; seuil 0
- C14 : OK ; mesure 0.1029 ; seuil 0.04
- C15 : OK ; mesure non applicable (couvert) ; seuil None
- C16 : ÉCHEC ; mesure None ; seuil 0.6
- C2 : OK ; mesure 2.004 ; seuil 0.5
- C3 : OK ; mesure 3.54 ; seuil 2
- C4 : OK ; mesure 1.851 ; seuil 0
- C10 : OK ; mesure 0.0007998 ; seuil 0.05

### R0158 (r-cible-vol-perp {L_vol_jours: 40, sigma_cible: 0.11})
- C1 : ÉCHEC ; mesure 5.516e-07 ; seuil 0.95
- C5 : ÉCHEC ; mesure {2020: 3.01, 2021: 5.33, 2022: -1.686, 2023: 2.148, 2024: 2.641, 2025: 0.2215} ; seuil {sharpe_min: -1, positives_min: 4}
- C6 : OK ; mesure 0.1159 ; seuil 0.2
- C7 : OK ; mesure 1 ; seuil {part_voisins_min: 0.75, ratio: 0.6, sharpe_voisin_min: 0.5}
- C8 : OK ; mesure (3.834, 0.08059) ; seuil (2, 0.3)
- C9 : OK ; mesure 1.527e-16 ; seuil {aleatoires: 20, fixes: 3, part_non_pleine_min: 0.4, tolerance: 1e-09}
- C11 : OK ; mesure (1.132, 0.6721) ; seuil (0.8488, 0)
- C12 : OK ; mesure (0.0591, 1.939) ; seuil (0.5, 40)
- C13 : OK ; mesure (2.35, 0.974) ; seuil 0
- C14 : OK ; mesure 0.1207 ; seuil 0.04
- C15 : OK ; mesure non applicable (couvert) ; seuil None
- C16 : ÉCHEC ; mesure None ; seuil 0.6
- C2 : OK ; mesure 1.698 ; seuil 0.5
- C3 : OK ; mesure 3.302 ; seuil 2
- C4 : OK ; mesure 1.589 ; seuil 0
- C10 : OK ; mesure 0.0012 ; seuil 0.05

### R0159 (r-cible-vol-perp {L_vol_jours: 40, sigma_cible: 0.15})
- C1 : ÉCHEC ; mesure 3.594e-08 ; seuil 0.95
- C5 : ÉCHEC ; mesure {2020: 2.791, 2021: 4.834, 2022: -1.579, 2023: 2.049, 2024: 2.386, 2025: 0.1516} ; seuil {sharpe_min: -1, positives_min: 4}
- C6 : OK ; mesure 0.1607 ; seuil 0.2
- C7 : OK ; mesure 1 ; seuil {part_voisins_min: 0.75, ratio: 0.6, sharpe_voisin_min: 0.5}
- C8 : OK ; mesure (3.148, 0.1105) ; seuil (2, 0.3)
- C9 : OK ; mesure 8.327e-17 ; seuil {aleatoires: 20, fixes: 3, part_non_pleine_min: 0.4, tolerance: 1e-09}
- C11 : OK ; mesure (0.9303, 0.465) ; seuil (0.749, 0)
- C12 : OK ; mesure (0.05048, 1.977) ; seuil (0.5, 40)
- C13 : OK ; mesure (2.114, 0.827) ; seuil 0
- C14 : OK ; mesure 0.1467 ; seuil 0.04
- C15 : OK ; mesure non applicable (couvert) ; seuil None
- C16 : ÉCHEC ; mesure None ; seuil 0.6
- C2 : OK ; mesure 1.498 ; seuil 0.5
- C3 : OK ; mesure 3.039 ; seuil 2
- C4 : OK ; mesure 1.417 ; seuil 0
- C10 : OK ; mesure 0.0016 ; seuil 0.05

### R0160 (r-cible-vol-perp {L_vol_jours: 40, sigma_cible: 0.22})
- C1 : ÉCHEC ; mesure 1.405e-09 ; seuil 0.95
- C5 : ÉCHEC ; mesure {2020: 2.533, 2021: 4.08, 2022: -1.43, 2023: 1.951, 2024: 2.135, 2025: 0.1722} ; seuil {sharpe_min: -1, positives_min: 4}
- C6 : ÉCHEC ; mesure 0.2327 ; seuil 0.2
- C7 : ÉCHEC ; mesure None ; seuil {part_voisins_min: 0.75, ratio: 0.6, sharpe_voisin_min: 0.5}
- C8 : OK ; mesure (2.355, 0.1642) ; seuil (2, 0.3)
- C9 : OK ; mesure 1.943e-16 ; seuil {aleatoires: 20, fixes: 3, part_non_pleine_min: 0.4, tolerance: 1e-09}
- C11 : OK ; mesure (0.7056, 0.2377) ; seuil (0.6484, 0)
- C12 : OK ; mesure (0.0394, 1.966) ; seuil (0.5, 40)
- C13 : OK ; mesure (1.839, 0.7178) ; seuil 0
- C14 : OK ; mesure 0.1876 ; seuil 0.04
- C15 : OK ; mesure non applicable (couvert) ; seuil None
- C16 : ÉCHEC ; mesure None ; seuil 0.6
- C2 : OK ; mesure 1.297 ; seuil 0.5
- C3 : OK ; mesure 2.795 ; seuil 2
- C4 : OK ; mesure 1.243 ; seuil 0
- C10 : OK ; mesure 0.003399 ; seuil 0.05

### R0161 (r-cible-vol-perp {L_vol_jours: 80, sigma_cible: 0.06})
- C1 : ÉCHEC ; mesure 0.001263 ; seuil 0.95
- C5 : ÉCHEC ; mesure {2020: 3.899, 2021: 6.382, 2022: -2.06, 2023: 2.644, 2024: 3.524, 2025: 0.3109} ; seuil {sharpe_min: -1, positives_min: 4}
- C6 : OK ; mesure 0.07128 ; seuil 0.2
- C7 : ÉCHEC ; mesure None ; seuil {part_voisins_min: 0.75, ratio: 0.6, sharpe_voisin_min: 0.5}
- C8 : OK ; mesure (4.853, 0.04475) ; seuil (2, 0.3)
- C9 : OK ; mesure 1.804e-16 ; seuil {aleatoires: 20, fixes: 3, part_non_pleine_min: 0.4, tolerance: 1e-09}
- C11 : OK ; mesure (1.893, 1.429) ; seuil (1.224, 0)
- C12 : OK ; mesure (0.07356, 1.921) ; seuil (0.5, 40)
- C13 : OK ; mesure (3.205, 1.483) ; seuil 0
- C14 : OK ; mesure 0.09611 ; seuil 0.04
- C15 : OK ; mesure non applicable (couvert) ; seuil None
- C16 : ÉCHEC ; mesure None ; seuil 0.6
- C2 : OK ; mesure 2.448 ; seuil 0.5
- C3 : OK ; mesure 3.912 ; seuil 2
- C4 : OK ; mesure 2.244 ; seuil 0
- C10 : OK ; mesure 0.0005999 ; seuil 0.05

### R0162 (r-cible-vol-perp {L_vol_jours: 80, sigma_cible: 0.08})
- C1 : ÉCHEC ; mesure 9.162e-05 ; seuil 0.95
- C5 : ÉCHEC ; mesure {2020: 3.326, 2021: 6.152, 2022: -1.954, 2023: 2.448, 2024: 3.057, 2025: 0.246} ; seuil {sharpe_min: -1, positives_min: 4}
- C6 : OK ; mesure 0.08062 ; seuil 0.2
- C7 : OK ; mesure 1 ; seuil {part_voisins_min: 0.75, ratio: 0.6, sharpe_voisin_min: 0.5}
- C8 : OK ; mesure (4.771, 0.05757) ; seuil (2, 0.3)
- C9 : OK ; mesure 1.943e-16 ; seuil {aleatoires: 20, fixes: 3, part_non_pleine_min: 0.4, tolerance: 1e-09}
- C11 : OK ; mesure (1.588, 1.112) ; seuil (1.074, 0)
- C12 : OK ; mesure (0.065, 1.883) ; seuil (0.5, 40)
- C13 : OK ; mesure (2.918, 1.24) ; seuil 0
- C14 : OK ; mesure 0.1082 ; seuil 0.04
- C15 : OK ; mesure non applicable (couvert) ; seuil None
- C16 : ÉCHEC ; mesure None ; seuil 0.6
- C2 : OK ; mesure 2.148 ; seuil 0.5
- C3 : OK ; mesure 3.767 ; seuil 2
- C4 : OK ; mesure 1.993 ; seuil 0
- C10 : OK ; mesure 0.0005999 ; seuil 0.05

### R0163 (r-cible-vol-perp {L_vol_jours: 80, sigma_cible: 0.11})
- C1 : ÉCHEC ; mesure 1.305e-06 ; seuil 0.95
- C5 : ÉCHEC ; mesure {2020: 2.748, 2021: 5.399, 2022: -1.706, 2023: 2.202, 2024: 2.747, 2025: 0.09656} ; seuil {sharpe_min: -1, positives_min: 4}
- C6 : OK ; mesure 0.1045 ; seuil 0.2
- C7 : OK ; mesure 1 ; seuil {part_voisins_min: 0.75, ratio: 0.6, sharpe_voisin_min: 0.5}
- C8 : OK ; mesure (4.027, 0.07812) ; seuil (2, 0.3)
- C9 : OK ; mesure 9.714e-17 ; seuil {aleatoires: 20, fixes: 3, part_non_pleine_min: 0.4, tolerance: 1e-09}
- C11 : OK ; mesure (1.183, 0.7197) ; seuil (0.8749, 0)
- C12 : OK ; mesure (0.05908, 1.858) ; seuil (0.5, 40)
- C13 : OK ; mesure (2.384, 1.056) ; seuil 0
- C14 : OK ; mesure 0.119 ; seuil 0.04
- C15 : OK ; mesure non applicable (couvert) ; seuil None
- C16 : ÉCHEC ; mesure None ; seuil 0.6
- C2 : OK ; mesure 1.75 ; seuil 0.5
- C3 : OK ; mesure 3.355 ; seuil 2
- C4 : OK ; mesure 1.639 ; seuil 0
- C10 : OK ; mesure 0.0009998 ; seuil 0.05

### R0164 (r-cible-vol-perp {L_vol_jours: 80, sigma_cible: 0.15})
- C1 : ÉCHEC ; mesure 2.703e-08 ; seuil 0.95
- C5 : ÉCHEC ; mesure {2020: 2.464, 2021: 4.77, 2022: -1.5, 2023: 1.959, 2024: 2.394, 2025: 0.1149} ; seuil {sharpe_min: -1, positives_min: 4}
- C6 : OK ; mesure 0.1487 ; seuil 0.2
- C7 : OK ; mesure 1 ; seuil {part_voisins_min: 0.75, ratio: 0.6, sharpe_voisin_min: 0.5}
- C8 : OK ; mesure (3.173, 0.108) ; seuil (2, 0.3)
- C9 : OK ; mesure 1.804e-16 ; seuil {aleatoires: 20, fixes: 3, part_non_pleine_min: 0.4, tolerance: 1e-09}
- C11 : OK ; mesure (0.8914, 0.4101) ; seuil (0.7361, 0)
- C12 : OK ; mesure (0.05136, 1.843) ; seuil (0.5, 40)
- C13 : OK ; mesure (2.027, 0.8911) ; seuil 0
- C14 : OK ; mesure 0.1383 ; seuil 0.04
- C15 : OK ; mesure non applicable (couvert) ; seuil None
- C16 : ÉCHEC ; mesure None ; seuil 0.6
- C2 : OK ; mesure 1.472 ; seuil 0.5
- C3 : OK ; mesure 3.046 ; seuil 2
- C4 : OK ; mesure 1.391 ; seuil 0
- C10 : OK ; mesure 0.002 ; seuil 0.05

### R0165 (r-cible-vol-perp {L_vol_jours: 80, sigma_cible: 0.22})
- C1 : ÉCHEC ; mesure 9.553e-10 ; seuil 0.95
- C5 : ÉCHEC ; mesure {2020: 2.059, 2021: 4.025, 2022: -1.391, 2023: 1.858, 2024: 2.178, 2025: 0.11} ; seuil {sharpe_min: -1, positives_min: 4}
- C6 : ÉCHEC ; mesure 0.2157 ; seuil 0.2
- C7 : ÉCHEC ; mesure None ; seuil {part_voisins_min: 0.75, ratio: 0.6, sharpe_voisin_min: 0.5}
- C8 : OK ; mesure (2.103, 0.162) ; seuil (2, 0.3)
- C9 : OK ; mesure 1.388e-16 ; seuil {aleatoires: 20, fixes: 3, part_non_pleine_min: 0.4, tolerance: 1e-09}
- C11 : OK ; mesure (0.6569, 0.1795) ; seuil (0.6236, 0)
- C12 : OK ; mesure (0.03968, 1.771) ; seuil (0.5, 40)
- C13 : OK ; mesure (1.663, 0.8036) ; seuil 0
- C14 : OK ; mesure 0.1737 ; seuil 0.04
- C15 : OK ; mesure non applicable (couvert) ; seuil None
- C16 : ÉCHEC ; mesure None ; seuil 0.6
- C2 : OK ; mesure 1.247 ; seuil 0.5
- C3 : OK ; mesure 2.726 ; seuil 2
- C4 : OK ; mesure 1.196 ; seuil 0
- C10 : OK ; mesure 0.003999 ; seuil 0.05

### R0166 (r-cible-vol-perp {L_vol_jours: 160, sigma_cible: 0.06})
- C1 : ÉCHEC ; mesure 0.001438 ; seuil 0.95
- C5 : ÉCHEC ; mesure {2020: 4.216, 2021: 6.678, 2022: -2.144, 2023: 2.846, 2024: 3.302, 2025: 0.2231} ; seuil {sharpe_min: -1, positives_min: 4}
- C6 : OK ; mesure 0.06912 ; seuil 0.2
- C7 : ÉCHEC ; mesure None ; seuil {part_voisins_min: 0.75, ratio: 0.6, sharpe_voisin_min: 0.5}
- C8 : OK ; mesure (4.69, 0.04098) ; seuil (2, 0.3)
- C9 : OK ; mesure 1.11e-16 ; seuil {aleatoires: 20, fixes: 3, part_non_pleine_min: 0.4, tolerance: 1e-09}
- C11 : OK ; mesure (1.907, 1.439) ; seuil (1.239, 0)
- C12 : OK ; mesure (0.07813, 1.926) ; seuil (0.5, 40)
- C13 : OK ; mesure (3.373, 1.373) ; seuil 0
- C14 : OK ; mesure 0.0902 ; seuil 0.04
- C15 : OK ; mesure non applicable (couvert) ; seuil None
- C16 : ÉCHEC ; mesure None ; seuil 0.6
- C2 : OK ; mesure 2.477 ; seuil 0.5
- C3 : OK ; mesure 3.922 ; seuil 2
- C4 : OK ; mesure 2.256 ; seuil 0
- C10 : OK ; mesure 0.0003999 ; seuil 0.05

### R0167 (r-cible-vol-perp {L_vol_jours: 160, sigma_cible: 0.08})
- C1 : ÉCHEC ; mesure 6.574e-05 ; seuil 0.95
- C5 : ÉCHEC ; mesure {2020: 3.615, 2021: 6.252, 2022: -1.99, 2023: 2.417, 2024: 2.658, 2025: 0.1395} ; seuil {sharpe_min: -1, positives_min: 4}
- C6 : OK ; mesure 0.07409 ; seuil 0.2
- C7 : ÉCHEC ; mesure None ; seuil {part_voisins_min: 0.75, ratio: 0.6, sharpe_voisin_min: 0.5}
- C8 : OK ; mesure (4.65, 0.05386) ; seuil (2, 0.3)
- C9 : OK ; mesure 6.939e-17 ; seuil {aleatoires: 20, fixes: 3, part_non_pleine_min: 0.4, tolerance: 1e-09}
- C11 : OK ; mesure (1.565, 1.094) ; seuil (1.069, 0)
- C12 : OK ; mesure (0.06892, 1.882) ; seuil (0.5, 40)
- C13 : OK ; mesure (3.075, 1.103) ; seuil 0
- C14 : OK ; mesure 0.1016 ; seuil 0.04
- C15 : OK ; mesure non applicable (couvert) ; seuil None
- C16 : ÉCHEC ; mesure None ; seuil 0.6
- C2 : OK ; mesure 2.137 ; seuil 0.5
- C3 : OK ; mesure 3.756 ; seuil 2
- C4 : OK ; mesure 1.974 ; seuil 0
- C10 : OK ; mesure 0.0005999 ; seuil 0.05

### R0168 (r-cible-vol-perp {L_vol_jours: 160, sigma_cible: 0.11})
- C1 : ÉCHEC ; mesure 1.807e-06 ; seuil 0.95
- C5 : ÉCHEC ; mesure {2020: 3.084, 2021: 5.135, 2022: -1.69, 2023: 2.241, 2024: 2.521, 2025: 0.06704} ; seuil {sharpe_min: -1, positives_min: 4}
- C6 : OK ; mesure 0.09475 ; seuil 0.2
- C7 : ÉCHEC ; mesure None ; seuil {part_voisins_min: 0.75, ratio: 0.6, sharpe_voisin_min: 0.5}
- C8 : OK ; mesure (4.445, 0.07514) ; seuil (2, 0.3)
- C9 : OK ; mesure 7.633e-17 ; seuil {aleatoires: 20, fixes: 3, part_non_pleine_min: 0.4, tolerance: 1e-09}
- C11 : OK ; mesure (1.233, 0.7737) ; seuil (0.904, 0)
- C12 : OK ; mesure (0.05962, 1.84) ; seuil (0.5, 40)
- C13 : OK ; mesure (2.524, 1.027) ; seuil 0
- C14 : OK ; mesure 0.1178 ; seuil 0.04
- C15 : OK ; mesure non applicable (couvert) ; seuil None
- C16 : ÉCHEC ; mesure None ; seuil 0.6
- C2 : OK ; mesure 1.808 ; seuil 0.5
- C3 : OK ; mesure 3.513 ; seuil 2
- C4 : OK ; mesure 1.692 ; seuil 0
- C10 : OK ; mesure 0.0007998 ; seuil 0.05

### R0169 (r-cible-vol-perp {L_vol_jours: 160, sigma_cible: 0.15})
- C1 : ÉCHEC ; mesure 2.708e-08 ; seuil 0.95
- C5 : ÉCHEC ; mesure {2020: 2.613, 2021: 4.474, 2022: -1.548, 2023: 2.034, 2024: 2.326, 2025: -0.08351} ; seuil {sharpe_min: -1, positives_min: 4}
- C6 : OK ; mesure 0.1374 ; seuil 0.2
- C7 : ÉCHEC ; mesure None ; seuil {part_voisins_min: 0.75, ratio: 0.6, sharpe_voisin_min: 0.5}
- C8 : OK ; mesure (3.499, 0.1033) ; seuil (2, 0.3)
- C9 : OK ; mesure 1.11e-16 ; seuil {aleatoires: 20, fixes: 3, part_non_pleine_min: 0.4, tolerance: 1e-09}
- C11 : OK ; mesure (0.8978, 0.4317) ; seuil (0.7442, 0)
- C12 : OK ; mesure (0.05259, 1.803) ; seuil (0.5, 40)
- C13 : OK ; mesure (2.112, 0.8471) ; seuil 0
- C14 : OK ; mesure 0.1328 ; seuil 0.04
- C15 : OK ; mesure non applicable (couvert) ; seuil None
- C16 : ÉCHEC ; mesure None ; seuil 0.6
- C2 : OK ; mesure 1.488 ; seuil 0.5
- C3 : OK ; mesure 3.112 ; seuil 2
- C4 : OK ; mesure 1.404 ; seuil 0
- C10 : OK ; mesure 0.0016 ; seuil 0.05

### R0170 (r-cible-vol-perp {L_vol_jours: 160, sigma_cible: 0.22})
- C1 : ÉCHEC ; mesure 9.012e-10 ; seuil 0.95
- C5 : ÉCHEC ; mesure {2020: 2.235, 2021: 3.878, 2022: -1.325, 2023: 1.906, 2024: 2.089, 2025: -0.1137} ; seuil {sharpe_min: -1, positives_min: 4}
- C6 : OK ; mesure 0.1979 ; seuil 0.2
- C7 : ÉCHEC ; mesure None ; seuil {part_voisins_min: 0.75, ratio: 0.6, sharpe_voisin_min: 0.5}
- C8 : OK ; mesure (2.435, 0.1549) ; seuil (2, 0.3)
- C9 : OK ; mesure 1.943e-16 ; seuil {aleatoires: 20, fixes: 3, part_non_pleine_min: 0.4, tolerance: 1e-09}
- C11 : OK ; mesure (0.6663, 0.1825) ; seuil (0.6329, 0)
- C12 : OK ; mesure (0.04074, 1.725) ; seuil (0.5, 40)
- C13 : OK ; mesure (1.77, 0.7461) ; seuil 0
- C14 : OK ; mesure 0.1676 ; seuil 0.04
- C15 : OK ; mesure non applicable (couvert) ; seuil None
- C16 : ÉCHEC ; mesure None ; seuil 0.6
- C2 : OK ; mesure 1.266 ; seuil 0.5
- C3 : OK ; mesure 2.82 ; seuil 2
- C4 : OK ; mesure 1.212 ; seuil 0
- C10 : OK ; mesure 0.003599 ; seuil 0.05

### R0171 (r-coussin-plancher {W_jours: 7, f_plancher: 0.01})
- C1 : ÉCHEC ; mesure 3.205e-06 ; seuil 0.95
- C5 : ÉCHEC ; mesure {2020: 3.712, 2021: 5.079, 2022: -1.75, 2023: 2.347, 2024: 2.441, 2025: 0.09811} ; seuil {sharpe_min: -1, positives_min: 4}
- C6 : OK ; mesure 0.09136 ; seuil 0.2
- C7 : ÉCHEC ; mesure None ; seuil {part_voisins_min: 0.75, ratio: 0.6, sharpe_voisin_min: 0.5}
- C8 : OK ; mesure (3.705, 0.05541) ; seuil (2, 0.3)
- C9 : OK ; mesure 2.29e-16 ; seuil {aleatoires: 20, fixes: 3, part_non_pleine_min: 0.4, tolerance: 1e-09}
- C11 : OK ; mesure (1.272, 0.7744) ; seuil (0.9301, 0)
- C12 : OK ; mesure (0.0771, 2.02) ; seuil (0.5, 40)
- C13 : OK ; mesure (2.578, 0.8894) ; seuil 0
- C14 : OK ; mesure 0.09248 ; seuil 0.04
- C15 : OK ; mesure non applicable (couvert) ; seuil None
- C16 : ÉCHEC ; mesure None ; seuil 0.6
- C2 : OK ; mesure 1.86 ; seuil 0.5
- C3 : OK ; mesure 3.183 ; seuil 2
- C4 : OK ; mesure 1.7 ; seuil 0
- C10 : OK ; mesure 0.0016 ; seuil 0.05

### R0172 (r-coussin-plancher {W_jours: 7, f_plancher: 0.016})
- C1 : ÉCHEC ; mesure 2.875e-09 ; seuil 0.95
- C5 : ÉCHEC ; mesure {2020: 2.66, 2021: 4.423, 2022: -1.785, 2023: 2.09, 2024: 1.958, 2025: -0.3229} ; seuil {sharpe_min: -1, positives_min: 4}
- C6 : OK ; mesure 0.1488 ; seuil 0.2
- C7 : ÉCHEC ; mesure None ; seuil {part_voisins_min: 0.75, ratio: 0.6, sharpe_voisin_min: 0.5}
- C8 : OK ; mesure (2.281, 0.08331) ; seuil (2, 0.3)
- C9 : OK ; mesure 2.22e-16 ; seuil {aleatoires: 20, fixes: 3, part_non_pleine_min: 0.4, tolerance: 1e-09}
- C11 : OK ; mesure (0.7218, 0.1964) ; seuil (0.6923, 0)
- C12 : OK ; mesure (0.07367, 2.433) ; seuil (0.5, 40)
- C13 : OK ; mesure (2.042, 0.4791) ; seuil 0
- C14 : OK ; mesure 0.1039 ; seuil 0.04
- C15 : OK ; mesure non applicable (couvert) ; seuil None
- C16 : ÉCHEC ; mesure None ; seuil 0.6
- C2 : OK ; mesure 1.385 ; seuil 0.5
- C3 : OK ; mesure 2.484 ; seuil 2
- C4 : OK ; mesure 1.271 ; seuil 0
- C10 : OK ; mesure 0.008398 ; seuil 0.05

### R0173 (r-coussin-plancher {W_jours: 7, f_plancher: 0.025})
- C1 : ÉCHEC ; mesure 2.122e-11 ; seuil 0.95
- C5 : ÉCHEC ; mesure {2020: 2.787, 2021: 3.404, 2022: -1.388, 2023: 1.857, 2024: 1.472, 2025: -0.4065} ; seuil {sharpe_min: -1, positives_min: 4}
- C6 : ÉCHEC ; mesure 0.2183 ; seuil 0.2
- C7 : ÉCHEC ; mesure None ; seuil {part_voisins_min: 0.75, ratio: 0.6, sharpe_voisin_min: 0.5}
- C8 : ÉCHEC ; mesure (1.136, 0.1371) ; seuil (2, 0.3)
- C9 : OK ; mesure 5.967e-16 ; seuil {aleatoires: 20, fixes: 3, part_non_pleine_min: 0.4, tolerance: 1e-09}
- C11 : ÉCHEC ; mesure (0.4031, -0.1166) ; seuil (0.5444, 0)
- C12 : OK ; mesure (0.07017, 3.785) ; seuil (0.5, 40)
- C13 : OK ; mesure (1.697, 0.3298) ; seuil 0
- C14 : OK ; mesure 0.1343 ; seuil 0.04
- C15 : OK ; mesure non applicable (couvert) ; seuil None
- C16 : ÉCHEC ; mesure None ; seuil 0.6
- C2 : OK ; mesure 1.089 ; seuil 0.5
- C3 : OK ; mesure 2.148 ; seuil 2
- C4 : OK ; mesure 1.006 ; seuil 0
- C10 : OK ; mesure 0.0186 ; seuil 0.05

### R0174 (r-coussin-plancher {W_jours: 7, f_plancher: 0.04})
- C1 : ÉCHEC ; mesure 8.978e-11 ; seuil 0.95
- C5 : ÉCHEC ; mesure {2020: 2.825, 2021: 3.013, 2022: -1.487, 2023: 1.758, 2024: 1.529, 2025: -0.1553} ; seuil {sharpe_min: -1, positives_min: 4}
- C6 : ÉCHEC ; mesure 0.2684 ; seuil 0.2
- C7 : ÉCHEC ; mesure None ; seuil {part_voisins_min: 0.75, ratio: 0.6, sharpe_voisin_min: 0.5}
- C8 : ÉCHEC ; mesure (1.813, 0.1915) ; seuil (2, 0.3)
- C9 : OK ; mesure 3.469e-16 ; seuil {aleatoires: 20, fixes: 3, part_non_pleine_min: 0.4, tolerance: 1e-09}
- C11 : ÉCHEC ; mesure (0.48, -0.02801) ; seuil (0.5877, 0)
- C12 : OK ; mesure (0.04108, 2.472) ; seuil (0.5, 40)
- C13 : OK ; mesure (1.671, 0.4696) ; seuil 0
- C14 : OK ; mesure 0.1962 ; seuil 0.04
- C15 : OK ; mesure non applicable (couvert) ; seuil None
- C16 : ÉCHEC ; mesure None ; seuil 0.6
- C2 : OK ; mesure 1.175 ; seuil 0.5
- C3 : OK ; mesure 2.386 ; seuil 2
- C4 : OK ; mesure 1.125 ; seuil 0
- C10 : OK ; mesure 0.009598 ; seuil 0.05

### R0175 (r-coussin-plancher {W_jours: 7, f_plancher: 0.06})
- C1 : ÉCHEC ; mesure 2.16e-10 ; seuil 0.95
- C5 : ÉCHEC ; mesure {2020: 2.513, 2021: 3.244, 2022: -1.445, 2023: 1.758, 2024: 1.622, 2025: -0.1099} ; seuil {sharpe_min: -1, positives_min: 4}
- C6 : ÉCHEC ; mesure 0.2883 ; seuil 0.2
- C7 : ÉCHEC ; mesure None ; seuil {part_voisins_min: 0.75, ratio: 0.6, sharpe_voisin_min: 0.5}
- C8 : OK ; mesure (3.023, 0.2292) ; seuil (2, 0.3)
- C9 : OK ; mesure 5.135e-16 ; seuil {aleatoires: 20, fixes: 3, part_non_pleine_min: 0.4, tolerance: 1e-09}
- C11 : ÉCHEC ; mesure (0.5705, 0.06267) ; seuil (0.6132, 0)
- C12 : OK ; mesure (0.02847, 1.609) ; seuil (0.5, 40)
- C13 : OK ; mesure (1.721, 0.5178) ; seuil 0
- C14 : OK ; mesure 0.2393 ; seuil 0.04
- C15 : OK ; mesure non applicable (couvert) ; seuil None
- C16 : ÉCHEC ; mesure None ; seuil 0.6
- C2 : OK ; mesure 1.226 ; seuil 0.5
- C3 : OK ; mesure 2.64 ; seuil 2
- C4 : OK ; mesure 1.19 ; seuil 0
- C10 : OK ; mesure 0.005199 ; seuil 0.05

### R0176 (r-coussin-plancher {W_jours: 14, f_plancher: 0.01})
- C1 : ÉCHEC ; mesure 5.523e-07 ; seuil 0.95
- C5 : ÉCHEC ; mesure {2020: 3.637, 2021: 4.865, 2022: -2.388, 2023: 5.476, 2024: 2.397, 2025: -0.2393} ; seuil {sharpe_min: -1, positives_min: 4}
- C6 : OK ; mesure 0.0823 ; seuil 0.2
- C7 : ÉCHEC ; mesure None ; seuil {part_voisins_min: 0.75, ratio: 0.6, sharpe_voisin_min: 0.5}
- C8 : OK ; mesure (2.491, 0.03872) ; seuil (2, 0.3)
- C9 : OK ; mesure 5.274e-16 ; seuil {aleatoires: 20, fixes: 3, part_non_pleine_min: 0.4, tolerance: 1e-09}
- C11 : OK ; mesure (1.035, 0.4656) ; seuil (0.8505, 0)
- C12 : OK ; mesure (0.09904, 2.05) ; seuil (0.5, 40)
- C13 : OK ; mesure (2.609, 0.5011) ; seuil 0
- C14 : OK ; mesure 0.07044 ; seuil 0.04
- C15 : OK ; mesure non applicable (couvert) ; seuil None
- C16 : ÉCHEC ; mesure None ; seuil 0.6
- C2 : OK ; mesure 1.701 ; seuil 0.5
- C3 : OK ; mesure 2.685 ; seuil 2
- C4 : OK ; mesure 1.506 ; seuil 0
- C10 : OK ; mesure 0.005599 ; seuil 0.05

### R0177 (r-coussin-plancher {W_jours: 14, f_plancher: 0.016})
- C1 : ÉCHEC ; mesure 1.802e-08 ; seuil 0.95
- C5 : ÉCHEC ; mesure {2020: 2.644, 2021: 4.4, 2022: -1.629, 2023: 2.118, 2024: 2.614, 2025: -0.4003} ; seuil {sharpe_min: -1, positives_min: 4}
- C6 : OK ; mesure 0.1143 ; seuil 0.2
- C7 : OK ; mesure 1 ; seuil {part_voisins_min: 0.75, ratio: 0.6, sharpe_voisin_min: 0.5}
- C8 : OK ; mesure (2.599, 0.072) ; seuil (2, 0.3)
- C9 : OK ; mesure 4.718e-16 ; seuil {aleatoires: 20, fixes: 3, part_non_pleine_min: 0.4, tolerance: 1e-09}
- C11 : OK ; mesure (0.8206, 0.2601) ; seuil (0.7616, 0)
- C12 : OK ; mesure (0.07267, 2.304) ; seuil (0.5, 40)
- C13 : OK ; mesure (2.135, 0.6848) ; seuil 0
- C14 : OK ; mesure 0.1042 ; seuil 0.04
- C15 : OK ; mesure non applicable (couvert) ; seuil None
- C16 : ÉCHEC ; mesure None ; seuil 0.6
- C2 : OK ; mesure 1.523 ; seuil 0.5
- C3 : OK ; mesure 2.654 ; seuil 2
- C4 : OK ; mesure 1.403 ; seuil 0
- C10 : OK ; mesure 0.004999 ; seuil 0.05

### R0178 (r-coussin-plancher {W_jours: 14, f_plancher: 0.025})
- C1 : ÉCHEC ; mesure 3.064e-10 ; seuil 0.95
- C5 : ÉCHEC ; mesure {2020: 3.257, 2021: 3.618, 2022: -1.6, 2023: 1.688, 2024: 1.916, 2025: -0.8039} ; seuil {sharpe_min: -1, positives_min: 4}
- C6 : OK ; mesure 0.1893 ; seuil 0.2
- C7 : OK ; mesure 1 ; seuil {part_voisins_min: 0.75, ratio: 0.6, sharpe_voisin_min: 0.5}
- C8 : ÉCHEC ; mesure (1.891, 0.1216) ; seuil (2, 0.3)
- C9 : OK ; mesure 4.996e-16 ; seuil {aleatoires: 20, fixes: 3, part_non_pleine_min: 0.4, tolerance: 1e-09}
- C11 : ÉCHEC ; mesure (0.5511, 0.01182) ; seuil (0.6314, 0)
- C12 : OK ; mesure (0.06245, 3.352) ; seuil (0.5, 40)
- C13 : OK ; mesure (1.947, 0.3794) ; seuil 0
- C14 : OK ; mesure 0.1435 ; seuil 0.04
- C15 : OK ; mesure non applicable (couvert) ; seuil None
- C16 : ÉCHEC ; mesure None ; seuil 0.6
- C2 : OK ; mesure 1.263 ; seuil 0.5
- C3 : OK ; mesure 2.425 ; seuil 2
- C4 : OK ; mesure 1.178 ; seuil 0
- C10 : OK ; mesure 0.0104 ; seuil 0.05

### R0179 (r-coussin-plancher {W_jours: 14, f_plancher: 0.04})
- C1 : ÉCHEC ; mesure 1.005e-10 ; seuil 0.95
- C5 : ÉCHEC ; mesure {2020: 2.517, 2021: 3.397, 2022: -1.882, 2023: 1.846, 2024: 1.643, 2025: -0.08329} ; seuil {sharpe_min: -1, positives_min: 4}
- C6 : ÉCHEC ; mesure 0.2669 ; seuil 0.2
- C7 : OK ; mesure 1 ; seuil {part_voisins_min: 0.75, ratio: 0.6, sharpe_voisin_min: 0.5}
- C8 : ÉCHEC ; mesure (1.697, 0.1611) ; seuil (2, 0.3)
- C9 : OK ; mesure 2.359e-16 ; seuil {aleatoires: 20, fixes: 3, part_non_pleine_min: 0.4, tolerance: 1e-09}
- C11 : ÉCHEC ; mesure (0.4431, -0.1001) ; seuil (0.5974, 0)
- C12 : OK ; mesure (0.04693, 2.486) ; seuil (0.5, 40)
- C13 : OK ; mesure (1.651, 0.544) ; seuil 0
- C14 : OK ; mesure 0.17 ; seuil 0.04
- C15 : OK ; mesure non applicable (couvert) ; seuil None
- C16 : ÉCHEC ; mesure None ; seuil 0.6
- C2 : OK ; mesure 1.195 ; seuil 0.5
- C3 : OK ; mesure 2.326 ; seuil 2
- C4 : OK ; mesure 1.136 ; seuil 0
- C10 : OK ; mesure 0.0132 ; seuil 0.05

### R0180 (r-coussin-plancher {W_jours: 14, f_plancher: 0.06})
- C1 : ÉCHEC ; mesure 1.621e-10 ; seuil 0.95
- C5 : ÉCHEC ; mesure {2020: 2.635, 2021: 3.134, 2022: -1.491, 2023: 1.818, 2024: 1.684, 2025: -0.1142} ; seuil {sharpe_min: -1, positives_min: 4}
- C6 : ÉCHEC ; mesure 0.2872 ; seuil 0.2
- C7 : ÉCHEC ; mesure None ; seuil {part_voisins_min: 0.75, ratio: 0.6, sharpe_voisin_min: 0.5}
- C8 : OK ; mesure (2.466, 0.2098) ; seuil (2, 0.3)
- C9 : OK ; mesure 2.984e-16 ; seuil {aleatoires: 20, fixes: 3, part_non_pleine_min: 0.4, tolerance: 1e-09}
- C11 : ÉCHEC ; mesure (0.5317, 0.007689) ; seuil (0.6052, 0)
- C12 : OK ; mesure (0.03219, 1.746) ; seuil (0.5, 40)
- C13 : OK ; mesure (1.755, 0.4117) ; seuil 0
- C14 : OK ; mesure 0.2204 ; seuil 0.04
- C15 : OK ; mesure non applicable (couvert) ; seuil None
- C16 : ÉCHEC ; mesure None ; seuil 0.6
- C2 : OK ; mesure 1.21 ; seuil 0.5
- C3 : OK ; mesure 2.519 ; seuil 2
- C4 : OK ; mesure 1.17 ; seuil 0
- C10 : OK ; mesure 0.006599 ; seuil 0.05

### R0181 (r-coussin-plancher {W_jours: 28, f_plancher: 0.01})
- C1 : ÉCHEC ; mesure 5.515e-06 ; seuil 0.95
- C5 : ÉCHEC ; mesure {2020: 3.559, 2021: 4.756, 2022: -2.144, 2023: 2.644, 2024: 3.021, 2025: 0.314} ; seuil {sharpe_min: -1, positives_min: 4}
- C6 : OK ; mesure 0.08959 ; seuil 0.2
- C7 : ÉCHEC ; mesure None ; seuil {part_voisins_min: 0.75, ratio: 0.6, sharpe_voisin_min: 0.5}
- C8 : OK ; mesure (3.243, 0.04633) ; seuil (2, 0.3)
- C9 : OK ; mesure 2.984e-16 ; seuil {aleatoires: 20, fixes: 3, part_non_pleine_min: 0.4, tolerance: 1e-09}
- C11 : OK ; mesure (1.27, 0.7346) ; seuil (0.954, 0)
- C12 : OK ; mesure (0.08243, 1.988) ; seuil (0.5, 40)
- C13 : OK ; mesure (2.444, 1.171) ; seuil 0
- C14 : OK ; mesure 0.08533 ; seuil 0.04
- C15 : OK ; mesure non applicable (couvert) ; seuil None
- C16 : ÉCHEC ; mesure None ; seuil 0.6
- C2 : OK ; mesure 1.908 ; seuil 0.5
- C3 : OK ; mesure 3.169 ; seuil 2
- C4 : OK ; mesure 1.728 ; seuil 0
- C10 : OK ; mesure 0.0018 ; seuil 0.05

### R0182 (r-coussin-plancher {W_jours: 28, f_plancher: 0.016})
- C1 : ÉCHEC ; mesure 6.483e-07 ; seuil 0.95
- C5 : ÉCHEC ; mesure {2020: 3.858, 2021: 4.928, 2022: -2.413, 2023: 2.086, 2024: 2.421, 2025: -0.02451} ; seuil {sharpe_min: -1, positives_min: 4}
- C6 : OK ; mesure 0.1384 ; seuil 0.2
- C7 : OK ; mesure 1 ; seuil {part_voisins_min: 0.75, ratio: 0.6, sharpe_voisin_min: 0.5}
- C8 : OK ; mesure (3.454, 0.06537) ; seuil (2, 0.3)
- C9 : OK ; mesure 3.747e-16 ; seuil {aleatoires: 20, fixes: 3, part_non_pleine_min: 0.4, tolerance: 1e-09}
- C11 : OK ; mesure (1.117, 0.5519) ; seuil (0.9062, 0)
- C12 : OK ; mesure (0.06445, 2.188) ; seuil (0.5, 40)
- C13 : OK ; mesure (2.509, 0.8881) ; seuil 0
- C14 : OK ; mesure 0.1171 ; seuil 0.04
- C15 : OK ; mesure non applicable (couvert) ; seuil None
- C16 : ÉCHEC ; mesure None ; seuil 0.6
- C2 : OK ; mesure 1.812 ; seuil 0.5
- C3 : OK ; mesure 3.064 ; seuil 2
- C4 : OK ; mesure 1.683 ; seuil 0
- C10 : OK ; mesure 0.0022 ; seuil 0.05

### R0183 (r-coussin-plancher {W_jours: 28, f_plancher: 0.025})
- C1 : ÉCHEC ; mesure 6.368e-09 ; seuil 0.95
- C5 : ÉCHEC ; mesure {2020: 3.409, 2021: 4.114, 2022: -1.311, 2023: 1.291, 2024: 2.251, 2025: -0.7932} ; seuil {sharpe_min: -1, positives_min: 4}
- C6 : OK ; mesure 0.1521 ; seuil 0.2
- C7 : OK ; mesure 1 ; seuil {part_voisins_min: 0.75, ratio: 0.6, sharpe_voisin_min: 0.5}
- C8 : OK ; mesure (2.571, 0.1021) ; seuil (2, 0.3)
- C9 : OK ; mesure 1.527e-16 ; seuil {aleatoires: 20, fixes: 3, part_non_pleine_min: 0.4, tolerance: 1e-09}
- C11 : OK ; mesure (0.7386, 0.1676) ; seuil (0.7334, 0)
- C12 : OK ; mesure (0.05774, 3.086) ; seuil (0.5, 40)
- C13 : OK ; mesure (2.188, 0.5534) ; seuil 0
- C14 : OK ; mesure 0.1538 ; seuil 0.04
- C15 : OK ; mesure non applicable (couvert) ; seuil None
- C16 : ÉCHEC ; mesure None ; seuil 0.6
- C2 : OK ; mesure 1.467 ; seuil 0.5
- C3 : OK ; mesure 2.7 ; seuil 2
- C4 : OK ; mesure 1.375 ; seuil 0
- C10 : OK ; mesure 0.005999 ; seuil 0.05

### R0184 (r-coussin-plancher {W_jours: 28, f_plancher: 0.04})
- C1 : ÉCHEC ; mesure 1.43e-10 ; seuil 0.95
- C5 : ÉCHEC ; mesure {2020: 2.957, 2021: 3.447, 2022: -1.912, 2023: 1.774, 2024: 1.698, 2025: -0.2752} ; seuil {sharpe_min: -1, positives_min: 4}
- C6 : ÉCHEC ; mesure 0.2965 ; seuil 0.2
- C7 : OK ; mesure 1 ; seuil {part_voisins_min: 0.75, ratio: 0.6, sharpe_voisin_min: 0.5}
- C8 : ÉCHEC ; mesure (1.642, 0.1547) ; seuil (2, 0.3)
- C9 : OK ; mesure 4.025e-16 ; seuil {aleatoires: 20, fixes: 3, part_non_pleine_min: 0.4, tolerance: 1e-09}
- C11 : ÉCHEC ; mesure (0.4823, -0.05571) ; seuil (0.5978, 0)
- C12 : OK ; mesure (0.04894, 2.782) ; seuil (0.5, 40)
- C13 : OK ; mesure (1.717, 0.4771) ; seuil 0
- C14 : OK ; mesure 0.1717 ; seuil 0.04
- C15 : OK ; mesure non applicable (couvert) ; seuil None
- C16 : ÉCHEC ; mesure None ; seuil 0.6
- C2 : OK ; mesure 1.196 ; seuil 0.5
- C3 : OK ; mesure 2.315 ; seuil 2
- C4 : OK ; mesure 1.134 ; seuil 0
- C10 : OK ; mesure 0.0126 ; seuil 0.05

### R0185 (r-coussin-plancher {W_jours: 28, f_plancher: 0.06})
- C1 : ÉCHEC ; mesure 1.87e-10 ; seuil 0.95
- C5 : ÉCHEC ; mesure {2020: 2.824, 2021: 3.322, 2022: -1.339, 2023: 1.758, 2024: 1.548, 2025: -0.323} ; seuil {sharpe_min: -1, positives_min: 4}
- C6 : ÉCHEC ; mesure 0.2808 ; seuil 0.2
- C7 : ÉCHEC ; mesure None ; seuil {part_voisins_min: 0.75, ratio: 0.6, sharpe_voisin_min: 0.5}
- C8 : OK ; mesure (2.288, 0.2046) ; seuil (2, 0.3)
- C9 : OK ; mesure 1.249e-15 ; seuil {aleatoires: 20, fixes: 3, part_non_pleine_min: 0.4, tolerance: 1e-09}
- C11 : ÉCHEC ; mesure (0.5341, 0.01026) ; seuil (0.6081, 0)
- C12 : OK ; mesure (0.03409, 2.143) ; seuil (0.5, 40)
- C13 : OK ; mesure (1.82, 0.3323) ; seuil 0
- C14 : OK ; mesure 0.2211 ; seuil 0.04
- C15 : OK ; mesure non applicable (couvert) ; seuil None
- C16 : ÉCHEC ; mesure None ; seuil 0.6
- C2 : OK ; mesure 1.216 ; seuil 0.5
- C3 : OK ; mesure 2.528 ; seuil 2
- C4 : OK ; mesure 1.173 ; seuil 0
- C10 : OK ; mesure 0.007199 ; seuil 0.05

### R0186 (r-coussin-plancher {W_jours: 56, f_plancher: 0.01})
- C1 : ÉCHEC ; mesure 9.607e-05 ; seuil 0.95
- C5 : ÉCHEC ; mesure {2020: 3.507, 2021: 5.001, 2022: -1.831, 2023: 1.764, 2024: 2.929, 2025: 0.435} ; seuil {sharpe_min: -1, positives_min: 4}
- C6 : OK ; mesure 0.05698 ; seuil 0.2
- C7 : ÉCHEC ; mesure None ; seuil {part_voisins_min: 0.75, ratio: 0.6, sharpe_voisin_min: 0.5}
- C8 : OK ; mesure (3.935, 0.0426) ; seuil (2, 0.3)
- C9 : OK ; mesure 3.886e-16 ; seuil {aleatoires: 20, fixes: 3, part_non_pleine_min: 0.4, tolerance: 1e-09}
- C11 : OK ; mesure (1.555, 1.016) ; seuil (1.093, 0)
- C12 : OK ; mesure (0.07593, 1.956) ; seuil (0.5, 40)
- C13 : OK ; mesure (2.866, 1.262) ; seuil 0
- C14 : OK ; mesure 0.09317 ; seuil 0.04
- C15 : OK ; mesure non applicable (couvert) ; seuil None
- C16 : ÉCHEC ; mesure None ; seuil 0.6
- C2 : OK ; mesure 2.186 ; seuil 0.5
- C3 : OK ; mesure 3.551 ; seuil 2
- C4 : OK ; mesure 1.998 ; seuil 0
- C10 : OK ; mesure 0.0012 ; seuil 0.05

### R0187 (r-coussin-plancher {W_jours: 56, f_plancher: 0.016})
- C1 : ÉCHEC ; mesure 1.518e-05 ; seuil 0.95
- C5 : ÉCHEC ; mesure {2020: 3.753, 2021: 4.945, 2022: -1.241, 2023: 2.351, 2024: 2.973, 2025: -0.3669} ; seuil {sharpe_min: -1, positives_min: 4}
- C6 : OK ; mesure 0.0767 ; seuil 0.2
- C7 : OK ; mesure 1 ; seuil {part_voisins_min: 0.75, ratio: 0.6, sharpe_voisin_min: 0.5}
- C8 : OK ; mesure (3.718, 0.05125) ; seuil (2, 0.3)
- C9 : OK ; mesure 4.51e-16 ; seuil {aleatoires: 20, fixes: 3, part_non_pleine_min: 0.4, tolerance: 1e-09}
- C11 : OK ; mesure (1.382, 0.7951) ; seuil (1.045, 0)
- C12 : OK ; mesure (0.06307, 2.086) ; seuil (0.5, 40)
- C13 : OK ; mesure (2.898, 0.9891) ; seuil 0
- C14 : OK ; mesure 0.1168 ; seuil 0.04
- C15 : OK ; mesure non applicable (couvert) ; seuil None
- C16 : ÉCHEC ; mesure None ; seuil 0.6
- C2 : OK ; mesure 2.091 ; seuil 0.5
- C3 : OK ; mesure 3.354 ; seuil 2
- C4 : OK ; mesure 1.949 ; seuil 0
- C10 : OK ; mesure 0.0012 ; seuil 0.05

### R0188 (r-coussin-plancher {W_jours: 56, f_plancher: 0.025})
- C1 : ÉCHEC ; mesure 2.688e-08 ; seuil 0.95
- C5 : ÉCHEC ; mesure {2020: 3.338, 2021: 4.435, 2022: -2.039, 2023: 1.333, 2024: 1.975, 2025: -0.2567} ; seuil {sharpe_min: -1, positives_min: 4}
- C6 : OK ; mesure 0.1446 ; seuil 0.2
- C7 : OK ; mesure 1 ; seuil {part_voisins_min: 0.75, ratio: 0.6, sharpe_voisin_min: 0.5}
- C8 : OK ; mesure (2.516, 0.07948) ; seuil (2, 0.3)
- C9 : OK ; mesure 3.955e-16 ; seuil {aleatoires: 20, fixes: 3, part_non_pleine_min: 0.4, tolerance: 1e-09}
- C11 : OK ; mesure (0.7779, 0.1678) ; seuil (0.7723, 0)
- C12 : OK ; mesure (0.06224, 2.711) ; seuil (0.5, 40)
- C13 : OK ; mesure (2.35, 0.56) ; seuil 0
- C14 : OK ; mesure 0.1333 ; seuil 0.04
- C15 : OK ; mesure non applicable (couvert) ; seuil None
- C16 : ÉCHEC ; mesure None ; seuil 0.6
- C2 : OK ; mesure 1.545 ; seuil 0.5
- C3 : OK ; mesure 2.622 ; seuil 2
- C4 : OK ; mesure 1.442 ; seuil 0
- C10 : OK ; mesure 0.006399 ; seuil 0.05

### R0189 (r-coussin-plancher {W_jours: 56, f_plancher: 0.04})
- C1 : ÉCHEC ; mesure 1.234e-09 ; seuil 0.95
- C5 : ÉCHEC ; mesure {2020: 3.007, 2021: 3.59, 2022: -1.498, 2023: 1.751, 2024: 1.595, 2025: -0.05988} ; seuil {sharpe_min: -1, positives_min: 4}
- C6 : ÉCHEC ; mesure 0.2059 ; seuil 0.2
- C7 : OK ; mesure 1 ; seuil {part_voisins_min: 0.75, ratio: 0.6, sharpe_voisin_min: 0.5}
- C8 : OK ; mesure (2.161, 0.1363) ; seuil (2, 0.3)
- C9 : OK ; mesure 7.147e-16 ; seuil {aleatoires: 20, fixes: 3, part_non_pleine_min: 0.4, tolerance: 1e-09}
- C11 : ÉCHEC ; mesure (0.5945, 0.04415) ; seuil (0.6755, 0)
- C12 : OK ; mesure (0.04648, 2.721) ; seuil (0.5, 40)
- C13 : OK ; mesure (2.014, 0.4843) ; seuil 0
- C14 : OK ; mesure 0.1825 ; seuil 0.04
- C15 : OK ; mesure non applicable (couvert) ; seuil None
- C16 : ÉCHEC ; mesure None ; seuil 0.6
- C2 : OK ; mesure 1.351 ; seuil 0.5
- C3 : OK ; mesure 2.549 ; seuil 2
- C4 : OK ; mesure 1.285 ; seuil 0
- C10 : OK ; mesure 0.008598 ; seuil 0.05

### R0190 (r-coussin-plancher {W_jours: 56, f_plancher: 0.06})
- C1 : ÉCHEC ; mesure 2.602e-09 ; seuil 0.95
- C5 : OK ; mesure {2020: 2.523, 2021: 3.622, 2022: -0.8528, 2023: 1.804, 2024: 1.626, 2025: -0.1783} ; seuil {sharpe_min: -1, positives_min: 4}
- C6 : ÉCHEC ; mesure 0.2092 ; seuil 0.2
- C7 : ÉCHEC ; mesure None ; seuil {part_voisins_min: 0.75, ratio: 0.6, sharpe_voisin_min: 0.5}
- C8 : OK ; mesure (2.939, 0.1764) ; seuil (2, 0.3)
- C9 : OK ; mesure 2.22e-16 ; seuil {aleatoires: 20, fixes: 3, part_non_pleine_min: 0.4, tolerance: 1e-09}
- C11 : ÉCHEC ; mesure (0.6747, 0.1127) ; seuil (0.6985, 0)
- C12 : OK ; mesure (0.03242, 2.011) ; seuil (0.5, 40)
- C13 : OK ; mesure (2.083, 0.4049) ; seuil 0
- C14 : OK ; mesure 0.2346 ; seuil 0.04
- C15 : OK ; mesure non applicable (couvert) ; seuil None
- C16 : ÉCHEC ; mesure None ; seuil 0.6
- C2 : OK ; mesure 1.397 ; seuil 0.5
- C3 : OK ; mesure 2.807 ; seuil 2
- C4 : OK ; mesure 1.35 ; seuil 0
- C10 : OK ; mesure 0.003599 ; seuil 0.05

### R0191 (r-coussin-plancher {W_jours: 112, f_plancher: 0.01})
- C1 : ÉCHEC ; mesure 0.0003948 ; seuil 0.95
- C5 : ÉCHEC ; mesure {2020: 3.426, 2021: 5.338, 2022: -3.214, 2023: 1.894, 2024: 2.132, 2025: 1.119} ; seuil {sharpe_min: -1, positives_min: 4}
- C6 : OK ; mesure 0.05619 ; seuil 0.2
- C7 : ÉCHEC ; mesure None ; seuil {part_voisins_min: 0.75, ratio: 0.6, sharpe_voisin_min: 0.5}
- C8 : OK ; mesure (3.646, 0.0324) ; seuil (2, 0.3)
- C9 : OK ; mesure 2.706e-16 ; seuil {aleatoires: 20, fixes: 3, part_non_pleine_min: 0.4, tolerance: 1e-09}
- C11 : OK ; mesure (1.628, 1.06) ; seuil (1.14, 0)
- C12 : OK ; mesure (0.08121, 1.971) ; seuil (0.5, 40)
- C13 : OK ; mesure (3.124, 1.146) ; seuil 0
- C14 : OK ; mesure 0.08702 ; seuil 0.04
- C15 : OK ; mesure non applicable (couvert) ; seuil None
- C16 : ÉCHEC ; mesure None ; seuil 0.6
- C2 : OK ; mesure 2.279 ; seuil 0.5
- C3 : OK ; mesure 3.445 ; seuil 2
- C4 : OK ; mesure 2.064 ; seuil 0
- C10 : OK ; mesure 0.0007998 ; seuil 0.05

### R0192 (r-coussin-plancher {W_jours: 112, f_plancher: 0.016})
- C1 : ÉCHEC ; mesure 1.043e-05 ; seuil 0.95
- C5 : ÉCHEC ; mesure {2020: 3.572, 2021: 5.189, 2022: -2.657, 2023: 1.656, 2024: 1.91, 2025: 0.6093} ; seuil {sharpe_min: -1, positives_min: 4}
- C6 : OK ; mesure 0.07717 ; seuil 0.2
- C7 : ÉCHEC ; mesure None ; seuil {part_voisins_min: 0.75, ratio: 0.6, sharpe_voisin_min: 0.5}
- C8 : OK ; mesure (3.562, 0.0409) ; seuil (2, 0.3)
- C9 : OK ; mesure 5.343e-16 ; seuil {aleatoires: 20, fixes: 3, part_non_pleine_min: 0.4, tolerance: 1e-09}
- C11 : OK ; mesure (1.35, 0.7141) ; seuil (1.054, 0)
- C12 : OK ; mesure (0.06927, 2.016) ; seuil (0.5, 40)
- C13 : OK ; mesure (2.989, 0.9769) ; seuil 0
- C14 : OK ; mesure 0.1044 ; seuil 0.04
- C15 : OK ; mesure non applicable (couvert) ; seuil None
- C16 : ÉCHEC ; mesure None ; seuil 0.6
- C2 : OK ; mesure 2.108 ; seuil 0.5
- C3 : OK ; mesure 3.279 ; seuil 2
- C4 : OK ; mesure 1.947 ; seuil 0
- C10 : OK ; mesure 0.0016 ; seuil 0.05

### R0193 (r-coussin-plancher {W_jours: 112, f_plancher: 0.025})
- C1 : ÉCHEC ; mesure 3.837e-08 ; seuil 0.95
- C5 : ÉCHEC ; mesure {2020: 3.349, 2021: 3.913, 2022: -1.771, 2023: 0.9443, 2024: 2.191, 2025: 0.4126} ; seuil {sharpe_min: -1, positives_min: 4}
- C6 : OK ; mesure 0.1266 ; seuil 0.2
- C7 : ÉCHEC ; mesure None ; seuil {part_voisins_min: 0.75, ratio: 0.6, sharpe_voisin_min: 0.5}
- C8 : OK ; mesure (2.514, 0.07076) ; seuil (2, 0.3)
- C9 : OK ; mesure 3.678e-16 ; seuil {aleatoires: 20, fixes: 3, part_non_pleine_min: 0.4, tolerance: 1e-09}
- C11 : ÉCHEC ; mesure (0.7488, 0.1473) ; seuil (0.7798, 0)
- C12 : OK ; mesure (0.06457, 2.367) ; seuil (0.5, 40)
- C13 : OK ; mesure (2.217, 0.7794) ; seuil 0
- C14 : OK ; mesure 0.1192 ; seuil 0.04
- C15 : OK ; mesure non applicable (couvert) ; seuil None
- C16 : ÉCHEC ; mesure None ; seuil 0.6
- C2 : OK ; mesure 1.56 ; seuil 0.5
- C3 : OK ; mesure 2.716 ; seuil 2
- C4 : OK ; mesure 1.452 ; seuil 0
- C10 : OK ; mesure 0.006199 ; seuil 0.05

### R0194 (r-coussin-plancher {W_jours: 112, f_plancher: 0.04})
- C1 : ÉCHEC ; mesure 1.932e-09 ; seuil 0.95
- C5 : ÉCHEC ; mesure {2020: 2.652, 2021: 3.258, 2022: -1.775, 2023: 1.312, 2024: 1.708, 2025: 0.7946} ; seuil {sharpe_min: -1, positives_min: 4}
- C6 : OK ; mesure 0.1741 ; seuil 0.2
- C7 : ÉCHEC ; mesure None ; seuil {part_voisins_min: 0.75, ratio: 0.6, sharpe_voisin_min: 0.5}
- C8 : OK ; mesure (2.126, 0.1034) ; seuil (2, 0.3)
- C9 : OK ; mesure 9.714e-16 ; seuil {aleatoires: 20, fixes: 3, part_non_pleine_min: 0.4, tolerance: 1e-09}
- C11 : ÉCHEC ; mesure (0.5551, -0.06197) ; seuil (0.6896, 0)
- C12 : OK ; mesure (0.05111, 2.55) ; seuil (0.5, 40)
- C13 : OK ; mesure (1.886, 0.7593) ; seuil 0
- C14 : OK ; mesure 0.1603 ; seuil 0.04
- C15 : OK ; mesure non applicable (couvert) ; seuil None
- C16 : ÉCHEC ; mesure None ; seuil 0.6
- C2 : OK ; mesure 1.379 ; seuil 0.5
- C3 : OK ; mesure 2.529 ; seuil 2
- C4 : OK ; mesure 1.304 ; seuil 0
- C10 : OK ; mesure 0.0106 ; seuil 0.05

### R0195 (r-coussin-plancher {W_jours: 112, f_plancher: 0.06})
- C1 : ÉCHEC ; mesure 3.318e-10 ; seuil 0.95
- C5 : ÉCHEC ; mesure {2020: 2.137, 2021: 3.094, 2022: -1.324, 2023: 1.769, 2024: 1.319, 2025: 0.5477} ; seuil {sharpe_min: -1, positives_min: 4}
- C6 : ÉCHEC ; mesure 0.2128 ; seuil 0.2
- C7 : ÉCHEC ; mesure None ; seuil {part_voisins_min: 0.75, ratio: 0.6, sharpe_voisin_min: 0.5}
- C8 : ÉCHEC ; mesure (1.951, 0.1521) ; seuil (2, 0.3)
- C9 : OK ; mesure 2.429e-16 ; seuil {aleatoires: 20, fixes: 3, part_non_pleine_min: 0.4, tolerance: 1e-09}
- C11 : ÉCHEC ; mesure (0.4798, -0.09342) ; seuil (0.6277, 0)
- C12 : OK ; mesure (0.03993, 2.136) ; seuil (0.5, 40)
- C13 : OK ; mesure (1.747, 0.5797) ; seuil 0
- C14 : OK ; mesure 0.1909 ; seuil 0.04
- C15 : OK ; mesure non applicable (couvert) ; seuil None
- C16 : ÉCHEC ; mesure None ; seuil 0.6
- C2 : OK ; mesure 1.255 ; seuil 0.5
- C3 : OK ; mesure 2.495 ; seuil 2
- C4 : OK ; mesure 1.203 ; seuil 0
- C10 : OK ; mesure 0.009598 ; seuil 0.05

### R0196 (t-ecart {L_jours: 30, zs_saturation: 0.15})
- C1 : ÉCHEC ; mesure 3.665e-08 ; seuil 0.95
- C5 : ÉCHEC ; mesure {2020: 2.823, 2021: 3.571, 2022: -1.576, 2023: 1.939, 2024: 1.718, 2025: -0.4294} ; seuil {sharpe_min: -1, positives_min: 4}
- C6 : OK ; mesure 0.1777 ; seuil 0.2
- C7 : ÉCHEC ; mesure None ; seuil {part_voisins_min: 0.75, ratio: 0.6, sharpe_voisin_min: 0.5}
- C8 : OK ; mesure (2.806, 0.1239) ; seuil (2, 0.3)
- C9 : OK ; mesure 4.857e-16 ; seuil {aleatoires: 20, fixes: 3, part_non_pleine_min: 0.4, tolerance: 1e-09}
- C11 : OK ; mesure (0.7927, 0.1613) ; seuil (0.7719, 0)
- C12 : OK ; mesure (0.06767, 5.082) ; seuil (0.5, 40)
- C13 : OK ; mesure (2.058, 0.8016) ; seuil 0
- C14 : OK ; mesure 0.2061 ; seuil 0.04
- C15 : OK ; mesure non applicable (couvert) ; seuil None
- C16 : ÉCHEC ; mesure None ; seuil 0.6
- C2 : OK ; mesure 1.544 ; seuil 0.5
- C3 : OK ; mesure 2.849 ; seuil 2
- C4 : OK ; mesure 1.431 ; seuil 0
- C10 : OK ; mesure 0.004199 ; seuil 0.05

### R0197 (t-ecart {L_jours: 30, zs_saturation: 0.25})
- C1 : ÉCHEC ; mesure 6.064e-08 ; seuil 0.95
- C5 : ÉCHEC ; mesure {2020: 2.905, 2021: 3.67, 2022: -1.613, 2023: 1.948, 2024: 1.763, 2025: -0.4329} ; seuil {sharpe_min: -1, positives_min: 4}
- C6 : OK ; mesure 0.1766 ; seuil 0.2
- C7 : ÉCHEC ; mesure None ; seuil {part_voisins_min: 0.75, ratio: 0.6, sharpe_voisin_min: 0.5}
- C8 : OK ; mesure (2.922, 0.124) ; seuil (2, 0.3)
- C9 : OK ; mesure 4.233e-16 ; seuil {aleatoires: 20, fixes: 3, part_non_pleine_min: 0.4, tolerance: 1e-09}
- C11 : OK ; mesure (0.8413, 0.2107) ; seuil (0.7957, 0)
- C12 : OK ; mesure (0.06675, 4.996) ; seuil (0.5, 40)
- C13 : OK ; mesure (2.125, 0.819) ; seuil 0
- C14 : OK ; mesure 0.2102 ; seuil 0.04
- C15 : OK ; mesure non applicable (couvert) ; seuil None
- C16 : ÉCHEC ; mesure None ; seuil 0.6
- C2 : OK ; mesure 1.591 ; seuil 0.5
- C3 : OK ; mesure 2.891 ; seuil 2
- C4 : OK ; mesure 1.477 ; seuil 0
- C10 : OK ; mesure 0.003599 ; seuil 0.05

### R0198 (t-ecart {L_jours: 30, zs_saturation: 0.4})
- C1 : ÉCHEC ; mesure 8.464e-08 ; seuil 0.95
- C5 : ÉCHEC ; mesure {2020: 3.007, 2021: 3.752, 2022: -1.697, 2023: 1.945, 2024: 1.833, 2025: -0.4741} ; seuil {sharpe_min: -1, positives_min: 4}
- C6 : OK ; mesure 0.1774 ; seuil 0.2
- C7 : ÉCHEC ; mesure None ; seuil {part_voisins_min: 0.75, ratio: 0.6, sharpe_voisin_min: 0.5}
- C8 : OK ; mesure (3.046, 0.1242) ; seuil (2, 0.3)
- C9 : OK ; mesure 2.22e-16 ; seuil {aleatoires: 20, fixes: 3, part_non_pleine_min: 0.4, tolerance: 1e-09}
- C11 : OK ; mesure (0.8737, 0.2483) ; seuil (0.8161, 0)
- C12 : OK ; mesure (0.06536, 4.772) ; seuil (0.5, 40)
- C13 : OK ; mesure (2.185, 0.833) ; seuil 0
- C14 : OK ; mesure 0.21 ; seuil 0.04
- C15 : OK ; mesure non applicable (couvert) ; seuil None
- C16 : ÉCHEC ; mesure None ; seuil 0.6
- C2 : OK ; mesure 1.632 ; seuil 0.5
- C3 : OK ; mesure 2.925 ; seuil 2
- C4 : OK ; mesure 1.518 ; seuil 0
- C10 : OK ; mesure 0.003399 ; seuil 0.05

### R0199 (t-ecart {L_jours: 30, zs_saturation: 0.65})
- C1 : ÉCHEC ; mesure 6.952e-08 ; seuil 0.95
- C5 : ÉCHEC ; mesure {2020: 2.961, 2021: 3.81, 2022: -1.848, 2023: 2.022, 2024: 1.928, 2025: -0.4808} ; seuil {sharpe_min: -1, positives_min: 4}
- C6 : OK ; mesure 0.1799 ; seuil 0.2
- C7 : ÉCHEC ; mesure None ; seuil {part_voisins_min: 0.75, ratio: 0.6, sharpe_voisin_min: 0.5}
- C8 : OK ; mesure (3.174, 0.1241) ; seuil (2, 0.3)
- C9 : OK ; mesure 1.596e-16 ; seuil {aleatoires: 20, fixes: 3, part_non_pleine_min: 0.4, tolerance: 1e-09}
- C11 : OK ; mesure (0.8803, 0.2707) ; seuil (0.8108, 0)
- C12 : OK ; mesure (0.06586, 4.319) ; seuil (0.5, 40)
- C13 : OK ; mesure (2.169, 0.8398) ; seuil 0
- C14 : OK ; mesure 0.1955 ; seuil 0.04
- C15 : OK ; mesure non applicable (couvert) ; seuil None
- C16 : ÉCHEC ; mesure None ; seuil 0.6
- C2 : OK ; mesure 1.622 ; seuil 0.5
- C3 : OK ; mesure 2.924 ; seuil 2
- C4 : OK ; mesure 1.507 ; seuil 0
- C10 : OK ; mesure 0.003199 ; seuil 0.05

### R0200 (t-ecart {L_jours: 30, zs_saturation: 1})
- C1 : ÉCHEC ; mesure 4.803e-08 ; seuil 0.95
- C5 : ÉCHEC ; mesure {2020: 2.88, 2021: 3.879, 2022: -1.912, 2023: 2.132, 2024: 1.996, 2025: -0.4515} ; seuil {sharpe_min: -1, positives_min: 4}
- C6 : OK ; mesure 0.1823 ; seuil 0.2
- C7 : ÉCHEC ; mesure None ; seuil {part_voisins_min: 0.75, ratio: 0.6, sharpe_voisin_min: 0.5}
- C8 : OK ; mesure (3.33, 0.1229) ; seuil (2, 0.3)
- C9 : OK ; mesure 2.637e-16 ; seuil {aleatoires: 20, fixes: 3, part_non_pleine_min: 0.4, tolerance: 1e-09}
- C11 : OK ; mesure (0.8716, 0.2928) ; seuil (0.7939, 0)
- C12 : OK ; mesure (0.06886, 3.819) ; seuil (0.5, 40)
- C13 : OK ; mesure (2.128, 0.8233) ; seuil 0
- C14 : OK ; mesure 0.1774 ; seuil 0.04
- C15 : OK ; mesure non applicable (couvert) ; seuil None
- C16 : ÉCHEC ; mesure None ; seuil 0.6
- C2 : OK ; mesure 1.588 ; seuil 0.5
- C3 : OK ; mesure 2.903 ; seuil 2
- C4 : OK ; mesure 1.471 ; seuil 0
- C10 : OK ; mesure 0.002799 ; seuil 0.05

### R0201 (t-ecart {L_jours: 50, zs_saturation: 0.15})
- C1 : ÉCHEC ; mesure 1.737e-08 ; seuil 0.95
- C5 : ÉCHEC ; mesure {2020: 2.389, 2021: 3.548, 2022: -1.836, 2023: 1.705, 2024: 1.502, 2025: 0.2254} ; seuil {sharpe_min: -1, positives_min: 4}
- C6 : OK ; mesure 0.1813 ; seuil 0.2
- C7 : ÉCHEC ; mesure None ; seuil {part_voisins_min: 0.75, ratio: 0.6, sharpe_voisin_min: 0.5}
- C8 : OK ; mesure (2.706, 0.1321) ; seuil (2, 0.3)
- C9 : OK ; mesure 2.082e-16 ; seuil {aleatoires: 20, fixes: 3, part_non_pleine_min: 0.4, tolerance: 1e-09}
- C11 : OK ; mesure (0.7576, 0.1401) ; seuil (0.756, 0)
- C12 : OK ; mesure (0.0577, 3.869) ; seuil (0.5, 40)
- C13 : OK ; mesure (1.964, 0.8715) ; seuil 0
- C14 : OK ; mesure 0.2106 ; seuil 0.04
- C15 : OK ; mesure non applicable (couvert) ; seuil None
- C16 : ÉCHEC ; mesure None ; seuil 0.6
- C2 : OK ; mesure 1.512 ; seuil 0.5
- C3 : OK ; mesure 2.845 ; seuil 2
- C4 : OK ; mesure 1.42 ; seuil 0
- C10 : OK ; mesure 0.003999 ; seuil 0.05

### R0202 (t-ecart {L_jours: 50, zs_saturation: 0.25})
- C1 : ÉCHEC ; mesure 1.795e-08 ; seuil 0.95
- C5 : ÉCHEC ; mesure {2020: 2.368, 2021: 3.602, 2022: -1.932, 2023: 1.778, 2024: 1.531, 2025: 0.1605} ; seuil {sharpe_min: -1, positives_min: 4}
- C6 : OK ; mesure 0.1809 ; seuil 0.2
- C7 : OK ; mesure 1 ; seuil {part_voisins_min: 0.75, ratio: 0.6, sharpe_voisin_min: 0.5}
- C8 : OK ; mesure (2.727, 0.132) ; seuil (2, 0.3)
- C9 : OK ; mesure 2.22e-16 ; seuil {aleatoires: 20, fixes: 3, part_non_pleine_min: 0.4, tolerance: 1e-09}
- C11 : OK ; mesure (0.7628, 0.145) ; seuil (0.7601, 0)
- C12 : OK ; mesure (0.05797, 3.818) ; seuil (0.5, 40)
- C13 : OK ; mesure (1.969, 0.887) ; seuil 0
- C14 : OK ; mesure 0.2086 ; seuil 0.04
- C15 : OK ; mesure non applicable (couvert) ; seuil None
- C16 : ÉCHEC ; mesure None ; seuil 0.6
- C2 : OK ; mesure 1.52 ; seuil 0.5
- C3 : OK ; mesure 2.842 ; seuil 2
- C4 : OK ; mesure 1.427 ; seuil 0
- C10 : OK ; mesure 0.004999 ; seuil 0.05

### R0203 (t-ecart {L_jours: 50, zs_saturation: 0.4})
- C1 : ÉCHEC ; mesure 1.881e-08 ; seuil 0.95
- C5 : ÉCHEC ; mesure {2020: 2.398, 2021: 3.577, 2022: -2.025, 2023: 1.917, 2024: 1.593, 2025: -0.004869} ; seuil {sharpe_min: -1, positives_min: 4}
- C6 : OK ; mesure 0.1801 ; seuil 0.2
- C7 : OK ; mesure 1 ; seuil {part_voisins_min: 0.75, ratio: 0.6, sharpe_voisin_min: 0.5}
- C8 : OK ; mesure (2.76, 0.1314) ; seuil (2, 0.3)
- C9 : OK ; mesure 1.874e-16 ; seuil {aleatoires: 20, fixes: 3, part_non_pleine_min: 0.4, tolerance: 1e-09}
- C11 : OK ; mesure (0.7724, 0.1594) ; seuil (0.7547, 0)
- C12 : OK ; mesure (0.06013, 3.706) ; seuil (0.5, 40)
- C13 : OK ; mesure (1.954, 0.8857) ; seuil 0
- C14 : OK ; mesure 0.1992 ; seuil 0.04
- C15 : OK ; mesure non applicable (couvert) ; seuil None
- C16 : ÉCHEC ; mesure None ; seuil 0.6
- C2 : OK ; mesure 1.509 ; seuil 0.5
- C3 : OK ; mesure 2.842 ; seuil 2
- C4 : OK ; mesure 1.414 ; seuil 0
- C10 : OK ; mesure 0.004599 ; seuil 0.05

### R0204 (t-ecart {L_jours: 50, zs_saturation: 0.65})
- C1 : ÉCHEC ; mesure 2.626e-08 ; seuil 0.95
- C5 : ÉCHEC ; mesure {2020: 2.457, 2021: 3.691, 2022: -2.078, 2023: 1.959, 2024: 1.726, 2025: -0.08731} ; seuil {sharpe_min: -1, positives_min: 4}
- C6 : OK ; mesure 0.1803 ; seuil 0.2
- C7 : OK ; mesure 1 ; seuil {part_voisins_min: 0.75, ratio: 0.6, sharpe_voisin_min: 0.5}
- C8 : OK ; mesure (2.941, 0.1303) ; seuil (2, 0.3)
- C9 : OK ; mesure 2.498e-16 ; seuil {aleatoires: 20, fixes: 3, part_non_pleine_min: 0.4, tolerance: 1e-09}
- C11 : OK ; mesure (0.7938, 0.1905) ; seuil (0.7706, 0)
- C12 : OK ; mesure (0.06172, 3.521) ; seuil (0.5, 40)
- C13 : OK ; mesure (2.011, 0.8818) ; seuil 0
- C14 : OK ; mesure 0.1921 ; seuil 0.04
- C15 : OK ; mesure non applicable (couvert) ; seuil None
- C16 : ÉCHEC ; mesure None ; seuil 0.6
- C2 : OK ; mesure 1.541 ; seuil 0.5
- C3 : OK ; mesure 2.871 ; seuil 2
- C4 : OK ; mesure 1.44 ; seuil 0
- C10 : OK ; mesure 0.004399 ; seuil 0.05

### R0205 (t-ecart {L_jours: 50, zs_saturation: 1})
- C1 : ÉCHEC ; mesure 1.844e-08 ; seuil 0.95
- C5 : ÉCHEC ; mesure {2020: 2.479, 2021: 3.631, 2022: -1.96, 2023: 2.054, 2024: 1.818, 2025: -0.1834} ; seuil {sharpe_min: -1, positives_min: 4}
- C6 : OK ; mesure 0.1769 ; seuil 0.2
- C7 : ÉCHEC ; mesure None ; seuil {part_voisins_min: 0.75, ratio: 0.6, sharpe_voisin_min: 0.5}
- C8 : OK ; mesure (3.063, 0.1274) ; seuil (2, 0.3)
- C9 : OK ; mesure 1.735e-16 ; seuil {aleatoires: 20, fixes: 3, part_non_pleine_min: 0.4, tolerance: 1e-09}
- C11 : OK ; mesure (0.7901, 0.223) ; seuil (0.7514, 0)
- C12 : OK ; mesure (0.06369, 3.152) ; seuil (0.5, 40)
- C13 : OK ; mesure (1.975, 0.8411) ; seuil 0
- C14 : OK ; mesure 0.1723 ; seuil 0.04
- C15 : OK ; mesure non applicable (couvert) ; seuil None
- C16 : ÉCHEC ; mesure None ; seuil 0.6
- C2 : OK ; mesure 1.503 ; seuil 0.5
- C3 : OK ; mesure 2.861 ; seuil 2
- C4 : OK ; mesure 1.402 ; seuil 0
- C10 : OK ; mesure 0.004399 ; seuil 0.05

### R0206 (t-ecart {L_jours: 80, zs_saturation: 0.15})
- C1 : ÉCHEC ; mesure 7.44e-10 ; seuil 0.95
- C5 : ÉCHEC ; mesure {2020: 1.327, 2021: 3.285, 2022: -2.472, 2023: 1.441, 2024: 1.609, 2025: 0.1601} ; seuil {sharpe_min: -1, positives_min: 4}
- C6 : ÉCHEC ; mesure 0.2133 ; seuil 0.2
- C7 : ÉCHEC ; mesure None ; seuil {part_voisins_min: 0.75, ratio: 0.6, sharpe_voisin_min: 0.5}
- C8 : ÉCHEC ; mesure (1.834, 0.1443) ; seuil (2, 0.3)
- C9 : OK ; mesure 3.192e-16 ; seuil {aleatoires: 20, fixes: 3, part_non_pleine_min: 0.4, tolerance: 1e-09}
- C11 : ÉCHEC ; mesure (0.5006, -0.09285) ; seuil (0.6359, 0)
- C12 : OK ; mesure (0.06198, 3.343) ; seuil (0.5, 40)
- C13 : OK ; mesure (1.561, 0.8963) ; seuil 0
- C14 : OK ; mesure 0.1821 ; seuil 0.04
- C15 : OK ; mesure non applicable (couvert) ; seuil None
- C16 : ÉCHEC ; mesure None ; seuil 0.6
- C2 : OK ; mesure 1.272 ; seuil 0.5
- C3 : OK ; mesure 2.497 ; seuil 2
- C4 : OK ; mesure 1.189 ; seuil 0
- C10 : OK ; mesure 0.009198 ; seuil 0.05

### R0207 (t-ecart {L_jours: 80, zs_saturation: 0.25})
- C1 : ÉCHEC ; mesure 1.016e-09 ; seuil 0.95
- C5 : ÉCHEC ; mesure {2020: 1.486, 2021: 3.302, 2022: -2.412, 2023: 1.441, 2024: 1.585, 2025: 0.2159} ; seuil {sharpe_min: -1, positives_min: 4}
- C6 : ÉCHEC ; mesure 0.2082 ; seuil 0.2
- C7 : OK ; mesure 1 ; seuil {part_voisins_min: 0.75, ratio: 0.6, sharpe_voisin_min: 0.5}
- C8 : ÉCHEC ; mesure (1.95, 0.1427) ; seuil (2, 0.3)
- C9 : OK ; mesure 1.943e-16 ; seuil {aleatoires: 20, fixes: 3, part_non_pleine_min: 0.4, tolerance: 1e-09}
- C11 : ÉCHEC ; mesure (0.5296, -0.05936) ; seuil (0.6505, 0)
- C12 : OK ; mesure (0.06279, 3.326) ; seuil (0.5, 40)
- C13 : OK ; mesure (1.613, 0.8868) ; seuil 0
- C14 : OK ; mesure 0.1822 ; seuil 0.04
- C15 : OK ; mesure non applicable (couvert) ; seuil None
- C16 : ÉCHEC ; mesure None ; seuil 0.6
- C2 : OK ; mesure 1.301 ; seuil 0.5
- C3 : OK ; mesure 2.542 ; seuil 2
- C4 : OK ; mesure 1.215 ; seuil 0
- C10 : OK ; mesure 0.008798 ; seuil 0.05

### R0208 (t-ecart {L_jours: 80, zs_saturation: 0.4})
- C1 : ÉCHEC ; mesure 1.44e-09 ; seuil 0.95
- C5 : ÉCHEC ; mesure {2020: 1.554, 2021: 3.332, 2022: -2.339, 2023: 1.537, 2024: 1.566, 2025: 0.1863} ; seuil {sharpe_min: -1, positives_min: 4}
- C6 : OK ; mesure 0.1959 ; seuil 0.2
- C7 : OK ; mesure 1 ; seuil {part_voisins_min: 0.75, ratio: 0.6, sharpe_voisin_min: 0.5}
- C8 : OK ; mesure (2.008, 0.1404) ; seuil (2, 0.3)
- C9 : OK ; mesure 1.874e-16 ; seuil {aleatoires: 20, fixes: 3, part_non_pleine_min: 0.4, tolerance: 1e-09}
- C11 : ÉCHEC ; mesure (0.548, -0.03946) ; seuil (0.6581, 0)
- C12 : OK ; mesure (0.06217, 3.226) ; seuil (0.5, 40)
- C13 : OK ; mesure (1.656, 0.8537) ; seuil 0
- C14 : OK ; mesure 0.1776 ; seuil 0.04
- C15 : OK ; mesure non applicable (couvert) ; seuil None
- C16 : ÉCHEC ; mesure None ; seuil 0.6
- C2 : OK ; mesure 1.316 ; seuil 0.5
- C3 : OK ; mesure 2.554 ; seuil 2
- C4 : OK ; mesure 1.23 ; seuil 0
- C10 : OK ; mesure 0.009398 ; seuil 0.05

### R0209 (t-ecart {L_jours: 80, zs_saturation: 0.65})
- C1 : ÉCHEC ; mesure 3.03e-09 ; seuil 0.95
- C5 : ÉCHEC ; mesure {2020: 1.722, 2021: 3.425, 2022: -2.221, 2023: 1.762, 2024: 1.616, 2025: 0.1137} ; seuil {sharpe_min: -1, positives_min: 4}
- C6 : OK ; mesure 0.1798 ; seuil 0.2
- C7 : OK ; mesure 1 ; seuil {part_voisins_min: 0.75, ratio: 0.6, sharpe_voisin_min: 0.5}
- C8 : OK ; mesure (2.279, 0.1387) ; seuil (2, 0.3)
- C9 : OK ; mesure 2.151e-16 ; seuil {aleatoires: 20, fixes: 3, part_non_pleine_min: 0.4, tolerance: 1e-09}
- C11 : ÉCHEC ; mesure (0.6145, 0.03599) ; seuil (0.6865, 0)
- C12 : OK ; mesure (0.06198, 3.067) ; seuil (0.5, 40)
- C13 : OK ; mesure (1.749, 0.8527) ; seuil 0
- C14 : OK ; mesure 0.1769 ; seuil 0.04
- C15 : OK ; mesure non applicable (couvert) ; seuil None
- C16 : ÉCHEC ; mesure None ; seuil 0.6
- C2 : OK ; mesure 1.373 ; seuil 0.5
- C3 : OK ; mesure 2.639 ; seuil 2
- C4 : OK ; mesure 1.283 ; seuil 0
- C10 : OK ; mesure 0.008198 ; seuil 0.05

### R0210 (t-ecart {L_jours: 80, zs_saturation: 1})
- C1 : ÉCHEC ; mesure 4.27e-09 ; seuil 0.95
- C5 : ÉCHEC ; mesure {2020: 1.935, 2021: 3.457, 2022: -2.054, 2023: 1.991, 2024: 1.623, 2025: 0.02229} ; seuil {sharpe_min: -1, positives_min: 4}
- C6 : OK ; mesure 0.1737 ; seuil 0.2
- C7 : ÉCHEC ; mesure None ; seuil {part_voisins_min: 0.75, ratio: 0.6, sharpe_voisin_min: 0.5}
- C8 : OK ; mesure (2.458, 0.1327) ; seuil (2, 0.3)
- C9 : OK ; mesure 2.637e-16 ; seuil {aleatoires: 20, fixes: 3, part_non_pleine_min: 0.4, tolerance: 1e-09}
- C11 : ÉCHEC ; mesure (0.669, 0.1195) ; seuil (0.6903, 0)
- C12 : OK ; mesure (0.068, 2.962) ; seuil (0.5, 40)
- C13 : OK ; mesure (1.785, 0.8165) ; seuil 0
- C14 : OK ; mesure 0.1624 ; seuil 0.04
- C15 : OK ; mesure non applicable (couvert) ; seuil None
- C16 : ÉCHEC ; mesure None ; seuil 0.6
- C2 : OK ; mesure 1.381 ; seuil 0.5
- C3 : OK ; mesure 2.685 ; seuil 2
- C4 : OK ; mesure 1.281 ; seuil 0
- C10 : OK ; mesure 0.006999 ; seuil 0.05

### R0211 (t-ecart {L_jours: 130, zs_saturation: 0.15})
- C1 : ÉCHEC ; mesure 2.79e-10 ; seuil 0.95
- C5 : ÉCHEC ; mesure {2020: 1.446, 2021: 2.898, 2022: -3.07, 2023: 1.288, 2024: 1.566, 2025: -0.2618} ; seuil {sharpe_min: -1, positives_min: 4}
- C6 : ÉCHEC ; mesure 0.2108 ; seuil 0.2
- C7 : ÉCHEC ; mesure None ; seuil {part_voisins_min: 0.75, ratio: 0.6, sharpe_voisin_min: 0.5}
- C8 : ÉCHEC ; mesure (1.465, 0.1488) ; seuil (2, 0.3)
- C9 : OK ; mesure 3.608e-16 ; seuil {aleatoires: 20, fixes: 3, part_non_pleine_min: 0.4, tolerance: 1e-09}
- C11 : ÉCHEC ; mesure (0.3897, -0.2144) ; seuil (0.5927, 0)
- C12 : OK ; mesure (0.06295, 2.954) ; seuil (0.5, 40)
- C13 : OK ; mesure (1.52, 0.718) ; seuil 0
- C14 : OK ; mesure 0.1713 ; seuil 0.04
- C15 : OK ; mesure non applicable (couvert) ; seuil None
- C16 : ÉCHEC ; mesure None ; seuil 0.6
- C2 : OK ; mesure 1.185 ; seuil 0.5
- C3 : OK ; mesure 2.436 ; seuil 2
- C4 : OK ; mesure 1.107 ; seuil 0
- C10 : OK ; mesure 0.0112 ; seuil 0.05

### R0212 (t-ecart {L_jours: 130, zs_saturation: 0.25})
- C1 : ÉCHEC ; mesure 3.836e-10 ; seuil 0.95
- C5 : ÉCHEC ; mesure {2020: 1.41, 2021: 2.967, 2022: -2.998, 2023: 1.389, 2024: 1.595, 2025: -0.1874} ; seuil {sharpe_min: -1, positives_min: 4}
- C6 : ÉCHEC ; mesure 0.2059 ; seuil 0.2
- C7 : OK ; mesure 1 ; seuil {part_voisins_min: 0.75, ratio: 0.6, sharpe_voisin_min: 0.5}
- C8 : ÉCHEC ; mesure (1.527, 0.1476) ; seuil (2, 0.3)
- C9 : OK ; mesure 2.429e-16 ; seuil {aleatoires: 20, fixes: 3, part_non_pleine_min: 0.4, tolerance: 1e-09}
- C11 : ÉCHEC ; mesure (0.4083, -0.1898) ; seuil (0.6024, 0)
- C12 : OK ; mesure (0.063, 2.928) ; seuil (0.5, 40)
- C13 : OK ; mesure (1.527, 0.7616) ; seuil 0
- C14 : OK ; mesure 0.1709 ; seuil 0.04
- C15 : OK ; mesure non applicable (couvert) ; seuil None
- C16 : ÉCHEC ; mesure None ; seuil 0.6
- C2 : OK ; mesure 1.205 ; seuil 0.5
- C3 : OK ; mesure 2.452 ; seuil 2
- C4 : OK ; mesure 1.125 ; seuil 0
- C10 : OK ; mesure 0.0112 ; seuil 0.05

### R0213 (t-ecart {L_jours: 130, zs_saturation: 0.4})
- C1 : ÉCHEC ; mesure 5.752e-10 ; seuil 0.95
- C5 : ÉCHEC ; mesure {2020: 1.421, 2021: 3.078, 2022: -2.873, 2023: 1.558, 2024: 1.582, 2025: -0.1446} ; seuil {sharpe_min: -1, positives_min: 4}
- C6 : OK ; mesure 0.1987 ; seuil 0.2
- C7 : OK ; mesure 1 ; seuil {part_voisins_min: 0.75, ratio: 0.6, sharpe_voisin_min: 0.5}
- C8 : ÉCHEC ; mesure (1.599, 0.1445) ; seuil (2, 0.3)
- C9 : OK ; mesure 1.735e-16 ; seuil {aleatoires: 20, fixes: 3, part_non_pleine_min: 0.4, tolerance: 1e-09}
- C11 : ÉCHEC ; mesure (0.4419, -0.1489) ; seuil (0.6144, 0)
- C12 : OK ; mesure (0.06399, 2.905) ; seuil (0.5, 40)
- C13 : OK ; mesure (1.555, 0.7807) ; seuil 0
- C14 : OK ; mesure 0.1677 ; seuil 0.04
- C15 : OK ; mesure non applicable (couvert) ; seuil None
- C16 : ÉCHEC ; mesure None ; seuil 0.6
- C2 : OK ; mesure 1.229 ; seuil 0.5
- C3 : OK ; mesure 2.463 ; seuil 2
- C4 : OK ; mesure 1.146 ; seuil 0
- C10 : OK ; mesure 0.0118 ; seuil 0.05

### R0214 (t-ecart {L_jours: 130, zs_saturation: 0.65})
- C1 : ÉCHEC ; mesure 8.089e-10 ; seuil 0.95
- C5 : ÉCHEC ; mesure {2020: 1.582, 2021: 3.209, 2022: -2.582, 2023: 1.755, 2024: 1.51, 2025: -0.1102} ; seuil {sharpe_min: -1, positives_min: 4}
- C6 : OK ; mesure 0.1881 ; seuil 0.2
- C7 : OK ; mesure 1 ; seuil {part_voisins_min: 0.75, ratio: 0.6, sharpe_voisin_min: 0.5}
- C8 : ÉCHEC ; mesure (1.715, 0.1386) ; seuil (2, 0.3)
- C9 : OK ; mesure 2.984e-16 ; seuil {aleatoires: 20, fixes: 3, part_non_pleine_min: 0.4, tolerance: 1e-09}
- C11 : ÉCHEC ; mesure (0.4939, -0.0772) ; seuil (0.6301, 0)
- C12 : OK ; mesure (0.06737, 2.84) ; seuil (0.5, 40)
- C13 : OK ; mesure (1.633, 0.7374) ; seuil 0
- C14 : OK ; mesure 0.1597 ; seuil 0.04
- C15 : OK ; mesure non applicable (couvert) ; seuil None
- C16 : ÉCHEC ; mesure None ; seuil 0.6
- C2 : OK ; mesure 1.26 ; seuil 0.5
- C3 : OK ; mesure 2.478 ; seuil 2
- C4 : OK ; mesure 1.17 ; seuil 0
- C10 : OK ; mesure 0.0116 ; seuil 0.05

### R0215 (t-ecart {L_jours: 130, zs_saturation: 1})
- C1 : ÉCHEC ; mesure 2.011e-09 ; seuil 0.95
- C5 : ÉCHEC ; mesure {2020: 1.914, 2021: 3.369, 2022: -2.313, 2023: 1.987, 2024: 1.535, 2025: -0.1085} ; seuil {sharpe_min: -1, positives_min: 4}
- C6 : OK ; mesure 0.1806 ; seuil 0.2
- C7 : ÉCHEC ; mesure None ; seuil {part_voisins_min: 0.75, ratio: 0.6, sharpe_voisin_min: 0.5}
- C8 : OK ; mesure (2.108, 0.1316) ; seuil (2, 0.3)
- C9 : OK ; mesure 2.151e-16 ; seuil {aleatoires: 20, fixes: 3, part_non_pleine_min: 0.4, tolerance: 1e-09}
- C11 : ÉCHEC ; mesure (0.5985, 0.04658) ; seuil (0.6645, 0)
- C12 : OK ; mesure (0.06996, 2.768) ; seuil (0.5, 40)
- C13 : OK ; mesure (1.756, 0.7265) ; seuil 0
- C14 : OK ; mesure 0.1542 ; seuil 0.04
- C15 : OK ; mesure non applicable (couvert) ; seuil None
- C16 : ÉCHEC ; mesure None ; seuil 0.6
- C2 : OK ; mesure 1.329 ; seuil 0.5
- C3 : OK ; mesure 2.604 ; seuil 2
- C4 : OK ; mesure 1.23 ; seuil 0
- C10 : OK ; mesure 0.008198 ; seuil 0.05

### R0216 (t-ecart {L_jours: 210, zs_saturation: 0.15})
- C1 : ÉCHEC ; mesure 2.293e-11 ; seuil 0.95
- C5 : ÉCHEC ; mesure {2020: 1.388, 2021: 2.569, 2022: -2.842, 2023: 1.404, 2024: 1.209, 2025: -0.6034} ; seuil {sharpe_min: -1, positives_min: 4}
- C6 : ÉCHEC ; mesure 0.2062 ; seuil 0.2
- C7 : ÉCHEC ; mesure None ; seuil {part_voisins_min: 0.75, ratio: 0.6, sharpe_voisin_min: 0.5}
- C8 : ÉCHEC ; mesure (0.8448, 0.1491) ; seuil (2, 0.3)
- C9 : OK ; mesure 3.192e-16 ; seuil {aleatoires: 20, fixes: 3, part_non_pleine_min: 0.4, tolerance: 1e-09}
- C11 : ÉCHEC ; mesure (0.2043, -0.3402) ; seuil (0.5089, 0)
- C12 : OK ; mesure (0.07176, 2.813) ; seuil (0.5, 40)
- C13 : OK ; mesure (1.405, 0.4527) ; seuil 0
- C14 : OK ; mesure 0.1423 ; seuil 0.04
- C15 : OK ; mesure non applicable (couvert) ; seuil None
- C16 : ÉCHEC ; mesure None ; seuil 0.6
- C2 : OK ; mesure 1.018 ; seuil 0.5
- C3 : OK ; mesure 2.281 ; seuil 2
- C4 : OK ; mesure 0.9401 ; seuil 0
- C10 : OK ; mesure 0.0148 ; seuil 0.05

### R0217 (t-ecart {L_jours: 210, zs_saturation: 0.25})
- C1 : ÉCHEC ; mesure 2.592e-11 ; seuil 0.95
- C5 : ÉCHEC ; mesure {2020: 1.476, 2021: 2.548, 2022: -2.985, 2023: 1.573, 2024: 1.215, 2025: -0.6035} ; seuil {sharpe_min: -1, positives_min: 4}
- C6 : ÉCHEC ; mesure 0.2071 ; seuil 0.2
- C7 : ÉCHEC ; mesure None ; seuil {part_voisins_min: 0.75, ratio: 0.6, sharpe_voisin_min: 0.5}
- C8 : ÉCHEC ; mesure (0.891, 0.1469) ; seuil (2, 0.3)
- C9 : OK ; mesure 2.151e-16 ; seuil {aleatoires: 20, fixes: 3, part_non_pleine_min: 0.4, tolerance: 1e-09}
- C11 : ÉCHEC ; mesure (0.2195, -0.3265) ; seuil (0.5158, 0)
- C12 : OK ; mesure (0.07314, 2.812) ; seuil (0.5, 40)
- C13 : OK ; mesure (1.417, 0.4708) ; seuil 0
- C14 : OK ; mesure 0.1414 ; seuil 0.04
- C15 : OK ; mesure non applicable (couvert) ; seuil None
- C16 : ÉCHEC ; mesure None ; seuil 0.6
- C2 : OK ; mesure 1.032 ; seuil 0.5
- C3 : OK ; mesure 2.306 ; seuil 2
- C4 : OK ; mesure 0.9511 ; seuil 0
- C10 : OK ; mesure 0.0144 ; seuil 0.05

### R0218 (t-ecart {L_jours: 210, zs_saturation: 0.4})
- C1 : ÉCHEC ; mesure 4.856e-11 ; seuil 0.95
- C5 : ÉCHEC ; mesure {2020: 1.614, 2021: 2.574, 2022: -3.06, 2023: 1.717, 2024: 1.266, 2025: -0.5382} ; seuil {sharpe_min: -1, positives_min: 4}
- C6 : ÉCHEC ; mesure 0.2025 ; seuil 0.2
- C7 : ÉCHEC ; mesure None ; seuil {part_voisins_min: 0.75, ratio: 0.6, sharpe_voisin_min: 0.5}
- C8 : ÉCHEC ; mesure (1.04, 0.1428) ; seuil (2, 0.3)
- C9 : OK ; mesure 1.735e-16 ; seuil {aleatoires: 20, fixes: 3, part_non_pleine_min: 0.4, tolerance: 1e-09}
- C11 : ÉCHEC ; mesure (0.2688, -0.2753) ; seuil (0.5363, 0)
- C12 : OK ; mesure (0.07377, 2.779) ; seuil (0.5, 40)
- C13 : OK ; mesure (1.448, 0.5303) ; seuil 0
- C14 : OK ; mesure 0.1418 ; seuil 0.04
- C15 : OK ; mesure non applicable (couvert) ; seuil None
- C16 : ÉCHEC ; mesure None ; seuil 0.6
- C2 : OK ; mesure 1.073 ; seuil 0.5
- C3 : OK ; mesure 2.366 ; seuil 2
- C4 : OK ; mesure 0.9882 ; seuil 0
- C10 : OK ; mesure 0.0126 ; seuil 0.05

### R0219 (t-ecart {L_jours: 210, zs_saturation: 0.65})
- C1 : ÉCHEC ; mesure 1.699e-10 ; seuil 0.95
- C5 : ÉCHEC ; mesure {2020: 1.854, 2021: 2.762, 2022: -2.88, 2023: 1.816, 2024: 1.418, 2025: -0.4581} ; seuil {sharpe_min: -1, positives_min: 4}
- C6 : OK ; mesure 0.1836 ; seuil 0.2
- C7 : ÉCHEC ; mesure None ; seuil {part_voisins_min: 0.75, ratio: 0.6, sharpe_voisin_min: 0.5}
- C8 : ÉCHEC ; mesure (1.301, 0.1354) ; seuil (2, 0.3)
- C9 : OK ; mesure 1.596e-16 ; seuil {aleatoires: 20, fixes: 3, part_non_pleine_min: 0.4, tolerance: 1e-09}
- C11 : ÉCHEC ; mesure (0.3723, -0.1634) ; seuil (0.5708, 0)
- C12 : OK ; mesure (0.07557, 2.736) ; seuil (0.5, 40)
- C13 : OK ; mesure (1.537, 0.5783) ; seuil 0
- C14 : OK ; mesure 0.1391 ; seuil 0.04
- C15 : OK ; mesure non applicable (couvert) ; seuil None
- C16 : ÉCHEC ; mesure None ; seuil 0.6
- C2 : OK ; mesure 1.142 ; seuil 0.5
- C3 : OK ; mesure 2.458 ; seuil 2
- C4 : OK ; mesure 1.05 ; seuil 0
- C10 : OK ; mesure 0.009198 ; seuil 0.05

### R0220 (t-ecart {L_jours: 210, zs_saturation: 1})
- C1 : ÉCHEC ; mesure 4.699e-10 ; seuil 0.95
- C5 : ÉCHEC ; mesure {2020: 2.085, 2021: 2.96, 2022: -2.471, 2023: 1.98, 2024: 1.543, 2025: -0.3673} ; seuil {sharpe_min: -1, positives_min: 4}
- C6 : OK ; mesure 0.1732 ; seuil 0.2
- C7 : ÉCHEC ; mesure None ; seuil {part_voisins_min: 0.75, ratio: 0.6, sharpe_voisin_min: 0.5}
- C8 : ÉCHEC ; mesure (1.674, 0.1284) ; seuil (2, 0.3)
- C9 : OK ; mesure 2.567e-16 ; seuil {aleatoires: 20, fixes: 3, part_non_pleine_min: 0.4, tolerance: 1e-09}
- C11 : ÉCHEC ; mesure (0.4727, -0.03085) ; seuil (0.6046, 0)
- C12 : OK ; mesure (0.07673, 2.65) ; seuil (0.5, 40)
- C13 : OK ; mesure (1.629, 0.6191) ; seuil 0
- C14 : OK ; mesure 0.1346 ; seuil 0.04
- C15 : OK ; mesure non applicable (couvert) ; seuil None
- C16 : ÉCHEC ; mesure None ; seuil 0.6
- C2 : OK ; mesure 1.209 ; seuil 0.5
- C3 : OK ; mesure 2.561 ; seuil 2
- C4 : OK ; mesure 1.109 ; seuil 0
- C10 : OK ; mesure 0.006599 ; seuil 0.05

## Sélection

Aucun candidat : issue B si aucune autre vague n'est décidée.
