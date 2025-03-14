import yt_dlp as youtube_dl
from moviepy.editor import *
import speech_recognition as sr
import os
import re
import time
from pydub import AudioSegment
import google.generativeai as genai
from dotenv import load_dotenv

# Carga las variables de entorno desde el archivo .env
load_dotenv()

# Obtiene la clave de la API de Gemini desde las variables de entorno
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
if not GEMINI_API_KEY:
    raise ValueError("La variable de entorno GEMINI_API_KEY no está configurada.")

# Configura la API de Gemini con la clave obtenida
genai.configure(api_key=GEMINI_API_KEY)

# Obtiene la ruta de ffmpeg desde las variables de entorno
FFMPEG_PATH = os.getenv("FFMPEG_PATH")
if not FFMPEG_PATH:
    raise ValueError("La variable de entorno FFMPEG_PATH no está configurada.")

def limpiar_nombre_archivo(nombre):
    """
    Limpia el nombre del archivo eliminando caracteres especiales que pueden causar problemas en el sistema de archivos.
    """
    nombre_limpio = re.sub(r'[<>:"/\\|?*\u2600-\u27BF\uD800-\uDBFF\uDC00-\uDFFF｜？]', '', nombre)  # Eliminación exhaustiva de caracteres problemáticos
    nombre_limpio = nombre_limpio.strip()  # Elimina espacios en blanco al inicio y al final
    return nombre_limpio

def descargar_video(url, ruta_destino="."):
    """
    Descarga un video desde una URL de YouTube utilizando yt-dlp.

    Primero obtiene el título del video para limpiar el nombre del archivo antes de la descarga.
    """
    try:
        # Opciones iniciales para obtener el título y simular la descarga
        ydl_opts = {
            'noplaylist': True,  # Maneja solo videos individuales, evita problemas con listas de reproducción.
            'quiet': True,  # Reduce la salida en consola.
            'no_warnings': True,  # Desactiva las advertencias.
            'simulate': True,  # Simula la descarga para obtener información sin descargar.
            'writesubtitles': False,  # No descarga subtítulos en este paso.
            'allsubtitles': False,  # No considera todos los subtítulos.
            'subtitleslangs': ['en'],  # Solo considera subtítulos en inglés (puede ser ajustado).
            'outtmpl': os.path.join(ruta_destino, '%(title)s.%(ext)s'),  # Define la plantilla para el nombre del archivo de salida.
        }

        with youtube_dl.YoutubeDL(ydl_opts) as ydl:
            info_dict = ydl.extract_info(url, download=False)  # Obtiene información del video sin descargarlo.
            video_titulo = info_dict.get('title', None)  # Extrae el título del video.
            video_titulo_limpio = limpiar_nombre_archivo(video_titulo)  # Limpia el título para usarlo en el nombre del archivo.
            video_extension = "mp4"  # Fuerza la extensión a mp4 después de la extracción de información.
            video_ruta = os.path.join(ruta_destino, f'{video_titulo_limpio}.{video_extension}')  # Construye la ruta completa del archivo.

        # Opciones para la descarga real del video
        ydl_opts = {
            'outtmpl': video_ruta,  # Usa el título limpio para el nombre del archivo de salida.
            'format': 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/mp4',  # Selecciona el mejor formato de video y audio en mp4.
            'verbose': True,  # Aumenta la salida en consola para mostrar detalles de la descarga.
            'ffmpeg_location': FFMPEG_PATH,  # Especifica la ubicación de ffmpeg.
        }

        with youtube_dl.YoutubeDL(ydl_opts) as ydl:
            ydl.download([url])  # Descarga el video con las opciones configuradas.
            return video_ruta  # Devuelve la ruta al archivo descargado.

    except Exception as e:
        print(f"Error al descargar el video: {e}")
        return None

def convertir_video_a_audio(ruta_video, ruta_destino="."):
    """
    Convierte un archivo de video a un archivo de audio en formato WAV.
    """
    try:
        ruta_video = os.path.abspath(ruta_video)  # Obtiene la ruta absoluta del archivo de video.
        video = VideoFileClip(ruta_video)  # Carga el archivo de video.
        audio_ruta = os.path.join(ruta_destino, os.path.splitext(os.path.basename(ruta_video))[0] + ".wav")  # Construye la ruta para el archivo de audio de salida.
        video.audio.write_audiofile(audio_ruta)  # Extrae el audio del video y lo guarda como un archivo WAV.
        video.close()  # Cierra el archivo de video.
        return audio_ruta  # Devuelve la ruta al archivo de audio.
    except Exception as e:
        print(f"Error al convertir el video a audio: {e}")
        print(f"Video file path: {ruta_video}")
        return None

