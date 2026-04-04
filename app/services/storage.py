"""Storage service for Supabase bucket operations."""

import httpx
from typing import BinaryIO

from app.config import get_settings

settings = get_settings()


class StorageService:
    """Service for Supabase Storage bucket operations."""
    
    def __init__(
        self,
        supabase_url: str | None = None,
        service_key: str | None = None
    ):
        """Initialize storage service.
        
        Args:
            supabase_url: Supabase project URL
            service_key: Service role key for authentication
        """
        self.supabase_url = supabase_url or settings.supabase_url
        self.service_key = service_key or settings.supabase_service_role_key
        self.storage_url = f"{self.supabase_url}/storage/v1"
    
    def _get_headers(self) -> dict[str, str]:
        """Get authorization headers."""
        return {
            "Authorization": f"Bearer {self.service_key}",
            "apikey": self.service_key,
        }
    
    async def upload(
        self,
        bucket: str,
        path: str,
        content: bytes,
        content_type: str = "application/octet-stream"
    ) -> str:
        """Upload a file to a storage bucket.
        
        Args:
            bucket: Bucket name
            path: Storage path within bucket
            content: File bytes
            content_type: MIME type
            
        Returns:
            Storage path
            
        Raises:
            httpx.HTTPStatusError: If upload fails
        """
        url = f"{self.storage_url}/object/{bucket}/{path}"
        
        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(
                url,
                headers={
                    **self._get_headers(),
                    "Content-Type": content_type,
                },
                content=content
            )
            
            if not response.is_success:
                error = response.json() if response.content else {}
                raise ValueError(f"Upload failed: {error.get('message', response.status_code)}")
            
            return path
    
    async def download(self, bucket: str, path: str) -> bytes:
        """Download a file from a storage bucket.
        
        Args:
            bucket: Bucket name
            path: Storage path within bucket
            
        Returns:
            File bytes
            
        Raises:
            httpx.HTTPStatusError: If download fails
        """
        url = f"{self.storage_url}/object/{bucket}/{path}"
        
        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.get(url, headers=self._get_headers())
            
            if not response.is_success:
                raise ValueError(f"Download failed: {response.status_code}")
            
            return response.content
    
    async def delete(self, bucket: str, paths: list[str]) -> None:
        """Delete files from a storage bucket.
        
        Args:
            bucket: Bucket name
            paths: List of storage paths to delete
            
        Raises:
            httpx.HTTPStatusError: If delete fails
        """
        url = f"{self.storage_url}/object/{bucket}"
        
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.delete(
                url,
                headers={
                    **self._get_headers(),
                    "Content-Type": "application/json",
                },
                json={"prefixes": paths}
            )
            
            if not response.is_success:
                error = response.json() if response.content else {}
                raise ValueError(f"Delete failed: {error.get('message', response.status_code)}")
    
    async def get_signed_url(
        self,
        bucket: str,
        path: str,
        expires_in: int = 3600
    ) -> str:
        """Get a signed URL for temporary file access.
        
        Args:
            bucket: Bucket name
            path: Storage path within bucket
            expires_in: URL expiration time in seconds
            
        Returns:
            Signed URL string
            
        Raises:
            httpx.HTTPStatusError: If signing fails
        """
        url = f"{self.storage_url}/object/sign/{bucket}/{path}"
        
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(
                url,
                headers={
                    **self._get_headers(),
                    "Content-Type": "application/json",
                },
                json={"expiresIn": expires_in}
            )
            
            if not response.is_success:
                raise ValueError(f"Signing failed: {response.status_code}")
            
            data = response.json()
            signed_url = data.get("signedURL", "")
            
            # Return full URL
            if signed_url.startswith("/"):
                return f"{self.supabase_url}{signed_url}"
            return signed_url
    
    async def list_files(
        self,
        bucket: str,
        prefix: str = "",
        limit: int = 100
    ) -> list[dict]:
        """List files in a storage bucket.
        
        Args:
            bucket: Bucket name
            prefix: Path prefix to filter by
            limit: Maximum number of files to return
            
        Returns:
            List of file metadata dicts
        """
        url = f"{self.storage_url}/object/list/{bucket}"
        
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                url,
                headers={
                    **self._get_headers(),
                    "Content-Type": "application/json",
                },
                json={
                    "prefix": prefix,
                    "limit": limit,
                }
            )
            
            if not response.is_success:
                return []
            
            return response.json()
