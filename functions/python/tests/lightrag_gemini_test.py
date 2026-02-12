import os
import asyncio
import numpy as np
import google.generativeai as genai
from lightrag import LightRAG, QueryParam
from lightrag.utils import EmbeddingFunc

# 1. Setup Gemini
if "GEMINI_API_KEY" not in os.environ:
    raise ValueError("GEMINI_API_KEY environment variable is not set")

genai.configure(api_key=os.environ["GEMINI_API_KEY"])

# 2. Custom Wrapper Functions
async def gemini_complete(prompt, system_prompt=None, history_messages=[], **kwargs) -> str:
    model_name = kwargs.get("hashing_kv", {}).global_config.get("llm_model_name", "gemini-2.5-flash")
    
    # Simple model mapping or use defaults
    if "gemini" not in model_name: 
        model_name = "gemini-2.5-flash" # Fallback
        
    model = genai.GenerativeModel(model_name)
    
    # Construct combined prompt
    full_prompt = ""
    if system_prompt:
        full_prompt += f"System: {system_prompt}\n\n"
    for msg in history_messages:
        full_prompt += f"{msg.get('role', 'User')}: {msg.get('content', '')}\n"
    full_prompt += f"User: {prompt}"
    
    try:
        response = await model.generate_content_async(full_prompt)
        return response.text
    except Exception as e:
        print(f"Gemini API Error: {e}")
        return ""

async def gemini_embed(texts: list[str]) -> np.ndarray:
    model = "models/text-embedding-004"
    try:
        # Batch embedding supported? google-generativeai usually supports batch
        result = await genai.embed_content_async(
            model=model,
            content=texts,
            task_type="retrieval_document"
        )
        return np.array(result['embedding'])
    except Exception as e:
        print(f"Gemini Embedding Error: {e}")
        # Return empty/dummy to prevent crash loop if one fails, but LightRAG might need valid shape
        return np.zeros((len(texts), 768)) 

# 3. Test Logic
WORKING_DIR = os.path.abspath("./lightrag_test_data")

async def run_test():
    print(f"📂 Working Directory: {WORKING_DIR}")
    if not os.path.exists(WORKING_DIR):
        os.makedirs(WORKING_DIR)

    # Initialize LightRAG
    print("⚙️ Initializing LightRAG with Custom Gemini Wrapper...")
    rag = LightRAG(
        working_dir=WORKING_DIR,
        llm_model_func=gemini_complete,
        llm_model_name="gemini-2.5-flash",
        embedding_func=EmbeddingFunc(
            embedding_dim=768,
            max_token_size=8192,
            func=gemini_embed
        ),
    )
    print("✅ LightRAG Initialized.")

    # Explicitly initialize storages (required for lightrag-hku)
    print("⚙️ Initializing Storages...")
    await rag.initialize_storages()
    print("✅ Storages Ready.")

    # Ensure storage is ready
    print(f"  - Storage type: {type(rag.key_string_value_json_storage_cls)}")

    # Test Data
    test_text = """
    Lee Jae-myung (born December 22, 1964) is a South Korean politician serving as the leader of the Democratic Party of Korea.
    He previously served as the 35th Governor of Gyeonggi Province from 2018 to 2021.
    The Democratic Party of Korea emphasizes economic democratization and peace on the Korean Peninsula.
    """

    # 4. Insert (Graph Building)
    print("🏗️ Inserting test text into Knowledge Graph...")
    try:
        await rag.ainsert(test_text)
        print("✅ Insertion Complete.")
    except Exception as e:
        import traceback
        traceback.print_exc()
        print(f"❌ Insertion Failed: {e}")
        return

    # 5. Check Output Files
    print("evaluating storage...")
    files = os.listdir(WORKING_DIR)
    print(f"📁 Files generated: {files}")
    
    total_size = sum(os.path.getsize(os.path.join(WORKING_DIR, f)) for f in files)
    print(f"📦 Total Storage Size: {total_size / 1024:.2f} KB")

    # 6. Test Hybrid Search
    print("🔍 Testing Hybrid Search...")
    query = "Who is the leader of the Democratic Party and what do they stand for?"
    
    # Standard Hybrid Search
    result = await rag.aquery(query, param=QueryParam(mode="hybrid"))
    print("\n📝 Search Result:")
    print(result[:500] + "..." if len(result) > 500 else result)
    
    # Context Only Mode (Check if supported or via workaround)
    # result_ctx = await rag.aquery(query, param=QueryParam(mode="hybrid", only_need_context=True))
    # print("\n📝 Context Only:")
    # print(result_ctx)

if __name__ == "__main__":
    asyncio.run(run_test())