def segmentar_audio(ruta_audio, duracion_segmento=30 * 1000):
    """
    Segmenta un archivo de audio en fragmentos más pequeños de la duración especificada (en milisegundos).
    """
    audio = AudioSegment.from_wav(ruta_audio)  # Carga el archivo de audio.
    longitud_total = len(audio)  # Obtiene la duración total del audio.
    segmentos = []  # Inicializa una lista para almacenar los segmentos de audio.
    inicio = 0  # Establece el punto de inicio del primer segmento.
    while inicio < longitud_total:  # Itera mientras el punto de inicio sea menor que la duración total.
        fin = inicio + duracion_segmento  # Calcula el punto final del segmento actual.
        segmento = audio[inicio:fin]  # Extrae el segmento de audio.
        segmentos.append(segmento)  # Agrega el segmento a la lista.
        inicio = fin  # Actualiza el punto de inicio para el siguiente segmento.
    return segmentos  # Devuelve la lista de segmentos de audio.

def transcribir_segmentos(segmentos, ruta_destino="."):
    """
    Transcribe una lista de segmentos de audio utilizando el reconocimiento de voz de Google.

    Guarda cada segmento como un archivo WAV temporal, lo transcribe y luego lo elimina.
    """
    transcripciones = []  # Inicializa una lista para almacenar las transcripciones.
    reconocedor = sr.Recognizer()  # Crea una instancia del reconocedor de voz.
    for i, segmento in enumerate(segmentos):  # Itera a través de cada segmento de audio.
        ruta_segmento = os.path.join(ruta_destino, f"segmento_{i}.wav")  # Construye la ruta para el archivo temporal del segmento.
        segmento.export(ruta_segmento, format="wav")  # Exporta el segmento a un archivo WAV.
        with sr.AudioFile(ruta_segmento) as fuente:  # Abre el archivo de audio como fuente para el reconocimiento.
            audio_data = reconocedor.record(fuente)  # Registra los datos de audio desde la fuente.
            try:
                texto = reconocedor.recognize_google(audio_data, language="es-ES")  # Intenta reconocer el texto en español.
                transcripciones.append(texto)  # Agrega el texto reconocido a la lista de transcripciones.
            except sr.UnknownValueError:
                print(f"No se pudo reconocer el segmento {i}.")
                transcripciones.append("[Segmento no reconocido]")  # Agrega un mensaje si no se pudo reconocer el segmento.
            except sr.RequestError as e:
                print(f"Error al reconocer el segmento {i}: {e}")
                transcripciones.append(f"[Error: {e}]")  # Agrega un mensaje de error si hubo un problema con la solicitud.
        os.remove(ruta_segmento)  # Elimina el archivo temporal del segmento.
    return transcripciones  # Devuelve la lista de transcripciones.

def analizar_y_mejorar_texto(texto):
    """
    Analiza, corrige y resume el texto utilizando la API de Gemini, generando resultados en formato Markdown.
    """
    model = genai.GenerativeModel('gemini-2.0-flash')  # Inicializa el modelo de Gemini.
    prompt = f"""
    Actúa como un analista de contenido experto y editor de textos especializado en programación, ciberseguridad y hacking ético.

    1.  Analiza el siguiente texto transcrito.
    2.  Corrige errores gramaticales, mejora la claridad y el orden de las oraciones.
    3.  Identifica los puntos clave o temas principales discutidos en el texto.
    4.  Cuando se mencione código (Linux, Windows, etc.), genera ejemplos en formato de bloque de código Markdown con explicación.
    5.  Cuando sea posible, proporciona ejemplos concretos extraídos del texto para ilustrar cada punto clave.
    6.  Escribe un resumen del texto como si narraras una experiencia. No añadas comentarios finales.

    Genera el resultado en formato Markdown (.md) con la siguiente estructura:

    # Resumen de la Experiencia

    [Aquí va el resumen narrativo]

    ## Puntos Clave

    -   **Tema 1:** [Descripción del tema]. Ejemplo: "[Cita del texto]".

        ```[lenguaje]
        [Código de ejemplo]
        ```

        Explicación del código: [Explicación del comando o código].

    -   **Tema 2:** [Descripción del tema]. Ejemplo: "[Cita del texto]".
    ... (continúa para cada tema)

    Texto:
    {texto}

    Resultado en Markdown:
    """
    response = model.generate_content(prompt)  # Envía la solicitud al modelo de Gemini.
    return response.text  # Devuelve el texto resultante en formato Markdown.

