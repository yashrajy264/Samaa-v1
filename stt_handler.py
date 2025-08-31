import os
import logging
import asyncio
import tempfile
from typing import Optional
import whisper
import torch

logger = logging.getLogger(__name__)

class STTHandler:
    def __init__(self):
        self.device = "cuda" if torch.cuda.is_available() else "cpu"
        self.model = None
        self._load_whisper_model()
    
    def _load_whisper_model(self):
        """Load Whisper model for speech recognition"""
        try:
            # Try to load a smaller model first for faster processing
            model_size = "base"  # Options: tiny, base, small, medium, large
            
            logger.info(f"Loading Whisper {model_size} model...")
            self.model = whisper.load_model(model_size, device=self.device)
            logger.info("Whisper model loaded successfully")
            
        except Exception as e:
            logger.error(f"Error loading Whisper model: {e}")
            try:
                # Fallback to tiny model
                logger.info("Trying to load tiny Whisper model as fallback...")
                self.model = whisper.load_model("tiny", device=self.device)
                logger.info("Fallback Whisper model loaded")
            except Exception as e2:
                logger.error(f"Failed to load any Whisper model: {e2}")
                self.model = None
    
    async def transcribe_audio(self, audio_path: str, language: str = None) -> Optional[str]:
        """Transcribe audio file to text"""
        if not self.model:
            logger.error("Whisper model not available")
            return None
        
        if not os.path.exists(audio_path):
            logger.error(f"Audio file not found: {audio_path}")
            return None
        
        try:
            # Convert audio format if needed
            processed_audio_path = await self._prepare_audio_for_whisper(audio_path)
            
            # Transcribe audio
            logger.info(f"Transcribing audio: {processed_audio_path}")
            
            # Set language for better accuracy
            language_code = self._get_whisper_language_code(language) if language else None
            
            result = self.model.transcribe(
                processed_audio_path,
                language=language_code,
                task="transcribe",
                fp16=False  # Use fp32 for better compatibility
            )
            
            transcribed_text = result["text"].strip()
            
            # Clean up temporary file if created
            if processed_audio_path != audio_path and os.path.exists(processed_audio_path):
                os.remove(processed_audio_path)
            
            logger.info(f"Transcription successful: {transcribed_text[:100]}...")
            return transcribed_text
            
        except Exception as e:
            logger.error(f"Error transcribing audio: {e}")
            return None
    
    async def _prepare_audio_for_whisper(self, audio_path: str) -> str:
        """Prepare audio file for Whisper processing"""
        try:
            # Check if file is already in a supported format
            supported_formats = ['.wav', '.mp3', '.m4a', '.flac']
            file_ext = os.path.splitext(audio_path)[1].lower()
            
            if file_ext in supported_formats:
                return audio_path
            
            # Convert to WAV format using ffmpeg
            temp_dir = tempfile.gettempdir()
            output_path = os.path.join(temp_dir, f"whisper_input_{os.getpid()}.wav")
            
            cmd = [
                'ffmpeg', '-i', audio_path,
                '-ar', '16000',  # Whisper prefers 16kHz
                '-ac', '1',      # Mono
                '-c:a', 'pcm_s16le',
                '-y',            # Overwrite output
                output_path
            ]
            
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            
            stdout, stderr = await process.communicate()
            
            if process.returncode == 0 and os.path.exists(output_path):
                return output_path
            else:
                logger.warning(f"Audio conversion failed: {stderr.decode()}")
                return audio_path  # Return original if conversion fails
                
        except Exception as e:
            logger.warning(f"Could not prepare audio (ffmpeg not available?): {e}")
            return audio_path
    
    def _get_whisper_language_code(self, language: str) -> Optional[str]:
        """Convert our language codes to Whisper language codes"""
        language_map = {
            'hindi': 'hi',
            'english': 'en',
            'hinglish': 'en'  # Use English for Hinglish
        }
        
        return language_map.get(language)
    
    async def detect_language(self, audio_path: str) -> Optional[str]:
        """Detect the language of the audio"""
        if not self.model:
            return None
        
        try:
            # Load audio and detect language
            audio = whisper.load_audio(audio_path)
            audio = whisper.pad_or_trim(audio)
            
            # Make log-Mel spectrogram and move to the same device as the model
            mel = whisper.log_mel_spectrogram(audio).to(self.model.device)
            
            # Detect the spoken language
            _, probs = self.model.detect_language(mel)
            detected_language = max(probs, key=probs.get)
            
            logger.info(f"Detected language: {detected_language} (confidence: {probs[detected_language]:.2f})")
            
            # Map back to our language codes
            reverse_map = {'hi': 'hindi', 'en': 'english'}
            return reverse_map.get(detected_language, 'english')
            
        except Exception as e:
            logger.error(f"Error detecting language: {e}")
            return None
    
    def is_available(self) -> bool:
        """Check if STT is available"""
        return self.model is not None