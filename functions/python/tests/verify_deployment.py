import requests
import json
import time

# Deployed Endpoints (based on logs)
# Project ID: ai-secretary-6e9c8
# Region: asia-northeast3
BASE_URL = "https://asia-northeast3-ai-secretary-6e9c8.cloudfunctions.net"
BUILD_GRAPH_URL = f"{BASE_URL}/rag_build_graph"
SEARCH_URL = f"{BASE_URL}/rag_search"

def test_build_graph():
    print(f"🚀 Testing rag_build_graph at {BUILD_GRAPH_URL}...")
    
    payload = {
        "user_id": "test_user_verifier",
        "text": """
        LightRAG is a retrieval-augmented generation system that combines vector search and knowledge graphs.
        It is designed to provide better context for LLMs by understanding relationships between entities.
        The system uses a graph storage to keep track of nodes and edges.
        """
    }
    
    try:
        response = requests.post(BUILD_GRAPH_URL, json=payload, timeout=600) # Long timeout for graph building
        print(f"Status Code: {response.status_code}")
        print(f"Response: {response.text}")
        
        if response.status_code == 200:
            print("✅ Build Graph Step Passed")
            return True
        else:
            print("❌ Build Graph Step Failed")
            return False
    except Exception as e:
        print(f"❌ Error during build graph: {e}")
        return False

def test_search():
    print(f"\n🔍 Testing rag_search at {SEARCH_URL}...")
    
    payload = {
        "user_id": "test_user_verifier",
        "query": "What is LightRAG and how does it work?"
    }
    
    try:
        response = requests.post(SEARCH_URL, json=payload, timeout=120)
        print(f"Status Code: {response.status_code}")
        # Truncate response for display
        resp_text = response.text
        display_text = resp_text[:500] + "..." if len(resp_text) > 500 else resp_text
        print(f"Response: {display_text}")
        
        if response.status_code == 200:
            data = response.json()
            if "context" in data and len(data["context"]) > 0:
                print("✅ Search Step Passed (Context received)")
                return True
            else:
                print("⚠️ Search Step Passed but context might be empty (Check GCS sync)")
                return True
        else:
            print("❌ Search Step Failed")
            return False
            
    except Exception as e:
        print(f"❌ Error during search: {e}")
        return False

if __name__ == "__main__":
    print("=== Starting Deployment Verification ===")
    if test_build_graph():
        print("\n⏳ Waiting 5 seconds before search...")
        time.sleep(5)
        test_search()
    else:
        print("\n⛔ Skipping search due to build failure.")
