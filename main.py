# ==================== main.py ====================
"""Main entry point for the bot"""

import asyncio
import logging
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent))

from src.api.bot import ProductionBot
from src.core.config import settings
from src.core.monitoring import monitoring

# Configure logging
logging.basicConfig(
    level=getattr(logging, settings.log_level),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('bot.log')
    ]
)

logger = logging.getLogger(__name__)


async def main():
    """Main function to run the bot"""
    logger.info(f"Starting bot in {settings.environment} mode")
    
    # Create and run bot
    bot = ProductionBot()
    
    try:
        await bot.run()
    except KeyboardInterrupt:
        logger.info("Bot stopped by user")
    except Exception as e:
        logger.error(f"Bot crashed: {e}")
        monitoring.track_error(e, {"context": "main"})
        raise
    finally:
        logger.info("Bot shutdown complete")


if __name__ == "__main__":
    asyncio.run(main())