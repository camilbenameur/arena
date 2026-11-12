# Vague 2

Document de l'orchestrateur et du propriétaire : il contient des chiffres et ne va à aucun agent. Les agents ne reçoivent que `vague-2-statuts.json`.

Essais de grille : 75 ; lignes supplémentaires (arène, contrôle) : 0 ; dont relues du journal sans relance (reprise) : 0 ; N réel dans le journal : 120 ; N du DSR : 726.
Meilleur DSR : 0.4163. Règle d'arrêt déclenchée : oui.

## Tous les essais

| id | famille | paramètres | code | Sharpe net | portes en échec | passe |
|---|---|---|---|---|---|---|
| R0046 | e-correlation | {L_jours: 20, c: 0.3} | OK | 0.9095 | C1, C5, C6, C7, C8, C11, C15, C16 | non |
| R0047 | e-correlation | {L_jours: 20, c: 0.4} | OK | 0.881 | C1, C5, C6, C7, C8, C11, C15, C16 | non |
| R0048 | e-correlation | {L_jours: 20, c: 0.52} | OK | 0.8066 | C1, C5, C6, C7, C8, C11, C15, C16, C3 | non |
| R0049 | e-correlation | {L_jours: 20, c: 0.67} | OK | 0.5288 | C1, C5, C6, C7, C8, C11, C15, C16, C3, C10 | non |
| R0050 | e-correlation | {L_jours: 20, c: 0.86} | OK | 0.1947 | C1, C5, C6, C7, C8, C11, C13, C14, C15, C16, C2, C3, C10 | non |
| R0051 | e-correlation | {L_jours: 28, c: 0.3} | OK | 0.8996 | C1, C5, C6, C7, C8, C11, C15, C16 | non |
| R0052 | e-correlation | {L_jours: 28, c: 0.4} | OK | 0.8996 | C1, C5, C6, C8, C11, C15, C16 | non |
| R0053 | e-correlation | {L_jours: 28, c: 0.52} | OK | 0.6789 | C1, C5, C6, C8, C11, C15, C16, C3 | non |
| R0054 | e-correlation | {L_jours: 28, c: 0.67} | OK | 0.4667 | C1, C5, C6, C8, C11, C15, C16, C2, C3, C10 | non |
| R0055 | e-correlation | {L_jours: 28, c: 0.86} | OK | 0.1012 | C1, C5, C6, C7, C8, C11, C13, C14, C15, C16, C2, C3, C10 | non |
| R0056 | e-correlation | {L_jours: 40, c: 0.3} | OK | 0.8996 | C1, C5, C6, C7, C8, C11, C15, C16 | non |
| R0057 | e-correlation | {L_jours: 40, c: 0.4} | OK | 0.8996 | C1, C5, C6, C7, C8, C11, C15, C16 | non |
| R0058 | e-correlation | {L_jours: 40, c: 0.52} | OK | 0.8917 | C1, C5, C6, C8, C11, C15, C16 | non |
| R0059 | e-correlation | {L_jours: 40, c: 0.67} | OK | 0.6409 | C1, C5, C6, C8, C11, C15, C16, C3 | non |
| R0060 | e-correlation | {L_jours: 40, c: 0.86} | OK | 0.6153 | C1, C5, C7, C8, C11, C15, C16, C3, C10 | non |
| R0061 | e-correlation | {L_jours: 56, c: 0.3} | OK | 0.8996 | C1, C5, C6, C7, C8, C11, C15, C16 | non |
| R0062 | e-correlation | {L_jours: 56, c: 0.4} | OK | 0.8996 | C1, C5, C6, C7, C8, C11, C15, C16 | non |
| R0063 | e-correlation | {L_jours: 56, c: 0.52} | OK | 0.8023 | C1, C5, C6, C8, C11, C15, C16, C3 | non |
| R0064 | e-correlation | {L_jours: 56, c: 0.67} | OK | 0.7654 | C1, C5, C6, C8, C11, C15, C16, C3 | non |
| R0065 | e-correlation | {L_jours: 56, c: 0.86} | OK | 0.5324 | C1, C5, C6, C7, C8, C11, C15, C16, C3, C10 | non |
| R0066 | e-correlation | {L_jours: 80, c: 0.3} | OK | 0.8996 | C1, C5, C6, C7, C8, C11, C15, C16 | non |
| R0067 | e-correlation | {L_jours: 80, c: 0.4} | OK | 0.8996 | C1, C5, C6, C7, C8, C11, C15, C16 | non |
| R0068 | e-correlation | {L_jours: 80, c: 0.52} | OK | 0.8996 | C1, C5, C6, C7, C8, C11, C15, C16 | non |
| R0069 | e-correlation | {L_jours: 80, c: 0.67} | OK | 0.808 | C1, C5, C6, C7, C8, C11, C15, C16, C3 | non |
| R0070 | e-correlation | {L_jours: 80, c: 0.86} | OK | 0.5015 | C1, C5, C6, C7, C8, C11, C15, C16, C3, C10 | non |
| R0071 | e-largeur | {L_jours: 20, s: 0.2} | OK | 0.5887 | C1, C5, C6, C7, C8, C11, C12, C13, C15, C16, C3, C10 | non |
| R0072 | e-largeur | {L_jours: 20, s: 0.26} | OK | 0.6696 | C1, C5, C6, C7, C8, C11, C12, C13, C15, C16, C3, C10 | non |
| R0073 | e-largeur | {L_jours: 20, s: 0.34} | OK | 0.6631 | C1, C5, C6, C7, C8, C11, C12, C15, C16, C3, C10 | non |
| R0074 | e-largeur | {L_jours: 20, s: 0.44} | OK | 0.8399 | C1, C5, C6, C7, C8, C11, C12, C13, C15, C16, C3 | non |
| R0075 | e-largeur | {L_jours: 20, s: 0.57} | OK | 0.8212 | C1, C5, C6, C7, C8, C11, C12, C15, C16, C3 | non |
| R0076 | e-largeur | {L_jours: 28, s: 0.2} | OK | 0.7299 | C1, C5, C6, C7, C8, C11, C12, C15, C16, C3, C10 | non |
| R0077 | e-largeur | {L_jours: 28, s: 0.26} | OK | 0.6637 | C1, C5, C6, C8, C11, C12, C15, C16, C3, C10 | non |
| R0078 | e-largeur | {L_jours: 28, s: 0.34} | OK | 0.4296 | C1, C5, C6, C8, C11, C12, C13, C15, C16, C2, C3, C10 | non |
| R0079 | e-largeur | {L_jours: 28, s: 0.44} | OK | 0.7174 | C1, C5, C6, C8, C11, C12, C13, C15, C16, C3, C10 | non |
| R0080 | e-largeur | {L_jours: 28, s: 0.57} | OK | 1.136 | C1, C5, C6, C7, C8, C11, C12, C15, C16 | non |
| R0081 | e-largeur | {L_jours: 40, s: 0.2} | OK | 1.103 | C1, C5, C6, C7, C8, C11, C12, C15, C16 | non |
| R0082 | e-largeur | {L_jours: 40, s: 0.26} | OK | 1.137 | C1, C5, C6, C8, C11, C12, C15, C16 | non |
| R0083 | e-largeur | {L_jours: 40, s: 0.34} | OK | 0.9986 | C1, C5, C6, C8, C11, C12, C15, C16 | non |
| R0084 | e-largeur | {L_jours: 40, s: 0.44} | OK | 1.082 | C1, C5, C6, C8, C11, C12, C15, C16 | non |
| R0085 | e-largeur | {L_jours: 40, s: 0.57} | OK | 1.296 | C1, C6, C7, C8, C11, C15, C16 | non |
| R0086 | e-largeur | {L_jours: 56, s: 0.2} | OK | 1.045 | C1, C5, C6, C7, C8, C11, C15, C16 | non |
| R0087 | e-largeur | {L_jours: 56, s: 0.26} | OK | 1.058 | C1, C5, C6, C8, C11, C15, C16 | non |
| R0088 | e-largeur | {L_jours: 56, s: 0.34} | OK | 1.132 | C1, C5, C6, C8, C11, C15, C16 | non |
| R0089 | e-largeur | {L_jours: 56, s: 0.44} | OK | 1.164 | C1, C6, C8, C11, C15, C16 | non |
| R0090 | e-largeur | {L_jours: 56, s: 0.57} | OK | 1.204 | C1, C6, C7, C8, C11, C15, C16 | non |
| R0091 | e-largeur | {L_jours: 80, s: 0.2} | OK | 0.6475 | C1, C5, C6, C7, C8, C11, C15, C16, C3, C10 | non |
| R0092 | e-largeur | {L_jours: 80, s: 0.26} | OK | 0.7669 | C1, C5, C6, C7, C8, C11, C15, C16, C3, C10 | non |
| R0093 | e-largeur | {L_jours: 80, s: 0.34} | OK | 0.9581 | C1, C5, C6, C7, C8, C11, C15, C16, C3 | non |
| R0094 | e-largeur | {L_jours: 80, s: 0.44} | OK | 0.9834 | C1, C5, C6, C7, C8, C11, C15, C16 | non |
| R0095 | e-largeur | {L_jours: 80, s: 0.57} | OK | 1.036 | C1, C5, C6, C7, C8, C11, C15, C16 | non |
| R0096 | f-rattrapage | {h_jours: 5, theta: 0.5} | OK | 0.2087 | C1, C5, C6, C7, C8, C11, C12, C13, C14, C15, C16, C2, C3, C4, C10 | non |
| R0097 | f-rattrapage | {h_jours: 5, theta: 0.75} | OK | -0.0001239 | C1, C5, C6, C7, C8, C11, C12, C13, C14, C15, C16, C2, C3, C4, C10 | non |
| R0098 | f-rattrapage | {h_jours: 5, theta: 1.1} | OK | 0.01042 | C1, C5, C7, C8, C11, C12, C13, C14, C15, C16, C2, C3, C4, C10 | non |
| R0099 | f-rattrapage | {h_jours: 5, theta: 1.6} | OK | -0.07107 | C1, C5, C7, C8, C11, C12, C13, C14, C15, C16, C2, C3, C4, C10 | non |
| R0100 | f-rattrapage | {h_jours: 5, theta: 2.4} | OK | -0.1711 | C1, C5, C7, C8, C11, C12, C13, C14, C15, C16, C2, C3, C4, C10 | non |
| R0101 | f-rattrapage | {h_jours: 7, theta: 0.5} | OK | -0.07921 | C1, C5, C6, C7, C8, C11, C12, C13, C14, C15, C16, C2, C3, C4, C10 | non |
| R0102 | f-rattrapage | {h_jours: 7, theta: 0.75} | OK | -0.07286 | C1, C5, C6, C7, C8, C11, C12, C13, C14, C15, C16, C2, C3, C4, C10 | non |
| R0103 | f-rattrapage | {h_jours: 7, theta: 1.1} | OK | -0.3613 | C1, C5, C6, C7, C8, C11, C12, C13, C14, C15, C16, C2, C3, C4, C10 | non |
| R0104 | f-rattrapage | {h_jours: 7, theta: 1.6} | OK | -0.2363 | C1, C5, C7, C8, C11, C12, C13, C14, C15, C16, C2, C3, C4, C10 | non |
| R0105 | f-rattrapage | {h_jours: 7, theta: 2.4} | OK | -0.1408 | C1, C5, C7, C8, C11, C12, C13, C14, C15, C16, C2, C3, C4, C10 | non |
| R0106 | f-rattrapage | {h_jours: 10, theta: 0.5} | OK | 0.2539 | C1, C5, C6, C7, C8, C11, C12, C13, C14, C15, C16, C2, C3, C4, C10 | non |
| R0107 | f-rattrapage | {h_jours: 10, theta: 0.75} | OK | 0.007052 | C1, C5, C7, C8, C11, C12, C13, C14, C15, C16, C2, C3, C4, C10 | non |
| R0108 | f-rattrapage | {h_jours: 10, theta: 1.1} | OK | -0.223 | C1, C5, C7, C8, C11, C12, C13, C14, C15, C16, C2, C3, C4, C10 | non |
| R0109 | f-rattrapage | {h_jours: 10, theta: 1.6} | OK | -0.2252 | C1, C5, C7, C8, C11, C12, C13, C14, C15, C16, C2, C3, C4, C10 | non |
| R0110 | f-rattrapage | {h_jours: 10, theta: 2.4} | OK | -0.1328 | C1, C5, C7, C8, C11, C12, C13, C14, C15, C16, C2, C3, C4, C10 | non |
| R0111 | f-rattrapage | {h_jours: 14, theta: 0.5} | OK | 0.1612 | C1, C5, C6, C7, C8, C11, C12, C13, C14, C15, C16, C2, C3, C4, C10 | non |
| R0112 | f-rattrapage | {h_jours: 14, theta: 0.75} | OK | 0.08691 | C1, C5, C6, C7, C8, C11, C12, C13, C14, C15, C16, C2, C3, C4, C10 | non |
| R0113 | f-rattrapage | {h_jours: 14, theta: 1.1} | OK | -0.2281 | C1, C5, C7, C8, C11, C12, C13, C14, C15, C16, C2, C3, C4, C10 | non |
| R0114 | f-rattrapage | {h_jours: 14, theta: 1.6} | OK | -0.2618 | C1, C5, C7, C8, C11, C12, C13, C14, C15, C16, C2, C3, C4, C10 | non |
| R0115 | f-rattrapage | {h_jours: 14, theta: 2.4} | OK | -0.3055 | C1, C5, C7, C8, C11, C12, C13, C14, C15, C16, C2, C3, C4, C10 | non |
| R0116 | f-rattrapage | {h_jours: 20, theta: 0.5} | OK | 0.4856 | C1, C5, C7, C8, C11, C13, C15, C16, C2, C3, C10 | non |
| R0117 | f-rattrapage | {h_jours: 20, theta: 0.75} | OK | 0.2472 | C1, C5, C7, C8, C11, C12, C13, C14, C15, C16, C2, C3, C4, C10 | non |
| R0118 | f-rattrapage | {h_jours: 20, theta: 1.1} | OK | 0.209 | C1, C5, C7, C8, C11, C12, C13, C14, C15, C16, C2, C3, C4, C10 | non |
| R0119 | f-rattrapage | {h_jours: 20, theta: 1.6} | OK | 0.1254 | C1, C5, C7, C8, C11, C12, C13, C14, C15, C16, C2, C3, C4, C10 | non |
| R0120 | f-rattrapage | {h_jours: 20, theta: 2.4} | OK | -0.1268 | C1, C5, C7, C8, C11, C12, C13, C14, C15, C16, C2, C3, C4, C10 | non |

## Verdicts détaillés

