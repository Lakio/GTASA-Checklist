# GTA SA Checklist

Checklist du 100 % de GTA San Andreas (PC) avec une carte interactive. Elle lit la progression directement dans le jeu.

## Lancer

Double-clique sur **`Lancer.bat`**. Au premier lancement, l'environnement Python est créé et les dépendances sont installées. Python 3.10 ou plus récent est requis.

Tu peux aussi lancer à la main :

```
.venv\Scripts\python.exe main.py
```

## Ce que fait l'appli

- **Checklist** : missions principales (Los Santos jusqu'à End of the Line), missions de véhicule, missions d'actifs, courses, stades et défis, écoles, Ammu-Nation et salles de sport, export/import, collectibles, planques. Une catégorie « bonus » regroupe ce qui ne compte pas pour le 100 % (sauts uniques, copines, etc.).
- **Détection automatique** : chaque élément est coché d'après les données du jeu (colonne « Détecté par » = `jeu`). Tu peux cocher ou décocher à la main (`manuel`). Clic droit pour revenir à la détection automatique.
- **Carte** : construite à partir des tuiles radar de ton `gta3.img`. Elle affiche :
  - les 50 photos, 50 fers à cheval et 50 huîtres, positions extraites de ton `main.scm` ;
  - les 100 tags (positions relevées dans la mémoire du jeu au premier lancement) ;
  - les 70 sauts uniques ;
  - les contacts de mission (positions approximatives) ;
  - la position de CJ en direct.

  Les éléments terminés apparaissent en gris (option pour les masquer). Molette pour zoomer, glisser pour se déplacer, clic sur un élément de la liste pour le situer.

## D'où viennent les données

1. **Jeu lancé** : lecture en direct de la mémoire de `gta_sa.exe`, en lecture seule, mise à jour chaque seconde. Les adresses de la version 1.0 sont connues. Pour les autres versions (Steam, Rockstar Games Launcher), l'appli retrouve les structures en balayant la mémoire, puis les mémorise.
2. **Jeu fermé** : lecture de la sauvegarde la plus récente (`Documents\GTA San Andreas User Files\GTASAsfN.b`), rechargée dès qu'elle change. Menu *Fichier → Ouvrir une sauvegarde…* pour en choisir une autre.

*Outils → Diagnostic* affiche ce qui a été trouvé (adresses, compteurs de missions). C'est utile si un élément n'est pas détecté.

## Fichiers

Les données de l'appli sont dans `%APPDATA%\GTASA_Checklist` :

| Fichier | Contenu |
|---|---|
| `progress.json` | tes coches manuelles |
| `settings.json` | réglages (dossier du jeu, filtres, calques) |
| `radar_map.png`, `collectibles.json` | générés à partir des fichiers du jeu |
| `tags.json` | positions des tags relevées en jeu |
| `addresses.json` | adresses mémoire trouvées pour ta version du jeu |


## Sources

- Variables globales du script : noms de [Sanny Builder](https://github.com/sannybuilder/data) et correspondance compteurs → missions de l'autosplitter [LiveSplit GTASA de tduva](https://github.com/tduva/LiveSplit-ASL).
- Structures du jeu : [gta-reversed](https://github.com/gta-reversed/gta-reversed).
- Format des sauvegardes : [GTAMods Wiki](https://gtamods.com/wiki/Saves_(GTA_SA)).
- Liste du 100 % : [GTA Wiki](https://gta.fandom.com/wiki/100%25_Completion_in_GTA_San_Andreas).
