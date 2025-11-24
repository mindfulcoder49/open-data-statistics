import os
import json
import io
from abc import ABC, abstractmethod
from typing import Any, List, Union
import boto3
from botocore.exceptions import ClientError
from fastapi.responses import FileResponse, StreamingResponse
import matplotlib.pyplot as plt
from app.config import settings

class StorageBackend(ABC):
    @abstractmethod
    def save_bytes(self, path: str, data: bytes) -> str: pass
    
    @abstractmethod
    def load_bytes(self, path: str) -> bytes: pass
    
    @abstractmethod
    def exists(self, path: str) -> bool: pass
    
    @abstractmethod
    def list_files(self, directory: str) -> List[str]: pass
    
    @abstractmethod
    def get_response(self, path: str, media_type: str): pass

class LocalStorage(StorageBackend):
    def __init__(self, base_dir: str):
        self.base_dir = base_dir
        os.makedirs(self.base_dir, exist_ok=True)

    def _full_path(self, path: str) -> str:
        return os.path.join(self.base_dir, path)

    def save_bytes(self, path: str, data: bytes) -> str:
        full_path = self._full_path(path)
        os.makedirs(os.path.dirname(full_path), exist_ok=True)
        with open(full_path, 'wb') as f:
            f.write(data)
        return full_path

    def load_bytes(self, path: str) -> bytes:
        with open(self._full_path(path), 'rb') as f:
            return f.read()

    def exists(self, path: str) -> bool:
        return os.path.exists(self._full_path(path))

    def list_files(self, directory: str) -> List[str]:
        full_dir = self._full_path(directory)
        if not os.path.exists(full_dir):
            return []
        return os.listdir(full_dir)

    def get_response(self, path: str, media_type: str):
        return FileResponse(self._full_path(path), media_type=media_type)

class S3Storage(StorageBackend):
    def __init__(self, bucket_name: str, region: str, access_key: str, secret_key: str):
        self.bucket_name = bucket_name
        self.s3_client = boto3.client(
            's3',
            region_name=region,
            aws_access_key_id=access_key,
            aws_secret_access_key=secret_key
        )

    def save_bytes(self, path: str, data: bytes) -> str:
        self.s3_client.put_object(Bucket=self.bucket_name, Key=path, Body=data)
        return f"s3://{self.bucket_name}/{path}"

    def load_bytes(self, path: str) -> bytes:
        response = self.s3_client.get_object(Bucket=self.bucket_name, Key=path)
        return response['Body'].read()

    def exists(self, path: str) -> bool:
        try:
            self.s3_client.head_object(Bucket=self.bucket_name, Key=path)
            return True
        except ClientError:
            return False

    def list_files(self, directory: str) -> List[str]:
        # Ensure directory ends with / for S3 prefixing
        prefix = directory if directory.endswith('/') else f"{directory}/"
        try:
            response = self.s3_client.list_objects_v2(Bucket=self.bucket_name, Prefix=prefix)
            if 'Contents' not in response:
                return []
            # Return just the filenames (keys relative to prefix)
            return [obj['Key'].replace(prefix, '') for obj in response['Contents']]
        except ClientError:
            return []

    def get_response(self, path: str, media_type: str):
        # Return a streaming response from S3
        try:
            file_obj = self.s3_client.get_object(Bucket=self.bucket_name, Key=path)
            return StreamingResponse(file_obj['Body'], media_type=media_type)
        except ClientError:
            return None

def get_backend() -> StorageBackend:
    if settings.STORAGE_TYPE == 's3':
        return S3Storage(
            bucket_name=settings.S3_BUCKET_NAME,
            region=settings.AWS_DEFAULT_REGION,
            access_key=settings.AWS_ACCESS_KEY_ID,
            secret_key=settings.AWS_SECRET_ACCESS_KEY
        )
    return LocalStorage(settings.RESULTS_DIR)

class JsonStorageModel:
    """Model for saving and retrieving JSON data (e.g., analysis results)."""
    def __init__(self):
        self.backend = get_backend()

    def save(self, job_id: str, filename: str, data: Any) -> str:
        path = f"{job_id}/{filename}"
        # Use default=str to handle dates/numpy types if not already handled
        json_bytes = json.dumps(data, indent=4, default=str).encode('utf-8')
        return self.backend.save_bytes(path, json_bytes)

    def load(self, job_id: str, filename: str) -> Any:
        path = f"{job_id}/{filename}"
        json_bytes = self.backend.load_bytes(path)
        return json.loads(json_bytes.decode('utf-8'))

    def exists(self, job_id: str, filename: str) -> bool:
        return self.backend.exists(f"{job_id}/{filename}")
    
    def list_artifacts(self, job_id: str) -> List[str]:
        return self.backend.list_files(job_id)

    def get_response(self, job_id: str, filename: str):
        return self.backend.get_response(f"{job_id}/{filename}", "application/json")

class ImageStorageModel:
    """Model for saving and retrieving Images (e.g., plots)."""
    def __init__(self):
        self.backend = get_backend()

    def save_plot(self, job_id: str, filename: str, fig: plt.Figure) -> str:
        path = f"{job_id}/{filename}"
        buf = io.BytesIO()
        fig.savefig(buf, format='png', bbox_inches='tight')
        buf.seek(0)
        plt.close(fig) # Close the figure to free memory
        return self.backend.save_bytes(path, buf.read())

    def exists(self, job_id: str, filename: str) -> bool:
        return self.backend.exists(f"{job_id}/{filename}")

    def get_response(self, job_id: str, filename: str):
        return self.backend.get_response(f"{job_id}/{filename}", "image/png")
