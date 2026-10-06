import os
from dotenv import load_dotenv
from google import genai

def audit_authorized_models() -> None:
    """
    Script de auditoría SRE: Interroga la API de Google para descubrir
    los modelos fundacionales explícitamente autorizados para la credencial actual.
    """
    load_dotenv(override=True)
    api_key = os.environ.get("AI_API_KEY")
    
    if not api_key:
        print("[ERROR] Credencial AI_API_KEY no encontrada en .env")
        return

    print("Iniciando auditoría de infraestructura en Google Cloud...")
    print(f"Token detectado: {api_key[:10]}... (Truncado por seguridad)")
    
    try:
        # Inicialización del cliente moderno
        client = genai.Client(api_key=api_key)
        
        print("\n--- Catálogo de Modelos Autorizados ---")
        authorized_count = 0
        
        # Petición GET al endpoint /models
        for model in client.models.list():
            # Filtramos solo los modelos que soportan generación de contenido
            if 'generateContent' in model.supported_generation_methods:
                print(f"✅ Habilitado: {model.name}")
                authorized_count += 1
                
        print(f"\nAuditoría finalizada. Total de modelos soportados: {authorized_count}")

    except Exception as exc:
        print(f"\n[CRÍTICO] Fallo en la interrogación de la API: {exc}")

if __name__ == "__main__":
    audit_authorized_models()