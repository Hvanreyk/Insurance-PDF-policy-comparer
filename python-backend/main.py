from fastapi import FastAPI, File, UploadFile, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import os
from dotenv import load_dotenv
from pdf_parser import parse_policy_pdf
from comparison import compare_policies

load_dotenv()

app = FastAPI(title="Insurance Policy Parser API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/")
async def root():
    return {"message": "Insurance Policy Parser API", "status": "running"}

@app.post("/api/parse-policy")
async def parse_policy(file: UploadFile = File(...)):
    """
    Parse an insurance policy PDF and extract structured data
    """
    if not file.filename.endswith('.pdf'):
        raise HTTPException(status_code=400, detail="Only PDF files are supported")

    try:
        contents = await file.read()

        policy_data = parse_policy_pdf(contents)

        return JSONResponse(content=policy_data)

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error parsing PDF: {str(e)}")

@app.post("/api/compare-policies")
async def compare_policies_endpoint(
    policy_a: UploadFile = File(...),
    policy_b: UploadFile = File(...)
):
    """
    Compare two insurance policies
    """
    try:
        contents_a = await policy_a.read()
        contents_b = await policy_b.read()

        policy_data_a = parse_policy_pdf(contents_a)
        policy_data_b = parse_policy_pdf(contents_b)

        comparison = compare_policies(policy_data_a, policy_data_b)

        return JSONResponse(content={
            "policy_a": policy_data_a,
            "policy_b": policy_data_b,
            "comparison": comparison
        })

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error comparing policies: {str(e)}")

if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)

# --- GCS helpers + GS endpoints ---
import os, base64, json
from datetime import timedelta
from pydantic import BaseModel
from google.cloud import storage
from google.oauth2 import service_account
import requests

def _gcs_client():
    sa = json.loads(base64.b64decode(os.environ["GCP_SA_JSON_BASE64"]))
    creds = service_account.Credentials.from_service_account_info(sa)
    return storage.Client(project=os.environ["GCP_PROJECT"], credentials=creds)

@app.post("/gcs/signed-url")
def gcs_signed_url(body: dict):
    """
    body = {"object_path":"pds-policies/policyA.pdf","method":"PUT"}
    Returns { "url": <signed_url>, "gs_uri":"gs://<bucket>/<object_path>" }
    """
    bucket = os.environ["GCS_BUCKET"]
    client = _gcs_client()
    blob = client.bucket(bucket).blob(body["object_path"])
    url = blob.generate_signed_url(
        version="v4",
        expiration=timedelta(minutes=30),
        method=body.get("method","PUT"),
    )
    return {"url": url, "gs_uri": f"gs://{bucket}/{body['object_path']}"}

class ParseGSReq(BaseModel):
    gs_uri: str

@app.post("/api/parse-gs")
def parse_gs(req: ParseGSReq):
    """
    Calls your existing extractor microservice that accepts {"file_uri": "gs://..."}
    Set EXTRACTOR_URL in Railway to that service's /extract/schedule endpoint.
    """
    extractor = os.environ["EXTRACTOR_URL"]
    r = requests.post(extractor, json={"file_uri": req.gs_uri})
    r.raise_for_status()
    return r.json()

class CompareGSReq(BaseModel):
    gs_uri_a: str
    gs_uri_b: str

@app.post("/api/compare-gs")
def compare_gs(req: CompareGSReq):
    """
    Minimal diff of limits by coverage name. Refine later.
    """
    extractor = os.environ["EXTRACTOR_URL"]
    a = requests.post(extractor, json={"file_uri": req.gs_uri_a}).json()
    b = requests.post(extractor, json={"file_uri": req.gs_uri_b}).json()

    def keyed(d): return { (i.get("coverage") or f"idx{i}"): i for i in d.get("limits",[]) }
    da, db = keyed(a), keyed(b)
    diff = {}
    for k in set(da)|set(db):
        va, vb = da.get(k), db.get(k)
        if va != vb: diff[k] = {"a": va, "b": vb}
    return {"a": req.gs_uri_a, "b": req.gs_uri_b, "diff": diff}
# --- end GCS block ---
