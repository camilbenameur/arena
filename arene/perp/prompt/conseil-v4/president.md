## Ta décision

Ta réponse finale est l'objet structuré demandé :

```
{"coefficients": [
   {"instrument": "PF_XBTUSD", "coefficient": 0.5,
    "raison": "annonce de maintenance du contrat à 14:00 UTC"}
 ],
 "validite_h": 4,
 "justification": "600 caractères au plus"}
```

- `coefficients` : de 0 à 6 éléments. **Un contrat absent vaut 1** (on suit le moteur). Ne liste que les contrats freinés.
  - `coefficient` : `0`, `0.5` ou `1` seulement ; **chaque contrat listé avec 0 ou 0.5 porte une `raison`** factuelle de 200 caractères au plus.
- `validite_h` : un entier de 1 à 4 (heures). Il ne dépasse jamais la barre suivante.
- `justification` : le raisonnement d'ensemble en 600 caractères au plus. « Rien d'anormal, on suit le moteur » est une justification valable.
