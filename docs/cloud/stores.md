# Cloud Stores

Chaser can write items directly to Amazon S3, Google Cloud Storage, or Parquet files. All three are pipeline stages — they slot in anywhere the standard `JsonlStore` would go.

## Amazon S3

`S3Store` accumulates items in a local temp file, then uploads it as a single object when the crawl finishes.

```bash
pip install "chaser[cloud]"
```

```python
from chaser.pipeline.store.s3 import S3Store

pipeline = Pipeline([
    S3Store("my-bucket", "crawls/run-001/items.jsonl")
])
```

Format is inferred from the key extension: `.parquet` → Parquet, everything else → JSONL.

```python
# Parquet output (requires chaser[parquet] as well)
S3Store("my-bucket", "crawls/run-001/items.parquet")
```

### Constructor parameters

| Parameter | Description |
|-----------|-------------|
| `bucket` | S3 bucket name |
| `key` | Object key (path within the bucket) |
| `endpoint_url` | Override endpoint — use for MinIO or other S3-compatible services |
| `region_name` | AWS region |
| `aws_access_key_id` | Explicit credentials (prefer IAM roles or env vars in production) |
| `aws_secret_access_key` | Explicit credentials |

### Authentication

By default `S3Store` uses the standard boto3 credential chain: `AWS_ACCESS_KEY_ID` / `AWS_SECRET_ACCESS_KEY` environment variables, `~/.aws/credentials`, or the instance IAM role. Explicit credentials in the constructor override the chain.

### S3-compatible storage (MinIO, Cloudflare R2, etc.)

```python
S3Store(
    "my-bucket",
    "items.jsonl",
    endpoint_url="http://minio:9000",
    aws_access_key_id="minioadmin",
    aws_secret_access_key="minioadmin",
)
```

## Google Cloud Storage

`GCSStore` works the same way — accumulate locally, upload on close.

```bash
pip install "chaser[cloud]"
```

```python
from chaser.pipeline.store.gcs import GCSStore

pipeline = Pipeline([
    GCSStore("my-bucket", "crawls/run-001/items.jsonl")
])
```

Format inference is identical to `S3Store`: `.parquet` → Parquet, otherwise JSONL.

### Constructor parameters

| Parameter | Description |
|-----------|-------------|
| `bucket` | GCS bucket name |
| `blob_name` | Object path within the bucket |
| `project` | GCP project ID (uses ADC project if omitted) |
| `credentials` | Explicit `google.oauth2.credentials.Credentials` object |

### Authentication

GCSStore uses [Application Default Credentials](https://cloud.google.com/docs/authentication/application-default-credentials). Set `GOOGLE_APPLICATION_CREDENTIALS` to a service account key file, or run `gcloud auth application-default login` for local development.

## Parquet (local)

For columnar output without uploading to cloud storage:

```bash
pip install "chaser[parquet]"
```

```python
from chaser.pipeline.store.parquet import ParquetStore

pipeline = Pipeline([ParquetStore("output.parquet")])
```

Items are buffered in memory and written to a single Parquet file on close. The schema is inferred from the items automatically using pyarrow.

## Combining stores

```python
pipeline = Pipeline([
    DuplicateFilter(key=lambda i: i.url),
    JsonlStore("local-backup.jsonl"),        # always write locally
    S3Store("my-bucket", "run/items.jsonl"), # and archive to S3
])
```
