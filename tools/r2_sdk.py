"""Optional persistent S3 read transport. Selection/atomic caching live in r2_assets."""
import os

from botocore.config import Config
from botocore.session import Session


class TransportError(Exception):
    pass


class SDKTransport:
    def __init__(self, endpoint, bucket):
        key, secret = os.environ.get('AWS_ACCESS_KEY_ID'), os.environ.get('AWS_SECRET_ACCESS_KEY')
        if not key or not secret:
            raise TransportError('SDK transport requires explicit AWS environment credentials')
        self.bucket = bucket
        self.closed = False
        try:
            # Per-session overrides: no profile/config/credential-file lookup and
            # no mutation of the process environment while downloads use threads.
            session = Session(session_vars={
                'profile': (None, None, None, None),
                'config_file': (None, None, os.devnull, None),
                'credentials_file': (None, None, os.devnull, None)})
            self.client = session.create_client('s3', endpoint_url=endpoint, region_name='auto',
                aws_access_key_id=key, aws_secret_access_key=secret,
                aws_session_token=os.environ.get('AWS_SESSION_TOKEN'),
                config=Config(signature_version='s3v4', max_pool_connections=4,
                    s3={'addressing_style': 'path'},
                    connect_timeout=10, read_timeout=60,
                    retries={'mode': 'standard', 'total_max_attempts': 3}))
        except Exception:
            raise TransportError('SDK client initialization failed') from None

    def list_page(self, prefix, token):
        args = {'Bucket': self.bucket, 'Prefix': prefix, 'MaxKeys': 1000}
        if token:
            args['ContinuationToken'] = token
        try:
            return self.client.list_objects_v2(**args)
        except Exception:
            raise TransportError('SDK object listing failed') from None

    def get_object(self, key, destination):
        try:
            response = self.client.get_object(Bucket=self.bucket, Key=key)
            body = response['Body']
            try:
                with open(destination, 'wb') as output:
                    while chunk := body.read(1024 * 1024):
                        output.write(chunk)
            finally:
                body.close()
            return {'ContentLength': response['ContentLength']}
        except Exception:
            raise TransportError('SDK object download failed') from None

    def close(self):
        if not self.closed:
            self.client.close()
            self.closed = True
