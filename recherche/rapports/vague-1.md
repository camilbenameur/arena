# Vague 1

Document de l'orchestrateur et du propriétaire : il contient des chiffres et ne va à aucun agent. Les agents ne reçoivent que `vague-1-statuts.json`.

Essais de grille : 45 ; lignes supplémentaires (arène, contrôle) : 0 ; dont relues du journal sans relance (reprise) : 0 ; N réel dans le journal : 45 ; N du DSR : 726.
Meilleur DSR : 0.4201. Règle d'arrêt déclenchée : oui.

## Tous les essais

| id | famille | paramètres | code | Sharpe net | portes en échec | passe |
|---|---|---|---|---|---|---|
| R0001 | c-carry-persistant | {entree: 0.09, sortie_ratio: 0.2} | OK | 0.425 | C1, C5, C7, C8, C11, C12, C13, C14, C16, C2, C3, C4, C10 | non |
| R0002 | c-carry-persistant | {entree: 0.09, sortie_ratio: 0.4} | OK | -0.07978 | C1, C5, C7, C8, C11, C12, C13, C14, C16, C2, C3, C4, C10 | non |
| R0003 | c-carry-persistant | {entree: 0.09, sortie_ratio: 0.8} | OK | -0.6915 | C1, C5, C6, C7, C8, C11, C12, C13, C14, C16, C2, C3, C4, C10 | non |
| R0004 | c-carry-persistant | {entree: 0.135, sortie_ratio: 0.2} | OK | 1.246 | C1, C5, C7, C8, C11, C12, C13, C14, C16, C3, C4, C10 | non |
| R0005 | c-carry-persistant | {entree: 0.135, sortie_ratio: 0.4} | OK | 0.8678 | C1, C5, C7, C8, C11, C12, C13, C14, C16, C3, C4, C10 | non |
| R0006 | c-carry-persistant | {entree: 0.135, sortie_ratio: 0.8} | OK | 0.4414 | C1, C5, C7, C8, C11, C12, C13, C14, C16, C2, C3, C4, C10 | non |
| R0007 | c-carry-persistant | {entree: 0.2, sortie_ratio: 0.2} | OK | 1.235 | C1, C5, C7, C8, C11, C12, C13, C14, C16, C3, C4, C10 | non |
| R0008 | c-carry-persistant | {entree: 0.2, sortie_ratio: 0.4} | OK | 1.164 | C1, C5, C7, C8, C11, C12, C13, C14, C16, C3, C4, C10 | non |
| R0009 | c-carry-persistant | {entree: 0.2, sortie_ratio: 0.8} | OK | 0.3942 | C1, C5, C7, C8, C11, C12, C13, C14, C16, C2, C3, C4, C10 | non |
| R0010 | c-carry-rang | {k: 2, tampon: 1} | OK | -1.539 | C1, C5, C6, C7, C8, C11, C12, C13, C14, C16, C2, C3, C4, C10 | non |
| R0011 | c-carry-rang | {k: 2, tampon: 2} | OK | -0.8742 | C1, C5, C6, C7, C8, C11, C12, C13, C14, C16, C2, C3, C4, C10 | non |
| R0012 | c-carry-rang | {k: 2, tampon: 4} | OK | -0.2583 | C1, C5, C6, C7, C8, C11, C12, C13, C14, C16, C2, C3, C4, C10 | non |
| R0013 | c-carry-rang | {k: 3, tampon: 1} | OK | -1.345 | C1, C5, C6, C7, C8, C11, C12, C13, C14, C16, C2, C3, C4, C10 | non |
| R0014 | c-carry-rang | {k: 3, tampon: 2} | OK | -0.5806 | C1, C5, C6, C7, C8, C11, C12, C13, C14, C16, C2, C3, C4, C10 | non |
| R0015 | c-carry-rang | {k: 3, tampon: 4} | OK | -0.1744 | C1, C5, C6, C7, C8, C11, C12, C13, C14, C16, C2, C3, C4, C10 | non |
| R0016 | c-carry-rang | {k: 5, tampon: 1} | OK | -0.7179 | C1, C5, C6, C7, C8, C11, C12, C13, C14, C16, C2, C3, C4, C10 | non |
| R0017 | c-carry-rang | {k: 5, tampon: 2} | OK | -0.6193 | C1, C5, C6, C7, C8, C11, C12, C13, C14, C16, C2, C3, C4, C10 | non |
| R0018 | c-carry-rang | {k: 5, tampon: 4} | OK | -0.382 | C1, C5, C6, C7, C8, C11, C12, C13, C14, C16, C2, C3, C4, C10 | non |
| R0019 | c-carry-regime | {entree: 0.09, plafond_extreme: 0.25} | OK | -4.489 | C1, C5, C6, C7, C8, C11, C12, C13, C14, C16, C2, C3, C4, C10 | non |
| R0020 | c-carry-regime | {entree: 0.09, plafond_extreme: 0.5} | OK | -2.315 | C1, C5, C6, C7, C8, C11, C12, C13, C14, C16, C2, C3, C4, C10 | non |
| R0021 | c-carry-regime | {entree: 0.09, plafond_extreme: 1} | OK | -0.4901 | C1, C5, C7, C8, C11, C12, C13, C14, C16, C2, C3, C4, C10 | non |
| R0022 | c-carry-regime | {entree: 0.135, plafond_extreme: 0.25} | OK | -3.895 | C1, C5, C6, C7, C8, C11, C12, C13, C14, C16, C2, C3, C4, C10 | non |
| R0023 | c-carry-regime | {entree: 0.135, plafond_extreme: 0.5} | OK | -1.596 | C1, C5, C7, C8, C11, C12, C13, C14, C16, C2, C3, C4, C10 | non |
| R0024 | c-carry-regime | {entree: 0.135, plafond_extreme: 1} | OK | 0.4515 | C1, C5, C7, C8, C11, C12, C13, C14, C16, C2, C3, C4, C10 | non |
| R0025 | c-carry-regime | {entree: 0.2, plafond_extreme: 0.25} | OK | -3.835 | C1, C5, C6, C7, C8, C11, C12, C13, C14, C16, C2, C3, C4, C10 | non |
| R0026 | c-carry-regime | {entree: 0.2, plafond_extreme: 0.5} | OK | -1.528 | C1, C5, C7, C8, C11, C12, C13, C14, C16, C2, C3, C4, C10 | non |
| R0027 | c-carry-regime | {entree: 0.2, plafond_extreme: 1} | OK | 0.7327 | C1, C5, C7, C8, C11, C12, C13, C14, C16, C3, C4, C10 | non |
| R0028 | m-semivar | {L_jours: 14, s: 0.1} | OK | 1.064 | C1, C5, C6, C7, C8, C11, C12, C15, C16 | non |
| R0029 | m-semivar | {L_jours: 14, s: 0.2} | OK | 1.058 | C1, C5, C6, C7, C8, C11, C15, C16 | non |
| R0030 | m-semivar | {L_jours: 14, s: 0.4} | OK | 0.6721 | C1, C5, C6, C7, C8, C9, C11, C15, C16, C3, C10 | non |
| R0031 | m-semivar | {L_jours: 28, s: 0.1} | OK | 1.161 | C1, C6, C7, C8, C11, C15, C16 | non |
| R0032 | m-semivar | {L_jours: 28, s: 0.2} | OK | 0.7992 | C1, C5, C6, C8, C11, C15, C16, C3 | non |
| R0033 | m-semivar | {L_jours: 28, s: 0.4} | OK | 0.6199 | C1, C6, C7, C8, C9, C11, C15, C16, C3, C10 | non |
| R0034 | m-semivar | {L_jours: 56, s: 0.1} | OK | 0.7191 | C1, C5, C6, C7, C8, C11, C15, C16, C3, C10 | non |
| R0035 | m-semivar | {L_jours: 56, s: 0.2} | OK | 0.6628 | C1, C5, C6, C7, C8, C11, C15, C16, C3, C10 | non |
| R0036 | m-semivar | {L_jours: 56, s: 0.4} | OK | 0.9058 | C1, C7, C8, C9, C11, C15, C16 | non |
| R0037 | r-fonds-foule | {L: 7, q: 0.5} | OK | 0.7057 | C1, C5, C6, C7, C8, C11, C15, C16, C3 | non |
| R0038 | r-fonds-foule | {L: 7, q: 0.7} | OK | 0.6733 | C1, C5, C6, C7, C8, C11, C15, C16, C3 | non |
| R0039 | r-fonds-foule | {L: 7, q: 0.9} | OK | 0.8252 | C1, C5, C6, C7, C8, C11, C15, C16 | non |
| R0040 | r-fonds-foule | {L: 14, q: 0.5} | OK | 0.6764 | C1, C5, C6, C7, C8, C11, C15, C16, C3 | non |
| R0041 | r-fonds-foule | {L: 14, q: 0.7} | OK | 0.6535 | C1, C5, C6, C8, C11, C15, C16, C3 | non |
| R0042 | r-fonds-foule | {L: 14, q: 0.9} | OK | 0.7766 | C1, C5, C6, C7, C8, C11, C15, C16, C3 | non |
| R0043 | r-fonds-foule | {L: 28, q: 0.5} | OK | 0.6227 | C1, C5, C6, C7, C8, C11, C15, C16, C3, C10 | non |
| R0044 | r-fonds-foule | {L: 28, q: 0.7} | OK | 0.6219 | C1, C5, C6, C7, C8, C11, C15, C16, C3, C10 | non |
| R0045 | r-fonds-foule | {L: 28, q: 0.9} | OK | 0.6133 | C1, C5, C6, C7, C8, C11, C15, C16, C3, C10 | non |

## Verdicts détaillés

