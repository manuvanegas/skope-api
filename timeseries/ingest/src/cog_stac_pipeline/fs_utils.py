import os
from osgeo import gdal


def is_s3(path: str) -> bool:
    return str(path).startswith("s3://")


def to_vsi(path: str) -> str:
    """Converts s3://bucket/key to /vsis3/bucket/key for raw GDAL calls.

    rasterio-based calls (e.g. create_stac_item) handle s3:// natively and
    do not need this conversion. Only explicit gdal.* calls require it.
    """
    return path.replace("s3://", "/vsis3/", 1) if is_s3(path) else path


def path_exists(path: str) -> bool:
    """Returns True if the file exists locally or as an S3 object."""
    if is_s3(path):
        return gdal.VSIStatL(to_vsi(path)) is not None
    return os.path.isfile(path)


def makedirs(path: str) -> None:
    """Creates local directories. No-op for S3 (S3 has no real directories)."""
    if not is_s3(path):
        os.makedirs(path, exist_ok=True)


def read_text(path: str) -> str:
    """Reads a local file or an S3 object as text."""
    if is_s3(path):
        import boto3
        bucket, key = path[5:].split("/", 1)
        return boto3.client("s3").get_object(Bucket=bucket, Key=key)["Body"].read().decode()
    with open(path, encoding="utf-8") as f:
        return f.read()


def write_text(path: str, content: str) -> None:
    """Writes a string to a local file or an S3 object."""
    if is_s3(path):
        import boto3
        bucket, key = path[5:].split("/", 1)
        boto3.client("s3").put_object(Bucket=bucket, Key=key, Body=content.encode())
    else:
        with open(path, "w") as f:
            f.write(content)
