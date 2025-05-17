import os
import boto3
from typing import Dict, Any

class StorageService:
    def __init__(self):
        self.s3_client = boto3.client(
            's3',
            endpoint_url=os.getenv('DO_SPACES_ENDPOINT'),
            aws_access_key_id=os.getenv('DO_SPACES_KEY'),
            aws_secret_access_key=os.getenv('DO_SPACES_SECRET'),
            region_name=os.getenv('DO_SPACES_REGION')
        )
        self.bucket_name = os.getenv('DO_SPACES_BUCKET')

    async def upload_resume(self, file_content: bytes, filename: str) -> Dict[str, str]:
        """
        Upload a resume to DigitalOcean Spaces.
        """
        key = f"resumes/{filename}"
        self.s3_client.put_object(
            Bucket=self.bucket_name,
            Key=key,
            Body=file_content
        )

        # Generate a temporary URL for the file
        url = self.s3_client.generate_presigned_url(
            'get_object',
            Params={
                'Bucket': self.bucket_name,
                'Key': key
            },
            ExpiresIn=3600  # URL expires in 1 hour
        )

        return {
            "bucket": self.bucket_name,
            "key": key,
            "url": url
        }

    async def upload_text(self, text_content: str, key: str) -> Dict[str, str]:
        """
        Upload a text content to DigitalOcean Spaces.
        This is used for agent data files.
        """
        self.s3_client.put_object(
            Bucket=self.bucket_name,
            Key=key,
            Body=text_content,
            ContentType='text/plain',
            ACL='public-read'  # Make the file publicly accessible for the agent
        )

        # Generate a direct URL for the file
        url = f"https://{self.bucket_name}.{os.getenv('DO_SPACES_REGION')}.digitaloceanspaces.com/{key}"

        return {
            "bucket": self.bucket_name,
            "key": key,
            "url": url
        }

    async def delete_resume(self, resume_key: str) -> bool:
        """
        Delete a resume from DigitalOcean Spaces.
        """
        try:
            self.s3_client.delete_object(
                Bucket=self.bucket_name,
                Key=resume_key
            )
            return True
        except Exception:
            return False 