C16 : mesure = (part, positifs, évaluables, non évaluables, taille de l'univers de contrôle) ; la part est rapportée à la taille fixe de l'univers.

### R0001 (c-carry-persistant {entree: 0.09, sortie_ratio: 0.2})
- C1 : ÉCHEC ; mesure 1.334e-29 ; seuil 0.95
- C5 : ÉCHEC ; mesure {2020: 2.223, 2021: 6.904, 2022: -5.748, 2023: -2.607, 2024: 1.179, 2025: -5.707} ; seuil {sharpe_min: -1, positives_min: 4}
- C6 : OK ; mesure 0.1379 ; seuil 0.2
- C7 : ÉCHEC ; mesure None ; seuil {part_voisins_min: 0.75, ratio: 0.6, sharpe_voisin_min: 0.5}
- C8 : ÉCHEC ; mesure (0.5139, -0.001167) ; seuil (2, 0.3)
- C9 : OK ; mesure 0 ; seuil {aleatoires: 20, fixes: 3, part_non_pleine_min: 0.4, tolerance: 1e-09}
- C11 : ÉCHEC ; mesure (-0.5668, -1.284) ; seuil (0.5, 0)
- C12 : ÉCHEC ; mesure (0.9388, 23.21) ; seuil (0.5, 40)
- C13 : ÉCHEC ; mesure (1.807, -2.236) ; seuil 0
- C14 : ÉCHEC ; mesure 0.005627 ; seuil 0.04
- C15 : OK ; mesure non applicable (couvert) ; seuil None
- C16 : ÉCHEC ; mesure None ; seuil 0.6
- C2 : ÉCHEC ; mesure 0.425 ; seuil 0.5
- C3 : ÉCHEC ; mesure 0.4397 ; seuil 2
- C4 : ÉCHEC ; mesure -4.33 ; seuil 0
- C10 : ÉCHEC ; mesure 0.3189 ; seuil 0.05

### R0002 (c-carry-persistant {entree: 0.09, sortie_ratio: 0.4})
- C1 : ÉCHEC ; mesure 9.412e-37 ; seuil 0.95
- C5 : ÉCHEC ; mesure {2020: 2.136, 2021: 6.616, 2022: -4.509, 2023: -3.531, 2024: -1.574, 2025: -5.202} ; seuil {sharpe_min: -1, positives_min: 4}
- C6 : OK ; mesure 0.1748 ; seuil 0.2
- C7 : ÉCHEC ; mesure None ; seuil {part_voisins_min: 0.75, ratio: 0.6, sharpe_voisin_min: 0.5}
- C8 : ÉCHEC ; mesure (-0.02738, -0.001032) ; seuil (2, 0.3)
- C9 : OK ; mesure 0 ; seuil {aleatoires: 20, fixes: 3, part_non_pleine_min: 0.4, tolerance: 1e-09}
- C11 : ÉCHEC ; mesure (-1.041, -1.704) ; seuil (0.5, 0)
- C12 : ÉCHEC ; mesure (1.013, 22.95) ; seuil (0.5, 40)
- C13 : ÉCHEC ; mesure (1.718, -2.965) ; seuil 0
- C14 : ÉCHEC ; mesure -0.001267 ; seuil 0.04
- C15 : OK ; mesure non applicable (couvert) ; seuil None
- C16 : ÉCHEC ; mesure None ; seuil 0.6
- C2 : ÉCHEC ; mesure -0.07978 ; seuil 0.5
- C3 : ÉCHEC ; mesure -0.08444 ; seuil 2
- C4 : ÉCHEC ; mesure -3.948 ; seuil 0
- C10 : ÉCHEC ; mesure 0.5315 ; seuil 0.05

### R0003 (c-carry-persistant {entree: 0.09, sortie_ratio: 0.8})
- C1 : ÉCHEC ; mesure 2.166e-48 ; seuil 0.95
- C5 : ÉCHEC ; mesure {2020: 1.122, 2021: 5.764, 2022: -4.313, 2023: -4.608, 2024: -2.385, 2025: -4.617} ; seuil {sharpe_min: -1, positives_min: 4}
- C6 : ÉCHEC ; mesure 0.2133 ; seuil 0.2
- C7 : ÉCHEC ; mesure None ; seuil {part_voisins_min: 0.75, ratio: 0.6, sharpe_voisin_min: 0.5}
- C8 : ÉCHEC ; mesure (-0.7358, -0.0008204) ; seuil (2, 0.3)
- C9 : OK ; mesure 0 ; seuil {aleatoires: 20, fixes: 3, part_non_pleine_min: 0.4, tolerance: 1e-09}
- C11 : ÉCHEC ; mesure (-1.615, -2.227) ; seuil (0.5, 0)
- C12 : ÉCHEC ; mesure (1.127, 24.81) ; seuil (0.5, 40)
- C13 : ÉCHEC ; mesure (1.01, -3.305) ; seuil 0
- C14 : ÉCHEC ; mesure -0.01107 ; seuil 0.04
- C15 : OK ; mesure non applicable (couvert) ; seuil None
- C16 : ÉCHEC ; mesure None ; seuil 0.6
- C2 : ÉCHEC ; mesure -0.6915 ; seuil 0.5
- C3 : ÉCHEC ; mesure -0.7703 ; seuil 2
- C4 : ÉCHEC ; mesure -4.197 ; seuil 0
- C10 : ÉCHEC ; mesure 0.7946 ; seuil 0.05

### R0004 (c-carry-persistant {entree: 0.135, sortie_ratio: 0.2})
- C1 : ÉCHEC ; mesure 4.711e-19 ; seuil 0.95
- C5 : ÉCHEC ; mesure {2020: 2.167, 2021: 6.758, 2022: -3.499, 2023: -1.828, 2024: 1.412, 2025: -3.812} ; seuil {sharpe_min: -1, positives_min: 4}
- C6 : OK ; mesure 0.07588 ; seuil 0.2
- C7 : ÉCHEC ; mesure None ; seuil {part_voisins_min: 0.75, ratio: 0.6, sharpe_voisin_min: 0.5}
- C8 : ÉCHEC ; mesure (1.362, -0.001011) ; seuil (2, 0.3)
- C9 : OK ; mesure 0 ; seuil {aleatoires: 20, fixes: 3, part_non_pleine_min: 0.4, tolerance: 1e-09}
- C11 : ÉCHEC ; mesure (0.3458, -0.3416) ; seuil (0.6229, 0)
- C12 : ÉCHEC ; mesure (0.8093, 17.88) ; seuil (0.5, 40)
- C13 : ÉCHEC ; mesure (2.664, -1.283) ; seuil 0
- C14 : ÉCHEC ; mesure 0.01618 ; seuil 0.04
- C15 : OK ; mesure non applicable (couvert) ; seuil None
- C16 : ÉCHEC ; mesure None ; seuil 0.6
- C2 : OK ; mesure 1.246 ; seuil 0.5
- C3 : ÉCHEC ; mesure 1.282 ; seuil 2
- C4 : ÉCHEC ; mesure -2.835 ; seuil 0
- C10 : ÉCHEC ; mesure 0.09778 ; seuil 0.05

### R0005 (c-carry-persistant {entree: 0.135, sortie_ratio: 0.4})
- C1 : ÉCHEC ; mesure 5.173e-23 ; seuil 0.95
- C5 : ÉCHEC ; mesure {2020: 1.773, 2021: 5.414, 2022: -2.454, 2023: -1.963, 2024: -0.6901, 2025: -3.361} ; seuil {sharpe_min: -1, positives_min: 4}
- C6 : OK ; mesure 0.09418 ; seuil 0.2
- C7 : ÉCHEC ; mesure 0.5 ; seuil {part_voisins_min: 0.75, ratio: 0.6, sharpe_voisin_min: 0.5}
- C8 : ÉCHEC ; mesure (1.003, -0.001029) ; seuil (2, 0.3)
- C9 : OK ; mesure 0 ; seuil {aleatoires: 20, fixes: 3, part_non_pleine_min: 0.4, tolerance: 1e-09}
- C11 : ÉCHEC ; mesure (-0.02455, -0.6845) ; seuil (0.5, 0)
- C12 : ÉCHEC ; mesure (0.8538, 17.52) ; seuil (0.5, 40)
- C13 : ÉCHEC ; mesure (2.221, -1.549) ; seuil 0
- C14 : ÉCHEC ; mesure 0.01192 ; seuil 0.04
- C15 : OK ; mesure non applicable (couvert) ; seuil None
- C16 : ÉCHEC ; mesure None ; seuil 0.6
- C2 : OK ; mesure 0.8678 ; seuil 0.5
- C3 : ÉCHEC ; mesure 0.9272 ; seuil 2
- C4 : ÉCHEC ; mesure -2.771 ; seuil 0
- C10 : ÉCHEC ; mesure 0.1668 ; seuil 0.05

### R0006 (c-carry-persistant {entree: 0.135, sortie_ratio: 0.8})
- C1 : ÉCHEC ; mesure 3.498e-28 ; seuil 0.95
- C5 : ÉCHEC ; mesure {2020: 0.06809, 2021: 4.563, 2022: -1.064, 2023: -2.231, 2024: -1.637, 2025: -2.153} ; seuil {sharpe_min: -1, positives_min: 4}
- C6 : OK ; mesure 0.1002 ; seuil 0.2
- C7 : ÉCHEC ; mesure None ; seuil {part_voisins_min: 0.75, ratio: 0.6, sharpe_voisin_min: 0.5}
- C8 : ÉCHEC ; mesure (0.5432, -0.0007719) ; seuil (2, 0.3)
- C9 : OK ; mesure 0 ; seuil {aleatoires: 20, fixes: 3, part_non_pleine_min: 0.4, tolerance: 1e-09}
- C11 : ÉCHEC ; mesure (-0.4658, -1.088) ; seuil (0.5, 0)
- C12 : ÉCHEC ; mesure (0.9139, 17.61) ; seuil (0.5, 40)
- C13 : ÉCHEC ; mesure (1.523, -1.596) ; seuil 0
- C14 : ÉCHEC ; mesure 0.006315 ; seuil 0.04
- C15 : OK ; mesure non applicable (couvert) ; seuil None
- C16 : ÉCHEC ; mesure None ; seuil 0.6
- C2 : ÉCHEC ; mesure 0.4414 ; seuil 0.5
- C3 : ÉCHEC ; mesure 0.4873 ; seuil 2
- C4 : ÉCHEC ; mesure -2.66 ; seuil 0
- C10 : ÉCHEC ; mesure 0.3083 ; seuil 0.05

### R0007 (c-carry-persistant {entree: 0.2, sortie_ratio: 0.2})
- C1 : ÉCHEC ; mesure 5.893e-19 ; seuil 0.95
- C5 : ÉCHEC ; mesure {2020: 2.19, 2021: 6.476, 2022: -2.684, 2023: -1.265, 2024: -0.8912, 2025: -3.44} ; seuil {sharpe_min: -1, positives_min: 4}
- C6 : OK ; mesure 0.07786 ; seuil 0.2
- C7 : ÉCHEC ; mesure None ; seuil {part_voisins_min: 0.75, ratio: 0.6, sharpe_voisin_min: 0.5}
- C8 : ÉCHEC ; mesure (1.333, -0.000635) ; seuil (2, 0.3)
- C9 : OK ; mesure 0 ; seuil {aleatoires: 20, fixes: 3, part_non_pleine_min: 0.4, tolerance: 1e-09}
- C11 : ÉCHEC ; mesure (0.3287, -0.3625) ; seuil (0.6174, 0)
- C12 : ÉCHEC ; mesure (0.7965, 16.23) ; seuil (0.5, 40)
- C13 : ÉCHEC ; mesure (2.826, -1.597) ; seuil 0
- C14 : ÉCHEC ; mesure 0.01585 ; seuil 0.04
- C15 : OK ; mesure non applicable (couvert) ; seuil None
- C16 : ÉCHEC ; mesure None ; seuil 0.6
- C2 : OK ; mesure 1.235 ; seuil 0.5
- C3 : ÉCHEC ; mesure 1.265 ; seuil 2
- C4 : ÉCHEC ; mesure -2.447 ; seuil 0
- C10 : ÉCHEC ; mesure 0.102 ; seuil 0.05

### R0008 (c-carry-persistant {entree: 0.2, sortie_ratio: 0.4})
- C1 : ÉCHEC ; mesure 7.493e-19 ; seuil 0.95
- C5 : ÉCHEC ; mesure {2020: 1.522, 2021: 5.767, 2022: -2.441, 2023: -1.265, 2024: -0.8121, 2025: -2.594} ; seuil {sharpe_min: -1, positives_min: 4}
- C6 : OK ; mesure 0.07255 ; seuil 0.2
- C7 : ÉCHEC ; mesure None ; seuil {part_voisins_min: 0.75, ratio: 0.6, sharpe_voisin_min: 0.5}
- C8 : ÉCHEC ; mesure (1.267, -0.00028) ; seuil (2, 0.3)
- C9 : OK ; mesure 0 ; seuil {aleatoires: 20, fixes: 3, part_non_pleine_min: 0.4, tolerance: 1e-09}
- C11 : ÉCHEC ; mesure (0.2715, -0.4025) ; seuil (0.5821, 0)
- C12 : ÉCHEC ; mesure (0.7947, 15.44) ; seuil (0.5, 40)
- C13 : ÉCHEC ; mesure (2.532, -1.348) ; seuil 0
- C14 : ÉCHEC ; mesure 0.01536 ; seuil 0.04
- C15 : OK ; mesure non applicable (couvert) ; seuil None
- C16 : ÉCHEC ; mesure None ; seuil 0.6
- C2 : OK ; mesure 1.164 ; seuil 0.5
- C3 : ÉCHEC ; mesure 1.218 ; seuil 2
- C4 : ÉCHEC ; mesure -2.204 ; seuil 0
- C10 : ÉCHEC ; mesure 0.111 ; seuil 0.05

### R0009 (c-carry-persistant {entree: 0.2, sortie_ratio: 0.8})
- C1 : ÉCHEC ; mesure 6.193e-29 ; seuil 0.95
- C5 : ÉCHEC ; mesure {2020: 0.6301, 2021: 3.426, 2022: 0, 2023: -1.265, 2024: -3.221, 2025: -1.596} ; seuil {sharpe_min: -1, positives_min: 4}
- C6 : OK ; mesure 0.1129 ; seuil 0.2
- C7 : ÉCHEC ; mesure None ; seuil {part_voisins_min: 0.75, ratio: 0.6, sharpe_voisin_min: 0.5}
- C8 : ÉCHEC ; mesure (0.4787, -0.0003595) ; seuil (2, 0.3)
- C9 : OK ; mesure 0 ; seuil {aleatoires: 20, fixes: 3, part_non_pleine_min: 0.4, tolerance: 1e-09}
- C11 : ÉCHEC ; mesure (-0.5164, -1.152) ; seuil (0.5, 0)
- C12 : ÉCHEC ; mesure (0.9166, 16.35) ; seuil (0.5, 40)
- C13 : ÉCHEC ; mesure (1.643, -2.097) ; seuil 0
- C14 : ÉCHEC ; mesure 0.005717 ; seuil 0.04
- C15 : OK ; mesure non applicable (couvert) ; seuil None
- C16 : ÉCHEC ; mesure None ; seuil 0.6
- C2 : ÉCHEC ; mesure 0.3942 ; seuil 0.5
- C3 : ÉCHEC ; mesure 0.4452 ; seuil 2
- C4 : ÉCHEC ; mesure -2.42 ; seuil 0
- C10 : ÉCHEC ; mesure 0.3261 ; seuil 0.05

### R0010 (c-carry-rang {k: 2, tampon: 1})
- C1 : ÉCHEC ; mesure 3.486e-69 ; seuil 0.95
- C5 : ÉCHEC ; mesure {2020: -0.1983, 2021: 3.702, 2022: -3.424, 2023: -5.592, 2024: -4.364, 2025: -3.523} ; seuil {sharpe_min: -1, positives_min: 4}
- C6 : ÉCHEC ; mesure 0.33 ; seuil 0.2
- C7 : ÉCHEC ; mesure None ; seuil {part_voisins_min: 0.75, ratio: 0.6, sharpe_voisin_min: 0.5}
- C8 : ÉCHEC ; mesure (-2.114, -0.0003485) ; seuil (2, 0.3)
- C9 : OK ; mesure 0 ; seuil {aleatoires: 20, fixes: 3, part_non_pleine_min: 0.4, tolerance: 1e-09}
- C11 : ÉCHEC ; mesure (-2.357, -2.909) ; seuil (0.5, 0)
- C12 : ÉCHEC ; mesure (1.372, 35.79) ; seuil (0.5, 40)
- C13 : ÉCHEC ; mesure (0.2932, -3.994) ; seuil 0
- C14 : ÉCHEC ; mesure -0.03687 ; seuil 0.04
- C15 : OK ; mesure non applicable (couvert) ; seuil None
- C16 : ÉCHEC ; mesure None ; seuil 0.6
- C2 : ÉCHEC ; mesure -1.539 ; seuil 0.5
- C3 : ÉCHEC ; mesure -2.092 ; seuil 2
- C4 : ÉCHEC ; mesure -4.097 ; seuil 0
- C10 : ÉCHEC ; mesure 0.9876 ; seuil 0.05

### R0011 (c-carry-rang {k: 2, tampon: 2})
- C1 : ÉCHEC ; mesure 6.724e-53 ; seuil 0.95
- C5 : ÉCHEC ; mesure {2020: 1.102, 2021: 4.189, 2022: -3.388, 2023: -5.066, 2024: -3.276, 2025: -3.227} ; seuil {sharpe_min: -1, positives_min: 4}
- C6 : ÉCHEC ; mesure 0.2839 ; seuil 0.2
- C7 : ÉCHEC ; mesure None ; seuil {part_voisins_min: 0.75, ratio: 0.6, sharpe_voisin_min: 0.5}
- C8 : ÉCHEC ; mesure (-1.162, -0.0005172) ; seuil (2, 0.3)
- C9 : OK ; mesure 0 ; seuil {aleatoires: 20, fixes: 3, part_non_pleine_min: 0.4, tolerance: 1e-09}
- C11 : ÉCHEC ; mesure (-1.703, -2.259) ; seuil (0.5, 0)
- C12 : ÉCHEC ; mesure (1.203, 30.54) ; seuil (0.5, 40)
- C13 : ÉCHEC ; mesure (1.009, -3.428) ; seuil 0
- C14 : ÉCHEC ; mesure -0.02005 ; seuil 0.04
- C15 : OK ; mesure non applicable (couvert) ; seuil None
- C16 : ÉCHEC ; mesure None ; seuil 0.6
- C2 : ÉCHEC ; mesure -0.8742 ; seuil 0.5
- C3 : ÉCHEC ; mesure -1.164 ; seuil 2
- C4 : ÉCHEC ; mesure -3.505 ; seuil 0
- C10 : ÉCHEC ; mesure 0.885 ; seuil 0.05

### R0012 (c-carry-rang {k: 2, tampon: 4})
- C1 : ÉCHEC ; mesure 2.607e-40 ; seuil 0.95
- C5 : ÉCHEC ; mesure {2020: 3.331, 2021: 4.077, 2022: -3.505, 2023: -4.583, 2024: -1.653, 2025: -2.75} ; seuil {sharpe_min: -1, positives_min: 4}
- C6 : ÉCHEC ; mesure 0.2389 ; seuil 0.2
- C7 : ÉCHEC ; mesure None ; seuil {part_voisins_min: 0.75, ratio: 0.6, sharpe_voisin_min: 0.5}
- C8 : ÉCHEC ; mesure (-0.2753, -0.0009863) ; seuil (2, 0.3)
- C9 : OK ; mesure 0 ; seuil {aleatoires: 20, fixes: 3, part_non_pleine_min: 0.4, tolerance: 1e-09}
- C11 : ÉCHEC ; mesure (-1.052, -1.569) ; seuil (0.5, 0)
- C12 : ÉCHEC ; mesure (1.056, 25.5) ; seuil (0.5, 40)
- C13 : ÉCHEC ; mesure (1.503, -2.607) ; seuil 0
- C14 : ÉCHEC ; mesure -0.005548 ; seuil 0.04
- C15 : OK ; mesure non applicable (couvert) ; seuil None
- C16 : ÉCHEC ; mesure None ; seuil 0.6
- C2 : ÉCHEC ; mesure -0.2583 ; seuil 0.5
- C3 : ÉCHEC ; mesure -0.3182 ; seuil 2
- C4 : ÉCHEC ; mesure -3.008 ; seuil 0
- C10 : ÉCHEC ; mesure 0.6381 ; seuil 0.05

### R0013 (c-carry-rang {k: 3, tampon: 1})
- C1 : ÉCHEC ; mesure 4.4e-62 ; seuil 0.95
- C5 : ÉCHEC ; mesure {2020: 0.2653, 2021: 4.001, 2022: -3.714, 2023: -5.433, 2024: -4.453, 2025: -3.681} ; seuil {sharpe_min: -1, positives_min: 4}
- C6 : ÉCHEC ; mesure 0.2943 ; seuil 0.2
- C7 : ÉCHEC ; mesure None ; seuil {part_voisins_min: 0.75, ratio: 0.6, sharpe_voisin_min: 0.5}
- C8 : ÉCHEC ; mesure (-1.71, -0.0006558) ; seuil (2, 0.3)
- C9 : OK ; mesure 0 ; seuil {aleatoires: 20, fixes: 3, part_non_pleine_min: 0.4, tolerance: 1e-09}
- C11 : ÉCHEC ; mesure (-2.256, -2.868) ; seuil (0.5, 0)
- C12 : ÉCHEC ; mesure (1.291, 30.19) ; seuil (0.5, 40)
- C13 : ÉCHEC ; mesure (0.5465, -4.042) ; seuil 0
- C14 : ÉCHEC ; mesure -0.02791 ; seuil 0.04
- C15 : OK ; mesure non applicable (couvert) ; seuil None
- C16 : ÉCHEC ; mesure None ; seuil 0.6
- C2 : ÉCHEC ; mesure -1.345 ; seuil 0.5
- C3 : ÉCHEC ; mesure -1.708 ; seuil 2
- C4 : ÉCHEC ; mesure -4.267 ; seuil 0
- C10 : ÉCHEC ; mesure 0.9674 ; seuil 0.05

### R0014 (c-carry-rang {k: 3, tampon: 2})
- C1 : ÉCHEC ; mesure 3.113e-46 ; seuil 0.95
- C5 : ÉCHEC ; mesure {2020: 2.808, 2021: 4.404, 2022: -3.793, 2023: -5.368, 2024: -2.739, 2025: -3.524} ; seuil {sharpe_min: -1, positives_min: 4}
- C6 : ÉCHEC ; mesure 0.2504 ; seuil 0.2
- C7 : ÉCHEC ; mesure 0 ; seuil {part_voisins_min: 0.75, ratio: 0.6, sharpe_voisin_min: 0.5}
- C8 : ÉCHEC ; mesure (-0.6664, -0.00084) ; seuil (2, 0.3)
- C9 : OK ; mesure 0 ; seuil {aleatoires: 20, fixes: 3, part_non_pleine_min: 0.4, tolerance: 1e-09}
- C11 : ÉCHEC ; mesure (-1.45, -2.013) ; seuil (0.5, 0)
- C12 : ÉCHEC ; mesure (1.116, 25.02) ; seuil (0.5, 40)
- C13 : ÉCHEC ; mesure (1.393, -3.419) ; seuil 0
- C14 : ÉCHEC ; mesure -0.01121 ; seuil 0.04
- C15 : OK ; mesure non applicable (couvert) ; seuil None
- C16 : ÉCHEC ; mesure None ; seuil 0.6
- C2 : ÉCHEC ; mesure -0.5806 ; seuil 0.5
- C3 : ÉCHEC ; mesure -0.6997 ; seuil 2
- C4 : ÉCHEC ; mesure -3.67 ; seuil 0
- C10 : ÉCHEC ; mesure 0.7706 ; seuil 0.05

### R0015 (c-carry-rang {k: 3, tampon: 4})
- C1 : ÉCHEC ; mesure 1.523e-38 ; seuil 0.95
- C5 : ÉCHEC ; mesure {2020: 2.919, 2021: 5.235, 2022: -3.848, 2023: -4.936, 2024: -1.505, 2025: -3.279} ; seuil {sharpe_min: -1, positives_min: 4}
- C6 : ÉCHEC ; mesure 0.2237 ; seuil 0.2
- C7 : ÉCHEC ; mesure None ; seuil {part_voisins_min: 0.75, ratio: 0.6, sharpe_voisin_min: 0.5}
- C8 : ÉCHEC ; mesure (-0.1595, -0.0008826) ; seuil (2, 0.3)
- C9 : OK ; mesure 0 ; seuil {aleatoires: 20, fixes: 3, part_non_pleine_min: 0.4, tolerance: 1e-09}
- C11 : ÉCHEC ; mesure (-0.999, -1.566) ; seuil (0.5, 0)
- C12 : ÉCHEC ; mesure (1.035, 22.43) ; seuil (0.5, 40)
- C13 : ÉCHEC ; mesure (1.685, -2.814) ; seuil 0
- C14 : ÉCHEC ; mesure -0.00345 ; seuil 0.04
- C15 : OK ; mesure non applicable (couvert) ; seuil None
- C16 : ÉCHEC ; mesure None ; seuil 0.6
- C2 : ÉCHEC ; mesure -0.1744 ; seuil 0.5
- C3 : ÉCHEC ; mesure -0.1984 ; seuil 2
- C4 : ÉCHEC ; mesure -3.209 ; seuil 0
- C10 : ÉCHEC ; mesure 0.5831 ; seuil 0.05

### R0016 (c-carry-rang {k: 5, tampon: 1})
- C1 : ÉCHEC ; mesure 3.646e-49 ; seuil 0.95
- C5 : ÉCHEC ; mesure {2020: 2.45, 2021: 4.883, 2022: -3.895, 2023: -5.442, 2024: -3.292, 2025: -4.336} ; seuil {sharpe_min: -1, positives_min: 4}
- C6 : ÉCHEC ; mesure 0.2565 ; seuil 0.2
- C7 : ÉCHEC ; mesure None ; seuil {part_voisins_min: 0.75, ratio: 0.6, sharpe_voisin_min: 0.5}
- C8 : ÉCHEC ; mesure (-0.795, -0.0005224) ; seuil (2, 0.3)
- C9 : OK ; mesure 0 ; seuil {aleatoires: 20, fixes: 3, part_non_pleine_min: 0.4, tolerance: 1e-09}
- C11 : ÉCHEC ; mesure (-1.61, -2.225) ; seuil (0.5, 0)
- C12 : ÉCHEC ; mesure (1.138, 21.83) ; seuil (0.5, 40)
- C13 : ÉCHEC ; mesure (1.386, -3.804) ; seuil 0
- C14 : ÉCHEC ; mesure -0.01307 ; seuil 0.04
- C15 : OK ; mesure non applicable (couvert) ; seuil None
- C16 : ÉCHEC ; mesure None ; seuil 0.6
- C2 : ÉCHEC ; mesure -0.7179 ; seuil 0.5
- C3 : ÉCHEC ; mesure -0.8066 ; seuil 2
- C4 : ÉCHEC ; mesure -4.003 ; seuil 0
- C10 : ÉCHEC ; mesure 0.7988 ; seuil 0.05

### R0017 (c-carry-rang {k: 5, tampon: 2})
- C1 : ÉCHEC ; mesure 2.714e-47 ; seuil 0.95
- C5 : ÉCHEC ; mesure {2020: 2.188, 2021: 4.866, 2022: -3.796, 2023: -5.162, 2024: -2.754, 2025: -4.018} ; seuil {sharpe_min: -1, positives_min: 4}
- C6 : ÉCHEC ; mesure 0.2454 ; seuil 0.2
- C7 : ÉCHEC ; mesure None ; seuil {part_voisins_min: 0.75, ratio: 0.6, sharpe_voisin_min: 0.5}
- C8 : ÉCHEC ; mesure (-0.6482, -0.001113) ; seuil (2, 0.3)
- C9 : OK ; mesure 0 ; seuil {aleatoires: 20, fixes: 3, part_non_pleine_min: 0.4, tolerance: 1e-09}
- C11 : ÉCHEC ; mesure (-1.495, -2.082) ; seuil (0.5, 0)
- C12 : ÉCHEC ; mesure (1.122, 20.61) ; seuil (0.5, 40)
- C13 : ÉCHEC ; mesure (1.316, -3.44) ; seuil 0
- C14 : ÉCHEC ; mesure -0.01124 ; seuil 0.04
- C15 : OK ; mesure non applicable (couvert) ; seuil None
- C16 : ÉCHEC ; mesure None ; seuil 0.6
- C2 : ÉCHEC ; mesure -0.6193 ; seuil 0.5
- C3 : ÉCHEC ; mesure -0.6931 ; seuil 2
- C4 : ÉCHEC ; mesure -3.831 ; seuil 0
- C10 : ÉCHEC ; mesure 0.7656 ; seuil 0.05

### R0018 (c-carry-rang {k: 5, tampon: 4})
- C1 : ÉCHEC ; mesure 6.107e-43 ; seuil 0.95
- C5 : ÉCHEC ; mesure {2020: 2.038, 2021: 5.404, 2022: -3.796, 2023: -5.101, 2024: -1.178, 2025: -4.051} ; seuil {sharpe_min: -1, positives_min: 4}
- C6 : ÉCHEC ; mesure 0.2165 ; seuil 0.2
- C7 : ÉCHEC ; mesure None ; seuil {part_voisins_min: 0.75, ratio: 0.6, sharpe_voisin_min: 0.5}
- C8 : ÉCHEC ; mesure (-0.4126, -0.0004744) ; seuil (2, 0.3)
- C9 : OK ; mesure 0 ; seuil {aleatoires: 20, fixes: 3, part_non_pleine_min: 0.4, tolerance: 1e-09}
- C11 : ÉCHEC ; mesure (-1.192, -1.733) ; seuil (0.5, 0)
- C12 : ÉCHEC ; mesure (1.076, 18.3) ; seuil (0.5, 40)
- C13 : ÉCHEC ; mesure (1.406, -2.993) ; seuil 0
- C14 : ÉCHEC ; mesure -0.006832 ; seuil 0.04
- C15 : OK ; mesure non applicable (couvert) ; seuil None
- C16 : ÉCHEC ; mesure None ; seuil 0.6
- C2 : ÉCHEC ; mesure -0.382 ; seuil 0.5
- C3 : ÉCHEC ; mesure -0.4289 ; seuil 2
- C4 : ÉCHEC ; mesure -3.507 ; seuil 0
- C10 : ÉCHEC ; mesure 0.6763 ; seuil 0.05

### R0019 (c-carry-regime {entree: 0.09, plafond_extreme: 0.25})
- C1 : ÉCHEC ; mesure 4.583e-230 ; seuil 0.95
- C5 : ÉCHEC ; mesure {2020: -5.173, 2021: -5.42, 2022: -4.509, 2023: -3.71, 2024: -5.229, 2025: -5.202} ; seuil {sharpe_min: -1, positives_min: 4}
- C6 : ÉCHEC ; mesure 0.3913 ; seuil 0.2
- C7 : ÉCHEC ; mesure None ; seuil {part_voisins_min: 0.75, ratio: 0.6, sharpe_voisin_min: 0.5}
- C8 : ÉCHEC ; mesure (-7.302, -0.001132) ; seuil (2, 0.3)
- C9 : OK ; mesure 0 ; seuil {aleatoires: 20, fixes: 3, part_non_pleine_min: 0.4, tolerance: 1e-09}
- C11 : ÉCHEC ; mesure (-5.061, -5.35) ; seuil (0.5, 0)
- C12 : ÉCHEC ; mesure (2.671, 30.04) ; seuil (0.5, 40)
- C13 : ÉCHEC ; mesure (-4.933, -4.223) ; seuil 0
- C14 : ÉCHEC ; mesure -0.07354 ; seuil 0.04
- C15 : OK ; mesure non applicable (couvert) ; seuil None
- C16 : ÉCHEC ; mesure None ; seuil 0.6
- C2 : ÉCHEC ; mesure -4.489 ; seuil 0.5
- C3 : ÉCHEC ; mesure -7.422 ; seuil 2
- C4 : ÉCHEC ; mesure -6.486 ; seuil 0
- C10 : ÉCHEC ; mesure 1 ; seuil 0.05

### R0020 (c-carry-regime {entree: 0.09, plafond_extreme: 0.5})
- C1 : ÉCHEC ; mesure 2.703e-85 ; seuil 0.95
- C5 : ÉCHEC ; mesure {2020: -1.086, 2021: -1.615, 2022: -4.509, 2023: -3.531, 2024: -1.941, 2025: -5.202} ; seuil {sharpe_min: -1, positives_min: 4}
- C6 : ÉCHEC ; mesure 0.2351 ; seuil 0.2
- C7 : ÉCHEC ; mesure None ; seuil {part_voisins_min: 0.75, ratio: 0.6, sharpe_voisin_min: 0.5}
- C8 : ÉCHEC ; mesure (-3.86, -0.0004438) ; seuil (2, 0.3)
- C9 : OK ; mesure 0 ; seuil {aleatoires: 20, fixes: 3, part_non_pleine_min: 0.4, tolerance: 1e-09}
- C11 : ÉCHEC ; mesure (-3.38, -3.804) ; seuil (0.5, 0)
- C12 : ÉCHEC ; mesure (1.584, 26.31) ; seuil (0.5, 40)
- C13 : ÉCHEC ; mesure (-2.102, -3.082) ; seuil 0
- C14 : ÉCHEC ; mesure -0.03839 ; seuil 0.04
- C15 : OK ; mesure non applicable (couvert) ; seuil None
- C16 : ÉCHEC ; mesure None ; seuil 0.6
- C2 : ÉCHEC ; mesure -2.315 ; seuil 0.5
- C3 : ÉCHEC ; mesure -3.912 ; seuil 2
- C4 : ÉCHEC ; mesure -5.184 ; seuil 0
- C10 : ÉCHEC ; mesure 0.9996 ; seuil 0.05

### R0021 (c-carry-regime {entree: 0.09, plafond_extreme: 1})
- C1 : ÉCHEC ; mesure 4.983e-44 ; seuil 0.95
- C5 : ÉCHEC ; mesure {2020: 2.075, 2021: 4.96, 2022: -4.509, 2023: -3.531, 2024: -1.574, 2025: -5.202} ; seuil {sharpe_min: -1, positives_min: 4}
- C6 : OK ; mesure 0.1748 ; seuil 0.2
- C7 : ÉCHEC ; mesure None ; seuil {part_voisins_min: 0.75, ratio: 0.6, sharpe_voisin_min: 0.5}
- C8 : ÉCHEC ; mesure (-0.4947, -0.001242) ; seuil (2, 0.3)
- C9 : OK ; mesure 0 ; seuil {aleatoires: 20, fixes: 3, part_non_pleine_min: 0.4, tolerance: 1e-09}
- C11 : ÉCHEC ; mesure (-1.442, -2.075) ; seuil (0.5, 0)
- C12 : ÉCHEC ; mesure (1.082, 24.22) ; seuil (0.5, 40)
- C13 : ÉCHEC ; mesure (1.068, -2.965) ; seuil 0
- C14 : ÉCHEC ; mesure -0.007086 ; seuil 0.04
- C15 : OK ; mesure non applicable (couvert) ; seuil None
- C16 : ÉCHEC ; mesure None ; seuil 0.6
- C2 : ÉCHEC ; mesure -0.4901 ; seuil 0.5
- C3 : ÉCHEC ; mesure -0.5677 ; seuil 2
- C4 : ÉCHEC ; mesure -4.395 ; seuil 0
- C10 : ÉCHEC ; mesure 0.7179 ; seuil 0.05

### R0022 (c-carry-regime {entree: 0.135, plafond_extreme: 0.25})
- C1 : ÉCHEC ; mesure 1.513e-204 ; seuil 0.95
- C5 : ÉCHEC ; mesure {2020: -5.648, 2021: -5.874, 2022: -2.454, 2023: -2.15, 2024: -4.361, 2025: -3.361} ; seuil {sharpe_min: -1, positives_min: 4}
- C6 : ÉCHEC ; mesure 0.3435 ; seuil 0.2
- C7 : ÉCHEC ; mesure None ; seuil {part_voisins_min: 0.75, ratio: 0.6, sharpe_voisin_min: 0.5}
- C8 : ÉCHEC ; mesure (-6.031, -0.001104) ; seuil (2, 0.3)
- C9 : OK ; mesure 0 ; seuil {aleatoires: 20, fixes: 3, part_non_pleine_min: 0.4, tolerance: 1e-09}
- C11 : ÉCHEC ; mesure (-4.467, -4.762) ; seuil (0.5, 0)
- C12 : ÉCHEC ; mesure (2.619, 24.88) ; seuil (0.5, 40)
- C13 : ÉCHEC ; mesure (-4.656, -3.085) ; seuil 0
- C14 : ÉCHEC ; mesure -0.06272 ; seuil 0.04
- C15 : OK ; mesure non applicable (couvert) ; seuil None
- C16 : ÉCHEC ; mesure None ; seuil 0.6
- C2 : ÉCHEC ; mesure -3.895 ; seuil 0.5
- C3 : ÉCHEC ; mesure -6.121 ; seuil 2
- C4 : ÉCHEC ; mesure -5.651 ; seuil 0
- C10 : ÉCHEC ; mesure 1 ; seuil 0.05

### R0023 (c-carry-regime {entree: 0.135, plafond_extreme: 0.5})
- C1 : ÉCHEC ; mesure 2.453e-70 ; seuil 0.95
- C5 : ÉCHEC ; mesure {2020: -1.44, 2021: -2.021, 2022: -2.454, 2023: -1.963, 2024: -1.041, 2025: -3.361} ; seuil {sharpe_min: -1, positives_min: 4}
- C6 : OK ; mesure 0.1674 ; seuil 0.2
- C7 : ÉCHEC ; mesure 0 ; seuil {part_voisins_min: 0.75, ratio: 0.6, sharpe_voisin_min: 0.5}
- C8 : ÉCHEC ; mesure (-2.759, -0.0004357) ; seuil (2, 0.3)
- C9 : OK ; mesure 0 ; seuil {aleatoires: 20, fixes: 3, part_non_pleine_min: 0.4, tolerance: 1e-09}
- C11 : ÉCHEC ; mesure (-2.621, -3.036) ; seuil (0.5, 0)
- C12 : ÉCHEC ; mesure (1.422, 20.88) ; seuil (0.5, 40)
- C13 : ÉCHEC ; mesure (-1.73, -1.69) ; seuil 0
- C14 : ÉCHEC ; mesure -0.02576 ; seuil 0.04
- C15 : OK ; mesure non applicable (couvert) ; seuil None
- C16 : ÉCHEC ; mesure None ; seuil 0.6
- C2 : ÉCHEC ; mesure -1.596 ; seuil 0.5
- C3 : ÉCHEC ; mesure -2.812 ; seuil 2
- C4 : ÉCHEC ; mesure -4.233 ; seuil 0
- C10 : ÉCHEC ; mesure 0.9964 ; seuil 0.05

### R0024 (c-carry-regime {entree: 0.135, plafond_extreme: 1})
- C1 : ÉCHEC ; mesure 2.141e-28 ; seuil 0.95
- C5 : ÉCHEC ; mesure {2020: 1.713, 2021: 3.868, 2022: -2.454, 2023: -1.963, 2024: -0.6901, 2025: -3.361} ; seuil {sharpe_min: -1, positives_min: 4}
- C6 : OK ; mesure 0.09418 ; seuil 0.2
- C7 : ÉCHEC ; mesure None ; seuil {part_voisins_min: 0.75, ratio: 0.6, sharpe_voisin_min: 0.5}
- C8 : ÉCHEC ; mesure (0.6234, -0.001238) ; seuil (2, 0.3)
- C9 : OK ; mesure 0 ; seuil {aleatoires: 20, fixes: 3, part_non_pleine_min: 0.4, tolerance: 1e-09}
- C11 : ÉCHEC ; mesure (-0.4441, -1.082) ; seuil (0.5, 0)
- C12 : ÉCHEC ; mesure (0.9241, 18.79) ; seuil (0.5, 40)
- C13 : ÉCHEC ; mesure (1.572, -1.549) ; seuil 0
- C14 : ÉCHEC ; mesure 0.006024 ; seuil 0.04
- C15 : OK ; mesure non applicable (couvert) ; seuil None
- C16 : ÉCHEC ; mesure None ; seuil 0.6
- C2 : ÉCHEC ; mesure 0.4515 ; seuil 0.5
- C3 : ÉCHEC ; mesure 0.5338 ; seuil 2
- C4 : ÉCHEC ; mesure -3.25 ; seuil 0
- C10 : ÉCHEC ; mesure 0.2871 ; seuil 0.05

### R0025 (c-carry-regime {entree: 0.2, plafond_extreme: 0.25})
- C1 : ÉCHEC ; mesure 6.715e-221 ; seuil 0.95
- C5 : ÉCHEC ; mesure {2020: -5.598, 2021: -5.979, 2022: -2.441, 2023: -1.412, 2024: -4.689, 2025: -2.594} ; seuil {sharpe_min: -1, positives_min: 4}
- C6 : ÉCHEC ; mesure 0.3494 ; seuil 0.2
- C7 : ÉCHEC ; mesure None ; seuil {part_voisins_min: 0.75, ratio: 0.6, sharpe_voisin_min: 0.5}
- C8 : ÉCHEC ; mesure (-5.721, -0.0003341) ; seuil (2, 0.3)
- C9 : OK ; mesure 0 ; seuil {aleatoires: 20, fixes: 3, part_non_pleine_min: 0.4, tolerance: 1e-09}
- C11 : ÉCHEC ; mesure (-4.38, -4.652) ; seuil (0.5, 0)
- C12 : ÉCHEC ; mesure (3.099, 22.58) ; seuil (0.5, 40)
- C13 : ÉCHEC ; mesure (-4.614, -3.011) ; seuil 0
- C14 : ÉCHEC ; mesure -0.064 ; seuil 0.04
- C15 : OK ; mesure non applicable (couvert) ; seuil None
- C16 : ÉCHEC ; mesure None ; seuil 0.6
- C2 : ÉCHEC ; mesure -3.835 ; seuil 0.5
- C3 : ÉCHEC ; mesure -5.725 ; seuil 2
- C4 : ÉCHEC ; mesure -5.046 ; seuil 0
- C10 : ÉCHEC ; mesure 1 ; seuil 0.05

### R0026 (c-carry-regime {entree: 0.2, plafond_extreme: 0.5})
- C1 : ÉCHEC ; mesure 7.153e-75 ; seuil 0.95
- C5 : ÉCHEC ; mesure {2020: -1.672, 2021: -2.123, 2022: -2.441, 2023: -1.265, 2024: -1.181, 2025: -2.594} ; seuil {sharpe_min: -1, positives_min: 4}
- C6 : OK ; mesure 0.1547 ; seuil 0.2
- C7 : ÉCHEC ; mesure None ; seuil {part_voisins_min: 0.75, ratio: 0.6, sharpe_voisin_min: 0.5}
- C8 : ÉCHEC ; mesure (-2.652, 0.0003698) ; seuil (2, 0.3)
- C9 : OK ; mesure 0 ; seuil {aleatoires: 20, fixes: 3, part_non_pleine_min: 0.4, tolerance: 1e-09}
- C11 : ÉCHEC ; mesure (-2.503, -2.902) ; seuil (0.5, 0)
- C12 : ÉCHEC ; mesure (1.439, 18.93) ; seuil (0.5, 40)
- C13 : ÉCHEC ; mesure (-1.719, -1.503) ; seuil 0
- C14 : ÉCHEC ; mesure -0.02348 ; seuil 0.04
- C15 : OK ; mesure non applicable (couvert) ; seuil None
- C16 : ÉCHEC ; mesure None ; seuil 0.6
- C2 : ÉCHEC ; mesure -1.528 ; seuil 0.5
- C3 : ÉCHEC ; mesure -2.609 ; seuil 2
- C4 : ÉCHEC ; mesure -3.915 ; seuil 0
- C10 : ÉCHEC ; mesure 0.9928 ; seuil 0.05

### R0027 (c-carry-regime {entree: 0.2, plafond_extreme: 1})
- C1 : ÉCHEC ; mesure 6.585e-24 ; seuil 0.95
- C5 : ÉCHEC ; mesure {2020: 1.467, 2021: 4.172, 2022: -2.441, 2023: -1.265, 2024: -0.8121, 2025: -2.594} ; seuil {sharpe_min: -1, positives_min: 4}
- C6 : OK ; mesure 0.07255 ; seuil 0.2
- C7 : ÉCHEC ; mesure None ; seuil {part_voisins_min: 0.75, ratio: 0.6, sharpe_voisin_min: 0.5}
- C8 : ÉCHEC ; mesure (0.9046, -0.0004968) ; seuil (2, 0.3)
- C9 : OK ; mesure 0 ; seuil {aleatoires: 20, fixes: 3, part_non_pleine_min: 0.4, tolerance: 1e-09}
- C11 : ÉCHEC ; mesure (-0.1686, -0.8041) ; seuil (0.5, 0)
- C12 : ÉCHEC ; mesure (0.8712, 16.72) ; seuil (0.5, 40)
- C13 : ÉCHEC ; mesure (1.866, -1.348) ; seuil 0
- C14 : ÉCHEC ; mesure 0.009395 ; seuil 0.04
- C15 : OK ; mesure non applicable (couvert) ; seuil None
- C16 : ÉCHEC ; mesure None ; seuil 0.6
- C2 : OK ; mesure 0.7327 ; seuil 0.5
- C3 : ÉCHEC ; mesure 0.8511 ; seuil 2
- C4 : ÉCHEC ; mesure -2.71 ; seuil 0
- C10 : ÉCHEC ; mesure 0.1938 ; seuil 0.05

### R0028 (m-semivar {L_jours: 14, s: 0.1})
- C1 : ÉCHEC ; mesure 0.3267 ; seuil 0.95
- C5 : ÉCHEC ; mesure {2020: 1.944, 2021: 2.834, 2022: -1.043, 2023: 1.889, 2024: 1.227, 2025: -0.7852} ; seuil {sharpe_min: -1, positives_min: 4}
- C6 : ÉCHEC ; mesure 0.567 ; seuil 0.45
- C7 : ÉCHEC ; mesure None ; seuil {part_voisins_min: 0.75, ratio: 0.6, sharpe_voisin_min: 0.5}
- C8 : ÉCHEC ; mesure 0.9626 ; seuil 0.05
- C9 : OK ; mesure 0 ; seuil {aleatoires: 20, fixes: 3, part_non_pleine_min: 0.4, tolerance: 1e-09}
- C11 : ÉCHEC ; mesure (0.3115, -0.2928) ; seuil (0.532, 0)
- C12 : ÉCHEC ; mesure (0.1774, 18.05) ; seuil (0.5, 15)
- C13 : OK ; mesure (1.623, 0.2341) ; seuil 0
- C14 : OK ; mesure 0.4774 ; seuil 0.04
- C15 : ÉCHEC ; mesure None ; seuil (0, 0.585)
- C16 : ÉCHEC ; mesure None ; seuil 0.6
- C2 : OK ; mesure 1.064 ; seuil 0.5
- C3 : OK ; mesure 2.093 ; seuil 2
- C4 : OK ; mesure 0.8341 ; seuil 0
- C10 : OK ; mesure 0.02539 ; seuil 0.05

### R0029 (m-semivar {L_jours: 14, s: 0.2})
- C1 : ÉCHEC ; mesure 0.3224 ; seuil 0.95
- C5 : ÉCHEC ; mesure {2020: 1.714, 2021: 2.849, 2022: -1.081, 2023: 1.912, 2024: 0.8734, 2025: -0.2922} ; seuil {sharpe_min: -1, positives_min: 4}
- C6 : ÉCHEC ; mesure 0.5261 ; seuil 0.45
- C7 : ÉCHEC ; mesure None ; seuil {part_voisins_min: 0.75, ratio: 0.6, sharpe_voisin_min: 0.5}
- C8 : ÉCHEC ; mesure 0.9614 ; seuil 0.05
- C9 : OK ; mesure 0 ; seuil {aleatoires: 20, fixes: 3, part_non_pleine_min: 0.4, tolerance: 1e-09}
- C11 : ÉCHEC ; mesure (0.3263, -0.2602) ; seuil (0.5292, 0)
- C12 : OK ; mesure (0.1205, 11.64) ; seuil (0.5, 15)
- C13 : OK ; mesure (1.609, 0.2389) ; seuil 0
- C14 : OK ; mesure 0.4813 ; seuil 0.04
- C15 : ÉCHEC ; mesure None ; seuil (0, 0.585)
- C16 : ÉCHEC ; mesure None ; seuil 0.6
- C2 : OK ; mesure 1.058 ; seuil 0.5
- C3 : OK ; mesure 2.155 ; seuil 2
- C4 : OK ; mesure 0.9138 ; seuil 0
- C10 : OK ; mesure 0.0208 ; seuil 0.05

### R0030 (m-semivar {L_jours: 14, s: 0.4})
- C1 : ÉCHEC ; mesure 0.07692 ; seuil 0.95
- C5 : ÉCHEC ; mesure {2020: 0.04066, 2021: 2.425, 2022: -1.507, 2023: 1.386, 2024: 1.425, 2025: 0.1503} ; seuil {sharpe_min: -1, positives_min: 4}
- C6 : ÉCHEC ; mesure 0.6918 ; seuil 0.45
- C7 : ÉCHEC ; mesure None ; seuil {part_voisins_min: 0.75, ratio: 0.6, sharpe_voisin_min: 0.5}
- C8 : ÉCHEC ; mesure 0.9954 ; seuil 0.05
- C9 : ÉCHEC ; mesure 0 ; seuil {aleatoires: 20, fixes: 3, part_non_pleine_min: 0.4, tolerance: 1e-09}
- C11 : ÉCHEC ; mesure (-0.1317, -0.6851) ; seuil (0.5, 0)
- C12 : OK ; mesure (0.09006, 5.424) ; seuil (0.5, 15)
- C13 : OK ; mesure (0.7689, 0.6259) ; seuil 0
- C14 : OK ; mesure 0.2294 ; seuil 0.04
- C15 : ÉCHEC ; mesure None ; seuil (0, 0.585)
- C16 : ÉCHEC ; mesure None ; seuil 0.6
- C2 : OK ; mesure 0.6721 ; seuil 0.5
- C3 : ÉCHEC ; mesure 1.55 ; seuil 2
- C4 : OK ; mesure 0.6058 ; seuil 0
- C10 : ÉCHEC ; mesure 0.06519 ; seuil 0.05

### R0031 (m-semivar {L_jours: 28, s: 0.1})
- C1 : ÉCHEC ; mesure 0.4201 ; seuil 0.95
- C5 : OK ; mesure {2020: 1.864, 2021: 3.14, 2022: -0.9929, 2023: 2.158, 2024: 0.8957, 2025: -0.397} ; seuil {sharpe_min: -1, positives_min: 4}
- C6 : ÉCHEC ; mesure 0.5601 ; seuil 0.45
- C7 : ÉCHEC ; mesure None ; seuil {part_voisins_min: 0.75, ratio: 0.6, sharpe_voisin_min: 0.5}
- C8 : ÉCHEC ; mesure 0.9162 ; seuil 0.05
- C9 : OK ; mesure 0 ; seuil {aleatoires: 20, fixes: 3, part_non_pleine_min: 0.4, tolerance: 1e-09}
- C11 : ÉCHEC ; mesure (0.4489, -0.1322) ; seuil (0.5807, 0)
- C12 : OK ; mesure (0.1019, 10.57) ; seuil (0.5, 15)
- C13 : OK ; mesure (1.72, 0.3467) ; seuil 0
- C14 : OK ; mesure 0.5566 ; seuil 0.04
- C15 : ÉCHEC ; mesure None ; seuil (0, 0.585)
- C16 : ÉCHEC ; mesure None ; seuil 0.6
- C2 : OK ; mesure 1.161 ; seuil 0.5
- C3 : OK ; mesure 2.383 ; seuil 2
- C4 : OK ; mesure 1.03 ; seuil 0
- C10 : OK ; mesure 0.0124 ; seuil 0.05

### R0032 (m-semivar {L_jours: 28, s: 0.2})
- C1 : ÉCHEC ; mesure 0.1338 ; seuil 0.95
- C5 : ÉCHEC ; mesure {2020: 0.62, 2021: 2.722, 2022: -1.933, 2023: 1.394, 2024: 0.8407, 2025: -0.5722} ; seuil {sharpe_min: -1, positives_min: 4}
- C6 : ÉCHEC ; mesure 0.5941 ; seuil 0.45
- C7 : OK ; mesure 1 ; seuil {part_voisins_min: 0.75, ratio: 0.6, sharpe_voisin_min: 0.5}
- C8 : ÉCHEC ; mesure 0.991 ; seuil 0.05
- C9 : OK ; mesure 0 ; seuil {aleatoires: 20, fixes: 3, part_non_pleine_min: 0.4, tolerance: 1e-09}
- C11 : ÉCHEC ; mesure (0.02665, -0.5657) ; seuil (0.5, 0)
- C12 : OK ; mesure (0.1003, 7.294) ; seuil (0.5, 15)
- C13 : OK ; mesure (1.203, 0.1721) ; seuil 0
- C14 : OK ; mesure 0.3097 ; seuil 0.04
- C15 : ÉCHEC ; mesure None ; seuil (0, 0.585)
- C16 : ÉCHEC ; mesure None ; seuil 0.6
- C2 : OK ; mesure 0.7992 ; seuil 0.5
- C3 : ÉCHEC ; mesure 1.738 ; seuil 2
- C4 : OK ; mesure 0.7104 ; seuil 0
- C10 : OK ; mesure 0.04699 ; seuil 0.05

### R0033 (m-semivar {L_jours: 28, s: 0.4})
- C1 : ÉCHEC ; mesure 0.05612 ; seuil 0.95
- C5 : OK ; mesure {2020: 0.7369, 2021: 2.053, 2022: -0.8208, 2023: 0.9882, 2024: 1.244, 2025: -0.1703} ; seuil {sharpe_min: -1, positives_min: 4}
- C6 : ÉCHEC ; mesure 0.5364 ; seuil 0.45
- C7 : ÉCHEC ; mesure None ; seuil {part_voisins_min: 0.75, ratio: 0.6, sharpe_voisin_min: 0.5}
- C8 : ÉCHEC ; mesure 0.9962 ; seuil 0.05
- C9 : ÉCHEC ; mesure 0 ; seuil {aleatoires: 20, fixes: 3, part_non_pleine_min: 0.4, tolerance: 1e-09}
- C11 : ÉCHEC ; mesure (-0.1484, -0.688) ; seuil (0.5, 0)
- C12 : OK ; mesure (0.09128, 4.085) ; seuil (0.5, 15)
- C13 : OK ; mesure (0.8889, 0.1773) ; seuil 0
- C14 : OK ; mesure 0.1813 ; seuil 0.04
- C15 : ÉCHEC ; mesure None ; seuil (0, 0.585)
- C16 : ÉCHEC ; mesure None ; seuil 0.6
- C2 : OK ; mesure 0.6199 ; seuil 0.5
- C3 : ÉCHEC ; mesure 1.523 ; seuil 2
- C4 : OK ; mesure 0.5577 ; seuil 0
- C10 : ÉCHEC ; mesure 0.06839 ; seuil 0.05

### R0034 (m-semivar {L_jours: 56, s: 0.1})
- C1 : ÉCHEC ; mesure 0.0981 ; seuil 0.95
- C5 : ÉCHEC ; mesure {2020: -0.08109, 2021: 2.759, 2022: -1.448, 2023: 1.732, 2024: 1.112, 2025: -0.7943} ; seuil {sharpe_min: -1, positives_min: 4}
- C6 : ÉCHEC ; mesure 0.6371 ; seuil 0.45
- C7 : ÉCHEC ; mesure None ; seuil {part_voisins_min: 0.75, ratio: 0.6, sharpe_voisin_min: 0.5}
- C8 : ÉCHEC ; mesure 0.9926 ; seuil 0.05
- C9 : OK ; mesure 0 ; seuil {aleatoires: 20, fixes: 3, part_non_pleine_min: 0.4, tolerance: 1e-09}
- C11 : ÉCHEC ; mesure (-0.03672, -0.6055) ; seuil (0.5, 0)
- C12 : OK ; mesure (0.1086, 7.405) ; seuil (0.5, 15)
- C13 : OK ; mesure (1.007, 0.2852) ; seuil 0
- C14 : OK ; mesure 0.2603 ; seuil 0.04
- C15 : ÉCHEC ; mesure None ; seuil (0, 0.585)
- C16 : ÉCHEC ; mesure None ; seuil 0.6
- C2 : OK ; mesure 0.7191 ; seuil 0.5
- C3 : ÉCHEC ; mesure 1.504 ; seuil 2
- C4 : OK ; mesure 0.6317 ; seuil 0
- C10 : ÉCHEC ; mesure 0.07159 ; seuil 0.05

### R0035 (m-semivar {L_jours: 56, s: 0.2})
- C1 : ÉCHEC ; mesure 0.07341 ; seuil 0.95
- C5 : ÉCHEC ; mesure {2020: -0.06748, 2021: 2.413, 2022: -1.316, 2023: 1.799, 2024: 1.367, 2025: -0.1271} ; seuil {sharpe_min: -1, positives_min: 4}
- C6 : ÉCHEC ; mesure 0.6534 ; seuil 0.45
- C7 : ÉCHEC ; mesure None ; seuil {part_voisins_min: 0.75, ratio: 0.6, sharpe_voisin_min: 0.5}
- C8 : ÉCHEC ; mesure 0.9972 ; seuil 0.05
- C9 : OK ; mesure 0 ; seuil {aleatoires: 20, fixes: 3, part_non_pleine_min: 0.4, tolerance: 1e-09}
- C11 : ÉCHEC ; mesure (-0.1053, -0.6021) ; seuil (0.5, 0)
- C12 : OK ; mesure (0.08496, 5.48) ; seuil (0.5, 15)
- C13 : OK ; mesure (0.8234, 0.4484) ; seuil 0
- C14 : OK ; mesure 0.2312 ; seuil 0.04
- C15 : ÉCHEC ; mesure None ; seuil (0, 0.585)
- C16 : ÉCHEC ; mesure None ; seuil 0.6
- C2 : OK ; mesure 0.6628 ; seuil 0.5
- C3 : ÉCHEC ; mesure 1.587 ; seuil 2
- C4 : OK ; mesure 0.6015 ; seuil 0
- C10 : ÉCHEC ; mesure 0.06099 ; seuil 0.05

### R0036 (m-semivar {L_jours: 56, s: 0.4})
- C1 : ÉCHEC ; mesure 0.1397 ; seuil 0.95
- C5 : OK ; mesure {2020: 1.824, 2021: 1.863, 2022: -0.6568, 2023: 0.1823, 2024: 1.777, 2025: 0.5301} ; seuil {sharpe_min: -1, positives_min: 4}
- C6 : OK ; mesure 0.1936 ; seuil 0.45
- C7 : ÉCHEC ; mesure None ; seuil {part_voisins_min: 0.75, ratio: 0.6, sharpe_voisin_min: 0.5}
- C8 : ÉCHEC ; mesure 0.9864 ; seuil 0.05
- C9 : ÉCHEC ; mesure 0 ; seuil {aleatoires: 20, fixes: 3, part_non_pleine_min: 0.4, tolerance: 1e-09}
- C11 : ÉCHEC ; mesure (0.0008377, -0.6119) ; seuil (0.5, 0)
- C12 : OK ; mesure (0.06404, 1.739) ; seuil (0.5, 15)
- C13 : OK ; mesure (1.163, 0.54) ; seuil 0
- C14 : OK ; mesure 0.1493 ; seuil 0.04
- C15 : ÉCHEC ; mesure None ; seuil (0, 0.585)
- C16 : ÉCHEC ; mesure None ; seuil 0.6
- C2 : OK ; mesure 0.9058 ; seuil 0.5
- C3 : OK ; mesure 2.133 ; seuil 2
- C4 : OK ; mesure 0.8441 ; seuil 0
- C10 : OK ; mesure 0.02619 ; seuil 0.05

### R0037 (r-fonds-foule {L: 7, q: 0.5})
- C1 : ÉCHEC ; mesure 0.08991 ; seuil 0.95
- C5 : ÉCHEC ; mesure {2020: 1.657, 2021: 1.783, 2022: -1.065, 2023: 2.675, 2024: 1.498, 2025: -0.1062} ; seuil {sharpe_min: -1, positives_min: 4}
- C6 : ÉCHEC ; mesure 0.7347 ; seuil 0.45
- C7 : ÉCHEC ; mesure None ; seuil {part_voisins_min: 0.75, ratio: 0.6, sharpe_voisin_min: 0.5}
- C8 : ÉCHEC ; mesure 0.9482 ; seuil 0.05
- C9 : OK ; mesure 0 ; seuil {aleatoires: 20, fixes: 3, part_non_pleine_min: 0.4, tolerance: 1e-09}
- C11 : ÉCHEC ; mesure (-0.06173, -0.6449) ; seuil (0.5, 0)
- C12 : OK ; mesure (0.1025, 8.439) ; seuil (0.5, 15)
- C13 : OK ; mesure (0.9315, 0.3733) ; seuil 0
- C14 : OK ; mesure 0.2717 ; seuil 0.04
- C15 : ÉCHEC ; mesure None ; seuil (0, 0.585)
- C16 : ÉCHEC ; mesure None ; seuil 0.6
- C2 : OK ; mesure 0.7057 ; seuil 0.5
- C3 : ÉCHEC ; mesure 1.989 ; seuil 2
- C4 : OK ; mesure 0.6252 ; seuil 0
- C10 : OK ; mesure 0.02579 ; seuil 0.05

### R0038 (r-fonds-foule {L: 7, q: 0.7})
- C1 : ÉCHEC ; mesure 0.07657 ; seuil 0.95
- C5 : ÉCHEC ; mesure {2020: 1.657, 2021: 2.43, 2022: -1.065, 2023: 1.408, 2024: 1.057, 2025: -0.2595} ; seuil {sharpe_min: -1, positives_min: 4}
- C6 : ÉCHEC ; mesure 0.775 ; seuil 0.45
- C7 : ÉCHEC ; mesure None ; seuil {part_voisins_min: 0.75, ratio: 0.6, sharpe_voisin_min: 0.5}
- C8 : ÉCHEC ; mesure 0.9568 ; seuil 0.05
- C9 : OK ; mesure 0 ; seuil {aleatoires: 20, fixes: 3, part_non_pleine_min: 0.4, tolerance: 1e-09}
- C11 : ÉCHEC ; mesure (-0.04573, -0.598) ; seuil (0.5, 0)
- C12 : OK ; mesure (0.09539, 8.098) ; seuil (0.5, 15)
- C13 : OK ; mesure (1.108, 0.03879) ; seuil 0
- C14 : OK ; mesure 0.2471 ; seuil 0.04
- C15 : ÉCHEC ; mesure None ; seuil (0, 0.585)
- C16 : ÉCHEC ; mesure None ; seuil 0.6
- C2 : OK ; mesure 0.6733 ; seuil 0.5
- C3 : ÉCHEC ; mesure 1.785 ; seuil 2
- C4 : OK ; mesure 0.6026 ; seuil 0
- C10 : OK ; mesure 0.04199 ; seuil 0.05

### R0039 (r-fonds-foule {L: 7, q: 0.9})
- C1 : ÉCHEC ; mesure 0.1481 ; seuil 0.95
- C5 : ÉCHEC ; mesure {2020: 1.657, 2021: 2.421, 2022: -1.065, 2023: 1.826, 2024: 1.119, 2025: -0.2868} ; seuil {sharpe_min: -1, positives_min: 4}
- C6 : ÉCHEC ; mesure 0.7906 ; seuil 0.45
- C7 : ÉCHEC ; mesure None ; seuil {part_voisins_min: 0.75, ratio: 0.6, sharpe_voisin_min: 0.5}
- C8 : ÉCHEC ; mesure 0.9856 ; seuil 0.05
- C9 : OK ; mesure 0 ; seuil {aleatoires: 20, fixes: 3, part_non_pleine_min: 0.4, tolerance: 1e-09}
- C11 : ÉCHEC ; mesure (0.1251, -0.3901) ; seuil (0.5, 0)
- C12 : OK ; mesure (0.06857, 7.656) ; seuil (0.5, 15)
- C13 : OK ; mesure (1.216, 0.2695) ; seuil 0
- C14 : OK ; mesure 0.3922 ; seuil 0.04
- C15 : ÉCHEC ; mesure None ; seuil (0, 0.585)
- C16 : ÉCHEC ; mesure None ; seuil 0.6
- C2 : OK ; mesure 0.8252 ; seuil 0.5
- C3 : OK ; mesure 2.061 ; seuil 2
- C4 : OK ; mesure 0.7645 ; seuil 0
- C10 : OK ; mesure 0.022 ; seuil 0.05

### R0040 (r-fonds-foule {L: 14, q: 0.5})
- C1 : ÉCHEC ; mesure 0.07856 ; seuil 0.95
- C5 : ÉCHEC ; mesure {2020: 1.657, 2021: 2.126, 2022: -1.065, 2023: 2.772, 2024: 1.065, 2025: -0.5936} ; seuil {sharpe_min: -1, positives_min: 4}
- C6 : ÉCHEC ; mesure 0.7331 ; seuil 0.45
- C7 : ÉCHEC ; mesure None ; seuil {part_voisins_min: 0.75, ratio: 0.6, sharpe_voisin_min: 0.5}
- C8 : ÉCHEC ; mesure 0.9594 ; seuil 0.05
- C9 : OK ; mesure 0 ; seuil {aleatoires: 20, fixes: 3, part_non_pleine_min: 0.4, tolerance: 1e-09}
- C11 : ÉCHEC ; mesure (-0.08341, -0.6752) ; seuil (0.5, 0)
- C12 : OK ; mesure (0.09946, 7.745) ; seuil (0.5, 15)
- C13 : OK ; mesure (1.026, 0.1036) ; seuil 0
- C14 : OK ; mesure 0.2481 ; seuil 0.04
- C15 : ÉCHEC ; mesure None ; seuil (0, 0.585)
- C16 : ÉCHEC ; mesure None ; seuil 0.6
- C2 : OK ; mesure 0.6764 ; seuil 0.5
- C3 : ÉCHEC ; mesure 1.847 ; seuil 2
- C4 : OK ; mesure 0.6017 ; seuil 0
- C10 : OK ; mesure 0.03379 ; seuil 0.05

### R0041 (r-fonds-foule {L: 14, q: 0.7})
- C1 : ÉCHEC ; mesure 0.07024 ; seuil 0.95
- C5 : ÉCHEC ; mesure {2020: 1.657, 2021: 2.266, 2022: -1.065, 2023: 1.612, 2024: 0.9307, 2025: -0.2722} ; seuil {sharpe_min: -1, positives_min: 4}
- C6 : ÉCHEC ; mesure 0.7741 ; seuil 0.45
- C7 : OK ; mesure 1 ; seuil {part_voisins_min: 0.75, ratio: 0.6, sharpe_voisin_min: 0.5}
- C8 : ÉCHEC ; mesure 0.9708 ; seuil 0.05
- C9 : OK ; mesure 0 ; seuil {aleatoires: 20, fixes: 3, part_non_pleine_min: 0.4, tolerance: 1e-09}
- C11 : ÉCHEC ; mesure (-0.0294, -0.5751) ; seuil (0.5, 0)
- C12 : OK ; mesure (0.0915, 7.434) ; seuil (0.5, 15)
- C13 : OK ; mesure (1.054, 0.06476) ; seuil 0
- C14 : OK ; mesure 0.2295 ; seuil 0.04
- C15 : ÉCHEC ; mesure None ; seuil (0, 0.585)
- C16 : ÉCHEC ; mesure None ; seuil 0.6
- C2 : OK ; mesure 0.6535 ; seuil 0.5
- C3 : ÉCHEC ; mesure 1.718 ; seuil 2
- C4 : OK ; mesure 0.5875 ; seuil 0
- C10 : OK ; mesure 0.04579 ; seuil 0.05

### R0042 (r-fonds-foule {L: 14, q: 0.9})
- C1 : ÉCHEC ; mesure 0.1227 ; seuil 0.95
- C5 : ÉCHEC ; mesure {2020: 1.657, 2021: 2.082, 2022: -1.065, 2023: 1.826, 2024: 1.427, 2025: -0.2868} ; seuil {sharpe_min: -1, positives_min: 4}
- C6 : ÉCHEC ; mesure 0.7906 ; seuil 0.45
- C7 : ÉCHEC ; mesure None ; seuil {part_voisins_min: 0.75, ratio: 0.6, sharpe_voisin_min: 0.5}
- C8 : ÉCHEC ; mesure 0.9686 ; seuil 0.05
- C9 : OK ; mesure 0 ; seuil {aleatoires: 20, fixes: 3, part_non_pleine_min: 0.4, tolerance: 1e-09}
- C11 : ÉCHEC ; mesure (0.1131, -0.4029) ; seuil (0.5, 0)
- C12 : OK ; mesure (0.07131, 7.381) ; seuil (0.5, 15)
- C13 : OK ; mesure (1.079, 0.3573) ; seuil 0
- C14 : OK ; mesure 0.3395 ; seuil 0.04
- C15 : ÉCHEC ; mesure None ; seuil (0, 0.585)
- C16 : ÉCHEC ; mesure None ; seuil 0.6
- C2 : OK ; mesure 0.7766 ; seuil 0.5
- C3 : ÉCHEC ; mesure 1.983 ; seuil 2
- C4 : OK ; mesure 0.7172 ; seuil 0
- C10 : OK ; mesure 0.02819 ; seuil 0.05

### R0043 (r-fonds-foule {L: 28, q: 0.5})
- C1 : ÉCHEC ; mesure 0.0612 ; seuil 0.95
- C5 : ÉCHEC ; mesure {2020: 1.657, 2021: 2.309, 2022: -1.065, 2023: 1.823, 2024: 1.103, 2025: -0.08674} ; seuil {sharpe_min: -1, positives_min: 4}
- C6 : ÉCHEC ; mesure 0.7234 ; seuil 0.45
- C7 : ÉCHEC ; mesure None ; seuil {part_voisins_min: 0.75, ratio: 0.6, sharpe_voisin_min: 0.5}
- C8 : ÉCHEC ; mesure 0.9722 ; seuil 0.05
- C9 : OK ; mesure 0 ; seuil {aleatoires: 20, fixes: 3, part_non_pleine_min: 0.4, tolerance: 1e-09}
- C11 : ÉCHEC ; mesure (-0.1021, -0.664) ; seuil (0.5, 0)
- C12 : OK ; mesure (0.1016, 7.191) ; seuil (0.5, 15)
- C13 : OK ; mesure (0.9997, 0.007954) ; seuil 0
- C14 : OK ; mesure 0.2059 ; seuil 0.04
- C15 : ÉCHEC ; mesure None ; seuil (0, 0.585)
- C16 : ÉCHEC ; mesure None ; seuil 0.6
- C2 : OK ; mesure 0.6227 ; seuil 0.5
- C3 : ÉCHEC ; mesure 1.608 ; seuil 2
- C4 : OK ; mesure 0.5522 ; seuil 0
- C10 : ÉCHEC ; mesure 0.05439 ; seuil 0.05

### R0044 (r-fonds-foule {L: 28, q: 0.7})
- C1 : ÉCHEC ; mesure 0.05972 ; seuil 0.95
- C5 : ÉCHEC ; mesure {2020: 1.657, 2021: 1.626, 2022: -1.065, 2023: 1.787, 2024: 1.164, 2025: -0.2015} ; seuil {sharpe_min: -1, positives_min: 4}
- C6 : ÉCHEC ; mesure 0.7906 ; seuil 0.45
- C7 : ÉCHEC ; mesure None ; seuil {part_voisins_min: 0.75, ratio: 0.6, sharpe_voisin_min: 0.5}
- C8 : ÉCHEC ; mesure 0.9734 ; seuil 0.05
- C9 : OK ; mesure 0 ; seuil {aleatoires: 20, fixes: 3, part_non_pleine_min: 0.4, tolerance: 1e-09}
- C11 : ÉCHEC ; mesure (-0.06596, -0.6035) ; seuil (0.5, 0)
- C12 : OK ; mesure (0.08426, 6.637) ; seuil (0.5, 15)
- C13 : OK ; mesure (0.8923, 0.2324) ; seuil 0
- C14 : OK ; mesure 0.2021 ; seuil 0.04
- C15 : ÉCHEC ; mesure None ; seuil (0, 0.585)
- C16 : ÉCHEC ; mesure None ; seuil 0.6
- C2 : OK ; mesure 0.6219 ; seuil 0.5
- C3 : ÉCHEC ; mesure 1.652 ; seuil 2
- C4 : OK ; mesure 0.5647 ; seuil 0
- C10 : ÉCHEC ; mesure 0.05159 ; seuil 0.05

### R0045 (r-fonds-foule {L: 28, q: 0.9})
- C1 : ÉCHEC ; mesure 0.05758 ; seuil 0.95
- C5 : ÉCHEC ; mesure {2020: 1.657, 2021: 1.397, 2022: -1.065, 2023: 1.826, 2024: 1.198, 2025: -0.2868} ; seuil {sharpe_min: -1, positives_min: 4}
- C6 : ÉCHEC ; mesure 0.7906 ; seuil 0.45
- C7 : ÉCHEC ; mesure None ; seuil {part_voisins_min: 0.75, ratio: 0.6, sharpe_voisin_min: 0.5}
- C8 : ÉCHEC ; mesure 0.9736 ; seuil 0.05
- C9 : OK ; mesure 0 ; seuil {aleatoires: 20, fixes: 3, part_non_pleine_min: 0.4, tolerance: 1e-09}
- C11 : ÉCHEC ; mesure (-0.04743, -0.5569) ; seuil (0.5, 0)
- C12 : OK ; mesure (0.08085, 6.646) ; seuil (0.5, 15)
- C13 : OK ; mesure (0.8368, 0.3145) ; seuil 0
- C14 : OK ; mesure 0.1865 ; seuil 0.04
- C15 : ÉCHEC ; mesure None ; seuil (0, 0.585)
- C16 : ÉCHEC ; mesure None ; seuil 0.6
- C2 : OK ; mesure 0.6133 ; seuil 0.5
- C3 : ÉCHEC ; mesure 1.641 ; seuil 2
- C4 : OK ; mesure 0.5595 ; seuil 0
- C10 : ÉCHEC ; mesure 0.05259 ; seuil 0.05

## Sélection

Aucun candidat : issue B si aucune autre vague n'est décidée.
