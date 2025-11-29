from langchain_core.tools import tool
from google import genai
from google.genai import types
from dotenv import load_dotenv
import os

load_dotenv()

@tool
def transcribe_audio(audio_file_path: str) -> str:
    """
    Transcribe an audio file (opus, mp3, wav, etc.) to text using Google's Gemini API.
    
    Args:
        audio_file_path (str): Path to the audio file to transcribe (relative or absolute).
        
    Returns:
        str: The transcribed text from the audio file.
    """
    try:
        api_key = os.getenv("GOOGLE_API_KEY")
        if not api_key:
            return "Error: GOOGLE_API_KEY not found in environment variables"
            
        client = genai.Client(api_key=api_key)
        
        # Read the audio file
        if not os.path.isabs(audio_file_path):
            # If relative path, try with LLMFiles directory
            if not os.path.exists(audio_file_path):
                audio_file_path = os.path.join("LLMFiles", audio_file_path)
        
        if not os.path.exists(audio_file_path):
            return f"Error: Audio file not found at {audio_file_path}"
        
        print(f"Uploading audio file: {audio_file_path}")
        
        # Upload the audio file using the File API
        uploaded_file = client.files.upload(file=audio_file_path)
        
        print(f"File uploaded: {uploaded_file.name}, URI: {uploaded_file.uri}")
        
        # Use Gemini to transcribe
        response = client.models.generate_content(
            model='gemini-2.5-flash',
            contents=[
                "Transcribe this audio file. Return ONLY the exact transcription, nothing else.",
                types.Part(file_data=types.FileData(file_uri=uploaded_file.uri, mime_type=uploaded_file.mime_type))
            ]
        )
        
        # Clean up the uploaded file
        try:
            client.files.delete(name=uploaded_file.name)
        except:
            pass  # Ignore cleanup errors
        
        transcription = response.text.strip()
        print(f"Transcribed audio: {transcription}")
        return transcription
        
    except Exception as e:
        import traceback
        error_details = traceback.format_exc()
        print(f"Error transcribing audio: {error_details}")
        return f"Error transcribing audio: {str(e)}"