def generar_ejemplos_codigo(texto):
    """
    Analiza el texto y extrae ejemplos de código (Linux, Windows, etc.), generando explicaciones detalladas.
    """
    model = genai.GenerativeModel('gemini-2.0-flash')
    prompt = f"""
    Actúa como un experto en ciberseguridad y programación.

    Analiza el siguiente texto y extrae cualquier ejemplo de código, comandos de terminal (Linux, Windows, etc.) o instrucciones técnicas relacionadas con programación, ciberseguridad o hacking ético.

    Para cada ejemplo encontrado, proporciona:

    1.  El código o comando en formato de bloque de código Markdown, indicando el lenguaje si es aplicable.
    2.  Una explicación detallada de lo que hace el código o comando, incluyendo su propósito, sintaxis y cómo se utiliza.
    3.  Advertencias o precauciones importantes al usar el código.

    Si no encuentras ejemplos relevantes, indica claramente que no se encontraron ejemplos de código o comandos en el texto.

    Texto:
    {texto}

    Análisis y ejemplos de código:
    """
    response = model.generate_content(prompt)
    return response.text

def generar_documento_texto(texto, ruta_destino, add_attribution=True):
    """
    Genera un documento de texto con la transcripción y, opcionalmente, agrega la atribución al final.
    """
    attribution = "\n\n" + "Este programa fue creado por s4mma3l. GitHub: https://github.com/S4mma3l"  # Define el texto de atribución.
    try:
        with open(ruta_destino, "w", encoding="utf-8") as archivo:  # Abre el archivo en modo escritura con codificación UTF-8.
            archivo.write(texto)  # Escribe el texto en el archivo.
            if add_attribution:
                archivo.write(attribution)  # Agrega la atribución si se especifica.
        print(f"Transcripción guardada en: {ruta_destino}")  # Imprime un mensaje indicando que la transcripción se guardó correctamente.
    except Exception as e:
        print(f"Error al generar el documento de texto: {e}")  # Imprime un mensaje de error si hubo un problema al generar el documento.

def main():
    """
    Función principal para coordinar la descarga, conversión, transcripción y análisis de videos.
    """
    url_video = input("Ingresa la URL del video de YouTube: ")  # Solicita al usuario que ingrese la URL del video.

    ruta_video = descargar_video(url_video)  # Descarga el video y obtiene la ruta al archivo.

    if ruta_video:  # Verifica si la descarga del video fue exitosa.
        if not os.path.exists(ruta_video):  # Verifica si el archivo de video existe.
            print(f"Video file not found: {ruta_video}")  # Imprime un mensaje si el archivo no se encuentra.
            return  # Sale de la función si el archivo no se encuentra.

        # Extrae el título del video para usarlo en los nombres de los archivos
        video_titulo_sin_extension = os.path.splitext(os.path.basename(ruta_video))[0]
        ruta_archivo_texto = f"{video_titulo_sin_extension}_transcripcion.txt"  # Define la ruta para el archivo de transcripción.
        ruta_archivo_md = f"{video_titulo_sin_extension}_analisis.md"  # Define la ruta para el archivo de análisis en Markdown.
        ruta_ejemplos_md = f"{video_titulo_sin_extension}_ejemplos.md" # Define la ruta para el archivo de ejemplos de código en Markdown

        ruta_audio = convertir_video_a_audio(ruta_video)  # Convierte el video a audio.

        if ruta_audio:  # Verifica si la conversión a audio fue exitosa.
            segmentos = segmentar_audio(ruta_audio)  # Segmenta el archivo de audio.
            transcripciones = transcribir_segmentos(segmentos)  # Transcribe los segmentos de audio.
            texto_completo = " ".join(transcripciones)  # Une todas las transcripciones en un solo texto.

            # Genera los documentos
            texto_mejorado = analizar_y_mejorar_texto(texto_completo)  # Analiza y mejora el texto, generando el resultado en Markdown.
            ejemplos_codigo = generar_ejemplos_codigo(texto_completo)  # Extrae ejemplos de código del texto.

            generar_documento_texto(texto_mejorado, ruta_archivo_md, add_attribution=True)  # Genera el archivo de análisis en Markdown con atribución.
            generar_documento_texto(ejemplos_codigo, ruta_ejemplos_md, add_attribution=True)  # Genera el archivo de ejemplos de código en Markdown con atribución
            generar_documento_texto(texto_completo, ruta_archivo_texto, add_attribution=True) # creates a text document

            try:
                os.remove(ruta_audio)  # Elimina el archivo de audio temporal.
            except Exception as e:
                print(f"Error removing audio file: {e}")  # Imprime un mensaje de error si no se pudo eliminar el archivo de audio.
        else:
            print("Audio conversion failed. Skipping remaining steps.")  # Imprime un mensaje si la conversión a audio falló.

        try:
            os.remove(ruta_video)  # Elimina el archivo de video.
        except Exception as e:
            print(f"Error removing video file: {e}")  # Imprime un mensaje de error si no se pudo eliminar el archivo de video.
    else:
        print("Video download failed. Exiting.")  # Imprime un mensaje si la descarga del video falló.

# Llama a la función principal para iniciar el proceso
main()