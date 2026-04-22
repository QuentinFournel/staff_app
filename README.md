# ⚽ Club — Séances & Questionnaires

Application Streamlit pour gérer les séances d'entraînement et les questionnaires post-séance d'un club de football.

- **Staff** : crée les séances, convoque les joueurs, gère les statuts, joint des PDF, crée les questionnaires et consulte les réponses.
- **Joueur** : consulte uniquement les séances auxquelles il est convoqué et remplit ses questionnaires.

> L'inscription en libre-service n'existe pas. Les comptes sont définis dans les **secrets Streamlit** par le staff, qui transmet ensuite les identifiants aux joueurs.

---

## Arborescence

```
football_app/
├── app.py                    # Point d'entrée Streamlit + navigation
├── auth.py                   # Connexion via st.secrets
├── database.py               # Fonctions SQLite (CRUD)
├── ui_sessions.py            # Interfaces séances (calendrier mensuel)
├── ui_questionnaires.py      # Interfaces questionnaires (sliders masqués)
├── requirements.txt
├── README.md
├── .gitignore
├── .streamlit/
│   └── secrets.toml.example  # Modèle de configuration des utilisateurs
└── data/
    ├── football.db           # Base SQLite (créée automatiquement)
    └── pdfs/                 # PDF joints aux séances
```

---

## 1. Lancer en local

```bash
# Cloner
git clone <ton-repo>
cd football_app

# Environnement virtuel
python -m venv .venv
source .venv/bin/activate        # Mac/Linux
# .venv\Scripts\activate         # Windows

# Dépendances
pip install -r requirements.txt

# Configuration des utilisateurs
cp .streamlit/secrets.toml.example .streamlit/secrets.toml
# -> édite .streamlit/secrets.toml avec les vrais identifiants

# Lancement
streamlit run app.py
```

L'application s'ouvre sur http://localhost:8501.

---

## 2. Déployer sur Streamlit Community Cloud

### Étape 1 — Publier le code sur GitHub

1. Crée un repo GitHub (public ou privé, les deux fonctionnent avec Streamlit Cloud).
2. Pousse le contenu du dossier `football_app/`.
3. Vérifie bien que `.streamlit/secrets.toml` **n'est PAS commit** (le `.gitignore` s'en occupe).

### Étape 2 — Créer l'app sur share.streamlit.io

1. Va sur [share.streamlit.io](https://share.streamlit.io) et connecte ton compte GitHub.
2. "New app" → sélectionne ton repo, la branche `main`, et `app.py` comme point d'entrée.
3. Avant de "Deploy", clique sur **"Advanced settings"** → **"Secrets"** et colle le contenu de ton `secrets.toml`. Exemple :

   ```toml
   [users.amaennel]
   password  = "motdepasse_antoine"
   role      = "staff"
   full_name = "Antoine Maennel"

   [users.jsmith]
   password  = "motdepasse_jonas"
   role      = "joueur"
   full_name = "Jonas Smith"
   ```
4. Déploie. L'URL publique sera du type `https://<slug>.streamlit.app`.

### Étape 3 — Ajouter / modifier des utilisateurs

- Soit tu modifies **Settings → Secrets** dans l'interface Streamlit Cloud (l'app redémarre automatiquement et l'utilisateur est créé au prochain démarrage).
- Soit tu fais la même chose en local dans `.streamlit/secrets.toml`.

Le nom de la section (après `users.`) EST le nom d'utilisateur que la personne saisira pour se connecter. Les rôles autorisés sont `staff` et `joueur`. Les noms d'utilisateur doivent être écrits en **minuscules**.

---

## 3. ⚠️ Persistance des données sur Streamlit Cloud

Streamlit Community Cloud utilise un système de fichiers **éphémère** : à chaque redémarrage, mise à jour ou push sur GitHub, le conteneur est recréé depuis zéro. Cela signifie que :

- ✅ Les **utilisateurs** sont conservés (ils proviennent des secrets, resynchronisés à chaque démarrage).
- ❌ Les **séances, convocations, PDF et réponses** stockés dans `data/football.db` et `data/pdfs/` sont **perdus** à chaque redémarrage.

Pour un usage réel en club, tu dois brancher une base de données externe. Trois options simples :

| Solution    | Type       | Tier gratuit | Complexité |
|-------------|------------|--------------|------------|
| Supabase    | PostgreSQL | Oui          | Facile     |
| Neon        | PostgreSQL | Oui          | Facile     |
| Turso       | SQLite edge| Oui          | Très facile|

La migration consiste à remplacer le contenu de `database.py` pour pointer vers une URL de connexion externe (stockée dans les secrets elle aussi). Le reste de l'app n'a pas à être modifié.

Tant que tu n'as pas migré : l'app est **parfaite pour tester**, mais considère les données comme temporaires.

---

## 4. Rappels fonctionnels

- **Calendrier mensuel** (streamlit-calendar) avec couleurs par jour relatif (J-1, J-2…), navigation prev/next/aujourd'hui, vues mois/semaine/liste.
- **Ballons animés** à la création d'une séance, d'un questionnaire, et à l'envoi des réponses joueur.
- **Slider 0-100 "aveugle"** : le joueur déplace un curseur de 0 à 100 (pas de 1), sans voir le chiffre. 👎 à gauche, 👍 à droite. La valeur stockée est bien un entier 0-100 pour l'analyse.
- **Ajout PDF via formulaire** : l'upload ne se déclenche qu'au clic sur "Ajouter le PDF", plus de boucle d'ajout.

---

## 5. Points d'amélioration possibles

- Migration vers Postgres / Supabase pour la persistance réelle.
- Hash des mots de passe (bcrypt / argon2) au lieu d'un stockage en clair dans les secrets.
- Export CSV / Excel des réponses aux questionnaires.
- Graphiques d'évolution par joueur (ressenti, sommeil, intensité).
- Notifications (email, push) au joueur à la création d'une séance.
- Verrouillage des questionnaires après une échéance.
