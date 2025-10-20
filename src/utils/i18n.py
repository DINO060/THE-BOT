# ==================== src/utils/i18n.py ====================
"""Internationalization support"""

import json
from pathlib import Path
from typing import Dict, Any, Optional


class I18n:
    """Multi-language support"""
    
    def __init__(self, locales_dir: str = "locales"):
        self.locales_dir = Path(locales_dir)
        self.translations: Dict[str, Dict[str, str]] = {}
        self.default_language = "en"
        self._load_translations()
    
    def _load_translations(self):
        """Load all translation files"""
        for lang_dir in self.locales_dir.glob("*/"):
            if lang_dir.is_dir():
                lang_code = lang_dir.name
                self.translations[lang_code] = {}
                
                # Load all JSON files in language directory
                for json_file in lang_dir.glob("*.json"):
                    with open(json_file, "r", encoding="utf-8") as f:
                        data = json.load(f)
                        self.translations[lang_code].update(data)
    
    def get(self, language: str, key: str, **kwargs) -> str:
        """Get translated string"""
        # Fallback to default language if not available
        if language not in self.translations:
            language = self.default_language
        
        # Get translation
        translation = self.translations.get(language, {}).get(key)
        
        if not translation:
            # Fallback to default language
            translation = self.translations.get(self.default_language, {}).get(key)
        
        if not translation:
            # Return key if no translation found
            return key
        
        # Format with provided arguments
        try:
            return translation.format(**kwargs)
        except KeyError:
            return translation
    
    def add_language(self, language: str, translations: Dict[str, str]):
        """Add or update language translations"""
        if language not in self.translations:
            self.translations[language] = {}
        self.translations[language].update(translations)
    
    def get_available_languages(self) -> List[str]:
        """Get list of available languages"""
        return list(self.translations.keys())
    
    def set_default_language(self, language: str):
        """Set default language"""
        if language in self.translations:
            self.default_language = language

