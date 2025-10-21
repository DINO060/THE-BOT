#!/usr/bin/env python3
"""
🤖 Test Simple du Bot Telegram
================================
Ce fichier permet de tester le bot sans toutes les dépendances complexes.
"""

import os
import sys
import logging
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

# Configuration logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# === CONFIGURATION ===
# METTEZ VOTRE TOKEN ICI OU DANS .env
BOT_TOKEN = "7742864469:AAGPsoiKg2mRYY0O7-TMAFA2bHJ3_686hBQ"  # <-- Collez votre token ici

# Charger depuis .env si disponible
try:
    from dotenv import load_dotenv
    load_dotenv()
    if not BOT_TOKEN:
        BOT_TOKEN = os.getenv("BOT_TOKEN", "")
except ImportError:
    logger.warning("python-dotenv non installé. Utilisez le token hardcodé.")

# Vérifier le token
if not BOT_TOKEN:
    print("\n" + "="*60)
    print("❌ ERREUR: BOT_TOKEN manquant!")
    print("="*60)
    print("\n📝 COMMENT OBTENIR UN TOKEN:\n")
    print("1. Ouvrez Telegram")
    print("2. Cherchez @BotFather")
    print("3. Envoyez /newbot")
    print("4. Suivez les instructions")
    print("5. Copiez le token reçu")
    print("6. Collez-le ligne 18 de ce fichier")
    print("\n" + "="*60 + "\n")
    sys.exit(1)

# === COMMANDES DU BOT ===

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Commande /start"""
    user = update.effective_user
    welcome_message = f"""
👋 <b>Bienvenue {user.first_name}!</b>

Je suis un bot de téléchargement de médias.

📥 <b>Ce que je peux faire:</b>
• Télécharger des vidéos YouTube
• Télécharger depuis Instagram
• Télécharger depuis TikTok

<b>Comment m'utiliser:</b>
Envoyez-moi simplement une URL!

<b>Exemple:</b>
<code>https://youtube.com/watch?v=dQw4w9WgXcQ</code>

💡 Commandes:
/start - Ce message
/help - Aide détaillée
/status - Voir votre quota
"""
    
    await update.message.reply_text(welcome_message, parse_mode='HTML')
    logger.info(f"User {user.id} started the bot")

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Commande /help"""
    help_text = """
📚 <b>AIDE - Bot de Téléchargement</b>

<b>Sites supportés:</b>
• YouTube (vidéos et playlists)
• Instagram (posts, stories, reels)
• TikTok (vidéos)
• Twitter/X
• Facebook
• Reddit

<b>Formats disponibles:</b>
• Vidéo: MP4, WEBM
• Audio: MP3, M4A
• Documents: PDF (manga)

<b>Limites:</b>
• Taille max: 50 MB
• Quota gratuit: 5 téléchargements/jour

<b>Commandes:</b>
/start - Menu principal
/help - Cette aide
/status - Voir votre quota
/premium - Passer en Premium

<b>Besoin d'aide?</b>
Contactez le support: @votre_username
"""
    
    await update.message.reply_text(help_text, parse_mode='HTML')

async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Commande /status"""
    user = update.effective_user
    
    status_text = f"""
📊 <b>Votre Statut</b>

👤 Utilisateur: {user.first_name}
🆔 ID: {user.id}
⭐ Plan: Gratuit
📥 Téléchargements aujourd'hui: 0/5
🔄 Réinitialisation: 24 heures

