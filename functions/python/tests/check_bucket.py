import firebase_admin
from firebase_admin import credentials, storage
import os

# Initialize with default credentials (should pick up from `GOOGLE_APPLICATION_CREDENTIALS` or similar if set, 
# otherwise we might need to rely on `gcloud auth application-default login`)
# Note: In this environment, we might rely on the existing auth context.

try:
    if not firebase_admin._apps:
        app = firebase_admin.initialize_app()
    
    # Try to list buckets via google-cloud-storage client directly if firebase_admin wrapper is limited
    from google.cloud import storage as gcs
    client = gcs.Client()
    
    print("Listing buckets:")
    for bucket in client.list_buckets():
        print(f"- {bucket.name}")
        
except Exception as e:
    print(f"Error listing buckets: {e}")
