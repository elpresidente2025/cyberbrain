import os
import shutil
import logging
import asyncio
import numpy as np
import google.generativeai as genai
from lightrag import LightRAG, QueryParam
from lightrag.utils import EmbeddingFunc
from firebase_admin import storage

# Configure Logger
logger = logging.getLogger("rag_manager")
logger.setLevel(logging.INFO)

# Retry Configuration
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
from google.api_core import exceptions as google_exceptions

def is_retryable_error(exception):
    """Check if the error is a rate limit or transient error."""
    return isinstance(exception, (
        google_exceptions.TooManyRequests, 
        google_exceptions.ServiceUnavailable,
        google_exceptions.ResourceExhausted
    ))

WORKING_DIR = "/tmp/lightrag_data"
GCS_PREFIX = "lightrag_graph"

# --- Gemini Wrappers ---

@retry(
    retry=retry_if_exception_type(google_exceptions.ResourceExhausted) | retry_if_exception_type(google_exceptions.TooManyRequests),
    wait=wait_exponential(multiplier=2, min=4, max=60),
    stop=stop_after_attempt(5)
)
async def gemini_complete(prompt, system_prompt=None, history_messages=[], **kwargs) -> str:
    """Custom wrapper for Gemini to work with LightRAG LLM interface."""
    model_name = kwargs.get("hashing_kv", {}).global_config.get("llm_model_name", "gemini-2.5-flash")
    if "gemini" not in model_name:
        model_name = "gemini-2.5-flash"

    # LightRAG passes specific kwargs that might not match Gemini's expected params
    # e.g., 'hashing_kv' needs to be ignored if passed to generate_content
    
    try:
        model = genai.GenerativeModel(model_name)
        
        full_prompt = ""
        if system_prompt:
            full_prompt += f"System: {system_prompt}\n\n"
        for msg in history_messages:
            full_prompt += f"{msg.get('role', 'User')}: {msg.get('content', '')}\n"
        full_prompt += f"User: {prompt}"

        # Safety settings and generation config can be added here
        response = await model.generate_content_async(
            full_prompt,
            generation_config=genai.types.GenerationConfig(
                temperature=kwargs.get("temperature", 0.7),
                max_output_tokens=kwargs.get("max_tokens", 8192)
            )
        )
        return response.text
    except Exception as e:
        logger.error(f"Gemini LLM Error: {e}")
        # Return empty string or re-raise depending on strictness
        return ""

@retry(
    retry=retry_if_exception_type(google_exceptions.ResourceExhausted) | retry_if_exception_type(google_exceptions.TooManyRequests),
    wait=wait_exponential(multiplier=2, min=4, max=60),
    stop=stop_after_attempt(5)
)
async def gemini_embed(texts: list[str]) -> np.ndarray:
    """Custom wrapper for Gemini Embeddings."""
    model = "models/text-embedding-004"
    try:
        # Note: genai.embed_content accepts 'content' as list for batch
        result = await genai.embed_content_async(
            model=model,
            content=texts,
            task_type="retrieval_document" # or retrieval_query depending on context, using doc for general
        )
        # 'embedding' field in result contains list of embeddings
        embeddings = result['embedding']
        return np.array(embeddings)
    except Exception as e:
        logger.error(f"Gemini Embedding Error: {e}")
        # Return zero vectors on failure to preserve shape
        return np.zeros((len(texts), 768))

# --- GCS Sync Functions ---

def download_graph_from_gcs(bucket_name: str):
    """Downloads LightRAG graph files from GCS to local tmp."""
    if not os.path.exists(WORKING_DIR):
        os.makedirs(WORKING_DIR)
        
    logger.info(f"Downloading graph from GCS bucket: {bucket_name}, prefix: {GCS_PREFIX}")
    bucket = storage.bucket(bucket_name)
    blobs = bucket.list_blobs(prefix=GCS_PREFIX)
    
    count = 0
    for blob in blobs:
        # Filename: lightrag_graph/kv_store_... -> /tmp/lightrag_data/kv_store_...
        filename = os.path.basename(blob.name)
        if not filename: continue # directory marker
        
        local_path = os.path.join(WORKING_DIR, filename)
        blob.download_to_filename(local_path)
        count += 1
    
    logger.info(f"Downloaded {count} files from GCS {bucket_name}/{GCS_PREFIX}")

def upload_graph_to_gcs(bucket_name: str):
    """Uploads local LightRAG graph files to GCS."""
    if not os.path.exists(WORKING_DIR):
        logger.warning(f"Working dir {WORKING_DIR} does not exist, nothing to upload.")
        return

    logger.info(f"Uploading graph to GCS bucket: {bucket_name}, prefix: {GCS_PREFIX}")
    bucket = storage.bucket(bucket_name)
    files = os.listdir(WORKING_DIR)
    
    count = 0
    for f in files:
        local_path = os.path.join(WORKING_DIR, f)
        if os.path.isfile(local_path):
            blob_path = f"{GCS_PREFIX}/{f}"
            blob = bucket.blob(blob_path)
            blob.upload_from_filename(local_path)
            count += 1
            
    logger.info(f"Uploaded {count} files to GCS {bucket_name}/{GCS_PREFIX}")

# --- Manager Class ---

class LightRAGManager:
    def __init__(self, bucket_name: str, model_name="gemini-2.5-flash"):
        self.bucket_name = bucket_name
        self.model_name = model_name
        self.rag = None

    async def initialize(self, mode="read"):
        """Initializes LightRAG instance.
        mode='read': Downloads existing graph.
        mode='write': Downloads existing graph (to append).
        """
        # 1. Download existing data
        # Check if we are in a fresh container or reused one.
        # Ideally, always sync from GCS to be safe or check consistency.
        # For 'read', minimal download cost. For 'write', mandatory to get latest state.
        try:
            download_graph_from_gcs(self.bucket_name)
        except Exception as e:
            logger.warning(f"Failed to download graph (might be first run): {e}")

        # 2. Init LightRAG
        self.rag = LightRAG(
            working_dir=WORKING_DIR,
            llm_model_func=gemini_complete,
            llm_model_name=self.model_name,
            embedding_func=EmbeddingFunc(
                embedding_dim=768,
                max_token_size=8192,
                func=gemini_embed
            ),
             # Optional: Configure storage classes if needed, defaults are usually fine
        )
        
        # 3. Explicitly init storages (Crucial fix from testing)
        await self.rag.initialize_storages()
        logger.info(f"LightRAG initialized in {WORKING_DIR} (Model: {self.model_name})")
        return self.rag

    def persist(self):
        """Uploads current state to GCS."""
        upload_graph_to_gcs(self.bucket_name)
