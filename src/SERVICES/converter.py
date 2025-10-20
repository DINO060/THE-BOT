# ==================== src/services/converter.py ====================
"""Media conversion service"""

import os
import asyncio
import subprocess
from typing import Optional, Dict, Any
from pathlib import Path

from src.core.monitoring import monitoring, metrics
from src.core.exceptions import ConversionError


class ConverterService:
    """Service for converting media files"""
    
    def __init__(self):
        self.ffmpeg_path = self._find_ffmpeg()
        
    def _find_ffmpeg(self) -> str:
        """Find FFmpeg executable"""
        for path in ['/usr/bin/ffmpeg', '/usr/local/bin/ffmpeg', 'ffmpeg']:
            if os.path.exists(path) or subprocess.run(['which', path], capture_output=True).returncode == 0:
                return path
        raise ConversionError("FFmpeg not found")
    
    async def convert_to_audio(
        self,
        input_path: str,
        output_path: str,
        format: str = "mp3",
        bitrate: str = "192k"
    ) -> bool:
        """Convert video to audio"""
        try:
            cmd = [
                self.ffmpeg_path,
                '-i', input_path,
                '-vn',  # No video
                '-acodec', 'libmp3lame' if format == 'mp3' else format,
                '-b:a', bitrate,
                '-y',  # Overwrite output
                output_path
            ]
            
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            
            stdout, stderr = await process.communicate()
            
            if process.returncode != 0:
                raise ConversionError(f"FFmpeg failed: {stderr.decode()}")
            
            metrics.downloads_total.labels(
                media_type='audio_conversion',
                status='success'
            ).inc()
            
            return True
            
        except Exception as e:
            monitoring.track_error(e, {
                'input': input_path,
                'output': output_path,
                'format': format
            })
            raise ConversionError(f"Conversion failed: {e}")
    
    async def compress_video(
        self,
        input_path: str,
        output_path: str,
        target_size_mb: int = None,
        quality: str = "medium"
    ) -> bool:
        """Compress video file"""
        quality_presets = {
            "low": {"crf": 28, "preset": "faster"},
            "medium": {"crf": 23, "preset": "medium"},
            "high": {"crf": 18, "preset": "slow"}
        }
        
        preset = quality_presets.get(quality, quality_presets["medium"])
        
        try:
            cmd = [
                self.ffmpeg_path,
                '-i', input_path,
                '-c:v', 'libx264',
                '-crf', str(preset['crf']),
                '-preset', preset['preset'],
                '-c:a', 'aac',
                '-b:a', '128k',
                '-movflags', '+faststart',
                '-y',
                output_path
            ]
            
            # Add size constraint if specified
            if target_size_mb:
                # Calculate bitrate for target size
                duration = await self._get_duration(input_path)
                if duration:
                    target_bitrate = (target_size_mb * 8192) / duration
                    cmd.extend(['-b:v', f'{int(target_bitrate)}k'])
            
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            
            stdout, stderr = await process.communicate()
            
            if process.returncode != 0:
                raise ConversionError(f"Compression failed: {stderr.decode()}")
            
            return True
            
        except Exception as e:
            monitoring.track_error(e, {
                'input': input_path,
                'quality': quality,
                'target_size': target_size_mb
            })
            raise
    
    async def _get_duration(self, file_path: str) -> Optional[float]:
        """Get media duration in seconds"""
        try:
            cmd = [
                'ffprobe',
                '-v', 'error',
                '-select_streams', 'v:0',
                '-show_entries', 'stream=duration',
                '-of', 'default=noprint_wrappers=1:nokey=1',
                file_path
            ]
            
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            
            stdout, _ = await process.communicate()
            
            if process.returncode == 0 and stdout:
                return float(stdout.decode().strip())
            
            return None
            
        except Exception:
            return None
    
    async def extract_thumbnail(
        self,
        video_path: str,
        output_path: str,
        timestamp: str = "00:00:01"
    ) -> bool:
        """Extract thumbnail from video"""
        try:
            cmd = [
                self.ffmpeg_path,
                '-i', video_path,
                '-ss', timestamp,
                '-vframes', '1',
                '-q:v', '2',
                '-y',
                output_path
            ]
            
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            
            await process.communicate()
            
            return process.returncode == 0
            
        except Exception as e:
            monitoring.track_error(e, {'video': video_path})
            return False