💡 <b>Astuce:</b>
Passez en Premium pour des téléchargements illimités!
/premium
"""
    
    await update.message.reply_text(status_text, parse_mode='HTML')

async def handle_url(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Gérer les URLs"""
    url = update.message.text
    user = update.effective_user
    
    logger.info(f"User {user.id} sent URL: {url}")
    
    # Vérifier si c'est une URL
    if not url.startswith(('http://', 'https://')):
        await update.message.reply_text(
            "❌ Veuillez envoyer une URL valide\n"
            "Elle doit commencer par http:// ou https://"
        )
        return
    
    # Détecter le type d'URL
    if "youtube.com" in url or "youtu.be" in url:
        await handle_youtube(update, url)
    elif "instagram.com" in url:
        await handle_instagram(update, url)
    elif "tiktok.com" in url:
        await handle_tiktok(update, url)
    else:
        await update.message.reply_text(
            "⚠️ <b>URL non supportée pour l'instant</b>\n\n"
            "Sites supportés:\n"
            "• YouTube\n"
            "• Instagram\n"
            "• TikTok\n\n"
            "Plus de sites bientôt disponibles!",
            parse_mode='HTML'
        )

async def handle_youtube(update: Update, url: str):
    """Traiter une URL YouTube"""
    msg = await update.message.reply_text("🎥 <b>YouTube détecté!</b>\n\n⏳ Analyse en cours...", parse_mode='HTML')
    
    try:
        # Import yt-dlp
        import yt_dlp
        
        # Récupérer les infos
        ydl_opts = {'quiet': True, 'no_warnings': True}
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            title = info.get('title', 'Vidéo')
            duration = info.get('duration', 0)
            
            await msg.edit_text(
                f"✅ <b>Vidéo trouvée!</b>\n\n"
                f"📹 Titre: {title[:50]}...\n"
                f"⏱ Durée: {duration // 60}:{duration % 60:02d}\n\n"
                f"💡 <b>Pour télécharger:</b>\n"
                f"Le téléchargement réel nécessite le bot complet.\n"
                f"Lancez: <code>python main.py</code>",
                parse_mode='HTML'
            )
    except ImportError:
        await msg.edit_text(
            "⚠️ <b>yt-dlp non installé</b>\n\n"
            "Pour activer le téléchargement:\n"
            "<code>pip install yt-dlp</code>",
            parse_mode='HTML'
        )
    except Exception as e:
        await msg.edit_text(f"❌ Erreur: {str(e)[:100]}")

async def handle_instagram(update: Update, url: str):
    """Traiter une URL Instagram"""
    await update.message.reply_text(
        "📸 <b>Instagram détecté!</b>\n\n"
        "⚠️ Mode démo\n\n"
        "Pour télécharger réellement:\n"
        "Lancez le bot complet avec <code>python main.py</code>",
        parse_mode='HTML'
    )

async def handle_tiktok(update: Update, url: str):
    """Traiter une URL TikTok"""
    await update.message.reply_text(
        "🎵 <b>TikTok détecté!</b>\n\n"
        "⚠️ Mode démo\n\n"
        "Pour télécharger réellement:\n"
        "Lancez le bot complet avec <code>python main.py</code>",
        parse_mode='HTML'
    )

async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Gérer les erreurs"""
    logger.error(f"Update {update} caused error {context.error}")
    
    if update and update.effective_message:
        await update.effective_message.reply_text(
            "❌ Une erreur est survenue.\n"
            "Veuillez réessayer."
        )

def main():
    """Fonction principale"""
    print("\n" + "="*60)
    print("🚀 DÉMARRAGE DU BOT TELEGRAM")
    print("="*60)
    print(f"\n📝 Token: {BOT_TOKEN[:15]}...{BOT_TOKEN[-5:]}")
    print("\n⏳ Connexion en cours...\n")
    
    # Créer l'application
    app = Application.builder().token(BOT_TOKEN).build()
    
    # Ajouter les handlers
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("status", status_command))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_url))
    
    # Handler d'erreur
    app.add_error_handler(error_handler)
    
    print("✅ Bot connecté avec succès!")
    print("\n📱 INSTRUCTIONS:")
    print("1. Ouvrez Telegram")
    print("2. Cherchez votre bot")
    print("3. Envoyez /start")
    print("4. Testez avec une URL YouTube!")
    print("\n⏸️  Appuyez sur Ctrl+C pour arrêter")
    print("\n" + "="*60 + "\n")
    
    # Lancer le bot
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
