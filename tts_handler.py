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
        
        # Voice settings for different languages
        self.voice_settings = {
            'hindi': {
                'model_name': 'tts_models/hi/male/tacotron2-DDC',
                'speaker': None,
                'language': 'hi'
            },
            'english': {
                'model_name': 'tts_models/en/ljspeech/tacotron2-DDC',
                'speaker': None,
                'language': 'en'
            },
            'hinglish': {
                'model_name': 'tts_models/en/ljspeech/tacotron2-DDC',  # Use English model for Hinglish
                'speaker': None,
                'language': 'en'
            }
        }
    
    def _load_tts_models(self):
        """Load TTS models for different languages"""
        try:
            # Load English model (most reliable)
            logger.info("Loading English TTS model...")
            self.tts_models['english'] = TTS(
                model_name="tts_models/en/ljspeech/tacotron2-DDC",
                progress_bar=False
            ).to(self.device)
            
            # Try to load Hindi model
            try:
                logger.info("Loading Hindi TTS model...")
                self.tts_models['hindi'] = TTS(
                    model_name="tts_models/hi/male/tacotron2-DDC",
                    progress_bar=False
                ).to(self.device)
            except Exception as e:
                logger.warning(f"Hindi TTS model not available, will use English: {e}")
                self.tts_models['hindi'] = self.tts_models['english']
            
            # Use English model for Hinglish
            self.tts_models['hinglish'] = self.tts_models['english']
            
            logger.info("TTS models loaded successfully")
            
        except Exception as e:
            logger.error(f"Error loading TTS models: {e}")
            # Fallback: try to load any available model
            try:
                logger.info("Loading fallback TTS model...")
                fallback_model = TTS(TTS.list_models()[0]).to(self.device)
                self.tts_models['english'] = fallback_model
                self.tts_models['hindi'] = fallback_model
                self.tts_models['hinglish'] = fallback_model
            except Exception as e2:
                logger.error(f"Failed to load any TTS model: {e2}")
                self.tts_models = {}
    
    async def generate_voice_note(self, text: str, language: str = 'english') -> Optional[str]:
        """Generate voice note from text"""
        if not self.tts_models:
            logger.error("No TTS models available")
            return None
        
        try:
            # Clean and prepare text
            clean_text = self._prepare_text_for_tts(text, language)
            
            if not clean_text:
                return None
            
            # Get appropriate model
            model = self.tts_models.get(language, self.tts_models.get('english'))
            if not model:
                logger.error(f"No TTS model available for language: {language}")
                return None
            
            # Generate audio
            output_path = await self._generate_audio(model, clean_text, language)
            
            return output_path
            
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
        """Generate audio file from text using TTS model"""
        try:
            # Create temporary file for output
            temp_dir = tempfile.gettempdir()
            output_filename = f"voice_note_{random.randint(1000, 9999)}.wav"
            output_path = os.path.join(temp_dir, output_filename)
            
            # Generate speech
            model.tts_to_file(text=text, file_path=output_path)
            
            # Convert to OGG format for Telegram (if needed)
            ogg_path = output_path.replace('.wav', '.ogg')
            await self._convert_to_ogg(output_path, ogg_path)
            
            # Clean up WAV file
            if os.path.exists(output_path):
                os.remove(output_path)
            
            return ogg_path if os.path.exists(ogg_path) else output_path
            
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