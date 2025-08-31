import os
import logging
import asyncio
from typing import Optional
import torch
from TTS.api import TTS
import tempfile
import random

logger = logging.getLogger(__name__)

class TTSHandler:
    def __init__(self):
        self.device = "cuda" if torch.cuda.is_available() else "cpu"
        self.tts_models = {}
        self._load_tts_models()
        
        # Indian accent reference audio files (you'll need to add these)
        self.indian_voice_samples = {
            'english': '/path/to/indian_english_voice.wav',  # Add Indian English speaker sample
            'hindi': '/path/to/indian_hindi_voice.wav',     # Add Indian Hindi speaker sample
            'hinglish': '/path/to/indian_hinglish_voice.wav' # Add Indian Hinglish speaker sample
        }
        
        # Voice settings for different languages with Indian accent
        self.voice_settings = {
            'hindi': {
                'model_name': 'tts_models/multilingual/multi-dataset/xtts_v2',
                'speaker_wav': self.indian_voice_samples.get('hindi'),
                'language': 'hi'
            },
            'english': {
                'model_name': 'tts_models/multilingual/multi-dataset/xtts_v2',
                'speaker_wav': self.indian_voice_samples.get('english'),
                'language': 'en'
            },
            'hinglish': {
                'model_name': 'tts_models/multilingual/multi-dataset/xtts_v2',
                'speaker_wav': self.indian_voice_samples.get('hinglish'),
                'language': 'en'  # Use English for Hinglish with Indian accent
            }
        }
    
    def _load_tts_models(self):
        """Load XTTS-v2 model for voice cloning with Indian accent"""
        try:
            # Load XTTS-v2 model (supports voice cloning and multiple languages)
            logger.info("Loading XTTS-v2 model for Indian accent voice cloning...")
            xtts_model = TTS(
                model_name="tts_models/multilingual/multi-dataset/xtts_v2",
                progress_bar=False
            ).to(self.device)
            
            # Use the same model for all languages (voice cloning will handle accents)
            self.tts_models['english'] = xtts_model
            self.tts_models['hindi'] = xtts_model
            self.tts_models['hinglish'] = xtts_model
            
            logger.info("XTTS-v2 model loaded successfully for Indian accent synthesis")
            
        except Exception as e:
            logger.error(f"Error loading XTTS-v2 model: {e}")
            # Fallback to basic models if XTTS-v2 fails
            try:
                logger.info("Loading fallback TTS models...")
                fallback_model = TTS("tts_models/en/ljspeech/tacotron2-DDC").to(self.device)
                self.tts_models['english'] = fallback_model
                self.tts_models['hindi'] = fallback_model
                self.tts_models['hinglish'] = fallback_model
            except Exception as e2:
                logger.error(f"Failed to load any TTS model: {e2}")
                self.tts_models = {}
    
    async def generate_voice_note(self, text: str, language: str = 'english', max_duration: int = 30) -> str:
        """Generate voice note with Indian accent using voice cloning"""
        try:
            # Truncate text to fit approximately 30 seconds (about 200-250 words)
            words = text.split()
            if len(words) > 200:  # Approximate 30-second limit
                text = ' '.join(words[:200]) + "... and that's your news update!"
            
            # Clean and prepare text for TTS
            clean_text = self._prepare_text_for_tts(text, language)
            
            # Get the appropriate TTS model
            if language not in self.tts_models:
                language = 'english'  # Fallback to English
            
            model = self.tts_models[language]
            
            # Generate voice file with Indian accent
            voice_path = await self._generate_audio(model, clean_text, language)
            return voice_path
            
        except Exception as e:
            logger.error(f"Error generating voice note: {e}")
            return None
    
    def _prepare_text_for_tts(self, text: str, language: str) -> str:
        """Prepare text for TTS conversion"""
        # Remove markdown formatting
        import re
        clean_text = re.sub(r'\*\*(.*?)\*\*', r'\1', text)  # Remove bold
        clean_text = re.sub(r'\*(.*?)\*', r'\1', clean_text)  # Remove italic
        clean_text = re.sub(r'`(.*?)`', r'\1', clean_text)  # Remove code formatting
        clean_text = re.sub(r'#{1,6}\s*', '', clean_text)  # Remove headers
        
        # Remove URLs
        clean_text = re.sub(r'http\S+|www\S+', '', clean_text)
        
        # Remove excessive whitespace
        clean_text = re.sub(r'\s+', ' ', clean_text).strip()
        
        # Handle emojis - remove them for better TTS
        clean_text = re.sub(r'[^\w\s\.,!?;:\-\(\)]+', '', clean_text)
        
        # Limit length for TTS (most models have limits)
        if len(clean_text) > 500:
            sentences = clean_text.split('.')
            clean_text = '. '.join(sentences[:3]) + '.'
        
        # Add pauses for better speech
        clean_text = clean_text.replace('.', '. ')
        clean_text = clean_text.replace(',', ', ')
        clean_text = clean_text.replace('!', '! ')
        clean_text = clean_text.replace('?', '? ')
        
        # Language-specific adjustments
        if language == 'hinglish':
            # Convert some Hindi words to phonetic English for better pronunciation
            replacements = {
                'bhai': 'bye',
                'aaj': 'aaj',
                'kya': 'kya',
                'hai': 'hai',
                'hua': 'hua',
                'yaar': 'yaar'
            }
            for hindi, phonetic in replacements.items():
                clean_text = clean_text.replace(hindi, phonetic)
        
        return clean_text
    
    async def _generate_audio(self, model, text: str, language: str) -> str:
        """Generate audio with Indian accent using voice cloning"""
        try:
            # Create temporary file for output
            with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp_file:
                wav_path = tmp_file.name
            
            # Get voice settings for the language
            voice_config = self.voice_settings.get(language, self.voice_settings['english'])
            speaker_wav = voice_config.get('speaker_wav')
            target_language = voice_config.get('language', 'en')
            
            # Generate speech with Indian accent voice cloning
            if speaker_wav and os.path.exists(speaker_wav):
                # Use voice cloning with Indian accent reference
                model.tts_to_file(
                    text=text,
                    file_path=wav_path,
                    speaker_wav=speaker_wav,
                    language=target_language,
                    split_sentences=True  # Better for longer texts
                )
                logger.info(f"Generated audio with Indian accent voice cloning: {language}")
            else:
                # Fallback to default model without voice cloning
                logger.warning(f"Indian voice sample not found for {language}, using default")
                model.tts_to_file(text=text, file_path=wav_path)
            
            # Convert to OGG format for Telegram
            ogg_path = wav_path.replace('.wav', '.ogg')
            success = await self._convert_to_ogg(wav_path, ogg_path)
            
            # Clean up WAV file
            if os.path.exists(wav_path):
                os.remove(wav_path)
            
            return ogg_path if success else None
            
        except Exception as e:
            logger.error(f"Error generating audio: {e}")
            return None
    
    async def _convert_to_ogg(self, input_path: str, output_path: str) -> bool:
        """Convert audio file to OGG format for Telegram"""
        try:
            # Try using ffmpeg if available
            import subprocess
            
            cmd = [
                'ffmpeg', '-i', input_path, 
                '-c:a', 'libopus', 
                '-b:a', '64k',
                '-y',  # Overwrite output file
                output_path
            ]
            
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            
            stdout, stderr = await process.communicate()
            
            if process.returncode == 0:
                return True
            else:
                logger.warning(f"FFmpeg conversion failed: {stderr.decode()}")
                return False
                
        except Exception as e:
            logger.warning(f"Could not convert to OGG (ffmpeg not available?): {e}")
            # If conversion fails, just use the original file
            try:
                import shutil
                shutil.copy2(input_path, output_path)
                return True
            except:
                return False
    
    def get_available_languages(self) -> list:
        """Get list of available TTS languages"""
        return list(self.tts_models.keys())
    
    def is_language_supported(self, language: str) -> bool:
        """Check if a language is supported"""
        return language in self.tts_models