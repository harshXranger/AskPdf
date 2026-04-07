def generate_answer_with_ollama(question: str, context: str) -> str:
#     url = f"{OLLAMA_API_URL}/api/generate"
    
#     We limit context to 2000 characters to prevent memory overflow (500 error)
#     safe_context = context[-2000:] if context else "No context available."

#     payload = {
#         "model": "llama3.2:1b",  # Using the lighter model for stability
#         "prompt": f"Context: {safe_context}\n\nQuestion: {question}\n\nAnswer concisely:",
#         "stream": False,
#         "options": {
#             "num_ctx": 2048, # Smaller context window = less RAM used
#             "temperature": 0.2
#         }
#     }

#     try:
#         Increase timeout to 120 because local LLMs take time to 'wake up'
#         response = requests.post(url, json=payload, timeout=120)
        
#         if response.status_code == 500:
#             return "Ollama Server Error: Try restarting the Ollama app or using a smaller model like llama3.2:1b."
            
#         response.raise_for_status() 
#         return response.json().get("response", "AI returned an empty response.")

#     except Exception as e:
#         return f"System Error: {str(e)}"