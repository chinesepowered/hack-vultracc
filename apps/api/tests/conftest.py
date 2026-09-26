import os
import tempfile

_tmp = tempfile.mkdtemp(prefix="tieout-test-")
os.environ["DATABASE_URL"] = f"sqlite:///{_tmp}/test.db"
os.environ["LOCAL_STORAGE_DIR"] = f"{_tmp}/storage"
os.environ["S3_ENDPOINT"] = ""
os.environ["S3_ACCESS_KEY"] = ""
os.environ["S3_BUCKET"] = ""
os.environ["SESSION_SECRET"] = "test-secret"
os.environ["SANDBOX_RUNNER_URL"] = "http://127.0.0.1:9"
