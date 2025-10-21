# 🚀 QUICK START - Lancement Rapide du Bot

## ⚡ LANCEMENT EN 3 MINUTES

### 1️⃣ Configurer le Bot Token

Vous avez déjà un fichier `.env` avec vos clés générées ! Il manque juste votre BOT_TOKEN.

**Obtenir un token:**
```
1. Ouvrez Telegram
2. Cherchez @BotFather
3. Envoyez /newbot
4. Suivez les instructions
5. Copiez le token
```

**Ajoutez-le dans `.env`:**
```env
BOT_TOKEN=7123456789:AAHdqTcvCH1vGWJxfSeofSAs0K5PALDsaw
```

✅ **Vos clés de sécurité sont déjà générées !**
```
ENCRYPTION_KEY=11aWTul7uADgFtrFNOigLTcuy2sqwHxwontTiV8ZbE8=
JWT_SECRET_KEY=FPhDmfQOm2ukhC0w9OIVmRBQ0bKAm8hh1MvV8GNRbh8
```

### 2️⃣ Installer les Dépendances Minimales

```bash
# Installer python-telegram-bot et yt-dlp
pip install python-telegram-bot python-dotenv yt-dlp
```

### 3️⃣ Lancer le Bot

**Option A: Bot de test simple (RECOMMANDÉ pour débuter)**
```bash
python test_bot_simple.py
```

**Option B: Bot complet**
```bash
python main.py
```

## 📱 Tester le Bot

1. Ouvrez Telegram
2. Cherchez votre bot (le username que vous avez choisi)
3. Envoyez `/start`
4. Testez avec une URL YouTube:
   ```
   https://youtube.com/watch?v=dQw4w9WgXcQ
   ```

## 🎯 Fonctionnalités du Bot de Test

### ✅ Ce qui fonctionne MAINTENANT:
- ✅ Commande /start avec menu complet
- ✅ Commande /help avec documentation
- ✅ Commande /status pour voir les quotas
- ✅ Détection d'URLs (YouTube, Instagram, TikTok)
- ✅ Extraction d'infos vidéo YouTube (avec yt-dlp)

### 🔧 Pour activer le téléchargement complet:
```bash
# Installer toutes les dépendances
pip install -r requirements.txt

# Lancer le bot complet
python main.py
```

## 📊 Configuration Actuelle

Votre fichier `.env` est configuré avec :

| Paramètre | Valeur | Status |
|-----------|--------|--------|
| BOT_TOKEN | À configurer | ⚠️ Requis |
| ENCRYPTION_KEY | ✅ Généré | ✅ Prêt |
| JWT_SECRET_KEY | ✅ Généré | ✅ Prêt |
| DATABASE_URL | SQLite local | ✅ Prêt |
| REDIS | Désactivé | ✅ OK pour test |
| MONITORING | Désactivé | ✅ OK pour test |

## 🐛 Résolution Rapide

### Erreur: "BOT_TOKEN not found"
→ Éditez le fichier `.env` et ajoutez votre token ligne 4

### Erreur: "No module named 'telegram'"
→ `pip install python-telegram-bot`

### Erreur: "yt-dlp not found"
→ `pip install yt-dlp`

### Le bot ne répond pas
→ Vérifiez que le token est correct
→ Vérifiez votre connexion internet
→ Regardez les logs dans la console

## 📁 Fichiers Importants

- **`test_bot_simple.py`** - Bot de test simple (270 lignes)
- **`main.py`** - Bot complet avec toutes les fonctionnalités
- **`.env`** - Configuration (BOT_TOKEN requis)
- **`manga_plugin_code.txt`** - Code du plugin manga (à installer)
- **`TODO_FINAL.md`** - Checklist complète
- **`LAUNCH_INSTRUCTIONS.md`** - Guide détaillé

## 🎯 Prochaines Étapes

1. **✅ Testez avec `test_bot_simple.py`**
2. Une fois fonctionnel, installez toutes les dépendances
3. Lancez le bot complet avec `main.py`
4. Ajoutez le plugin manga si besoin

## 💡 Astuces

- **Pour le téléchargement vidéo:** Installez FFmpeg
- **Pour les mangas PDF:** Installez `playwright` et `img2pdf`
- **Pour Redis:** Changez `ENABLE_CACHE=true` dans `.env`
- **Pour production:** Utilisez Docker avec `docker-compose up`

---

**Votre bot est prêt à être lancé ! 🚀**

Tapez simplement:
```bash
python test_bot_simple.py
```
