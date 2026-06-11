# Prépa Classique Ressources

Site statique en français pour afficher des ressources de prépa depuis des fichiers JSON locaux.

## Structure

```txt
prepa-ressources-site/
├── index.html
├── folders.html
├── files.html
├── websites.html
├── downloadAll.html
├── collaborate.html
├── about.html
├── 404.html
├── style.css
├── script.js
├── data/
│   ├── folders.json
│   ├── files.json
│   └── websites.json
├── netlify.toml
├── vercel.json
└── README.md
```

## Lancer en local

Il ne faut pas ouvrir `index.html` directement avec `file://`, car JavaScript utilise `fetch()` pour lire les JSON.

```bash
python -m http.server 3000
```

Puis ouvrir :

```txt
http://localhost:3000
```

## Déploiement GitHub Pages

1. Créer un repository GitHub.
2. Mettre tous les fichiers du dossier à la racine du repository.
3. Aller dans `Settings` → `Pages`.
4. Choisir la branche `main` et le dossier `/root`.
5. Ouvrir le lien généré par GitHub Pages.

## Déploiement Netlify

1. Importer le repository sur Netlify.
2. Build command : laisser vide.
3. Publish directory : `.`
4. Déployer.

## Déploiement Vercel

1. Importer le repository sur Vercel.
2. Framework preset : `Other`.
3. Build command : laisser vide.
4. Output directory : `.`
5. Déployer.

## Modifier les données

Les cartes sont générées depuis :

- `data/folders.json`
- `data/files.json`
- `data/websites.json`

Après modification d’un JSON, il suffit de redéployer le site.
