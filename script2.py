import yt_dlp as youtube_dl
from moviepy.editor import *
import speech_recognition as sr
import os
import re
import time
from pydub import AudioSegment
import google.generativeai as genai
from dotenv import load_dotenv

load_dotenv() # Carga las variables desde el archivo .env
# Obtiene la clave de API de Gemini desde las variables de entorno.
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
if not GEMINI_API_KEY:
    raise ValueError("La variable de entorno GEMINI_API_KEY no está configurada.")
genai.configure(api_key=GEMINI_API_KEY)

# Obtiene la ruta de ffmpeg desde las variables de entorno.
FFMPEG_PATH = os.getenv("FFMPEG_PATH")
if not FFMPEG_PATH:
    raise ValueError("La variable de entorno FFMPEG_PATH no está configurada.")

def limpiar_nombre_archivo(nombre):
    """Limpia el nombre del archivo eliminando caracteres especiales."""
    nombre_limpio = re.sub(r'[<>:"/\\|?*]', '', nombre)
    return nombre_limpio

def descargar_video(url, ruta_destino="."):
    """Descarga un video desde una URL."""
    try:
        ydl_opts = {
            'outtmpl': os.path.join(ruta_destino, '%(title)s.%(ext)s'),
            'format': 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/mp4',
            'verbose': True,
            'ffmpeg_location': FFMPEG_PATH,
        }
        with youtube_dl.YoutubeDL(ydl_opts) as ydl:
            info_dict = ydl.extract_info(url, download=True)
            video_titulo = info_dict.get('title', None)
            video_extension = info_dict.get('ext', None)
            video_titulo_limpio = limpiar_nombre_archivo(video_titulo)
            video_ruta = os.path.join(ruta_destino, f'{video_titulo_limpio}.{video_extension}')
            ydl_opts['outtmpl'] = video_ruta
            with youtube_dl.YoutubeDL(ydl_opts) as ydl_2:
                info_dict_2 = ydl_2.extract_info(url, download=True)
            return video_ruta
    except Exception as e:
        print(f"Error al descargar el video: {e}")
        return None

def convertir_video_a_audio(ruta_video, ruta_destino="."):
    """Convierte un video a un archivo de audio WAV."""
    try:
        video = VideoFileClip(ruta_video)
        audio_ruta = os.path.join(ruta_destino, os.path.splitext(os.path.basename(ruta_video))[0] + ".wav")
        video.audio.write_audiofile(audio_ruta)
        video.close()
        return audio_ruta
    except Exception as e:
        print(f"Error al convertir el video a audio: {e}")
        return None

def segmentar_audio(ruta_audio, duracion_segmento=30 * 1000):
    """Segmenta un archivo de audio en fragmentos más pequeños."""
    audio = AudioSegment.from_wav(ruta_audio)
    longitud_total = len(audio)
    segmentos = []
    inicio = 0
    while inicio < longitud_total:
        fin = inicio + duracion_segmento
        segmento = audio[inicio:fin]
        segmentos.append(segmento)
        inicio = fin
    return segmentos

def transcribir_segmentos(segmentos, ruta_destino="."):
    """Transcribe una lista de segmentos de audio."""
    transcripciones = []
    reconocedor = sr.Recognizer()
    for i, segmento in enumerate(segmentos):
        ruta_segmento = os.path.join(ruta_destino, f"segmento_{i}.wav")
        segmento.export(ruta_segmento, format="wav")
        with sr.AudioFile(ruta_segmento) as fuente:
            audio_data = reconocedor.record(fuente)
            try:
                texto = reconocedor.recognize_google(audio_data, language="es-ES")
                transcripciones.append(texto)
            except sr.UnknownValueError:
                print(f"No se pudo reconocer el segmento {i}.")
                transcripciones.append("[Segmento no reconocido]")
            except sr.RequestError as e:
                print(f"Error al reconocer el segmento {i}: {e}")
                transcripciones.append(f"[Error: {e}]")
        os.remove(ruta_segmento)
    return transcripciones

def analizar_y_mejorar_texto(texto):
    """Analiza y mejora el texto usando la API de Gemini."""
    model = genai.GenerativeModel('gemini-pro')
    prompt = f"""
    Eres un filólogo experto. Analiza el siguiente texto transcrito, corrige errores gramaticales, mejora la claridad y el orden de las oraciones, y dale un formato adecuado para un texto bien presentado.
    Luego, genera un resumen conciso del texto.

    Texto:
    {texto}

    Mejora y resumen:
    """
    response = model.generate_content(prompt)
    return response.text

def generar_documento_texto(texto, ruta_destino):
    """Genera un documento de texto con la transcripción."""
    try:
        with open(ruta_destino, "w", encoding="utf-8") as archivo:
            archivo.write(texto)
        print(f"Transcripción guardada en: {ruta_destino}")
    except Exception as e:
        print(f"Error al generar el documento de texto: {e}")

def main(url_video, ruta_archivo_texto):
    ruta_video = descargar_video(url_video)
    if ruta_video:
        ruta_audio = convertir_video_a_audio(ruta_video)
        if ruta_audio:
            segmentos = segmentar_audio(ruta_audio)
            transcripciones = transcribir_segmentos(segmentos)
            texto_completo = " ".join(transcripciones)
            texto_mejorado = analizar_y_mejorar_texto(texto_completo)
            generar_documento_texto(texto_mejorado, ruta_archivo_texto)
            os.remove(ruta_audio)
        time.sleep(2)
        os.remove(ruta_video)

# Ejemplo de uso:
url_video = "https://www.youtube.com/watch?v=603QJryefFg"
ruta_archivo_texto = "transcripcion_mejorada.txt"

main(url_video, ruta_archivo_texto)