# utils/word_filter.py
import json
import logging
import os
from typing import List, Set

logger = logging.getLogger(__name__)

class WordFilter:
    def __init__(self, filter_file: str = "data/bad_words.json"):
        self.filter_file = filter_file
        self.bad_words: Set[str] = set()
        self.load_words()

    def load_words(self) -> None:
        """Load bad words from JSON file"""
        try:
            if os.path.exists(self.filter_file):
                with open(self.filter_file, 'r', encoding='utf-8') as f:
                    self.bad_words = set(json.load(f))
            else:
                self.bad_words = set()
                logger.info("Initialising empty word filter at %s", self.filter_file)
                self.save_words()
        except Exception:
            logger.exception("Failed to load word filter from %s", self.filter_file)
            self.bad_words = set()

    def save_words(self) -> None:
        """Save bad words to JSON file"""
        try:
            dirpath = os.path.dirname(self.filter_file)
            if dirpath:
                os.makedirs(dirpath, exist_ok=True)
            with open(self.filter_file, 'w', encoding='utf-8') as f:
                json.dump(sorted(self.bad_words), f, indent=4)
        except Exception:
            logger.exception("Failed to save word filter to %s", self.filter_file)

    def add_word(self, word: str) -> bool:
        """Add a new word to the filter"""
        word = word.lower()
        if word not in self.bad_words:
            self.bad_words.add(word)
            self.save_words()
            return True
        return False

    def remove_word(self, word: str) -> bool:
        """Remove a word from the filter"""
        word = word.lower()
        if word in self.bad_words:
            self.bad_words.remove(word)
            self.save_words()
            return True
        return False

    def check_message(self, message: str) -> List[str]:
        """Check a message for bad words and return list of found words"""
        message = message.lower()
        words = message.split()
        found_words = []
        for word in words:
            if word in self.bad_words:
                found_words.append(word)
        return found_words