C16 : mesure = (part, positifs, évaluables, non évaluables, taille de l'univers de contrôle) ; la part est rapportée à la taille fixe de l'univers.

### R0046 (e-correlation {L_jours: 20, c: 0.3})
- C1 : ÉCHEC ; mesure 0.1186 ; seuil 0.95
- C5 : ÉCHEC ; mesure {2020: 1.657, 2021: 2.677, 2022: -1.065, 2023: 1.826, 2024: 1.198, 2025: -0.2868} ; seuil {sharpe_min: -1, positives_min: 4}
- C6 : ÉCHEC ; mesure 0.7906 ; seuil 0.45
- C7 : ÉCHEC ; mesure None ; seuil {part_voisins_min: 0.75, ratio: 0.6, sharpe_voisin_min: 0.5}
- C8 : ÉCHEC ; mesure 0.982 ; seuil 0.05
- C9 : OK ; mesure 0 ; seuil {aleatoires: 20, fixes: 3, part_non_pleine_min: 0.4, tolerance: 1e-09}
- C11 : ÉCHEC ; mesure (0.2339, -0.2717) ; seuil (0.5, 0)
- C12 : OK ; mesure (0.05768, 7.188) ; seuil (0.5, 15)
- C13 : OK ; mesure (1.328, 0.3145) ; seuil 0
- C14 : OK ; mesure 0.4876 ; seuil 0.04
- C15 : ÉCHEC ; mesure None ; seuil (0, 0.585)
- C16 : ÉCHEC ; mesure None ; seuil 0.6
- C2 : OK ; mesure 0.9095 ; seuil 0.5
- C3 : OK ; mesure 2.21 ; seuil 2
- C4 : OK ; mesure 0.8539 ; seuil 0
- C10 : OK ; mesure 0.0156 ; seuil 0.05

### R0047 (e-correlation {L_jours: 20, c: 0.4})
- C1 : ÉCHEC ; mesure 0.1051 ; seuil 0.95
- C5 : ÉCHEC ; mesure {2020: 1.657, 2021: 2.571, 2022: -1.065, 2023: 1.826, 2024: 1.198, 2025: -0.2868} ; seuil {sharpe_min: -1, positives_min: 4}
- C6 : ÉCHEC ; mesure 0.7906 ; seuil 0.45
- C7 : ÉCHEC ; mesure None ; seuil {part_voisins_min: 0.75, ratio: 0.6, sharpe_voisin_min: 0.5}
- C8 : ÉCHEC ; mesure 0.9736 ; seuil 0.05
- C9 : OK ; mesure 0 ; seuil {aleatoires: 20, fixes: 3, part_non_pleine_min: 0.4, tolerance: 1e-09}
- C11 : ÉCHEC ; mesure (0.2025, -0.3044) ; seuil (0.5, 0)
- C12 : OK ; mesure (0.06103, 7.349) ; seuil (0.5, 15)
- C13 : OK ; mesure (1.283, 0.3145) ; seuil 0
- C14 : OK ; mesure 0.4543 ; seuil 0.04
- C15 : ÉCHEC ; mesure None ; seuil (0, 0.585)
- C16 : ÉCHEC ; mesure None ; seuil 0.6
- C2 : OK ; mesure 0.881 ; seuil 0.5
- C3 : OK ; mesure 2.138 ; seuil 2
- C4 : OK ; mesure 0.8239 ; seuil 0
- C10 : OK ; mesure 0.0188 ; seuil 0.05

### R0048 (e-correlation {L_jours: 20, c: 0.52})
- C1 : ÉCHEC ; mesure 0.07477 ; seuil 0.95
- C5 : ÉCHEC ; mesure {2020: 1.657, 2021: 2.503, 2022: -1.065, 2023: 1.922, 2024: 0.829, 2025: -0.2868} ; seuil {sharpe_min: -1, positives_min: 4}
- C6 : ÉCHEC ; mesure 0.7906 ; seuil 0.45
- C7 : ÉCHEC ; mesure None ; seuil {part_voisins_min: 0.75, ratio: 0.6, sharpe_voisin_min: 0.5}
- C8 : ÉCHEC ; mesure 0.9714 ; seuil 0.05
- C9 : OK ; mesure 0 ; seuil {aleatoires: 20, fixes: 3, part_non_pleine_min: 0.4, tolerance: 1e-09}
- C11 : ÉCHEC ; mesure (0.1205, -0.4007) ; seuil (0.5, 0)
- C12 : OK ; mesure (0.07513, 8.191) ; seuil (0.5, 15)
- C13 : OK ; mesure (1.236, 0.1906) ; seuil 0
- C14 : OK ; mesure 0.3722 ; seuil 0.04
- C15 : ÉCHEC ; mesure None ; seuil (0, 0.585)
- C16 : ÉCHEC ; mesure None ; seuil 0.6
- C2 : OK ; mesure 0.8066 ; seuil 0.5
- C3 : ÉCHEC ; mesure 1.921 ; seuil 2
- C4 : OK ; mesure 0.7415 ; seuil 0
- C10 : OK ; mesure 0.02979 ; seuil 0.05

### R0049 (e-correlation {L_jours: 20, c: 0.67})
- C1 : ÉCHEC ; mesure 0.01588 ; seuil 0.95
- C5 : ÉCHEC ; mesure {2020: 1.851, 2021: 1.153, 2022: -1.065, 2023: 1.762, 2024: 1.09, 2025: -0.2868} ; seuil {sharpe_min: -1, positives_min: 4}
- C6 : ÉCHEC ; mesure 0.7906 ; seuil 0.45
- C7 : ÉCHEC ; mesure None ; seuil {part_voisins_min: 0.75, ratio: 0.6, sharpe_voisin_min: 0.5}
- C8 : ÉCHEC ; mesure 0.967 ; seuil 0.05
- C9 : OK ; mesure 0 ; seuil {aleatoires: 20, fixes: 3, part_non_pleine_min: 0.4, tolerance: 1e-09}
- C11 : ÉCHEC ; mesure (-0.1934, -0.7397) ; seuil (0.5, 0)
- C12 : OK ; mesure (0.106, 7.177) ; seuil (0.5, 15)
- C13 : OK ; mesure (0.7722, 0.2026) ; seuil 0
- C14 : OK ; mesure 0.1289 ; seuil 0.04
- C15 : ÉCHEC ; mesure None ; seuil (0, 0.585)
- C16 : ÉCHEC ; mesure None ; seuil 0.6
- C2 : OK ; mesure 0.5288 ; seuil 0.5
- C3 : ÉCHEC ; mesure 1.416 ; seuil 2
- C4 : OK ; mesure 0.4662 ; seuil 0
- C10 : ÉCHEC ; mesure 0.08058 ; seuil 0.05

### R0050 (e-correlation {L_jours: 20, c: 0.86})
- C1 : ÉCHEC ; mesure 0.001285 ; seuil 0.95
- C5 : ÉCHEC ; mesure {2020: 2.015, 2021: 0.1456, 2022: -0.3843, 2023: 2.139, 2024: 0, 2025: -1.071} ; seuil {sharpe_min: -1, positives_min: 4}
- C6 : ÉCHEC ; mesure 0.669 ; seuil 0.45
- C7 : ÉCHEC ; mesure None ; seuil {part_voisins_min: 0.75, ratio: 0.6, sharpe_voisin_min: 0.5}
- C8 : ÉCHEC ; mesure 0.9852 ; seuil 0.05
- C9 : OK ; mesure 0 ; seuil {aleatoires: 20, fixes: 3, part_non_pleine_min: 0.4, tolerance: 1e-09}
- C11 : ÉCHEC ; mesure (-0.8874, -1.649) ; seuil (0.5, 0)
- C12 : OK ; mesure (0.1926, 2.969) ; seuil (0.5, 15)
- C13 : ÉCHEC ; mesure (0.6527, -0.5659) ; seuil 0
- C14 : ÉCHEC ; mesure 0.0003949 ; seuil 0.04
- C15 : ÉCHEC ; mesure None ; seuil (0, 0.585)
- C16 : ÉCHEC ; mesure None ; seuil 0.6
- C2 : ÉCHEC ; mesure 0.1947 ; seuil 0.5
- C3 : ÉCHEC ; mesure 0.5788 ; seuil 2
- C4 : OK ; mesure 0.1484 ; seuil 0
- C10 : ÉCHEC ; mesure 0.2745 ; seuil 0.05

### R0051 (e-correlation {L_jours: 28, c: 0.3})
- C1 : ÉCHEC ; mesure 0.1138 ; seuil 0.95
- C5 : ÉCHEC ; mesure {2020: 1.657, 2021: 2.611, 2022: -1.065, 2023: 1.826, 2024: 1.198, 2025: -0.2868} ; seuil {sharpe_min: -1, positives_min: 4}
- C6 : ÉCHEC ; mesure 0.7906 ; seuil 0.45
- C7 : ÉCHEC ; mesure None ; seuil {part_voisins_min: 0.75, ratio: 0.6, sharpe_voisin_min: 0.5}
- C8 : ÉCHEC ; mesure 0.9954 ; seuil 0.05
- C9 : OK ; mesure 0 ; seuil {aleatoires: 20, fixes: 3, part_non_pleine_min: 0.4, tolerance: 1e-09}
- C11 : ÉCHEC ; mesure (0.2266, -0.2776) ; seuil (0.5, 0)
- C12 : OK ; mesure (0.05633, 6.966) ; seuil (0.5, 15)
- C13 : OK ; mesure (1.31, 0.3145) ; seuil 0
- C14 : OK ; mesure 0.4769 ; seuil 0.04
- C15 : ÉCHEC ; mesure None ; seuil (0, 0.585)
- C16 : ÉCHEC ; mesure None ; seuil 0.6
- C2 : OK ; mesure 0.8996 ; seuil 0.5
- C3 : OK ; mesure 2.189 ; seuil 2
- C4 : OK ; mesure 0.8461 ; seuil 0
- C10 : OK ; mesure 0.016 ; seuil 0.05

### R0052 (e-correlation {L_jours: 28, c: 0.4})
- C1 : ÉCHEC ; mesure 0.1138 ; seuil 0.95
- C5 : ÉCHEC ; mesure {2020: 1.657, 2021: 2.611, 2022: -1.065, 2023: 1.826, 2024: 1.198, 2025: -0.2868} ; seuil {sharpe_min: -1, positives_min: 4}
- C6 : ÉCHEC ; mesure 0.7906 ; seuil 0.45
- C7 : OK ; mesure 1 ; seuil {part_voisins_min: 0.75, ratio: 0.6, sharpe_voisin_min: 0.5}
- C8 : ÉCHEC ; mesure 0.9954 ; seuil 0.05
- C9 : OK ; mesure 0 ; seuil {aleatoires: 20, fixes: 3, part_non_pleine_min: 0.4, tolerance: 1e-09}
- C11 : ÉCHEC ; mesure (0.2266, -0.2776) ; seuil (0.5, 0)
- C12 : OK ; mesure (0.05633, 6.966) ; seuil (0.5, 15)
- C13 : OK ; mesure (1.31, 0.3145) ; seuil 0
- C14 : OK ; mesure 0.4769 ; seuil 0.04
- C15 : ÉCHEC ; mesure None ; seuil (0, 0.585)
- C16 : ÉCHEC ; mesure None ; seuil 0.6
- C2 : OK ; mesure 0.8996 ; seuil 0.5
- C3 : OK ; mesure 2.189 ; seuil 2
- C4 : OK ; mesure 0.8461 ; seuil 0
- C10 : OK ; mesure 0.016 ; seuil 0.05

### R0053 (e-correlation {L_jours: 28, c: 0.52})
- C1 : ÉCHEC ; mesure 0.03923 ; seuil 0.95
- C5 : ÉCHEC ; mesure {2020: 1.657, 2021: 1.753, 2022: -1.065, 2023: 1.826, 2024: 1.127, 2025: -0.2868} ; seuil {sharpe_min: -1, positives_min: 4}
- C6 : ÉCHEC ; mesure 0.7906 ; seuil 0.45
- C7 : OK ; mesure 0.75 ; seuil {part_voisins_min: 0.75, ratio: 0.6, sharpe_voisin_min: 0.5}
- C8 : ÉCHEC ; mesure 0.9414 ; seuil 0.05
- C9 : OK ; mesure 0 ; seuil {aleatoires: 20, fixes: 3, part_non_pleine_min: 0.4, tolerance: 1e-09}
- C11 : ÉCHEC ; mesure (0.007703, -0.5072) ; seuil (0.5, 0)
- C12 : OK ; mesure (0.07702, 7.048) ; seuil (0.5, 15)
- C13 : OK ; mesure (0.9692, 0.2752) ; seuil 0
- C14 : OK ; mesure 0.2455 ; seuil 0.04
- C15 : ÉCHEC ; mesure None ; seuil (0, 0.585)
- C16 : ÉCHEC ; mesure None ; seuil 0.6
- C2 : OK ; mesure 0.6789 ; seuil 0.5
- C3 : ÉCHEC ; mesure 1.761 ; seuil 2
- C4 : OK ; mesure 0.6224 ; seuil 0
- C10 : OK ; mesure 0.04259 ; seuil 0.05

### R0054 (e-correlation {L_jours: 28, c: 0.67})
- C1 : ÉCHEC ; mesure 0.01051 ; seuil 0.95
- C5 : ÉCHEC ; mesure {2020: 1.657, 2021: 1.153, 2022: -1.065, 2023: 1.442, 2024: 1.128, 2025: -0.2959} ; seuil {sharpe_min: -1, positives_min: 4}
- C6 : ÉCHEC ; mesure 0.7906 ; seuil 0.45
- C7 : OK ; mesure 0.75 ; seuil {part_voisins_min: 0.75, ratio: 0.6, sharpe_voisin_min: 0.5}
- C8 : ÉCHEC ; mesure 0.976 ; seuil 0.05
- C9 : OK ; mesure 0 ; seuil {aleatoires: 20, fixes: 3, part_non_pleine_min: 0.4, tolerance: 1e-09}
- C11 : ÉCHEC ; mesure (-0.2531, -0.8017) ; seuil (0.5, 0)
- C12 : OK ; mesure (0.1056, 6.368) ; seuil (0.5, 15)
- C13 : OK ; mesure (0.7372, 0.08067) ; seuil 0
- C14 : OK ; mesure 0.07995 ; seuil 0.04
- C15 : ÉCHEC ; mesure None ; seuil (0, 0.585)
- C16 : ÉCHEC ; mesure None ; seuil 0.6
- C2 : ÉCHEC ; mesure 0.4667 ; seuil 0.5
- C3 : ÉCHEC ; mesure 1.244 ; seuil 2
- C4 : OK ; mesure 0.4117 ; seuil 0
- C10 : ÉCHEC ; mesure 0.108 ; seuil 0.05

### R0055 (e-correlation {L_jours: 28, c: 0.86})
- C1 : ÉCHEC ; mesure 0.0005622 ; seuil 0.95
- C5 : ÉCHEC ; mesure {2020: 2.061, 2021: 0.3209, 2022: -0.632, 2023: 2.659, 2024: 0, 2025: -1.108} ; seuil {sharpe_min: -1, positives_min: 4}
- C6 : ÉCHEC ; mesure 0.6995 ; seuil 0.45
- C7 : ÉCHEC ; mesure None ; seuil {part_voisins_min: 0.75, ratio: 0.6, sharpe_voisin_min: 0.5}
- C8 : ÉCHEC ; mesure 0.991 ; seuil 0.05
- C9 : OK ; mesure 0 ; seuil {aleatoires: 20, fixes: 3, part_non_pleine_min: 0.4, tolerance: 1e-09}
- C11 : ÉCHEC ; mesure (-0.9604, -1.698) ; seuil (0.5, 0)
- C12 : OK ; mesure (0.2875, 2.753) ; seuil (0.5, 15)
- C13 : ÉCHEC ; mesure (0.6113, -0.9079) ; seuil 0
- C14 : ÉCHEC ; mesure -0.04074 ; seuil 0.04
- C15 : ÉCHEC ; mesure None ; seuil (0, 0.585)
- C16 : ÉCHEC ; mesure None ; seuil 0.6
- C2 : ÉCHEC ; mesure 0.1012 ; seuil 0.5
- C3 : ÉCHEC ; mesure 0.2705 ; seuil 2
- C4 : OK ; mesure 0.06032 ; seuil 0
- C10 : ÉCHEC ; mesure 0.3889 ; seuil 0.05

### R0056 (e-correlation {L_jours: 40, c: 0.3})
- C1 : ÉCHEC ; mesure 0.1138 ; seuil 0.95
- C5 : ÉCHEC ; mesure {2020: 1.657, 2021: 2.611, 2022: -1.065, 2023: 1.826, 2024: 1.198, 2025: -0.2868} ; seuil {sharpe_min: -1, positives_min: 4}
- C6 : ÉCHEC ; mesure 0.7906 ; seuil 0.45
- C7 : ÉCHEC ; mesure None ; seuil {part_voisins_min: 0.75, ratio: 0.6, sharpe_voisin_min: 0.5}
- C8 : ÉCHEC ; mesure 0.9954 ; seuil 0.05
- C9 : OK ; mesure 0 ; seuil {aleatoires: 20, fixes: 3, part_non_pleine_min: 0.4, tolerance: 1e-09}
- C11 : ÉCHEC ; mesure (0.2266, -0.2776) ; seuil (0.5, 0)
- C12 : OK ; mesure (0.05633, 6.966) ; seuil (0.5, 15)
- C13 : OK ; mesure (1.31, 0.3145) ; seuil 0
- C14 : OK ; mesure 0.4769 ; seuil 0.04
- C15 : ÉCHEC ; mesure None ; seuil (0, 0.585)
- C16 : ÉCHEC ; mesure None ; seuil 0.6
- C2 : OK ; mesure 0.8996 ; seuil 0.5
- C3 : OK ; mesure 2.189 ; seuil 2
- C4 : OK ; mesure 0.8461 ; seuil 0
- C10 : OK ; mesure 0.016 ; seuil 0.05

### R0057 (e-correlation {L_jours: 40, c: 0.4})
- C1 : ÉCHEC ; mesure 0.1138 ; seuil 0.95
- C5 : ÉCHEC ; mesure {2020: 1.657, 2021: 2.611, 2022: -1.065, 2023: 1.826, 2024: 1.198, 2025: -0.2868} ; seuil {sharpe_min: -1, positives_min: 4}
- C6 : ÉCHEC ; mesure 0.7906 ; seuil 0.45
- C7 : ÉCHEC ; mesure None ; seuil {part_voisins_min: 0.75, ratio: 0.6, sharpe_voisin_min: 0.5}
- C8 : ÉCHEC ; mesure 0.9954 ; seuil 0.05
- C9 : OK ; mesure 0 ; seuil {aleatoires: 20, fixes: 3, part_non_pleine_min: 0.4, tolerance: 1e-09}
- C11 : ÉCHEC ; mesure (0.2266, -0.2776) ; seuil (0.5, 0)
- C12 : OK ; mesure (0.05633, 6.966) ; seuil (0.5, 15)
- C13 : OK ; mesure (1.31, 0.3145) ; seuil 0
- C14 : OK ; mesure 0.4769 ; seuil 0.04
- C15 : ÉCHEC ; mesure None ; seuil (0, 0.585)
- C16 : ÉCHEC ; mesure None ; seuil 0.6
- C2 : OK ; mesure 0.8996 ; seuil 0.5
- C3 : OK ; mesure 2.189 ; seuil 2
- C4 : OK ; mesure 0.8461 ; seuil 0
- C10 : OK ; mesure 0.016 ; seuil 0.05

### R0058 (e-correlation {L_jours: 40, c: 0.52})
- C1 : ÉCHEC ; mesure 0.11 ; seuil 0.95
- C5 : ÉCHEC ; mesure {2020: 1.657, 2021: 2.616, 2022: -1.065, 2023: 1.826, 2024: 1.198, 2025: -0.2868} ; seuil {sharpe_min: -1, positives_min: 4}
- C6 : ÉCHEC ; mesure 0.7906 ; seuil 0.45
- C7 : OK ; mesure 1 ; seuil {part_voisins_min: 0.75, ratio: 0.6, sharpe_voisin_min: 0.5}
- C8 : ÉCHEC ; mesure 0.9864 ; seuil 0.05
- C9 : OK ; mesure 0 ; seuil {aleatoires: 20, fixes: 3, part_non_pleine_min: 0.4, tolerance: 1e-09}
- C11 : ÉCHEC ; mesure (0.211, -0.2989) ; seuil (0.5, 0)
- C12 : OK ; mesure (0.05845, 7.112) ; seuil (0.5, 15)
- C13 : OK ; mesure (1.3, 0.3145) ; seuil 0
- C14 : OK ; mesure 0.4666 ; seuil 0.04
- C15 : ÉCHEC ; mesure None ; seuil (0, 0.585)
- C16 : ÉCHEC ; mesure None ; seuil 0.6
- C2 : OK ; mesure 0.8917 ; seuil 0.5
- C3 : OK ; mesure 2.152 ; seuil 2
- C4 : OK ; mesure 0.8365 ; seuil 0
- C10 : OK ; mesure 0.018 ; seuil 0.05

### R0059 (e-correlation {L_jours: 40, c: 0.67})
- C1 : ÉCHEC ; mesure 0.03143 ; seuil 0.95
- C5 : ÉCHEC ; mesure {2020: 1.657, 2021: 1.213, 2022: -1.065, 2023: 1.826, 2024: 2.146, 2025: -0.372} ; seuil {sharpe_min: -1, positives_min: 4}
- C6 : ÉCHEC ; mesure 0.7906 ; seuil 0.45
- C7 : OK ; mesure 0.75 ; seuil {part_voisins_min: 0.75, ratio: 0.6, sharpe_voisin_min: 0.5}
- C8 : ÉCHEC ; mesure 0.9416 ; seuil 0.05
- C9 : OK ; mesure 0 ; seuil {aleatoires: 20, fixes: 3, part_non_pleine_min: 0.4, tolerance: 1e-09}
- C11 : ÉCHEC ; mesure (-0.04022, -0.5721) ; seuil (0.5, 0)
- C12 : OK ; mesure (0.08259, 6.739) ; seuil (0.5, 15)
- C13 : OK ; mesure (0.7569, 0.4986) ; seuil 0
- C14 : OK ; mesure 0.2179 ; seuil 0.04
- C15 : ÉCHEC ; mesure None ; seuil (0, 0.585)
- C16 : ÉCHEC ; mesure None ; seuil 0.6
- C2 : OK ; mesure 0.6409 ; seuil 0.5
- C3 : ÉCHEC ; mesure 1.668 ; seuil 2
- C4 : OK ; mesure 0.5831 ; seuil 0
- C10 : OK ; mesure 0.04759 ; seuil 0.05

### R0060 (e-correlation {L_jours: 40, c: 0.86})
- C1 : ÉCHEC ; mesure 0.0257 ; seuil 0.95
- C5 : ÉCHEC ; mesure {2020: 2.061, 2021: 1.013, 2022: -0.5414, 2023: 1.067, 2024: 0, 2025: 0} ; seuil {sharpe_min: -1, positives_min: 4}
- C6 : OK ; mesure 0.4177 ; seuil 0.45
- C7 : ÉCHEC ; mesure None ; seuil {part_voisins_min: 0.75, ratio: 0.6, sharpe_voisin_min: 0.5}
- C8 : ÉCHEC ; mesure 0.9564 ; seuil 0.05
- C9 : OK ; mesure 0 ; seuil {aleatoires: 20, fixes: 3, part_non_pleine_min: 0.4, tolerance: 1e-09}
- C11 : ÉCHEC ; mesure (-0.4236, -1.201) ; seuil (0.5, 0)
- C12 : OK ; mesure (0.06052, 2.539) ; seuil (0.5, 15)
- C13 : OK ; mesure (0.8923, 0.05709) ; seuil 0
- C14 : OK ; mesure 0.1764 ; seuil 0.04
- C15 : ÉCHEC ; mesure None ; seuil (0, 0.585)
- C16 : ÉCHEC ; mesure None ; seuil 0.6
- C2 : OK ; mesure 0.6153 ; seuil 0.5
- C3 : ÉCHEC ; mesure 1.639 ; seuil 2
- C4 : OK ; mesure 0.5758 ; seuil 0
- C10 : ÉCHEC ; mesure 0.05599 ; seuil 0.05

### R0061 (e-correlation {L_jours: 56, c: 0.3})
- C1 : ÉCHEC ; mesure 0.1138 ; seuil 0.95
- C5 : ÉCHEC ; mesure {2020: 1.657, 2021: 2.611, 2022: -1.065, 2023: 1.826, 2024: 1.198, 2025: -0.2868} ; seuil {sharpe_min: -1, positives_min: 4}
- C6 : ÉCHEC ; mesure 0.7906 ; seuil 0.45
- C7 : ÉCHEC ; mesure None ; seuil {part_voisins_min: 0.75, ratio: 0.6, sharpe_voisin_min: 0.5}
- C8 : ÉCHEC ; mesure 0.9954 ; seuil 0.05
- C9 : OK ; mesure 0 ; seuil {aleatoires: 20, fixes: 3, part_non_pleine_min: 0.4, tolerance: 1e-09}
- C11 : ÉCHEC ; mesure (0.2266, -0.2776) ; seuil (0.5, 0)
- C12 : OK ; mesure (0.05633, 6.966) ; seuil (0.5, 15)
- C13 : OK ; mesure (1.31, 0.3145) ; seuil 0
- C14 : OK ; mesure 0.4769 ; seuil 0.04
- C15 : ÉCHEC ; mesure None ; seuil (0, 0.585)
- C16 : ÉCHEC ; mesure None ; seuil 0.6
- C2 : OK ; mesure 0.8996 ; seuil 0.5
- C3 : OK ; mesure 2.189 ; seuil 2
- C4 : OK ; mesure 0.8461 ; seuil 0
- C10 : OK ; mesure 0.016 ; seuil 0.05

### R0062 (e-correlation {L_jours: 56, c: 0.4})
- C1 : ÉCHEC ; mesure 0.1138 ; seuil 0.95
- C5 : ÉCHEC ; mesure {2020: 1.657, 2021: 2.611, 2022: -1.065, 2023: 1.826, 2024: 1.198, 2025: -0.2868} ; seuil {sharpe_min: -1, positives_min: 4}
- C6 : ÉCHEC ; mesure 0.7906 ; seuil 0.45
- C7 : ÉCHEC ; mesure None ; seuil {part_voisins_min: 0.75, ratio: 0.6, sharpe_voisin_min: 0.5}
- C8 : ÉCHEC ; mesure 0.9954 ; seuil 0.05
- C9 : OK ; mesure 0 ; seuil {aleatoires: 20, fixes: 3, part_non_pleine_min: 0.4, tolerance: 1e-09}
- C11 : ÉCHEC ; mesure (0.2266, -0.2776) ; seuil (0.5, 0)
- C12 : OK ; mesure (0.05633, 6.966) ; seuil (0.5, 15)
- C13 : OK ; mesure (1.31, 0.3145) ; seuil 0
- C14 : OK ; mesure 0.4769 ; seuil 0.04
- C15 : ÉCHEC ; mesure None ; seuil (0, 0.585)
- C16 : ÉCHEC ; mesure None ; seuil 0.6
- C2 : OK ; mesure 0.8996 ; seuil 0.5
- C3 : OK ; mesure 2.189 ; seuil 2
- C4 : OK ; mesure 0.8461 ; seuil 0
- C10 : OK ; mesure 0.016 ; seuil 0.05

### R0063 (e-correlation {L_jours: 56, c: 0.52})
- C1 : ÉCHEC ; mesure 0.07231 ; seuil 0.95
- C5 : ÉCHEC ; mesure {2020: 1.657, 2021: 2.371, 2022: -1.065, 2023: 1.826, 2024: 1.198, 2025: -0.2868} ; seuil {sharpe_min: -1, positives_min: 4}
- C6 : ÉCHEC ; mesure 0.7906 ; seuil 0.45
- C7 : OK ; mesure 1 ; seuil {part_voisins_min: 0.75, ratio: 0.6, sharpe_voisin_min: 0.5}
- C8 : ÉCHEC ; mesure 0.9142 ; seuil 0.05
- C9 : OK ; mesure 0 ; seuil {aleatoires: 20, fixes: 3, part_non_pleine_min: 0.4, tolerance: 1e-09}
- C11 : ÉCHEC ; mesure (0.1065, -0.4217) ; seuil (0.5, 0)
- C12 : OK ; mesure (0.06333, 6.698) ; seuil (0.5, 15)
- C13 : OK ; mesure (1.161, 0.3145) ; seuil 0
- C14 : OK ; mesure 0.3701 ; seuil 0.04
- C15 : ÉCHEC ; mesure None ; seuil (0, 0.585)
- C16 : ÉCHEC ; mesure None ; seuil 0.6
- C2 : OK ; mesure 0.8023 ; seuil 0.5
- C3 : ÉCHEC ; mesure 1.954 ; seuil 2
- C4 : OK ; mesure 0.7483 ; seuil 0
- C10 : OK ; mesure 0.03019 ; seuil 0.05

### R0064 (e-correlation {L_jours: 56, c: 0.67})
- C1 : ÉCHEC ; mesure 0.06078 ; seuil 0.95
- C5 : ÉCHEC ; mesure {2020: 1.657, 2021: 2.306, 2022: -1.065, 2023: 1.826, 2024: 1.198, 2025: -0.2868} ; seuil {sharpe_min: -1, positives_min: 4}
- C6 : ÉCHEC ; mesure 0.7906 ; seuil 0.45
- C7 : OK ; mesure 1 ; seuil {part_voisins_min: 0.75, ratio: 0.6, sharpe_voisin_min: 0.5}
- C8 : ÉCHEC ; mesure 0.9508 ; seuil 0.05
- C9 : OK ; mesure 0 ; seuil {aleatoires: 20, fixes: 3, part_non_pleine_min: 0.4, tolerance: 1e-09}
- C11 : ÉCHEC ; mesure (0.102, -0.4246) ; seuil (0.5, 0)
- C12 : OK ; mesure (0.06657, 6.594) ; seuil (0.5, 15)
- C13 : OK ; mesure (1.105, 0.3145) ; seuil 0
- C14 : OK ; mesure 0.3315 ; seuil 0.04
- C15 : ÉCHEC ; mesure None ; seuil (0, 0.585)
- C16 : ÉCHEC ; mesure None ; seuil 0.6
- C2 : OK ; mesure 0.7654 ; seuil 0.5
- C3 : ÉCHEC ; mesure 1.867 ; seuil 2
- C4 : OK ; mesure 0.7109 ; seuil 0
- C10 : OK ; mesure 0.03479 ; seuil 0.05

### R0065 (e-correlation {L_jours: 56, c: 0.86})
- C1 : ÉCHEC ; mesure 0.01566 ; seuil 0.95
- C5 : ÉCHEC ; mesure {2020: 2.369, 2021: 1.204, 2022: -1.065, 2023: 1.356, 2024: 0, 2025: 0} ; seuil {sharpe_min: -1, positives_min: 4}
- C6 : ÉCHEC ; mesure 0.7906 ; seuil 0.45
- C7 : ÉCHEC ; mesure None ; seuil {part_voisins_min: 0.75, ratio: 0.6, sharpe_voisin_min: 0.5}
- C8 : ÉCHEC ; mesure 0.9642 ; seuil 0.05
- C9 : OK ; mesure 0 ; seuil {aleatoires: 20, fixes: 3, part_non_pleine_min: 0.4, tolerance: 1e-09}
- C11 : ÉCHEC ; mesure (-0.3524, -1.003) ; seuil (0.5, 0)
- C12 : OK ; mesure (0.07152, 3.195) ; seuil (0.5, 15)
- C13 : OK ; mesure (0.6849, 0.3365) ; seuil 0
- C14 : OK ; mesure 0.1491 ; seuil 0.04
- C15 : ÉCHEC ; mesure None ; seuil (0, 0.585)
- C16 : ÉCHEC ; mesure None ; seuil 0.6
- C2 : OK ; mesure 0.5324 ; seuil 0.5
- C3 : ÉCHEC ; mesure 1.387 ; seuil 2
- C4 : OK ; mesure 0.4917 ; seuil 0
- C10 : ÉCHEC ; mesure 0.08618 ; seuil 0.05

### R0066 (e-correlation {L_jours: 80, c: 0.3})
- C1 : ÉCHEC ; mesure 0.1138 ; seuil 0.95
- C5 : ÉCHEC ; mesure {2020: 1.657, 2021: 2.611, 2022: -1.065, 2023: 1.826, 2024: 1.198, 2025: -0.2868} ; seuil {sharpe_min: -1, positives_min: 4}
- C6 : ÉCHEC ; mesure 0.7906 ; seuil 0.45
- C7 : ÉCHEC ; mesure None ; seuil {part_voisins_min: 0.75, ratio: 0.6, sharpe_voisin_min: 0.5}
- C8 : ÉCHEC ; mesure 0.9954 ; seuil 0.05
- C9 : OK ; mesure 0 ; seuil {aleatoires: 20, fixes: 3, part_non_pleine_min: 0.4, tolerance: 1e-09}
- C11 : ÉCHEC ; mesure (0.2266, -0.2776) ; seuil (0.5, 0)
- C12 : OK ; mesure (0.05633, 6.966) ; seuil (0.5, 15)
- C13 : OK ; mesure (1.31, 0.3145) ; seuil 0
- C14 : OK ; mesure 0.4769 ; seuil 0.04
- C15 : ÉCHEC ; mesure None ; seuil (0, 0.585)
- C16 : ÉCHEC ; mesure None ; seuil 0.6
- C2 : OK ; mesure 0.8996 ; seuil 0.5
- C3 : OK ; mesure 2.189 ; seuil 2
- C4 : OK ; mesure 0.8461 ; seuil 0
- C10 : OK ; mesure 0.016 ; seuil 0.05

### R0067 (e-correlation {L_jours: 80, c: 0.4})
- C1 : ÉCHEC ; mesure 0.1138 ; seuil 0.95
- C5 : ÉCHEC ; mesure {2020: 1.657, 2021: 2.611, 2022: -1.065, 2023: 1.826, 2024: 1.198, 2025: -0.2868} ; seuil {sharpe_min: -1, positives_min: 4}
- C6 : ÉCHEC ; mesure 0.7906 ; seuil 0.45
- C7 : ÉCHEC ; mesure None ; seuil {part_voisins_min: 0.75, ratio: 0.6, sharpe_voisin_min: 0.5}
- C8 : ÉCHEC ; mesure 0.9954 ; seuil 0.05
- C9 : OK ; mesure 0 ; seuil {aleatoires: 20, fixes: 3, part_non_pleine_min: 0.4, tolerance: 1e-09}
- C11 : ÉCHEC ; mesure (0.2266, -0.2776) ; seuil (0.5, 0)
- C12 : OK ; mesure (0.05633, 6.966) ; seuil (0.5, 15)
- C13 : OK ; mesure (1.31, 0.3145) ; seuil 0
- C14 : OK ; mesure 0.4769 ; seuil 0.04
- C15 : ÉCHEC ; mesure None ; seuil (0, 0.585)
- C16 : ÉCHEC ; mesure None ; seuil 0.6
- C2 : OK ; mesure 0.8996 ; seuil 0.5
- C3 : OK ; mesure 2.189 ; seuil 2
- C4 : OK ; mesure 0.8461 ; seuil 0
- C10 : OK ; mesure 0.016 ; seuil 0.05

### R0068 (e-correlation {L_jours: 80, c: 0.52})
- C1 : ÉCHEC ; mesure 0.1138 ; seuil 0.95
- C5 : ÉCHEC ; mesure {2020: 1.657, 2021: 2.611, 2022: -1.065, 2023: 1.826, 2024: 1.198, 2025: -0.2868} ; seuil {sharpe_min: -1, positives_min: 4}
- C6 : ÉCHEC ; mesure 0.7906 ; seuil 0.45
- C7 : ÉCHEC ; mesure None ; seuil {part_voisins_min: 0.75, ratio: 0.6, sharpe_voisin_min: 0.5}
- C8 : ÉCHEC ; mesure 0.9954 ; seuil 0.05
- C9 : OK ; mesure 0 ; seuil {aleatoires: 20, fixes: 3, part_non_pleine_min: 0.4, tolerance: 1e-09}
- C11 : ÉCHEC ; mesure (0.2266, -0.2776) ; seuil (0.5, 0)
- C12 : OK ; mesure (0.05633, 6.966) ; seuil (0.5, 15)
- C13 : OK ; mesure (1.31, 0.3145) ; seuil 0
- C14 : OK ; mesure 0.4769 ; seuil 0.04
- C15 : ÉCHEC ; mesure None ; seuil (0, 0.585)
- C16 : ÉCHEC ; mesure None ; seuil 0.6
- C2 : OK ; mesure 0.8996 ; seuil 0.5
- C3 : OK ; mesure 2.189 ; seuil 2
- C4 : OK ; mesure 0.8461 ; seuil 0
- C10 : OK ; mesure 0.016 ; seuil 0.05

### R0069 (e-correlation {L_jours: 80, c: 0.67})
- C1 : ÉCHEC ; mesure 0.07499 ; seuil 0.95
- C5 : ÉCHEC ; mesure {2020: 1.657, 2021: 2.568, 2022: -1.065, 2023: 1.826, 2024: 1.198, 2025: -0.2868} ; seuil {sharpe_min: -1, positives_min: 4}
- C6 : ÉCHEC ; mesure 0.7906 ; seuil 0.45
- C7 : ÉCHEC ; mesure None ; seuil {part_voisins_min: 0.75, ratio: 0.6, sharpe_voisin_min: 0.5}
- C8 : ÉCHEC ; mesure 0.9274 ; seuil 0.05
- C9 : OK ; mesure 0 ; seuil {aleatoires: 20, fixes: 3, part_non_pleine_min: 0.4, tolerance: 1e-09}
- C11 : ÉCHEC ; mesure (0.1471, -0.3768) ; seuil (0.5, 0)
- C12 : OK ; mesure (0.06372, 6.622) ; seuil (0.5, 15)
- C13 : OK ; mesure (1.18, 0.3145) ; seuil 0
- C14 : OK ; mesure 0.373 ; seuil 0.04
- C15 : ÉCHEC ; mesure None ; seuil (0, 0.585)
- C16 : ÉCHEC ; mesure None ; seuil 0.6
- C2 : OK ; mesure 0.808 ; seuil 0.5
- C3 : ÉCHEC ; mesure 1.933 ; seuil 2
- C4 : OK ; mesure 0.7532 ; seuil 0
- C10 : OK ; mesure 0.03219 ; seuil 0.05

### R0070 (e-correlation {L_jours: 80, c: 0.86})
- C1 : ÉCHEC ; mesure 0.01441 ; seuil 0.95
- C5 : ÉCHEC ; mesure {2020: 1.591, 2021: 1.217, 2022: -1.065, 2023: 1.48, 2024: 0, 2025: 0} ; seuil {sharpe_min: -1, positives_min: 4}
- C6 : ÉCHEC ; mesure 0.7906 ; seuil 0.45
- C7 : ÉCHEC ; mesure None ; seuil {part_voisins_min: 0.75, ratio: 0.6, sharpe_voisin_min: 0.5}
- C8 : ÉCHEC ; mesure 0.9666 ; seuil 0.05
- C9 : OK ; mesure 0 ; seuil {aleatoires: 20, fixes: 3, part_non_pleine_min: 0.4, tolerance: 1e-09}
- C11 : ÉCHEC ; mesure (-0.311, -0.8955) ; seuil (0.5, 0)
- C12 : OK ; mesure (0.07271, 3.366) ; seuil (0.5, 15)
- C13 : OK ; mesure (0.6174, 0.4293) ; seuil 0
- C14 : OK ; mesure 0.1271 ; seuil 0.04
- C15 : ÉCHEC ; mesure None ; seuil (0, 0.585)
- C16 : ÉCHEC ; mesure None ; seuil 0.6
- C2 : OK ; mesure 0.5015 ; seuil 0.5
- C3 : ÉCHEC ; mesure 1.319 ; seuil 2
- C4 : OK ; mesure 0.4622 ; seuil 0
- C10 : ÉCHEC ; mesure 0.09958 ; seuil 0.05

### R0071 (e-largeur {L_jours: 20, s: 0.2})
- C1 : ÉCHEC ; mesure 0.02238 ; seuil 0.95
- C5 : ÉCHEC ; mesure {2020: 2.271, 2021: 2.593, 2022: -2.359, 2023: 1.603, 2024: 0.6819, 2025: -1.914} ; seuil {sharpe_min: -1, positives_min: 4}
- C6 : ÉCHEC ; mesure 0.9301 ; seuil 0.45
- C7 : ÉCHEC ; mesure None ; seuil {part_voisins_min: 0.75, ratio: 0.6, sharpe_voisin_min: 0.5}
- C8 : ÉCHEC ; mesure 0.9978 ; seuil 0.05
- C9 : OK ; mesure 0 ; seuil {aleatoires: 20, fixes: 3, part_non_pleine_min: 0.4, tolerance: 1e-09}
- C11 : ÉCHEC ; mesure (-0.1409, -0.6978) ; seuil (0.5, 0)
- C12 : ÉCHEC ; mesure (0.2718, 22.68) ; seuil (0.5, 15)
- C13 : ÉCHEC ; mesure (1.163, -0.2564) ; seuil 0
- C14 : OK ; mesure 0.186 ; seuil 0.04
- C15 : ÉCHEC ; mesure None ; seuil (0, 0.585)
- C16 : ÉCHEC ; mesure None ; seuil 0.6
- C2 : OK ; mesure 0.5887 ; seuil 0.5
- C3 : ÉCHEC ; mesure 1.182 ; seuil 2
- C4 : OK ; mesure 0.3683 ; seuil 0
- C10 : ÉCHEC ; mesure 0.1166 ; seuil 0.05

### R0072 (e-largeur {L_jours: 20, s: 0.26})
- C1 : ÉCHEC ; mesure 0.03601 ; seuil 0.95
- C5 : ÉCHEC ; mesure {2020: 2.223, 2021: 2.526, 2022: -2.123, 2023: 1.441, 2024: 0.3882, 2025: -1.236} ; seuil {sharpe_min: -1, positives_min: 4}
- C6 : ÉCHEC ; mesure 0.889 ; seuil 0.45
- C7 : ÉCHEC ; mesure None ; seuil {part_voisins_min: 0.75, ratio: 0.6, sharpe_voisin_min: 0.5}
- C8 : ÉCHEC ; mesure 0.9942 ; seuil 0.05
- C9 : OK ; mesure 0 ; seuil {aleatoires: 20, fixes: 3, part_non_pleine_min: 0.4, tolerance: 1e-09}
- C11 : ÉCHEC ; mesure (-0.06902, -0.6341) ; seuil (0.5, 0)
- C12 : ÉCHEC ; mesure (0.264, 23.89) ; seuil (0.5, 15)
- C13 : ÉCHEC ; mesure (1.233, -0.1786) ; seuil 0
- C14 : OK ; mesure 0.2452 ; seuil 0.04
- C15 : ÉCHEC ; mesure None ; seuil (0, 0.585)
- C16 : ÉCHEC ; mesure None ; seuil 0.6
- C2 : OK ; mesure 0.6696 ; seuil 0.5
- C3 : ÉCHEC ; mesure 1.362 ; seuil 2
- C4 : OK ; mesure 0.4284 ; seuil 0
- C10 : ÉCHEC ; mesure 0.08978 ; seuil 0.05

### R0073 (e-largeur {L_jours: 20, s: 0.34})
- C1 : ÉCHEC ; mesure 0.03463 ; seuil 0.95
- C5 : ÉCHEC ; mesure {2020: 1.877, 2021: 2.356, 2022: -1.942, 2023: 1.82, 2024: 0.4581, 2025: -0.9437} ; seuil {sharpe_min: -1, positives_min: 4}
- C6 : ÉCHEC ; mesure 0.823 ; seuil 0.45
- C7 : ÉCHEC ; mesure None ; seuil {part_voisins_min: 0.75, ratio: 0.6, sharpe_voisin_min: 0.5}
- C8 : ÉCHEC ; mesure 0.9892 ; seuil 0.05
- C9 : OK ; mesure 0 ; seuil {aleatoires: 20, fixes: 3, part_non_pleine_min: 0.4, tolerance: 1e-09}
- C11 : ÉCHEC ; mesure (-0.126, -0.7077) ; seuil (0.5, 0)
- C12 : ÉCHEC ; mesure (0.2674, 23.69) ; seuil (0.5, 15)
- C13 : OK ; mesure (1.109, 0.004589) ; seuil 0
- C14 : OK ; mesure 0.2398 ; seuil 0.04
- C15 : ÉCHEC ; mesure None ; seuil (0, 0.585)
- C16 : ÉCHEC ; mesure None ; seuil 0.6
- C2 : OK ; mesure 0.6631 ; seuil 0.5
- C3 : ÉCHEC ; mesure 1.385 ; seuil 2
- C4 : OK ; mesure 0.42 ; seuil 0
- C10 : ÉCHEC ; mesure 0.08778 ; seuil 0.05

### R0074 (e-largeur {L_jours: 20, s: 0.44})
- C1 : ÉCHEC ; mesure 0.08558 ; seuil 0.95
- C5 : ÉCHEC ; mesure {2020: 1.974, 2021: 2.654, 2022: -1.442, 2023: 1.762, 2024: 0.7409, 2025: -1.329} ; seuil {sharpe_min: -1, positives_min: 4}
- C6 : ÉCHEC ; mesure 0.7253 ; seuil 0.45
- C7 : ÉCHEC ; mesure None ; seuil {part_voisins_min: 0.75, ratio: 0.6, sharpe_voisin_min: 0.5}
- C8 : ÉCHEC ; mesure 0.9534 ; seuil 0.05
- C9 : OK ; mesure 0 ; seuil {aleatoires: 20, fixes: 3, part_non_pleine_min: 0.4, tolerance: 1e-09}
- C11 : ÉCHEC ; mesure (0.06298, -0.5198) ; seuil (0.5, 0)
- C12 : ÉCHEC ; mesure (0.2201, 22.53) ; seuil (0.5, 15)
- C13 : ÉCHEC ; mesure (1.454, -0.03632) ; seuil 0
- C14 : OK ; mesure 0.37 ; seuil 0.04
- C15 : ÉCHEC ; mesure None ; seuil (0, 0.585)
- C16 : ÉCHEC ; mesure None ; seuil 0.6
- C2 : OK ; mesure 0.8399 ; seuil 0.5
- C3 : ÉCHEC ; mesure 1.746 ; seuil 2
- C4 : OK ; mesure 0.6011 ; seuil 0
- C10 : OK ; mesure 0.04439 ; seuil 0.05

### R0075 (e-largeur {L_jours: 20, s: 0.57})
- C1 : ÉCHEC ; mesure 0.07806 ; seuil 0.95
- C5 : ÉCHEC ; mesure {2020: 1.703, 2021: 2.482, 2022: -0.816, 2023: 1.609, 2024: 1.265, 2025: -1.471} ; seuil {sharpe_min: -1, positives_min: 4}
- C6 : ÉCHEC ; mesure 0.7153 ; seuil 0.45
- C7 : ÉCHEC ; mesure None ; seuil {part_voisins_min: 0.75, ratio: 0.6, sharpe_voisin_min: 0.5}
- C8 : ÉCHEC ; mesure 0.964 ; seuil 0.05
- C9 : OK ; mesure 0 ; seuil {aleatoires: 20, fixes: 3, part_non_pleine_min: 0.4, tolerance: 1e-09}
- C11 : ÉCHEC ; mesure (0.04164, -0.5872) ; seuil (0.5, 0)
- C12 : ÉCHEC ; mesure (0.2489, 22.83) ; seuil (0.5, 15)
- C13 : OK ; mesure (1.413, 0.01318) ; seuil 0
- C14 : OK ; mesure 0.3311 ; seuil 0.04
- C15 : ÉCHEC ; mesure None ; seuil (0, 0.585)
- C16 : ÉCHEC ; mesure None ; seuil 0.6
- C2 : OK ; mesure 0.8212 ; seuil 0.5
- C3 : ÉCHEC ; mesure 1.737 ; seuil 2
- C4 : OK ; mesure 0.547 ; seuil 0
- C10 : OK ; mesure 0.04659 ; seuil 0.05

### R0076 (e-largeur {L_jours: 28, s: 0.2})
- C1 : ÉCHEC ; mesure 0.04983 ; seuil 0.95
- C5 : ÉCHEC ; mesure {2020: 1.957, 2021: 2.636, 2022: -2.393, 2023: 1.509, 2024: 0.9219, 2025: -1.365} ; seuil {sharpe_min: -1, positives_min: 4}
- C6 : ÉCHEC ; mesure 0.8551 ; seuil 0.45
- C7 : ÉCHEC ; mesure None ; seuil {part_voisins_min: 0.75, ratio: 0.6, sharpe_voisin_min: 0.5}
- C8 : ÉCHEC ; mesure 0.9908 ; seuil 0.05
- C9 : OK ; mesure 0 ; seuil {aleatoires: 20, fixes: 3, part_non_pleine_min: 0.4, tolerance: 1e-09}
- C11 : ÉCHEC ; mesure (0.006074, -0.5593) ; seuil (0.5, 0)
- C12 : ÉCHEC ; mesure (0.2124, 20.23) ; seuil (0.5, 15)
- C13 : OK ; mesure (1.23, 0.005457) ; seuil 0
- C14 : OK ; mesure 0.294 ; seuil 0.04
- C15 : ÉCHEC ; mesure None ; seuil (0, 0.585)
- C16 : ÉCHEC ; mesure None ; seuil 0.6
- C2 : OK ; mesure 0.7299 ; seuil 0.5
- C3 : ÉCHEC ; mesure 1.495 ; seuil 2
- C4 : OK ; mesure 0.532 ; seuil 0
- C10 : ÉCHEC ; mesure 0.07199 ; seuil 0.05

### R0077 (e-largeur {L_jours: 28, s: 0.26})
- C1 : ÉCHEC ; mesure 0.03492 ; seuil 0.95
- C5 : ÉCHEC ; mesure {2020: 2.128, 2021: 2.292, 2022: -2.553, 2023: 1.546, 2024: 1.107, 2025: -1.181} ; seuil {sharpe_min: -1, positives_min: 4}
- C6 : ÉCHEC ; mesure 0.8815 ; seuil 0.45
- C7 : OK ; mesure 0.75 ; seuil {part_voisins_min: 0.75, ratio: 0.6, sharpe_voisin_min: 0.5}
- C8 : ÉCHEC ; mesure 0.995 ; seuil 0.05
- C9 : OK ; mesure 0 ; seuil {aleatoires: 20, fixes: 3, part_non_pleine_min: 0.4, tolerance: 1e-09}
- C11 : ÉCHEC ; mesure (-0.06825, -0.6366) ; seuil (0.5, 0)
- C12 : ÉCHEC ; mesure (0.2381, 20.82) ; seuil (0.5, 15)
- C13 : OK ; mesure (1.034, 0.1278) ; seuil 0
- C14 : OK ; mesure 0.241 ; seuil 0.04
- C15 : ÉCHEC ; mesure None ; seuil (0, 0.585)
- C16 : ÉCHEC ; mesure None ; seuil 0.6
- C2 : OK ; mesure 0.6637 ; seuil 0.5
- C3 : ÉCHEC ; mesure 1.353 ; seuil 2
- C4 : OK ; mesure 0.4551 ; seuil 0
- C10 : ÉCHEC ; mesure 0.09618 ; seuil 0.05

### R0078 (e-largeur {L_jours: 28, s: 0.34})
- C1 : ÉCHEC ; mesure 0.007891 ; seuil 0.95
- C5 : ÉCHEC ; mesure {2020: 1.581, 2021: 2.785, 2022: -2.585, 2023: 1.522, 2024: 0.1594, 2025: -2.173} ; seuil {sharpe_min: -1, positives_min: 4}
- C6 : ÉCHEC ; mesure 0.9311 ; seuil 0.45
- C7 : OK ; mesure 1 ; seuil {part_voisins_min: 0.75, ratio: 0.6, sharpe_voisin_min: 0.5}
- C8 : ÉCHEC ; mesure 0.999 ; seuil 0.05
- C9 : OK ; mesure 0 ; seuil {aleatoires: 20, fixes: 3, part_non_pleine_min: 0.4, tolerance: 1e-09}
- C11 : ÉCHEC ; mesure (-0.3641, -0.9604) ; seuil (0.5, 0)
- C12 : ÉCHEC ; mesure (0.3388, 21) ; seuil (0.5, 15)
- C13 : ÉCHEC ; mesure (1.06, -0.5166) ; seuil 0
- C14 : OK ; mesure 0.08332 ; seuil 0.04
- C15 : ÉCHEC ; mesure None ; seuil (0, 0.585)
- C16 : ÉCHEC ; mesure None ; seuil 0.6
- C2 : ÉCHEC ; mesure 0.4296 ; seuil 0.5
- C3 : ÉCHEC ; mesure 0.8636 ; seuil 2
- C4 : OK ; mesure 0.2089 ; seuil 0
- C10 : ÉCHEC ; mesure 0.1914 ; seuil 0.05

### R0079 (e-largeur {L_jours: 28, s: 0.44})
- C1 : ÉCHEC ; mesure 0.04663 ; seuil 0.95
- C5 : ÉCHEC ; mesure {2020: 2.186, 2021: 2.762, 2022: -1.576, 2023: 1.524, 2024: 0.2903, 2025: -1.945} ; seuil {sharpe_min: -1, positives_min: 4}
- C6 : ÉCHEC ; mesure 0.8553 ; seuil 0.45
- C7 : OK ; mesure 0.75 ; seuil {part_voisins_min: 0.75, ratio: 0.6, sharpe_voisin_min: 0.5}
- C8 : ÉCHEC ; mesure 0.9838 ; seuil 0.05
- C9 : OK ; mesure 0 ; seuil {aleatoires: 20, fixes: 3, part_non_pleine_min: 0.4, tolerance: 1e-09}
- C11 : ÉCHEC ; mesure (-0.06115, -0.6592) ; seuil (0.5, 0)
- C12 : ÉCHEC ; mesure (0.224, 19.5) ; seuil (0.5, 15)
- C13 : ÉCHEC ; mesure (1.46, -0.3803) ; seuil 0
- C14 : OK ; mesure 0.2762 ; seuil 0.04
- C15 : ÉCHEC ; mesure None ; seuil (0, 0.585)
- C16 : ÉCHEC ; mesure None ; seuil 0.6
- C2 : OK ; mesure 0.7174 ; seuil 0.5
- C3 : ÉCHEC ; mesure 1.442 ; seuil 2
- C4 : OK ; mesure 0.5088 ; seuil 0
- C10 : ÉCHEC ; mesure 0.08158 ; seuil 0.05

### R0080 (e-largeur {L_jours: 28, s: 0.57})
- C1 : ÉCHEC ; mesure 0.2692 ; seuil 0.95
- C5 : ÉCHEC ; mesure {2020: 2.307, 2021: 3.037, 2022: -0.5907, 2023: 1.638, 2024: 0.9001, 2025: -1.396} ; seuil {sharpe_min: -1, positives_min: 4}
- C6 : ÉCHEC ; mesure 0.6711 ; seuil 0.45
- C7 : ÉCHEC ; mesure None ; seuil {part_voisins_min: 0.75, ratio: 0.6, sharpe_voisin_min: 0.5}
- C8 : ÉCHEC ; mesure 0.7974 ; seuil 0.05
- C9 : OK ; mesure 0 ; seuil {aleatoires: 20, fixes: 3, part_non_pleine_min: 0.4, tolerance: 1e-09}
- C11 : ÉCHEC ; mesure (0.3611, -0.2517) ; seuil (0.5681, 0)
- C12 : ÉCHEC ; mesure (0.1505, 17.92) ; seuil (0.5, 15)
- C13 : OK ; mesure (1.868, 0.06185) ; seuil 0
- C14 : OK ; mesure 0.5885 ; seuil 0.04
- C15 : ÉCHEC ; mesure None ; seuil (0, 0.585)
- C16 : ÉCHEC ; mesure None ; seuil 0.6
- C2 : OK ; mesure 1.136 ; seuil 0.5
- C3 : OK ; mesure 2.312 ; seuil 2
- C4 : OK ; mesure 0.9324 ; seuil 0
- C10 : OK ; mesure 0.0156 ; seuil 0.05

### R0081 (e-largeur {L_jours: 40, s: 0.2})
- C1 : ÉCHEC ; mesure 0.2423 ; seuil 0.95
- C5 : ÉCHEC ; mesure {2020: 2.328, 2021: 3.168, 2022: -1.732, 2023: 2.019, 2024: 1.253, 2025: -0.9108} ; seuil {sharpe_min: -1, positives_min: 4}
- C6 : ÉCHEC ; mesure 0.7981 ; seuil 0.45
- C7 : ÉCHEC ; mesure None ; seuil {part_voisins_min: 0.75, ratio: 0.6, sharpe_voisin_min: 0.5}
- C8 : ÉCHEC ; mesure 0.7187 ; seuil 0.05
- C9 : OK ; mesure 0 ; seuil {aleatoires: 20, fixes: 3, part_non_pleine_min: 0.4, tolerance: 1e-09}
- C11 : ÉCHEC ; mesure (0.4266, -0.113) ; seuil (0.5514, 0)
- C12 : ÉCHEC ; mesure (0.1191, 15.45) ; seuil (0.5, 15)
- C13 : OK ; mesure (1.663, 0.3327) ; seuil 0
- C14 : OK ; mesure 0.6324 ; seuil 0.04
- C15 : ÉCHEC ; mesure None ; seuil (0, 0.585)
- C16 : ÉCHEC ; mesure None ; seuil 0.6
- C2 : OK ; mesure 1.103 ; seuil 0.5
- C3 : OK ; mesure 2.285 ; seuil 2
- C4 : OK ; mesure 0.9519 ; seuil 0
- C10 : OK ; mesure 0.014 ; seuil 0.05

### R0082 (e-largeur {L_jours: 40, s: 0.26})
- C1 : ÉCHEC ; mesure 0.2702 ; seuil 0.95
- C5 : ÉCHEC ; mesure {2020: 2.355, 2021: 2.778, 2022: -1.437, 2023: 1.988, 2024: 1.321, 2025: -0.9319} ; seuil {sharpe_min: -1, positives_min: 4}
- C6 : ÉCHEC ; mesure 0.7447 ; seuil 0.45
- C7 : OK ; mesure 0.75 ; seuil {part_voisins_min: 0.75, ratio: 0.6, sharpe_voisin_min: 0.5}
- C8 : ÉCHEC ; mesure 0.7099 ; seuil 0.05
- C9 : OK ; mesure 0 ; seuil {aleatoires: 20, fixes: 3, part_non_pleine_min: 0.4, tolerance: 1e-09}
- C11 : ÉCHEC ; mesure (0.4395, -0.1137) ; seuil (0.5684, 0)
- C12 : ÉCHEC ; mesure (0.1232, 15.92) ; seuil (0.5, 15)
- C13 : OK ; mesure (1.629, 0.45) ; seuil 0
- C14 : OK ; mesure 0.6469 ; seuil 0.04
- C15 : ÉCHEC ; mesure None ; seuil (0, 0.585)
- C16 : ÉCHEC ; mesure None ; seuil 0.6
- C2 : OK ; mesure 1.137 ; seuil 0.5
- C3 : OK ; mesure 2.341 ; seuil 2
- C4 : OK ; mesure 0.9756 ; seuil 0
- C10 : OK ; mesure 0.0122 ; seuil 0.05

### R0083 (e-largeur {L_jours: 40, s: 0.34})
- C1 : ÉCHEC ; mesure 0.1683 ; seuil 0.95
- C5 : ÉCHEC ; mesure {2020: 1.854, 2021: 2.982, 2022: -1.581, 2023: 1.9, 2024: 0.2084, 2025: -0.5065} ; seuil {sharpe_min: -1, positives_min: 4}
- C6 : ÉCHEC ; mesure 0.6872 ; seuil 0.45
- C7 : OK ; mesure 0.75 ; seuil {part_voisins_min: 0.75, ratio: 0.6, sharpe_voisin_min: 0.5}
- C8 : ÉCHEC ; mesure 0.8796 ; seuil 0.05
- C9 : OK ; mesure 0 ; seuil {aleatoires: 20, fixes: 3, part_non_pleine_min: 0.4, tolerance: 1e-09}
- C11 : ÉCHEC ; mesure (0.2589, -0.3235) ; seuil (0.5, 0)
- C12 : ÉCHEC ; mesure (0.1473, 16.21) ; seuil (0.5, 15)
- C13 : OK ; mesure (1.533, 0.2171) ; seuil 0
- C14 : OK ; mesure 0.4949 ; seuil 0.04
- C15 : ÉCHEC ; mesure None ; seuil (0, 0.585)
- C16 : ÉCHEC ; mesure None ; seuil 0.6
- C2 : OK ; mesure 0.9986 ; seuil 0.5
- C3 : OK ; mesure 2.068 ; seuil 2
- C4 : OK ; mesure 0.825 ; seuil 0
- C10 : OK ; mesure 0.0246 ; seuil 0.05

### R0084 (e-largeur {L_jours: 40, s: 0.44})
- C1 : ÉCHEC ; mesure 0.2266 ; seuil 0.95
- C5 : ÉCHEC ; mesure {2020: 1.836, 2021: 3.105, 2022: -1.291, 2023: 1.823, 2024: 0.1601, 2025: -0.3047} ; seuil {sharpe_min: -1, positives_min: 4}
- C6 : ÉCHEC ; mesure 0.5821 ; seuil 0.45
- C7 : OK ; mesure 1 ; seuil {part_voisins_min: 0.75, ratio: 0.6, sharpe_voisin_min: 0.5}
- C8 : ÉCHEC ; mesure 0.8206 ; seuil 0.05
- C9 : OK ; mesure 0 ; seuil {aleatoires: 20, fixes: 3, part_non_pleine_min: 0.4, tolerance: 1e-09}
- C11 : ÉCHEC ; mesure (0.3404, -0.2471) ; seuil (0.5409, 0)
- C12 : ÉCHEC ; mesure (0.1313, 15.19) ; seuil (0.5, 15)
- C13 : OK ; mesure (1.642, 0.2661) ; seuil 0
- C14 : OK ; mesure 0.5612 ; seuil 0.04
- C15 : ÉCHEC ; mesure None ; seuil (0, 0.585)
- C16 : ÉCHEC ; mesure None ; seuil 0.6
- C2 : OK ; mesure 1.082 ; seuil 0.5
- C3 : OK ; mesure 2.25 ; seuil 2
- C4 : OK ; mesure 0.9171 ; seuil 0
- C10 : OK ; mesure 0.018 ; seuil 0.05

### R0085 (e-largeur {L_jours: 40, s: 0.57})
- C1 : ÉCHEC ; mesure 0.4163 ; seuil 0.95
- C5 : OK ; mesure {2020: 1.892, 2021: 3.263, 2022: -0.7792, 2023: 1.931, 2024: 1.095, 2025: -0.7547} ; seuil {sharpe_min: -1, positives_min: 4}
- C6 : ÉCHEC ; mesure 0.5553 ; seuil 0.45
- C7 : ÉCHEC ; mesure None ; seuil {part_voisins_min: 0.75, ratio: 0.6, sharpe_voisin_min: 0.5}
- C8 : ÉCHEC ; mesure 0.6505 ; seuil 0.05
- C9 : OK ; mesure 0 ; seuil {aleatoires: 20, fixes: 3, part_non_pleine_min: 0.4, tolerance: 1e-09}
- C11 : ÉCHEC ; mesure (0.5462, -0.05852) ; seuil (0.6479, 0)
- C12 : OK ; mesure (0.1145, 14.86) ; seuil (0.5, 15)
- C13 : OK ; mesure (1.878, 0.437) ; seuil 0
- C14 : OK ; mesure 0.7271 ; seuil 0.04
- C15 : ÉCHEC ; mesure None ; seuil (0, 0.585)
- C16 : ÉCHEC ; mesure None ; seuil 0.6
- C2 : OK ; mesure 1.296 ; seuil 0.5
- C3 : OK ; mesure 2.669 ; seuil 2
- C4 : OK ; mesure 1.126 ; seuil 0
- C10 : OK ; mesure 0.006799 ; seuil 0.05

### R0086 (e-largeur {L_jours: 56, s: 0.2})
- C1 : ÉCHEC ; mesure 0.1977 ; seuil 0.95
- C5 : ÉCHEC ; mesure {2020: 1.674, 2021: 2.851, 2022: -1.28, 2023: 1.534, 2024: 1.071, 2025: -0.08272} ; seuil {sharpe_min: -1, positives_min: 4}
- C6 : ÉCHEC ; mesure 0.6984 ; seuil 0.45
- C7 : ÉCHEC ; mesure None ; seuil {part_voisins_min: 0.75, ratio: 0.6, sharpe_voisin_min: 0.5}
- C8 : ÉCHEC ; mesure 0.766 ; seuil 0.05
- C9 : OK ; mesure 0 ; seuil {aleatoires: 20, fixes: 3, part_non_pleine_min: 0.4, tolerance: 1e-09}
- C11 : ÉCHEC ; mesure (0.3055, -0.2475) ; seuil (0.5225, 0)
- C12 : OK ; mesure (0.1097, 13.74) ; seuil (0.5, 15)
- C13 : OK ; mesure (1.502, 0.4044) ; seuil 0
- C14 : OK ; mesure 0.5882 ; seuil 0.04
- C15 : ÉCHEC ; mesure None ; seuil (0, 0.585)
- C16 : ÉCHEC ; mesure None ; seuil 0.6
- C2 : OK ; mesure 1.045 ; seuil 0.5
- C3 : OK ; mesure 2.269 ; seuil 2
- C4 : OK ; mesure 0.9151 ; seuil 0
- C10 : OK ; mesure 0.0152 ; seuil 0.05

### R0087 (e-largeur {L_jours: 56, s: 0.26})
- C1 : ÉCHEC ; mesure 0.2088 ; seuil 0.95
- C5 : ÉCHEC ; mesure {2020: 1.75, 2021: 2.765, 2022: -1.238, 2023: 1.923, 2024: 0.9702, 2025: -0.5526} ; seuil {sharpe_min: -1, positives_min: 4}
- C6 : ÉCHEC ; mesure 0.6392 ; seuil 0.45
- C7 : OK ; mesure 1 ; seuil {part_voisins_min: 0.75, ratio: 0.6, sharpe_voisin_min: 0.5}
- C8 : ÉCHEC ; mesure 0.776 ; seuil 0.05
- C9 : OK ; mesure 0 ; seuil {aleatoires: 20, fixes: 3, part_non_pleine_min: 0.4, tolerance: 1e-09}
- C11 : ÉCHEC ; mesure (0.3493, -0.2056) ; seuil (0.5291, 0)
- C12 : OK ; mesure (0.1151, 14) ; seuil (0.5, 15)
- C13 : OK ; mesure (1.544, 0.3745) ; seuil 0
- C14 : OK ; mesure 0.5799 ; seuil 0.04
- C15 : ÉCHEC ; mesure None ; seuil (0, 0.585)
- C16 : ÉCHEC ; mesure None ; seuil 0.6
- C2 : OK ; mesure 1.058 ; seuil 0.5
- C3 : OK ; mesure 2.171 ; seuil 2
- C4 : OK ; mesure 0.9197 ; seuil 0
- C10 : OK ; mesure 0.0196 ; seuil 0.05

### R0088 (e-largeur {L_jours: 56, s: 0.34})
- C1 : ÉCHEC ; mesure 0.2658 ; seuil 0.95
- C5 : ÉCHEC ; mesure {2020: 1.653, 2021: 2.957, 2022: -1.122, 2023: 1.771, 2024: 0.6021, 2025: 0.152} ; seuil {sharpe_min: -1, positives_min: 4}
- C6 : ÉCHEC ; mesure 0.5692 ; seuil 0.45
- C7 : OK ; mesure 1 ; seuil {part_voisins_min: 0.75, ratio: 0.6, sharpe_voisin_min: 0.5}
- C8 : ÉCHEC ; mesure 0.7477 ; seuil 0.05
- C9 : OK ; mesure 0 ; seuil {aleatoires: 20, fixes: 3, part_non_pleine_min: 0.4, tolerance: 1e-09}
- C11 : ÉCHEC ; mesure (0.3961, -0.179) ; seuil (0.5659, 0)
- C12 : OK ; mesure (0.1105, 13.6) ; seuil (0.5, 15)
- C13 : OK ; mesure (1.569, 0.5163) ; seuil 0
- C14 : OK ; mesure 0.6265 ; seuil 0.04
- C15 : ÉCHEC ; mesure None ; seuil (0, 0.585)
- C16 : ÉCHEC ; mesure None ; seuil 0.6
- C2 : OK ; mesure 1.132 ; seuil 0.5
- C3 : OK ; mesure 2.341 ; seuil 2
- C4 : OK ; mesure 0.99 ; seuil 0
- C10 : OK ; mesure 0.0136 ; seuil 0.05

### R0089 (e-largeur {L_jours: 56, s: 0.44})
- C1 : ÉCHEC ; mesure 0.2928 ; seuil 0.95
- C5 : OK ; mesure {2020: 1.82, 2021: 2.957, 2022: -0.7711, 2023: 1.69, 2024: 0.5523, 2025: -0.1172} ; seuil {sharpe_min: -1, positives_min: 4}
- C6 : ÉCHEC ; mesure 0.5426 ; seuil 0.45
- C7 : OK ; mesure 1 ; seuil {part_voisins_min: 0.75, ratio: 0.6, sharpe_voisin_min: 0.5}
- C8 : ÉCHEC ; mesure 0.7205 ; seuil 0.05
- C9 : OK ; mesure 0 ; seuil {aleatoires: 20, fixes: 3, part_non_pleine_min: 0.4, tolerance: 1e-09}
- C11 : ÉCHEC ; mesure (0.4242, -0.1567) ; seuil (0.5818, 0)
- C12 : OK ; mesure (0.1038, 12.91) ; seuil (0.5, 15)
- C13 : OK ; mesure (1.703, 0.3922) ; seuil 0
- C14 : OK ; mesure 0.6514 ; seuil 0.04
- C15 : ÉCHEC ; mesure None ; seuil (0, 0.585)
- C16 : ÉCHEC ; mesure None ; seuil 0.6
- C2 : OK ; mesure 1.164 ; seuil 0.5
- C3 : OK ; mesure 2.403 ; seuil 2
- C4 : OK ; mesure 1.028 ; seuil 0
- C10 : OK ; mesure 0.012 ; seuil 0.05

### R0090 (e-largeur {L_jours: 56, s: 0.57})
- C1 : ÉCHEC ; mesure 0.3291 ; seuil 0.95
- C5 : OK ; mesure {2020: 1.73, 2021: 3.195, 2022: -0.5326, 2023: 1.564, 2024: 0.1216, 2025: 0.176} ; seuil {sharpe_min: -1, positives_min: 4}
- C6 : ÉCHEC ; mesure 0.5175 ; seuil 0.45
- C7 : ÉCHEC ; mesure None ; seuil {part_voisins_min: 0.75, ratio: 0.6, sharpe_voisin_min: 0.5}
- C8 : ÉCHEC ; mesure 0.75 ; seuil 0.05
- C9 : OK ; mesure 0 ; seuil {aleatoires: 20, fixes: 3, part_non_pleine_min: 0.4, tolerance: 1e-09}
- C11 : ÉCHEC ; mesure (0.452, -0.1511) ; seuil (0.6019, 0)
- C12 : OK ; mesure (0.1106, 13.38) ; seuil (0.5, 15)
- C13 : OK ; mesure (1.865, 0.2198) ; seuil 0
- C14 : OK ; mesure 0.6489 ; seuil 0.04
- C15 : ÉCHEC ; mesure None ; seuil (0, 0.585)
- C16 : ÉCHEC ; mesure None ; seuil 0.6
- C2 : OK ; mesure 1.204 ; seuil 0.5
- C3 : OK ; mesure 2.473 ; seuil 2
- C4 : OK ; mesure 1.053 ; seuil 0
- C10 : OK ; mesure 0.0102 ; seuil 0.05

### R0091 (e-largeur {L_jours: 80, s: 0.2})
- C1 : ÉCHEC ; mesure 0.03303 ; seuil 0.95
- C5 : ÉCHEC ; mesure {2020: 0.9872, 2021: 2.579, 2022: -1.721, 2023: 0.5395, 2024: 0.6519, 2025: -0.09002} ; seuil {sharpe_min: -1, positives_min: 4}
- C6 : ÉCHEC ; mesure 0.8764 ; seuil 0.45
- C7 : ÉCHEC ; mesure None ; seuil {part_voisins_min: 0.75, ratio: 0.6, sharpe_voisin_min: 0.5}
- C8 : ÉCHEC ; mesure 0.9946 ; seuil 0.05
- C9 : OK ; mesure 0 ; seuil {aleatoires: 20, fixes: 3, part_non_pleine_min: 0.4, tolerance: 1e-09}
- C11 : ÉCHEC ; mesure (-0.07782, -0.609) ; seuil (0.5, 0)
- C12 : OK ; mesure (0.1542, 13.2) ; seuil (0.5, 15)
- C13 : OK ; mesure (0.9979, 0.1214) ; seuil 0
- C14 : OK ; mesure 0.2238 ; seuil 0.04
- C15 : ÉCHEC ; mesure None ; seuil (0, 0.585)
- C16 : ÉCHEC ; mesure None ; seuil 0.6
- C2 : OK ; mesure 0.6475 ; seuil 0.5
- C3 : ÉCHEC ; mesure 1.395 ; seuil 2
- C4 : OK ; mesure 0.5287 ; seuil 0
- C10 : ÉCHEC ; mesure 0.08918 ; seuil 0.05

### R0092 (e-largeur {L_jours: 80, s: 0.26})
- C1 : ÉCHEC ; mesure 0.06363 ; seuil 0.95
- C5 : ÉCHEC ; mesure {2020: 0.9488, 2021: 2.497, 2022: -1.329, 2023: 0.7919, 2024: 0.8466, 2025: 0.1974} ; seuil {sharpe_min: -1, positives_min: 4}
- C6 : ÉCHEC ; mesure 0.8061 ; seuil 0.45
- C7 : ÉCHEC ; mesure None ; seuil {part_voisins_min: 0.75, ratio: 0.6, sharpe_voisin_min: 0.5}
- C8 : ÉCHEC ; mesure 0.9724 ; seuil 0.05
- C9 : OK ; mesure 0 ; seuil {aleatoires: 20, fixes: 3, part_non_pleine_min: 0.4, tolerance: 1e-09}
- C11 : ÉCHEC ; mesure (0.06962, -0.4646) ; seuil (0.5, 0)
- C12 : OK ; mesure (0.1332, 12.64) ; seuil (0.5, 15)
- C13 : OK ; mesure (1.032, 0.3874) ; seuil 0
- C14 : OK ; mesure 0.3212 ; seuil 0.04
- C15 : ÉCHEC ; mesure None ; seuil (0, 0.585)
- C16 : ÉCHEC ; mesure None ; seuil 0.6
- C2 : OK ; mesure 0.7669 ; seuil 0.5
- C3 : ÉCHEC ; mesure 1.58 ; seuil 2
- C4 : OK ; mesure 0.6485 ; seuil 0
- C10 : ÉCHEC ; mesure 0.06179 ; seuil 0.05

### R0093 (e-largeur {L_jours: 80, s: 0.34})
- C1 : ÉCHEC ; mesure 0.1435 ; seuil 0.95
- C5 : ÉCHEC ; mesure {2020: 1.538, 2021: 2.741, 2022: -1.51, 2023: 0.5734, 2024: 0.994, 2025: 0.1974} ; seuil {sharpe_min: -1, positives_min: 4}
- C6 : ÉCHEC ; mesure 0.7498 ; seuil 0.45
- C7 : ÉCHEC ; mesure None ; seuil {part_voisins_min: 0.75, ratio: 0.6, sharpe_voisin_min: 0.5}
- C8 : ÉCHEC ; mesure 0.8938 ; seuil 0.05
- C9 : OK ; mesure 0 ; seuil {aleatoires: 20, fixes: 3, part_non_pleine_min: 0.4, tolerance: 1e-09}
- C11 : ÉCHEC ; mesure (0.2255, -0.3408) ; seuil (0.5, 0)
- C12 : OK ; mesure (0.1117, 11.94) ; seuil (0.5, 15)
- C13 : OK ; mesure (1.377, 0.3655) ; seuil 0
- C14 : OK ; mesure 0.478 ; seuil 0.04
- C15 : ÉCHEC ; mesure None ; seuil (0, 0.585)
- C16 : ÉCHEC ; mesure None ; seuil 0.6
- C2 : OK ; mesure 0.9581 ; seuil 0.5
- C3 : ÉCHEC ; mesure 1.974 ; seuil 2
- C4 : OK ; mesure 0.8373 ; seuil 0
- C10 : OK ; mesure 0.03259 ; seuil 0.05

### R0094 (e-largeur {L_jours: 80, s: 0.44})
- C1 : ÉCHEC ; mesure 0.1588 ; seuil 0.95
- C5 : ÉCHEC ; mesure {2020: 1.335, 2021: 2.741, 2022: -1.289, 2023: 0.916, 2024: 0.9617, 2025: 0.1597} ; seuil {sharpe_min: -1, positives_min: 4}
- C6 : ÉCHEC ; mesure 0.6744 ; seuil 0.45
- C7 : ÉCHEC ; mesure None ; seuil {part_voisins_min: 0.75, ratio: 0.6, sharpe_voisin_min: 0.5}
- C8 : ÉCHEC ; mesure 0.8722 ; seuil 0.05
- C9 : OK ; mesure 0 ; seuil {aleatoires: 20, fixes: 3, part_non_pleine_min: 0.4, tolerance: 1e-09}
- C11 : ÉCHEC ; mesure (0.2588, -0.306) ; seuil (0.5, 0)
- C12 : OK ; mesure (0.1018, 10.92) ; seuil (0.5, 15)
- C13 : OK ; mesure (1.355, 0.4667) ; seuil 0
- C14 : OK ; mesure 0.4963 ; seuil 0.04
- C15 : ÉCHEC ; mesure None ; seuil (0, 0.585)
- C16 : ÉCHEC ; mesure None ; seuil 0.6
- C2 : OK ; mesure 0.9834 ; seuil 0.5
- C3 : OK ; mesure 2.029 ; seuil 2
- C4 : OK ; mesure 0.8719 ; seuil 0
- C10 : OK ; mesure 0.02819 ; seuil 0.05

### R0095 (e-largeur {L_jours: 80, s: 0.57})
- C1 : ÉCHEC ; mesure 0.1925 ; seuil 0.95
- C5 : ÉCHEC ; mesure {2020: 1.372, 2021: 3.133, 2022: -1.5, 2023: 1.016, 2024: 0.2877, 2025: -0.04192} ; seuil {sharpe_min: -1, positives_min: 4}
- C6 : ÉCHEC ; mesure 0.573 ; seuil 0.45
- C7 : ÉCHEC ; mesure None ; seuil {part_voisins_min: 0.75, ratio: 0.6, sharpe_voisin_min: 0.5}
- C8 : ÉCHEC ; mesure 0.858 ; seuil 0.05
- C9 : OK ; mesure 0 ; seuil {aleatoires: 20, fixes: 3, part_non_pleine_min: 0.4, tolerance: 1e-09}
- C11 : ÉCHEC ; mesure (0.2685, -0.3317) ; seuil (0.5178, 0)
- C12 : OK ; mesure (0.1094, 11.63) ; seuil (0.5, 15)
- C13 : OK ; mesure (1.582, 0.2181) ; seuil 0
- C14 : OK ; mesure 0.5154 ; seuil 0.04
- C15 : ÉCHEC ; mesure None ; seuil (0, 0.585)
- C16 : ÉCHEC ; mesure None ; seuil 0.6
- C2 : OK ; mesure 1.036 ; seuil 0.5
- C3 : OK ; mesure 2.205 ; seuil 2
- C4 : OK ; mesure 0.9083 ; seuil 0
- C10 : OK ; mesure 0.0198 ; seuil 0.05

### R0096 (f-rattrapage {h_jours: 5, theta: 0.5})
- C1 : ÉCHEC ; mesure 0.001213 ; seuil 0.95
- C5 : ÉCHEC ; mesure {2020: 0.6353, 2021: 2.299, 2022: -2.321, 2023: 0.7255, 2024: 0.22, 2025: -0.4682} ; seuil {sharpe_min: -1, positives_min: 4}
- C6 : ÉCHEC ; mesure 0.6252 ; seuil 0.45
- C7 : ÉCHEC ; mesure None ; seuil {part_voisins_min: 0.75, ratio: 0.6, sharpe_voisin_min: 0.5}
- C8 : ÉCHEC ; mesure 0.997 ; seuil 0.05
- C9 : OK ; mesure 0 ; seuil {aleatoires: 20, fixes: 3, part_non_pleine_min: 0.4, tolerance: 1e-09}
- C11 : ÉCHEC ; mesure (-0.7547, -1.447) ; seuil (0.5, 0)
- C12 : ÉCHEC ; mesure (0.7478, 28.06) ; seuil (0.5, 15)
- C13 : ÉCHEC ; mesure (0.5831, -0.4093) ; seuil 0
- C14 : ÉCHEC ; mesure 0.02082 ; seuil 0.04
- C15 : ÉCHEC ; mesure None ; seuil (0, 0.585)
- C16 : ÉCHEC ; mesure None ; seuil 0.6
- C2 : ÉCHEC ; mesure 0.2087 ; seuil 0.5
- C3 : ÉCHEC ; mesure 0.4901 ; seuil 2
- C4 : ÉCHEC ; mesure -0.4096 ; seuil 0
- C10 : ÉCHEC ; mesure 0.3061 ; seuil 0.05

### R0097 (f-rattrapage {h_jours: 5, theta: 0.75})
- C1 : ÉCHEC ; mesure 0.0002173 ; seuil 0.95
- C5 : ÉCHEC ; mesure {2020: 0.2226, 2021: 2.051, 2022: -2.179, 2023: 0.6285, 2024: 0.2966, 2025: -0.2856} ; seuil {sharpe_min: -1, positives_min: 4}
- C6 : ÉCHEC ; mesure 0.5429 ; seuil 0.45
- C7 : ÉCHEC ; mesure None ; seuil {part_voisins_min: 0.75, ratio: 0.6, sharpe_voisin_min: 0.5}
- C8 : ÉCHEC ; mesure 0.9956 ; seuil 0.05
- C9 : OK ; mesure 0 ; seuil {aleatoires: 20, fixes: 3, part_non_pleine_min: 0.4, tolerance: 1e-09}
- C11 : ÉCHEC ; mesure (-0.9016, -1.602) ; seuil (0.5, 0)
- C12 : ÉCHEC ; mesure (1, 21.98) ; seuil (0.5, 15)
- C13 : ÉCHEC ; mesure (0.2382, -0.3571) ; seuil 0
- C14 : ÉCHEC ; mesure -0.02107 ; seuil 0.04
- C15 : ÉCHEC ; mesure None ; seuil (0, 0.585)
- C16 : ÉCHEC ; mesure None ; seuil 0.6
- C2 : ÉCHEC ; mesure -0.0001239 ; seuil 0.5
- C3 : ÉCHEC ; mesure -0.00031 ; seuil 2
- C4 : ÉCHEC ; mesure -0.6386 ; seuil 0
- C10 : ÉCHEC ; mesure 0.5005 ; seuil 0.05

### R0098 (f-rattrapage {h_jours: 5, theta: 1.1})
- C1 : ÉCHEC ; mesure 0.0002407 ; seuil 0.95
- C5 : ÉCHEC ; mesure {2020: -0.2568, 2021: 1.471, 2022: -1.235, 2023: 0.5487, 2024: 0.4585, 2025: -0.2355} ; seuil {sharpe_min: -1, positives_min: 4}
- C6 : OK ; mesure 0.2915 ; seuil 0.45
- C7 : ÉCHEC ; mesure None ; seuil {part_voisins_min: 0.75, ratio: 0.6, sharpe_voisin_min: 0.5}
- C8 : ÉCHEC ; mesure 0.993 ; seuil 0.05
- C9 : OK ; mesure 0 ; seuil {aleatoires: 20, fixes: 3, part_non_pleine_min: 0.4, tolerance: 1e-09}
- C11 : ÉCHEC ; mesure (-1.034, -1.777) ; seuil (0.5, 0)
- C12 : ÉCHEC ; mesure (0.9819, 13.72) ; seuil (0.5, 15)
- C13 : ÉCHEC ; mesure (0.2484, -0.3581) ; seuil 0
- C14 : ÉCHEC ; mesure -0.0091 ; seuil 0.04
- C15 : ÉCHEC ; mesure None ; seuil (0, 0.585)
- C16 : ÉCHEC ; mesure None ; seuil 0.6
- C2 : ÉCHEC ; mesure 0.01042 ; seuil 0.5
- C3 : ÉCHEC ; mesure 0.0276 ; seuil 2
- C4 : ÉCHEC ; mesure -0.5514 ; seuil 0
- C10 : ÉCHEC ; mesure 0.4809 ; seuil 0.05

### R0099 (f-rattrapage {h_jours: 5, theta: 1.6})
- C1 : ÉCHEC ; mesure 0.0001082 ; seuil 0.95
- C5 : ÉCHEC ; mesure {2020: 0.3404, 2021: 1.205, 2022: -1.018, 2023: -0.05465, 2024: -0.4571, 2025: -0.2487} ; seuil {sharpe_min: -1, positives_min: 4}
- C6 : OK ; mesure 0.269 ; seuil 0.45
- C7 : ÉCHEC ; mesure None ; seuil {part_voisins_min: 0.75, ratio: 0.6, sharpe_voisin_min: 0.5}
- C8 : ÉCHEC ; mesure 0.9914 ; seuil 0.05
- C9 : OK ; mesure 0 ; seuil {aleatoires: 20, fixes: 3, part_non_pleine_min: 0.4, tolerance: 1e-09}
- C11 : ÉCHEC ; mesure (-1.388, -2.126) ; seuil (0.5, 0)
- C12 : ÉCHEC ; mesure (1.192, 7.149) ; seuil (0.5, 15)
- C13 : ÉCHEC ; mesure (0.4227, -0.8116) ; seuil 0
- C14 : ÉCHEC ; mesure -0.01158 ; seuil 0.04
- C15 : ÉCHEC ; mesure None ; seuil (0, 0.585)
- C16 : ÉCHEC ; mesure None ; seuil 0.6
- C2 : ÉCHEC ; mesure -0.07107 ; seuil 0.5
- C3 : ÉCHEC ; mesure -0.2076 ; seuil 2
- C4 : ÉCHEC ; mesure -0.5091 ; seuil 0
- C10 : ÉCHEC ; mesure 0.5695 ; seuil 0.05

### R0100 (f-rattrapage {h_jours: 5, theta: 2.4})
- C1 : ÉCHEC ; mesure 2.581e-05 ; seuil 0.95
- C5 : ÉCHEC ; mesure {2020: -0.09553, 2021: 1.303, 2022: -0.4581, 2023: -0.1981, 2024: -1.063, 2025: -0.4237} ; seuil {sharpe_min: -1, positives_min: 4}
- C6 : OK ; mesure 0.1096 ; seuil 0.45
- C7 : ÉCHEC ; mesure None ; seuil {part_voisins_min: 0.75, ratio: 0.6, sharpe_voisin_min: 0.5}
- C8 : ÉCHEC ; mesure 0.99 ; seuil 0.05
- C9 : OK ; mesure 0 ; seuil {aleatoires: 20, fixes: 3, part_non_pleine_min: 0.4, tolerance: 1e-09}
- C11 : ÉCHEC ; mesure (-1.527, -2.05) ; seuil (0.5, 0)
- C12 : ÉCHEC ; mesure (3.321, 1.931) ; seuil (0.5, 15)
- C13 : ÉCHEC ; mesure (0.1102, -0.59) ; seuil 0
- C14 : ÉCHEC ; mesure -0.009184 ; seuil 0.04
- C15 : ÉCHEC ; mesure None ; seuil (0, 0.585)
- C16 : ÉCHEC ; mesure None ; seuil 0.6
- C2 : ÉCHEC ; mesure -0.1711 ; seuil 0.5
- C3 : ÉCHEC ; mesure -0.713 ; seuil 2
- C4 : ÉCHEC ; mesure -0.4137 ; seuil 0
- C10 : ÉCHEC ; mesure 0.767 ; seuil 0.05

### R0101 (f-rattrapage {h_jours: 7, theta: 0.5})
- C1 : ÉCHEC ; mesure 9.912e-05 ; seuil 0.95
- C5 : ÉCHEC ; mesure {2020: 0.4413, 2021: 2.068, 2022: -2.345, 2023: 1.376, 2024: -0.2407, 2025: -1.047} ; seuil {sharpe_min: -1, positives_min: 4}
- C6 : ÉCHEC ; mesure 0.6715 ; seuil 0.45
- C7 : ÉCHEC ; mesure None ; seuil {part_voisins_min: 0.75, ratio: 0.6, sharpe_voisin_min: 0.5}
- C8 : ÉCHEC ; mesure 0.9972 ; seuil 0.05
- C9 : OK ; mesure 0 ; seuil {aleatoires: 20, fixes: 3, part_non_pleine_min: 0.4, tolerance: 1e-09}
- C11 : ÉCHEC ; mesure (-0.9587, -1.594) ; seuil (0.5, 0)
- C12 : ÉCHEC ; mesure (1.156, 23.17) ; seuil (0.5, 15)
- C13 : ÉCHEC ; mesure (0.2414, -0.5871) ; seuil 0
- C14 : ÉCHEC ; mesure -0.04574 ; seuil 0.04
- C15 : ÉCHEC ; mesure None ; seuil (0, 0.585)
- C16 : ÉCHEC ; mesure None ; seuil 0.6
- C2 : ÉCHEC ; mesure -0.07921 ; seuil 0.5
- C3 : ÉCHEC ; mesure -0.1997 ; seuil 2
- C4 : ÉCHEC ; mesure -0.6649 ; seuil 0
- C10 : ÉCHEC ; mesure 0.5831 ; seuil 0.05

### R0102 (f-rattrapage {h_jours: 7, theta: 0.75})
- C1 : ÉCHEC ; mesure 0.0001052 ; seuil 0.95
- C5 : ÉCHEC ; mesure {2020: 0.4024, 2021: 2.118, 2022: -1.831, 2023: 0.3057, 2024: -0.04376, 2025: -1.069} ; seuil {sharpe_min: -1, positives_min: 4}
- C6 : ÉCHEC ; mesure 0.5673 ; seuil 0.45
- C7 : ÉCHEC ; mesure 0 ; seuil {part_voisins_min: 0.75, ratio: 0.6, sharpe_voisin_min: 0.5}
- C8 : ÉCHEC ; mesure 0.995 ; seuil 0.05
- C9 : OK ; mesure 0 ; seuil {aleatoires: 20, fixes: 3, part_non_pleine_min: 0.4, tolerance: 1e-09}
- C11 : ÉCHEC ; mesure (-0.9846, -1.651) ; seuil (0.5, 0)
- C12 : ÉCHEC ; mesure (1.151, 17.69) ; seuil (0.5, 15)
- C13 : ÉCHEC ; mesure (0.3587, -0.798) ; seuil 0
- C14 : ÉCHEC ; mesure -0.03175 ; seuil 0.04
- C15 : ÉCHEC ; mesure None ; seuil (0, 0.585)
- C16 : ÉCHEC ; mesure None ; seuil 0.6
- C2 : ÉCHEC ; mesure -0.07286 ; seuil 0.5
- C3 : ÉCHEC ; mesure -0.1927 ; seuil 2
- C4 : ÉCHEC ; mesure -0.6261 ; seuil 0
- C10 : ÉCHEC ; mesure 0.5747 ; seuil 0.05

### R0103 (f-rattrapage {h_jours: 7, theta: 1.1})
- C1 : ÉCHEC ; mesure 4.395e-06 ; seuil 0.95
- C5 : ÉCHEC ; mesure {2020: 0.1275, 2021: 1.307, 2022: -1.624, 2023: 0.6183, 2024: -0.967, 2025: -1.154} ; seuil {sharpe_min: -1, positives_min: 4}
- C6 : ÉCHEC ; mesure 0.4717 ; seuil 0.45
- C7 : ÉCHEC ; mesure 0 ; seuil {part_voisins_min: 0.75, ratio: 0.6, sharpe_voisin_min: 0.5}
- C8 : ÉCHEC ; mesure 0.9948 ; seuil 0.05
- C9 : OK ; mesure 0 ; seuil {aleatoires: 20, fixes: 3, part_non_pleine_min: 0.4, tolerance: 1e-09}
- C11 : ÉCHEC ; mesure (-1.457, -2.171) ; seuil (0.5, 0)
- C12 : ÉCHEC ; mesure (3.93, 11.27) ; seuil (0.5, 15)
- C13 : ÉCHEC ; mesure (0.1239, -1.159) ; seuil 0
- C14 : ÉCHEC ; mesure -0.05839 ; seuil 0.04
- C15 : ÉCHEC ; mesure None ; seuil (0, 0.585)
- C16 : ÉCHEC ; mesure None ; seuil 0.6
- C2 : ÉCHEC ; mesure -0.3613 ; seuil 0.5
- C3 : ÉCHEC ; mesure -1.006 ; seuil 2
- C4 : ÉCHEC ; mesure -0.8435 ; seuil 0
- C10 : ÉCHEC ; mesure 0.8486 ; seuil 0.05

### R0104 (f-rattrapage {h_jours: 7, theta: 1.6})
- C1 : ÉCHEC ; mesure 1.773e-05 ; seuil 0.95
- C5 : ÉCHEC ; mesure {2020: -0.2866, 2021: 1.854, 2022: -0.9184, 2023: 0.3102, 2024: -0.978, 2025: -1.174} ; seuil {sharpe_min: -1, positives_min: 4}
- C6 : OK ; mesure 0.2498 ; seuil 0.45
- C7 : ÉCHEC ; mesure 0 ; seuil {part_voisins_min: 0.75, ratio: 0.6, sharpe_voisin_min: 0.5}
- C8 : ÉCHEC ; mesure 0.9918 ; seuil 0.05
- C9 : OK ; mesure 0 ; seuil {aleatoires: 20, fixes: 3, part_non_pleine_min: 0.4, tolerance: 1e-09}
- C11 : ÉCHEC ; mesure (-1.471, -2.219) ; seuil (0.5, 0)
- C12 : ÉCHEC ; mesure (2.504, 5.782) ; seuil (0.5, 15)
- C13 : ÉCHEC ; mesure (0.231, -0.9724) ; seuil 0
- C14 : ÉCHEC ; mesure -0.02444 ; seuil 0.04
- C15 : ÉCHEC ; mesure None ; seuil (0, 0.585)
- C16 : ÉCHEC ; mesure None ; seuil 0.6
- C2 : ÉCHEC ; mesure -0.2363 ; seuil 0.5
- C3 : ÉCHEC ; mesure -0.7297 ; seuil 2
- C4 : ÉCHEC ; mesure -0.6265 ; seuil 0
- C10 : ÉCHEC ; mesure 0.7736 ; seuil 0.05

### R0105 (f-rattrapage {h_jours: 7, theta: 2.4})
- C1 : ÉCHEC ; mesure 4.866e-05 ; seuil 0.95
- C5 : ÉCHEC ; mesure {2020: 0.201, 2021: 1.904, 2022: -1.286, 2023: 0.5245, 2024: -1.04, 2025: -1.095} ; seuil {sharpe_min: -1, positives_min: 4}
- C6 : OK ; mesure 0.1022 ; seuil 0.45
- C7 : ÉCHEC ; mesure None ; seuil {part_voisins_min: 0.75, ratio: 0.6, sharpe_voisin_min: 0.5}
- C8 : ÉCHEC ; mesure 0.99 ; seuil 0.05
- C9 : OK ; mesure 0 ; seuil {aleatoires: 20, fixes: 3, part_non_pleine_min: 0.4, tolerance: 1e-09}
- C11 : ÉCHEC ; mesure (-1.64, -2.288) ; seuil (0.5, 0)
- C12 : ÉCHEC ; mesure (2.346, 1.723) ; seuil (0.5, 15)
- C13 : ÉCHEC ; mesure (0.234, -0.7271) ; seuil 0
- C14 : ÉCHEC ; mesure -0.006799 ; seuil 0.04
- C15 : ÉCHEC ; mesure None ; seuil (0, 0.585)
- C16 : ÉCHEC ; mesure None ; seuil 0.6
- C2 : ÉCHEC ; mesure -0.1408 ; seuil 0.5
- C3 : ÉCHEC ; mesure -0.5196 ; seuil 2
- C4 : ÉCHEC ; mesure -0.3856 ; seuil 0
- C10 : ÉCHEC ; mesure 0.7017 ; seuil 0.05

### R0106 (f-rattrapage {h_jours: 10, theta: 0.5})
- C1 : ÉCHEC ; mesure 0.001544 ; seuil 0.95
- C5 : ÉCHEC ; mesure {2020: 0.5547, 2021: 2.293, 2022: -1.88, 2023: 0.8781, 2024: 0.4543, 2025: -1.004} ; seuil {sharpe_min: -1, positives_min: 4}
- C6 : ÉCHEC ; mesure 0.5519 ; seuil 0.45
- C7 : ÉCHEC ; mesure None ; seuil {part_voisins_min: 0.75, ratio: 0.6, sharpe_voisin_min: 0.5}
- C8 : ÉCHEC ; mesure 0.9958 ; seuil 0.05
- C9 : OK ; mesure 0 ; seuil {aleatoires: 20, fixes: 3, part_non_pleine_min: 0.4, tolerance: 1e-09}
- C11 : ÉCHEC ; mesure (-0.7778, -1.413) ; seuil (0.5, 0)
- C12 : ÉCHEC ; mesure (0.6413, 18.51) ; seuil (0.5, 15)
- C13 : ÉCHEC ; mesure (0.699, -0.5414) ; seuil 0
- C14 : ÉCHEC ; mesure 0.03376 ; seuil 0.04
- C15 : ÉCHEC ; mesure None ; seuil (0, 0.585)
- C16 : ÉCHEC ; mesure None ; seuil 0.6
- C2 : ÉCHEC ; mesure 0.2539 ; seuil 0.5
- C3 : ÉCHEC ; mesure 0.6122 ; seuil 2
- C4 : ÉCHEC ; mesure -0.1998 ; seuil 0
- C10 : ÉCHEC ; mesure 0.2631 ; seuil 0.05

### R0107 (f-rattrapage {h_jours: 10, theta: 0.75})
- C1 : ÉCHEC ; mesure 0.0002328 ; seuil 0.95
- C5 : ÉCHEC ; mesure {2020: 0.2416, 2021: 2.198, 2022: -1.643, 2023: 0.6501, 2024: 0.86, 2025: -1.159} ; seuil {sharpe_min: -1, positives_min: 4}
- C6 : OK ; mesure 0.446 ; seuil 0.45
- C7 : ÉCHEC ; mesure 0 ; seuil {part_voisins_min: 0.75, ratio: 0.6, sharpe_voisin_min: 0.5}
- C8 : ÉCHEC ; mesure 0.9944 ; seuil 0.05
- C9 : OK ; mesure 0 ; seuil {aleatoires: 20, fixes: 3, part_non_pleine_min: 0.4, tolerance: 1e-09}
- C11 : ÉCHEC ; mesure (-0.9578, -1.624) ; seuil (0.5, 0)
- C12 : ÉCHEC ; mesure (0.9855, 14.19) ; seuil (0.5, 15)
- C13 : ÉCHEC ; mesure (0.388, -0.5821) ; seuil 0
- C14 : ÉCHEC ; mesure -0.01433 ; seuil 0.04
- C15 : ÉCHEC ; mesure None ; seuil (0, 0.585)
- C16 : ÉCHEC ; mesure None ; seuil 0.6
- C2 : ÉCHEC ; mesure 0.007052 ; seuil 0.5
- C3 : ÉCHEC ; mesure 0.01818 ; seuil 2
- C4 : ÉCHEC ; mesure -0.4723 ; seuil 0
- C10 : ÉCHEC ; mesure 0.4855 ; seuil 0.05

### R0108 (f-rattrapage {h_jours: 10, theta: 1.1})
- C1 : ÉCHEC ; mesure 2.212e-05 ; seuil 0.95
- C5 : ÉCHEC ; mesure {2020: 0.2245, 2021: 1.361, 2022: -1.573, 2023: 0.4387, 2024: 0.8245, 2025: -1.49} ; seuil {sharpe_min: -1, positives_min: 4}
- C6 : OK ; mesure 0.3883 ; seuil 0.45
- C7 : ÉCHEC ; mesure 0 ; seuil {part_voisins_min: 0.75, ratio: 0.6, sharpe_voisin_min: 0.5}
- C8 : ÉCHEC ; mesure 0.9942 ; seuil 0.05
- C9 : OK ; mesure 0 ; seuil {aleatoires: 20, fixes: 3, part_non_pleine_min: 0.4, tolerance: 1e-09}
- C11 : ÉCHEC ; mesure (-1.199, -1.909) ; seuil (0.5, 0)
- C12 : ÉCHEC ; mesure (2.047, 9.318) ; seuil (0.5, 15)
- C13 : ÉCHEC ; mesure (0.1883, -0.8448) ; seuil 0
- C14 : ÉCHEC ; mesure -0.03614 ; seuil 0.04
- C15 : ÉCHEC ; mesure None ; seuil (0, 0.585)
- C16 : ÉCHEC ; mesure None ; seuil 0.6
- C2 : ÉCHEC ; mesure -0.223 ; seuil 0.5
- C3 : ÉCHEC ; mesure -0.6054 ; seuil 2
- C4 : ÉCHEC ; mesure -0.6567 ; seuil 0
- C10 : ÉCHEC ; mesure 0.7365 ; seuil 0.05

### R0109 (f-rattrapage {h_jours: 10, theta: 1.6})
- C1 : ÉCHEC ; mesure 2.25e-05 ; seuil 0.95
- C5 : ÉCHEC ; mesure {2020: -0.1417, 2021: 1.875, 2022: -2.056, 2023: 1.001, 2024: -0.469, 2025: -1.603} ; seuil {sharpe_min: -1, positives_min: 4}
- C6 : OK ; mesure 0.2406 ; seuil 0.45
- C7 : ÉCHEC ; mesure 0 ; seuil {part_voisins_min: 0.75, ratio: 0.6, sharpe_voisin_min: 0.5}
- C8 : ÉCHEC ; mesure 0.9916 ; seuil 0.05
- C9 : OK ; mesure 0 ; seuil {aleatoires: 20, fixes: 3, part_non_pleine_min: 0.4, tolerance: 1e-09}
- C11 : ÉCHEC ; mesure (-1.524, -2.229) ; seuil (0.5, 0)
- C12 : ÉCHEC ; mesure (3.001, 4.648) ; seuil (0.5, 15)
- C13 : ÉCHEC ; mesure (0.2846, -1.016) ; seuil 0
- C14 : ÉCHEC ; mesure -0.02176 ; seuil 0.04
- C15 : ÉCHEC ; mesure None ; seuil (0, 0.585)
- C16 : ÉCHEC ; mesure None ; seuil 0.6
- C2 : ÉCHEC ; mesure -0.2252 ; seuil 0.5
- C3 : ÉCHEC ; mesure -0.6312 ; seuil 2
- C4 : ÉCHEC ; mesure -0.5616 ; seuil 0
- C10 : ÉCHEC ; mesure 0.7429 ; seuil 0.05

### R0110 (f-rattrapage {h_jours: 10, theta: 2.4})
- C1 : ÉCHEC ; mesure 6.626e-05 ; seuil 0.95
- C5 : ÉCHEC ; mesure {2020: 0.3897, 2021: 1.513, 2022: -1.38, 2023: 0.4553, 2024: 0.04272, 2025: -1.25} ; seuil {sharpe_min: -1, positives_min: 4}
- C6 : OK ; mesure 0.1077 ; seuil 0.45
- C7 : ÉCHEC ; mesure None ; seuil {part_voisins_min: 0.75, ratio: 0.6, sharpe_voisin_min: 0.5}
- C8 : ÉCHEC ; mesure 0.9902 ; seuil 0.05
- C9 : OK ; mesure 0 ; seuil {aleatoires: 20, fixes: 3, part_non_pleine_min: 0.4, tolerance: 1e-09}
- C11 : ÉCHEC ; mesure (-1.787, -2.525) ; seuil (0.5, 0)
- C12 : ÉCHEC ; mesure (3.048, 1.251) ; seuil (0.5, 15)
- C13 : ÉCHEC ; mesure (0.313, -0.6531) ; seuil 0
- C14 : ÉCHEC ; mesure -0.005747 ; seuil 0.04
- C15 : ÉCHEC ; mesure None ; seuil (0, 0.585)
- C16 : ÉCHEC ; mesure None ; seuil 0.6
- C2 : ÉCHEC ; mesure -0.1328 ; seuil 0.5
- C3 : ÉCHEC ; mesure -0.3994 ; seuil 2
- C4 : ÉCHEC ; mesure -0.3287 ; seuil 0
- C10 : ÉCHEC ; mesure 0.6635 ; seuil 0.05

### R0111 (f-rattrapage {h_jours: 14, theta: 0.5})
- C1 : ÉCHEC ; mesure 0.0007686 ; seuil 0.95
- C5 : ÉCHEC ; mesure {2020: 0.5548, 2021: 2.06, 2022: -1.764, 2023: 1.066, 2024: 0.4966, 2025: -1.511} ; seuil {sharpe_min: -1, positives_min: 4}
- C6 : ÉCHEC ; mesure 0.5662 ; seuil 0.45
- C7 : ÉCHEC ; mesure None ; seuil {part_voisins_min: 0.75, ratio: 0.6, sharpe_voisin_min: 0.5}
- C8 : ÉCHEC ; mesure 0.9962 ; seuil 0.05
- C9 : OK ; mesure 0 ; seuil {aleatoires: 20, fixes: 3, part_non_pleine_min: 0.4, tolerance: 1e-09}
- C11 : ÉCHEC ; mesure (-0.8448, -1.472) ; seuil (0.5, 0)
- C12 : ÉCHEC ; mesure (0.7029, 15.12) ; seuil (0.5, 15)
- C13 : ÉCHEC ; mesure (0.5779, -0.5481) ; seuil 0
- C14 : ÉCHEC ; mesure 0.01104 ; seuil 0.04
- C15 : ÉCHEC ; mesure None ; seuil (0, 0.585)
- C16 : ÉCHEC ; mesure None ; seuil 0.6
- C2 : ÉCHEC ; mesure 0.1612 ; seuil 0.5
- C3 : ÉCHEC ; mesure 0.3839 ; seuil 2
- C4 : ÉCHEC ; mesure -0.2197 ; seuil 0
- C10 : ÉCHEC ; mesure 0.3343 ; seuil 0.05

### R0112 (f-rattrapage {h_jours: 14, theta: 0.75})
- C1 : ÉCHEC ; mesure 0.0004048 ; seuil 0.95
- C5 : ÉCHEC ; mesure {2020: 0.4342, 2021: 2.008, 2022: -1.759, 2023: 0.214, 2024: 0.5389, 2025: -1.546} ; seuil {sharpe_min: -1, positives_min: 4}
- C6 : ÉCHEC ; mesure 0.5536 ; seuil 0.45
- C7 : ÉCHEC ; mesure 0 ; seuil {part_voisins_min: 0.75, ratio: 0.6, sharpe_voisin_min: 0.5}
- C8 : ÉCHEC ; mesure 0.9954 ; seuil 0.05
- C9 : OK ; mesure 0 ; seuil {aleatoires: 20, fixes: 3, part_non_pleine_min: 0.4, tolerance: 1e-09}
- C11 : ÉCHEC ; mesure (-0.9648, -1.595) ; seuil (0.5, 0)
- C12 : ÉCHEC ; mesure (0.7972, 11.81) ; seuil (0.5, 15)
- C13 : ÉCHEC ; mesure (0.5696, -0.7714) ; seuil 0
- C14 : ÉCHEC ; mesure -0.00257 ; seuil 0.04
- C15 : ÉCHEC ; mesure None ; seuil (0, 0.585)
- C16 : ÉCHEC ; mesure None ; seuil 0.6
- C2 : ÉCHEC ; mesure 0.08691 ; seuil 0.5
- C3 : ÉCHEC ; mesure 0.202 ; seuil 2
- C4 : ÉCHEC ; mesure -0.2541 ; seuil 0
- C10 : ÉCHEC ; mesure 0.4001 ; seuil 0.05

### R0113 (f-rattrapage {h_jours: 14, theta: 1.1})
- C1 : ÉCHEC ; mesure 1.952e-05 ; seuil 0.95
- C5 : ÉCHEC ; mesure {2020: 0.1255, 2021: 1.723, 2022: -1.68, 2023: 0.5199, 2024: 1.278, 2025: -2.021} ; seuil {sharpe_min: -1, positives_min: 4}
- C6 : OK ; mesure 0.4036 ; seuil 0.45
- C7 : ÉCHEC ; mesure 0 ; seuil {part_voisins_min: 0.75, ratio: 0.6, sharpe_voisin_min: 0.5}
- C8 : ÉCHEC ; mesure 0.9944 ; seuil 0.05
- C9 : OK ; mesure 0 ; seuil {aleatoires: 20, fixes: 3, part_non_pleine_min: 0.4, tolerance: 1e-09}
- C11 : ÉCHEC ; mesure (-1.097, -1.765) ; seuil (0.5, 0)
- C12 : ÉCHEC ; mesure (2.625, 7.963) ; seuil (0.5, 15)
- C13 : ÉCHEC ; mesure (0.1243, -0.7394) ; seuil 0
- C14 : ÉCHEC ; mesure -0.0373 ; seuil 0.04
- C15 : ÉCHEC ; mesure None ; seuil (0, 0.585)
- C16 : ÉCHEC ; mesure None ; seuil 0.6
- C2 : ÉCHEC ; mesure -0.2281 ; seuil 0.5
- C3 : ÉCHEC ; mesure -0.5641 ; seuil 2
- C4 : ÉCHEC ; mesure -0.5951 ; seuil 0
- C10 : ÉCHEC ; mesure 0.7113 ; seuil 0.05

### R0114 (f-rattrapage {h_jours: 14, theta: 1.6})
- C1 : ÉCHEC ; mesure 1.284e-05 ; seuil 0.95
- C5 : ÉCHEC ; mesure {2020: -0.2544, 2021: 3.183, 2022: -1.742, 2023: 0.1256, 2024: 1.078, 2025: -2.142} ; seuil {sharpe_min: -1, positives_min: 4}
- C6 : OK ; mesure 0.2754 ; seuil 0.45
- C7 : ÉCHEC ; mesure 0 ; seuil {part_voisins_min: 0.75, ratio: 0.6, sharpe_voisin_min: 0.5}
- C8 : ÉCHEC ; mesure 0.9926 ; seuil 0.05
- C9 : OK ; mesure 0 ; seuil {aleatoires: 20, fixes: 3, part_non_pleine_min: 0.4, tolerance: 1e-09}
- C11 : ÉCHEC ; mesure (-1.354, -2.08) ; seuil (0.5, 0)
- C12 : ÉCHEC ; mesure (7.226, 4.299) ; seuil (0.5, 15)
- C13 : ÉCHEC ; mesure (0.1343, -0.912) ; seuil 0
- C14 : ÉCHEC ; mesure -0.02551 ; seuil 0.04
- C15 : ÉCHEC ; mesure None ; seuil (0, 0.585)
- C16 : ÉCHEC ; mesure None ; seuil 0.6
- C2 : ÉCHEC ; mesure -0.2618 ; seuil 0.5
- C3 : ÉCHEC ; mesure -0.6156 ; seuil 2
- C4 : ÉCHEC ; mesure -0.5652 ; seuil 0
- C10 : ÉCHEC ; mesure 0.7317 ; seuil 0.05

### R0115 (f-rattrapage {h_jours: 14, theta: 2.4})
- C1 : ÉCHEC ; mesure 7.094e-06 ; seuil 0.95
- C5 : ÉCHEC ; mesure {2020: -0.4997, 2021: 0.8859, 2022: -2.241, 2023: 0.7194, 2024: 0.2491, 2025: -0.5734} ; seuil {sharpe_min: -1, positives_min: 4}
- C6 : OK ; mesure 0.115 ; seuil 0.45
- C7 : ÉCHEC ; mesure None ; seuil {part_voisins_min: 0.75, ratio: 0.6, sharpe_voisin_min: 0.5}
- C8 : ÉCHEC ; mesure 0.99 ; seuil 0.05
- C9 : OK ; mesure 0 ; seuil {aleatoires: 20, fixes: 3, part_non_pleine_min: 0.4, tolerance: 1e-09}
- C11 : ÉCHEC ; mesure (-1.791, -2.366) ; seuil (0.5, 0)
- C12 : ÉCHEC ; mesure (inf, 0.8907) ; seuil (0.5, 15)
- C13 : ÉCHEC ; mesure (-0.3924, -0.1809) ; seuil 0
- C14 : ÉCHEC ; mesure -0.0109 ; seuil 0.04
- C15 : ÉCHEC ; mesure None ; seuil (0, 0.585)
- C16 : ÉCHEC ; mesure None ; seuil 0.6
- C2 : ÉCHEC ; mesure -0.3055 ; seuil 0.5
- C3 : ÉCHEC ; mesure -0.8201 ; seuil 2
- C4 : ÉCHEC ; mesure -0.4621 ; seuil 0
- C10 : ÉCHEC ; mesure 0.8012 ; seuil 0.05

### R0116 (f-rattrapage {h_jours: 20, theta: 0.5})
- C1 : ÉCHEC ; mesure 0.007726 ; seuil 0.95
- C5 : ÉCHEC ; mesure {2020: 0.8767, 2021: 2.022, 2022: -1.317, 2023: 1.503, 2024: 0.6626, 2025: -0.5019} ; seuil {sharpe_min: -1, positives_min: 4}
- C6 : OK ; mesure 0.3564 ; seuil 0.45
- C7 : ÉCHEC ; mesure None ; seuil {part_voisins_min: 0.75, ratio: 0.6, sharpe_voisin_min: 0.5}
- C8 : ÉCHEC ; mesure 0.9928 ; seuil 0.05
- C9 : OK ; mesure 0 ; seuil {aleatoires: 20, fixes: 3, part_non_pleine_min: 0.4, tolerance: 1e-09}
- C11 : ÉCHEC ; mesure (-0.5066, -1.131) ; seuil (0.5, 0)
- C12 : OK ; mesure (0.4058, 13.01) ; seuil (0.5, 15)
- C13 : ÉCHEC ; mesure (0.8614, -0.06956) ; seuil 0
- C14 : OK ; mesure 0.09153 ; seuil 0.04
- C15 : ÉCHEC ; mesure None ; seuil (0, 0.585)
- C16 : ÉCHEC ; mesure None ; seuil 0.6
- C2 : ÉCHEC ; mesure 0.4856 ; seuil 0.5
- C3 : ÉCHEC ; mesure 1.223 ; seuil 2
- C4 : OK ; mesure 0.1538 ; seuil 0
- C10 : ÉCHEC ; mesure 0.1126 ; seuil 0.05

### R0117 (f-rattrapage {h_jours: 20, theta: 0.75})
- C1 : ÉCHEC ; mesure 0.001215 ; seuil 0.95
- C5 : ÉCHEC ; mesure {2020: 0.8274, 2021: 1.536, 2022: -1.745, 2023: 1.332, 2024: 0.2961, 2025: -0.6382} ; seuil {sharpe_min: -1, positives_min: 4}
- C6 : OK ; mesure 0.3634 ; seuil 0.45
- C7 : ÉCHEC ; mesure None ; seuil {part_voisins_min: 0.75, ratio: 0.6, sharpe_voisin_min: 0.5}
- C8 : ÉCHEC ; mesure 0.9942 ; seuil 0.05
- C9 : OK ; mesure 0 ; seuil {aleatoires: 20, fixes: 3, part_non_pleine_min: 0.4, tolerance: 1e-09}
- C11 : ÉCHEC ; mesure (-0.8582, -1.498) ; seuil (0.5, 0)
- C12 : ÉCHEC ; mesure (0.5365, 9.694) ; seuil (0.5, 15)
- C13 : ÉCHEC ; mesure (0.5804, -0.2695) ; seuil 0
- C14 : ÉCHEC ; mesure 0.03102 ; seuil 0.04
- C15 : ÉCHEC ; mesure None ; seuil (0, 0.585)
- C16 : ÉCHEC ; mesure None ; seuil 0.6
- C2 : ÉCHEC ; mesure 0.2472 ; seuil 0.5
- C3 : ÉCHEC ; mesure 0.6619 ; seuil 2
- C4 : ÉCHEC ; mesure -0.03886 ; seuil 0
- C10 : ÉCHEC ; mesure 0.2422 ; seuil 0.05

### R0118 (f-rattrapage {h_jours: 20, theta: 1.1})
- C1 : ÉCHEC ; mesure 0.000765 ; seuil 0.95
- C5 : ÉCHEC ; mesure {2020: 0.2651, 2021: 1.686, 2022: -1.774, 2023: 0.9543, 2024: 1.511, 2025: -1.269} ; seuil {sharpe_min: -1, positives_min: 4}
- C6 : OK ; mesure 0.301 ; seuil 0.45
- C7 : ÉCHEC ; mesure None ; seuil {part_voisins_min: 0.75, ratio: 0.6, sharpe_voisin_min: 0.5}
- C8 : ÉCHEC ; mesure 0.993 ; seuil 0.05
- C9 : OK ; mesure 0 ; seuil {aleatoires: 20, fixes: 3, part_non_pleine_min: 0.4, tolerance: 1e-09}
- C11 : ÉCHEC ; mesure (-0.9964, -1.683) ; seuil (0.5, 0)
- C12 : ÉCHEC ; mesure (0.539, 6.921) ; seuil (0.5, 15)
- C13 : ÉCHEC ; mesure (0.4401, -0.1961) ; seuil 0
- C14 : ÉCHEC ; mesure 0.02213 ; seuil 0.04
- C15 : ÉCHEC ; mesure None ; seuil (0, 0.585)
- C16 : ÉCHEC ; mesure None ; seuil 0.6
- C2 : ÉCHEC ; mesure 0.209 ; seuil 0.5
- C3 : ÉCHEC ; mesure 0.5354 ; seuil 2
- C4 : ÉCHEC ; mesure -0.03533 ; seuil 0
- C10 : ÉCHEC ; mesure 0.2739 ; seuil 0.05

### R0119 (f-rattrapage {h_jours: 20, theta: 1.6})
- C1 : ÉCHEC ; mesure 0.0006873 ; seuil 0.95
- C5 : ÉCHEC ; mesure {2020: 0.5199, 2021: 2.347, 2022: -1.428, 2023: 0.8828, 2024: 0.8, 2025: -1.148} ; seuil {sharpe_min: -1, positives_min: 4}
- C6 : OK ; mesure 0.1889 ; seuil 0.45
- C7 : ÉCHEC ; mesure None ; seuil {part_voisins_min: 0.75, ratio: 0.6, sharpe_voisin_min: 0.5}
- C8 : ÉCHEC ; mesure 0.9898 ; seuil 0.05
- C9 : OK ; mesure 0 ; seuil {aleatoires: 20, fixes: 3, part_non_pleine_min: 0.4, tolerance: 1e-09}
- C11 : ÉCHEC ; mesure (-1.033, -1.797) ; seuil (0.5, 0)
- C12 : ÉCHEC ; mesure (0.6663, 3.618) ; seuil (0.5, 15)
- C13 : ÉCHEC ; mesure (0.439, -0.3259) ; seuil 0
- C14 : ÉCHEC ; mesure 0.007144 ; seuil 0.04
- C15 : ÉCHEC ; mesure None ; seuil (0, 0.585)
- C16 : ÉCHEC ; mesure None ; seuil 0.6
- C2 : ÉCHEC ; mesure 0.1254 ; seuil 0.5
- C3 : ÉCHEC ; mesure 0.3379 ; seuil 2
- C4 : ÉCHEC ; mesure -0.1247 ; seuil 0
- C10 : ÉCHEC ; mesure 0.3647 ; seuil 0.05

### R0120 (f-rattrapage {h_jours: 20, theta: 2.4})
- C1 : ÉCHEC ; mesure 5.781e-05 ; seuil 0.95
- C5 : ÉCHEC ; mesure {2020: 0.07483, 2021: 1.447, 2022: -1.414, 2023: 0.2091, 2024: -0.1084, 2025: -0.4215} ; seuil {sharpe_min: -1, positives_min: 4}
- C6 : OK ; mesure 0.0738 ; seuil 0.45
- C7 : ÉCHEC ; mesure None ; seuil {part_voisins_min: 0.75, ratio: 0.6, sharpe_voisin_min: 0.5}
- C8 : ÉCHEC ; mesure 0.9898 ; seuil 0.05
- C9 : OK ; mesure 0 ; seuil {aleatoires: 20, fixes: 3, part_non_pleine_min: 0.4, tolerance: 1e-09}
- C11 : ÉCHEC ; mesure (-1.54, -2.306) ; seuil (0.5, 0)
- C12 : ÉCHEC ; mesure (inf, 0.6682) ; seuil (0.5, 15)
- C13 : ÉCHEC ; mesure (0.0878, -0.7175) ; seuil 0
- C14 : ÉCHEC ; mesure -0.004709 ; seuil 0.04
- C15 : ÉCHEC ; mesure None ; seuil (0, 0.585)
- C16 : ÉCHEC ; mesure None ; seuil 0.6
- C2 : ÉCHEC ; mesure -0.1268 ; seuil 0.5
- C3 : ÉCHEC ; mesure -0.3742 ; seuil 2
- C4 : ÉCHEC ; mesure -0.2479 ; seuil 0
- C10 : ÉCHEC ; mesure 0.6593 ; seuil 0.05

## Sélection

Aucun candidat : issue B si aucune autre vague n'est décidée.
